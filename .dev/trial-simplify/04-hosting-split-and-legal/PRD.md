# PRD: SP4 — Hosting Split, CI & Legal Pages

**Sub-project:** SP4
**Branch context:** users/tejitpabari/trial-app
**Date:** 2026-09-04
**Status:** Draft
**Dependencies:** SP3 (needs frontend-trial build output); coordinates with SP2 (CORS, max-instances)

---

## 1. Problem

Per the brainstorm's **D2 (locked)**, the trial app takes over the primary public address
`juno-medical-clarity.web.app`, and the existing full app relocates to a new Firebase
Hosting site, `juno-app-99` (`juno-app-99.web.app`), in the same Firebase/GCP project
(`juno-medical-clarity`). No custom domain exists or is planned.

Today the repo is single-site, single-app, across three places that must all change
together:

1. **Hosting config.** `frontend/firebase.json` has one unnamed `hosting` block (`public:
   dist`, catch-all SPA rewrite). `frontend/.firebaserc` and the root `.firebaserc` both
   pin `{"projects": {"default": "juno-medical-clarity"}}` with no `targets` key. Neither
   file has any notion of "which app goes to which site."
2. **CI.** `.github/workflows/deploy.yml`'s `deploy-frontend` job builds one Vite app
   (`frontend/`) and runs `firebase-tools deploy --only hosting` from `working-directory:
   ./frontend` — implicitly targeting whatever site `firebase.json`'s cwd resolves to
   (today: the project's default site, `juno-medical-clarity`). There is also a second,
   independent deploy path — `.github/workflows/rollback-production.yml` — which builds
   and deploys the frontend via `FirebaseExtended/action-hosting-deploy@v0` with
   `entryPoint: ./frontend` and no `target:` input. **Both break** the moment
   `firebase.json` becomes a multi-target array, because neither currently says which
   target it means.
3. **Legal pages.** No Privacy Policy or Terms & Conditions exist anywhere in the repo
   today (confirmed: no `privacy`/`terms` route, component, or static page in
   `frontend/src` or elsewhere). Per **D8 (locked)**, Claude drafts these; the user
   reviews and approves before launch (§8).

Additionally, moving the full app to a new origin (`juno-app-99.web.app`) breaks its own API
calls unless `backend/app.py`'s CORS allow-list is widened first — a hard ordering
constraint (§5).

This PRD is the design for all three: the hosting-config split, the CI change to deploy
both frontends, and the legal-page copy + serving contract for SP3.

---

## 2. Goals

1. `juno-medical-clarity.web.app` serves the trial app (SP3's `frontend-trial/`);
   `juno-app-99.web.app` serves the existing full app (`frontend/`) — same Firebase project,
   two Hosting sites, via Hosting **deploy targets**.
2. CI (`deploy.yml`) builds and deploys both frontends on every run, preserving the
   existing no-op-tolerance behavior for each site independently.
3. `backend/app.py`'s CORS origins are widened, deployed **before** the frontend cutover,
   so the relocated full app's API calls keep working.
4. A safe, explicit cutover plan: create and verify `juno-app-99` **before** the trial
   overwrites the currently-live `juno-medical-clarity.web.app`, plus a rollback path.
5. Full draft Privacy Policy and Terms & Conditions text, a footer-copy contract, and a
   precise "where do these pages live" contract for SP3 to implement against.
6. Keep `rollback-production.yml` functional across the split (it independently deploys
   hosting and will break the same way `deploy.yml` would if left untouched).

---

## 3. Non-Goals

- A custom domain. Confirmed by the user: none exists, none is planned (D2).
- Any change to `frontend-trial/`'s own screens, GA instrumentation code, or job-flow
  logic — that's SP3. This PRD only defines the **contract** SP3 builds against (routes,
  footer text, env var name for the GA measurement ID).
- ~~The exact numeric value for Cloud Run `max-instances`~~ — **no longer a non-goal.**
  SP2 and SP4 each deferred this number to the other and nobody picked one; per user
  direction (2026-09-05) this PRD now decides it directly: `juno-api` = 10, `juno-worker`
  = 5 (§4.6, resolves §9 Q3).
- Firestore TTL / anonymous-account cleanup (SP5, stretch).
- Changing `cloudbuild.yaml` / `cloudbuild-build.yaml` (backend container build) — out of
  scope, this PRD is Hosting/CORS/legal only.
- Deploying Firestore rules via CI. Confirmed: no workflow deploys
  `firestore.rules` today (it's presumably applied manually/via console); the root
  `firebase.json`'s existing `firestore` block is preserved as-is, untouched by this SP.

---

## 4. Architecture Decisions

### 4.1 Where the multi-site hosting config lives — root, not `frontend/`

**Decision: move `firebase.json` and the `targets` block to repo root**, consolidating
with the root `firebase.json` that already exists (today it holds only the `firestore`
block). Delete `frontend/firebase.json` and `frontend/.firebaserc`.

**Why not keep it in `frontend/`:** with two hosting targets, `frontend/firebase.json`'s
`public` paths would have to be `dist` (for itself) and `../frontend-trial/dist` (reaching
*out of* the directory the config file lives in) — workable, but backwards: a config file
that lives inside one of the two apps it configures, referencing its sibling by relative
path, is confusing and makes it look like `frontend-trial/` is subordinate to `frontend/`
when the two are peers. A root-level `firebase.json` is Firebase's own documented pattern
for "one Firebase project, multiple hosting targets, multiple app directories," and both
`public` paths (`frontend/dist`, `frontend-trial/dist`) read naturally as siblings of the
config file's own location. It also unifies with the existing `firestore` block instead of
splitting Firebase config across two files in two directories.

**Old — `/root/projects/juno/firebase.json`:**
```json
{
  "firestore": {
    "rules": "firestore.rules"
  }
}
```

**New — `/root/projects/juno/firebase.json`:**
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

**Old — `/root/projects/juno/.firebaserc`** (and identical `frontend/.firebaserc`):
```json
{
  "projects": {
    "default": "juno-medical-clarity"
  }
}
```

**New — `/root/projects/juno/.firebaserc`** (matches what `firebase target:apply` actually
wrote and what is now committed — the CLI expands each target's site-id array onto its own
line rather than the compact single-line form; it also appended an empty `"etags": {}` key,
confirmed to be harmless CLI bookkeeping and removed before commit):
```json
{
  "projects": {
    "default": "juno-medical-clarity"
  },
  "targets": {
    "juno-medical-clarity": {
      "hosting": {
        "trial": [
          "juno-medical-clarity"
        ],
        "app": [
          "juno-app-99"
        ]
      }
    }
  }
}
```

**Delete:** `frontend/firebase.json`, `frontend/.firebaserc` (superseded by root).

The target name `trial` maps to site id `juno-medical-clarity` — every Firebase project's
**default Hosting site id equals the project id**, which is why the trial (taking over the
primary address) doesn't need a new site at all, only a target label pointing at the
already-existing default site. `app` maps to the **new** site id `juno-app-99`, created in
§4.4.

### 4.2 One-time target setup — exact command sequence

These commands are **delegated to us** per the brainstorm (not owner-only) and must run
once, with credentials that have Firebase Hosting Admin (or Owner) on the
`juno-medical-clarity` project, **before** the new `firebase.json`/`.firebaserc` land and
**before** any CI run tries to deploy to a target that doesn't exist yet. The existing CI
service-account secret (`secrets.FIREBASE_SERVICE_ACCOUNT`) already successfully runs
`firebase deploy --only hosting` today, which requires Firebase Hosting Admin — the same
role that (per Firebase's documented IAM requirements) also covers `hosting:sites:create`
and `target:apply`, so no new credential should be needed, but this is an assumption to
verify at execution time (flagged §9 Q1), not something checkable from this design pass.

```bash
# 1. Authenticate non-interactively with the same service account CI uses.
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-service-account.json

# 2. Create the new Hosting site for the relocated full app.
firebase hosting:sites:create juno-app-99 --project juno-medical-clarity

# 3. Map local target names to site ids — this is what writes the "targets" block
#    into .firebaserc. Run from the repo root (or pass --config) so it edits the
#    root .firebaserc, not a stray one.
firebase target:apply hosting trial juno-medical-clarity --project juno-medical-clarity
firebase target:apply hosting app juno-app-99 --project juno-medical-clarity

# 4. Confirm the resulting .firebaserc matches §4.1's "New" block exactly, then commit it.
cat .firebaserc
```

`target:apply` is idempotent and safe to re-run. Running it is what produces the
`.firebaserc` "New" content in §4.1 — an implementer should run these commands and diff
the result against §4.1 rather than hand-writing the file, in case Firebase CLI's output
format differs from the hand-authored example above.

### 4.3 CI — `deploy.yml` frontend section

**Decision: keep one job (renamed `deploy-frontend`, unchanged `needs: deploy-backend`),
with two sequential build steps and two sequential deploy steps** (build app → build
trial → deploy `hosting:app` → deploy `hosting:trial`), rather than two parallel jobs.

**Why one job, not two parallel jobs:**
- **Ordering matters, and jobs can't easily express "deploy app before trial" without an
  artificial `needs:` edge between two frontend jobs** — which is just a worse-ergonomics
  version of two steps in one job (extra job-boundary overhead: a second checkout, a
  second Node setup, a second npm cache restore, for no benefit).
- **Ordering is deliberately preserved from the cutover discipline (§4.5) into steady
  state.** `app` (the relocated full app, the "less newly-risky" site since it's the one
  we test immediately after every deploy per §7) deploys first; `trial` (the primary
  public address) deploys second. This isn't just a one-time cutover rule — keeping the
  same order on every subsequent CI run means there is never a special-cased "first
  deploy is different" script, and a broken build always shows up on `app` first without
  ever touching the currently-live-to-the-world `trial` site.
- **One npm cache step can cover both lockfiles.** `actions/setup-node@v4`'s
  `cache-dependency-path` accepts multiple newline-separated paths hashed together into
  one cache key — no need for two separate cache steps/jobs.

**Old (`deploy.yml`, `deploy-frontend` job):**
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
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: frontend

      - name: Build
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

      - name: Deploy to Firebase Hosting
        working-directory: ./frontend
        env:
          FIREBASE_SERVICE_ACCOUNT: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
        run: |
          creds_file="$RUNNER_TEMP/firebase-service-account.json"
          printf '%s' "$FIREBASE_SERVICE_ACCOUNT" > "$creds_file"
          export GOOGLE_APPLICATION_CREDENTIALS="$creds_file"

          set +e
          deploy_output=$(npx firebase-tools deploy --only hosting \
            --project juno-medical-clarity --non-interactive 2>&1)
          deploy_exit=$?
          set -e

          rm -f "$creds_file"
          echo "$deploy_output"

          if [ "$deploy_exit" -ne 0 ]; then
            if echo "$deploy_output" | grep -q "is the current active version"; then
              echo "::warning::Frontend build is identical to the current live Firebase Hosting version; nothing to release. Treating this no-op deploy as success."
              exit 0
            fi
            exit "$deploy_exit"
          fi
```

**New (`deploy.yml`, `deploy-frontend` job):**
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

          # Ordering: app before trial (see rationale, §4.3). Repo root is the
          # firebase.json/.firebaserc location (§4.1), so no working-directory
          # override is needed for this step.
          deploy_target app
          deploy_target trial

          rm -f "$creds_file"
```

**Why two separate `deploy_target` invocations instead of one `--only hosting` call
covering both targets:** a single multi-target invocation's exit code and no-op-tolerance
grep would conflate the two sites' outcomes — e.g. if `app` is a genuine no-op (identical
build) but `trial` has a real failure, or vice versa, one combined exit code can't
distinguish "one site no-op, other site fine" from "one site no-op, other site broken."
Two independent invocations keep the existing no-op-tolerance semantics exactly as
designed (per-site), and keep the app-before-trial ordering explicit and inspectable in
the logs (two clearly labeled blocks) rather than implicit in a single command's internal
site-iteration order.

**Also note:** the `VITE_GA_MEASUREMENT_ID: G-4R0CDYKSPW` build-env line is a literal
(like the existing `VITE_DEFAULT_VERSION: v1-2`), not a GitHub secret — a GA4 measurement
ID is not sensitive; it's visible in the trial site's own page source/network requests to
any visitor regardless of how it's injected at build time. This is the contract SP3
should expect (§9 — confirm exact env var name with SP3 before they wire up GA init).

### 4.4 `rollback-production.yml` — also breaks, also needs the fix

**Not explicitly in the original ask, but a direct, otherwise-silent casualty of §4.1:**
`rollback-production.yml` independently builds and deploys the frontend via
`FirebaseExtended/action-hosting-deploy@v0`, `entryPoint: ./frontend`, no `target:` input.
Once `firebase.json` becomes a two-target array, this action will fail (or deploy to an
ambiguous/wrong target) the next time anyone invokes a rollback — silently breaking the
emergency path this whole cutover plan (§4.5) depends on as its safety net. Left
unaddressed, this is a real risk hiding behind "not the file you told me to change."

**Decision: fix it now, scoped minimally** — rollback only ever needs to restore the
**relocated full app** (`app` target) to a previously-tagged commit; it has never rolled
back "the trial" (which didn't exist before this initiative), so there's no need to widen
rollback's scope to build+deploy both frontends.

**Old (`rollback-production.yml`, frontend portion):**
```yaml
      - name: Deploy rollback frontend
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          projectId: juno-medical-clarity
          channelId: live
          entryPoint: ./frontend
```

**New:**
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

Only `entryPoint` (root, where `firebase.json` now lives — §4.1) and the new `target: app`
input change. The build step above it (`npm run build`, `working-directory: frontend`) is
unaffected. **The trial frontend is intentionally not part of rollback** — a bad trial
deploy is recovered by re-running the normal `deploy.yml` (which always redeploys both
sites from the current `main`), not by the emergency rollback path, since "trial" has no
historical prod-tag lineage before this initiative shipped it.

**Second, independent fix in the same file — `--min-instances=1` on `juno-api` (resolves
§9 Q4):** `rollback-production.yml`'s "Deploy rollback juno-api" step
(`google-github-actions/deploy-cloudrun@v2`) sets `--min-instances=1` in its `flags:`
block (lines 106-110 today) — a pre-existing inconsistency with D7's locked
"min-instances=0, no cold-start masking" that the trial-hosting split didn't introduce,
but which is resolved here per user direction (2026-09-05: "min instance = 0").

**Old (`rollback-production.yml`, lines 106-110):**
```yaml
          flags: >-
            --allow-unauthenticated
            --memory 2Gi
            --timeout 300
            --min-instances=1
```

**New:**
```yaml
          flags: >-
            --allow-unauthenticated
            --memory 2Gi
            --timeout 300
            --min-instances=0
```

No other flag on this step changes. `juno-worker`'s rollback deploy step already sets
`--min-instances=0` (alongside its existing `--max-instances=3`) — only `juno-api`'s
value was inconsistent, and only `juno-api`'s changes here.

### 4.5 Cutover plan and risk

This is the single riskiest step across the whole initiative (per `brainstorm.md`
§7): deploying the trial to `juno-medical-clarity.web.app` **overwrites the currently
live full app** at the address people may already have bookmarked or been sent.

**Safe ordering (one-time, manual, performed by the implementer with real credentials —
not something CI does automatically the first time):**

1. Land this PRD's config changes (§4.1–§4.4) and SP3's `frontend-trial/` on a branch, but
   **do not merge to `main`** yet (CI only runs on `workflow_dispatch` against `main` per
   the existing trigger, so this is naturally gated).
2. Run §4.2's one-time `firebase hosting:sites:create juno-app-99` +
   `target:apply` commands. Confirm `.firebaserc` matches §4.1.
3. **Deploy the backend CORS change (§5) to production first, alone**, ahead of any
   frontend change — the relocated app's origin (`https://juno-app-99.web.app`) must already
   be an allowed CORS origin before anything is ever served from it, or its very first
   page load will fail every API call.
4. Merge to `main`, trigger `deploy.yml`. Because `deploy-frontend` deploys `app` before
   `trial` (§4.3), the very first thing that happens is: `juno-app-99.web.app` goes live with
   the full app, **while `juno-medical-clarity.web.app` still serves the pre-cutover full
   app, unchanged**, since a partially-completed workflow run has not reached the `trial`
   deploy step yet.
5. **Verify `juno-app-99.web.app` end-to-end before the workflow continues** — since the two
   deploy steps are sequential within the same job and there's no manual gate between
   them today, this verification is really: watch the `deploy_target app` step's log
   succeed, then, once `deploy_target trial` also completes (seconds later — Firebase
   Hosting deploys are fast), immediately do the verification checklist in §7 against
   `juno-app-99.web.app`. Because both targets deploy in one workflow run with no built-in
   pause, the practical safety net is **§4.4's rollback path**, not a manual approval gate
   — flagged as an explicit design tradeoff in §9 (a `workflow_dispatch` input or GitHub
   Environment manual-approval gate between the two deploy steps was considered and
   rejected as over-engineering for a single-operator project; see §9 Q2).
6. Verify `juno-medical-clarity.web.app` now serves the trial correctly (input → live
   steps → results, end to end, with a non-PHI sample document).
7. If anything is wrong with `juno-app-99.web.app`: re-run `deploy.yml` after fixing forward
   (fast — Hosting deploys are seconds, not minutes), or use `rollback-production.yml`
   with the last known-good `prod-*` tag (§4.4) to restore the full app's *backend and
   frontend* to a previous working state. Rollback only restores `app` (§4.4) — the trial
   site is never touched by the rollback workflow, which is correct: a rollback is about
   restoring the relocated full app to safety, not about the trial's lifecycle.
8. If anything is wrong with the **trial** at `juno-medical-clarity.web.app` post-cutover:
   there is no historical "previous good trial" to roll back to (it's brand new), so the
   fix-forward path is the only path — push a fix and re-run `deploy.yml`. This is an
   accepted, inherent risk of D2 (trial takes the primary address) that this PRD cannot
   design away, only shorten the blast radius of via fast redeploys and the verification
   checklist in §7.

**Ordering summary (why this is safe):** the pre-existing full app is never taken down
before its replacement (`juno-app-99`) is live and reachable — worst case, for the few
seconds between step 4 and step 6, `juno-medical-clarity.web.app` still serves the *old*
full app (not a 404, not a broken trial) while `juno-app-99.web.app` is already verifiable in
parallel. The primary address only changes content at the very last deploy step.

### 4.6 Cloud Run `--max-instances` — decided values (resolves §9 Q3)

**Decision, per user direction (2026-09-05): `juno-api` = 10, `juno-worker` = 5.** SP2 and
SP4 each deferred this number to the other (SP2 §9 Q7; this PRD's own §9 Q3) — nobody had
actually picked one. Resolving it here, since this PRD is the one that owns `deploy.yml`.

**Rationale:**
- `juno-worker` is the real cost driver — it's the service making the Gemini/Vertex AI
  calls (`JUNO_MODE=worker`), not `juno-api`, which only accepts requests and enqueues
  Cloud Tasks. 5 concurrent worker instances is generous headroom against SP2's own
  5-requests-per-IP-per-hour trial rate limit — even several distinct IPs bursting
  simultaneously stays comfortably under 5 concurrent Gemini calls for realistic trial
  traffic.
- 5 is also consistent with existing precedent: `rollback-production.yml` already sets
  `--max-instances=3` for `juno-worker` (§4.4) — 5 is a close, slightly more generous
  sibling value for the primary deploy path, not an arbitrary new number.
- `juno-api` gets a higher ceiling (10) since it's the thin, cheap, request-accepting
  layer (no Gemini calls, no long-running work) — it can scale wider without materially
  changing the cost picture, and a tighter `juno-api` ceiling would risk request-queueing
  latency for legitimate traffic sharing the same service.

**`deploy.yml`, `deploy-backend` job env block — old (lines 19-23):**
```yaml
    env:
      GCP_PROJECT_ID: juno-medical-clarity
      GCP_REGION: us-central1
      GCP_BUCKET_NAME: juno-medical-clarity-backend
      BACKEND_IMAGE: us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
```

**New:**
```yaml
    env:
      GCP_PROJECT_ID: juno-medical-clarity
      GCP_REGION: us-central1
      GCP_BUCKET_NAME: juno-medical-clarity-backend
      BACKEND_IMAGE: us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
      API_MAX_INSTANCES: "10"
      WORKER_MAX_INSTANCES: "5"
```

**`juno-api`'s `gcloud run services update` call — old (lines 58-64):**
```yaml
          gcloud run services update juno-api \
            --region "$GCP_REGION" \
            --project "$GCP_PROJECT_ID" \
            --memory 2Gi \
            --timeout 300 \
            --set-env-vars "$API_ENV_VARS" \
            --set-secrets "FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest"
```

**New:**
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

**`juno-worker`'s `gcloud run services update` call — old (lines 70-76):**
```yaml
          gcloud run services update juno-worker \
            --region "$GCP_REGION" \
            --project "$GCP_PROJECT_ID" \
            --memory 2Gi \
            --timeout 900 \
            --set-env-vars "$WORKER_ENV_VARS" \
            --set-secrets "FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest,ATHENA_HEALTH_TEST_CLIENT_ID=athena-health-test-client-id:latest,ATHENA_HEALTH_TEST_CLIENT_SECRET=athena-health-test-client-secret:latest"
```

**New:**
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

No other flag on either call changes.

### 4.7 `ci.yml` — add a `frontend-trial` job (resolves §9 Q8)

**Decision: extend the existing `ci.yml`, not a new workflow.** `ci.yml` already runs a
`backend` job (ruff + pytest) and a `frontend` job (`npm run test` in `frontend/`) on
every pull request into `main`. `frontend-trial/` needs the identical treatment once SP3
lands it — a third job, not a rethink of the existing two.

**Old (`ci.yml`, trigger):**
```yaml
on:
  pull_request:
    branches: [main]
```

**New:**
```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
```

**Why the trigger also gains `push: branches: [main]`:** not for its own sake (PR review
already runs CI before merge) — this is a hard prerequisite for §4.8's automatic-deploy
gate. `deploy.yml`'s new automatic trigger (§4.8) fires off *this workflow's* completion
via `workflow_run`, which requires `ci.yml` to actually run against the post-merge `main`
commit, not just the pre-merge PR commit (a PR's merge/squash commit on `main` is a
different SHA than what the PR's own `pull_request`-triggered run validated).

**New job, mirroring the existing `frontend` job:**
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

Same shape as the existing `frontend` job, pointed at `frontend-trial/` — no lint step
added beyond what `frontend`'s job already does (it has none either; `backend`'s `ruff
check` is the only lint step today, and this PRD does not expand lint scope beyond
matching existing precedent). Depends on SP3 actually producing a `frontend-trial/
package-lock.json` and a `test` script — cannot be merged/tested until SP3 lands, same
caveat as §4.3's build job.

### 4.8 Automatic deploy on merge to `main` (redesigns the trigger in §4.3)

**Decision, per user direction (2026-09-05):** CI should run on GitHub (§4.7, covering
backend/frontend/frontend-trial); deploy should also run automatically once code lands on
`main`, covering the **backend** and the **new `frontend-trial/` app** (the primary public
address post-cutover, §4.1). **The relocated full app (`juno-app-99` site) explicitly does
not get automatic deployment** — the user does not want a merge to `main` to risk that
site, so it stays `workflow_dispatch`-only, same as `deploy.yml` is today. This is a real
change to the trigger and job graph designed in §4.3, not just a value change — recorded
here rather than rewritten into §4.3 to keep that section's own rationale (job ordering,
why-one-job) intact; read the two together.

**Risk, called out plainly:** automatic deploy on merge to `main` means an unreviewed (or
review-bypassed) merge ships straight to the public trial site with no human gate in
between. **Recommendation: gate the automatic deploy job on CI (§4.7) actually passing**,
not merely on the push event firing — a plain `push: branches: [main]` trigger on
`deploy.yml` would race an in-flight or failing CI run with no ordering guarantee between
the two workflows. The design below implements this recommendation structurally (a real
workflow dependency), rather than leaving it as an unenforced suggestion.

**`deploy.yml` trigger — old:**
```yaml
on:
  workflow_dispatch:
    branches: [main]
```

**New:**
```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
```

`workflow_run` fires once `ci.yml` (§4.7) finishes running against a push to `main` —
this is what makes "deploy depends on CI passing" a real job dependency instead of a
convention. `workflow_dispatch` is retained unchanged, so a human can still trigger a full
manual deploy (including the `app` target, below) at any time, exactly as today.

**`deploy-backend` gains a top-level gate**, so an automatic run that followed a *failed*
CI run never proceeds (a manual dispatch always proceeds — there is no `workflow_run`
context to check in that event):
```yaml
  deploy-backend:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
```
Because `deploy-frontend` (`needs: deploy-backend`) and `tag` (`needs: deploy-frontend`)
already only run if their `needs:` job **succeeded** (GitHub's default `needs:` semantics
— a skipped job does not count as success), gating `deploy-backend` alone cascades: a
failed-CI automatic trigger skips the entire workflow, not just the first job.

**Checkout must pin the exact commit CI validated**, not "whatever `main`'s HEAD happens
to be by the time this job starts" (a second push could otherwise race ahead between CI
finishing and deploy starting). Every job's `actions/checkout@v4` step gains:
```yaml
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha || github.sha }}
```
`github.event.workflow_run.head_sha` is the commit `ci.yml` actually ran against and
reported success for; it's empty/absent on a `workflow_dispatch` run, where `github.sha`
(the ref the dispatch was run against, `main` by default) is the correct fallback.

**Within §4.3's `deploy-frontend` job, the `app`-target steps become manual-only** — the
`trial`-target steps are unchanged and run on every trigger (automatic or manual):
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
          # unchanged from §4.3
```
And the combined "Deploy to Firebase Hosting" step's bash (§4.3) guards the `app` call
the same way:
```yaml
          # Ordering: app before trial (§4.3) — the app branch is only reached at all on
          # a manual dispatch, since the app target is never auto-deployed.
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            deploy_target app
          fi
          deploy_target trial
```
`deploy_target trial` always runs (both triggers) — this is the one line that makes
"deploy to this new site for main changes" true regardless of whether the automatic
trigger was caused by a backend-only or frontend-trial-only commit, per the user's own
"BACKEND OR THE new frontend folder, doesn't matter" — the whole job graph runs on any
push to `main` that passes CI, not on a path-filtered subset.

**Net effect, stated plainly:**

| Trigger | `deploy-backend` | `deploy-frontend`: build+deploy `trial` | `deploy-frontend`: build+deploy `app` | `tag` |
|---|---|---|---|---|
| Push to `main`, CI passes | Yes | Yes | **No** | Yes |
| Push to `main`, CI fails | Skipped | Skipped | Skipped | Skipped |
| Manual `workflow_dispatch` | Yes | Yes | Yes | Yes |

The `app` site (relocated full app) is therefore only ever redeployed by a human
explicitly running `workflow_dispatch` — exactly the "don't have to worry about deploying
to the other site" instruction — while `trial` and the backend track `main` automatically
once CI is green.

---

## 5. API Change Summary

**`backend/app.py`, CORS origin allow-list** (lines 33-38 today) — must deploy **before**
the frontend cutover (§4.5 step 3), or the relocated full app's first page load breaks
every API call.

**Old:**
```python
CORS(
    app,
    origins=[
        "https://juno-medical-clarity.web.app",
        "https://juno-medical-clarity.firebaseapp.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    ...
)
```

**New:**
```python
CORS(
    app,
    origins=[
        "https://juno-medical-clarity.web.app",       # trial app (SP3), primary address post-cutover
        "https://juno-medical-clarity.firebaseapp.com",
        "https://juno-app-99.web.app",                    # relocated full app — NEW
        "https://juno-app-99.firebaseapp.com",             # NEW
        "http://localhost:3000",
        "http://localhost:5173",                       # frontend/ (full app) dev server
        "http://localhost:5174",                       # frontend-trial/ dev server — NEW, see note
    ],
    ...
)
```

No other line in the `CORS(...)` call changes (methods, allow_headers, expose_headers,
`supports_credentials=False`, `max_age=600` all stay as-is).

**Note on `http://localhost:5174`:** Vite's default dev port is `5173`; if a developer runs
`frontend/` and `frontend-trial/` simultaneously, Vite auto-increments the second one to
`5174` — but only if `5174` is free and only as an *observed convention*, not a guarantee.
**Recommend to SP3:** pin `frontend-trial/vite.config.ts`'s `server.port` to `5174`
explicitly, so this CORS entry is a hard contract rather than an assumption about Vite's
port-selection behavior. Flagged as a cross-cutting note for SP3 (§9).

**Deploy ordering (already correct, no reordering needed):** `deploy.yml`'s existing job
graph already has `deploy-frontend: needs: deploy-backend`, so the backend (carrying this
CORS change) always deploys before the frontend job runs in the same workflow trigger.
The hard ordering constraint this PRD calls out is therefore **already satisfied by the
existing job structure** — no change to job dependencies is needed, only the CORS list
content itself.

---

## 6. Frontend Change Summary

### 6.1 Where the legal pages are served — routes inside SP3's trial app

**Decision: `/privacy` and `/terms` as client-side routes inside `frontend-trial/`, not
static HTML files.**

**Why:** `firebase.json`'s `trial` hosting target keeps the same catch-all SPA rewrite
(`{"source": "**", "destination": "/index.html"}` — §4.1) as today. A static HTML file
placed in `frontend-trial/dist/privacy.html` would need a **rewrite exception** (an
earlier, more specific `source` rule before the catch-all) to be served as a real file
instead of always resolving to `index.html` — extra Hosting config, extra build-output
wiring, for no benefit over just adding two routes to whatever router `frontend-trial/`
already uses. The main app already depends on `react-router-dom` (`frontend/package.json`,
confirmed); it's reasonable and consistent for `frontend-trial/` (a separate Vite/React
app per D3) to use the same library, in which case `/privacy` and `/terms` are two more
`<Route>` entries, no different from the existing input/processing/results routes SP3 is
already building. Deep-linking directly to `/privacy` or `/terms` works automatically
under the existing catch-all rewrite (any path falls through to `index.html`, the router
then renders the matching route client-side) — no special Hosting config at all.

**Contract for SP3 (precise, so SP3 can implement without re-deriving this):**
- Two routes, `/privacy` and `/terms`, each rendering one of the two full texts in §6.2 /
  §6.3 verbatim (plain React components — no markdown renderer needed, this is static
  copy, not user content).
- A `Footer` component (§6.4) rendered on every screen (input, processing, results, and
  the two legal pages themselves) containing the exact footer copy plus `<Link to="/privacy">`
  and `<Link to="/terms">` (client-side navigation, not full-page `<a href>` reloads,
  consistent with SPA routing).
- GA4 page-view instrumentation (D10, owned by SP3) should fire for `/privacy` and
  `/terms` navigations exactly like any other route change — no special-casing needed or
  wanted; a page view is a page view, it carries no document content.
- The `VITE_GA_MEASUREMENT_ID` env var (literal `G-4R0CDYKSPW`, injected by `deploy.yml`
  per §4.3) is the name SP3's GA-init code should read from — confirm this exact name with
  SP3 before they wire up `gtag`/GA4 initialization, since this PRD is choosing the name on
  SP3's behalf and SP3 hasn't been written yet.

### 6.2 Privacy Policy — full draft text

> **Not legal advice — user must review and approve before publishing (D8).** The text
> below is a first draft written to satisfy the disclosure requirements in this PRD's
> brief (Vertex AI / Firebase processing, immediate deletion, anonymous auth, GA
> disclosure, PHI warning, "not medical advice," "demo, not HIPAA-covered"). It has not
> been reviewed by a lawyer. See §8.

```markdown
# Privacy Policy — Juno Care Plan Simplifier (Trial)
Last updated: September 4, 2026

This page describes how the Juno Care Plan Simplifier trial ("this tool," "the Service")
handles your information. This is a free demo product. Please read this before uploading
anything.

## The short version
- We do not create accounts, and we do not collect your name, email address, or any
  contact information.
- Documents and text you submit are processed automatically and deleted as soon as your
  browser finishes displaying your results, with an automatic backstop that removes
  anything left behind if that never happens. We do not keep a copy.
- We use Google Analytics to count visits and understand how the tool is used. We do not
  send any of your document content to Analytics.
- This is a demonstration tool. It is not a substitute for professional medical advice,
  and it is not a HIPAA-covered service. Do not upload real patient information.

## What we process
When you upload a file or paste text, it is sent to:
- **Google Cloud Vertex AI (Gemini)**, to generate the simplified version of your care
  plan and to score how readable it is.
- **Google Firebase**, to coordinate the background job that processes your submission
  (a temporary, anonymous session — see "Accounts" below) and to briefly store the job's
  status and result while it runs.

These are the only third parties involved in processing your content, and both are Google
Cloud services operating under Google's standard cloud data-processing terms.

## How long we keep your content
We designed this tool around one rule: **your content should not outlive the job that
processes it.**
- The uploaded file(s) or pasted text are used only to generate your simplified result.
- The underlying file is deleted from our storage as soon as text has been extracted from
  it.
- The job record (including the simplified output) is deleted as soon as your browser has
  finished displaying your results and you close or navigate away from the page. As a
  safety net — in case that never happens, for example if you close the tab mid-process —
  an automatic backstop still removes it, typically within a day.
- We do not keep a permanent copy, we do not use your content to train any model, and we
  do not share it with anyone.

This means: your content **is** briefly written to a database and cloud storage bucket,
because that is how the automated processing pipeline works — but it is deleted
immediately after processing, not retained. We will never say "nothing is stored"; we
will always say "nothing is kept."

## Accounts
This tool does not have user accounts. To let the page track your submission's progress,
we automatically create an **anonymous, temporary Firebase identity** in your browser
when you load the page. It is not linked to your name, email, or any other identifying
information, and it does not persist any personal data. Anonymous identities that are no
longer in use are periodically deleted.

## Analytics
We use **Google Analytics 4** to understand how people use this trial — for example, how
many people visit, which input method they choose, whether the tool succeeds or fails,
and how long processing takes. Google Analytics sets cookies and collects standard usage
data (like your browser type and approximate location) in your browser.

**We do not send any document content, filenames, or care-plan text to Google
Analytics.** The events we record are limited to counts, categories, and timings (for
example, "a PDF was uploaded," "processing took 22 seconds," "the report was
downloaded") — never the substance of what you uploaded.

If you would prefer not to be measured by Google Analytics, you can use a browser
extension or setting that blocks Google Analytics scripts; the tool will still work.

## Do not upload real patient information
This is a public demo. **Do not upload real, identifiable patient health information
(PHI)** — use a sample, redacted, or fictional care plan instead. This service is not
covered by a HIPAA Business Associate Agreement and is not intended for real clinical
use.

## Not medical advice
The simplified text and readability score are generated automatically by an AI model and
may contain errors, omissions, or inaccuracies. **This tool does not provide medical
advice** and must never be used as the basis for a clinical or treatment decision. Always
consult a qualified healthcare professional about your care.

## Rate limiting
To keep this free demo available to everyone, submissions are limited per visitor. If you
are rate-limited, please try again later.

## Changes to this policy
We may update this policy as the tool evolves. The "Last updated" date at the top will
reflect the most recent change.

## Contact
Questions about this trial can be directed to tejitpabari99@gmail.com.
```

### 6.3 Terms & Conditions — full draft text

> Same caveat as §6.2: **not legal advice, draft only, user must review and approve
> (D8).**

```markdown
# Terms & Conditions — Juno Care Plan Simplifier (Trial)
Last updated: September 4, 2026

By using this tool, you agree to the following terms.

## 1. What this is
This is a free, public demonstration of Juno's care-plan simplification technology ("the
Service"). It is provided for evaluation and demonstration purposes only.

## 2. No medical advice
The Service uses an AI model to rewrite and score care-plan text. It is **not medical
advice**, is **not a substitute for professional clinical judgment**, and must not be
relied upon for any medical, treatment, or health-related decision. Always consult a
qualified healthcare professional.

## 3. No real patient data
You agree not to upload or submit any real, identifiable patient health information. Use
sample, redacted, or fictional content only. You are solely responsible for the content
you submit.

## 4. Provided "as is," no warranty
The Service is provided **"as is" and "as available,"** without warranties of any kind,
express or implied, including but not limited to accuracy, reliability, availability,
merchantability, or fitness for a particular purpose. We do not guarantee the Service
will be uninterrupted, error-free, or available at any given time, and it may be changed,
suspended, or withdrawn at any time without notice.

## 5. No reliance for clinical decisions
Any output produced by the Service — including simplified text, readability scores, and
downloaded reports — is generated automatically and may be incomplete, inaccurate, or out
of date. You agree not to rely on any output of this Service for a clinical, treatment,
insurance, or legal decision.

## 6. Acceptable use
You agree not to:
- Use the Service for any unlawful purpose, or to submit content you do not have the
  right to submit.
- Attempt to disrupt, overload, or circumvent the Service's rate limits or security
  controls.
- Use automated tools to submit requests at a volume beyond normal individual use.
- Attempt to reverse-engineer, scrape, or extract the underlying model, prompts, or
  infrastructure.

We may block or rate-limit any use that we believe violates these terms.

## 7. Rate limits
To keep the Service free and available to everyone, submissions are limited per visitor
(currently 5 per hour, subject to change without notice).

## 8. Limitation of liability
To the fullest extent permitted by law, we are not liable for any direct, indirect,
incidental, consequential, or special damages arising from your use of, or inability to
use, the Service, including any damages resulting from reliance on its output.

## 9. Right to withdraw the Service
We may modify, suspend, or discontinue the Service, in whole or in part, at any time and
without notice or liability.

## 10. Changes to these terms
We may update these terms as the Service evolves. Continued use of the Service after a
change constitutes acceptance of the updated terms.

## 11. Contact
Questions about these terms can be directed to tejitpabari99@gmail.com.
```

### 6.4 Footer copy — exact text

Rendered on every screen of the trial app (input, processing, results, and the two legal
pages), deliberately short and honest — it does not claim "no tracking" anywhere (which
would contradict the GA disclosure in §6.2):

```
No documents are saved — content is deleted right after processing, with an automatic
backstop if that doesn't happen.
This is a demo, not medical advice. Do not upload real patient information.

Privacy Policy · Terms & Conditions
```

The first two lines are static text; "Privacy Policy" and "Terms & Conditions" are the
`<Link>`s from §6.1.

### 6.5 Relocated full-app changes — grep findings

Grepped `frontend/src` for hardcoded references to `juno-medical-clarity.web.app` or the
Firebase project id, to check whether relocating the app to a new origin requires any
in-app code change:

- **`AdminPage.tsx`** (5 occurrences) and **`CarePlanJobErrorView.tsx`** /
  **`CarePlanJobResultView.tsx`** (2 occurrences each): all are hardcoded
  `console.cloud.google.com/...?project=juno-medical-clarity` deep links (Cloud Tasks,
  Traces, Logs, Firestore panel, Cloud Run metrics) — these reference the **GCP project
  id**, which does not change (both Hosting sites live in the same
  `juno-medical-clarity` GCP project). **No change needed.**
- **`api/firebase.ts`**: `firebaseConfig.authDomain` is read from
  `import.meta.env.VITE_FIREBASE_AUTH_DOMAIN` (a build-time secret, not hardcoded).
  Firebase Auth's `authDomain` is tied to the **project**, not to which Hosting site
  serves the page — it stays `juno-medical-clarity.firebaseapp.com` (or whatever the
  existing secret value already is) regardless of whether the app is served from
  `juno-medical-clarity.web.app` or `juno-app-99.web.app`. **No change needed** — the same
  `VITE_FIREBASE_*` secrets already used for `frontend/`'s build are reused unmodified in
  §4.3's new `Build trial` step (same project, same Firebase config, both frontends are
  clients of the same one Firebase project).
- No other hardcoded hosting-domain reference found anywhere in `frontend/src` (repo-wide
  grep for `juno-medical-clarity.web.app` / `juno-medical-clarity.firebaseapp.com`
  returned zero hits — every existing reference is one of the GCP console links above).

**Conclusion: the relocated full app needs zero in-app code changes.** The only changes
that make it work at its new address are the Hosting config (§4.1), the CI deploy target
(§4.3), and the CORS widening (§5) — all infrastructure, none of it inside
`frontend/src`.

---

## 7. Testing

No automated test suite covers Hosting config or CI YAML (neither `deploy.yml` nor
`firebase.json` are under `frontend`'s Vitest or `backend`'s pytest). Verification here is
manual, procedural — a checklist to run once during the cutover (§4.5) and again on every
subsequent normal deploy.

**Pre-cutover (one-time):**
1. `firebase hosting:sites:list --project juno-medical-clarity` shows both
   `juno-medical-clarity` and `juno-app-99` as existing sites, after §4.2's
   `hosting:sites:create`.
2. `cat .firebaserc` matches §4.1's "New" block exactly.
3. `firebase deploy --only hosting:app --project juno-medical-clarity --non-interactive
   --dry-run` (if the installed firebase-tools version supports `--dry-run`; otherwise
   skip straight to a real deploy against `app` only, verified in isolation before ever
   touching `trial`) resolves to the `juno-app-99` site, not the default one.

**Cutover verification (§4.5 step 5-6), against the live URLs:**
1. Visit `https://juno-app-99.web.app` — full app loads, sign-in / auth flow (whatever the
   full app currently requires) works, a care-plan job can be submitted and completes
   successfully (proves CORS §5 took effect and Firebase Auth's `authDomain` still
   resolves correctly per §6.5).
2. Visit `https://juno-medical-clarity.web.app` — trial app loads (not the old full app),
   submit a non-PHI sample document through input → live steps → results → download
   report, confirm it completes.
3. Visit `https://juno-medical-clarity.web.app/privacy` and `.../terms` directly (deep
   link, not via footer click) — both render the correct full text, proving the SPA
   rewrite (§6.1) handles direct navigation, not just in-app `<Link>` clicks.
4. Confirm `https://juno-app-99.web.app`'s Cloud Console deep links (`AdminPage.tsx`, §6.5)
   still resolve to the correct project dashboards (sanity-check that the "no in-app
   change needed" conclusion holds in practice, not just in grep).

**Every subsequent normal deploy (steady state), updated for §4.8's auto/manual split:**
1. On an **automatic** run (push to `main`, CI passed, §4.8): `deploy.yml`'s Actions log
   shows `deploy-backend` and the `trial` deploy block running — the `app`-target steps
   show as skipped, which is correct by design, not a bug.
2. On a **manual** `workflow_dispatch` run: the Actions log shows both the `app` and
   `trial` deploy blocks running in order, each either genuinely deploying or hitting the
   no-op-tolerance branch with the `::warning::` message — never a silent skip of one
   target.
3. Spot-check `https://juno-medical-clarity.web.app` (trial) after every automatic deploy;
   spot-check both live URLs after any manual deploy touching frontend code.

**Rollback drill (recommended once, not blocking launch):** trigger
`rollback-production.yml` against a known-good `prod-*` tag in a low-stakes moment (e.g.
right after the cutover, once `juno-app-99.web.app` is confirmed healthy) to confirm the
`target: app` / `entryPoint: .` fix (§4.4) actually works end-to-end before the first time
it's ever needed for a real incident.

---

## 8. Manual Intervention Required From You

1. **Review and approve the Privacy Policy (§6.2) and Terms & Conditions (§6.3) text
   before launch (D8, locked).** Both are first drafts, not reviewed by a lawyer. In
   particular: confirm the rate-limit number stated in Terms §7 ("5 per hour") stays in
   sync with whatever SP2 ships, and confirm you're comfortable with the liability/
   warranty language as a non-lawyer-reviewed draft for a health-adjacent public tool.
2. **[RESOLVED]** Contact method supplied: `tejitpabari99@gmail.com`. Both the
   Privacy Policy (§6.2) and Terms & Conditions (§6.3) now list this address in
   place of the `[CONTACT — placeholder]` line.
3. **[RESOLVED]** Cloud Run `max-instances` numbers are decided (`juno-api` = 10,
   `juno-worker` = 5, per user 2026-09-05) and wired into `deploy.yml`'s design (§4.6) —
   no further confirmation needed.
4. **Run §4.2's one-time `firebase hosting:sites:create` / `target:apply` commands**
   (delegated to us per the brainstorm, but still requires a human to actually execute
   them with real GCP/Firebase credentials before this PRD's config changes can be merged
   — they can't run from this design-only pass).
5. **[RESOLVED]** Owner has confirmed the deploy service account's IAM already
   covers `firebase hosting:sites:create` (and `target:apply`) — no additional role
   grant is needed before §4.2's one-time commands are run.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Does the existing `FIREBASE_SERVICE_ACCOUNT` secret's IAM role cover `hosting:sites:create` and `target:apply`, or only `hosting:deploy`? | **[RESOLVED]** — owner has confirmed the deploy service account's IAM already covers `hosting:sites:create` and `target:apply`; no role grant needed. See §8 item 5. |
| Q2 | Should there be a manual-approval gate (GitHub Environment protection rule) between the `app` and `trial` deploy steps, so a human confirms `juno-app-99.web.app` looks right before `trial` overwrites the primary address? | **[DEFERRED]** — considered in §4.5 step 5 and rejected for now as over-engineering for a single-operator project where Hosting deploys are seconds, not minutes, and the rollback path (§4.4) is the accepted safety net. Revisit if this project ever has multiple deploy operators or the cutover risk tolerance changes. |
| Q3 | Exact `max-instances` values for `juno-api` / `juno-worker` in `deploy.yml`'s `gcloud run services update` calls. | **[RESOLVED: `juno-api` = 10, `juno-worker` = 5, per user 2026-09-05]** — `juno-worker` is the real cost driver (it makes the Gemini calls); 5 concurrent is generous against SP2's 5-requests-per-IP-per-hour trial rate limit and consistent with `rollback-production.yml`'s existing `--max-instances=3` precedent for `juno-worker`. `juno-api` gets the higher ceiling (10) as the cheap, non-Gemini request layer. Wired into `deploy.yml` via new workflow-level env vars `API_MAX_INSTANCES` / `WORKER_MAX_INSTANCES` — see §4.6. |
| Q4 | `rollback-production.yml`'s `juno-api` deploy sets `--min-instances=1`, contradicting D7's locked "min-instances=0, no cold-start masking" for the primary deploy pipeline. Pre-existing inconsistency, not introduced by this PRD. | **[RESOLVED: corrected to `--min-instances=0`, per user 2026-09-05]** — D7 is locked and applies everywhere, including the emergency rollback path; there is no reason a rollback should reintroduce always-warm-instance cost D7 explicitly rejected. See §4.4 for the exact line change. |
| Q5 | Exact env var name (`VITE_GA_MEASUREMENT_ID`) SP3 should read for GA4 initialization. | **[RESOLVED for this PRD's purposes, confirm with SP3]** — this PRD picks the name and wires it into `deploy.yml`'s build step (§4.3) since SP3's PRD doesn't exist yet; SP3 should treat this as the contract unless SP3's own design has a strong reason to name it differently, in which case update §4.3's env var line to match. |
| Q6 | Should `frontend-trial/vite.config.ts` pin `server.port` to `5174` explicitly? | **[RESOLVED, recommend to SP3]** — see §5's note; avoids depending on Vite's auto-increment behavior for a value baked into the backend's CORS allow-list. Not this PRD's file to edit (owned by SP3), but the CORS entry (§5) is written against this assumption and should be confirmed once SP3 exists. |
| Q7 | Does the earlier `docs/public-version-scope.md` design (an `internal`/`public` two-target proposal with a `juno-public` site, predating the current brainstorm) need reconciling with this PRD? | **[RESOLVED: no]** — that document explored a similar idea under different names before D2 was locked; this PRD's target names (`trial`/`app`) and site ids (`juno-medical-clarity`/`juno-app-99`) supersede it. No code or config from that doc exists in the repo today (confirmed: `frontend/firebase.json` is still single-target), so there is nothing to migrate away from, only a naming precedent to note. |
| Q8 | Does CI (`ci.yml`, the PR-triggered workflow, distinct from `deploy.yml`) need a `frontend-trial` test/build job? | **[RESOLVED: yes, per user 2026-09-05]** — added as part of the automatic-deploy redesign (§4.7): the automatic deploy path (§4.8) is gated on CI passing, so CI must actually exercise `frontend-trial` for that gate to mean anything once SP3 lands it. |
| Q9 | Does the deletion-timing language in the Privacy Policy, Terms, and footer copy (§6.2, §6.4) accurately reflect Firestore TTL's real latency? | [RESOLVED: Privacy/Terms deletion-timing wording corrected per SP5's finding — explicit DELETE is the primary, effectively-immediate path; Firestore TTL is a backstop described as "typically within a day" (documented TTL latency is up to 24h after expiry). Uploaded file deletion at extraction remains fast and is stated as such.] |

**Dependencies:** Needs SP3's `frontend-trial/` to exist (with a `package-lock.json`,
`vite.config.ts`, and a build producing `dist/`) before `deploy.yml`'s new build step can
actually run — this PRD's CI design assumes that shape but cannot be merged/tested until
SP3 lands. Coordinates with SP2 on CORS origin list content (§5, already includes SP2's
trial dev port); the `max-instances` value SP2 deferred here is now resolved (§9 Q3, §4.6).
