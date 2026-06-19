# GCloud, Firebase, and GitHub Deployment Setup

Use this runbook to recreate Juno infrastructure from scratch in the single Google Cloud/Firebase project:

```text
juno-medical-clarity
```

The repo deploys:

- Backend: Flask API on Cloud Run
- Backend image storage: Artifact Registry
- Backend source/image build: Cloud Build
- Backend file storage: Cloud Storage
- Backend runtime secrets: Secret Manager
- App data/auth: Firebase/Auth/Firestore
- Frontend: Firebase Hosting
- CI/CD: GitHub Actions on the `deploy` branch

## 0. Constants

Use these values consistently:

```bash
PROJECT_ID=juno-medical-clarity
REGION=us-central1
BACKEND_SERVICE=simplify-backend
BACKEND_BUCKET=juno-medical-clarity-backend
ARTIFACT_REPO=juno
BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${BACKEND_SERVICE}"
DEPLOY_SA="github-actions-deploy@${PROJECT_ID}.iam.gserviceaccount.com"
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

## 11. Gemini API Key

The backend workflow injects `GEMINI_API_KEY` into Cloud Run from GitHub secrets.

Create or copy the key from Google AI Studio, then set GitHub repository secret:

```text
GEMINI_API_KEY
```

The backend also has Vertex AI support. The current deploy workflow sets:

```text
VERTEX_AI_MODEL=gemini-3.5-flash
GCP_LOCATION=us-central1
```

## 12. Firebase Hosting GitHub Secret

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

## 13. GitHub Repository Secrets Checklist

Set these in GitHub repository settings:

```text
GCP_SA_KEY
GEMINI_API_KEY
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

## 14. Repo Configuration Checklist

Backend deploy workflow should contain:

```text
GCP_PROJECT_ID: juno-medical-clarity
GCP_REGION: us-central1
GCP_BUCKET_NAME: juno-medical-clarity-backend
BACKEND_IMAGE: us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
```

Backend runtime envs in the workflow should include:

```text
GCP_PROJECT_ID
GCP_BUCKET_NAME
GCP_LOCATION
VERTEX_AI_MODEL
SIMPLIFY_DEFAULT_VERSION
FIRESTORE_DATABASE_ID
GEMINI_API_KEY
FIREBASE_SERVICE_ACCOUNT_JSON
```

Frontend deploy workflow should use:

```text
projectId: juno-medical-clarity
entryPoint: ./frontend
```

## 15. First Backend Deploy

The backend workflow runs on pushes to `deploy` when backend files or the backend workflow change.

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

After it succeeds, get the Cloud Run URL:

```bash
gcloud run services describe "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(status.url)"
```

Set GitHub secret `VITE_API_PROCESSING_URL` to that URL.

## 16. Frontend Deploy

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

## 17. Post-Deploy Verification

Backend:

```bash
BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(status.url)")

curl -i "$BACKEND_URL"
```

If the root path does not have a health route, a 404 from Cloud Run still proves the service is reachable. Use an app route for a stronger check.

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

## 18. Common Failures

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

the deploy service account can submit builds but cannot stream Cloud Build logs. The backend workflow uses `--suppress-logs` on `gcloud builds submit` so the command waits for build completion without streaming logs. Inspect build logs in Google Cloud Console or with a user account that has project viewer access.

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

## 19. Cleanup Sensitive Local Files

Remove downloaded JSON keys from your machine after adding them to GitHub or Secret Manager:

```bash
rm -f gcp-sa-key.json
rm -f path/to/firebase-admin-sdk.json
```

Do not commit service account JSON files.
