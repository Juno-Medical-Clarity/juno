# Juno — Simplify

AI-powered medical appointment note simplification. Converts clinical provider notes
(SOAP notes, appointment summaries) into plain-language summaries a patient can understand.

## What It Does

1. User uploads a PDF, TXT, or DOCX provider note (or pastes text)
2. The pipeline runs 5 stages: extract text → detect medical terms → simplify language → clarify actions → structure output
3. The result is a structured patient-friendly summary with sections (Why You Came In, What the Doctor Found, Your Medications, etc.)
4. Results are saved per user. A sidebar lists past outputs for quick access.
5. "Show Original" opens a split view: left = original PDF, right = simplified output.

## Project Structure

```
juno/
├── backend/          Python Flask API (deployed on Cloud Run)
├── frontend/         React + Vite web app (deployed on Firebase Hosting)
└── README.md
```

## Running Locally

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in values
python app.py
# Runs on http://localhost:8080
```

**Frontend:**
```bash
cd frontend
npm install
cp .env.local.example .env.local  # fill in values
npm run dev
# Runs on http://localhost:5173
```

## Deployment

See `backend/README.md` for Cloud Run deployment and `frontend/README.md` for Firebase Hosting.
See `docs/logging.md` for logging setup, developer logging conventions, and Cloud Logging queries.

## Required Environment Variables

| Variable | Where | Description |
|---|---|---|
| `GCP_PROJECT_ID` | backend | Google Cloud/Firebase project ID (`juno-medical-clarity`) |
| `GCP_BUCKET_NAME` | backend | GCS bucket for input PDFs (`juno-medical-clarity-backend`) |
| `GCP_LOCATION` | backend | GCP region (default: us-central1) |
| `VERTEX_AI_MODEL` | backend | Gemini model name |
| `FIRESTORE_DATABASE_ID` | backend | Firestore database (default: `(default)`) |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | backend | Path to service account key JSON |
| `VITE_FIREBASE_API_KEY` | frontend | Firebase web app API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | frontend | Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | frontend | Firebase project ID |
| `VITE_FIREBASE_STORAGE_BUCKET` | frontend | Firebase storage bucket |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | frontend | Firebase messaging sender ID |
| `VITE_FIREBASE_APP_ID` | frontend | Firebase app ID |
| `VITE_API_PROCESSING_URL` | frontend | Backend Cloud Run URL |
