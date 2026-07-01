# PRD: SP07 — Pipeline Consolidation + SSE Retirement

**Sub-project:** SP07
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-29
**Status:** Planning — no implementation started

---

## 1. Problem

### 1a. Duplicate Step Chain

`routes/care_plan.py:251-409` (`run_care_plan_pipeline`) and `care_plan/v1_2/pipeline.py:139-176` (`CarePlanV1_2Pipeline.run()`) both implement the identical five-step orchestration:

```
detect_terms → simplify_language_with_term_plan → clarify_and_action
→ structure_appointment_note → build_glossary_from_simplified_text
→ CarePlan.from_pipeline_result
```

The route copy is the **production path**: `routes/worker.py:30` registers `run_care_plan_pipeline` in `PIPELINES`; `routes/batch.py:40` (`_pipeline_for_version`) returns it. The pipeline's `run()` is **test-only**: its sole caller is `tests/care_plan/test_pipeline_schema.py:70`. Neither path delegates to the other. Any bug fix or step change must be applied twice, and either copy can silently drift.

### 1b. SSE Protocol Carried in a Non-SSE Path

`run_care_plan_pipeline` is a generator that yields `"data: {JSON}\n\n"` strings — the HTTP Server-Sent Events wire format — even though no browser ever reads these strings. The worker (`routes/worker.py:274-283`) consumes them by `json.loads(chunk.removeprefix("data: ").strip())`. This indirection exists because the route was originally a streaming HTTP endpoint; that endpoint (`POST /care_plan`) is now a 410 stub (`routes/care_plan.py:49-55`). The SSE protocol is now dead scaffolding inside a pure internal function.

### 1c. Dead 410 Stubs

Two routes serve only a hardcoded 410 error body and carry no logic:

- `routes/care_plan.py:49-55` — `care_plan_sse_deprecated` (`POST /care_plan`)
- `routes/batch.py:19-25` — `care_plan_batch_sse_deprecated` (`POST /care_plan/batch`)

Note: SP06 renames `batch.py` to `batch_utils.py`; SP07 must coordinate to delete from the renamed file.

### 1d. Flat Files With No Navigation

`routes/care_plan.py` (~408 lines) and `routes/worker.py` (~377 lines) both have zero section-header comments. Finding any function requires reading the entire file.

---

## 2. Goals

1. `care_plan/v1_2/pipeline.py` owns the full step chain. A single method (`run_streaming`) is the canonical per-version orchestration entry point, callable from both the route adapter and tests.
2. `routes/care_plan.py:run_care_plan_pipeline` becomes a **thin adapter** — it calls `run_streaming`, layers Markers/JunoContext instrumentation, computes grading, fires tracing spans, and yields typed events. It contains zero step logic.
3. The worker (`routes/worker.py`) consumes typed event objects from the generator. It no longer parses `"data: "` strings or handles `RESULT_SENTINEL` tuples.
4. Both 410 stub endpoints are deleted.
5. All SSE formatting helpers (`_sse`, `_sse_error`, `_sse_error_rich`) are deleted from `routes/care_plan.py`.
6. Section-header comments are added to `routes/care_plan.py` and `routes/worker.py`.
7. `care_plan/interface.py` (`CarePlanPipeline` ABC) is retained as the version contract, with its docstring updated to reflect the new `run_streaming` interface.

---

## 3. Non-Goals

- No changes to LLM prompts, temperature settings, or model configuration.
- No changes to `utils/markers.py` or the Markers API (`Markers.X.execute(fn)` stays as-is).
- No changes to the Firestore job document schema or `utils/firebase.py`.
- No changes to input-resolution utilities (`_resolve_uploaded_files`, `_fetch_from_gcs`, `_extract_text_from_bytes`, `upload_combined_pdf`). These are shared by `care_plan_jobs.py`, `worker.py`, and `batch_utils.py` and are not duplication — they are shared infrastructure. Extracting them to a shared module is an optional cleanup, flagged [OPEN] in section 9.
- No changes to the frontend job submission or display flow (coordinate with SP10 in section 6).
- No changes to `Grading`, `CarePlan.from_pipeline_result`, or `CarePlanInternal` model shapes.
- No performance or model-quality changes.
- No changes to the `_INPUT_TYPE_MAP` routing or Athena input resolution in `worker.py`.

