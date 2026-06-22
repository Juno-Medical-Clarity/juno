# Local Development

This project has two runnable parts:

- `backend/`: Flask API, default local URL `http://localhost:8080`
- `frontend/`: React + Vite app, default local URL `http://localhost:5173`

Use the deployment guide only for deploying. This file is for running the app from a local checkout.

## Prerequisites

- Python 3.11 is recommended. The backend container uses Python 3.11.
- Node.js compatible with Vite 7. The installed Vite package requires Node `^20.19.0` or `>=22.12.0`.
- npm.
- Firebase project access and an existing Firebase Auth user. The app uses email/password login and does not expose self-registration.
- Backend credentials for Firebase Admin, Firestore, GCS, and model access.

For model access, the backend supports `GEMINI_API_KEY` for the Gemini API. If that is not set, it falls back to Vertex AI configuration.

## Environment Files

Create local env files from the templates:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

Do not commit filled `.env` files or service account JSON files.

### Backend Env

Fill `backend/.env` with the values needed by your local backend:

```text
FIREBASE_SERVICE_ACCOUNT_PATH=path/to/serviceAccountKey.json
GCP_PROJECT_ID=juno-medical-clarity
GCP_BUCKET_NAME=juno-medical-clarity-backend
GCP_LOCATION=us-central1
FIRESTORE_DATABASE_ID=(default)
VERTEX_AI_MODEL=gemini-3.5-flash
GEMINI_API_KEY=
SIMPLIFY_DEFAULT_VERSION=v1-2
```

Notes:

- `FIREBASE_SERVICE_ACCOUNT_PATH` should point to a Firebase Admin SDK service account JSON file on your machine.
- Instead of a service account file, local Application Default Credentials can work for some Google Cloud calls, but Firebase Admin still needs credentials that can initialize the app.
- Set `GEMINI_API_KEY` if you want the simpler Gemini API path for supported code paths. Otherwise make sure Vertex AI credentials and project settings are available.
- `SIMPLIFY_DEFAULT_VERSION` should usually match the frontend `VITE_DEFAULT_VERSION`.

### Frontend Env

Fill `frontend/.env.local` with Firebase web app config and a backend URL:

```text
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_API_PROCESSING_URL=http://localhost:8080
VITE_DEFAULT_VERSION=v1-2
```

The frontend reads `VITE_API_PROCESSING_URL` directly when making API calls.

## Run The Full App Locally

Use two terminals.

Terminal 1, backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The backend listens on `http://localhost:8080` by default. Confirm it is up:

```bash
curl http://localhost:8080/health
```

Terminal 2, frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Sign in with a Firebase Auth email/password account from the configured Firebase project. The `/simplify` API routes used by the frontend require the frontend to send a Firebase ID token.

## Run Only The Frontend Against Production Backend

Use this when you want local frontend iteration while calling the deployed Cloud Run backend.

1. Make sure `frontend/.env.local` contains the production Firebase web app config.
2. Set `VITE_API_PROCESSING_URL` in `frontend/.env.local` to the production backend Cloud Run URL.
3. Run the Vite dev server.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The production backend URL is not committed in the env examples. Get it from the project owner, the GitHub secret named `VITE_API_PROCESSING_URL`, or Cloud Run. The deployment guide documents the Cloud Run lookup command, but local development only needs the final HTTPS service URL.

Keep `VITE_API_PROCESSING_URL` as the base URL only, for example:

```text
VITE_API_PROCESSING_URL=https://your-cloud-run-service-url
```

Do not append `/simplify`; the frontend appends API paths itself.

## Useful Commands

Frontend:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Backend tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

## Troubleshooting

- `http://localhost:8080/health` fails: the backend is not running, crashed during Firebase initialization, or is using another port.
- Backend port conflict: run `PORT=8081 python app.py` and update `frontend/.env.local` to `VITE_API_PROCESSING_URL=http://localhost:8081`.
- Frontend port conflict: run `npm run dev -- --port 5174` and open the URL Vite prints.
- Requests go to `undefined/simplify`: `VITE_API_PROCESSING_URL` is missing from `frontend/.env.local`. Restart Vite after changing env vars.
- `401` or sign-in related errors: verify the frontend Firebase config points at the same Firebase project that the backend verifies with Firebase Admin.
- Production-backend mode returns auth or permission errors: confirm your Firebase user exists in the production Firebase project and has access to any required Firestore/GCS data.
- CORS errors are usually not from local Flask config because the backend enables CORS for all routes. Check that `VITE_API_PROCESSING_URL` is the backend base URL and that the backend is reachable.
- The Vite config includes a `/simplify` proxy to `localhost:8082`, but the current frontend code uses `VITE_API_PROCESSING_URL` for API calls. Set the env var rather than relying on the proxy.
