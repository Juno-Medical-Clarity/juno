# Tasks: Observability — Code-Marker Metrics, session_id Correlation, Trace/Metrics Explorer, Multi-Version Logging

Read `PRD.md` in this folder first. SP4 lands in **Phase 2** after SP1 (models + version fields), SP2 (single `care_plan` route, `appointment_id` plumbing removed), SP3 (utils restructure, `utils/LOGGING.md` deleted).

**Assumed interfaces (state up front, adapt if wrong):**
- SP2 hands SP4 **one** instrumented route/pipeline (the `care_plan` route). Tasks below say "the care_plan route" — that is the SP2 file. Do not re-instrument deleted v1/v1-1 routes.
- SP1 exposes per-function versions; assumed as importable constants `models.care_plan.CARE_PLAN_VERSION`, `models.grading.GRADING_VERSION`, `models.input.INPUT_VERSION`. If SP1 only has instance `.version`, pass the literal version strings the route already knows.

---

### Task 1 — Create the `markers` package by copying the sample core

**Files (new):** `backend/utils/markers/{__init__.py, marker.py, registry.py}`

1. Copy `/root/projects/code_marker_sample/marker.py` **verbatim** to `backend/utils/markers/marker.py`. (It already provides `Scope`, `CodeMarker`, `@code_marker`, `execute`, `execute_async`, auto-duration via `time.perf_counter_ns`, auto-`OpOutcome`, and the bad-sink-swallowing `_emit`.)
2. Copy `/root/projects/code_marker_sample/registry.py` **verbatim** to `backend/utils/markers/registry.py` (global `register_sink`/`resolve_sink`).
3. Write `backend/utils/markers/__init__.py` re-exporting: `CodeMarker, Scope, code_marker, Context, JunoContext, Sink, ConsoleSink, InMemorySink, JunoSink, Markers, register_sink, resolve_sink`.

**Acceptance:** `from utils.markers import Markers, register_sink, InMemorySink, JunoSink, JunoContext` imports cleanly; copied files are byte-identical to the sample except the package docstring.

**Depends on:** SP3 (the `utils/` layout it produces).

---

### Task 2 — `sinks.py`: copy sample sinks + add `JunoSink`

**File (new):** `backend/utils/markers/sinks.py`

1. Copy `Sink` (Protocol), `ConsoleSink`, `InMemorySink` from the sample verbatim.
2. Append `JunoSink` exactly per PRD.md §4.3: it reads the `{name, duration_ms, success, dimensions}` event and emits **two** log lines:
   - metric line via `logging.getLogger("juno.metrics").info("juno_metric", extra={metric:True, metric_type:"marker", operation:name, duration_ms, success, outcome, **dims})`
   - timeline line via `logging.getLogger("juno.markers").log(INFO|ERROR, "op_complete", extra={operation:name, duration_ms, success, **dims})`

**Acceptance:** unit test with a captured handler: `JunoSink().emit({"name":"care_plan.simplify_language","duration_ms":12,"success":True,"dimensions":{"session_id":"s"}})` produces exactly one record with `metric==True and metric_type=="marker"` and one with `message=="op_complete"`; on `success=False` the timeline record level is ERROR.

**Depends on:** Task 1.

---

### Task 3 — `context.py`: copy sample `Context` + add `JunoContext`

**File (new):** `backend/utils/markers/context.py`

1. Copy the sample `Context` dataclass verbatim.
2. Append `JunoContext` per PRD.md §4.4: `from_g(function=None, **extra)` + `apply(scope)` that pushes `session_id, user_id, function, care_plan_version, grading_version, input_version, service, environment` from `flask.g` (use a local `_g()` helper that swallows `RuntimeError` outside request context), then `scope.add_many(self.extra)`. Rely on `Scope.add` already dropping `None`.

**Acceptance:** `JunoContext.from_g(function="x", foo="bar")` applied to a fresh `Scope` outside any Flask context adds `function="x"`, `foo="bar"`, `service`, `environment` and **no** `None` keys (no crash). Inside a request with `g.session_id`/`g.user_id`/`g.care_plan_version` set, those appear in `scope._dims`.