---

## 4. Architecture Decisions

### 4a. New Typed Event Protocol

Replace the SSE string + sentinel tuple protocol with three typed dataclasses. Define them at the top of `care_plan/v1_2/pipeline.py` (or a new `care_plan/events.py` — see [OPEN] Q3):

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class StepEvent:
    """Emitted before and after each pipeline step."""
    step: int
    status: Literal["active", "done"]
    label: str

@dataclass
class PipelineRunResult:
    """Emitted once at the end of a successful run."""
    care_plan: "CarePlanV1_2"
    term_data: dict          # {substitution_candidates, preserve_and_define_terms, abbreviations}
    simplified: str          # output of simplify step (input to grading scorer)
    clarified: str           # output of clarify step (input to after-score and grading)
    raw_text: str            # original input text

@dataclass
class PipelineStepError:
    """Emitted when a step raises an unrecoverable exception."""
    step: int | None         # None for errors outside any specific step
    exc: Exception
```

These replace all uses of `(Constants.RESULT_SENTINEL, care_plan, grading, text, clarified)` tuples and `"data: {JSON}\n\n"` strings.

### 4b. `CarePlanV1_2Pipeline.run_streaming()` — New Canonical Entry Point

Add to `care_plan/v1_2/pipeline.py`:

```python
from typing import Callable, Generator
# StepEvent, PipelineRunResult, PipelineStepError as above

WrapStepFn = Callable[[int, str, Callable[[], Any]], Any]
# Signature: wrap_step(step_num, step_label, fn) -> fn()
# The adapter provides a version that wraps fn with Markers.
# If None, steps are called directly (used in tests and non-instrumented contexts).

def run_streaming(
    self,
    text: str,
    wrap_step: WrapStepFn | None = None,
) -> Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]:
    """
    Run the full V1.2 pipeline, yielding step progress and the final result.

    The caller (adapter layer) supplies an optional `wrap_step` hook that is
    called around each LLM-heavy step. This lets the adapter attach Markers,
    JunoContext, and tracing spans without the pipeline importing Flask or g.

    Yields:
        StepEvent(step, "active", label)  — immediately before each step
        StepEvent(step, "done", label)    — immediately after each step
        PipelineRunResult(...)            — on success
        PipelineStepError(step, exc)      — on unrecoverable failure (generator returns after this)
    """

    def _call(step: int, label: str, fn: Callable[[], Any]) -> Any:
        if wrap_step is not None:
            return wrap_step(step, label, fn)
        return fn()

    # Step 2: term detection (deterministic, no LLM)
    yield StepEvent(step=2, status="active", label=Constants.STEPS[2])
    try:
        term_data = _call(2, Constants.STEPS[2], lambda: detect_terms(text))
    except Exception as exc:
        logger.exception("pipeline: term detection failed — continuing with empty terms")
        term_data = {"substitution_candidates": [], "preserve_and_define_terms": [], "abbreviations": []}
    yield StepEvent(step=2, status="done", label=Constants.STEPS[2])

    # Step 3: simplify language
    yield StepEvent(step=3, status="active", label=Constants.STEPS[3])
    try:
        simplified = _call(
            3, Constants.STEPS[3],
            lambda: self.simplify_language_with_term_plan(
                text,
                term_data["substitution_candidates"],
                term_data["preserve_and_define_terms"],
                term_data["abbreviations"],
            ),
        )
    except Exception as exc:
        logger.exception("pipeline: simplification failed")
        yield PipelineStepError(step=3, exc=exc)
        return
    yield StepEvent(step=3, status="done", label=Constants.STEPS[3])

    # Step 4: clarify and action
    yield StepEvent(step=4, status="active", label=Constants.STEPS[4])
    try:
        clarified = _call(
            4, Constants.STEPS[4],
            lambda: self.clarify_and_action(simplified, term_data["abbreviations"]),
        )
    except Exception as exc:
        logger.exception("pipeline: clarify step failed — using simplified text")
        clarified = simplified   # non-fatal fallback
    yield StepEvent(step=4, status="done", label=Constants.STEPS[4])

    # Step 5: structure note
    yield StepEvent(step=5, status="active", label=Constants.STEPS[5])
    try:
        structured = _call(
            5, Constants.STEPS[5],
            lambda: self.structure_appointment_note(clarified),
        )
    except Exception as exc:
        logger.exception("pipeline: structuring failed")
        yield PipelineStepError(step=5, exc=exc)
        return
    yield StepEvent(step=5, status="done", label=Constants.STEPS[5])

    terms_glossary = build_glossary_from_simplified_text(
        clarified, term_data["preserve_and_define_terms"]
    )
    result = {
        **structured,
        "terms": terms_glossary,
        "raw": {"text": text, "simplified_text": simplified, "clarified_text": clarified},
    }
    care_plan = CarePlan.from_pipeline_result(Constants.CARE_PLAN_VERSIONS.V1_2.value, result)
    if not isinstance(care_plan, CarePlanV1_2):
        raise TypeError(f"Expected CarePlanV1_2, got {type(care_plan).__name__}")

    yield PipelineRunResult(
        care_plan=care_plan,
        term_data=term_data,
        simplified=simplified,
        clarified=clarified,
        raw_text=text,
    )
