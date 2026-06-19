# Logging & Metrics Analysis — Juno

**Date:** June 2026  
**Stack:** React 19 (Firebase Hosting) · Flask (Cloud Run) · Firestore · Google Cloud Storage  
**GCP project:** `juno-medical-clarity` · **Firebase project:** `juno-medical-clarity` · **Region:** `us-central1`

---

## 1. What We Already Have

### 1.1 Structured JSON Logging (`logging_config.py`)

The formatter outputs single-line JSON to stdout on every log call. On Cloud Run, stdout is automatically ingested by Cloud Logging — no agent, no sidecar, no configuration needed.

**Fields emitted today on every log line:**

| Field | Source | Notes |
|-------|--------|-------|
| `severity` | Python log level | Maps to Cloud Logging severity (INFO, WARNING, ERROR) |
| `message` | Log call message | Free text |
| `logger` | Python module name | e.g. `routes.simplify_v1_2` |
| `session_id` | Flask `g.session_id` via `SessionIdFilter` | Auto-injected; no manual `extra=` needed in route code |
| `trace_id` | OTel span context | 32-char hex; links to Cloud Trace |
| `span_id` | OTel span context | 16-char hex |
| `logging.googleapis.com/trace` | Derived from trace_id + project | Enables Cloud Logging ↔ Cloud Trace correlation in Console |
| `logging.googleapis.com/spanId` | Same | Same |
| `exception` | Python exc_info | Full traceback, only on errors |

**What the `SessionIdFilter` does:** It hooks into the Python logging pipeline as a `Filter`. Before every log record is formatted, it reads `flask.g.session_id` (set by the `before_request` middleware in `app.py`) and stamps it onto the record. This means any `logger.info("...")` call anywhere in the request lifecycle automatically carries `session_id` without the developer passing `extra={}`.

**What's missing from today's log fields:**
- `user_id` (Firebase UID) — the route knows it (`@verify_firebase_token` passes it in), but it's not on `flask.g` and not logged
- `duration_ms` — no per-step or per-request timing is captured
- `step_name` / `step_number` — pipeline steps emit SSE progress events but don't emit structured log entries with step context
- `version` — the API version handling the request (v1-2 vs. v1-1 vs. legacy)
- `input_chars` / `source_kind` — the resolved input size and type (upload / text / doc_id) are not logged
- `status` — whether the step succeeded or failed is only implicit in log level; no explicit `status: "ok" | "error"` field
- `http.status_code` — Flask auto-instrumentation adds this to OTel spans, but it's not in log lines
- `saved_id` — the Firestore document ID created at the end of a successful request is not logged

### 1.2 OpenTelemetry + Cloud Trace (`telemetry.py`)

`FlaskInstrumentor` creates one root span per HTTP request. `RequestsInstrumentor` creates child spans for any outgoing HTTP call made via the `requests` library. The `CloudTraceSpanExporter` (in production) ships spans to Cloud Trace.

**What Cloud Trace gives you today:**
- One trace per request, with `session.id` and `http.route` as span attributes (set in `extract_session_id`)
- End-to-end request latency visible in the Cloud Trace waterfall
- Outgoing HTTP calls (e.g. calls to Gemini/Vertex AI) appear as child spans automatically

**What Cloud Trace is missing:**
- No manual child spans for individual pipeline steps (term detection, simplify, clarify, structure, GCS upload, Firestore save). The entire pipeline appears as one undifferentiated root span — you can't see which step took how long.
- The `service.version` is hardcoded as `"1.1.0"` in `telemetry.py` and is not pulled from an env var, so version comparisons across deploys will always show the same version.

### 1.3 Session ID Correlation — How It Works Today

```
Client sends:  POST /simplify/v1-2
               Header: X-Session-Id: <uuid>

app.py before_request:
  1. Checks request.view_args for appointment_id → not present for /simplify routes
  2. Reads X-Session-Id header → sets g.session_id = <uuid>
  3. Attaches session.id and http.route to the current OTel span

logging_config.py SessionIdFilter:
  → Every log.info/warning/error call in that request automatically includes
    "session_id": "<uuid>" in the JSON payload

app.py after_request:
  → Echoes X-Session-Id: <uuid> back to the client in the response header
```

For appointment routes (e.g. `POST /appointments/<id>/process`), the `appointment_id` from the URL path is used as `session_id`, which naturally groups all log lines and spans for a single appointment together — even across multiple HTTP requests.