**Depends on:** Task 1.

---

### Task 4 — `markers.py`: the Juno `Markers` registry

**File (new):** `backend/utils/markers/markers.py`

Implement `Markers` exactly per PRD.md §4.2: groups `CarePlan` (ReadInput, FindMedicalTerms, SimplifyLanguage, ClarifyActions, StructureNote, SaveOutput, Pipeline), `Grading` (Run), `Http` (Request); each leaf a `CodeMarker` subclass decorated with its `@code_marker("…")` name.

**Acceptance:** `Markers.CarePlan.SimplifyLanguage.name() == "care_plan.simplify_language"`; all 9 leaves resolve and `.execute(lambda s: 1)` returns `1` and emits to the registered sink.

**Depends on:** Task 1.

---

### Task 5 — Register `JunoSink` at startup

**File:** `backend/app.py`

After `setup_logging()` (line ~20), add:

```python
from utils.markers import register_sink, JunoSink
register_sink(JunoSink())
```

**Acceptance:** at import time the global sink is a `JunoSink`; a marker `.execute()` during a request produces the two log lines.

**Depends on:** Tasks 1–4.

---

### Task 6 — Fix the session_id bug + drop appointment_id + rename to session_id everywhere

**Files:** `backend/app.py`, `backend/routes/simplify_v1_2.py` (or the SP2 care_plan route), `backend/routes/batch.py`