```

**Fate of the existing `run()` method** (lines 139-176): Rewrite as a one-liner that calls `run_streaming` without instrumentation:

```python
def run(self, text: str) -> CarePlanV1_2:
    """Run the full pipeline without instrumentation. Used in tests and batch pre-checks."""
    for event in self.run_streaming(text):
        if isinstance(event, PipelineRunResult):
            return event.care_plan
        if isinstance(event, PipelineStepError):
            raise event.exc
    raise RuntimeError("run_streaming completed without yielding a result")
```

This eliminates the duplicate step chain while keeping the existing test (`test_pipeline_schema.py:70`) intact without modification.

### 4c. `run_care_plan_pipeline` — Thin Adapter

Rewrite `routes/care_plan.py:251-409` as a thin adapter. It retains: Markers wiring, JunoContext application, tracing spans, grading, and the typed generator contract. It contains zero step logic.

```python
# Typed events imported from care_plan.v1_2.pipeline (or care_plan.events)
from care_plan.v1_2.pipeline import (
    CarePlanV1_2Pipeline, StepEvent, PipelineRunResult, PipelineStepError
)

# New event types for the route↔worker contract (emitted by this adapter):
@dataclass
class AdapterStepEvent:
    step: int
    status: Literal["active", "done"]
    label: str

@dataclass
class AdapterResult:
    care_plan: CarePlan
    grading: Grading
    raw_text: str
    clarified_text: str

@dataclass
class AdapterError:
    error_data: dict   # rich error dict from build_error_data_from_exc