For the simplify routes, the client must send (or receive and re-use) the `X-Session-Id` header. Today, if the client doesn't send the header, a new UUID is generated per request — meaning there's no cross-request continuity for the same user session.

---

## 2. Recommended End-to-End Tracing Approach

### 2.1 The Mental Model (vs. Kusto at Work)

At work, you log every request end-to-end with a single correlation ID — you can run a query like `| where correlationId == "abc-123"` and see every step in order, with timing. You can also query `| where status == "error" | summarize count() by step_name` to get error rates per step.

**Cloud Logging gives you exactly this**, via `jsonPayload.session_id`. The query syntax is different (Log Explorer's filtering language instead of KQL) but the mental model is identical:

```
# "Show me everything for session X"
jsonPayload.session_id="abc-1234-5678"

# "Show me all ERROR logs in the last hour, grouped by step"
severity=ERROR
jsonPayload.step_name != ""

# "Show me all requests that failed at the structuring step"
jsonPayload.step_name="structure_appointment_note"
jsonPayload.status="error"
```

The key difference from Kusto: Cloud Logging is optimized for filtering and tail-following, not for GROUP BY aggregations over large time windows. For aggregations and charting, you need Cloud Monitoring metrics (log-based or built-in) or BigQuery export — covered in section 3.

### 2.2 What to Log at Each Step

The goal is: every meaningful event in the request lifecycle emits one structured log line with a consistent set of fields. Then any single request is fully reconstructable from Cloud Logging by filtering on `session_id`.

**Standard fields to add to every log line (via `flask.g`):**

```python
g.session_id   # already there
g.user_id      # add this — set after @verify_firebase_token runs
g.api_version  # add this — e.g. "v1-2", derived from the route
```

**Per-event fields to include as `extra={}` on each log call:**

| Event | Fields to log |
|-------|--------------|
| Request received | `step_name="request_start"`, `source_kind`, `input_chars`, `http_method`, `http_path` |
| Each pipeline step start | `step_name`, `step_number`, `status="start"` |
| Each pipeline step end | `step_name`, `step_number`, `status="ok"`, `duration_ms` |
| Each pipeline step error | `step_name`, `step_number`, `status="error"`, `error_type`, `error_message` |
| GCS upload | `step_name="gcs_upload"`, `status`, `duration_ms`, `blob_name` |
| Firestore save | `step_name="firestore_save"`, `status`, `duration_ms`, `saved_id` |
| Response sent | `step_name="request_end"`, `status`, `total_duration_ms`, `http_status_code` |

This gives you a log stream that reads like a timeline:
```json
{"session_id":"abc","user_id":"uid123","step_name":"request_start","source_kind":"upload","input_chars":4200}
{"session_id":"abc","user_id":"uid123","step_name":"term_detection","step_number":2,"status":"ok","duration_ms":23}
{"session_id":"abc","user_id":"uid123","step_name":"simplify_language","step_number":3,"status":"ok","duration_ms":1840}
{"session_id":"abc","user_id":"uid123","step_name":"firestore_save","status":"ok","duration_ms":112,"saved_id":"xyz"}
{"session_id":"abc","user_id":"uid123","step_name":"request_end","status":"ok","total_duration_ms":2201}
```

### 2.3 Manual OTel Spans for Pipeline Steps

Beyond logging, wrapping each pipeline step in a child OTel span gives you a flame-graph view in Cloud Trace showing exactly where time was spent. This is the closest equivalent to distributed tracing in your work environment.

```python
# In _generate_stream(), around each step:
from telemetry import get_tracer
tracer = get_tracer()

with tracer.start_as_current_span("simplify_language") as span:
    span.set_attribute("step.number", 3)
    span.set_attribute("session.id", g.session_id)
    simplified = pipeline.simplify_language_with_term_plan(...)
```

With this in place, Cloud Trace will show:
```
[root: POST /simplify/v1-2]  ←— 2.2s total
  [term_detection]            ←— 23ms
  [simplify_language]         ←— 1.84s  ← obvious bottleneck
  [clarify_and_action]        ←— 190ms
  [structure_appointment_note]←— 80ms
  [gcs_upload]                ←— 55ms
  [firestore_save]            ←— 112ms
```

### 2.4 Cloud Logging Query Syntax (Log Explorer)

Log Explorer URL: `https://console.cloud.google.com/logs/query?project=juno-medical-clarity`

**Show all logs for a specific session:**
```
resource.type="cloud_run_revision"
jsonPayload.session_id="<your-session-id-here>"
```

**Show all failed requests in the last hour:**
```
resource.type="cloud_run_revision"
severity=ERROR
timestamp>="2026-06-15T00:00:00Z"
```

**Show all errors at the simplify step:**
```
resource.type="cloud_run_revision"
jsonPayload.step_name="simplify_language"
jsonPayload.status="error"
```

**Show requests by a specific user:**
```
resource.type="cloud_run_revision"
jsonPayload.user_id="<firebase-uid>"
```

**Show slow requests (once duration_ms is logged):**
```
resource.type="cloud_run_revision"
jsonPayload.step_name="request_end"
jsonPayload.total_duration_ms>5000
```

**Tip:** Cloud Logging supports saving queries and linking directly to them — you can build a small library of bookmarks that replicate your common Kusto queries.

---

## 3. Metrics Options — Evaluated

### 3.1 Cloud Monitoring (Built-in GCP)

**What it gives you:**
- Cloud Run built-in metrics out of the box: `request_count`, `request_latencies`, `container/cpu/utilization`, `container/memory/utilization` — no setup needed
- Log-based metrics: you define a filter (e.g. `jsonPayload.step_name="request_end"`) and Cloud Monitoring extracts a numeric field (e.g. `total_duration_ms`) as a distribution metric — then you can chart percentiles (p50/p95/p99) over time
- Uptime checks: ping your `/health` endpoint every minute; alert if it fails
- Alerting policies: alert on error rate > 5%, latency p95 > 10s, etc.

**Cost:** Included in Cloud Run's free tier for built-in metrics. Log-based metrics: free up to 10 custom metrics; $0.01/metric/month beyond that. Alerting: free for basic checks.

**Ease of setup:** Very easy. Cloud Run metrics appear automatically in the GCP Console under Cloud Run → Metrics. Log-based metrics require a one-time configuration in Console (point-and-click, no code). Dashboards are built with drag-and-drop in Cloud Monitoring → Dashboards.

**Query/charting capability:** Good for operational dashboards (latency histograms, error rates, request counts by revision). Not suited for ad-hoc exploration or joining across dimensions. You cannot write SQL-style queries.

**Recommendation:** Use this as your primary metrics layer. It requires zero additional infrastructure and gives you production-grade charts within an hour of setup. The built-in Cloud Run metrics alone are enough for the early stage.

---

### 3.2 Cloud Trace (Already Partially Set Up)

**What it gives you:**
- Per-request latency waterfall (once you add manual child spans — see §2.3)
- Latency distribution charts: p50/p95/p99 across all requests or filtered by span name
- "Trace list" view: every request in a time window, sortable by latency — lets you click into the slowest ones
- Automatic sampling (100% at low volume, reduces at high volume)

**Cost:** First 2.5 million spans/month free; $0.20/million spans after that. At 100 requests/day with ~8 spans per request (one root + 6 pipeline steps + GCS + Firestore), you're at ~24,000 spans/month — well within the free tier.

**Ease of setup:** Already initialized. Adding child spans requires small code changes in `simplify_v1_2.py` and equivalent route files — roughly 2–3 lines per step.

**Query/charting capability:** Good for latency analysis by span. Limited — you cannot filter by custom attributes (like `user_id`) in the Cloud Trace UI directly. The real value is the waterfall view and the latency distribution per endpoint.

**Recommendation:** Add manual child spans for the 5 pipeline steps plus GCS/Firestore calls. This gives you the flame-graph view that's most useful for diagnosing slowdowns. This is complementary to logging, not a replacement.

---

### 3.3 Firebase Performance Monitoring

**What it gives you:**
- Frontend-only SDK: measures page load time, time-to-first-contentful-paint, network request latency from the browser's perspective
- "Custom traces": you can wrap a frontend function call (e.g. the SSE stream consumption) and measure wall-clock time as seen by the user
- Automatic URL-based breakdown of network requests

**Cost:** Free, included with Firebase.

**Ease of setup:** Add the Firebase Performance SDK to the React app (`firebase/performance`), call `getPerformance(app)` once. Custom traces require 2–3 lines of code per trace.

**Query/charting capability:** Limited. The Firebase Console shows aggregated charts (p75/p90 latency per trace, over time). You cannot query raw data or write custom filters. No export to BigQuery in the free plan.

**Recommendation:** Useful as a complementary signal for "what does the user experience look like?" — specifically for measuring how long the full SSE stream takes from the user's perspective. Not a replacement for backend metrics. Low priority for now; add once core backend observability is solid.

---

### 3.4 Grafana + Cloud Monitoring (or Prometheus)

**Option A — Grafana Cloud (SaaS, free tier):**
- Connect Grafana Cloud to Cloud Monitoring as a data source (one-time OAuth setup)
- Build dashboards in Grafana's UI using Cloud Monitoring metrics as the data source
- Grafana's query UI is significantly better than Cloud Monitoring's built-in dashboard editor
- Free tier: 10,000 series, 14-day retention, 3 users

**Option B — Self-hosted Grafana + Prometheus on GCE/Cloud Run:**
- Run Prometheus scraping a `/metrics` endpoint on the Flask app (requires adding `prometheus_flask_exporter`)
- Run Grafana as a separate Cloud Run service or GCE VM
- Full control, unlimited retention, no SaaS dependency
- Adds ~$10–30/month for the VM/container, plus operational overhead

**Cost:**
- Grafana Cloud free tier: $0 (within limits)
- Self-hosted: $10–30/month infra + setup time

**Ease of setup:** Grafana Cloud is easy — 30 minutes to connect Cloud Monitoring and build a dashboard. Self-hosted Prometheus requires instrumentation code changes, a scrape config, and infrastructure.

**Query/charting capability:** Best charting experience of all options. PromQL (for Prometheus) or MQL (for Cloud Monitoring in Grafana) are more expressive than Cloud Monitoring's built-in chart editor. Grafana's visualization library is excellent.

**Recommendation:** Grafana Cloud connecting to Cloud Monitoring is worth considering if you want better dashboard aesthetics and flexibility than the GCP Console provides — and the free tier is enough for Juno's current volume. However, it's a "nice to have" — Cloud Monitoring's built-in dashboards are functional and you're not blocked without it. Do not set up self-hosted Prometheus; the operational overhead is not worth it at this stage.

---

### 3.5 BigQuery (Cloud Logging → BigQuery Export)

**What it gives you:**
- Export all Cloud Logging entries to a BigQuery dataset (near real-time, ~1 minute lag)
- Query log data with standard SQL — the closest equivalent to Kusto
- Example query:
  ```sql
  SELECT
    JSON_VALUE(json_payload, '$.session_id') AS session_id,
    JSON_VALUE(json_payload, '$.step_name') AS step_name,
    CAST(JSON_VALUE(json_payload, '$.duration_ms') AS INT64) AS duration_ms,
    timestamp
  FROM `juno-medical-clarity.juno_logs.run_googleapis_com_stderr_*`
  WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND JSON_VALUE(json_payload, '$.status') = 'error'
  ORDER BY timestamp DESC
  ```
- Use BigQuery's `ARRAY_AGG`, `AVG`, percentile functions — directly analogous to Kusto aggregation operators
- Connect to Looker Studio (free) or Grafana for charts over the BigQuery data

**Cost:**
- Log export: free (log sink creation is free)
- BigQuery storage: first 10 GB/month free; $0.02/GB/month after that
- BigQuery queries: first 1 TB/month free; $5/TB after that
- At 100 requests/day with ~10 log lines per request at ~500 bytes each: ~0.5 MB/day = ~15 MB/month → essentially free
- At 10,000 requests/day (future): ~1.5 GB/month → still under free tier

**Ease of setup:**
- Go to Cloud Logging → Log Router → Create Sink → select BigQuery as destination
- Choose or create a dataset (e.g. `juno_logs`)
- Takes 5 minutes; logs start flowing immediately
- No code changes required

**Query/charting capability:** Excellent. This is the closest thing to your Kusto workflow — full SQL, JOINs, window functions, aggregations. You can query `jsonPayload.session_id`, `jsonPayload.step_name`, `jsonPayload.duration_ms` directly using `JSON_VALUE()`. The schema auto-partitions by date, so queries over a specific day are fast and cheap.

**Recommendation:** Set this up. It's 5 minutes of configuration, essentially free at current volume, and gives you the full SQL-on-logs capability you're used to from Kusto. This is the "analytics layer" on top of Cloud Logging — not a replacement, but the natural complement when you want to ask "how many requests failed at step 3 in the last 7 days across all users?"

---

## 4. Cost Estimate

All estimates assume 100 requests/day with verbose structured logging (~15 log lines per request at ~800 bytes each = ~1.2 MB/day = ~36 MB/month).

| Service | Usage | Cost |
|---------|-------|------|
| Cloud Logging ingestion | 36 MB/month | **Free** (first 50 GB/month free) |
| Cloud Logging storage | 36 MB/month | **Free** (first 30 days free; _Default bucket) |
| Cloud Trace | ~24,000 spans/month (8 spans × 100 req/day × 30 days) | **Free** (first 2.5M spans/month free) |
| Cloud Run built-in metrics | Included | **Free** |
| Log-based metrics | ≤10 custom metrics | **Free** |
| BigQuery storage | ~36 MB/month | **Free** (first 10 GB free) |
| BigQuery queries | < 1 MB/query on 36 MB dataset | **Free** (first 1 TB queries/month free) |
| Grafana Cloud | Connect to Cloud Monitoring | **Free** (within free tier) |
| Firebase Performance | Frontend SDK | **Free** |

**Total monthly cost at 100 req/day: $0**

Even at 10,000 requests/day (100x current scale):
- Cloud Logging: ~3.6 GB/month → still free (under 50 GB)
- Cloud Trace: 2.4M spans/month → ~$0 (under 2.5M free limit, may just exceed)
- BigQuery: ~3.6 GB storage → still free

**You will not pay for observability until you're at meaningful scale (>100k requests/day).**

---

## 5. Recommended Approach

### Now (implement this week)

**Use Cloud Logging + Cloud Trace + BigQuery export.**

This is the right stack for Juno's current stage:
1. **Cloud Logging** is already working. Add `user_id`, `step_name`, `duration_ms`, `status` fields (details in §6) and every request becomes fully traceable from a single `session_id` filter.
2. **Cloud Trace** is already initialized. Add manual child spans for each pipeline step (5 lines of code per step). The flame-graph view in the GCP Console will show you exactly where time is going.
3. **BigQuery export** (5-minute setup, no code) gives you the SQL-on-logs capability closest to your Kusto workflow. You can query across all requests, all users, all time windows — exactly like at work.
4. **Cloud Monitoring** log-based metrics (30-minute setup, no code): create two metrics — `simplify_request_duration` (extract `total_duration_ms` from `step_name="request_end"` log lines) and `simplify_error_count` (count logs where `status="error"`). Build a 3-panel dashboard: p50/p95 latency, error rate, request count. This is your always-on monitoring view.

**Do not** set up self-hosted Prometheus, Grafana (self-hosted), or Firebase Performance yet. They add complexity without proportional benefit at this volume.

### Later (when volume grows or you need more)

- **Grafana Cloud** (free): connect to Cloud Monitoring for nicer dashboards if the GCP Console's dashboard editor starts to feel limiting.
- **Firebase Performance Monitoring**: add when you want to understand frontend-perceived latency (separate from backend processing time).
- **Alerting policies**: once you have 1–2 weeks of baseline data, set up Cloud Monitoring alert policies (p95 latency > 15s, error rate > 10%) with email/PagerDuty notifications.
- **Log-based metrics on `version`**: once you're running multiple pipeline versions in parallel, add a `version` field to logs and segment your metrics by it — analogous to your work dashboards that break down by version.

---

## 6. What to Implement

These are concrete code changes needed to reach the recommended state. No implementation — just what needs to change and where.

### 6.1 Add `user_id` and `api_version` to Flask `g` context

**File:** `/root/projects/juno/backend/utils/auth.py`  
The `@verify_firebase_token` decorator already decodes the Firebase token and passes `user_id` to the route function. It should also set `flask.g.user_id = user_id` so the logging filter can pick it up automatically.

**File:** `/root/projects/juno/backend/app.py` — `extract_session_id()`  
After setting `g.session_id`, also set `g.api_version` by inspecting the request URL prefix (`/simplify/v1-2` → `"v1-2"`, `/simplify/v1-1` → `"v1-1"`, etc.). Alternatively, blueprints can set this themselves.

### 6.2 Extend `SessionIdFilter` to inject `user_id` and `api_version`

**File:** `/root/projects/juno/backend/logging_config.py` — `SessionIdFilter.filter()`  
Currently only reads `g.session_id`. Extend to also read `g.user_id` and `g.api_version` and stamp them onto the log record. Then update `StructuredJsonFormatter.format()` to include these in the JSON output if present.

### 6.3 Add per-step structured log calls in the pipeline route

**File:** `/root/projects/juno/backend/routes/simplify_v1_2.py` — `_generate_stream()`  
Before and after each pipeline step, add `logger.info(...)` calls with `extra={"step_name": ..., "step_number": ..., "status": ..., "duration_ms": ...}`. Use `time.monotonic()` to measure duration. This is approximately 3 lines per step × 5 steps = ~15 lines of additions.

Also add a request-start log (with `source_kind`, `input_chars`) and a request-end log (with `total_duration_ms`, `http_status`) at the top and bottom of the generator.

Log the `saved_id` on success:
```python
logger.info("output saved", extra={"step_name": "firestore_save", "status": "ok", "saved_id": saved_id, "duration_ms": ...})
```

### 6.4 Add manual OTel child spans for pipeline steps

**File:** `/root/projects/juno/backend/routes/simplify_v1_2.py` — `_generate_stream()`  
Wrap each pipeline step call in `with tracer.start_as_current_span("step_name") as span:`. Import `get_tracer` from `telemetry`. Set `span.set_attribute("step.number", N)` and `span.set_attribute("session.id", g.session_id)` on each span.

### 6.5 Fix hardcoded service version in telemetry

**File:** `/root/projects/juno/backend/telemetry.py` — `init_telemetry()`  
Change `"service.version": "1.1.0"` to `"service.version": os.getenv("SERVICE_VERSION", "unknown")`. Add `SERVICE_VERSION` as an environment variable in the Cloud Run deploy config (set it to the git SHA or semver on each deploy). This makes version-segmented latency charts possible in Cloud Trace.

### 6.6 Apply the same step-logging pattern to other route files

**Files:** `/root/projects/juno/backend/routes/simplify.py`, `simplify_v1_1.py`, `saved_outputs.py`  
Apply the same step-name + duration_ms logging pattern as §6.3. The exact steps differ per route, but the pattern is the same.

### 6.7 Set up BigQuery log export (no code — GCP Console)

1. Go to Cloud Logging → Log Router → Create Sink
2. Name: `juno-logs-bq`
3. Destination: BigQuery dataset — create `juno_logs` in `us-central1`
4. Filter: `resource.type="cloud_run_revision"` (optional: add `project_id="juno-medical-clarity"`)
5. Enable partitioned tables: yes (by `_PARTITIONTIME`)
6. Click Create

Logs will appear in BigQuery within ~1 minute. Query via BigQuery Console or `bq` CLI.

### 6.8 Create Cloud Monitoring log-based metrics (no code — GCP Console)

Create two log-based metrics in Cloud Monitoring → Metrics → Log-based metrics → Create:

**Metric 1: `simplify_request_duration_ms`**
- Type: Distribution
- Filter: `resource.type="cloud_run_revision" jsonPayload.step_name="request_end"`
- Value: `jsonPayload.total_duration_ms`

**Metric 2: `simplify_step_error_count`**
- Type: Counter
- Filter: `resource.type="cloud_run_revision" jsonPayload.status="error"`
- Label: `step_name` → extracted from `jsonPayload.step_name`

Then build a dashboard with:
- Panel 1: `simplify_request_duration_ms` p50/p95/p99 over time
- Panel 2: `simplify_step_error_count` by `step_name` over time  
- Panel 3: Cloud Run built-in `request_count` by revision (shows traffic per version)

---

## Summary Decision Table

| Need | Tool | Cost | Effort |
|------|------|------|--------|
| End-to-end request tracing by session_id | Cloud Logging (already live) + code changes (§6.1–6.3) | Free | 2–3 hours |
| Flame-graph latency breakdown per pipeline step | Cloud Trace manual spans (§6.4) | Free | 1 hour |
| SQL-style ad-hoc queries on logs (like Kusto) | BigQuery export (§6.7) | Free | 5 minutes |
| Always-on latency/error charts | Cloud Monitoring log-based metrics + dashboard (§6.8) | Free | 30 minutes |
| Better dashboard UI than GCP Console | Grafana Cloud | Free | 30 minutes | 
| Frontend-perceived latency | Firebase Performance | Free | 1 hour |
| Per-version traffic/latency breakdown | `SERVICE_VERSION` env var in Cloud Run + Cloud Run revision metrics | Free | 15 minutes |
