# Tasks: SP4 — Hosting Split, CI & Legal Pages

Source PRD: `.dev/trial-simplify/04-hosting-split-and-legal/PRD.md`. §9 is fully
`[RESOLVED]`/`[DEFERRED]` — no `[OPEN]` items block this work. Q2 (a manual-approval gate
between the `app` and `trial` deploy steps) is `[DEFERRED]` per the PRD and the initiative
README — **no task below implements it**; it is noted again in the final summary only.

**Already implemented on this branch — verified against the actual files before writing
this list, not assumed:**
- `.firebaserc` at the repo root already matches PRD §4.1's "New" block exactly (`trial` →
  `juno-medical-clarity`, `app` → `juno-app-99`), and the Firebase Hosting sites
  `juno-medical-clarity` / `juno-app-99` already exist in GCP — both confirmed by the
  initiative README's "Infrastructure already provisioned" list and by `cat .firebaserc`.
  §4.2's one-time `firebase hosting:sites:create` / `target:apply` commands have therefore
  already been run with real credentials. **Task 1 below is verify-only, not a redundant
  re-run.**
- `deploy.yml`'s `deploy-backend` job already carries SP2's trial-specific additions
  (commit `d64f9429`: the `CLOUD_TASKS_QUEUE_TRIAL` env var, the "Ensure trial Cloud Tasks
  queue exists" step, `TRIAL_RATE_LIMIT_SALT`) — none of that is this PRD's concern and
  none of the tasks below touch those lines.
- Everything else this PRD calls "Old" — root `firebase.json` (still the plain
  `{"firestore": ...}` object, no `hosting` key), `frontend/firebase.json` and
  `frontend/.firebaserc` (still present, single-target), `backend/app.py`'s CORS
  `origins` list (still 4 entries, no `juno-app-99`), `deploy.yml`'s `deploy-frontend`
  job and trigger (still single-target, `workflow_dispatch`-only, no `--max-instances`),
  `rollback-production.yml` (still `--min-instances=1` on `juno-api`, no `target:` input),
  and `ci.yml` (still `pull_request`-only, two jobs, no `frontend-trial`) — was confirmed
  by directly reading each file. **These are real, unstarted work** — Tasks 2–9 below.

**Cross-SP boundaries respected in this file:** no changes inside `frontend-trial/`
itself (routes, footer component, GA init) — PRD §3 non-goals assigns that to SP3; this
file only edits the infra/config/CI files SP4 owns, and Tasks 6–7 note that their
`frontend-trial/` build steps can't be exercised end-to-end until SP3 lands a
`package-lock.json` and `dist` build (same caveat the PRD itself states in §9's
Dependencies line). No Firestore TTL, GCS lifecycle rule, or anon-cleanup Job/Scheduler
work (SP5). No `cloudbuild.yaml`/`cloudbuild-build.yaml` changes (PRD §3 non-goal). No
`firestore.rules` changes (PRD §3 non-goal — the existing root `firebase.json`'s
`firestore` block is preserved, not touched, by Task 2 below).

---

### Task 1 — Verify one-time Hosting site/target setup is already applied (§4.2)

   - Files: `/root/projects/juno/.firebaserc` (read-only check — no edit expected)
   - Changes: **None expected.** Per the initiative README's "Infrastructure already
     provisioned" section, `firebase hosting:sites:create juno-app-99 --project
     juno-medical-clarity` and both `firebase target:apply hosting ...` commands from PRD
     §4.2 have already been run against real GCP credentials, and the resulting
     `.firebaserc` is already committed. This task exists only to make a junior dev
     actually confirm that before touching anything in Task 2, rather than re-running
     `target:apply` speculatively.
   - Verify:
     ```bash
     cat /root/projects/juno/.firebaserc
     ```
     must equal, byte-for-byte on the meaningful keys (whitespace/ordering aside):
     ```json
     {
       "projects": {
         "default": "juno-medical-clarity"
       },
       "targets": {
         "juno-medical-clarity": {
           "hosting": {
             "trial": ["juno-medical-clarity"],
             "app": ["juno-app-99"]
           }
         }
       }
     }
     ```
     If it does **not** match (e.g. `targets` key is missing), stop and escalate — do not
     run `firebase target:apply` yourself without GCP credentials scoped to
     `juno-medical-clarity`; this is the one step in the PRD that genuinely requires real
     cloud credentials (§4.2), and per the PRD it should already be done.
   - Acceptance criteria:
     - The `cat` output matches the block above (this should already pass with zero
       changes — if it doesn't, do not proceed to Task 2 until it does).
     - No file is modified by this task.

---

### Task 2 — Add multi-target `hosting` config to root `firebase.json` (§4.1)

   - Files: `/root/projects/juno/firebase.json`
   - Changes: Replace the file's current contents (today: only the `firestore` key) with:
     ```json
     {
       "firestore": {
         "rules": "firestore.rules"
       },
       "hosting": [
         {
           "target": "trial",
           "public": "frontend-trial/dist",
           "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
           "rewrites": [{ "source": "**", "destination": "/index.html" }]
         },
         {
           "target": "app",
           "public": "frontend/dist",
           "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
           "rewrites": [{ "source": "**", "destination": "/index.html" }]
         }
       ]
     }
     ```
     Do not touch the existing `firestore.rules` value or add a `firestore` change of any
     kind (PRD §3 non-goal). Do not add a third hosting entry or rename either `target`
     (must be exactly `trial` and `app` — these names are what Task 6/7's `deploy.yml`
     edits and Task 1's already-applied `.firebaserc` targets reference).
   - Acceptance criteria:
     - `python3 -m json.tool /root/projects/juno/firebase.json` exits 0 (valid JSON).
     - `firebase.json` contains both `"target": "trial"` (with `"public":
       "frontend-trial/dist"`) and `"target": "app"` (with `"public": "frontend/dist"`).
     - The `firestore` key is unchanged (`{"rules": "firestore.rules"}`).
     - `.firebaserc` (Task 1) is untouched by this task.

---

### Task 3 — Delete the now-superseded `frontend/firebase.json` and `frontend/.firebaserc` (§4.1)

   - Files: `/root/projects/juno/frontend/firebase.json`,
     `/root/projects/juno/frontend/.firebaserc`
   - Changes: Delete both files. They are fully superseded by the root `firebase.json`
     (Task 2) and root `.firebaserc` (Task 1) — a per-app Firebase config alongside a
     root-level multi-target one is exactly the confusing, backwards setup PRD §4.1
     rejects.
     ```bash
     git rm frontend/firebase.json frontend/.firebaserc
     ```
   - Acceptance criteria:
     - `ls frontend/firebase.json frontend/.firebaserc` reports both as non-existent.
     - `grep -rn "firebase.json\|\.firebaserc" frontend/package.json frontend/vite.config.ts`
       (or equivalent config files) returns nothing that referenced the deleted files by
       relative path — confirming nothing in `frontend/`'s own build tooling depended on
       them directly (Firebase CLI resolves hosting config by walking up from cwd to the
       nearest `firebase.json`/`.firebaserc`, which after Task 2/3 is the root one).

---

### Task 4 — Widen backend CORS allow-list for `juno-app-99.web.app` (§5)

   - Files: `/root/projects/juno/backend/app.py`
   - Changes: In the existing `CORS(app, origins=[...], ...)` call (currently 4 origins,
     around line 31), replace the `origins` list:
     ```python
     origins=[
         "https://juno-medical-clarity.web.app",       # trial app (SP3), primary address post-cutover
         "https://juno-medical-clarity.firebaseapp.com",
         "https://juno-app-99.web.app",                    # relocated full app — NEW
         "https://juno-app-99.firebaseapp.com",             # NEW
         "http://localhost:3000",
         "http://localhost:5173",                       # frontend/ (full app) dev server
         "http://localhost:5174",                       # frontend-trial/ dev server — NEW
     ],
     ```
     No other argument to `CORS(...)` changes (`methods`, `allow_headers`,
     `expose_headers`, `supports_credentials=False`, `max_age=600` all stay exactly as-is).
     This deploys via the existing `deploy-backend` job on the next run of `deploy.yml` —
     no separate deploy step is needed, but see the cutover-ordering note in the final
     summary: this change must reach production **before** the relocated full app is
     ever served from `juno-app-99.web.app`.
   - Acceptance criteria:
     - `grep -n "juno-app-99" backend/app.py` shows both the `.web.app` and
       `.firebaseapp.com` origins.
     - `grep -n "5174" backend/app.py` shows the new localhost dev-port origin.
     - The 3 pre-existing origins (`juno-medical-clarity.web.app`,
       `juno-medical-clarity.firebaseapp.com`, `localhost:3000`, `localhost:5173`) are
       still present, unremoved.
     - From `backend/`: `python -m pytest tests/utils/test_app_observability.py -q`
       exits 0 (this test file imports the real `app.py` module and builds a Flask test
       client — the cheapest existing regression check that the edited `CORS(...)` call
       still parses and the app still boots).

---

### Task 5 — `deploy.yml`: wire `--max-instances` for `juno-api` / `juno-worker` (§4.6)

   - Files: `/root/projects/juno/.github/workflows/deploy.yml`
   - Changes: Three edits inside the `deploy-backend` job:
     1. Add two new keys to the job's top-level `env:` block (after `BACKEND_IMAGE`):
        ```yaml
        API_MAX_INSTANCES: "10"
        WORKER_MAX_INSTANCES: "5"
        ```
     2. In the "Configure juno-api env vars and secrets" step's `gcloud run services
        update juno-api` call, add a `--max-instances "$API_MAX_INSTANCES"` flag (any
        position among the other flags is fine; PRD places it after `--timeout 300`):
        ```yaml
          gcloud run services update juno-api \
            --region "$GCP_REGION" \
            --project "$GCP_PROJECT_ID" \
            --memory 2Gi \
            --timeout 300 \
            --max-instances "$API_MAX_INSTANCES" \
            --set-env-vars "$API_ENV_VARS" \
            --set-secrets "FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest"
        ```
     3. In the "Configure juno-worker env vars and secrets" step's `gcloud run services
        update juno-worker` call, add `--max-instances "$WORKER_MAX_INSTANCES"` the same
        way (after `--timeout 900`):
        ```yaml
          gcloud run services update juno-worker \
            --region "$GCP_REGION" \
            --project "$GCP_PROJECT_ID" \
            --memory 2Gi \
            --timeout 900 \
            --max-instances "$WORKER_MAX_INSTANCES" \
            --set-env-vars "$WORKER_ENV_VARS" \
            --set-secrets "FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest,ATHENA_HEALTH_TEST_CLIENT_ID=athena-health-test-client-id:latest,ATHENA_HEALTH_TEST_CLIENT_SECRET=athena-health-test-client-secret:latest"
        ```
     Do not touch the "Ensure trial Cloud Tasks queue exists" step or either
     `*_ENV_VARS=` string's content (SP2's territory) — only add the one new flag to each
     `gcloud run services update` call, and the two new top-level `env:` entries.
   - Acceptance criteria:
     - `grep -n "API_MAX_INSTANCES\|WORKER_MAX_INSTANCES" .github/workflows/deploy.yml`
       shows the two `env:` block entries (`"10"` / `"5"`) plus their two usages inside
       the `--max-instances` flags.
     - `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
       exits 0 (valid YAML) — or `yamllint`/`actionlint` if available locally.
     - Neither `gcloud run services update` call's other flags (`--memory`, `--timeout`,
       `--set-env-vars`, `--set-secrets`) changed.

