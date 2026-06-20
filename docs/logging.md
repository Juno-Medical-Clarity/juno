# Observability — Logging, Tracing, and Metrics

This document is the single home for all Juno observability. It covers the three
correlation IDs, working trace queries, Metrics/Trace Explorer how-tos, the
code-marker developer guide, and the full field reference.

---

## 1. The Three IDs — trace_id, span_id, session_id

Understanding the three identifiers prevents most debugging dead-ends.

### trace_id

A 32-hex-character ID for one whole request tree. OTel's `FlaskInstrumentor`
mints it when the request arrives; every span and log line in that request
carries the same `trace_id`. It is the "this single HTTP call" id.

### span_id

A 16-hex-character ID for one operation *inside* the trace. The root span (the
HTTP request) has one; each child span (e.g. an outgoing Gemini call, a manual
`simplify_language` span) has its own. A trace is a tree of spans. That is why
you "see a bunch of span ids": one trace legitimately contains many.

### session_id

Our application-level correlation id (`X-Session-Id`). The only one that spans
multiple HTTP requests in the same user session.

**Three scopes:**

| ID | Scope | Set by | Lifetime |
|---|---|---|---|
| `trace_id` | One HTTP request | OTel `FlaskInstrumentor` (auto) | Ends when the request ends |
| `span_id` | One operation within a request | OTel (auto) / manual spans | Sub-request |
| `session_id` | A user session across many requests | Our `before_request` middleware | Entire session |

A trace ends when the HTTP request ends; a session can contain dozens of traces.
You cannot replace `session_id` with `trace_id` because `trace_id` resets on
every request.

### Should I share trace_id to the frontend?

Yes. Both `X-Session-Id` (durable session) and `X-Trace-Id` (per-request) are
now echoed as response headers.

- **Frontend persists `session_id`** for the whole session and sends it on every
  subsequent request so the backend can correlate all calls in the same session.
- **Frontend captures `trace_id` per failed request** for support deep-links
  ("this exact request failed") — paste the hex into query B or C in §2.

Do not display raw IDs to end users; keep them in diagnostics and error reports
only.

---

## 2. Logs Explorer: Find Logs for a Trace

### Why the bare hex fails

Cloud Logging indexes `LogEntry.trace` as a full resource path, not the bare
hex. A bare hex query against the top-level field matches nothing.

### Three working queries

**Query A — canonical (full resource path, what GCP actually indexes):**

```
trace="projects/juno-medical-clarity/traces/YOUR_32_HEX_TRACE_ID"
resource.type="cloud_run_revision"
```

**Query B — bare hex via jsonPayload (we mirror it there too):**

```
jsonPayload.trace_id="YOUR_32_HEX_TRACE_ID"
resource.type="cloud_run_revision"
```

**Query C — from the Trace waterfall (easiest path):**

Open Cloud Trace, find the trace, click **"View logs"** on any span. GCP builds
query A automatically and opens Logs Explorer pre-filtered to that trace.

Query A is the canonical form. Prefer query C when you already have the trace
open. Use query B when you only have the hex and want to avoid typing the full
path.

---

## 3. Trace Explorer: Query by session_id

### How to find all spans for a session

1. Go to `console.cloud.google.com/traces`.
2. In the **Filter** field, enter:
   ```
   session.id = YOUR_SESSION_UUID
   ```
3. This returns every span across all requests in that session that carries
   `session.id` — the whole session's trace tree.
4. From any span, click **"View logs"** to jump to Logs Explorer filtered to
   that trace. From a log line, click **"Run in Trace"** to jump to the span
   waterfall.

### How session.id gets onto spans

The backend sets `session.id` on the root span in `before_request` and on
manual child spans for LLM steps in the care_plan pipeline. This means every
network call within a session carries the attribute and shows up in step 2
above.

---

## 4. Metrics Explorer: Charting Pipeline Latency

### View pipeline latency

