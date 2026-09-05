# Tasks: SP5 — Retention Automation (Firestore TTL & Anonymous User Cleanup)

Source PRD: `.dev/trial-simplify/05-retention-automation/PRD.md`. All decisions below
trace to PRD §4 (Architecture Decisions); §9 is fully `[RESOLVED]`/`[DEFERRED]` — no
`[OPEN]` items block this work. **Q5** (persisting a `next_page_token` cursor across
runs) and **Q6** (an explicit lock against overlapping runs) are `[DEFERRED]` — no tasks
below implement either; do not add locking or cursor-persistence code while doing this
work. Order matches dependency order; each task is committable on its own.

**This SP activates destructive automation** (Firestore TTL deletion, Firebase Auth
account deletion). Every dev task below either builds code that defaults to safe
(dry-run) behavior, or is pure infrastructure config that ships in an inert/off state.
**No task in this file flips `RETENTION_DRY_RUN` to `false`, runs the
`gcloud firestore fields ttls update` commands, creates the Cloud Run Job/Scheduler, or
applies the GCS lifecycle rule** — those are one-time, human-run `gcloud`/`gsutil`
commands against the live project, listed in dependency order in the "Summary of what
requires you" section at the end of this file (PRD §8 / the initiative
`.dev/trial-simplify/README.md`'s "CI & IAM setup checklist").

**Cross-SP boundaries respected in this file:** no changes to `backend/routes/trial.py`,
`backend/utils/rate_limit.py`, or `backend/models/job.py` (SP2's territory — this PRD
only acts on the `expires_at` field SP2 already writes, per PRD §3 non-goals). No
Firestore security-rules changes. No changes to `04-hosting-split-and-legal/` — another
agent owns that PRD's `TASKS.md`; where this file touches `.github/workflows/deploy.yml`
(Task 6), it adds a new step to the existing `deploy-backend` job only — it does not
touch `deploy-frontend`, `tag`, hosting-target config, or CORS, all of which are SP4's.
No Terraform/IaC (PRD §9 Q7). No regression test guarding non-trial `care_plan_outputs`
docs against acquiring a non-null `expires_at` (PRD §9 Q2) — the PRD explicitly
recommends this but assigns it to SP2's own test suite, not to this PRD; it is **not** a
task here and is flagged again in the summary so it isn't lost.

---

### Task 1 — Add a `Retention` marker leaf to `backend/utils/markers/markers.py`

   - Files: `backend/utils/markers/markers.py`
   - Changes: Per PRD §4.9, add a new top-level nested class, alongside the existing
     `Batch`/`Trial`/`Worker`/`SavedOutputs`/`Firestore` classes (append after the
     `Firestore` class at the end of the file):
     ```python
     class Retention:
         @code_marker("retention.anon_user_cleanup")
         class AnonUserCleanup(CodeMarker): pass
     ```
     This mirrors the existing `Trial` class's shape exactly (a single-purpose nested
     class with one `@code_marker`-decorated leaf). Do not modify any existing class in
     this file.
   - Acceptance criteria:
     - `python -c "from utils.markers.markers import Markers; print(Markers.Retention.AnonUserCleanup.name())"` prints `retention.anon_user_cleanup`.
     - `git diff backend/utils/markers/markers.py` shows only an addition at the end of
       the file — no existing lines changed.

---

