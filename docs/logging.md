# Logging

This runbook covers how Juno logging is wired, how to add useful log lines, and
how to find logs in Google Cloud.

## What Gets Logged

Backend logs are the source of truth for production troubleshooting.

- Local backend logs are printed to the terminal in a readable text format.
- Cloud Run backend logs are written to stdout as JSON and ingested by Cloud
  Logging.
- Backend request logs include an `X-Session-Id` correlation ID. The backend
  accepts this header from the client or generates one, stores it on `flask.g`,
  and echoes it back on the response.
- OpenTelemetry traces are initialized at backend startup. In Cloud Run, traces
  are exported to Cloud Trace when `GCP_PROJECT_ID` is set.
- Frontend logs currently stay in the browser console. They are structured for a
  future ingestion endpoint, but they are not sent to Cloud Logging today.

Key files:

- `backend/app.py` initializes logging, tracing, request start/end logs, session
  IDs, and request latency metrics.
- `backend/logging_config.py` controls local text output vs Cloud Run JSON
  output.
- `backend/telemetry.py` initializes OpenTelemetry and Cloud Trace export.
- `backend/utils/juno_logger.py` provides the backend application logging helper.
- `backend/utils/juno_metrics.py` records log-based metric events.
- `frontend/src/utils/logger.ts` provides browser-only frontend logging.
- `backend/utils/LOGGING.md` has lower-level backend helper examples and metric
  filter patterns.

## Set Up Logging Infrastructure

### Local Backend

No separate logging service is required locally.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Local output uses the development formatter because `K_SERVICE` is not set:

```text
[2026-06-19 12:00:00,000] INFO routes.simplify_v1_2 - simplify_v1_2: processing source=file (1234 chars)
```

Use `curl -i` when you need the generated session ID:

```bash
curl -i http://localhost:8080/health
```

For authenticated routes, pass a stable session ID while reproducing an issue:

```bash
curl -H "X-Session-Id: debug-2026-06-19-001" \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN" \
  "$BACKEND_URL/simplify/saved"
```

### Cloud Run

Cloud Run sets `K_SERVICE` automatically. That switches the backend formatter to
JSON logs on stdout, which Cloud Logging ingests without a separate agent.

The backend deploy workflow configures the production logging context in
`.github/workflows/deploy-backend.yml`:

```text
GCP_PROJECT_ID=juno-medical-clarity
GCP_BUCKET_NAME=juno-medical-clarity-backend
GCP_LOCATION=us-central1
VERTEX_AI_MODEL=gemini-3.5-flash
SIMPLIFY_DEFAULT_VERSION=v1-2
FIRESTORE_DATABASE_ID=(default)
GEMINI_API_KEY=<GitHub secret>
FIREBASE_SERVICE_ACCOUNT_JSON=<Secret Manager secret>
```

The Firebase Admin SDK JSON is stored in Secret Manager as
`firebase-service-account` and injected into Cloud Run as
`FIREBASE_SERVICE_ACCOUNT_JSON`.

The deploy service account is configured through the GitHub secret `GCP_SA_KEY`.
The Cloud Run runtime service account must be able to read Secret Manager,
Firestore, GCS, Vertex AI or Gemini API dependencies, and write Cloud Trace.

`backend/cloudbuild.yaml` sets:

```yaml
options:
  logging: CLOUD_LOGGING_ONLY
```

That sends Cloud Build logs to Cloud Logging instead of the default build logs
bucket. It avoids needing build-log bucket permissions just to stream build logs.

### Cloud Trace

`backend/telemetry.py` exports traces to Cloud Trace in production when both
conditions are true:

- `K_SERVICE` exists, meaning the app is running on Cloud Run.
- `GCP_PROJECT_ID` is set.

Set `SERVICE_VERSION` on Cloud Run when you want trace views grouped by deploy:

```text
SERVICE_VERSION=<git-sha>
```

The current deploy workflow does not set this variable. Without it, traces use
`service.version=unknown`.

### Log-Based Metrics

The backend records metrics as structured log events through `JunoMetrics`.
Create Cloud Monitoring log-based metrics from the filters in
`backend/utils/LOGGING.md`.

Recommended metrics:

- `simplify_request_duration_ms`: distribution from `jsonPayload.duration_ms`.
- `simplify_step_error_count`: counter grouped by error type and operation.
- `simplify_request_count`: counter grouped by pipeline version.
- `http_request`: latency for non-SSE HTTP responses from `backend/app.py`.

## Use Logging In Code

### Backend Request And Pipeline Logs

Use `JunoLogger` for request, pipeline, and user-impacting workflow logs.

```python
from utils.juno_logger import JunoLogger, monotonic_ms

juno_logger = JunoLogger(api_version="v1-2")

juno_logger.log_step("simplify_language", "start")
step_start_ms = monotonic_ms()
try:
    result = pipeline.simplify_language(text)
except Exception as exc:
    juno_logger.log_step(
        "simplify_language",
        "error",
        extra={"error": str(exc)},
    )
    raise

juno_logger.log_step(
    "simplify_language",
    "done",
    duration_ms=monotonic_ms() - step_start_ms,
)
```

Use stable `snake_case` values for `step_name` and keep `extra` small. Do not
log raw provider notes, patient text, Firebase tokens, service account JSON,
signed URLs, or API keys.

