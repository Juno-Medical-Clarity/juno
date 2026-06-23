# GCloud, Firebase, and GitHub Deployment Setup

Use this runbook to recreate Juno infrastructure from scratch in the single Google Cloud/Firebase project:

```text
juno-medical-clarity
```

The repo deploys:

- Backend: Flask app on Cloud Run, run as **two services from the same image** —
  `juno-api` (`JUNO_MODE=api`) and `juno-worker` (`JUNO_MODE=worker`)
- Async jobs: Cloud Tasks queue dispatching to the worker's internal endpoint
- Backend image storage: Artifact Registry
- Backend source/image build: Cloud Build
- Backend file storage: Cloud Storage
- Backend runtime secrets: Secret Manager
- App data/auth: Firebase/Auth/Firestore
- Frontend: Firebase Hosting
- CI/CD: GitHub Actions on the `deploy` branch (plus ephemeral PR previews)

## Backend service topology

The same container image is deployed as different Cloud Run services depending on
the `JUNO_MODE` environment variable, which selects which Flask blueprints are
registered in `backend/app.py`:

| `JUNO_MODE` | Blueprints registered | Where it runs |
|---|---|---|
| `api` (default) | API/enqueue routes | Production `juno-api` service |
| `worker` | Worker route `POST /internal/jobs/execute/<job_id>` | Production `juno-worker` service |
| `combined` | Both API and worker routes in one service | Ephemeral PR previews |