def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]:
    try:
        try:
            pipeline = CarePlanV1_2Pipeline()
        except Exception as e:
            yield AdapterError(
                error_data=build_error_data(ErrorCode.PIPELINE_INIT_ERROR, str(e))
            )
            return

        # Build the wrap_step hook — attaches Markers, JunoContext, tracing per step.
        _STEP_MARKER_MAP = {
            2: (Markers.CarePlan.FindMedicalTerms, "find_medical_terms", None),
            3: (Markers.CarePlan.SimplifyLanguage, "simplify_language", "care_plan.simplify_language"),
            4: (Markers.CarePlan.ClarifyActions,   "clarify_actions",   "care_plan.clarify_actions"),
            5: (Markers.CarePlan.StructureNote,    "structure_note",    "care_plan.structure_note"),
        }

        def wrap_step(step: int, label: str, fn: Callable[[], Any]) -> Any:
            marker, juno_fn, span_name = _STEP_MARKER_MAP.get(step, (None, None, None))
            if marker is None:
                return fn()

            def _inner(scope):
                JunoContext.from_g(function=juno_fn).apply(scope)
                if step == 3:
                    scope.add("input_chars", len(text))
                if span_name:
                    with get_tracer().start_as_current_span(span_name) as span:
                        try:
                            span.set_attribute("session.id", g.session_id)
                        except (AttributeError, RuntimeError):
                            span.set_attribute("session.id", "")
                        return fn()
                return fn()

            return marker.execute(_inner)

        for event in pipeline.run_streaming(text, wrap_step=wrap_step):
            if isinstance(event, StepEvent):
                yield AdapterStepEvent(step=event.step, status=event.status, label=event.label)

            elif isinstance(event, PipelineStepError):
                yield AdapterError(error_data=build_error_data_from_exc(event.exc))
                return

            elif isinstance(event, PipelineRunResult):
                if grading_enabled:
                    before_score = _score_or_none(text, "before")
                    after_score  = _score_or_none(event.clarified, "after")

                    def _grade(scope):
                        JunoContext.from_g(function="grading").apply(scope)
                        result = build_grading(before_score, text, after_score, event.clarified)
                        scope.add("before_composite", (before_score or {}).get("composite", 0.0))
                        scope.add("after_composite",  (after_score  or {}).get("composite", 0.0))
                        scope.add("grading_method_count", len({e.name for e in result.entries if e.name != "combined"}))
                        return result

                    grading = Markers.Grading.Run.execute(_grade)
                else:
                    grading = Grading(enabled=False)

                def _pipeline_done(scope):
                    JunoContext.from_g(function="pipeline").apply(scope)
                    scope.add("input_chars", len(text))
                    scope.add("source_kind", source_kind)
                    scope.add("grading_enabled", grading_enabled)
                    scope.add("is_batch", is_batch)
                Markers.CarePlan.Pipeline.execute(_pipeline_done)

                yield AdapterResult(
                    care_plan=event.care_plan,
                    grading=grading,
                    raw_text=event.raw_text,
                    clarified_text=event.clarified,
                )

    except Exception as exc:
        def _pipeline_fail(scope):
            JunoContext.from_g(function="pipeline").apply(scope)
            scope.mark_failed()
        Markers.CarePlan.Pipeline.execute(_pipeline_fail)
        logger.exception("care_plan: unexpected pipeline error")
        yield AdapterError(error_data=build_error_data_from_exc(exc))
```

**Functions to delete from `routes/care_plan.py`**:

| Function | Lines | Reason |
|---|---|---|
| `care_plan_sse_deprecated` | 49-55 | 410 stub, no logic |
| `_sse` | 90-92 | SSE formatter, no longer used |
| `_sse_error` | 95-97 | SSE error formatter, no longer used |
| `_sse_error_rich` | 100-109 | SSE rich error formatter, no longer used |

**Functions to retain**:

`upload_combined_pdf`, `ResolvedInput`, `_allowed`, `_extract_text_from_bytes`, `_source_separator`, `_text_artifact_filename`, `_resolve_uploaded_files`, `_fetch_from_gcs`, `_score_or_none`, `_grading_enabled_from_request` — all shared infrastructure, not duplication.

### 4d. Worker — Consume Typed Events

Rewrite the generator-consuming loop in `routes/worker.py:269-303`:

**Before** (parses SSE strings + sentinel tuples):
```python
for chunk in pipeline_fn(text, metrics, grading_enabled, source_kind=source_kind, is_batch=is_batch):
    if isinstance(chunk, tuple) and chunk and chunk[0] == Constants.RESULT_SENTINEL:
        pipeline_result = chunk
        continue
    if isinstance(chunk, str) and chunk.startswith("data: "):
        try:
            payload = json.loads(chunk.removeprefix("data: ").strip())
        except Exception:
            continue
        if payload.get("step") == "error":
            pipeline_error_data = payload.get("error_data") or None
            break
        step = payload.get("step")
        status = payload.get("status")
        if isinstance(step, int) and status == "active" and step != current_stage:
            current_stage = step
            if _check_timeout(current_stage):
                return "", 200
            update_job_stage(job_id, current_stage)