Expected backend log context includes:

| Field | Meaning |
| --- | --- |
| `session_id` | Request/session correlation ID from `X-Session-Id` or backend fallback. |
| `user_id` | Firebase UID set by auth middleware when present. |
| `api_version` | Pipeline version passed to `JunoLogger`. |
| `step_name` | Stable workflow step, such as `simplify_language`. |
| `status` | Step status, usually `start`, `done`, `error`, or request `ok`. |
| `duration_ms` | Step duration for pipeline steps. |
| `total_duration_ms` | End-to-end request duration from `after_request`. |
| `trace_id` / `span_id` | OpenTelemetry identifiers for Cloud Trace correlation. |

Current caveat: `JunoLogger` and `JunoMetrics` attach these fields through the
standard Python `extra` mechanism. If a field is missing in Cloud Logging,
confirm the deployed `StructuredJsonFormatter` in `backend/logging_config.py`
serializes that field into `jsonPayload`.

For ordinary module diagnostics where request context is less important, the
standard library logger is acceptable:

```python
import logging

logger = logging.getLogger(__name__)
logger.warning("saved_outputs: missing input_pdf_gcs for doc_id=%s", doc_id)
```

Prefer `logger.exception(...)` inside `except` blocks so the traceback is
available in logs.

### Backend Metrics

Use `JunoMetrics` when the value should become a chart or alert.

```python
from utils.juno_metrics import JunoMetrics

metrics = JunoMetrics()
metrics.record_counter("simplify_request", labels={"version": "v1-2"})
metrics.record_latency(
    "simplify_pipeline",
    total_ms,
    labels={"version": "v1-2", "input_type": source_kind},
)
metrics.record_error(
    type(exc).__name__,
    "simplify_language",
    labels={"version": "v1-2"},
)
```

Use logs for diagnosis and metrics for aggregation. If you need both, emit both.

### Frontend Logs

Use `frontend/src/utils/logger.ts` for browser diagnostics and UX events:

```ts
import { logger } from '../utils/logger';

logger.logPageView('SimplifyPage');
logger.logUserAction('submit_text', { inputLength: text.length });
logger.error('simplify_request_failed', { status });
```

Set the backend session ID after reading the `X-Session-Id` response header so
browser logs can be matched manually to backend logs:

```ts
const sessionId = response.headers.get('X-Session-Id');
if (sessionId) {
  logger.setSessionId(sessionId);
}
```

Production frontend logs are still browser-console logs. To troubleshoot a user
issue in Cloud Logging, use the backend `session_id`, `user_id`, request path,
and timestamp.

## Look Up Logs

Set shell defaults:

```bash
PROJECT_ID=juno-medical-clarity
REGION=us-central1
BACKEND_SERVICE=simplify-backend
```

Find the deployed backend URL:

```bash
gcloud run services describe "$BACKEND_SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(status.url)"
```

Read recent Cloud Run logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   resource.labels.service_name="simplify-backend"' \
  --project "$PROJECT_ID" \
  --limit 50 \
  --format json
```

Follow recent errors:

```bash
gcloud logging tail \
  'resource.type="cloud_run_revision"
   resource.labels.service_name="simplify-backend"
   severity>=ERROR' \
  --project "$PROJECT_ID"
```

### Cloud Logging Query Recipes

Open Logs Explorer:

```text
https://console.cloud.google.com/logs/query?project=juno-medical-clarity
```

All backend logs:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
```

Recent errors:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
severity>=ERROR
```

One session:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.session_id="<session-id>"
```

One Firebase user:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.user_id="<firebase-uid>"
```

One route:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.http_path="/simplify"
```

Request completions that returned errors:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.step_name="request_end"
jsonPayload.http_status_code>=400
```

Slow requests over 10 seconds:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.step_name="request_end"
jsonPayload.total_duration_ms>10000
```

Pipeline step failures:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.message="pipeline_step"
jsonPayload.status="error"
```

Failures in one step:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.step_name="simplify_language"
jsonPayload.status="error"
```

Pipeline latency metric events:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
jsonPayload.metric=true
jsonPayload.metric_type="latency"
jsonPayload.operation="simplify_pipeline"
```

Several filters above rely on structured fields emitted through `JunoLogger` or
`JunoMetrics`. If a query returns no matches for a request you know happened,
first search by `jsonPayload.session_id` or free text, then inspect the expanded
`jsonPayload` to confirm which fields are present in the deployed revision.

Cloud Build logs:

```text
resource.type="build"
resource.labels.project_id="juno-medical-clarity"
```

Cloud Run revision deploy logs:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="simplify-backend"
protoPayload.methodName=~"google.cloud.run"
```

## Troubleshooting

- No Cloud Run logs: confirm the service is `simplify-backend`, the project is
  `juno-medical-clarity`, and the query time range includes the request.
- No structured fields in Logs Explorer: expand `jsonPayload`. If a field is not
  present, check `backend/logging_config.py` and the exact deployed revision.
- No `user_id`: the log likely happened before Firebase auth ran, on an
  unauthenticated route, or outside a request context.
- No trace link: confirm the deployed service has `GCP_PROJECT_ID` and that the
  runtime service account can write Cloud Trace data.
- No frontend logs in Cloud Logging: this is expected. Frontend logging currently
  writes only to the browser console.