1. **`app.py` `extract_session_id`** — replace the body per PRD.md §4.7: drop the `appointment_id` branch entirely; `session_id = request.headers.get("X-Session-Id","").strip() or str(uuid.uuid4())`. Keep setting `g.session_id`, the span `session.id` + `http.route`, and `g.request_start_ms`.
2. **`simplify_v1_2.py:491`** — change `session_id=getattr(g, "session_id", user_id)` to `session_id=g.session_id`.
3. **`batch.py:191`** — change `session_id=getattr(g, "session_id", user_id)` to `session_id=g.session_id`.
4. Grep the backend for `request_id`, `correlation_id`, `getattr(g, "session_id", user_id)`, and `appointment_id` used as a session/correlation id; rename/remove so the only term is `session_id` / `X-Session-Id`. (Do not touch `appointment_id` where it's a real Firestore appointment field — only its correlation-id use, which SP2 is removing.)

**Acceptance:** the §7 regression test passes — no `X-Session-Id` header + authenticated user ⇒ `g.session_id` is a UUID ≠ `g.user_id`, and the same UUID is in `Metrics.session_id` and the `X-Session-Id` response header. `grep -rn "session_id\", user_id" backend/` returns nothing.

**Depends on:** SP2 (route rename / appointment_id removal); Task 5.

---

### Task 7 — Wrap `http_request` in `Markers.Http.Request` (replace after_request stopwatch)

**File:** `backend/app.py`

Replace the manual `record_latency("http_request", …)` block in `after_request` with the `http.request` marker. Because Flask's request/response straddle two hooks, open the marker scope manually in `before_request` and finalize in `after_request` (or, simpler and recommended: keep timing via `g.request_start_ms` and emit one marker event from `after_request` by calling `Markers.Http.Request.execute` around a no-op that just records dimensions + sets duration via `scope.add`). Recommended concrete form:

```python
# after_request, replacing the JunoMetrics block (skip /health and SSE as today)
if request.path != "/health" and response.content_type != "text/event-stream":
    duration_ms = (monotonic_ms() - getattr(g, "request_start_ms", monotonic_ms()))
    def _emit(scope):
        JunoContext.from_g(function="http_request").apply(scope)
        scope.add("http_method", request.method)
        scope.add("http_path", request.path)
        scope.add("http_status", str(response.status_code))
        scope.add("duration_ms_observed", round(duration_ms, 1))
        if response.status_code >= 500:
            scope.mark_failed()
    Markers.Http.Request.execute(_emit)
```

Also add `X-Trace-Id` to the response here (Task 9) and keep `X-Session-Id`.

> Note: the marker's own auto-duration measures only the `_emit` body (≈0ms); the *real* request duration is carried as the `duration_ms_observed` dimension. That's fine for http_request because the request spans two hooks. For in-pipeline ops (Task 8) the marker times the actual work, so no `_observed` dimension is needed there.

**Acceptance:** a non-SSE request emits one `operation="http.request"` marker line with `http_status`, `duration_ms_observed`, `function="http_request"`, `session_id`; 5xx responses emit `success=false`.

**Depends on:** Tasks 3–5.

---

### Task 8 — Replace pipeline stopwatch boilerplate with `.execute()` markers

**File:** `backend/routes/simplify_v1_2.py` (the SP2 care_plan route/pipeline)

Set the versions on `g` once at the top of the request handler (before the pipeline), per PRD.md §4.5:

```python
g.care_plan_version = CARE_PLAN_VERSION   # SP1 (or literal "1.2")
g.grading_version   = GRADING_VERSION
g.input_version     = INPUT_VERSION
```

Then convert each step. **Before (today, `simplify_language` step, lines ~356-376):**

```python
yield _sse({"step": 3, "status": "active", "label": STEPS[3]})
juno_logger.log_step("simplify_language", "start")
t0 = monotonic_ms()
try:
    simplified = pipeline.simplify_language_with_term_plan(
        text, term_data["substitution_candidates"],
        term_data["preserve_and_define_terms"], term_data["abbreviations"],
    )
except Exception as exc:
    juno_logger.exception("simplify_v1_2: simplification failed")
    juno_logger.log_step("simplify_language", "error", extra={"error": str(exc)})
    juno_metrics.record_error(type(exc).__name__, "simplify_language", labels={"version": "v1-2"})
    yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
    return
simplify_language_ms = monotonic_ms() - t0
juno_logger.log_step("simplify_language", "done", duration_ms=simplify_language_ms)
metrics.step_durations_ms["simplify_language"] = simplify_language_ms
yield _sse({"step": 3, "status": "done", "label": STEPS[3]})
```

**After (marker wraps timing + outcome + metric + dimensions; one child span for the flame graph):**

```python
yield _sse({"step": 3, "status": "active", "label": STEPS[3]})
try:
    def _do(scope):
        JunoContext.from_g(function="simplify_language").apply(scope)
        scope.add("input_chars", len(text))
        with get_tracer().start_as_current_span("care_plan.simplify_language") as span:
            span.set_attribute("session.id", g.session_id)
            return pipeline.simplify_language_with_term_plan(
                text, term_data["substitution_candidates"],
                term_data["preserve_and_define_terms"], term_data["abbreviations"],
            )
    simplified = Markers.CarePlan.SimplifyLanguage.execute(_do)
except Exception as exc:
    logger.exception("care_plan: simplification failed")   # marker already emitted success=False
    yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
    return
yield _sse({"step": 3, "status": "done", "label": STEPS[3]})
```

Key points the implementer must preserve per step:
- The marker **auto-times** (delete `t0`/`monotonic_ms()` pairs), **auto-sets** success/`OpOutcome` (delete the manual `log_step("...","done"/"error")` and `record_error`/`record_latency` calls), and **auto-emits** the metric+timeline lines via `JunoSink`.
- `metrics.step_durations_ms[...]` (the `Metrics` model field used by the SSE result) is **still wanted** for the result envelope. Keep it by reading the duration off the scope or, simplest, capture it: have `_do` write into a local and assign after — OR (recommended) add a tiny helper `execute_timed(marker, action)` returning `(result, duration_ms)` so the route can still do `metrics.step_durations_ms["simplify_language"] = dur`. Add this helper to `marker.py` as a classmethod `execute_returning_duration` if the `Metrics` envelope must keep per-step durations. **Confirm with SP1/SP2 whether `Metrics.step_durations_ms` is still part of the output contract; if SP1 dropped it, omit this entirely.**
- Steps with a **non-fatal** failure today (`find_medical_terms`, `clarify_actions` fall back instead of returning) must keep falling back: catch inside `_do`, call `scope.mark_failed()`, and return the fallback value so the marker records `Failed` but the pipeline continues.

Apply the same transform to all seven ops:
| Step | Marker | Fatal on error? |
|---|---|---|
| read_input (lines ~474-503) | `Markers.CarePlan.ReadInput` | yes (returns) |
| find_medical_terms (~335-354) | `Markers.CarePlan.FindMedicalTerms` | no (fallback empty terms → `scope.mark_failed()`) |
| simplify_language (~356-376) | `Markers.CarePlan.SimplifyLanguage` | yes |
| clarify_actions (~378-393) | `Markers.CarePlan.ClarifyActions` | no (fallback to `simplified` → `scope.mark_failed()`) |
| structure_note (~395-410) | `Markers.CarePlan.StructureNote` | yes |
| save_output (~518-548) | `Markers.CarePlan.SaveOutput` | no (continues without saved_id → `mark_failed()`) |
| whole pipeline total (~438-442) | `Markers.CarePlan.Pipeline` | wraps the run; replaces `record_latency("simplify_pipeline")` + `record_counter` |

Delete the now-unused `juno_metrics = JunoMetrics()` locals in `run_v1_2_pipeline` and `_generate_stream` and the `juno_logger.log_step(...)` step calls (keep `juno_logger`/`logger` only for free-text `.exception()` context lines that aren't operation-scoped).

**Acceptance:** the route file contains **zero** `monotonic_ms()`-based per-step timing, **zero** `record_latency`/`record_error`/`record_counter` calls, and **zero** `log_step(...)` calls; each of the 7 ops emits exactly one marker event (verified with `InMemorySink` in a route test) carrying `function`, `care_plan_version`, `grading_version`, `input_version`, `session_id`, `user_id`; non-fatal steps emit `success=false` but the pipeline still produces a result. If `Metrics.step_durations_ms` is still in the contract, it is still populated.

**Depends on:** Tasks 1–6; SP1 (version constants); SP2 (the route).

---

### Task 9 — Add `X-Trace-Id` response header + CORS expose

**Files:** `backend/app.py`

1. In `after_request`, after setting `X-Session-Id`, add:
   ```python
   span_ctx = trace.get_current_span().get_span_context()
   if span_ctx and span_ctx.is_valid:
       response.headers["X-Trace-Id"] = format(span_ctx.trace_id, "032x")
   ```
2. Update CORS: `CORS(app, expose_headers=["X-Session-Id", "X-Trace-Id"])`.

**Acceptance:** a normal response carries `X-Trace-Id` (32 hex chars) matching the `jsonPayload.trace_id` of that request's logs; both headers are listed in `Access-Control-Expose-Headers`.

**Depends on:** none (independent of markers).

---

### Task 10 — Multi-version + function logging in `JunoLogger`

**File:** `backend/utils/juno_logger.py`

1. Change `__init__(self, api_version=None)` → `__init__(self, function: str | None = None)`; store `self._function`.
2. In `_base_fields()`: drop `api_version`; add `function` (`self._function`), `care_plan_version`, `grading_version`, `input_version` (each via `_g_field(...)`). Keep `session_id`, `user_id`, `service`, `environment`.
3. `log_step` is now redundant with markers — **deprecate**: keep the method (so non-pipeline callers don't break) but the care_plan route stops calling it (Task 8). Add a docstring line: "Prefer `Markers.*.execute()` for operation timing; use JunoLogger for free-text logs."
4. Update the `app.py` `log_request_start` call to `JunoLogger(function="http_request")`.

**Acceptance:** a care_plan log line has `function`, `care_plan_version`, `grading_version`, `input_version` and **no** `api_version`. `grep -rn "api_version" backend/` returns only deliberate/legacy references (none in `juno_logger.py` or the care_plan route).

**Depends on:** SP1 (version constants), SP2 (route caller updates).

---

### Task 11 — Extend `StructuredJsonFormatter` to serialize the new fields reliably

**File:** `backend/logging_config.py`

1. In `StructuredJsonFormatter.format()`, after `session_id`, copy through a whitelist of known `extra` attributes if present on the record: `user_id, function, care_plan_version, grading_version, input_version, operation, metric, metric_type, duration_ms, success, outcome, step_name, status, http_method, http_path, http_status, http_status_code, total_duration_ms, saved_id, input_chars, error, labels`. (Iterate the list; `getattr(record, k, _SENTINEL)`; include if not sentinel.) This guarantees marker/JunoSink `extra` keys land in `jsonPayload` even though the formatter builds the dict explicitly.
2. Keep the existing `logging.googleapis.com/trace` (full path) and `trace_id`/`span_id` (bare hex) emission unchanged — both are needed for the two working trace queries (PRD §4.6a).

**Acceptance:** a `JunoSink` metric line serialized by the formatter contains `metric:true, metric_type:"marker", operation, duration_ms, success, function, care_plan_version` in `jsonPayload`; a normal log line still contains `trace_id` (hex) and `logging.googleapis.com/trace` (path).

**Depends on:** Tasks 2, 10.

---

### Task 12 — Rewrite `docs/logging.md` (single home)

**File:** `docs/logging.md` (SP3 deletes `utils/LOGGING.md`; do not reference it)

Rewrite/extend to cover, in this order:
1. **The three IDs** — copy the trace_id / span_id / session_id explanation from PRD §4.6 verbatim (the owner asked for this explicitly).
2. **Working Logs Explorer trace queries** — PRD §4.6a queries A/B/C, with query A marked canonical and the "bare hex matches nothing at top level" caveat.
3. **Trace Explorer for a session** — PRD §4.6b: filter `session.id = <id>`, the logs↔trace round-trip buttons.
4. **Metrics Explorer for Juno** — PRD §8.3 step-by-step: select `logging.googleapis.com/user/marker_duration_ms`, group by `operation`, p50/p95/p99; the 3-tile dashboard.
5. **Code-marker usage for devs** — how to wrap an op: `Markers.CarePlan.SimplifyLanguage.execute(lambda s: JunoContext.from_g(function="simplify_language").apply(s) or do_work())`; how to add a new marker (add a leaf to `markers.py`); testing with `InMemorySink`.
6. **Field reference table** — updated: drop `api_version`, add `function`, `care_plan_version`, `grading_version`, `input_version`, `operation`, `outcome`, `success`.
7. **session_id rules** — never a Firebase UID; `X-Session-Id` in/out; `X-Trace-Id` out; when to use which.
8. Update the existing `gcloud logging read` / log-based-metric recipes to the new `metric_type="marker"` selector.

**Acceptance:** `docs/logging.md` answers all six owner questions from PRD §1.3 verbatim, contains the copy-paste working trace queries, the Metrics Explorer + Trace Explorer how-to, and the marker dev guide; no reference to `utils/LOGGING.md` or `api_version`.

**Depends on:** Tasks 1–11 (so the doc matches shipped code).

---

## Summary of what requires you (not a dev agent)

1. **Cloud Console (cannot be coded):** create the 3 log-based metrics (PRD §8.2), build the Metrics Explorer dashboard (§8.3), save the Trace Explorer `session.id` filter (§8.4). Step-by-step lands in `docs/logging.md` (Task 12) — but the clicks are yours.
2. **Deploy config:** set `SERVICE_VERSION` (git SHA) in `.github/workflows/deploy-backend.yml` so version-segmented Trace/metrics aren't flat `unknown` (PRD §8.1).
3. **IAM verify:** confirm Cloud Run runtime SA has `roles/cloudtrace.agent`; check telemetry.py isn't logging an exporter-init warning (PRD §8.5).
4. **Confirm two interfaces before Tasks 8/10:** (a) SP1's version source of truth (module constants vs instance `.version`) for `g.*_version`; (b) whether `Metrics.step_durations_ms` is still in the output contract (decides whether Task 8 keeps per-step duration capture).
5. **Confirm SP3 disposition of `JunoMetrics`/`JunoLogger`** (delete vs deprecated shim) — PRD §9.1–9.2.