### Task 2 — New file `backend/services/retention.py` (core cleanup logic)

   - Files: `backend/services/retention.py` (new)
   - Changes: Per PRD §4.5, create this file with exactly the following content (this is
     safety-critical code — the anonymous-account predicate must never match a real,
     password-authenticated account; copy it verbatim rather than paraphrasing):
     ```python
     """services/retention.py — anonymous Firebase Auth account cleanup.

     Deletes anonymous Auth accounts older than a configurable age. Safety-critical:
     the predicate below must never match a real (password/other-provider) account.
     Called by scripts/cleanup_anonymous_users.py, which is the Cloud Run Job's
     entrypoint; kept here (not in scripts/) so it's importable and mockable from
     backend/tests/services/ like every other service module.
     """
     import logging
     from dataclasses import dataclass, field
     from datetime import datetime, timezone, timedelta

     from firebase_admin import auth

     logger = logging.getLogger(__name__)

     DEFAULT_MAX_AGE_HOURS = 24
     DEFAULT_PAGE_SIZE = 1000          # auth.list_users' own page-size ceiling


     @dataclass
     class CleanupSummary:
         scanned: int = 0
         matched: int = 0
         deleted: int = 0
         delete_errors: int = 0
         pages: int = 0
         dry_run: bool = False
         error_uids: list[str] = field(default_factory=list)


     def _is_anonymous(user: "auth.ExportedUserRecord") -> bool:
         """True only if the account has NO linked sign-in providers. Password-auth
         accounts (frontend/src/pages/LoginPage.tsx's signInWithEmailAndPassword,
         the ONLY other sign-in method this project uses) always carry a
         provider_data entry with provider_id == 'password' — never empty. An
         anonymous account created via signInAnonymously() (D1, the trial's only
         auth path) has provider_data == [] by Firebase's own design. If a real
         account somehow ever has empty provider_data (e.g. every provider was
         unlinked via the Admin SDK, which — unlike the client SDK — does not
         block removing the last provider), this predicate would incorrectly treat
         it as anonymous; there is no additional signal available from
         ExportedUserRecord to distinguish that case. This is the one residual
         risk in this design — [RESOLVED: accepted risk per user 2026-09-05, no
         additional guard] — see PRD §9 Q4. The defensive age check below
         (_older_than) and the dry-run gate (§7, §8 item 2) remain as-is; nothing
         further is added to engineer around this edge case."""
         return len(user.provider_data) == 0


     def _older_than(user: "auth.ExportedUserRecord", cutoff_ms: int) -> bool:
         return user.user_metadata.creation_timestamp < cutoff_ms


     def cleanup_anonymous_users(
         *,
         max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
         dry_run: bool = True,
         now: datetime | None = None,
     ) -> CleanupSummary:
         """Delete (or, if dry_run, just count) anonymous accounts older than
         max_age_hours. Paginates list_users at 1000/page; batches delete_users at
         <=1000 uids/call (one call per page, since a page is already <=1000).
         No persisted cursor — see PRD §4.5 for why a full re-sweep per run is the
         chosen resumption strategy instead."""
         now = now or datetime.now(timezone.utc)
         cutoff_ms = int((now - timedelta(hours=max_age_hours)).timestamp() * 1000)
         summary = CleanupSummary(dry_run=dry_run)

         page = auth.list_users(max_results=DEFAULT_PAGE_SIZE)
         while page:
             summary.pages += 1
             summary.scanned += len(page.users)
             matched_uids = [
                 u.uid for u in page.users
                 if _is_anonymous(u) and _older_than(u, cutoff_ms)
             ]
             summary.matched += len(matched_uids)

             if matched_uids and not dry_run:
                 result = auth.delete_users(matched_uids)
                 summary.deleted += len(matched_uids) - len(result.errors)
                 summary.delete_errors += len(result.errors)
                 for err in result.errors:
                     summary.error_uids.append(matched_uids[err.index])
                     logger.warning(
                         "retention: failed to delete anon user index=%d reason=%s",
                         err.index, err.reason,
                     )
             elif matched_uids:
                 summary.deleted += len(matched_uids)  # dry-run: "would delete"

             page = page.get_next_page()

         logger.info(
             "retention: anon user cleanup complete scanned=%d matched=%d deleted=%d "
             "errors=%d pages=%d dry_run=%s",
             summary.scanned, summary.matched, summary.deleted,
             summary.delete_errors, summary.pages, summary.dry_run,
         )
         return summary
     ```
   - Acceptance criteria:
     - `python -c "from services.retention import cleanup_anonymous_users, CleanupSummary, DEFAULT_MAX_AGE_HOURS; print(DEFAULT_MAX_AGE_HOURS)"` prints `24` with no import error.
     - This file imports nothing from `flask`, `routes/`, or `app.py` — it has no Flask
       dependency, per PRD §4.5's stated design goal of unit-testability.
     - No other file is touched by this task.

---