```

**After** (typed event dispatch):
```python
from routes.care_plan import AdapterStepEvent, AdapterResult, AdapterError

for event in pipeline_fn(text, metrics, grading_enabled, source_kind=source_kind, is_batch=is_batch):
    if isinstance(event, AdapterResult):
        pipeline_result = event
    elif isinstance(event, AdapterError):
        pipeline_error_data = event.error_data
        break
    elif isinstance(event, AdapterStepEvent):
        if event.status == "active" and event.step != current_stage:
            current_stage = event.step
            if _check_timeout(current_stage):
                return "", 200
            update_job_stage(job_id, current_stage)
```

Result unpacking (currently `_, care_plan, grading, _raw_text, _clarified_text = pipeline_result`) becomes:
```python
care_plan     = pipeline_result.care_plan
grading       = pipeline_result.grading
```

The `json` import in `worker.py` may be removable after this change if no other usage remains — verify at implementation time.

### 4e. `batch_utils.py` — 410 Stub Deletion + `_pipeline_for_version` Update

After SP06 renames `batch.py` to `batch_utils.py`:

1. Delete the `care_plan_batch_sse_deprecated` route stub (lines 19-25 in current `batch.py`).
2. Update `_pipeline_for_version` return type annotation from `Callable[..., Generator[str | tuple, None, None]]` to `Callable[..., Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]]`.

### 4f. `RESULT_SENTINEL` Retirement

`Constants.RESULT_SENTINEL` (`"__result__"`) is used only to tag the sentinel tuple. Once the worker and adapter both use typed events, this constant is dead. **Do not delete from `constants.py` in SP07** — flag for SP08/SP09 sweep to avoid introducing a risky cross-SP dependency mid-refactor. Remove the import in `routes/care_plan.py` (`RESULT_SENTINEL = Constants.RESULT_SENTINEL`, line 21) once the adapter no longer yields sentinel tuples.

### 4g. Section-Header Comments

Add section-header comments to both flat files. Neither file currently has any.

**`routes/care_plan.py`** — add before each logical block:
```python
# ── Imports & blueprint setup ──────────────────────────────────────────────────
# ── GCS upload helpers ─────────────────────────────────────────────────────────
# ── Input resolution helpers ───────────────────────────────────────────────────
# ── Scoring helpers ────────────────────────────────────────────────────────────
# ── Pipeline adapter ───────────────────────────────────────────────────────────
```

**`routes/worker.py`** — add before each logical block:
```python
# ── Imports & blueprint setup ──────────────────────────────────────────────────
# ── Configuration constants ────────────────────────────────────────────────────
# ── Input resolution ───────────────────────────────────────────────────────────
# ── OIDC token verification ────────────────────────────────────────────────────
# ── Job execution handler ──────────────────────────────────────────────────────
# ── Name derivation ────────────────────────────────────────────────────────────
```

### 4h. `care_plan/interface.py` — ABC Retention

Keep `CarePlanPipeline(ABC)` with `run()` as the abstract method. It documents the version contract and is enforced by `CarePlanV1_2Pipeline(CarePlanPipeline)`. Add `run_streaming` as a non-abstract default that calls `run()` — this provides a default implementation while making it overridable:

```python
# In care_plan/interface.py