1. Go to **Google Cloud Console → Monitoring → Metrics Explorer**.
2. **Resource**: `Cloud Run Revision`
3. **Metric**: `logging.googleapis.com/user/marker_duration_ms`
4. **Group by**: `operation`; **Aggregation**: `p50` / `p95` / `p99`
5. Save as the **"Juno Pipeline Latency"** dashboard tile.

### View error rate

- **Metric**: `logging.googleapis.com/user/marker_op_count`
- **Filter**: `success=false`
- **Group by**: `operation`

### View error count

- **Metric**: `logging.googleapis.com/user/care_plan_errors`
- **Group by**: `operation`

### Creating the log-based metrics (Console-only — you must do this)

Go to **Logging → Logs-based Metrics → Create metric**.

Base filter for all three metrics:

```
resource.type="cloud_run_revision"
AND jsonPayload.metric=true
AND jsonPayload.metric_type="marker"
```

**`marker_duration_ms`** — Distribution metric:
- **Field**: `jsonPayload.duration_ms`
- **Labels**:
  - `operation` → `jsonPayload.operation`
  - `success` → `jsonPayload.success`
  - `care_plan_version` → `jsonPayload.care_plan_version`

**`marker_op_count`** — Counter metric:
- **Labels**: `operation`, `success`, `outcome`

**`care_plan_errors`** — Counter metric:
- **Extra filter**: add `AND jsonPayload.success=false`
- **Label**: `operation`

---

## 5. Code Markers: Adding Instrumentation

Code markers are the standard way to instrument an operation so it gets
automatic timing, success/failure tracking, and metric emission.

### Wrap an operation

```python
from utils.markers import Markers, JunoContext

def _do(scope):
    JunoContext.from_g(function="my_operation").apply(scope)
    # optional: add custom dimensions
    scope.add("input_chars", len(text))
    # do the actual work
    return do_my_work()

result = Markers.CarePlan.MyOperation.execute(_do)
```

### Non-fatal fallback steps

For steps that can fail gracefully, catch inside `_do`, call `scope.mark_failed()`,
and return the fallback value:

```python
def _do(scope):
    JunoContext.from_g(function="my_step").apply(scope)
    try:
        return risky_operation()
    except Exception:
        logger.exception("step failed - using fallback")
        scope.mark_failed()
        return fallback_value

result = Markers.CarePlan.MyStep.execute(_do)
```

The marker records `success=false` and `outcome="Failed"` in the metric log
line, then returns the fallback normally. The request does not fail.

### Add a new marker to the registry

Edit `backend/utils/markers/markers.py`:

```python
class CarePlan:
    @code_marker("care_plan.my_new_step")
    class MyNewStep(CodeMarker): pass
```

The string argument becomes the `operation` field on every metric log line and
span emitted by this marker. Use `snake_case` dot-separated names.

### Testing with InMemorySink

```python
from utils.markers import register_sink, InMemorySink, Markers

sink = InMemorySink()
register_sink(sink)
Markers.CarePlan.SimplifyLanguage.execute(lambda s: None)
assert sink.events[0]["name"] == "care_plan.simplify_language"
assert sink.events[0]["success"] is True
```

`InMemorySink` captures every marker event in memory. Register it before the
call under test; inspect `sink.events` after. Unregister between tests if
multiple test cases share the same sink.

---

## 6. jsonPayload Field Reference

All fields below appear in `jsonPayload` in Cloud Logging.

