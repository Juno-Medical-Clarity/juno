# Manual Steps & Scripts — 2026-06-21 Feature Initiative

**Project:** `juno-medical-clarity`
**Audience:** the owner (human-only steps the dev agents cannot do: GCP/Firebase/GitHub Console actions, `gcloud`/`git` CLI, deploys, BAA, manual QA).
**Status:** runbook only — nothing here has been executed.

> **The one hard ordering rule:** Sign the **GCP HIPAA BAA (Step 1)** before enabling Identity Platform (Step 4) and before any production PHI processing via Vertex AI (Steps 2–3). The BAA is a single document per GCP project — sign once; everything else just verifies it.

---

## 0. Set up your shell variables first

Run these once per terminal session so the copy-paste commands below work as-is. Replace the region with your actual Cloud Run region (check the existing deploy / Cloud Build trigger if unsure).

```bash
export PROJECT="juno-medical-clarity"
export REGION="us-central1"   # <-- CONFIRM this matches your existing Cloud Run region
gcloud config set project "$PROJECT"
gcloud auth login              # if not already authenticated
```

> Tip: to run an interactive login inside this Claude session, type `! gcloud auth login` in the prompt.

Verify you're pointed at the right project:

```bash
gcloud config get-value project   # should print juno-medical-clarity
```

---

## Recommended execution order (checklist)

- [ ] 1. Sign GCP HIPAA BAA *(compliance — do first)*
- [ ] 2. Verify Vertex AI API + IAM role *(SP09)*
- [ ] 3. Deploy SP09 code, then delete `GEMINI_API_KEY` GitHub secret *(SP09)*
- [ ] 4. Enable Identity Platform + verify *(SP10 — after BAA)*
- [ ] 5. Create Cloud Tasks queue *(SP01)*
- [ ] 6. Create invoker service account + grant `run.invoker` *(SP01)*
- [ ] 7. Add `_REGION` substitution to Cloud Build trigger *(SP01)*
- [ ] 8. Set Cloud Run env vars on juno-api *(SP01)*
- [ ] 9. Confirm Firestore database ID / set `VITE_FIRESTORE_DATABASE_ID` *(SP01)*
- [ ] 10. Deploy SP01 two-service cloudbuild *(SP01)*
- [ ] 11. Deploy Firestore security rules *(SP01)*
- [ ] 12. Verify `grade_breakdown` keys match config *(SP03/SP05)*
- [ ] 13. Download + parse + commit primock57 data *(SP07)*
- [ ] 14. Manual QA passes *(SP04/SP08/SP10)*
- [ ] 15. (Conditional) Assess prior PHI exposure with legal *(SP09)*

---

## 1. Sign the GCP HIPAA BAA  ⭐ FIRST