Async flow: an API request creates a Firestore job doc and enqueues a Cloud Task
on the `care-plan-jobs` queue. Cloud Tasks then calls
`POST /internal/jobs/execute/<job_id>` on `WORKER_URL`, attaching a Google-signed
OIDC token minted for the worker invoker service account. The worker verifies that
token (see [section 12](#12-worker-endpoint-oidc-security)) before executing the
pipeline.

- **Production**: `juno-api` (public, `--allow-unauthenticated`, `--min-instances=1`)
  enqueues tasks whose `WORKER_URL` points at `juno-worker`. `juno-worker` is
  private (`--no-allow-unauthenticated`, `--ingress=internal`,
  `--min-instances=0 --max-instances=3`) and is invoked by Cloud Tasks via the
  OIDC token plus a `roles/run.invoker` grant.
- **PR previews**: a single `combined` service named
  `simplify-backend-pr-<PR_NUMBER>` is deployed `--allow-unauthenticated`. Its
  `WORKER_URL` points at *itself*, so it enqueues tasks that call back into the
  same service. Because the preview is publicly reachable, the in-app OIDC check
  is what protects the worker route.

## 0. Constants

Use these values consistently:

```bash
PROJECT_ID=juno-medical-clarity
REGION=us-central1
API_SERVICE=juno-api
WORKER_SERVICE=juno-worker
BACKEND_BUCKET=juno-medical-clarity-backend
ARTIFACT_REPO=juno
# Both Cloud Run services share this single image. The repo image name is still
# "simplify-backend"; only the deployed service names changed to juno-api/juno-worker.
BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/simplify-backend"
DEPLOY_SA="github-actions-deploy@${PROJECT_ID}.iam.gserviceaccount.com"
WORKER_INVOKER_SA="juno-worker-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
TASKS_QUEUE=care-plan-jobs
FIREBASE_SECRET_NAME=firebase-service-account
```

The backend workflow expects the same values in `.github/workflows/deploy-backend.yml`.

## 1. Local Prerequisites

Install and authenticate the CLIs:

```bash
gcloud auth login
gcloud config set project "$PROJECT_ID"
gcloud auth application-default login

npm install -g firebase-tools
firebase login
```

Confirm project access:

```bash
gcloud projects describe "$PROJECT_ID"
firebase projects:list
```

## 2. Create or Select the Firebase/GCP Project

If the Firebase project already exists, just select it:

```bash
gcloud config set project "$PROJECT_ID"
firebase use "$PROJECT_ID"
```

If rebuilding from scratch, create the Google Cloud project first, then add Firebase to it in the Firebase Console:

1. Go to Firebase Console.
2. Add project.
3. Use project ID `juno-medical-clarity`.
4. Disable Google Analytics unless needed.

## 3. Enable Required Google Cloud APIs

```bash
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  cloudtasks.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  firestore.googleapis.com \
  firebase.googleapis.com \
  firebasehosting.googleapis.com \
  identitytoolkit.googleapis.com \
  aiplatform.googleapis.com \
  --project "$PROJECT_ID"
```

## 4. Firebase Product Setup

### Authentication

In Firebase Console:

1. Go to Authentication.
2. Click Get started.
3. Enable the sign-in providers the app uses.

At minimum, configure the provider used by your current users. If unsure, start with Google provider and Email/Password only if the UI supports it.

### Firestore

Create Firestore in Native mode:

```bash
gcloud firestore databases create \
  --project "$PROJECT_ID" \
  --database="(default)" \
  --location="$REGION"
```

If the database already exists, this command may fail with an already-exists error. That is fine.

### Firebase Web App

In Firebase Console:

1. Project settings.
2. General.
3. Your apps.
4. Add or open the Web app.
5. Copy the Firebase config values.

Those values become GitHub secrets:

```text
VITE_FIREBASE_API_KEY
VITE_FIREBASE_AUTH_DOMAIN
VITE_FIREBASE_PROJECT_ID
VITE_FIREBASE_STORAGE_BUCKET
VITE_FIREBASE_MESSAGING_SENDER_ID
VITE_FIREBASE_APP_ID
```

Expected project-oriented values:

```text
VITE_FIREBASE_PROJECT_ID=juno-medical-clarity
VITE_FIREBASE_AUTH_DOMAIN=juno-medical-clarity.firebaseapp.com
VITE_FIREBASE_STORAGE_BUCKET=<value from Firebase web config>
```

Do not guess `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_MESSAGING_SENDER_ID`, or `VITE_FIREBASE_APP_ID`; copy them from Firebase.

### Firebase Hosting

The repo already has `frontend/firebase.json`. The GitHub workflow deploys with:

```text
projectId: juno-medical-clarity
entryPoint: ./frontend
channelId: live
```

If you need to initialize hosting manually:

```bash
cd frontend
firebase use "$PROJECT_ID"
firebase init hosting
```

When prompted:

- Public directory: `dist`
- Single-page app rewrite: yes
- GitHub deploy setup: no, because this repo already has `.github/workflows/deploy-frontend.yml`

## 5. Cloud Storage Bucket

Create the backend bucket:

```bash
gcloud storage buckets create "gs://${BACKEND_BUCKET}" \
  --project "$PROJECT_ID" \
  --location "$REGION" \
  --uniform-bucket-level-access
```

If this returns HTTP 409 and you already created the bucket in this project, continue. Verify ownership:

```bash
gcloud storage buckets describe "gs://${BACKEND_BUCKET}" \
  --project "$PROJECT_ID"
```

If the bucket is owned by someone else, choose a new globally unique name and update all `GCP_BUCKET_NAME` references in the repo and workflow.

## 6. Artifact Registry

Create the Docker repository used by Cloud Build and Cloud Run:

```bash
gcloud artifacts repositories create "$ARTIFACT_REPO" \
  --project "$PROJECT_ID" \
  --repository-format docker \
  --location "$REGION" \
  --description "Juno Docker images"
```

If it already exists, continue.

Expected backend image:

```bash
echo "$BACKEND_IMAGE"
```

Expected output:

```text
us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
```

## 7. GitHub Actions Deploy Service Account

Create a dedicated deploy service account:

```bash
gcloud iam service-accounts create github-actions-deploy \
  --project "$PROJECT_ID" \
  --display-name "GitHub Actions Deploy"
```

Grant deploy permissions:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/cloudbuild.builds.editor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/secretmanager.secretAccessor"
```

Create a JSON key for GitHub Actions:

```bash
gcloud iam service-accounts keys create gcp-sa-key.json \
  --iam-account "$DEPLOY_SA" \
  --project "$PROJECT_ID"
```

In GitHub, set repository secret `GCP_SA_KEY` to the full contents of `gcp-sa-key.json`.

Delete the local key file after storing the secret:

```bash
rm gcp-sa-key.json
```

## 8. Cloud Build Service Account Permissions

Cloud Build may run as either the Compute Engine default service account or the legacy Cloud Build service account, depending on project age/configuration. Grant Artifact Registry write permission to both; it is simple and avoids ambiguity.

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
LEGACY_CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${LEGACY_CLOUDBUILD_SA}" \
  --role="roles/artifactregistry.writer"
```

If Cloud Build later fails while reading source/uploading build artifacts, grant the active build service account Cloud Storage object access:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${LEGACY_CLOUDBUILD_SA}" \
  --role="roles/storage.objectAdmin"
```

## 9. Runtime Firebase Admin Secret

The backend reads Firebase Admin credentials from `FIREBASE_SERVICE_ACCOUNT_JSON`, injected from Secret Manager by Cloud Run.

Create or download a Firebase Admin SDK service account JSON:

1. Firebase Console.
2. Project settings.
3. Service accounts.
4. Generate new private key.

Store it in Secret Manager:

```bash
gcloud secrets create "$FIREBASE_SECRET_NAME" \
  --project "$PROJECT_ID" \
  --replication-policy automatic

gcloud secrets versions add "$FIREBASE_SECRET_NAME" \
  --project "$PROJECT_ID" \
  --data-file path/to/firebase-admin-sdk.json
```

If the secret already exists, only add a new version:

```bash
gcloud secrets versions add "$FIREBASE_SECRET_NAME" \
  --project "$PROJECT_ID" \
  --data-file path/to/firebase-admin-sdk.json
```

## 10. Cloud Run Runtime Service Account Permissions

The workflow currently deploys Cloud Run without an explicit `--service-account`, so Cloud Run uses the Compute Engine default service account unless changed in the Cloud Run console.

Grant runtime permissions to the default runtime account:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding "$FIREBASE_SECRET_NAME" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/aiplatform.user"
```

If you later configure a dedicated Cloud Run runtime service account, grant these same roles to that account instead.

The runtime SA also needs `roles/cloudtasks.enqueuer` so `juno-api` (and the
combined preview) can create tasks on the queue:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudtasks.enqueuer"
```

## 11. Async Jobs: Cloud Tasks Queue and Worker Invoker IAM

The async care-plan / batch flow needs a Cloud Tasks queue plus a dedicated
"invoker" service account that Cloud Tasks impersonates to mint OIDC tokens for
the worker. Set this up once.

### Create the Cloud Tasks queue

```bash
gcloud tasks queues create "$TASKS_QUEUE" \
  --project "$PROJECT_ID" \
  --location "$REGION"
```

This produces the queue resource name used in `CLOUD_TASKS_QUEUE`:

```text
projects/juno-medical-clarity/locations/us-central1/queues/care-plan-jobs
```

### Create the worker invoker service account

Cloud Tasks attaches an OIDC token issued for this identity; the worker verifies
its email matches `WORKER_SERVICE_ACCOUNT`.

```bash
gcloud iam service-accounts create juno-worker-invoker \
  --project "$PROJECT_ID" \
  --display-name "Juno worker invoker (Cloud Tasks OIDC)"
```

### Grant the three IAM bindings

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
CLOUDTASKS_AGENT="service-${PROJECT_NUMBER}@gcp-sa-cloudtasks.iam.gserviceaccount.com"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# 1. Let the Cloud Tasks service agent mint OIDC tokens AS the invoker SA.
gcloud iam service-accounts add-iam-policy-binding "$WORKER_INVOKER_SA" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${CLOUDTASKS_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator"

# 2. Let the Cloud Run runtime SA (the enqueuing service) attach the invoker SA
#    to tasks it creates (actAs).
gcloud iam service-accounts add-iam-policy-binding "$WORKER_INVOKER_SA" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/iam.serviceAccountUser"

# 3. Let the invoker SA call the private juno-worker Cloud Run service.
gcloud run services add-iam-policy-binding "$WORKER_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --member="serviceAccount:${WORKER_INVOKER_SA}" \
  --role="roles/run.invoker"
```

The `run.invoker` grant is what lets Cloud Tasks reach the private (`--no-allow-unauthenticated`)
`juno-worker`. The `--allow-unauthenticated` combined preview does not rely on
this grant; it relies on the in-app OIDC check instead (see section 12).

## 12. Worker Endpoint OIDC Security

The worker route `POST /internal/jobs/execute/<job_id>` (`backend/routes/worker.py`)
verifies the OIDC token Cloud Tasks attaches, rejecting anything else with `403`.
On each request it checks:

- An `Authorization: Bearer <token>` header is present.
- The JWT signature/issuer/expiry are valid (via google-auth).
- `email_verified` is truthy.
- When `WORKER_SERVICE_ACCOUNT` is set, the token `email` matches it.
- The token `aud` equals the reconstructed request URL (`X-Forwarded-Proto` +
  host + path).

A `WORKER_VERIFY_OIDC=false` kill-switch disables verification for local/dev/tests
only. The deploy workflows never set it, so verification stays enforced in every
deployed environment. This matters because the combined PR preview is
`--allow-unauthenticated`; without the in-app check, its worker route would be
publicly callable.

## 13. Gemini Model via Vertex AI

The backend calls Gemini through **Vertex AI** (`backend/utils/vertex_ai.py`); the
standalone Gemini API key path has been removed, so no `GEMINI_API_KEY` secret is
needed. The deploy workflows set:

```text
VERTEX_AI_MODEL=gemini-3.5-flash
GCP_LOCATION=us-central1
```

Vertex AI access comes from the `roles/aiplatform.user` grant on the Cloud Run
runtime service account (section 10).

## 14. Firebase Hosting GitHub Secret

The frontend workflow uses Firebase Hosting deploy action with:

```text
FIREBASE_SERVICE_ACCOUNT
```

This should be a Firebase/GCP service account JSON that can deploy Firebase Hosting for `juno-medical-clarity`.

If recreating it:

1. Firebase Console.
2. Project settings.
3. Service accounts.
4. Generate new private key.
5. Store the full JSON as GitHub repository secret `FIREBASE_SERVICE_ACCOUNT`.

If Firebase Hosting deploy fails with permission errors, grant the service account Firebase Hosting Admin:

```bash
FIREBASE_DEPLOY_SA="<client_email from FIREBASE_SERVICE_ACCOUNT json>"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${FIREBASE_DEPLOY_SA}" \
  --role="roles/firebasehosting.admin"
```

## 15. GitHub Repository Secrets Checklist

Set these in GitHub repository settings:

```text
GCP_SA_KEY
FIREBASE_SERVICE_ACCOUNT
VITE_FIREBASE_API_KEY
VITE_FIREBASE_AUTH_DOMAIN
VITE_FIREBASE_PROJECT_ID
VITE_FIREBASE_STORAGE_BUCKET
VITE_FIREBASE_MESSAGING_SENDER_ID
VITE_FIREBASE_APP_ID
VITE_API_PROCESSING_URL
```

Notes:

- `GCP_SA_KEY`: deploy service account JSON for `github-actions-deploy`.
- `FIREBASE_SERVICE_ACCOUNT`: Firebase Hosting deploy JSON.
- `VITE_API_PROCESSING_URL`: Cloud Run backend URL. Use a placeholder for the first backend deploy, then update it after Cloud Run exists.
- `VITE_FIREBASE_*`: copy from Firebase Web App config.

## 16. Repo Configuration Checklist

Backend deploy workflow should contain:

```text
GCP_PROJECT_ID: juno-medical-clarity
GCP_REGION: us-central1
GCP_BUCKET_NAME: juno-medical-clarity-backend
BACKEND_IMAGE: us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
```

Backend runtime environment variables are set per-service by the deploy
workflows. The full set:

| Variable | Set on | Meaning |
|---|---|---|
| `JUNO_MODE` | api / worker / preview | `api`, `worker`, or `combined` — selects which blueprints register |
| `GCP_PROJECT_ID` | all | GCP project id |
| `GCP_BUCKET_NAME` | all | Backend Cloud Storage bucket |
| `GCP_LOCATION` | all | Region for Vertex AI / Cloud Tasks (`us-central1`) |
| `VERTEX_AI_MODEL` | all | Gemini model id served via Vertex AI (`gemini-3.5-flash`) |
| `SIMPLIFY_DEFAULT_VERSION` | all | Default pipeline version (`v1-2`) |
| `FIRESTORE_DATABASE_ID` | all | Firestore database (`(default)`) |
| `CLOUD_TASKS_QUEUE` | api + preview | Full queue resource name `projects/<PROJECT>/locations/<REGION>/queues/care-plan-jobs` |
| `WORKER_URL` | api + preview | Base URL the worker route is reached at (prod: `juno-worker` URL; preview: the service's own URL) |
| `WORKER_SERVICE_ACCOUNT` | api + worker + preview | `juno-worker-invoker@<PROJECT>.iam.gserviceaccount.com`; on the worker it is the expected OIDC email |
| `JOB_TIMEOUT_SECONDS_SINGLE` | api + preview | Cloud Task dispatch deadline for single jobs (`300`) |
| `JOB_TIMEOUT_SECONDS_BATCH` | api + preview | Cloud Task dispatch deadline for batch items (`900`) |
| `WORKER_VERIFY_OIDC` | (none in deploy) | Kill-switch for the worker OIDC check; defaults enabled, only set falsey in local/tests |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | all (secret) | Firebase Admin SDK JSON, injected from Secret Manager |

Notes on what each service gets:

- `juno-api`: the API/enqueue set, including `CLOUD_TASKS_QUEUE`, `WORKER_URL`
  (resolved from the deployed `juno-worker` URL), `WORKER_SERVICE_ACCOUNT`, and
  the `JOB_TIMEOUT_SECONDS_*` pair.
- `juno-worker`: the base set plus `WORKER_SERVICE_ACCOUNT` (used as the expected
  OIDC caller email). It does not enqueue, so it has no `CLOUD_TASKS_QUEUE` /
  `WORKER_URL`.
- `simplify-backend-pr-<N>` (preview): the full combined set with
  `JUNO_MODE=combined`; `WORKER_URL` is patched to the service's own URL in a
  follow-up step after deploy (the URL is not known beforehand).

Frontend deploy workflow should use:

```text
projectId: juno-medical-clarity
entryPoint: ./frontend
```

All workflows that run Node (`ci.yml`, `deploy-frontend.yml`, `preview-deploy.yml`,
`rollback-production.yml`) standardize on `node-version: '24'`.

## 17. First Backend Deploy

The backend workflow runs on every push to `deploy`. It builds and pushes one
image via `backend/cloudbuild.yaml`, which also deploys both `juno-api` and
`juno-worker` from that image; the workflow then resolves the `juno-worker` URL and
sets the full per-service env var sets (including `WORKER_URL` on `juno-api`). This
keeps each production release tied to both a backend and frontend deploy result,
even when one side has no code changes.

To trigger from local git:

```bash
git checkout main
git pull
git checkout deploy
git pull
git merge main
git push origin deploy
```

Watch the run:

```bash
gh run list --branch deploy --limit 5
gh run watch
```

After it succeeds, get the public API URL (the frontend talks to `juno-api`, not
the private `juno-worker`):

```bash
gcloud run services describe "$API_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(status.url)"
```

Set GitHub secret `VITE_API_PROCESSING_URL` to that URL.

## 18. Frontend Deploy

The frontend workflow runs on every push to `deploy`.

After updating `VITE_API_PROCESSING_URL`, rerun the frontend workflow from GitHub Actions, or push a no-op commit to `deploy`.

Manual local build check:

```bash
cd frontend
npm ci
npm run build
```

Manual Firebase deploy, if needed:

```bash
cd frontend
npm ci
npm run build
firebase deploy --only hosting --project "$PROJECT_ID"
```

## 19. Production Tags

After both `Deploy Backend` and `Deploy Frontend` succeed for the same `deploy` commit, the `Tag Production Deploy` workflow creates an annotated tag:

```text
prod-YYYYMMDD-HHMMSS
```

The tag points at the exact deployed commit. If the tag workflow runs twice for the same commit, it detects the existing `prod-*` tag and does not create a duplicate.

List production tags:

```bash
git fetch --tags
git tag --list 'prod-*' --sort=-creatordate
```

Show what is in a production tag:

```bash
git show --stat prod-YYYYMMDD-HHMMSS
```

## 20. Git-Based Rollback

Use the rollback script to trigger a runtime rollback from a production tag:

```bash
scripts/rollback_to_tag.sh prod-YYYYMMDD-HHMMSS
```

The script:

1. Fetches tags.
2. Verifies the requested `prod-*` tag exists.
3. Triggers the `Rollback Production` GitHub Actions workflow with the tag.

The rollback workflow checks out the tag, builds and pushes a tagged image via
`backend/cloudbuild-build.yaml` (build/push only — it deliberately does NOT use
`cloudbuild.yaml`, whose embedded deploy steps would re-run a production deploy),
then redeploys **both** `juno-worker` and `juno-api` from that image (resolving the
worker URL in between and re-setting the full `juno-api` env set), plus the
frontend. It does not change `main` or `deploy`.

For emergency runtime rollback without a Git PR:

- Cloud Run: use revision traffic rollback in the Cloud Run console or `gcloud run services update-traffic`.
- Firebase Hosting: use Hosting release history rollback in the Firebase console.

The Git rollback script is slower, but it keeps backend and frontend source state aligned.

## 21. Post-Deploy Verification

Backend:

```bash
API_URL=$(gcloud run services describe "$API_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(status.url)")

curl -i "$API_URL/health"
```

The `juno-worker` service is private (`--ingress=internal`,
`--no-allow-unauthenticated`), so it is not directly reachable from your machine;
verify it indirectly by running an async job through `juno-api` and confirming the
job doc reaches a terminal state in Firestore. An end-to-end async check:

1. Submit a `POST /care_plan/jobs` request to `juno-api`.
2. Confirm a Cloud Task is created on the `care-plan-jobs` queue.
3. Confirm the Firestore job doc transitions `processing` → `completed`.
4. If it stalls, check `juno-worker` logs for OIDC `403`s (env/IAM misconfig).

Frontend:

1. Open the Firebase Hosting URL.
2. Sign in.
3. Run one simplify request.
4. Confirm the browser calls the new Cloud Run URL.
5. Confirm a saved output appears in Firestore and the backend bucket receives any uploaded file objects.

Cloud logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"' \
  --project "$PROJECT_ID" \
  --limit 20 \
  --format json
```

## 22. Common Failures

### `gcloud.builds.submit PERMISSION_DENIED`

Likely causes:

- `GCP_SA_KEY` points to the wrong service account.
- Deploy service account lacks `roles/cloudbuild.builds.editor`.
- Active project is not `juno-medical-clarity`.

Check the Actions log for:

```text
This command is authenticated as ...
CLOUDSDK_CORE_PROJECT
```

### Build is created but workflow fails while streaming logs

If the build is created and later succeeds, but the GitHub step exits with a message like:

```text
This tool can only stream logs if you are Viewer/Owner of the project
```

the deploy service account can submit builds but cannot stream logs from the default Cloud Build logs bucket. The backend workflow uses `backend/cloudbuild.yaml`, which sets `options.logging: CLOUD_LOGGING_ONLY` so build logs are written to Cloud Logging instead of the default Cloud Storage logs bucket.

### Artifact Registry push denied

Grant `roles/artifactregistry.writer` to the Cloud Build service account that appears in the Cloud Build log.

### Cloud Run deploy denied

Grant the deploy service account:

```text
roles/run.admin
roles/iam.serviceAccountUser
```

### Secret Manager mount denied

Grant `roles/secretmanager.secretAccessor` to the Cloud Run runtime service account.

### Backend cannot save files

Grant the Cloud Run runtime service account:

```text
roles/storage.objectAdmin
```

Confirm `GCP_BUCKET_NAME` matches the bucket created in this guide.

### Async jobs never complete / worker returns 403

The worker rejects requests that fail OIDC verification with `403`. Check:

- The `care-plan-jobs` queue exists in `us-central1` and `CLOUD_TASKS_QUEUE` on
  `juno-api` points at it.
- `WORKER_URL` on `juno-api` is the real `juno-worker` URL (or, on a preview, the
  preview's own URL).
- `WORKER_SERVICE_ACCOUNT` is set to the invoker SA on the enqueuing service AND
  on the worker — the worker compares the token `email` against it.
- The Cloud Tasks service agent has `roles/iam.serviceAccountTokenCreator` on the
  invoker SA, and the runtime SA has `roles/iam.serviceAccountUser` on it (actAs).
- For production specifically, the invoker SA has `roles/run.invoker` on
  `juno-worker` (the worker is private).
- The token audience must match the worker URL; a proxy that strips
  `X-Forwarded-Proto` can cause an audience mismatch.

### Frontend points at old backend

Update GitHub secret:

```text
VITE_API_PROCESSING_URL
```

Then rerun frontend deploy.

### Firebase Hosting deploy denied

Grant the service account in `FIREBASE_SERVICE_ACCOUNT`:

```text
roles/firebasehosting.admin
```

## 23. Cleanup Sensitive Local Files

Remove downloaded JSON keys from your machine after adding them to GitHub or Secret Manager:

```bash
rm -f gcp-sa-key.json
rm -f path/to/firebase-admin-sdk.json
```

Do not commit service account JSON files.
