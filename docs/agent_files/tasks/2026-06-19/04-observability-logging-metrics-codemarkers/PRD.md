# PRD: Observability — Code-Marker Metrics, session_id Correlation, Trace/Metrics Explorer, Multi-Version Logging

Sub-project 4 of 6 (SP4). **Phase 2.** Depends on **SP1** (Pydantic/`JsonModel` models with per-function `version` fields), **SP2** (the single `care_plan` route + pipeline this instruments; removes dead `appointment_id` route plumbing), **SP3** (utils restructure; removes `utils/LOGGING.md`). Consumed by **SP5** (frontend reads `X-Session-Id` / `X-Trace-Id`) and **SP6** (tests the marker + sink via an `InMemorySink`).

---

## 1. Problem

Juno's observability works but is hand-rolled, inconsistent, and has a security bug.

1. **Stopwatch boilerplate everywhere.** Every pipeline step in `routes/simplify_v1_2.py` repeats the same five lines: `t0 = monotonic_ms()` … `juno_logger.log_step(name, "start")` … work … `juno_logger.log_step(name, "done", duration_ms=monotonic_ms()-t0)` … `metrics.step_durations_ms[name] = …` … plus a separate `juno_metrics.record_latency/record_error(...)` call in the error branch. Six steps × ~10 lines each = a wall of copy-paste where the timing, the success/error outcome, the metric emission, and the log line are all wired by hand and easy to get subtly wrong (and they already are inconsistent — `find_medical_terms` records duration only on success, `simplify_language` records it unconditionally, the per-step `record_latency` is missing entirely while a single `simplify_pipeline` total is recorded at the end). There is no single place that says "this is where the metric for this operation is emitted."

2. **`session_id` security bug + naming drift.** Two routes fall back to **`user_id` (the Firebase UID) as the session_id** when `g.session_id` is missing:
   - `routes/simplify_v1_2.py:491` — `Metrics.start(session_id=getattr(g, "session_id", user_id), …)`
   - `routes/batch.py:191` — `Metrics.start(session_id=getattr(g, "session_id", user_id), …)`

   This can stamp a raw Firebase UID into the `Metrics.session_id` field, into logs, into the `X-Session-Id` response header, and onto the OTel span's `session.id` attribute — leaking a stable user identifier into a correlation field that is echoed to the client and shared across the trace surface. It is also pointless: `before_request` always sets `g.session_id`, and `user_id` is already carried in its **own** field. The fallback is dead-but-dangerous code. Separately, the analysis doc and code mix "request id" / "correlation id" / "session_id"; the owner wants **one name everywhere: `session_id` (`X-Session-Id`)**.

3. **Three IDs, no explanation, and the trace-id log query "doesn't work."** The owner sees `trace_id`, `span_id`, and `session_id` in logs and asks: what is each, why three, why can't I just use the trace id, should I share it with the frontend, and *why did pasting a trace id into the Logs Explorer return nothing while I see lots of span ids?* These are answerable and the answers drive concrete config changes (§4.6).

4. **Single `api_version`, but the pipeline is multi-function multi-version.** `JunoLogger` stamps one `api_version` ("v1-2"). But the pipeline is several functions, **each with its own data model and its own version**: the care_plan (SimplifiedCarePlan `version` "1.2"), grading (its own version), input (its own version). A single `api_version` can't express "care_plan v1.2 + grading v2 + input v1 ran in this request," and logs don't reliably say **which function** produced a line.

5. **`appointment_id` leaking into correlation semantics.** `before_request` still prefers `appointment_id` from the URL as the `session_id` (`app.py:67-69`). SP2 removes that route plumbing; SP4 owns the resulting session-id / logging semantics and must drop the `appointment_id` special-case.

6. **Metrics/Trace Explorer not actually wired or documented.** Metrics are emitted as `jsonPayload.metric=true` log lines, but no log-based metrics are created, and there is no doc on *using* Metrics Explorer or Trace Explorer for Juno. The span already gets a `session.id` attribute (`app.py:81`) but nobody knows how to query Trace by it.