class CarePlanPipeline(ABC):
    """
    Contract for all care_plan pipeline versions.

    Each version must implement run(text) returning the typed CarePlan model,
    and should override run_streaming() for instrumented/step-aware execution.
    run_streaming() defaults to calling run() without step events.
    """

    @abstractmethod
    def run(self, text: str) -> "CarePlan":
        """Run the full pipeline; returns typed CarePlan. No instrumentation."""
        pass

    def run_streaming(
        self,
        text: str,
        wrap_step: "WrapStepFn | None" = None,
    ) -> "Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]":
        """
        Default: run() without step events. Subclasses override to yield step progress.
        """
        try:
            care_plan = self.run(text)
            yield PipelineRunResult(
                care_plan=care_plan,
                term_data={},
                simplified="",
                clarified="",
                raw_text=text,
            )
        except Exception as exc:
            yield PipelineStepError(step=None, exc=exc)
```

`CarePlanV1_2Pipeline` overrides `run_streaming` with the full step-by-step implementation from §4b. `run()` becomes the lightweight wrapper from §4b.

### 4i. `batch_dataset` Legacy Branch

`worker.py:36` comment: `# legacy, pre-extracted text`. The `batch_dataset` key in `_INPUT_TYPE_MAP` maps to `"text"` meaning the job doc already contains pre-extracted text. Check whether any live job docs still carry `input_source_kind == "batch_dataset"` before removing the key. Flag as [OPEN] Q6 — if no live usage, remove in SP08 sweep.

---

## 5. API Change Summary

### Worker ↔ Route Contract (Internal, Not HTTP)

| Before | After |
|---|---|
| Generator yields `str` (SSE: `"data: {...}\n\n"`) for step progress | Generator yields `AdapterStepEvent(step, status, label)` |
| Generator yields `str` (SSE: `"data: {step: 'error', error_data: {...}}\n\n"`) for errors | Generator yields `AdapterError(error_data: dict)` |
| Generator yields `tuple` `(RESULT_SENTINEL, care_plan, grading, raw_text, clarified)` | Generator yields `AdapterResult(care_plan, grading, raw_text, clarified_text)` |
| Worker parses `json.loads(chunk.removeprefix("data: "))` | Worker uses `isinstance(event, ...)` dispatch |
| Worker checks `chunk[0] == Constants.RESULT_SENTINEL` | Worker checks `isinstance(event, AdapterResult)` |

**No HTTP API changes.** `POST /care_plan/jobs`, `POST /care_plan/batch/jobs`, `GET /care_plan/datasets/*` are all unchanged. The generator contract is internal (worker → route, not over HTTP).

### Deleted HTTP Routes

| Route | File | Reason |
|---|---|---|
| `POST /care_plan` | `routes/care_plan.py:49-55` | 410 stub, no functionality |
| `POST /care_plan/batch` | `batch_utils.py:19-25` (post SP06 rename) | 410 stub, no functionality |

These endpoints already return 410 in production. Clients that call them already receive errors; deleting the route returns 404 instead of 410. This is acceptable for permanently retired endpoints.

---

## 6. Frontend Change Summary

SP07 makes no changes to the Firestore output shape that the frontend reads. The `CarePlanInternal` envelope (`metrics`, `input`, `grading`, `care_plan`) written by `complete_job` is unchanged. The `care_plan` sub-dict structure (`CarePlanV1_2` fields) is unchanged.

**Coordinate with SP10**: SP10 should confirm that:
1. It does not depend on `POST /care_plan` or `POST /care_plan/batch` (both already 410; their deletion is safe).
2. The `care_plan` field shape in Firestore job docs (`reason_for_visit`, `diagnosis`, `medications`, etc.) remains identical — SP07 does not alter field names or types.
3. The `grading` field shape is unchanged.

If SP10 introduces any frontend change that reads `raw` artifacts (`raw.text`, `raw.simplified_text`, `raw.clarified_text`) from the Firestore job doc, those fields continue to be written by SP07 via the same `CarePlanV1_2.raw: RawArtifacts` field.

---

## 7. Testing

### Tests to Update

