# Juno Backend Logging & Metrics

## Standard Fields on Every Log Entry

Every structured log line emitted by `JunoLogger` includes:

| Field | Source | Notes |
|-------|--------|-------|
| `severity` | Python log level | `INFO`, `WARNING`, `ERROR` |
| `message` | Log call message | `"pipeline_step"`, `"request_start"`, etc. |
| `session_id` | `flask.g.session_id` | Set by `before_request` middleware |
| `user_id` | `flask.g.user_id` | Set by `@verify_firebase_token` |
| `api_version` | `JunoLogger(api_version=...)` | e.g. `"v1-2"` |
| `service` | `K_SERVICE` env var | `"juno-backend"` on Cloud Run |
| `environment` | `"production"` if `K_SERVICE` is set | `"development"` locally |
| `trace_id` | OTel span context | Links to Cloud Trace |
| `span_id` | OTel span context | Links to Cloud Trace |

Step-specific log entries also include: `step_name`, `status`, `duration_ms`.

---

## How to Add Logging to a New Pipeline Version

**Step 1** — Import and instantiate at the top of the route's generator function:

```python
from utils.juno_logger import JunoLogger, monotonic_ms
from utils.juno_metrics import JunoMetrics

juno_logger = JunoLogger(api_version="v1-3")
metrics = JunoMetrics()
pipeline_start = monotonic_ms()
```

**Step 2** — Wrap each pipeline step with start/done/error calls:

```python
juno_logger.log_step("my_step_name", "start")
t0 = monotonic_ms()
try:
    result = do_the_work()
except Exception as exc:
    juno_logger.log_step("my_step_name", "error", extra={"error": str(exc)})
    metrics.record_error(type(exc).__name__, "my_step_name", labels={"version": "v1-3"})
    raise
juno_logger.log_step("my_step_name", "done", duration_ms=monotonic_ms() - t0)
```

**Step 3** — Record pipeline-level metrics at the end:

```python
total_ms = monotonic_ms() - pipeline_start
metrics.record_latency("simplify_pipeline", total_ms,
                       labels={"version": "v1-3", "input_type": source_kind})
metrics.record_counter("simplify_request", labels={"version": "v1-3"})
```

That's it. No changes to `juno_logger.py` or `juno_metrics.py` are needed.

---

## Cloud Logging Queries (Log Explorer)

URL: `https://console.cloud.google.com/logs/query?project=juno-medical-clarity`

**All logs for a specific session:**
```
resource.type="cloud_run_revision"
jsonPayload.session_id="<your-session-id-here>"
```

**All logs for a specific user:**
```
resource.type="cloud_run_revision"
jsonPayload.user_id="<firebase-uid>"
```

**All ERROR logs with step context:**
```
resource.type="cloud_run_revision"
severity=ERROR
jsonPayload.step_name!=""
```

**Errors at a specific pipeline step:**
```
resource.type="cloud_run_revision"
jsonPayload.step_name="simplify_language"
jsonPayload.status="error"
```

**Slow requests (total duration over 10 seconds):**
```
resource.type="cloud_run_revision"
jsonPayload.step_name="request_end"
jsonPayload.total_duration_ms>10000
```

---

## Log-Based Metrics Filter Patterns

Use these in Cloud Monitoring → Metrics → Log-based metrics → Create.

**Match all metric entries:**
```
resource.type="cloud_run_revision"
jsonPayload.metric=true
```

**Latency metric (extract `duration_ms` as a Distribution):**
```
resource.type="cloud_run_revision"
jsonPayload.metric=true AND jsonPayload.metric_type="latency"
AND jsonPayload.operation="simplify_pipeline"
```
Value field: `jsonPayload.duration_ms`

**Error counter (count log entries, label by `error_type`):**
```
resource.type="cloud_run_revision"
jsonPayload.metric=true AND jsonPayload.metric_type="error"
```
Label extractor: `jsonPayload.error_type`, `jsonPayload.operation`

**Request counter (label by version):**
```
resource.type="cloud_run_revision"
jsonPayload.metric=true AND jsonPayload.metric_type="counter"
AND jsonPayload.metric_name="simplify_request"
```
Label extractor: `jsonPayload.labels.version`

---

## GCP Console Setup (Manual — No Code Required)

### 1. BigQuery Log Export

1. Go to **Cloud Logging → Log Router → Create Sink**
2. Name: `juno-logs-bq`
3. Destination: **BigQuery dataset** — create `juno_logs` in `us-central1`
4. Filter: `resource.type="cloud_run_revision"`
5. Enable partitioned tables: **yes** (partitioned by `_PARTITIONTIME`)
6. Click **Create**

Logs appear in BigQuery within ~1 minute. Query with:
```sql
SELECT
  JSON_VALUE(json_payload, '$.session_id') AS session_id,
  JSON_VALUE(json_payload, '$.step_name') AS step_name,
  CAST(JSON_VALUE(json_payload, '$.duration_ms') AS FLOAT64) AS duration_ms,
  timestamp
FROM `juno-medical-clarity.juno_logs.run_googleapis_com_stdout_*`
WHERE DATE(_PARTITIONTIME) = CURRENT_DATE()
ORDER BY timestamp DESC
```

### 2. Log-Based Metrics in Cloud Monitoring

Go to **Cloud Monitoring → Metrics → Log-based metrics → Create metric**.

**Metric A: `simplify_request_duration_ms`**
- Type: **Distribution**
- Filter: `resource.type="cloud_run_revision" jsonPayload.metric=true jsonPayload.metric_type="latency" jsonPayload.operation="simplify_pipeline"`
- Value field: `jsonPayload.duration_ms`
- Units: `ms`

**Metric B: `simplify_step_error_count`**
- Type: **Counter**
- Filter: `resource.type="cloud_run_revision" jsonPayload.metric=true jsonPayload.metric_type="error"`
- Label: name=`error_type`, field=`jsonPayload.error_type`, type=STRING
- Label: name=`operation`, field=`jsonPayload.operation`, type=STRING

**Metric C: `simplify_request_count`**
- Type: **Counter**
- Filter: `resource.type="cloud_run_revision" jsonPayload.metric=true jsonPayload.metric_type="counter" jsonPayload.metric_name="simplify_request"`
- Label: name=`version`, field=`jsonPayload.labels.version`, type=STRING

### 3. Dashboard

Go to **Cloud Monitoring → Dashboards → Create Dashboard** and add:
- Panel 1: `simplify_request_duration_ms` — percentile distribution (p50/p95/p99)
- Panel 2: `simplify_step_error_count` — bar chart grouped by `operation`
- Panel 3: `simplify_request_count` — line chart grouped by `version`
- Panel 4: Cloud Run built-in `request_count` by revision (auto-available, no setup)

### 4. SERVICE_VERSION Environment Variable

In the Cloud Run deploy config (or CI/CD), set:
```
SERVICE_VERSION=<git-sha>   # e.g. $(git rev-parse --short HEAD)
```
This populates `service.version` in Cloud Trace, enabling latency comparisons across deploys.