| Field | Source | Values | Notes |
|---|---|---|---|
| `severity` | Python log level | `INFO`, `WARNING`, `ERROR` | |
| `message` | logger message | string | `"op_complete"` for markers, `"juno_metric"` for metric lines |
| `session_id` | `flask.g.session_id` | UUID | Set by `before_request`; never a Firebase UID |
| `user_id` | `flask.g.user_id` | Firebase UID | Always its own field; never used as `session_id` |
| `function` | marker `JunoContext` | e.g. `"simplify_language"` | |
| `care_plan_version` | `CARE_PLAN_VERSION` constant | `"1.2"` | |
| `grading_version` | `GRADING_VERSION` constant | `"1.0"` | |
| `input_version` | `INPUT_VERSION` constant | `"1.0"` | |
| `operation` | marker name | e.g. `"care_plan.simplify_language"` | Present on marker events only |
| `metric` | JunoSink | `true` | Present on metric log lines only |
| `metric_type` | JunoSink | `"marker"` | |
| `duration_ms` | marker auto-timer | float (ms) | Present on metric log lines |
| `success` | marker outcome | bool | `true` = Succeeded |
| `outcome` | marker outcome | `"Succeeded"` / `"Failed"` | |
| `trace_id` | OTel | 32-hex string | Links to Cloud Trace |
| `span_id` | OTel | 16-hex string | Links to specific span |
| `logging.googleapis.com/trace` | OTel | `projects/.../traces/...` | Used by Logs Explorer "Run in Trace" |
| `service` | `K_SERVICE` env var | e.g. `"juno-backend"` | |
| `environment` | `K_SERVICE` presence | `"production"` / `"development"` | |

**Removed field**: `api_version` was retired and replaced by three separate
version fields: `function`, `care_plan_version`, `grading_version`, and
`input_version`.

---

## 7. session_id Rules

- `session_id` is **never** a Firebase UID. The `before_request` middleware sets
  it from the `X-Session-Id` header (client-supplied) or generates a UUID when
  the header is absent.
- `user_id` is always its own separate field (`g.user_id`), set by
  `@verify_firebase_token`.
- **`X-Session-Id`**: Send on every request to correlate a session across
  multiple HTTP calls. Read it from the first response and resend it on all
  subsequent requests.
- **`X-Trace-Id`**: Present on every non-SSE response. Capture it per failed
  request for support deep-links ("this exact request failed").
- Use `session_id` for "my whole session is broken" reports. Include `trace_id`
  for "this one action failed."
- Do not display raw IDs to end users; keep them in diagnostics and error
  reports only.

---

## 8. gcloud Logging Recipes

```bash
# All logs for a session (most useful for support)
gcloud logging read \
  'resource.type="cloud_run_revision" jsonPayload.session_id="YOUR_SESSION_UUID"' \
  --project=juno-medical-clarity --limit=100 --format=json

# All marker metric events (use for manual latency inspection)
gcloud logging read \
  'resource.type="cloud_run_revision" jsonPayload.metric=true jsonPayload.metric_type="marker"' \
  --project=juno-medical-clarity --limit=50 --format=json

# All failed operations
gcloud logging read \
  'resource.type="cloud_run_revision" jsonPayload.metric=true jsonPayload.success=false' \
  --project=juno-medical-clarity --limit=50 --format=json

# Logs for a specific trace (use full path — bare hex won't work)
gcloud logging read \
  'trace="projects/juno-medical-clarity/traces/YOUR_32_HEX"' \
  --project=juno-medical-clarity --limit=100 --format=json
```

---

## 9. Manual Steps Required

The following cannot be automated and must be done by a person in the Cloud
Console or CI config.

1. **Create the 3 log-based metrics** in Cloud Console (see §4 above for filter
   and label details).
2. **Build the Metrics Explorer dashboard tiles** for pipeline latency, error
   rate, and error count (see §4).
3. **Confirm `session.id` span attribute appears in Trace Explorer**: send a
   test request with an `X-Session-Id` header, then filter in Trace Explorer
   with `session.id = YOUR_SESSION_UUID`.
4. **IAM check**: confirm the Cloud Run runtime service account has
   `roles/cloudtrace.agent`.
5. **Deploy `SERVICE_VERSION`**: add
   `--set-env-vars "SERVICE_VERSION=${GITHUB_SHA}"` to the `gcloud run deploy`
   step in `.github/workflows/deploy-backend.yml` to stamp each revision with
   its git SHA. The `backend/VERSION` file provides a semver fallback when this
   env var is absent.
