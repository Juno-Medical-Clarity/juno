# Juno Backend

Python Flask API for the Simplify pipeline. Deployed on Google Cloud Run.

## API Routes

All routes except `/health` require `Authorization: Bearer <firebase_id_token>`.

### Pipeline

| Method | Path | Description |
|---|---|---|
| `POST` | `/simplify` | Run the simplify pipeline (SSE stream) |

The `version` field is optional and can be sent as form metadata or in a JSON
body. Supported values are `v1`, `v1-1`, and `v1-2`; omitting `version` uses
the latest default, `v1-2`.

**Request:** `multipart/form-data`
- `files` — one or more PDF/TXT/DOCX files (max 10 files, 25 MB aggregate)
- `text` — plain text input (alternative to files)
- `version` — optional pipeline version (`v1`, `v1-1`, or `v1-2`; default `v1-2`)

**SSE Event Stream:**
```
data: {"step": 1, "status": "active", "label": "Extracting text"}
data: {"step": 1, "status": "done", "label": "Extracting text"}
data: {"step": 2, "status": "active", "label": "Detecting medical terms"}
...
data: {"step": "result", "data": { ...AppointmentNote... }}
data: {"step": "error", "error": "error message"}
```

### Saved Outputs

| Method | Path | Description |
|---|---|---|
| `GET` | `/simplify/saved` | List user's saved outputs (metadata only) |
| `GET` | `/simplify/saved/<id>` | Get full output data for one saved output |
| `PATCH` | `/simplify/saved/<id>` | Rename saved output `{"name": "new name"}` |
| `DELETE` | `/simplify/saved/<id>` | Delete saved output + GCS file |
| `GET` | `/simplify/saved/<id>/input-pdf-url` | Get 30-min signed URL for original PDF |

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (no auth required) |

## Storage Model

- **GCS**: Combined input PDF stored at `simplify/<user_id>/inputs/<uuid>.pdf`
- **Firestore**: Output metadata in `simplify_outputs` collection

  ```
  simplify_outputs/<doc_id>:
    uid: string
    name: string
    source_filename: string
    created_at: timestamp
    updated_at: timestamp
    input_pdf_gcs: string (gs:// URI)
    output_data: map (AppointmentNote without 'raw' field)
  ```

### Firestore Composite Index

Required for `GET /simplify/saved` (uid filter + created_at sort):
- Collection: `simplify_outputs`
- Fields: `uid ASC`, `created_at DESC`

Create in Firebase Console → Firestore → Indexes → Add Composite Index.

## Pipeline Versions

| Version | File | Notes |
|---|---|---|
| V1.2 | `simplify/v1_2/pipeline.py` | Current, primary version |
| V1.1 | `simplify/v1_1/pipeline.py` | Intermediate |
| V1 | `simplify/v1/pipeline.py` | Legacy |

### Adding a New Version

1. Create `simplify/v<X>/` with `__init__.py` and `pipeline.py`
2. Subclass `SimplifyPipeline` from `simplify/interface.py`, implement `run(text) -> dict`
3. Add a version-specific handler module under `routes/`
4. Register the version in the `/simplify` dispatcher

## Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env values
python app.py
# Server starts on http://0.0.0.0:8080
```

## Cloud Run Deployment

```bash
gcloud config set project juno-medical-clarity
gcloud builds submit --project juno-medical-clarity --tag us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend
gcloud run deploy simplify-backend \
  --image us-central1-docker.pkg.dev/juno-medical-clarity/juno/simplify-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-env-vars GCP_PROJECT_ID=juno-medical-clarity,GCP_BUCKET_NAME=juno-medical-clarity-backend,GCP_LOCATION=us-central1,VERTEX_AI_MODEL=gemini-3.5-flash,SIMPLIFY_DEFAULT_VERSION=v1-2,FIRESTORE_DATABASE_ID='(default)'
```

For GitHub Actions, store a deploy service account JSON key in the `GCP_SA_KEY` repository secret. Store the Firebase Admin SDK JSON in Secret Manager as `firebase-service-account` so Cloud Run can inject `FIREBASE_SERVICE_ACCOUNT_JSON`.

## Linting

The backend uses [ruff](https://docs.astral.sh/ruff/) for static analysis (pyflakes F rules).

Run locally from `backend/`:

```bash
pip install -r requirements-dev.txt
ruff check . --config pyproject.toml
```

A pre-commit hook (`.pre-commit-config.yaml` at repo root) runs `ruff check` automatically on staged `.py` files before every commit. Install it once with:

```bash
pip install pre-commit
pre-commit install
```

To add stricter rules (E, I, UP) in the future, update the `select` list in `[tool.ruff.lint]` inside `pyproject.toml`.
