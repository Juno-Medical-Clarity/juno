# PRD: SP5 — Retention Automation (Firestore TTL & Anonymous User Cleanup)

**Sub-project:** SP5
**Branch context:** users/tejitpabari/trial-app
**Date:** 2026-09-04
**Status:** Draft
**Dependencies:** SP2 (defines `expires_at` fields and `trial_rate_limits`); coordinates with SP4 (deploy workflow, legal copy accuracy)

---

## 1. Problem

The trial's zero-retention promise (brainstorm §5, D9) has two layers that only SP2 has
built so far:

1. **Worker deletes the GCS input** immediately after extraction (SP2 §4.5).
2. **Frontend calls `DELETE /trial/jobs/<id>`** once results have rendered (SP2 §4.6).

Both depend on a well-behaved browser completing its round trip. If the tab is closed
before results render, the request is aborted mid-flight, or the network drops, neither
layer fires. SP2 already writes an `expires_at` Timestamp on every trial job doc
(`care_plan_outputs`, 1 hour from creation) and every rate-limit counter doc
(`trial_rate_limits`, ~3 hours from window start) specifically so a third layer — a
Firestore native TTL policy — can sweep these up automatically. **SP2 explicitly did not
enable that policy**; enabling it is SP5's job.

Separately, every trial visitor mints a new anonymous Firebase Auth account
(`signInAnonymously()`, D1) that never signs out and is never deleted by anything in the
app today. Left alone, this accumulates without bound — a real cost/hygiene problem
independent of document retention, approved for cleanup in brainstorm D9 ("small cron,
every 24 hours, if not too much effort or cost").

This PRD designs both: (a) turning on Firestore TTL for the two collections SP2 already
prepared, verifying by direct code re-inspection that the shared `care_plan_outputs`
collection cannot leak main-app data through this mechanism, and (b) a daily job that
deletes anonymous Auth accounts older than 24 hours, designed defensively so it cannot
touch a real user's account.

**Finding surfaced by this design pass (see §4.1):** SP4's drafted Privacy Policy text
originally said the job record is deleted "generally within an hour." Firestore's
documented TTL behavior is deletion *within 24 hours of expiration* — not instant, and not
bounded by "an hour." With SP2's 1-hour `expires_at` plus up to a further 24 hours of TTL
sweep latency, an abandoned trial job's absolute worst-case lifetime is **~25 hours**, not
"an hour." This was a real overclaim in health-adjacent public copy; SP4 has since adopted
the corrected wording proposed in §4.1 (see SP4 §9 Q9).

---

## 2. Goals

1. Enable a native Firestore TTL policy on `care_plan_outputs.expires_at` and on
   `trial_rate_limits.expires_at`, both on the `(default)` database, with an exact,
   copy-pasteable command sequence and a verification step.
2. Re-verify, independently of SP2's own claim, that this TTL policy cannot ever delete a
   main-app (non-trial) document — this is the single highest-blast-radius risk in the
   whole trial initiative.
3. A daily scheduled job that deletes Firebase Auth accounts that are (a) genuinely
   anonymous and (b) older than 24 hours, with a predicate that is provably safe against
   ever matching a real (password-authenticated) account, a dry-run mode, and a design
   that stays within its execution deadline even at 100k+ anonymous accounts.
4. Reconcile the "immediate deletion" promise in SP4's legal copy with TTL's actual
   documented latency — flag the mismatch, don't paper over it.
5. A cost estimate and an honest answer on what ships now versus what can slip past
   launch without breaking the privacy promise.

---

## 3. Non-Goals

- **No changes to SP2's `expires_at` values or write sites.** SP2 already writes the
  field correctly (§4.3 below is a re-verification, not a change) — 1 hour on job docs,
  ~3 hours on rate-limit counters. This PRD does not touch `backend/routes/trial.py`,
  `backend/utils/rate_limit.py`, or `backend/models/job.py`.
- **No change to `POST /trial/jobs` / `DELETE /trial/jobs/<id>`.** Those are SP2's; this
  PRD only adds infrastructure that acts on data those routes already produce.
- **No Firestore security rules changes.** TTL deletion is a server-side Firestore Admin
  operation, entirely outside the client-facing rules SP2 already verified are
  unaffected (SP2 §4.11).
- **Not a general-purpose Firebase Auth admin tool.** The cleanup job does exactly one
  thing — delete anonymous accounts past a fixed age threshold — not account merging,
  not provider-linking cleanup, not any other Auth housekeeping.
- ~~No GCS lifecycle rule on the existing `care_plan/` prefix~~ — **no longer a non-goal.**
  Investigated in §4.10 and originally rejected as unsafe under the old path layout (trial
  and main-app uploads were indistinguishable by path). Per user direction (2026-09-05,
  §9 Q3), SP2 now writes trial uploads to a distinct `care_plan_trial/` prefix
  (`02-trial-backend/PRD.md` §4.1/§9 Q15), which makes a prefix-scoped lifecycle rule
  safe — designed as a third backstop in §4.10.
- **No Terraform / IaC.** The repo has zero IaC today (confirmed: no `*.tf` file anywhere,
  `scripts/` holds only bash/Python one-off helpers). Introducing a new IaC toolchain for
  one small feature is disproportionate — see §9 Q7.
- **No change to `juno-api`'s or `juno-worker`'s Cloud Run `--timeout`.** The cleanup
  mechanism chosen (§4.4) deliberately avoids needing this.

---

## 4. Architecture Decisions

### 4.1 Firestore TTL policy — exact commands, verification, and the legal-copy mismatch

**Commands** (one-time, idempotent — safe to re-run):

```bash
# care_plan_outputs — the shared collection. Field: expires_at (SP2 §4.3/§4.7).
gcloud firestore fields ttls update expires_at \
  --collection-group=care_plan_outputs \
  --database="(default)" \
  --project=juno-medical-clarity

# trial_rate_limits — SP2's per-IP counter collection.
gcloud firestore fields ttls update expires_at \
  --collection-group=trial_rate_limits \
  --database="(default)" \
  --project=juno-medical-clarity
```

`--database="(default)"` matches `FIRESTORE_DATABASE_ID`'s default everywhere else in the
codebase (`Constants.Storage.FIRESTORE_DATABASE_ID_DEFAULT`, `utils/firebase.py`'s
`firestore_client()`) — there is only the one Firestore database in this project, but the
flag is required by the command regardless.

**IAM required to run this command:** the Firestore Admin API method backing
`fields ttls update` is `google.firestore.admin.v1.FirestoreAdmin.UpdateField`, gated by
the `datastore.fields.update` permission. This is included in `roles/datastore.owner` (and
broader roles like `roles/owner`/`roles/editor`). **[RESOLVED, per user 2026-09-05]** —
this design assumes the running identity already has it; the user will grant whatever
role turns out to be missing when the command is actually run (§9 Q1). The exact
one-time `gcloud` grant, if needed, is in §8's new "CI & IAM setup checklist."

**Verifying the policy is active:**

```bash
gcloud firestore fields ttls describe expires_at \
  --collection-group=care_plan_outputs \
  --database="(default)" \
  --project=juno-medical-clarity
```

Look for `ttlConfig.state: ACTIVE` in the output. A freshly-created policy starts in
`CREATING` and transitions to `ACTIVE` — Google's own documentation notes this transition,
and the subsequent deletion sweep across already-existing documents, "can take up to 24
hours" to fully take effect project-wide. Repeat for `trial_rate_limits`.

**The latency mismatch — flagged by this PRD, since resolved in SP4's file:**
Firestore's documented TTL behavior is: *expired documents are deleted within 24 hours of
their `expires_at` timestamp, with no stronger SLA*. This is a background sweep, not an
instant trigger. Combined with SP2's values:

| Collection | `expires_at` set to | + TTL sweep latency | Worst-case total lifetime |
|---|---|---|---|
| `care_plan_outputs` (trial jobs) | `created_at` + 1 hour | up to +24 hours | **~25 hours** |
| `trial_rate_limits` (IP counters) | window end + 2 hours | up to +24 hours | **~27 hours** |

SP4's drafted Privacy Policy (`04-hosting-split-and-legal/PRD.md` §6.2) currently reads:

> "The job record (including the simplified output) is deleted from our database
> automatically, **generally within an hour**, and sooner once your browser has finished
> displaying your results and you close or navigate away from the page."

**"Generally within an hour" is not accurate for the TTL backstop path** — it's accurate
only for describing the field's *value* (1 hour), not the actual deletion event, which can
trail by up to a further day. TTL is correctly understood as *the safety net for the case
the primary path fails*, and the primary path (`DELETE /trial/jobs/<id>`, fired right after
render) really is fast — but the copy currently reads as if TTL itself is fast, which it
isn't. **Replacement text SP4 has adopted:**

> "The job record (including the simplified output) is deleted as soon as your browser has
> finished displaying your results and you close or navigate away from the page. As a
> safety net — in case that never happens, for example if you close the tab mid-process —
> an automatic backstop still removes it, typically within a day."

This keeps the honest "we don't say nothing is stored, we say nothing is kept" framing
SP4 already committed to, while not overclaiming TTL's speed. **This was the one finding
this PRD surfaced for a sibling SP's file** — SP4's PRD and its drafted copy have since
been amended to adopt this exact wording; SP4's §9 now carries a `Q9` entry recording that
resolution.

### 4.2 Re-verifying SP2's shared-collection safety claim (independent check)

SP2 §4.3 claims: `JobDoc.to_firestore()` is `model_dump(mode="python",
exclude_none=False)`, so every main-app job (`is_trial=False`, `expires_at=None` by
default) writes an **explicit** `expires_at: null` to Firestore, and Firestore TTL only
ever acts on a field holding an actual `Timestamp` — `null` (or an absent field) is
permanently ineligible, forever.

**Independently re-checked against the current code** (`backend/models/job.py`, read in
full for this PRD): confirmed. `expires_at: Optional[datetime] = None` is a real field on
`JobDoc` (not client-writable — nothing in `care_plan_jobs.py`, `batch_jobs.py`,
`saved_outputs.py`, or `worker.py` ever sets `expires_at` on a non-trial doc), `for_single`
defaults `expires_at=None` for every caller except the new trial route, and
`to_firestore()`'s `exclude_none=False` means the key is always present with a `null`
value rather than omitted. Firestore's own documentation is explicit that a TTL policy
"only deletes documents where the [TTL] field ... is a timestamp value" — a `null` or
missing field is never a match. **No path was found anywhere in the current codebase
where a non-trial `care_plan_outputs` doc could acquire a non-null `expires_at`.**
Grep confirms `expires_at` is written in exactly one place outside `models/job.py`'s
default (`routes/trial.py`'s `JobDoc.for_single(..., expires_at=now + timedelta(...))`,
SP2 §4.1) and one place in `rate_limit.py` (a different collection entirely,
`trial_rate_limits`, never `care_plan_outputs`).

**Conclusion: SP2's claim holds. Enabling the TTL policy in §4.1 is safe for the shared
`care_plan_outputs` collection as the codebase exists today.** The residual risk is
process, not code: if a future PR ever adds a new write path to `care_plan_outputs` that
sets `expires_at` to a real timestamp without also setting `is_trial=True` for a genuine
reason, that doc becomes silently TTL-eligible. **Recommend (§9 Q2, non-blocking):** a
lightweight regression test asserting every non-trial code path that creates or updates a
`care_plan_outputs` doc never sets a non-null `expires_at` — cheap insurance against this
exact regression, better placed in SP2's or a shared test file than duplicated here.

### 4.3 What TTL value SP2 chose, and whether it's right

Re-stating and evaluating SP2's choices (SP5 does not change these, only acts on them):

- **`care_plan_outputs.expires_at` = `created_at` + 1 hour (`Constants.Trial.JOB_TTL_HOURS
  = 1`).** Right-sized: generous relative to the pipeline's own 300-second processing
  deadline (so no in-flight job is ever at risk of being swept while still processing),
  short enough that an abandoned browser's data doesn't linger for days. This is a
  *safety-net* window, not the primary deletion mechanism (that's the `DELETE` call) — 1
  hour is a reasonable backstop value for that role.
- **`trial_rate_limits.expires_at` = window end + 2 hours
  (`Constants.Trial.RATE_LIMIT_COUNTER_TTL_HOURS = 2`), i.e. ~3 hours after the counter's
  window starts.** Right-sized for a different reason: this collection has no "browser
  closed" failure mode at all (nothing client-side depends on it existing), so its only
  requirement is "outlive the 1-hour window it counts, plus a safety margin for the
  transactional read/write pattern." A ~3-hour total lifetime comfortably clears that with
  room to spare, and keeps the collection's steady-state size bounded to a few hours'
  worth of small counter docs rather than accumulating indefinitely.

Both values are appropriate for their very different natural lifetimes (§ design question
2) — no change recommended.

### 4.4 Anonymous-user cleanup — mechanism choice

**Options considered:**

| Option | Cost | New public attack surface | Execution-time ceiling | New infra |
|---|---|---|---|---|
| A. Cloud Scheduler → authenticated endpoint on `juno-api` | Same as B | **Yes** — one more publicly-routable endpoint on the internet-facing service, defended only by OIDC verification | Bounded by `juno-api`'s own `--timeout` (currently 300s) — would need raising for the whole service just to accommodate this one background task | Lowest — no new compute resource |
| B. **Cloud Scheduler → Cloud Run Job** (chosen) | Cents/month (§8) | **No** — a Cloud Run Job has no HTTP ingress at all; it is invoked only via the Cloud Run Admin API's `:run` method, gated by IAM (`run.jobs.run`), never reachable from the public internet | Independent `--task-timeout`, up to 24h, does not touch `juno-api`/`juno-worker`'s serving config at all | One Cloud Run Job resource (reuses the existing backend image) + one small dedicated IAM identity |
| C. Cloud Function | Similar compute cost | New, smaller surface than A but still HTTP by default unless made Pub/Sub-triggered | Function timeout ceilings are also service-specific config | A second runtime/deploy toolchain the repo has never used — no existing Cloud Function anywhere in this codebase |

**Decision: B, Cloud Scheduler → Cloud Run Job**, reusing the exact backend Docker image
already built by `backend/cloudbuild.yaml` (`$_BACKEND_IMAGE`), with a command override
instead of a new container.

**Why not A, given the repo already has a working OIDC-authenticated internal-endpoint
pattern (`worker.py`'s `verify_oidc_token()`) that's tempting to just mirror:** that
pattern exists to defend a route Cloud Tasks must reach synchronously as part of the
user-facing job pipeline (`juno-worker`, already internet-reachable for that reason,
`--ingress=internal` non-withstanding it still needs a public/authenticated HTTP surface
for Cloud Tasks dispatch). Bulk-deleting Firebase Auth users has no such requirement — it
is a pure batch task with no caller waiting on a response. Standing up a whole new
authenticated HTTP route on `juno-api` (the one service that *is* `--allow-unauthenticated`
per `cloudbuild.yaml`) purely so Cloud Scheduler can hit it is strictly more attack surface
than a Cloud Run Job, which cannot be reached by an HTTP request at all — a bug in a
future OIDC check would be a real vulnerability on option A and is structurally impossible
on option B. Additionally, deleting up to 100k+ Auth accounts (§4.5) can plausibly take
several minutes; forcing that inside a request/response cycle on `juno-api` means either
raising `--timeout` for the *entire* public-facing service (increasing the blast radius of
any future hung request, unrelated to this feature) or building a resumable
background-thread-plus-poll design — meaningfully more complexity than a Cloud Run Job,
which simply gets to run for as long as it needs, isolated from the request-serving
service entirely.

**Why not C:** the repo has zero Cloud Function infrastructure today. Introducing one
would mean a second deploy toolchain, a second dependency-management file, and
reimplementing `initialize_firebase()`'s credential-resolution logic in a new runtime for
no benefit over a Cloud Run Job that can reuse the *exact same image, dependencies, and
Firebase-init code already in `backend/utils/firebase.py`* — genuinely the lowest-effort
option once you exclude the public-surface downside of A.

### 4.5 Job design — code, pagination, batching, deadline, idempotency

**New file: `backend/services/retention.py`** (core logic, unit-testable, no Flask
dependency):

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

**New file: `backend/scripts/cleanup_anonymous_users.py`** (thin CLI entrypoint — the
Cloud Run Job's actual container command):

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
from services.retention import cleanup_anonymous_users

setup_logging()
logger = logging.getLogger(__name__)


def main() -> int:
    initialize_firebase()
    dry_run = os.environ.get("RETENTION_DRY_RUN", "true").lower() not in ("false", "0", "no")
    summary = cleanup_anonymous_users(dry_run=dry_run)
    if summary.delete_errors:
        logger.warning("retention: completed with %d delete errors — see prior warnings", summary.delete_errors)
    return 0  # non-zero would trigger a Cloud Run Job retry; partial failure is not fatal (§4.9)


if __name__ == "__main__":
    sys.exit(main())
```

**Pagination/batching at scale — real numbers, not hand-waving:** `auth.list_users`'s
`ExportedUserIterator` pages internally at up to 1000 users/request; `auth.delete_users`
accepts up to 1000 uids/call. Since this design processes one page at a time and each page
is already ≤1000, exactly one `delete_users` call happens per page — no extra chunking
logic needed. Both Admin SDK calls are typically sub-second to low-seconds for 1000-user
pages. At 100k anonymous accounts (100 pages): roughly 30–90 seconds of `list_users` time
plus roughly 100–300 seconds of `delete_users` time — **a few minutes, comfortably inside
a generous execution budget.** Even at 500k accounts (5x the design brief's stress case,
implausible for a free trial demo), the same arithmetic scales to roughly 15–30 minutes.

**Deadline and resumption strategy — deliberately no persisted cursor.** The Cloud Run
Job's `--task-timeout` is set to **30 minutes** (§4.7) — comfortably covering even the
500k-account extreme case above with headroom. If a run is nonetheless killed by that
timeout partway through (e.g. Firebase Admin API degradation, not account volume), no
state is corrupted: every page's `delete_users` call either completed before the kill or
never started; nothing is left half-deleted. **Resumption is by design property of the
predicate, not a stored cursor:** because "older than 24 hours" is a rolling, re-evaluated
condition, any account missed by a killed run is still `>24h` old (in fact more so) the
next time the job runs and gets swept then. A persisted `next_page_token` cursor was
considered (would save re-scanning already-processed pages on a killed run) and explicitly
**deferred** (§9 Q5) — at this product's realistic volume (steady-state daily deltas of a
few hundred to a few thousand new anonymous accounts, not the 100k+ stress case, which
would only arise if the job silently failed to run for months), a full daily re-sweep is
simpler, has no state to get wrong, and the added engineering (Firestore-backed cursor
doc, staleness handling for a token that's hours old while the underlying user set keeps
changing) is not justified by the actual expected load. This is the honest "not too much
effort" tradeoff the user asked for.

### 4.6 Idempotency and failure handling

- **Concurrent runs (Cloud Scheduler double-fires, or a manual + scheduled run overlap):**
  both runs' `list_users` reads are independent and consistent snapshots-in-time; both may
  select overlapping matched uids. `auth.delete_users()` on a uid that's already been
  deleted by the other run is expected to appear in that call's `.errors` list with a
  "not found"-shaped reason rather than raise — **this exact behavior is asserted by a
  unit test (§7) rather than assumed, and is not blocking** since the code already treats
  any `.errors` entry as a logged-and-continued non-fatal outcome, whether the cause is a
  genuine failure or a race with another run. Net effect of a double-fire: wasted
  duplicate work, never incorrect behavior. No locking mechanism is added (§9 Q6,
  deferred) — Cloud Scheduler jobs are single cron triggers that don't self-overlap absent
  a manual extra invocation, and the failure mode of an accidental overlap is "some
  redundant work," not "data corruption."
- **Job dies mid-run (OOM, node preemption, hitting `--task-timeout`):** see §4.5 —
  self-healing via the next scheduled run, since the predicate is purely time-based and
  re-evaluated fresh every invocation.
- **`RETENTION_DRY_RUN` misconfigured to `true` forever:** silent-but-safe failure mode —
  the job "succeeds" every day but deletes nothing. Caught by the observability plan (§4.9)
  logging `dry_run=True` on every run; an operator reviewing logs would notice quickly.
  Intentionally fails safe rather than fails loud, appropriate for a destructive operation.

### 4.7 Cloud Run Job — one-time setup and CI-driven redeploy

**One-time creation** (delegated to us per the brainstorm's pattern for infra setup, not
owner-only — mirrors SP4 §4.2's `firebase hosting:sites:create` precedent: performed once
by an implementer with real credentials, then kept in sync by CI thereafter):

```bash
gcloud run jobs deploy juno-trial-anon-cleanup \
  --image="$BACKEND_IMAGE" \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --command=python \
  --args="-m,scripts.cleanup_anonymous_users" \
  --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,FIRESTORE_DATABASE_ID=(default),RETENTION_DRY_RUN=true" \
  --set-secrets="FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest" \
  --task-timeout=1800 \
  --max-retries=0 \
  --memory=512Mi \
  --cpu=1
```

Notes on these flags:
- **Reuses `$BACKEND_IMAGE`** — the exact image `cloudbuild.yaml` already builds for
  `juno-api`/`juno-worker`. `--command`/`--args` overrides the Dockerfile's default
  `CMD ["gunicorn", ...]` for this one resource only, without a second Dockerfile or a
  second `cloudbuild.yaml` build step.
- **Reuses the existing `firebase-service-account` Secret Manager secret** — the same
  identity `juno-api`/`juno-worker` already authenticate as via
  `FIREBASE_SERVICE_ACCOUNT_JSON` (`utils/firebase.py::initialize_firebase`). No new
  service-account key is minted. **This does mean that existing service account needs the
  Firebase Authentication Admin IAM role** (`roles/firebaseauth.admin`, or the narrowest
  role that covers `identitytoolkit.accounts.list`/`.delete` — Firebase's own console
  documents "Firebase Authentication Admin" as the intended role for exactly this).
  **[RESOLVED, per user 2026-09-05]** — this design assumes the role is already granted;
  the user will grant it if the job's first dry-run shows an IAM error (§9 Q1, §8's new
  "CI & IAM setup checklist").
- `--max-retries=0`: a failed run should not auto-retry (retrying a partially-completed
  bulk-delete run adds no safety given §4.6's idempotency, and auto-retry could mask a
  persistent failure that deserves a human look rather than silent repeated attempts).
- `RETENTION_DRY_RUN=true` is the **initial deployed default** — flipped to `false` only
  after a manual review of a real dry-run's logs (§7, §8 item 2). This is the one place
  this PRD deliberately ships "off" by default even though the job itself is created.

**Ongoing sync via `deploy.yml`** — new step in the `deploy-backend` job, after the
existing `gcloud builds submit` step (so `$BACKEND_IMAGE` already reflects the current
commit) and before `tag`:

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

**Deliberately using `--update-env-vars` (merge), not `--set-env-vars` (replace), for
this step**: unlike `deploy.yml`'s existing `juno-api`/`juno-worker` steps (which own
their full env-var set and can safely replace it wholesale every deploy), this step must
never clobber the operator-controlled `RETENTION_DRY_RUN` flag (§8 item 2) back to its
image-default `true` on every ordinary code deploy — that would silently re-arm dry-run
after a deliberate go-live decision. `--update-env-vars` only touches the two keys listed,
leaving `RETENTION_DRY_RUN` (set once, manually, outside this step) untouched.

**Why this step belongs in `deploy.yml` and not a separate one-time script:** matches the
repo's existing convention exactly — SP2's own new Cloud Tasks queue-creation step
(`02-trial-backend/PRD.md` §4.12) is idempotent and re-run on every deploy for the same
reason: infra-as-code-by-convention, not Terraform, keeping the Cloud Run Job's image and
resource limits in sync with every commit the same way `juno-api`/`juno-worker` already are
— see §9 Q7 for why Terraform itself is rejected.

### 4.8 Cloud Scheduler — one-time setup

```bash
# Small, single-purpose invoker identity — mirrors the existing
# juno-worker-invoker@... naming convention (deploy.yml's WORKER_SERVICE_ACCOUNT).
gcloud iam service-accounts create juno-scheduler-invoker \
  --project="$GCP_PROJECT_ID" \
  --display-name="Cloud Scheduler -> Cloud Run Jobs invoker"

gcloud run jobs add-iam-policy-binding juno-trial-anon-cleanup \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --member="serviceAccount:juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

gcloud scheduler jobs create http juno-trial-anon-cleanup-trigger \
  --location="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --schedule="0 9 * * *" \
  --uri="https://$GCP_REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$GCP_PROJECT_ID/jobs/juno-trial-anon-cleanup:run" \
  --http-method=POST \
  --oauth-service-account-email="juno-scheduler-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  || echo "scheduler job already exists — continuing"
```

`0 9 * * *` (09:00 UTC daily) is an arbitrary but reasonable off-peak-for-most-US-timezones
slot; no correctness dependency on the exact hour since the predicate is a rolling 24-hour
window regardless of when the job runs. Kept as a one-time setup command (like SP4's
`hosting:sites:create`/`target:apply`), **not** added to `deploy.yml`'s idempotent-rerun
pattern, because `gcloud scheduler jobs create` errors (rather than no-ops) if the resource
already exists and updating its schedule/target has no reason to happen on every code
deploy — this mirrors SP2's own choice to run its Cloud Tasks queue-creation as a
tolerate-already-exists step precisely because that one *is* worth re-running (env vars
referencing it change per-deploy); the Scheduler job's config here never changes
per-deploy, so there's nothing to keep "in sync" on every run.

### 4.9 Observability

Following `docs/logging.md`'s existing conventions:

- **A new marker leaf**, `backend/utils/markers/markers.py`:
  ```python
  class Retention:
      @code_marker("retention.anon_user_cleanup")
      class AnonUserCleanup(CodeMarker): pass
  ```
  `scripts/cleanup_anonymous_users.py::main()` wraps the call in
  `Markers.Retention.AnonUserCleanup.execute(...)`, attaching `scope.add_many({"scanned":
  ..., "matched": ..., "deleted": ..., "delete_errors": ..., "dry_run": ...})` from the
  returned `CleanupSummary` — this makes the run's outcome queryable the same way every
  other operation in the codebase already is (`marker_duration_ms`, `marker_op_count`
  log-based metrics per `docs/logging.md` §4), with zero new logging infrastructure.
- **A structured summary log line** on every run (already in `cleanup_anonymous_users`
  itself, §4.5) — `scanned`, `matched`, `deleted`, `delete_errors`, `pages`, `dry_run` —
  enough to answer "did it run, and what did it do" from Logs Explorer alone, without
  needing the marker/metric pipeline.
- **Alerting recommendation (not built here, a console-side follow-up):** a log-based
  alert on `jsonPayload.operation="retention.anon_user_cleanup" AND
  jsonPayload.OpOutcome="Failed"` (same base filter pattern `docs/logging.md` already
  documents for creating log-based metrics) firing if the job doesn't succeed. Also
  recommend: **Cloud Scheduler's own built-in execution-failure notifications** (a
  Console-configurable alerting policy on `scheduler.googleapis.com/job/...`) as a second,
  independent signal that doesn't depend on the job container even starting — catches the
  case where the Scheduler trigger itself fails (bad OAuth SA, wrong URI) before the job's
  own logging would ever fire. Both are console-configured, one-time setup, not code —
  flagged as a manual step (§8).
- **What "the user knows it ran"** boils down to, in priority order: (1) the structured
  summary log line, queryable any time; (2) the marker-derived metric, if the log-based
  metrics from `docs/logging.md` are ever set up for this operation too; (3) the
  recommended alert, for the negative case ("didn't run" / "failed"). No new dashboard is
  built as part of this PRD — reusing the existing Logs Explorer query patterns is
  sufficient for a once-a-day job at this scale.

### 4.10 Orphaned GCS objects — prefix fix adopted, lifecycle rule now designed as a third backstop (resolves §9 Q3)

Traced the original path layout (`services/care_plan_input.py::upload_combined_pdf`, as of
this PRD's first draft):

```python
blob_name = f"care_plan/{user_id}/inputs/{object_id}.pdf"
```

**`user_id` here is a Firebase uid — indistinguishable in shape between a trial's
anonymous uid and a main app's real (password-authenticated) uid.** There was no
`is_trial` marker anywhere in the GCS path; trial and main-app uploads wrote to the exact
same prefix pattern. GCS Object Lifecycle Management conditions (`age`, `createdBefore`,
`matchesPrefix`/`matchesSuffix`, storage class, version count, etc. — the complete
condition set) have no concept of "check this custom Firestore field before deleting," and
prefix/suffix matching could not separate the two use cases given that layout, because
both would match `care_plan/**` identically. **This PRD originally rejected a lifecycle
rule outright** for exactly this reason.

**Resolved 2026-09-05, per user direction ("give a distinct prefix if you can, if
cheap"):** SP2 adopted the fix this PRD flagged as a would-be-safe path
(`02-trial-backend/PRD.md` §4.1/§9 Q15) — `upload_combined_pdf` now takes an `is_trial`
keyword, and trial uploads write to a visually distinct prefix,
`care_plan_trial/{user_id}/inputs/{object_id}.pdf`, while every main-app call site
(`is_trial` defaulting `False`) is unchanged and keeps writing `care_plan/...`. This makes
a prefix-scoped lifecycle rule safe: `matchesPrefix: ["care_plan_trial/"]` can never match
a main-app object, because no main-app object is ever written under that prefix.

**Lifecycle rule design — a third backstop, not the primary or secondary path.** The two
retention layers SP2 already ships (worker `finally`-block delete, §4.5's dependency; and
the `DELETE /trial/jobs/<id>` route's best-effort delete) already cover every graceful
job-completion path. This rule exists purely for the residual, rare case both of those
miss: a hard process kill (SIGKILL/OOM/node preemption) between the GCS upload completing
and the worker's `finally` block running. A short age keeps that residual exposure small
without risking an in-flight upload being swept mid-job (the pipeline's own processing
deadline is 300s single / 900s batch — comfortably inside a 1-day age condition).

```bash
# One-time: add a lifecycle rule to the existing bucket, scoped to the trial prefix only.
# Age is in days; 1 day is deliberately short (a backstop for a rare failure mode, not the
# primary deletion mechanism) but generous relative to the pipeline's own <=900s deadline.
cat > /tmp/trial-lifecycle-rule.json <<'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 1,
        "matchesPrefix": ["care_plan_trial/"]
      }
    }
  ]
}
EOF

# Inspect first — do not blindly overwrite if the bucket already has other lifecycle
# rules (e.g. storage-class transitions); merge this rule into the existing "rule" array
# instead of replacing it wholesale.
gsutil lifecycle get gs://$GCP_BUCKET_NAME > /tmp/existing-lifecycle.json

gsutil lifecycle set /tmp/trial-lifecycle-rule.json gs://$GCP_BUCKET_NAME
```

**Why `matchesPrefix: ["care_plan_trial/"]` and not the whole bucket:** the bucket
(`juno-medical-clarity-backend`, per `deploy.yml`'s `GCP_BUCKET_NAME`) also holds
main-app objects under `care_plan/` and any other prefixes the main app uses — a
bucket-wide rule would delete those too. Scoping to `care_plan_trial/` is exactly what the
prefix split above makes possible and safe.

**Verification:** `gsutil lifecycle get gs://$GCP_BUCKET_NAME` after applying, confirm the
`care_plan_trial/` rule is present; create one throwaway object under
`care_plan_trial/test-uid/inputs/test.pdf` and confirm it disappears after the age window
elapses, while a control object under `care_plan/` does not.

**Cost:** negligible — this deletes at most a handful of ≤25MB objects/incident (the rare
hard-crash case this backstops); GCS lifecycle-triggered deletes carry no separate
API-call billing.

**IAM required to run `gsutil lifecycle set`:** `storage.buckets.update`, covered by
`roles/storage.admin` — already held by the CI service account
(`github-actions-deploy@...`, confirmed, §8's new checklist) or the narrower
`roles/storage.legacyBucketOwner`. Kept here as a one-time manual command (consistent with
SP4's own `hosting:sites:create` and this PRD's own Cloud Scheduler setup, §4.8) rather
than folded into `deploy.yml`'s idempotent-rerun pattern — bucket lifecycle config has no
reason to change on every code deploy.

---

## 5. API Change Summary

None. This PRD adds no HTTP routes reachable by any client — the Cloud Run Job has no
ingress at all (§4.4), and Firestore TTL is a database-level policy, not an API. The only
"surface" this PRD creates is a Cloud Scheduler → Cloud Run Jobs Admin API call, entirely
internal to GCP's own control plane.

---

## 6. Frontend Change Summary

N/A. Nothing in this PRD touches `frontend/`, `frontend-trial/`, or any client code.

---

## 7. Testing

Destructive Auth deletion demands a design that can be fully tested without ever touching
a real Firebase Auth user pool — everything below runs against mocks, mirroring
`backend/tests/`'s existing `monkeypatch`-based conventions (e.g. how `utils/gcs.py`'s
module-level client is reset between tests).

**`backend/tests/services/test_retention.py`** (new):
- `_is_anonymous`: `True` for `provider_data == []`; `False` for a record with one or more
  `UserInfo` entries (e.g. `provider_id="password"`).
- `_older_than`: correctly compares `creation_timestamp` (ms) against a cutoff derived
  from a fixed, injected `now`.
- `cleanup_anonymous_users(dry_run=True)`: with a mocked `auth.list_users` returning a
  single page of mixed users (anonymous+old, anonymous+new, real+old, real+new), asserts
  `matched` only counts anonymous+old, `deleted` reflects the dry-run "would delete" count,
  and **`auth.delete_users` is never called**.
- `cleanup_anonymous_users(dry_run=False)`: same fixture, asserts `auth.delete_users` is
  called exactly once with exactly the matched uids (never the real or too-young ones);
  asserts a mocked `.errors` entry increments `delete_errors` and appears in `error_uids`
  without raising.
- **Real-account safety, explicit regression guard:** a fixture where every "real" user has
  non-empty `provider_data` and is older than 24h — asserts none of them ever appear in
  `matched`, specifically because this is the one property that must never regress.
- **Pagination:** a mocked multi-page iterator (`get_next_page()` returns a second page
  once, then `None`) — asserts `delete_users` is called once per page (not once for the
  whole run), and `scanned`/`matched`/`pages` sum correctly across both pages.
- **Empty result set:** zero users in the mocked page — `scanned=0, matched=0, deleted=0`,
  no exception.

**`backend/tests/services/test_retention.py`** (continued) or a `scripts/` test, per
whichever placement the implementer finds more consistent with existing layout:
- `cleanup_anonymous_users.py::main()` reads `RETENTION_DRY_RUN` from the environment
  correctly (`"true"`/unset → `dry_run=True`; `"false"` → `dry_run=False`), and returns 0
  even when `delete_errors > 0` (non-fatal, per §4.6).

**Dry-run as the primary safety gate before any real deployment (§8):** the Cloud Run Job
is deployed with `RETENTION_DRY_RUN=true` (§4.7) as its initial state. Before ever flipping
it to `false`, the implementer/operator should trigger one real dry-run execution
(`gcloud run jobs execute juno-trial-anon-cleanup --region=... --project=...`) against the
live project and read the resulting structured log line (§4.9) — confirming `scanned` and
`matched` counts look sane (roughly matching the expected trial-traffic volume, not
wildly higher, which would suggest the predicate is matching more broadly than intended)
before the one manual `--update-env-vars RETENTION_DRY_RUN=false` flip (§8 item 2). This is
the closest thing to an integration test this feature gets, and it is a required manual
gate, not optional — deleting a real user's account is unrecoverable, and no amount of unit
testing against mocks substitutes for seeing real counts once before going live.

**No automated test exercises the Firestore TTL policy itself** — TTL is a Google-managed
background service with no local emulator equivalent for the *timing* behavior (the
Firestore emulator does not simulate TTL deletion sweeps). Verification there is
inherently manual: after enabling the policy (§4.1), create one throwaway trial-shaped doc
with a short `expires_at` in the near past, confirm it disappears within the documented
window, and confirm a doc with `expires_at: null` (simulating a main-app doc) does not.

---

## 8. Manual Intervention Required From You

1. **Confirm the existing `firebase-service-account` identity (the one backing the
   `FIREBASE_SERVICE_ACCOUNT_JSON` secret already used by `juno-api`/`juno-worker`) has the
   Firebase Authentication Admin IAM role**, or grant it once — needed for
   `auth.list_users`/`auth.delete_users` to succeed from the new Cloud Run Job (§4.7).
   **[RESOLVED, per user 2026-09-05]** — assumed available; grant only if a dry-run
   surfaces a permission error. Exact command in the new "CI & IAM setup checklist" below.
2. **Flip `RETENTION_DRY_RUN` from `true` to `false`** on the Cloud Run Job, only after
   reviewing at least one real dry-run's log output (§7) and being satisfied the
   scanned/matched counts look right:
   ```bash
   gcloud run jobs update juno-trial-anon-cleanup \
     --region=us-central1 --project=juno-medical-clarity \
     --update-env-vars=RETENTION_DRY_RUN=false
   ```
   This is a deliberate one-time manual step, not automated by `deploy.yml` (§4.7) —
   destructive-by-design behavior should never silently activate itself.
3. **Run §4.1's two `gcloud firestore fields ttls update` commands once**, and confirm
   both report `ACTIVE` via `fields ttls describe` (may need to check back — the
   transition can take time per Google's own documentation).
4. **Run §4.7's one-time `gcloud run jobs deploy` and §4.8's Scheduler/IAM setup once** —
   after that, `deploy.yml`'s new step (§4.7) keeps the Job's image/resources in sync
   automatically on every subsequent deploy.
5. ~~Amend SP4's drafted Privacy Policy text per §4.1's recommended replacement wording~~
   — **done.** SP4's Privacy Policy, Terms, and footer copy (§6.2, §6.4) have been
   corrected to the wording proposed in §4.1; see SP4 §9 Q9. The still-open item is
   whatever `frontend-trial/` component eventually renders that copy, which belongs to
   SP3, not here.
6. **Optional: set up the two recommended Cloud Monitoring alerting policies** (§4.9) —
   Console-only configuration, no code, not blocking launch.
7. **Add the GCS lifecycle rule on the `care_plan_trial/` prefix** (§4.10, new per §9 Q3)
   — one-time `gsutil lifecycle set` command, see the checklist below.

### CI & IAM setup checklist (added 2026-09-05, resolves §9 Q1)

**What CI can and can't already do.** The `GCP_SA_KEY` identity used throughout
`deploy.yml`, `github-actions-deploy@juno-medical-clarity.iam.gserviceaccount.com`, was
checked against the live project's IAM bindings (2026-09-05) and holds:
`artifactregistry.writer`, `cloudbuild.builds.editor`, `iam.serviceAccountUser`,
`run.admin`, `secretmanager.secretAccessor`, `storage.admin`. **Notably absent: any Cloud
Tasks role.** This means CI cannot create SP2's `care-plan-jobs-trial` queue
(`02-trial-backend/PRD.md` §4.9) despite that PRD's `deploy.yml` step attempting it —
and because that step's `|| echo "queue already exists — continuing"` swallows *any*
nonzero exit code, not just "already exists," **a permission-denied failure there will
report green in CI while the queue was never actually created.** Decision: create the
queue once, manually, below — not by granting CI a Cloud Tasks admin role it would only
ever use once.

Everything below is copy-pasteable. Items in §2 are one-time setup, run once with your own
(Owner/Editor) `gcloud`/`firebase` login — not with CI's `GCP_SA_KEY` — matching the same
"delegated to us, not owner-only, but still a human running it once" pattern SP4 and this
PRD already use for `hosting:sites:create` and the Cloud Run Job/Scheduler setup.

**1. GitHub repository secret to add** (Settings → Secrets and variables → Actions):
```bash
# SP2's trial rate-limit IP-hashing salt (02-trial-backend/PRD.md §8 item 1)
openssl rand -hex 32
# → paste the output as the value of a new secret named TRIAL_RATE_LIMIT_SALT
```

**2. One-time `gcloud`/`firebase` commands:**
```bash
export GCP_PROJECT_ID=juno-medical-clarity
export GCP_REGION=us-central1

# a. SP2's trial Cloud Tasks queue — CI cannot create this (see above). Create once:
gcloud tasks queues create care-plan-jobs-trial \
  --location="$GCP_REGION" --project="$GCP_PROJECT_ID" \
  --max-concurrent-dispatches=5 --max-dispatches-per-second=2

# Verify it actually exists — do not trust deploy.yml's own green checkmark for this one:
gcloud tasks queues describe care-plan-jobs-trial \
  --location="$GCP_REGION" --project="$GCP_PROJECT_ID"

# b. Firestore TTL policy on both collections (§4.1):
gcloud firestore fields ttls update expires_at \
  --collection-group=care_plan_outputs --database="(default)" --project="$GCP_PROJECT_ID"
gcloud firestore fields ttls update expires_at \
  --collection-group=trial_rate_limits --database="(default)" --project="$GCP_PROJECT_ID"

# Verify — state should read ACTIVE (may take time to transition from CREATING):
gcloud firestore fields ttls describe expires_at \
  --collection-group=care_plan_outputs --database="(default)" --project="$GCP_PROJECT_ID"

# c. Anonymous-user cleanup Cloud Run Job — one-time create (§4.7):
gcloud run jobs deploy juno-trial-anon-cleanup \
  --image="us-central1-docker.pkg.dev/$GCP_PROJECT_ID/juno/simplify-backend:latest" \
  --region="$GCP_REGION" --project="$GCP_PROJECT_ID" \
  --command=python --args="-m,scripts.cleanup_anonymous_users" \
  --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,FIRESTORE_DATABASE_ID=(default),RETENTION_DRY_RUN=true" \
  --set-secrets="FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest" \
  --task-timeout=1800 --max-retries=0 --memory=512Mi --cpu=1

# d. Cloud Scheduler -> the Job above, daily at 09:00 UTC (§4.8):
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

# e. GCS lifecycle rule on the trial upload prefix (§4.10):
cat > /tmp/trial-lifecycle-rule.json <<'EOF'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":1,"matchesPrefix":["care_plan_trial/"]}}]}
EOF
gsutil lifecycle get gs://juno-medical-clarity-backend > /tmp/existing-lifecycle.json  # inspect first, merge if non-empty
gsutil lifecycle set /tmp/trial-lifecycle-rule.json gs://juno-medical-clarity-backend

# f. SP4's Firebase Hosting split — one-time site + target setup
# (04-hosting-split-and-legal/PRD.md §4.2):
firebase hosting:sites:create juno-app --project "$GCP_PROJECT_ID"
firebase target:apply hosting trial juno-medical-clarity --project "$GCP_PROJECT_ID"
firebase target:apply hosting app juno-app --project "$GCP_PROJECT_ID"
```

**3. IAM grants — only if a command above fails with a permission error (grant, then
re-run the failing command):**
```bash
# a. If (2a) fails and you deliberately choose to let CI create the queue instead of you
# (not the decision made above, but here for completeness):
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:github-actions-deploy@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.admin"

# b. If (2b) fails (Firestore TTL commands need roles/datastore.owner):
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="user:YOUR_EMAIL@example.com" \
  --role="roles/datastore.owner"

# c. If the deployed Cloud Run Job (2c) fails at runtime calling
# auth.list_users/auth.delete_users — grant Firebase Authentication Admin to the identity
# backing the firebase-service-account secret (find its email via the JSON key's
# "client_email" field, or `gcloud iam service-accounts list --project="$GCP_PROJECT_ID"`):
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:FIREBASE_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/firebaseauth.admin"
```

**4. Only after reviewing at least one real dry-run's log output and being satisfied the
scanned/matched counts look right (§7, §8 item 2) — flip the retention job live:**
```bash
gcloud run jobs update juno-trial-anon-cleanup \
  --region=us-central1 --project=juno-medical-clarity \
  --update-env-vars=RETENTION_DRY_RUN=false
```

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Does the existing `firebase-service-account` identity already have Firebase Authentication Admin (or equivalent) IAM, and does the identity running the one-time TTL commands have `roles/datastore.owner` (or equivalent)? | **[RESOLVED, per user 2026-09-05: "it should have. Tell me what I need to do for CI after you finish all tasks."]** — this design assumes the roles are already available; if a dry-run or the TTL commands surface a permission error, the user grants whatever role is missing. Every IAM grant, secret, and one-time command needed for CI and this PRD's retention job to work is now enumerated in §8's new "CI & IAM setup checklist" (includes the finding that `GCP_SA_KEY`'s identity, `github-actions-deploy@juno-medical-clarity.iam.gserviceaccount.com`, holds no Cloud Tasks role — see that checklist for the consequence for SP2's `care-plan-jobs-trial` queue). |
| Q2 | Should a regression test assert no non-trial `care_plan_outputs` write path ever sets a non-null `expires_at`? | **[RESOLVED: recommended, non-blocking]** — cheap insurance against the one true way this design could ever become unsafe in the future (§4.2). Better owned alongside SP2's own test suite (`backend/tests/models/test_job.py`, `backend/tests/routes/test_trial.py`) than duplicated in a retention-only test file; flagged here so it isn't lost, not implemented by this PRD. |
| Q3 | Should SP2 change the GCS path layout to give trial uploads a distinct prefix, enabling a safe lifecycle-rule third backstop? | **[RESOLVED: yes, per user 2026-09-05: "give a distinct prefix if you can, if cheap."]** — SP2 now writes trial uploads to `care_plan_trial/{user_id}/inputs/{uuid}.pdf` instead of the shared `care_plan/` prefix (`02-trial-backend/PRD.md` §4.1/§9 Q15). This makes a prefix-scoped GCS lifecycle rule (`age: 1` day) safe as a third backstop behind the two existing retention layers (worker `finally` + `DELETE` route) — designed in §4.10. |
| Q4 | What if a real (non-anonymous) user somehow has empty `provider_data`? | **[RESOLVED: accepted risk per user 2026-09-05 — "nah dont worry about it" — no additional guard]** — per §4.5's docstring: this project's only two sign-in paths are `signInAnonymously()` (trial) and `signInWithEmailAndPassword()` (main app, `LoginPage.tsx`), and Firebase always populates `provider_data` with a `password` entry for the latter — so this case does not arise under this codebase's actual auth flows today. It could only arise via an out-of-band Admin SDK action (e.g., manually unlinking every provider from a real account, which the Admin SDK permits even though the client SDK blocks it) that nothing in this codebase currently does. No additional signal exists on `ExportedUserRecord` to further disambiguate if it ever did happen, and none is added. The existing defensive `_older_than` age check and the dry-run gate (§7, §8 item 2) remain the safety net: a real account with empty `provider_data` would show up in a dry-run's `matched` count before any live deletion ever occurs, giving a human a chance to notice before flipping `RETENTION_DRY_RUN=false`. |
| Q5 | Should the cleanup job persist a `next_page_token` cursor across runs for faster resumption after a killed run? | **[DEFERRED]** — see §4.5. Not justified at this product's realistic daily volume (hundreds to low thousands of new anonymous accounts/day); a full daily re-sweep is simpler and has no stale-cursor edge cases. Revisit only if actual production volume is later observed to approach the 100k+ stress case regularly (which would itself indicate the job had been failing to run for an extended period — a bigger problem than cursor design). |
| Q6 | Should overlapping/concurrent job runs be prevented with an explicit lock (e.g. a Firestore transaction doc)? | **[DEFERRED]** — see §4.6. Cloud Scheduler triggers a single cron cadence; accidental overlap (e.g. a manual `gcloud run jobs execute` colliding with the scheduled run) wastes duplicate work but is not unsafe given `delete_users`' tolerance of already-deleted uids (§7 test coverage). Add a lock only if overlap is ever observed to actually cause problems in practice. |
| Q7 | Should this whole SP5 stack (TTL policies, Cloud Run Job, Cloud Scheduler, IAM bindings) be captured in Terraform instead of one-time `gcloud`/CI steps? | **[RESOLVED: no]** — the repo has zero IaC today (confirmed: no `*.tf` anywhere; `scripts/` holds only bash/Python helpers, `deploy.yml` itself is the closest thing to "infra as code" this project has, via idempotent `gcloud ... || echo already exists` steps). Introducing Terraform for one small stretch feature would be a disproportionate new toolchain for a single-operator project — consistent with SP4's own §9 Q2 reasoning about not over-engineering for a team size of one. Follow the exact same convention SP2 and SP4 already established. |
| Q8 | Does the "~25 hour" worst-case TTL lifetime for trial job docs create any correctness problem (as opposed to a legal-copy wording problem)? | **[RESOLVED: no correctness problem, copy problem only]** — nothing in the product depends on the job doc being gone within any particular window; the frontend never re-reads a job after rendering results, and a lingering doc for up to a day is exactly the accepted "backstop, not primary path" design SP2 already committed to. The only actual issue is SP4's copy overclaiming the backstop's speed (§4.1), not any functional gap. |
| Q9 | Is a 30-minute Cloud Run Job `--task-timeout` the right number? | **[RESOLVED, revisit only if volume assumptions are wrong]** — sized against §4.5's real-numbers estimate (a few minutes at 100k accounts, ~15-30 minutes even at a 500k stress case). If actual anonymous-account accumulation ever regularly approaches that stress case (which would itself mean daily cleanup had been silently failing for a long stretch — a bigger problem worth investigating on its own), raise this value; Cloud Run Jobs supports up to 24 hours. |
| Q10 | Cost estimate — is this really "cents/month" as the brainstorm's D9 assumed? | **[RESOLVED: yes, with real numbers]** — Cloud Scheduler: 1 job, within the free tier (first 3 jobs/month free). Cloud Run Job compute: ~1-2 minutes/day at 1 vCPU/512MiB ≈ well under $0.10/month at standard Cloud Run Jobs per-second billing (no idle/min-instance cost — it only bills for actual execution seconds, unlike a warm Cloud Run *service*). Firestore TTL-triggered deletes bill as ordinary delete ops (~$0.02/100k) — negligible at trial-scale document volume. **Total: comfortably under $1-2/month**, consistent with the brainstorm's own "cents/month" estimate. |

**Dependencies:** Requires SP2's `expires_at` fields (already written per SP2's design,
independently re-verified safe in §4.2) and `trial_rate_limits` collection to exist before
§4.1's TTL commands act on real data — no code dependency, since the TTL policy can be
enabled at any time (it simply has nothing to act on until SP2 ships). Coordinates with
SP4 on the one legal-copy fix flagged in §4.1 — SP4 has since adopted the corrected
wording (SP4 §9 Q9).