---

### Task 6 — `deploy.yml`: multi-target frontend build + deploy (§4.3)

   - Files: `/root/projects/juno/.github/workflows/deploy.yml`
   - Changes: Replace the entire `deploy-frontend` job body with the two-build,
     two-deploy sequence from PRD §4.3 ("New"):
     ```yaml
       deploy-frontend:
         needs: deploy-backend
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4

           - uses: actions/setup-node@v4
             with:
               node-version: '24'
               cache: 'npm'
               cache-dependency-path: |
                 frontend/package-lock.json
                 frontend-trial/package-lock.json

           - name: Install app dependencies
             run: npm ci
             working-directory: frontend

           - name: Build app (frontend/)
             run: npm run build
             working-directory: frontend
             env:
               VITE_FIREBASE_API_KEY: ${{ secrets.VITE_FIREBASE_API_KEY }}
               VITE_FIREBASE_AUTH_DOMAIN: ${{ secrets.VITE_FIREBASE_AUTH_DOMAIN }}
               VITE_FIREBASE_PROJECT_ID: ${{ secrets.VITE_FIREBASE_PROJECT_ID }}
               VITE_FIREBASE_STORAGE_BUCKET: ${{ secrets.VITE_FIREBASE_STORAGE_BUCKET }}
               VITE_FIREBASE_MESSAGING_SENDER_ID: ${{ secrets.VITE_FIREBASE_MESSAGING_SENDER_ID }}
               VITE_FIREBASE_APP_ID: ${{ secrets.VITE_FIREBASE_APP_ID }}
               VITE_API_PROCESSING_URL: ${{ secrets.VITE_API_PROCESSING_URL }}
               VITE_DEFAULT_VERSION: v1-2

           - name: Install trial dependencies
             run: npm ci
             working-directory: frontend-trial

           - name: Build trial (frontend-trial/)
             run: npm run build
             working-directory: frontend-trial
             env:
               VITE_FIREBASE_API_KEY: ${{ secrets.VITE_FIREBASE_API_KEY }}
               VITE_FIREBASE_AUTH_DOMAIN: ${{ secrets.VITE_FIREBASE_AUTH_DOMAIN }}
               VITE_FIREBASE_PROJECT_ID: ${{ secrets.VITE_FIREBASE_PROJECT_ID }}
               VITE_FIREBASE_STORAGE_BUCKET: ${{ secrets.VITE_FIREBASE_STORAGE_BUCKET }}
               VITE_FIREBASE_MESSAGING_SENDER_ID: ${{ secrets.VITE_FIREBASE_MESSAGING_SENDER_ID }}
               VITE_FIREBASE_APP_ID: ${{ secrets.VITE_FIREBASE_APP_ID }}
               VITE_API_PROCESSING_URL: ${{ secrets.VITE_API_PROCESSING_URL }}
               VITE_DEFAULT_VERSION: v1-2
               VITE_GA_MEASUREMENT_ID: G-4R0CDYKSPW

           - name: Deploy to Firebase Hosting
             env:
               FIREBASE_SERVICE_ACCOUNT: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
             run: |
               creds_file="$RUNNER_TEMP/firebase-service-account.json"
               printf '%s' "$FIREBASE_SERVICE_ACCOUNT" > "$creds_file"
               export GOOGLE_APPLICATION_CREDENTIALS="$creds_file"

               deploy_target() {
                 local target="$1"
                 set +e
                 deploy_output=$(npx firebase-tools deploy --only "hosting:$target" \
                   --project juno-medical-clarity --non-interactive 2>&1)
                 deploy_exit=$?
                 set -e
                 echo "$deploy_output"
                 if [ "$deploy_exit" -ne 0 ]; then
                   if echo "$deploy_output" | grep -q "is the current active version"; then
                     echo "::warning::hosting:$target build is identical to the current live version; nothing to release. Treating this no-op deploy as success."
                     return 0
                   fi
                   return "$deploy_exit"
                 fi
               }

               deploy_target app
               deploy_target trial

               rm -f "$creds_file"
     ```
     Notes for the implementer:
     - The old job's `working-directory: ./frontend` on the "Deploy to Firebase Hosting"
       step is **removed** — the step now runs from the checkout root, where Task 2 put
       `firebase.json`.
     - `VITE_GA_MEASUREMENT_ID: G-4R0CDYKSPW` is a literal in the workflow file (like
       `VITE_DEFAULT_VERSION: v1-2` above it), **not** a GitHub secret — do not add it to
       repo/environment secrets.
     - This job's `app`/`trial` ordering (`app` first) is deliberate (§4.3) and is
       superseded by Task 7's manual-only gating on the `app` steps — apply this task
       first, then Task 7 on top of it.
     - **This task cannot be fully exercised until SP3 lands `frontend-trial/`** (no
       `package-lock.json` or buildable app exists yet on this branch) — same caveat the
       PRD itself states (§9 Dependencies). Land the YAML now; the "Install/Build trial"
       steps will only succeed once SP3 merges.
   - Acceptance criteria:
     - `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
       exits 0.
     - The job has exactly one "Deploy to Firebase Hosting" step, calling
       `deploy_target app` before `deploy_target trial` in the script body.
     - `cache-dependency-path` lists both `frontend/package-lock.json` and
       `frontend-trial/package-lock.json`.
     - The "Build app (frontend/)" step's env block is byte-for-byte identical to the old
       job's `Build` step env block (no accidental drift in the app's own build secrets).
     - `working-directory: ./frontend` no longer appears on the Firebase deploy step.

---

### Task 7 — `deploy.yml`: automatic deploy-on-merge trigger, gated on CI (§4.8)

   - Files: `/root/projects/juno/.github/workflows/deploy.yml`
   - Changes: Four edits, applied on top of Task 6's job body (do this task after Task 6):
     1. Replace the workflow's top-level `on:` trigger:
        ```yaml
        on:
          workflow_run:
            workflows: ["CI"]
            types: [completed]
            branches: [main]
          workflow_dispatch:
        ```
     2. Add a top-level `if:` gate to the `deploy-backend` job (so a `workflow_run`
        triggered by a *failed* CI run never proceeds; a manual `workflow_dispatch` always
        proceeds):
        ```yaml
          deploy-backend:
            if: >-
              github.event_name == 'workflow_dispatch' ||
              github.event.workflow_run.conclusion == 'success'
            runs-on: ubuntu-latest
        ```
        (`deploy-frontend` and `tag` need no new `if:` — GitHub's default `needs:`
        semantics already skip them when `deploy-backend` is skipped.)
     3. On **every** `actions/checkout@v4` step in this file (there are three: one in
        `deploy-backend`, one in `deploy-frontend`, one in `tag`), pin the ref:
        ```yaml
          - uses: actions/checkout@v4
            with:
              ref: ${{ github.event.workflow_run.head_sha || github.sha }}
        ```
        For the `tag` job's checkout, keep its existing `fetch-depth: 0` alongside the new
        `ref:` line (both keys under the same `with:`).
     4. Within `deploy-frontend` (as edited by Task 6), make only the `app`-target steps
        conditional on manual dispatch — the `trial`-target steps run on every trigger,
        unchanged:
        ```yaml
              - name: Install app dependencies
                if: github.event_name == 'workflow_dispatch'
                run: npm ci
                working-directory: frontend

              - name: Build app (frontend/)
                if: github.event_name == 'workflow_dispatch'
                run: npm run build
                working-directory: frontend
                env:
                  # unchanged from Task 6
        ```
        And inside the "Deploy to Firebase Hosting" step's script, guard the `app` call:
        ```yaml
              if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
                deploy_target app
              fi
              deploy_target trial
        ```
   - Acceptance criteria:
     - `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
       exits 0.
     - `grep -n "workflow_run" .github/workflows/deploy.yml` shows the new trigger block;
       the old bare `workflow_dispatch: branches: [main]` form is gone (replaced by a bare
       `workflow_dispatch:` with no `branches:` key, since `workflow_dispatch` doesn't
       support branch filtering the way this repo previously wrote it — matching PRD
       §4.8's "New" block exactly).
     - `deploy-backend` has the `if:` gate shown above; `deploy-frontend` and `tag` do not
       (they inherit via `needs:`).
     - All three `actions/checkout@v4` steps carry the `ref:` expression; the `tag` job's
       checkout still also has `fetch-depth: 0`.
     - Exactly two steps in `deploy-frontend` ("Install app dependencies", "Build app
       (frontend/)") carry `if: github.event_name == 'workflow_dispatch'`; the
       trial-target steps ("Install trial dependencies", "Build trial
       (frontend-trial/)") carry no such `if:`.
     - The "Deploy to Firebase Hosting" step's script wraps `deploy_target app` in the
       `if [ "${{ github.event_name }}" = "workflow_dispatch" ]` guard; `deploy_target
       trial` is unconditional.

---

### Task 8 — Fix `rollback-production.yml` for the multi-target split and `min-instances` (§4.4)

   - Files: `/root/projects/juno/.github/workflows/rollback-production.yml`
   - Changes: Two independent edits:
     1. "Deploy rollback frontend" step (currently `entryPoint: ./frontend`, no
        `target:`) — change to:
        ```yaml
              - name: Deploy rollback frontend
                uses: FirebaseExtended/action-hosting-deploy@v0
                with:
                  repoToken: ${{ secrets.GITHUB_TOKEN }}
                  firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
                  projectId: juno-medical-clarity
                  channelId: live
                  entryPoint: .
                  target: app
        ```
        Only `entryPoint` (now `.`, the repo root, where Task 2 put `firebase.json`) and
        the new `target: app` line change — `repoToken`, `firebaseServiceAccount`,
        `projectId`, `channelId` stay as-is. The preceding "Build rollback frontend" step
        (`working-directory: frontend`) is untouched — rollback still only ever rebuilds
        and redeploys the **relocated full app** (`app` target), never the trial (PRD
        §4.4 — there is no historical trial prod-tag lineage to roll back to).
     2. "Deploy rollback juno-api" step's `flags:` block — change
        `--min-instances=1` to `--min-instances=0`:
        ```yaml
              flags: >-
                --allow-unauthenticated
                --memory 2Gi
                --timeout 300
                --min-instances=0
        ```
        No other flag on this step changes. Do not touch the "Deploy rollback
        juno-worker" step — it already sets `--min-instances=0 --max-instances=3` and is
        correct as-is.
   - Acceptance criteria:
     - `grep -n "target: app" .github/workflows/rollback-production.yml` shows the new
       line under the "Deploy rollback frontend" step; `grep -n "entryPoint" .github/workflows/rollback-production.yml`
       shows `entryPoint: .` (no `./frontend` value remaining anywhere in this file).
     - `grep -n "min-instances" .github/workflows/rollback-production.yml` shows
       `--min-instances=0` twice (once under "Deploy rollback juno-worker", now also once
       under "Deploy rollback juno-api") and `--min-instances=1` zero times.
     - `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/rollback-production.yml'))"`
       exits 0.
     - `juno-worker`'s step is byte-for-byte unchanged (`--max-instances=3` still present,
       still the only Cloud Run service in this file with that flag).

---

### Task 9 — `ci.yml`: `push` trigger + new `frontend-trial` job (§4.7)

   - Files: `/root/projects/juno/.github/workflows/ci.yml`
   - Changes: Two edits:
     1. Add a `push` trigger alongside the existing `pull_request` one:
        ```yaml
        on:
          pull_request:
            branches: [main]
          push:
            branches: [main]
        ```
     2. Add a third job, `frontend-trial`, mirroring the existing `frontend` job exactly
        but pointed at `frontend-trial/`:
        ```yaml
          frontend-trial:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4

              - uses: actions/setup-node@v4
                with:
                  node-version: '24'
                  cache: 'npm'
                  cache-dependency-path: frontend-trial/package-lock.json

              - name: Install dependencies
                run: npm ci
                working-directory: frontend-trial

              - name: Run frontend-trial tests
                run: npm run test
                working-directory: frontend-trial
        ```
        No lint/type-check step is added (matches the existing `frontend` job's scope
        exactly — PRD §4.7 and the initiative README's Q7 both defer adding a build/
        typecheck step to either frontend CI job as a follow-up, not part of this task).
        Do not modify the existing `backend` or `frontend` jobs.
     - **This job cannot pass CI until SP3 lands `frontend-trial/package-lock.json` and a
       `test` script** — same caveat as Task 6, and explicitly called out in PRD §4.7.
       Land the YAML now.
   - Acceptance criteria:
     - `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`
       exits 0.
     - `grep -n "push:" .github/workflows/ci.yml` shows the new trigger; `pull_request:`
       trigger is still present, unchanged.
     - `ci.yml` has exactly three jobs: `backend`, `frontend`, `frontend-trial`.
     - The new `frontend-trial` job's steps are identical in shape to `frontend`'s (same
       four steps), differing only in `working-directory`/`cache-dependency-path`
       pointing at `frontend-trial` instead of `frontend`, and the step name "Run
       frontend-trial tests".
     - `backend` and `frontend` jobs are byte-for-byte unchanged from before this task.

---

## Summary of what requires you (not a dev agent)

1. **Legal-copy review and approval (PRD §8 item 1, D8 locked).** The Privacy Policy
   (PRD §6.2) and Terms & Conditions (PRD §6.3) are first drafts written by Claude, not
   reviewed by a lawyer. Before launch you need to: read both in full, confirm the
   stated rate limit ("5 per hour," Terms §7) matches whatever SP2 actually ships,
   and confirm you're comfortable with the liability/warranty language for a
   health-adjacent public tool. This is a reading/judgment task, not something a dev
   agent can sign off on for you. Note: the contact address
   (`tejitpabari99@gmail.com`) and the deletion-timing wording are both already
   corrected in the drafted text (PRD §8 items 2 and 9) — this review is about tone and
   liability comfort, not a pending text fix. **No task above transcribes this copy into
   `frontend-trial/` — that implementation work belongs to SP3's TASKS.md; SP4's job
   ends at drafting the copy and the routing/footer contract (PRD §6.1/§6.4), which
   already exists in the PRD text itself.**

2. **Cutover ordering — a hard constraint, not a suggestion (PRD §4.5, initiative README
   "Cross-cutting risks").** The relocated full app only works at `juno-app-99.web.app`
   once Task 4's CORS change is live in production. Concretely, when you actually run
   the cutover:
   - Task 4 (backend CORS) must reach production **before** `juno-app-99.web.app` is
     ever loaded by a real user — deploy backend-only first if needed, do not assume
     the ordinary `deploy-backend → deploy-frontend` job sequence inside one workflow
     run is "early enough" if you are hand-triggering things out of order.
   - Do not merge Tasks 2–9 to `main` until Task 1's one-time site/target setup is
     confirmed (it already is, per this file's header) — this is naturally gated today
     since `deploy.yml` was `workflow_dispatch`-only, but Task 7 makes `main` push
     CI-gated-automatic, so once this lands, merging to `main` will automatically
     deploy the backend + trial frontend. Sequence your merge accordingly (see PRD
     §4.5 steps 1-8 for the full one-time runbook: create sites → confirm
     `.firebaserc` → deploy CORS alone → merge → watch `app` deploy → verify → watch
     `trial` deploy → verify with a non-PHI sample document).
   - This actual production cutover (running the deploy, watching both sites come up,
     verifying end-to-end per PRD §7) is an operational act on live infrastructure,
     not a code-review-able task — it requires you (or whoever holds deploy
     credentials) to execute and watch it happen, per the initiative README's
     "Cross-cutting risks" section.

3. **Q2 — manual-approval gate between `app` and `trial` deploy steps — [DEFERRED], not
   implemented.** Per the PRD (§9 Q2) and the initiative README, a GitHub Environment
   manual-approval gate between the two `deploy_target` calls in Task 6/7 was
   considered and explicitly rejected as over-engineering for a single-operator
   project; the accepted safety net is the rollback path (Task 8) instead. No task in
   this file builds it — flagging only so it isn't silently forgotten if the
   single-operator assumption ever changes.

4. **Rollback drill (PRD §7, "recommended once, not blocking launch").** After the
   cutover, at a low-stakes moment, trigger `rollback-production.yml` against a known
   `prod-*` tag to confirm Task 8's `target: app` / `entryPoint: .` fix actually works
   end-to-end before it's ever needed for a real incident. Optional, but you're the
   only one who can decide when a "low-stakes moment" is.

5. **No new GitHub secret, IAM grant, or GCP resource is needed for anything in Tasks
   1-9.** `API_MAX_INSTANCES`/`WORKER_MAX_INSTANCES` (Task 5) are plain workflow `env:`
   literals, not secrets; `VITE_GA_MEASUREMENT_ID` (Task 6) is a literal GA4 ID, not
   sensitive; the Hosting sites/targets (Task 1) and the `FIREBASE_SERVICE_ACCOUNT`
   secret's IAM scope (PRD §9 Q1) are both already confirmed sufficient per the
   initiative README.