---

## 2. Goals

1. Adopt the **code-marker pattern** (port of the C# `MonitoredCodeMarkers` system at `/root/projects/code_marker_sample/`) as the single way to time + emit a metric for an operation. `Markers.CarePlan.SimplifyLanguage.execute(lambda scope: …)` auto-times, auto-sets outcome, collects dimensions, and emits to a pluggable `Sink`. **No manual stopwatch.**
2. Ship every marker event to **both** Cloud Monitoring log-based metrics **and** the structured logger, via one `JunoSink` — superseding the `JunoMetrics` *call sites* while reusing the existing JSON-log-to-stdout transport.
3. A **`Markers` registry** naming every Juno operation (the care_plan pipeline steps + `http_request` + grading), so there is literally "a code marker so you know exactly where that metric is output."
4. Replace the manual stopwatch/record_latency boilerplate in the care_plan route with `.execute()` wrapping (before/after in §4.4).
5. **Fix the session_id bug:** never use `user_id` as the `session_id` fallback; fallback is a generated UUID; `user_id` stays its own field. Rename everything to `session_id` / `X-Session-Id`. Audit `before_request`.
6. **Auto-add standard dimensions** (`session_id`, `user_id`, function/layer, the three versions, `outcome`) on every emitted metric and metric-log via a `Context` bound to `flask.g` — devs never repeat them.
7. **Multi-version + function logging:** replace the single `api_version` field with `function` (the layer name) + `care_plan_version` / `grading_version` / `input_version`.
8. Wire and **document** Trace Explorer (query a whole session's spans by `session.id`) and Metrics Explorer (chart the log-based metrics), plus the **exact working** Logs-Explorer trace query, and decide + spec sharing `trace_id` to the frontend (`X-Trace-Id`).
9. Rewrite `docs/logging.md` as the single home for all of the above (SP3 deletes `utils/LOGGING.md`).

---

## 3. Non-Goals

- **Not** rewriting the OTel/Cloud Trace transport in `telemetry.py` (it's fine; we add manual child spans + make `session.id` queryable, and read `SERVICE_VERSION` which is already wired).
- **Not** adding manual child OTel spans for *every* step in this SP beyond what the markers naturally need — markers emit metrics/logs; we add child spans only where the flame-graph value is high (the LLM steps). Full per-step span coverage can be a follow-up.
- **Not** changing the SSE protocol, the pipeline's clinical behavior, or grading math (SP3's territory).
- **Not** building dashboards/alerts in code — Metrics Explorer charts, dashboards, and alert policies are Console steps (§8), because log-based metric creation is Console-only on GCP.
- **Not** BigQuery export or Grafana — out of scope for SP4 (covered as "later" in the research doc).
- **Not** owning the `care_plan` route rename itself (SP2) — SP4 aligns marker/log/metric *operation names* to `care_plan`.

---

## 4. Architecture Decisions

### 4.1 Where the code lives

New package **`backend/utils/markers/`** (SP3 owns `utils/`; markers are a util). Mirrors the sample 1:1 so SP6 testability (`InMemorySink`) is free:

```
backend/utils/markers/
  __init__.py     # re-exports CodeMarker, Scope, Context, Sink, ConsoleSink, InMemorySink,
                  #            Markers, register_sink, resolve_sink, code_marker
  marker.py       # COPIED verbatim from sample (Scope, CodeMarker, code_marker, execute/execute_async)
  registry.py     # COPIED verbatim (global sink slot)
  sinks.py        # sample Sink/ConsoleSink/InMemorySink  +  new JunoSink (Juno bridge)
  context.py      # sample Context  +  new JunoContext.from_g() (binds flask.g + versions)
  markers.py      # Juno Markers registry (replaces the sample's Orders/Users/Jobs demo)
```

**`marker.py` and `registry.py` are copied unchanged** — they are domain-agnostic and already do exactly what we need (auto-duration via `time.perf_counter_ns`, auto-`OpOutcome` Succeeded/Failed, never-let-a-bad-sink-break-the-caller in `_emit`). Re-deriving them is pure risk. Only `sinks.py`, `context.py`, `markers.py` get Juno content.

### 4.2 The `Markers` registry (operation names → metric names)

Names align to **care_plan** (SP2 rename), one nested group per layer. Each leaf is a singleton `CodeMarker` subclass; its `@code_marker("…")` string is the **metric/operation name** emitted to the sink — this is the "code marker so you know exactly where the metric is output."

```python
# backend/utils/markers/markers.py
from __future__ import annotations
from .marker import CodeMarker, code_marker


class Markers:
    """Juno operation registry. Each leaf's name() is the emitted metric name."""

    class CarePlan:  # the care_plan pipeline (SP2 route)
        @code_marker("care_plan.read_input")
        class ReadInput(CodeMarker): pass

        @code_marker("care_plan.find_medical_terms")
        class FindMedicalTerms(CodeMarker): pass

        @code_marker("care_plan.simplify_language")
        class SimplifyLanguage(CodeMarker): pass

        @code_marker("care_plan.clarify_actions")
        class ClarifyActions(CodeMarker): pass

        @code_marker("care_plan.structure_note")
        class StructureNote(CodeMarker): pass

        @code_marker("care_plan.save_output")
        class SaveOutput(CodeMarker): pass

        @code_marker("care_plan.pipeline")   # whole-pipeline total (replaces simplify_pipeline)
        class Pipeline(CodeMarker): pass

    class Grading:
        @code_marker("grading.run")
        class Run(CodeMarker): pass

    class Http:
        @code_marker("http.request")          # replaces the after_request record_latency("http_request")
        class Request(CodeMarker): pass
```

Operation→metric mapping (the 7 pipeline ops the owner listed + http + grading) is therefore: `read_input, find_medical_terms, simplify_language, clarify_actions, structure_note, save_output, grading` → `Markers.CarePlan.*` / `Markers.Grading.Run`, plus `Markers.Http.Request`. Pipeline-total is `care_plan.pipeline`.

### 4.3 The `JunoSink` (bridge to Cloud Monitoring + structured logger)

**Decision: the marker sink supersedes `JunoMetrics` at the call sites, but reuses its transport.** `JunoMetrics` today *is* "write a `jsonPayload.metric=true` JSON line to stdout, Cloud Logging ingests it, log-based metrics extract it." That transport is correct and free. We keep it; we just stop hand-calling `record_latency/record_counter/record_error` and let the marker `_emit` → `JunoSink.emit` do it once, uniformly. `JunoSink` writes **two outputs per event**:

1. a **metric log line** (`jsonPayload.metric=true`, `metric_type="marker"`) that Metrics Explorer log-based metrics chart, and
2. a **human-readable structured log line** (`message="op_complete"`) so the same event shows up on the session timeline in Logs Explorer.

(Whether `JunoMetrics`/`JunoLogger` classes are deleted or kept as thin wrappers is coordinated with SP3 — SP4's position: **delete `JunoMetrics`' public methods' call sites**, keep `JunoLogger` for free-text/step logs that aren't operation-scoped. See §9.)

```python
# backend/utils/markers/sinks.py   (appended to the copied Sink/ConsoleSink/InMemorySink)
import logging
from typing import Any, Dict

_metric_logger = logging.getLogger("juno.metrics")
_event_logger = logging.getLogger("juno.markers")


class JunoSink:
    """Marker sink: one event -> a log-based-metric line + a timeline log line.

    Event shape from CodeMarker._emit:
        {"name": "care_plan.simplify_language", "duration_ms": 1840,
         "success": True, "dimensions": {...}}
    """

    def emit(self, event: Dict[str, Any]) -> None:
        name = event["name"]
        duration_ms = event["duration_ms"]
        success = event["success"]
        dims = event.get("dimensions") or {}

        # (1) metric line — Metrics Explorer log-based metrics read these.
        #     metric=true + metric_type="marker" is the stable selector.
        _metric_logger.info(
            "juno_metric",
            extra={
                "metric": True,
                "metric_type": "marker",
                "operation": name,           # label: which marker
                "duration_ms": round(duration_ms, 1),
                "success": success,          # label: distribution split ok/fail
                "outcome": dims.get("OpOutcome", "Succeeded" if success else "Failed"),
                **dims,                       # session_id, user_id, function, versions, etc.
            },
        )

        # (2) timeline line — Logs Explorer session view reads these.
        level = logging.INFO if success else logging.ERROR
        _event_logger.log(
            level, "op_complete",
            extra={"operation": name, "duration_ms": round(duration_ms, 1),
                   "success": success, **dims},
        )
```

`StructuredJsonFormatter` already serializes arbitrary `extra` keys into `jsonPayload` (§4.7 extends it to whitelist the new keys reliably). `register_sink(JunoSink())` is called once at startup in `app.py`, right after `setup_logging()`. In tests, SP6 calls `register_sink(InMemorySink())` and asserts on `sink.events` — identical to `code_marker_sample/example.py`.

### 4.4 The `JunoContext` — auto-standard dimensions (no repetition)

`Context.apply(scope)` from the sample pushes common dimensions. We add `JunoContext.from_g()` which reads `flask.g` once and bundles **session_id, user_id, function/layer, the three versions, and any custom dims** so every `.execute()` body is one line: `JunoContext.from_g(function="simplify_language").apply(scope)`.

```python
# backend/utils/markers/context.py  (appended to the copied Context)
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from .marker import Scope


def _g(name: str, default=None):
    try:
        from flask import g
        return getattr(g, name, default)
    except RuntimeError:
        return default


@dataclass
class JunoContext:
    """Standard Juno dimensions, sourced from flask.g, applied to every scope."""
    function: Optional[str] = None       # the layer/function name, e.g. "simplify_language"
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_g(cls, function: Optional[str] = None, **extra) -> "JunoContext":
        return cls(function=function, extra=extra)

    def apply(self, scope: Scope) -> None:
        scope.add("session_id", _g("session_id"))
        scope.add("user_id", _g("user_id"))                       # never used as session_id
        scope.add("function", self.function)                      # the layer
        scope.add("care_plan_version", _g("care_plan_version"))   # set by route (§4.5)
        scope.add("grading_version", _g("grading_version"))
        scope.add("input_version", _g("input_version"))
        scope.add("service", _g("service") or "juno-backend")
        scope.add("environment", _g("environment") or "production")
        scope.add_many(self.extra)
```

`scope.add` already drops `None` values, so missing versions never pollute the event.

### 4.5 Multi-version + function logging schema

The single `api_version` field is **replaced** by:

| Field | Source | Meaning |
|---|---|---|
| `function` | marker `Context.function` (or `JunoLogger(function=…)`) | the layer/function producing the line: `read_input`, `simplify_language`, `grading`, `http_request`, … |
| `care_plan_version` | `SimplifiedCarePlan` version (SP1), e.g. `"1.2"` | care_plan data-model version |
| `grading_version` | Grading model version (SP1) | grading data-model version |
| `input_version` | Input model version (SP1) | input data-model version |

The route sets these on `g` once (so both markers and `JunoLogger` pick them up):

```python
# in the care_plan route, after resolving input / picking pipeline (SP2 route)
g.care_plan_version = "1.2"          # = SimplifiedCarePlan version for this pipeline
g.grading_version   = GRADING_VERSION    # from SP1 grading model
g.input_version     = INPUT_VERSION      # from SP1 input model
```

`JunoLogger.__init__(api_version=…)` becomes `__init__(function=…)`; `_base_fields()` drops `api_version` and adds `function` + the three `*_version` fields read from `g`. **Assumed SP1 interface:** each model exposes a module-level version constant (e.g. `models.grading.GRADING_VERSION`) or a `.version` attribute; if SP1 instead encodes version only on instances, the route passes the literal strings — either way the route is the single place that knows all three.

### 4.6 The owner's questions — trace_id vs span_id vs session_id (answer all)

> **"I already see a trace ID in logs. What is that?"**
A `trace_id` is a 32-hex-char ID for **one whole request tree**. OTel's `FlaskInstrumentor` mints it when the request arrives; every span and every log line in that request carries the same `trace_id`. It's the "this single HTTP call" id.

> **"What is a span ID?"**
A `span_id` is a 16-hex-char ID for **one operation *inside* the trace** — the root span (the HTTP request) has one; each child span (e.g. an outgoing Gemini call, or a manual `simplify_language` span) has its own. A trace is a tree of spans; the span id tells you *which node*. That's why you "see a bunch of span ids": one trace legitimately contains many.

> **"What is session_id? Why three different ids?"**
`session_id` is **our application-level** correlation id (`X-Session-Id`), and it's the only one that spans **multiple HTTP requests** in the same user session. The three answer three different scopes:
- `trace_id` → **one request** (auto, ephemeral, infra-level).
- `span_id` → **one operation within that request** (auto, even more granular).
- `session_id` → **a user session across many requests** (ours, the unit *we* care about for "show me everything this user did").
A trace ends when the HTTP request ends; a session can contain dozens of traces. You can't replace `session_id` with `trace_id` because `trace_id` resets every request.

> **"Why can't I use trace_id directly / should I share it to the frontend?"**
Use **`trace_id` for one-request debugging** ("this exact failed call — show me its span waterfall in Trace") and **`session_id` for cross-request correlation** ("everything in this user's session"). We **do** share both to the frontend: `X-Session-Id` (already echoed) for the durable session, and we **add `X-Trace-Id`** (§5) so a frontend error report can deep-link the support engineer straight to that one trace. Frontend persists `session_id` for the whole session; `trace_id` it captures per failed request.

> **"I pasted a trace id into the Logs Explorer and got nothing, but I see span ids — why?"**
Because Cloud Logging does **not** index the bare hex `trace_id`. `logging_config.py` writes the special field `logging.googleapis.com/trace` as the **full resource path** `projects/juno-medical-clarity/traces/<hex>` (and `jsonPayload.trace_id` as the bare hex). A query of `trace="<hex>"` matches the top-level `LogEntry.trace` field, which only equals the **full path**, not the hex — so the bare hex matches nothing at top level. Two queries that **do** work (§4.6a).

#### 4.6a Exact working Logs Explorer trace queries (copy-paste)

Bare hex against the top-level field fails. Use **one** of:

```text
# A) Match the special trace field by its FULL resource path (what GCP actually indexes):
trace="projects/juno-medical-clarity/traces/abc123def456...<32 hex>"
resource.type="cloud_run_revision"
```
```text
# B) Match the bare hex we ALSO mirror into jsonPayload (handy when you only have the hex):
jsonPayload.trace_id="abc123def456...<32 hex>"
resource.type="cloud_run_revision"
```
```text
# C) From the Trace waterfall, click "View logs" — GCP builds query (A) for you automatically.
```

The fix to document (and the reason A is the canonical form): the value in `LogEntry.trace` is the **path**, never the hex. SP4 keeps emitting both fields so either query works, and the doc shows query A as primary.

#### 4.6b Trace Explorer: view all spans/logs for a session_id

The span already gets `session.id` (`app.py:81`). To make it **queryable** in Trace Explorer:
1. Keep setting `session.id` on the **root** span (done) **and** set it on every **manual child span** we add (§4.8), so a span-attribute filter returns the whole tree.
2. In Trace Explorer (`console.cloud.google.com/traces`), the **Filter** field supports span-attribute filters: `session.id = <uuid>` returns every span (across requests in that session) carrying it — that's the "all spans for a session" view.
3. Cross-link: from any log line, "Run in Trace" jumps via `logging.googleapis.com/trace`; from a span, "View logs" jumps back via the same field — so `session_id` (logs) ↔ `trace_id`/`session.id` (traces) round-trip in the Console.

### 4.7 `before_request` / session_id rules (the fix)

New `before_request` logic (drop the `appointment_id` special-case per SP2; never fall back to `user_id`):

```python
@app.before_request
def extract_session_id():
    # 1) client-supplied durable session id, else 2) a fresh UUID. NEVER user_id.
    session_id = request.headers.get("X-Session-Id", "").strip() or str(uuid.uuid4())
    g.session_id = session_id

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("session.id", session_id)
        span.set_attribute("http.route", request.path)
    # http.request marker (replaces after_request record_latency) is opened here / closed in after_request — see TASKS Task 7.
```

`Metrics.start(...)` call sites change from `session_id=getattr(g, "session_id", user_id)` to `session_id=g.session_id` (guaranteed set). `user_id` continues to flow only through its own `g.user_id` / dimension. This closes the UID-leak in both `simplify_v1_2.py` and `batch.py`.

### 4.8 Manual child spans (high-value only)

Wrap the three LLM steps (`simplify_language`, `clarify_actions`, `structure_note`) in `tracer.start_as_current_span(name)` and set `span.set_attribute("session.id", g.session_id)` so Trace Explorer's `session.id` filter returns them. This is complementary to markers (markers = metrics+timeline logs; spans = flame graph). Done inside the same `.execute()` body, so no extra boilerplate scatter.

---

## 5. API Change Summary

**New response header:**
- `X-Trace-Id: <32-hex>` — current request's trace id, set in `after_request` from the active span context. Added to `CORS(expose_headers=[…])` alongside `X-Session-Id`.

**Unchanged:** `X-Session-Id` request/response header (still the durable session id; now guaranteed never to be a Firebase UID).

**Log/metric field changes (`jsonPayload.*`):**
- **Removed:** `api_version`.
- **Added:** `function`, `care_plan_version`, `grading_version`, `input_version`, `outcome` (`Succeeded`/`Failed`), `operation` (marker name), `success` (bool) on marker metric lines.
- **`metric_type`** gains value `"marker"` (the selector for the new log-based metrics).
- `session_id` semantics fixed (never a UID); `user_id` always its own field.

**No route/path/SSE changes** (SP2 owns the route rename).

---

## 6. Frontend Change Summary (SP5 implements — brief)

- Read **`X-Session-Id`** from the first response, store it for the whole session (already partly done), and **send it back as `X-Session-Id`** on every subsequent request so all of a session's requests correlate.
- Read **`X-Trace-Id`** per response; attach it to any client-side error report / "report a problem" payload so support can deep-link the exact trace.
- Guidance: use `session_id` for "my whole session is broken" reports; include `trace_id` for "this one action failed." Do **not** display raw ids to end users; keep them in diagnostics.

---

## 7. Testing (SP6 implements — what SP4 must make testable)

- **Marker core is testable like the sample:** `register_sink(InMemorySink())`, run `Markers.CarePlan.SimplifyLanguage.execute(lambda s: …)`, assert one event with `name="care_plan.simplify_language"`, `success=True`, `duration_ms>=0`, and dimensions containing `session_id`, `function`, versions, `OpOutcome="Succeeded"`.
- **Failure path:** an action that raises → event still emitted with `success=False`, `outcome="Failed"`, and the exception propagates (assert both).
- **`JunoSink` double-emit:** with a fake/captured logger, assert one `metric=true, metric_type="marker"` line **and** one `message="op_complete"` line per event.
- **`JunoContext.from_g` outside a request context** returns a context that applies no `None`s (no crash).
- **session_id bug regression test:** request with **no** `X-Session-Id` and an authenticated user → `g.session_id` is a UUID, `Metrics.session_id` is that UUID, and it is **not equal** to `g.user_id`; `X-Session-Id` response header is the UUID, not the UID. Same assertion for `routes/batch.py`.
- **Multi-version fields:** a care_plan request emits log lines with `function`, `care_plan_version`, `grading_version`, `input_version` and **no** `api_version`.
- **`X-Trace-Id` header** present and 32-hex on a normal response.

---

## 8. Manual Intervention Required From You (Cloud Console / deploy)

These cannot be done from code (log-based metric creation, Explorer setup, env, IAM are Console/deploy-config actions).

1. **Set `SERVICE_VERSION` on Cloud Run** (git SHA or semver) in `.github/workflows/deploy-backend.yml` env — `telemetry.py` already reads it; today it's `unknown`, so version-segmented Trace/metrics are flat until set.
2. **Create log-based metrics** (Logging → Logs-based Metrics → Create), all filtered `resource.type="cloud_run_revision"`:
   - **`marker_duration_ms`** — *Distribution*; filter `jsonPayload.metric=true AND jsonPayload.metric_type="marker"`; field `jsonPayload.duration_ms`; labels: `operation` (`jsonPayload.operation`), `success` (`jsonPayload.success`), `care_plan_version`.
   - **`marker_op_count`** — *Counter*; same filter; labels `operation`, `success`, `outcome`.
   - **`care_plan_errors`** — *Counter*; filter `… metric_type="marker" AND jsonPayload.success=false`; label `operation`.
   (≤10 custom metrics = free.)
3. **Metrics Explorer** (Monitoring → Metrics Explorer): select resource/metric `logging.googleapis.com/user/marker_duration_ms`, group by `operation`, aggregate p50/p95/p99; save to a "Juno Pipeline" dashboard (3 tiles: latency by op, op count by success, error count by op). Step-by-step copy goes in `docs/logging.md`.
4. **Trace Explorer**: confirm the `session.id` span attribute appears (send a test request with `X-Session-Id`), then save a filter `session.id = <id>`. Document the round-trip (logs ↔ trace) buttons.
5. **IAM sanity check**: the Cloud Run runtime SA needs `roles/cloudtrace.agent` (write traces) and `roles/logging.logWriter` (already implicit via stdout). No new IAM expected, but verify trace export isn't silently failing (telemetry.py logs a warning if the exporter fails).
6. **Confirm the `*_version` source of truth from SP1** (a module constant vs instance attribute) so the route sets `g.*_version` from the right place (§4.5, §9).

---

## 9. Open Questions

1. **SP3 coordination — delete vs keep `JunoMetrics`?** SP4's stance: retire `JunoMetrics`' call sites in favor of markers; keep the `metric=true` log shape (so existing log-based metrics keep working during migration). Should `JunoMetrics` the *class* be deleted now, or kept one release as a deprecated shim? (Recommend: keep as a thin shim that internally opens a marker, delete in a later cleanup.)
2. **`JunoLogger.api_version` → `function`** is a signature change touching SP2's route and any other caller. Confirm SP2 hands SP4 the single instrumented route so we don't chase v1/v1-1 callers that SP2 may be deleting.
3. **SP1 version constants** (Q in §8.6): exact import path for `care_plan_version` / `grading_version` / `input_version`. Assumed module-level constants; will adapt.
4. **Async**: the pipeline is sync generators today; `execute_async` is ported but unused. Keep it for future Vertex async calls? (Recommend: yes, it's free.)
5. **Sampling**: at higher volume, should the timeline `op_complete` log line be sampled while the metric line stays 100%? (Out of scope now; flag for scale.)