- **Type:** Console only (no CLI).
- **Where:** [GCP Console](https://console.cloud.google.com) → with project `juno-medical-clarity` selected → **Account / Company settings → Legal & Compliance → HIPAA** (also reachable via **IAM & Admin → Data Protection → HIPAA**).
- **Do:** Execute / accept the HIPAA Business Associate Agreement for the project.
- **Why:** Legal basis that makes Vertex AI + Identity Platform usage with PHI HIPAA-permissible.
- **Blocks:** Steps 3 (Vertex prod use) and 4 (Identity Platform).

---

## 2. Verify Vertex AI is enabled (SP09)

Enable the API (no-op if already enabled) and confirm the backend Cloud Run service account can call it.

```bash
# Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com

# Find the backend Cloud Run service account (note the email it runs as)
gcloud run services describe juno-api --region="$REGION" \
  --format="value(spec.template.spec.serviceAccountName)"

# Grant Vertex AI user role to that SA (replace SA_EMAIL with the value above;
# if it printed blank, the service uses the default compute SA: PROJECT_NUMBER-compute@developer.gserviceaccount.com)
export BACKEND_SA="SA_EMAIL"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/aiplatform.user"
```

> If `juno-api` doesn't exist yet (first deploy is Step 10), do this step against the current backend service name instead, and re-verify after Step 10.

---

## 3. Deploy SP09 code, then delete the `GEMINI_API_KEY` secret (SP09)

**Order matters:** deploy the Gemini-removal code first, *then* delete the secret — so a workflow rollback can't silently re-activate the non-BAA AI Studio path.

1. Merge/deploy the SP09 backend changes (Gemini path removed from `backend/utils/llm.py`; `GEMINI_API_KEY` removed from `deploy-backend.yml`, `rollback-production.yml`, `ci.yml`, and `preview-deploy.yml`).
2. Delete the secret:
   - **Where:** GitHub repo → **Settings → Secrets and variables → Actions → Repository secrets** → `GEMINI_API_KEY` → **Remove**.
   - Or via CLI:
     ```bash
     gh secret delete GEMINI_API_KEY
     ```

---

## 4. Enable Identity Platform + verify (SP10) — AFTER the BAA

All Console; **zero code changes** (do not edit `firebase.ts`, `.env.production`, or `backend/utils/firebase.py`). The upgrade is in-place and non-destructive — existing Firebase Auth users are preserved automatically (no migration script).

1. **Enable:** GCP Console → **Identity Platform** → **Upgrade** (or **APIs & Services → Library → "Identity Platform API" → Enable**).
   - CLI alternative to enable the API:
     ```bash
     gcloud services enable identitytoolkit.googleapis.com
     ```
2. **Verify users:** Console → **Identity Platform → Users** — confirm existing accounts are listed. Then log in end-to-end with a test clinician account.
3. **Verify SA role:** Console → **IAM & Admin → IAM** — filter by the backend Cloud Run SA; confirm it has `roles/firebase.admin` or `roles/identityplatform.admin`.

> MFA and Firebase Analytics changes are **deferred** — do not configure them now.

---

## 5. Create the Cloud Tasks queue (SP01)

Needed before the worker can receive jobs. `max-concurrent-dispatches=3` matches juno-worker's `--max-instances=3`.

```bash
gcloud tasks queues create care-plan-jobs \
  --location="$REGION" \
  --max-concurrent-dispatches=3
```

Verify:

```bash
gcloud tasks queues describe care-plan-jobs --location="$REGION"
```

---

## 6. Create the invoker service account + grant `run.invoker` (SP01)

Cloud Tasks authenticates to the internal-only worker via an OIDC token using this SA.

```bash
# Create the invoker SA
gcloud iam service-accounts create juno-worker-invoker \
  --display-name="Juno Worker Cloud Tasks Invoker"

# Grant it permission to invoke the juno-worker Cloud Run service
gcloud run services add-iam-policy-binding juno-worker \
  --region="$REGION" \
  --member="serviceAccount:juno-worker-invoker@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

> The `add-iam-policy-binding` line requires `juno-worker` to **exist**. If you haven't deployed yet (Step 10), create the SA now and run the binding command **after** the first worker deploy. The SA email (`juno-worker-invoker@${PROJECT}.iam.gserviceaccount.com`) is what you set as `WORKER_SERVICE_ACCOUNT` in Step 8.

---

## 7. Add the `_REGION` substitution to the Cloud Build trigger (SP01)

`cloudbuild.yaml` references `$_REGION` in both `gcloud run deploy` steps.

- **Where:** GCP Console → **Cloud Build → Triggers** → edit your backend trigger → **Substitution variables** → add:
  - `_REGION` = your region (e.g. `us-central1`)
  - (`_BACKEND_IMAGE` should already exist.)
- Save.

---

## 8. Set Cloud Run env vars on juno-api (SP01)

Set these on the **juno-api** service (Console **Cloud Run → juno-api → Edit & Deploy New Revision → Variables**, or via the `gcloud run deploy ... --set-env-vars` flags in your deploy):

| Variable | Value |
|---|---|
| `CLOUD_TASKS_QUEUE` | `projects/juno-medical-clarity/locations/<REGION>/queues/care-plan-jobs` |
| `WORKER_URL` | the juno-worker base URL (known after Step 10 — see note) |
| `WORKER_SERVICE_ACCOUNT` | `juno-worker-invoker@juno-medical-clarity.iam.gserviceaccount.com` |
| `JOB_TIMEOUT_SECONDS_SINGLE` | `300` |
| `JOB_TIMEOUT_SECONDS_BATCH` | `900` |

CLI example (run after the worker exists so you have its URL):

```bash
export WORKER_URL="$(gcloud run services describe juno-worker --region="$REGION" --format='value(status.url)')"

gcloud run services update juno-api --region="$REGION" \
  --set-env-vars="CLOUD_TASKS_QUEUE=projects/${PROJECT}/locations/${REGION}/queues/care-plan-jobs,WORKER_URL=${WORKER_URL},WORKER_SERVICE_ACCOUNT=juno-worker-invoker@${PROJECT}.iam.gserviceaccount.com,JOB_TIMEOUT_SECONDS_SINGLE=300,JOB_TIMEOUT_SECONDS_BATCH=900"
```

> `juno-worker`'s `JUNO_MODE=worker` is already set by `cloudbuild.yaml` — no action needed there.
> Because `WORKER_URL` is only known after the worker exists, the typical flow is: deploy (Step 10) → grab the worker URL → set this env var → it takes effect on the next juno-api revision.

---

## 9. Confirm the Firestore database ID (SP01)

The frontend reads `care_plan_outputs` directly via `onSnapshot`, so it must point at the **same** Firestore database as the backend.

```bash
# Check the backend's configured database id
gcloud run services describe juno-api --region="$REGION" \
  --format="value(spec.template.spec.containers[0].env)" | tr ',' '\n' | grep -i FIRESTORE
```

- If the database is `(default)` → nothing to do.
- If it's a **named** database → set `VITE_FIRESTORE_DATABASE_ID=<id>` in the frontend production environment (hosting env vars / `.env.production`) so `onSnapshot` connects to the same DB.

---

## 10. Deploy SP01 — two Cloud Run services (SP01)

`cloudbuild.yaml` (edited by the SP01 dev task) builds one image and deploys both services:
- **juno-api** — public, `--min-instances=1`, `--allow-unauthenticated`, `JUNO_MODE=api`
- **juno-worker** — internal, `--min-instances=0`, `--max-instances=3`, `--no-allow-unauthenticated`, `--ingress=internal`, `JUNO_MODE=worker`

Trigger via your normal backend deploy, or manually:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions _BACKEND_IMAGE=<your-image-ref>,_REGION=${REGION}
```

After this completes, go back and finish **Step 6's binding** (if deferred) and **Step 8's `WORKER_URL`**.

> Old SSE endpoints (`/care_plan`, `/care_plan/batch`) are kept deprecated until the SP3 window to avoid a deploy race — that's expected.

---

## 11. Deploy Firestore security rules (SP01)

Ensure authenticated users can read only their own docs; writes are backend-only (Admin SDK). The rule file is `firestore.rules` in the repo root.

```bash
firebase deploy --only firestore:rules
```

Expected rule shape for `care_plan_outputs`:

```
match /care_plan_outputs/{docId} {
  allow read: if request.auth != null && request.auth.uid == resource.data.uid;
  allow write: if false;  // backend only, via Admin SDK
}
```

> **No composite index needed** — the design uses N separate per-job `onSnapshot` listeners (owner decision SP1-2), not a query.

---

## 12. Verify `grade_breakdown` keys (SP03 / SP05)

The code fix already corrected `breakdownKeys` in `frontend/src/config.ts` to match `backend/utils/scoring_methods.py`. Sanity-check after deploy: open a graded result and confirm each method's sub-score labels render correctly (no stray/blank keys). Reference keys per method: smog `[grade, insufficient_sample]`, flesch_kincaid `[reading_ease, grade_level]`, dale_chall `[raw_score, grade_range]`, pemat `[understandability, actionability]`, sam `[content, literacy_demand, layout_typography]`, cdc_cci `[main_message, behavioral_recommendations, numbers, call_to_action]`.

---

## 13. Download, parse & commit primock57 data (SP07)

One-time offline data generation. **Do this only after the SP07 code (parser + `.gitignore` rules) is merged.** Run from the repo root (`/root/projects/juno`).

```bash
# 1. Download the source dataset (goes to /tmp, NOT the repo)
git clone https://github.com/Sydney-Informatics-Hub/primock57 /tmp/primock57

# 2. Run the parser (add --overwrite to replace existing files)
python -m backend.utils.preset_data_parser.primock57.parser --source /tmp/primock57
#   Expected: "primock57 parser: 57 written, 0 skipped, 0 errors"

# 3. Spot-check the output
ls preset-data/primock57/ | head -5
cat preset-data/primock57/day1-consultation01/consultation_notes.txt

# 4. Commit ONLY the generated files
git add preset-data/primock57/
git commit -m "Add primock57 preset data (57 consultations)"

# 5. (optional) clean up the source download
rm -rf /tmp/primock57
```

> **Do not commit the source clone.** The SP07 `.gitignore` rules exclude it; the fix to `.gitignore` ensures the generated `preset-data/primock57/**/*.txt` files are *not* ignored and will commit correctly. You can confirm with:
> ```bash
> git check-ignore -v preset-data/primock57/day1-consultation01/consultation_notes.txt   # should print nothing (not ignored)
> ```

---

## 14. Manual QA (SP04 / SP08 / SP10)

- **SP04 docs cross-links:** After SP3 + SP4 are both live, from each grading method's detail page click through to `/docs/grading/<slug>` and confirm Markdown renders (no raw syntax). Slugs: `smog`, `flesch-kincaid`, `dale-chall`, `pemat`, `sam`, `cdc-cci`. Unknown slug → not-found page.
- **SP08 PresetDataCard:** panel height ~480px; file-types section stays visible while scrolling appointments; preview resets on tab switch; header summary totals update across groups; long group names truncate with a `title` tooltip.
- **SP10 session timeout (local):** set `VITE_SESSION_TIMEOUT_MS=15000` in `frontend/.env.development.local`, then verify warning banner ~13s, auto sign-out at 15s, timer resets on activity / "Stay logged in".

---

## 15. (Conditional) Assess prior PHI exposure (SP09)

Only if `GEMINI_API_KEY` was ever set in production while real patient data was processed: consult legal + HIPAA compliance about a breach assessment under **45 CFR §164.400–414**. Not a console/CLI action.

---

## Decision-only items (no console/CLI action — confirm intent)

- **SP02:** success responses stay un-wrapped (error-only `ApiResponse`); `authenticatedFetchJson` rollout limited to `savedOutputs.ts` + SSE parser unless you want it broader.
- **SP06:** `frontend/public/preset-data/manifest.json` was a disk-only (gitignored) delete and `frontend/scripts/` was removed — already done in code; nothing to run.

---

## Quick reference — what each step protects

| Step | Without it… |
|---|---|
| 1 BAA | PHI through Vertex/Identity Platform is a HIPAA violation |
| 3 secret delete | a workflow rollback could re-route PHI to non-BAA AI Studio |
| 5 queue | job submission has nowhere to enqueue |
| 6 invoker SA | Cloud Tasks can't authenticate to the internal worker (403) |
| 8 env vars | juno-api can't enqueue tasks to the worker |
| 9 DB id | frontend `onSnapshot` reads the wrong/empty database |
| 11 rules | users could read other users' care plans |
| 13 gitignore fix | generated preset data silently skipped on `git add` |
