# Backend Infrastructure Architecture

This document describes the backend infrastructure shape found in this repo. It is architectural context, not a deployment runbook. For step-by-step setup and deployment commands, see `docs/setup_gcloud_deployment.md`.

## Runtime and Application

The backend is a Python Flask API in `backend/`, with `backend/app.py` as the WSGI application entry point. Routes are registered from `backend/routes/__init__.py` and include Simplify pipeline streaming, saved output CRUD, dataset reads, batch processing, and grading.

Production runs through Gunicorn from `backend/Dockerfile`:

```text
gunicorn app:app -b 0.0.0.0:8080 --workers=1 --threads=1 --timeout=300
```

The public API pattern is request/response plus Server-Sent Events for long-running pipeline work. The main `/simplify` route streams progress and final results as `text/event-stream`.

## Cloud and Hosting

The backend is hosted on Google Cloud Run as the `simplify-backend` service in the `juno-medical-clarity` Google Cloud/Firebase project. Repo deployment configuration uses `us-central1` as the region.

The frontend is hosted separately on Firebase Hosting and calls the backend through `VITE_API_PROCESSING_URL`. Firebase Hosting is frontend infrastructure, but it is part of the end-to-end deployment topology because browser clients authenticate with Firebase and send Firebase ID tokens to the backend.

## Backend Services and Dependencies

The repo shows these backend infrastructure services:

| Concern | Service | Repo evidence |
|---|---|---|
| Backend compute | Cloud Run | `README.md`, `backend/README.md`, `.github/workflows/deploy-backend.yml` |
| Container image build | Cloud Build | `backend/cloudbuild.yaml`, `.github/workflows/deploy-backend.yml` |
| Container image registry | Artifact Registry | `docs/setup_gcloud_deployment.md`, `.github/workflows/deploy-backend.yml` |
| Authentication | Firebase Authentication + Firebase Admin SDK | `backend/config.py`, `backend/utils/auth.py` |
| Application database | Firestore | `backend/utils/save_output.py`, `backend/routes/saved_outputs.py`, `backend/routes/grading.py` |
| Object storage | Google Cloud Storage | `backend/utils/save_output.py`, `backend/routes/saved_outputs.py`, `backend/utils/storage.py` |
| Secrets | Secret Manager for Firebase service account JSON | `.github/workflows/deploy-backend.yml`, `backend/.env.example` |
| AI model calls | Gemini through Vertex AI, with Gemini API key fallback in newer pipeline code | `backend/simplify/v1_2/pipeline.py`, `backend/utils/gemini_client.py`, `backend/utils/vertex_ai.py` |
| Logging and tracing | Cloud Logging and Cloud Trace | `backend/logging_config.py`, `backend/telemetry.py`, `backend/utils/LOGGING.md` |

The repo also contains Google Cloud Vision OCR utilities in `backend/utils/ocr.py` and `google-cloud-vision` in `backend/requirements.txt`, but the registered Simplify routes found here use `backend/utils/pdf_extract.py` for PDF text extraction. `google-cloud-speech` is listed in `backend/requirements.txt`, but no registered active route using Speech-to-Text was found in the current route registration.

## Data Architecture

Firestore is the primary application database. Saved Simplify outputs are stored in the `simplify_outputs` collection with user ownership (`uid`), display metadata, timestamps, optional batch metadata, an `input_pdf_gcs` URI, and sanitized output data. The persistence helper strips the `raw` field before saving output data.

Google Cloud Storage stores input PDF artifacts for saved outputs under paths like:

```text
simplify/<user_id>/inputs/<uuid>.pdf
```

Saved output reads verify document ownership in Firestore before returning metadata, full output data, or a short-lived signed URL for the original PDF. Deletes remove both the Firestore document and the associated GCS object when present.

Preset datasets are read from the repo-local `preset-data/` directory via `backend/utils/preset_data.py`; this is packaged with the deployed backend image rather than stored in a separate database or bucket based on the files found here.

No Redis, Memcached, relational database, Pub/Sub topic, task queue, Celery worker, or separate background worker service was found in the repo.

## Auth and Request Boundary

The `/simplify` API routes require a Firebase ID token in:

```text
Authorization: Bearer <firebase_id_token>
```

`backend/utils/auth.py` verifies the token with Firebase Admin SDK, stores the Firebase UID on `flask.g`, and passes `user_id` into route handlers. Saved-output routes enforce ownership by comparing Firestore document `uid` to the authenticated user.

Cloud Run is deployed with `--allow-unauthenticated` in the workflow, so application-level Firebase token verification is the backend access control boundary for protected routes.

## Deployment Architecture

At a high level, backend deployment is:

1. A push to the `deploy` branch triggers `.github/workflows/deploy-backend.yml`.
2. GitHub Actions authenticates to Google Cloud with the `GCP_SA_KEY` repository secret.
3. Cloud Build builds `backend/Dockerfile` using `backend/cloudbuild.yaml`.
4. The resulting image is pushed to Artifact Registry at `us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend`.
5. GitHub Actions deploys that image to the Cloud Run `simplify-backend` service with backend environment variables and Secret Manager injection for `FIREBASE_SERVICE_ACCOUNT_JSON`.

The frontend has a separate deployment workflow in `.github/workflows/deploy-frontend.yml`. A successful production deploy is tagged by `.github/workflows/tag-production-deploy.yml`, and rollback is handled by `.github/workflows/rollback-production.yml` plus `scripts/rollback_to_tag.sh`.

This section intentionally avoids command-level deployment steps. See `docs/setup_gcloud_deployment.md` for the infrastructure setup and deployment runbook.

## Container Usage

Containers are used for the backend. `backend/Dockerfile` builds a Python 3.11 slim image, installs `ffmpeg`, installs Python dependencies from `backend/requirements.txt`, copies the backend source, and starts Gunicorn on port 8080.

No Docker Compose file, Kubernetes manifest, or local container orchestration configuration was found. The container target found in the repo is Cloud Run.

## Configuration and IaC

Configuration is environment-variable driven. Important backend variables are documented in `backend/.env.example` and include:

- `GCP_PROJECT_ID`
- `GCP_BUCKET_NAME`
- `GCP_LOCATION`
- `VERTEX_AI_MODEL`
- `GEMINI_API_KEY`
- `FIRESTORE_DATABASE_ID`
- `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_PATH`
- `SIMPLIFY_DEFAULT_VERSION`

The repo contains deployment configuration and runbooks, but no full infrastructure-as-code stack was found. Specifically, no Terraform, Pulumi, Kubernetes, or Docker Compose files were found. Google Cloud resources are described procedurally in `docs/setup_gcloud_deployment.md`; CI/CD is configured with GitHub Actions workflow YAML files and `backend/cloudbuild.yaml`.