### Task 3 — New test file `backend/tests/services/test_retention.py`

   - Files: `backend/tests/services/test_retention.py` (new)
   - Changes: Per PRD §7, write tests against `services/retention.py` using
     `unittest.mock`/`monkeypatch`, mirroring the mocking style already used in
     `backend/tests/utils/test_gcs.py` (patch the module's imported name, e.g.
     `monkeypatch.setattr("services.retention.auth", mock_auth)`) — this test suite must
     never touch a real Firebase Auth user pool. Build small helper factories for a fake
     `ExportedUserRecord`-shaped object (a `SimpleNamespace` or tiny dataclass with
     `.uid`, `.provider_data` (list of objects with `.provider_id`), and
     `.user_metadata.creation_timestamp` (int, ms)) and a fake page object exposing
     `.users` (list) and `.get_next_page()` (callable). Cover, at minimum:
     - `_is_anonymous`: `True` for `provider_data == []`; `False` for a record with one
       or more provider entries (e.g. `provider_id="password"`).
     - `_older_than`: correctly compares `creation_timestamp` (ms) against a cutoff
       derived from a fixed, injected `now` passed through `cleanup_anonymous_users`.
     - `cleanup_anonymous_users(dry_run=True)`: mock `auth.list_users` to return a single
       page of four mixed users (anonymous+old, anonymous+new, real+old, real+new).
       Assert `matched == 1` (only anonymous+old), `deleted == 1` (dry-run "would
       delete" count), and that the mocked `auth.delete_users` is **never called**.
     - `cleanup_anonymous_users(dry_run=False)`: same fixture. Assert `auth.delete_users`
       is called exactly once, with exactly the matched uid(s) (never the real or
       too-young ones). Also assert: when the mocked `delete_users` return value carries
       one `.errors` entry (an object with `.index` and `.reason`), `delete_errors == 1`
       and that uid appears in `error_uids`, without the call raising.
     - **Real-account safety, explicit regression guard:** a fixture where every "real"
       user has non-empty `provider_data` and is older than 24h — assert none of them
       ever appear in `matched`. Name this test something explicit like
       `test_real_users_never_matched_regardless_of_age` — this is the one property that
       must never regress.
     - **Pagination:** mock `auth.list_users` to return a page whose `get_next_page()`
       returns a second page once, then `None`. Assert `auth.delete_users` is called
       once per page containing matches (not once for the whole run), and that
       `scanned`/`matched`/`pages` sum correctly across both pages.
     - **Empty result set:** a mocked page with zero users — assert
       `scanned == matched == deleted == 0` and no exception is raised.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/services/test_retention.py -q` passes, with
       every test above present and green.
     - No test in this file imports `firebase_admin` unmocked in a way that would attempt
       a real network call (grep the file for `auth.list_users(` / `auth.delete_users(`
       outside of `monkeypatch.setattr`/mock assertions — there should be none).

---

### Task 4 — New Cloud Run Job entrypoint `backend/scripts/cleanup_anonymous_users.py`

   - Files: `backend/scripts/__init__.py` (new, empty — matches the existing
     `routes/__init__.py`/`services/__init__.py`/`utils/__init__.py` convention of an
     explicit package marker rather than relying on Python's implicit namespace
     packages), `backend/scripts/cleanup_anonymous_users.py` (new)
   - Changes: Per PRD §4.5, this is the thin CLI entrypoint the Cloud Run Job's
     `--command=python --args="-m,scripts.cleanup_anonymous_users"` override runs.
     Content, verbatim:
     ```python
     """scripts/cleanup_anonymous_users.py — Cloud Run Job entrypoint.

     Invoked daily by Cloud Scheduler via the Cloud Run Jobs `:run` API (PRD §4.7).
     Reads DRY_RUN from the environment so the job can be deployed once in
     dry-run mode and flipped to live later without a code change (mirrors the
     WORKER_VERIFY_OIDC kill-switch pattern in utils/firebase.py).
     """
     import logging
     import os
     import sys

     from utils.firebase import initialize_firebase
     from observability import setup_logging
     from utils.markers.markers import Markers
     from services.retention import cleanup_anonymous_users

     setup_logging()
     logger = logging.getLogger(__name__)


     def _dry_run_from_env() -> bool:
         return os.environ.get("RETENTION_DRY_RUN", "true").lower() not in ("false", "0", "no")


     def main() -> int:
         initialize_firebase()
         dry_run = _dry_run_from_env()

         def _run(scope):
             summary = cleanup_anonymous_users(dry_run=dry_run)
             scope.add_many({
                 "scanned": summary.scanned,
                 "matched": summary.matched,
                 "deleted": summary.deleted,
                 "delete_errors": summary.delete_errors,
                 "dry_run": summary.dry_run,
             })
             return summary

         summary = Markers.Retention.AnonUserCleanup.execute(_run)
         if summary.delete_errors:
             logger.warning("retention: completed with %d delete errors — see prior warnings", summary.delete_errors)
         return 0  # non-zero would trigger a Cloud Run Job retry; partial failure is not fatal (§4.9)


     if __name__ == "__main__":
         sys.exit(main())
     ```
     Note: the PRD's §4.5 code listing inlines the `os.environ.get(...)` check directly
     in `main()`; this task factors it into `_dry_run_from_env()` purely so Task 5 can
     unit-test the env-var-parsing behavior without invoking Firebase or Firestore. This
     is a non-substantive refactor of the PRD's own snippet, not a behavior change — the
     three-way `"false"/"0"/"no"` (case-insensitive) → `False`, everything else
     (including unset) → `True` logic is unchanged. The marker wiring
     (`Markers.Retention.AnonUserCleanup.execute(...)` with `scope.add_many(...)`) is per
     PRD §4.9, added here since the PRD's §4.5 code listing predates §4.9's marker design
     and doesn't show the wiring inline — follow §4.9's instruction, not §4.5's
     unmarked `return 0` literally.
   - Acceptance criteria:
     - `cd backend && python -c "import scripts.cleanup_anonymous_users as m; print(m._dry_run_from_env.__name__)"` imports with no error (Firebase is not initialized at import time — only inside `main()`).
     - `cd backend && RETENTION_DRY_RUN=false python -c "import os; os.environ['RETENTION_DRY_RUN']='false'; from scripts.cleanup_anonymous_users import _dry_run_from_env; print(_dry_run_from_env())"` prints `False`; unset or `RETENTION_DRY_RUN=true` prints `True`.
     - `backend/scripts/__init__.py` exists and is empty (or docstring-only).

---

### Task 5 — New test file `backend/tests/scripts/test_cleanup_anonymous_users.py`

   - Files: `backend/tests/scripts/__init__.py` (new, empty), `backend/tests/scripts/test_cleanup_anonymous_users.py` (new)
   - Changes: Per PRD §7's continuation ("`cleanup_anonymous_users.py::main()` reads
     `RETENTION_DRY_RUN` from the environment correctly ... and returns 0 even when
     `delete_errors > 0`"). Placed in a new `tests/scripts/` directory mirroring
     `scripts/`, consistent with how `tests/routes/`, `tests/models/`, `tests/services/`,
     `tests/utils/` each mirror their non-test counterpart.
     - `_dry_run_from_env`: parametrize over `{"": True, "true": True, "TRUE": True,
       "false": False, "0": False, "no": False, "1": True}` (unset env var, and each
       string value) via `monkeypatch.setenv`/`monkeypatch.delenv`.
     - `main()`: `monkeypatch.setattr("scripts.cleanup_anonymous_users.initialize_firebase", lambda: None)`
       and `monkeypatch.setattr("scripts.cleanup_anonymous_users.cleanup_anonymous_users", lambda dry_run: CleanupSummary(dry_run=dry_run, delete_errors=2))`
       (import `CleanupSummary` from `services.retention`) — assert `main()` returns `0`
       even though `delete_errors=2` (per §4.6, partial failure is non-fatal and must
       never make the Cloud Run Job retry). Assert a warning is logged when
       `delete_errors > 0` (`caplog` at `WARNING` level) and not logged when
       `delete_errors == 0`.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/scripts/test_cleanup_anonymous_users.py -q`
       passes.
     - No test in this file calls the real `firebase_admin.initialize_app` or
       `services.retention.cleanup_anonymous_users` (both are monkeypatched away).

---

### Task 6 — `.github/workflows/deploy.yml`: ongoing Cloud Run Job sync step

   - Files: `.github/workflows/deploy.yml`
   - **This file is shared with SP4's task list** (SP4 adds `deploy-frontend`-adjacent
     hosting-target jobs elsewhere in the same file). This task touches only the
     `deploy-backend` job, appending one new step — do not reorder, remove, or edit any
     existing step, and do not touch `deploy-frontend` or `tag`.
   - Changes: Per PRD §4.7's "Ongoing sync via `deploy.yml`", add a new step at the end
     of the `deploy-backend` job (after the existing "Configure juno-worker env vars and
     secrets" step, which is currently the job's last step):
     ```yaml
       - name: Deploy anonymous-user-cleanup Cloud Run Job
         run: |
           gcloud run jobs deploy juno-trial-anon-cleanup \
             --image="$BACKEND_IMAGE" \
             --region="$GCP_REGION" \
             --project="$GCP_PROJECT_ID" \
             --command=python \
             --args="-m,scripts.cleanup_anonymous_users" \
             --update-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,FIRESTORE_DATABASE_ID=(default)" \
             --update-secrets="FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest" \
             --task-timeout=1800 \
             --max-retries=0 \
             --memory=512Mi \
             --cpu=1
     ```
     `$BACKEND_IMAGE`, `$GCP_REGION`, and `$GCP_PROJECT_ID` are already defined as
     job-level `env:` on `deploy-backend` (used by the existing "Build, push, and deploy
     juno-api + juno-worker" step) — no new env vars need to be added to this job for
     this step to resolve them.

     **Use `--update-env-vars`/`--update-secrets` (merge), not `--set-env-vars`/
     `--set-secrets` (replace).** This is deliberate per PRD §4.7: this step must never
     clobber the operator-controlled `RETENTION_DRY_RUN` flag back to its image-default
     `true` on every ordinary code deploy — `--update-env-vars` only touches the two keys
     listed, leaving `RETENTION_DRY_RUN` (set once, manually, outside this step per the
     manual-steps summary below) untouched on every subsequent deploy.

     **This step does not create the Cloud Run Job** — `gcloud run jobs deploy` against a
     job that doesn't exist yet fails; it only keeps an *already-created* job's image and
     resource limits in sync on every deploy, exactly like `02-trial-backend/TASKS.md`
     Task 17's Cloud Tasks queue step keeps that resource in sync. The one-time creation
     (§4.7's `gcloud run jobs deploy` with `--set-env-vars`/`--set-secrets`, and §4.8's
     Cloud Scheduler/IAM setup) is a human-run step — see the summary at the end of this
     file. **Do not add a `|| echo "already exists"` fallback to this step** — unlike
     SP2's queue-creation step, this one is expected to genuinely fail on every deploy
     until the human-run one-time creation has happened; that failure is a correct,
     informative CI signal (not a queue-style idempotent-create-or-noop), so leave it
     failing loud until the one-time step is done.
   - Acceptance criteria:
     - `grep -n "juno-trial-anon-cleanup\|scripts.cleanup_anonymous_users" .github/workflows/deploy.yml`
       shows the new step.
     - `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
       succeeds with no parse error.
     - `git diff .github/workflows/deploy.yml` shows an addition only — confined to one
       new step appended inside `deploy-backend`; `deploy-frontend` and `tag` are
       byte-for-byte unchanged.

---

### Task 7 — Run the SP5-scoped test files and fix any regressions

   - Files: any file that fails — diagnose before editing; do not touch files outside
     this SP's scope (Tasks 1–6's files) without a clear regression reason.
   - Changes / steps: Per project convention (see `02-trial-backend/TASKS.md` Task 18),
     run only the test files this SP touched or extended — not the full backend suite:
     ```bash
     cd backend && python -m pytest \
       tests/utils/test_markers.py \
       tests/utils/test_code_markers.py \
       tests/services/test_retention.py \
       tests/scripts/test_cleanup_anonymous_users.py \
       -q
     ```
     For each failure, read the traceback and fix with a minimal targeted edit; re-run
     until green.
   - Acceptance criteria:
     - The command above exits 0 (all listed test files pass).
     - `git diff --stat` shows changes confined to: `backend/utils/markers/markers.py`,
       `backend/services/retention.py` (new), `backend/tests/services/test_retention.py`
       (new), `backend/scripts/__init__.py` (new),
       `backend/scripts/cleanup_anonymous_users.py` (new),
       `backend/tests/scripts/__init__.py` (new),
       `backend/tests/scripts/test_cleanup_anonymous_users.py` (new),
       `.github/workflows/deploy.yml` — nothing else.
     - `RETENTION_DRY_RUN` does not appear set to `false` anywhere in this diff (grep
       `.github/workflows/deploy.yml` and both new `scripts/` files to confirm — this SP
       ships the kill-switch code, never flips it).

---

## Summary of what requires you (not a dev agent)

Every item below is destructive-infrastructure setup or a decision no coding task
performs. They are listed in the dependency order they must actually be run in — this
list is the same one already consolidated in
`.dev/trial-simplify/README.md` ("Consolidated Manual Steps") and spelled out in full,
copy-pasteable form in `05-retention-automation/PRD.md` §8's "CI & IAM setup checklist"
(around line 810); this summary exists so you don't have to hunt for it.

1. **Enable Firestore TTL on both collections (PRD §4.1, §8 item 3) — run once, then
   verify `ACTIVE`:**
   ```bash
   export GCP_PROJECT_ID=juno-medical-clarity

   gcloud firestore fields ttls update expires_at \
     --collection-group=care_plan_outputs --database="(default)" \
     --enable-ttl --project="$GCP_PROJECT_ID"
   gcloud firestore fields ttls update expires_at \
     --collection-group=trial_rate_limits --database="(default)" \
     --enable-ttl --project="$GCP_PROJECT_ID"

   # Verify — state should read ACTIVE (may take time to transition from CREATING):
   gcloud firestore fields ttls describe expires_at \
     --collection-group=care_plan_outputs --database="(default)" --project="$GCP_PROJECT_ID"
   gcloud firestore fields ttls describe expires_at \
     --collection-group=trial_rate_limits --database="(default)" --project="$GCP_PROJECT_ID"
   ```
   **Note the corrected flag:** the project's first attempt at this command failed with
   `ERROR: (gcloud.firestore.fields.ttls.update) Exactly one of (--disable-ttl |
   [--enable-ttl : --expiration-offset]) must be specified.` — the commands above include
   the required `--enable-ttl` flag that was missing before.
   If this errors on IAM, grant `roles/datastore.owner` to your own identity (not CI's
   `GCP_SA_KEY`) and re-run:
   ```bash
   gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
     --member="user:YOUR_EMAIL@example.com" --role="roles/datastore.owner"
   ```

2. **Create the anonymous-cleanup Cloud Run Job once, with `RETENTION_DRY_RUN=true`**
   (PRD §4.7, §8 item 4) — after Task 6 has been merged and at least one deploy has run
   (so `scripts/cleanup_anonymous_users.py` exists in the image `$BACKEND_IMAGE` points
   at):
   ```bash
   export GCP_REGION=us-central1

   gcloud run jobs deploy juno-trial-anon-cleanup \
     --image="us-central1-docker.pkg.dev/$GCP_PROJECT_ID/juno/simplify-backend:latest" \
     --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
     --command=python --args="-m,scripts.cleanup_anonymous_users" \
     --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,FIRESTORE_DATABASE_ID=(default),RETENTION_DRY_RUN=true" \
     --set-secrets="FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest" \
     --task-timeout=1800 --max-retries=0 --memory=512Mi --cpu=1
   ```
   From this point on, Task 6's `deploy.yml` step keeps this Job's image/resources in
   sync automatically on every subsequent deploy, without ever touching
   `RETENTION_DRY_RUN`.

3. **Set up Cloud Scheduler → the Job above, once** (PRD §4.8, §8 item 4):
   ```bash
   gcloud iam service-accounts create juno-scheduler-invoker \
     --project="$GCP_PROJECT_ID" \
     --display-name="Cloud Scheduler -> Cloud Run Jobs invoker"

   gcloud run jobs add-iam-policy-binding juno-trial-anon-cleanup \
     --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
     --member="serviceAccount:juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/run.invoker"

   gcloud scheduler jobs create http juno-trial-anon-cleanup-trigger \
     --location="$GCP_REGION" --project="$GCP_PROJECT_ID" \
     --schedule="0 9 * * *" \
     --uri="https://$GCP_REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$GCP_PROJECT_ID/jobs/juno-trial-anon-cleanup:run" \
     --http-method=POST \
     --oauth-service-account-email="juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com"
   ```
   Per the initiative README, this step was previously blocked on the Cloud Scheduler API
   not being enabled on the project — confirm it's enabled first
   (`gcloud services enable cloudscheduler.googleapis.com --project="$GCP_PROJECT_ID"`)
   if the `jobs create` command errors with an API-disabled message.

4. **Trigger one real dry-run and review its log output before going live** (PRD §7, §8
   item 2) — this is the closest thing to an integration test this feature gets, and it
   is a required gate, not optional:
   ```bash
   gcloud run jobs execute juno-trial-anon-cleanup --region="$GCP_REGION" --project="$GCP_PROJECT_ID"
   ```
   Then read the structured summary log line in Cloud Logging
   (`jsonPayload.operation="retention.anon_user_cleanup"`) and confirm `scanned`/
   `matched` look plausible for actual trial traffic volume — not wildly higher, which
   would suggest the anonymous predicate is matching more broadly than intended. If the
   run instead surfaces a permission error calling `auth.list_users`/`auth.delete_users`,
   grant the existing `firebase-service-account` identity the Firebase Authentication
   Admin role (find its email via the JSON key's `client_email` field, or
   `gcloud iam service-accounts list --project="$GCP_PROJECT_ID"`):
   ```bash
   gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
     --member="serviceAccount:FIREBASE_SERVICE_ACCOUNT_EMAIL" \
     --role="roles/firebaseauth.admin"
   ```
   then re-run the dry-run execution above.

5. **Only after step 4 looks right — flip `RETENTION_DRY_RUN` to `false`** (PRD §8 item
   2). This is a deliberate one-time manual step, never automated by `deploy.yml`
   (Task 6 explicitly preserves this flag across deploys via `--update-env-vars`) —
   destructive-by-design behavior should never silently activate itself:
   ```bash
   gcloud run jobs update juno-trial-anon-cleanup \
     --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
     --update-env-vars=RETENTION_DRY_RUN=false
   ```

6. **Add the GCS lifecycle rule on the `care_plan_trial/` prefix, once** (PRD §4.10, §8
   item 7) — safe now that trial uploads have their own distinct prefix (SP2 §9 Q15).
   Inspect the bucket's existing lifecycle config first; merge rather than overwrite if
   it already has other rules (e.g. storage-class transitions):
   ```bash
   gsutil lifecycle get gs://juno-medical-clarity-backend > /tmp/existing-lifecycle.json

   cat > /tmp/trial-lifecycle-rule.json <<'EOF'
   {"rule":[{"action":{"type":"Delete"},"condition":{"age":1,"matchesPrefix":["care_plan_trial/"]}}]}
   EOF
   gsutil lifecycle set /tmp/trial-lifecycle-rule.json gs://juno-medical-clarity-backend
   ```
   Verify: `gsutil lifecycle get gs://juno-medical-clarity-backend` shows the
   `care_plan_trial/` rule present. Optionally confirm behaviorally: upload a throwaway
   object to `care_plan_trial/test-uid/inputs/test.pdf`, confirm it disappears after the
   1-day age window, while a control object under `care_plan/` does not.

7. **Optional, not blocking launch: set up two Cloud Monitoring alerting policies** (PRD
   §4.9, §8 item 6) — console-configured, no `gcloud`/code:
   - A log-based alert on `jsonPayload.operation="retention.anon_user_cleanup" AND
     jsonPayload.OpOutcome="Failed"`.
   - Cloud Scheduler's own built-in execution-failure notification on
     `scheduler.googleapis.com/job/...` for `juno-trial-anon-cleanup-trigger` — an
     independent signal that doesn't depend on the job container ever starting.

8. **Verify the Firestore TTL policy's manual timing test once, after step 1** (PRD §7):
   there is no automated or emulator test for TTL's actual deletion timing. Manually
   create one throwaway trial-shaped `care_plan_outputs` doc with a short `expires_at` in
   the near past, confirm it disappears within the documented window (up to 24 hours),
   and confirm a doc with `expires_at: null` (simulating a main-app doc) does not.

**Not a task in this file, flagged so it isn't lost (PRD §9 Q2, non-blocking):** a
regression test asserting no non-trial `care_plan_outputs` write path ever sets a
non-null `expires_at`. The PRD recommends this as cheap insurance but assigns it to SP2's
own test suite (`backend/tests/models/test_job.py` / `backend/tests/routes/test_trial.py`)
rather than duplicating it here — worth doing, but not part of SP5's scope or gate.

**Deliberately deferred, not tasks (PRD §9 Q5, Q6):**
- **Q5 — persisted `next_page_token` cursor:** not built. A full daily re-sweep is the
  chosen resumption strategy; revisit only if real anonymous-account volume approaches
  the 100k+ stress case regularly (which would itself indicate the job had been silently
  failing to run for an extended period).
- **Q6 — explicit overlap lock:** not built. `auth.delete_users` tolerates
  already-deleted uids (asserted by Task 3's pagination/real-account tests), so an
  accidental double-fire wastes duplicate work but causes no incorrect behavior; add a
  lock only if overlap is ever observed to actually cause problems in practice.