**`tests/care_plan/test_pipeline_executors.py`** — currently tests `run_care_plan_pipeline` yielding SSE strings and sentinel tuples. Rewrite for typed events:

- `test_run_care_plan_pipeline_yields_typed_step_events`: assert `AdapterStepEvent` objects are yielded for steps 2-5 with `("active", "done")` pairs.
- `test_run_care_plan_pipeline_yields_adapter_result`: assert final event is `AdapterResult` with `care_plan`, `grading`, `raw_text`, `clarified_text`.
- `test_run_care_plan_pipeline_step_error_yields_adapter_error`: mock `pipeline.run_streaming` to yield `PipelineStepError(step=3, exc=RuntimeError("fail"))`; assert `AdapterError` is yielded.
- Remove `_events_from_chunks` helper (SSE parsing logic no longer needed).

**`tests/utils/test_care_plan_markers.py`** — currently imports and calls `run_care_plan_pipeline`, asserting marker payloads. Tests at lines 108, 149, 217, 260 each do `_exhaust(run_care_plan_pipeline(...))`. Update:
- Change `_exhaust` to accept the new typed generator (currently it skips tuples and parses SSE strings — rewrite to skip non-SSE event objects).
- All marker assertion logic stays the same; only the chunk-inspection helpers change.

**`tests/routes/test_route_rewire.py:47`** — asserts `batch._pipeline_for_version("v1-2") is batch.run_care_plan_pipeline`. This assertion remains valid after SP07 (the function is renamed/rewritten but still registered).

**`tests/care_plan/test_pipeline_schema.py:70`** — calls `pipeline.run("original note")`. Remains valid after SP07 because `run()` is kept as a thin wrapper around `run_streaming()`.

### New Tests to Add

**`tests/care_plan/test_pipeline_streaming.py`** (new):
- `test_run_streaming_yields_step_events_in_order`: mock all three LLM methods; assert step events are `(2,active), (2,done), (3,active), (3,done), (4,active), (4,done), (5,active), (5,done)` followed by `PipelineRunResult`.
- `test_run_streaming_wrap_step_is_called_per_step`: provide a `wrap_step` that records calls; assert it is called once per LLM step (steps 3, 4, 5) with the correct step numbers.
- `test_run_streaming_step3_failure_yields_step_error`: mock `simplify_language_with_term_plan` to raise; assert `PipelineStepError(step=3)` is yielded.
- `test_run_streaming_step4_failure_falls_back_to_simplified`: mock `clarify_and_action` to raise; assert no `PipelineStepError` is yielded and the result's `clarified` equals `simplified`.
- `test_run_streaming_step5_failure_yields_step_error`: mock `structure_appointment_note` to raise; assert `PipelineStepError(step=5)` is yielded.
- `test_run_delegates_to_run_streaming`: assert `pipeline.run(text)` returns the same `CarePlanV1_2` as the `PipelineRunResult.care_plan` from `run_streaming(text)`.

### Manual Verification

1. Submit a `POST /care_plan/jobs` with a real PDF. Confirm the job completes, the Firestore doc has `status: "completed"`, and all five stages are recorded (`stage: 5`).
2. Submit a batch job (`POST /care_plan/batch/jobs`). Confirm individual job docs complete.
3. Verify `POST /care_plan` (deleted route) now returns 404 instead of 410 — confirm no frontend code calls this endpoint.
4. Verify `POST /care_plan/batch` (deleted route) returns 404 — same check.
5. Inspect Cloud Logging / OpenTelemetry traces for a completed job; confirm all five Marker spans and the pipeline-total span are present.

---

## 8. Manual Intervention Required

None. SP07 is a pure code refactor:

- No GCS bucket changes.
- No Cloud Run environment variable changes.
- No Firestore schema migration (job doc fields are unchanged).
- No Cloud Tasks queue changes.
- No deployment configuration changes.

