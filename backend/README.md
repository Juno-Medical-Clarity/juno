# Juno Backend

Python Flask API for the Simplify pipeline. Deployed on Google Cloud Run.

## API Routes

All routes except `/health` require `Authorization: Bearer <firebase_id_token>`.

### Pipeline

| Method | Path | Description |
|---|---|---|
| `POST` | `/simplify/v1-2` | Run V1.2 pipeline (SSE stream) |
| `POST` | `/simplify/v1-1` | Run V1.1 pipeline (SSE stream) |
| `POST` | `/simplify/v1` | Run V1 pipeline (SSE stream) |

**Request (v1-2):** `multipart/form-data`
- `files` — one or more PDF/TXT/DOCX files (max 10 files, 25 MB aggregate)
- `text` — plain text input (alternative to files)

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
3. Create `routes/simplify_v<X>.py` with one SSE route
4. Register the blueprint in `routes/__init__.py`

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
gcloud builds submit --tag gcr.io/<GCP_PROJECT_ID>/simplify-backend
gcloud run deploy simplify-backend \
  --image gcr.io/<GCP_PROJECT_ID>/simplify-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-env-vars GCP_PROJECT_ID=<GCP_PROJECT_ID>,GCP_BUCKET_NAME=<GCP_BUCKET_NAME>,VERTEX_AI_MODEL=gemini-2.0-flash,SIMPLIFY_DEFAULT_VERSION=v1-2
```

Set the secret `FIREBASE_SERVICE_ACCOUNT_PATH` via Cloud Run secret manager or mount the JSON as a volume.