The deleted 410 stub routes return 404 instead after deletion. If any monitoring alert fires on 404s for `/care_plan` or `/care_plan/batch`, those alerts should be suppressed or removed — those endpoints have been permanently retired since the SSE migration.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Exact streaming interface shape: callback (`wrap_step`) vs. generator yielding typed events from the pipeline. | [RESOLVED: `run_streaming(text, wrap_step=None)` where `wrap_step` is an optional callable. Pipeline yields typed `StepEvent`, `PipelineRunResult`, `PipelineStepError`. The `wrap_step` hook lets the adapter layer Markers around each LLM call without the pipeline importing Flask or g. See §4b.] |
| Q2 | Whether `RESULT_SENTINEL` survives SSE retirement. | [RESOLVED: `RESULT_SENTINEL` is retired in concept — SP07 removes its use from `routes/care_plan.py` and `routes/worker.py`. The constant itself is NOT deleted from `utils/constants.py` in SP07 to avoid scope creep. SP08/SP09 sweeps the dead constant.] |
| Q3 | Where to define `StepEvent`, `PipelineRunResult`, `PipelineStepError`, `AdapterStepEvent`, `AdapterResult`, `AdapterError` — in `pipeline.py`, a shared `care_plan/events.py`, or `routes/care_plan.py`. | [OPEN: Preferred option is `care_plan/v1_2/pipeline.py` for pipeline events (`StepEvent`, `PipelineRunResult`, `PipelineStepError`) and `routes/care_plan.py` for adapter events (`AdapterStepEvent`, `AdapterResult`, `AdapterError`). A separate `care_plan/events.py` avoids circular imports if worker needs to import event types; evaluate at implementation time.] |
| Q4 | Whether `interface.py`'s `CarePlanPipeline` ABC should declare `run_streaming` as abstract or provide a default. | [RESOLVED: provide a default implementation that calls `run()` and yields a single `PipelineRunResult`. This keeps ABC backwards-compatible if a future version doesn't need step-level streaming. See §4h.] |
| Q5 | Whether the 404 (vs. 410) behavior after stub deletion causes any monitoring or contract issues. | [OPEN: Confirm with SP10 that no frontend code calls `POST /care_plan` or `POST /care_plan/batch`. If a third-party integration still hits these routes, keep the stubs; otherwise deletion is safe.] |
| Q6 | `batch_dataset` legacy entry in `_INPUT_TYPE_MAP` (`worker.py:36`). | [OPEN: Check whether any Firestore job docs in production still carry `input_source_kind == "batch_dataset"`. If no live jobs use it, remove in SP08/SP09 sweep. SP07 does not change this entry.] |
| Q7 | Frontend impact: whether job result/output shape changes. | [RESOLVED: No shape changes. `CarePlanInternal.to_dict()` output is identical. SP10 reads the same fields. Coordinate with SP10 to confirm no dependency on the now-deleted SSE endpoints.] |
| Q8 | Whether to extract input-resolution helpers (`_resolve_uploaded_files`, `_fetch_from_gcs`, `_extract_text_from_bytes`, `upload_combined_pdf`) to a shared module (e.g., `utils/input_resolution.py`). | [DEFERRED: These functions are shared infrastructure, not duplication. Extraction is a clarity improvement worth doing but out of scope for SP07. Flag for SP08/SP09.] |
| Q9 | SP06 ordering dependency: SP07 deletes `care_plan_batch_sse_deprecated` from what SP06 renames to `batch_utils.py`. | [RESOLVED: SP07 must be implemented after SP06's rename lands, or the deletion must target the pre-rename file name and the rename must be coordinated in the same PR. Prefer running SP06 before SP07 to avoid merge conflicts.] |
| Q10 | Whether `wrap_step` should also be called for the term detection step (step 2), which has its own `Markers.CarePlan.FindMedicalTerms` marker but is deterministic (no LLM). | [RESOLVED: Yes — include step 2 in `_STEP_MARKER_MAP`. The marker records deterministic timing and term counts regardless of LLM usage. `wrap_step` is called for all four mapped steps (2, 3, 4, 5).] |
