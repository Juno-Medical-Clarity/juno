# SP07 Pipeline Consolidation + SSE Retirement — TASKS

## Prerequisites

SP07 retires the dead SSE wire protocol inside the care plan pipeline and makes `CarePlanV1_2Pipeline` the single owner of the five-step orchestration chain. Assumes SP01–SP06 are fully implemented and merged (including SP06's rename of `routes/batch.py` to `routes/batch_utils.py`). All tasks below target the post-SP06 file names.

---

## Tasks

### Task 07.1: Create `models/pipeline_events.py` — typed event dataclasses

**Goal**
Define the three canonical pipeline-layer event types (`StepEvent`, `PipelineRunResult`, `PipelineStepError`) and the three adapter-layer event types (`AdapterStepEvent`, `AdapterResult`, `AdapterError`) in a single shared module inside `models/`. Placing them in `models/` avoids circular imports because both `care_plan/v1_2/pipeline.py` and `routes/worker.py` can import from `models/` without any Flask dependency.

**Files**
- Create: `backend/models/pipeline_events.py`
- Edit: `backend/models/__init__.py` (export the six new types)

**Steps**

1. Create `backend/models/pipeline_events.py` with the following content:

```python
"""
pipeline_events.py — Typed event protocol for the care plan pipeline.

Pipeline-layer events (yielded by CarePlanV1_2Pipeline.iter_steps):
  StepEvent         — before/after each step
  PipelineRunResult — successful completion
  PipelineStepError — unrecoverable step failure

Adapter-layer events (yielded by run_care_plan_pipeline in routes/care_plan.py):
  AdapterStepEvent  — forwarded step progress for the worker
  AdapterResult     — final result carrying care_plan + grading
  AdapterError      — error dict ready for Firestore
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from models.care_plan import CarePlan
    from models.care_plan_versions.v1_2 import CarePlanV1_2
    from models.grading import Grading


# ---------------------------------------------------------------------------
# Pipeline-layer events (care_plan/v1_2/pipeline.py yields these)
# ---------------------------------------------------------------------------

@dataclass
class StepEvent:
    """Emitted immediately before and after each pipeline step."""
    step: int
    status: Literal["active", "done"]
    label: str


@dataclass
class PipelineRunResult:
    """Emitted once at the end of a successful pipeline run."""
    care_plan: CarePlanV1_2
    term_data: dict          # keys: substitution_candidates, preserve_and_define_terms, abbreviations
    simplified: str          # output of simplify step; input to grading scorer
    clarified: str           # output of clarify step; input to after-score and grading
    raw_text: str            # original input text


@dataclass
class PipelineStepError:
    """Emitted when a step raises an unrecoverable exception. Generator stops after this."""
    step: int | None         # None for errors that occur outside any specific step
    exc: Exception


# ---------------------------------------------------------------------------
# Adapter-layer events (routes/care_plan.py yields these to routes/worker.py)
# ---------------------------------------------------------------------------

@dataclass
class AdapterStepEvent:
    """Forwarded step progress event for the worker's stage-tracking loop."""
    step: int
    status: Literal["active", "done"]
    label: str


@dataclass
class AdapterResult:
    """Final result from the adapter; consumed by the worker to complete the job."""
    care_plan: CarePlan
    grading: Grading
    raw_text: str
    clarified_text: str


@dataclass
class AdapterError:
    """Rich error dict ready to pass directly to fail_job()."""
    error_data: dict
```

2. In `backend/models/__init__.py`, add an import block after the existing imports:

```python
from .pipeline_events import (
    StepEvent,
    PipelineRunResult,
    PipelineStepError,
    AdapterStepEvent,
    AdapterResult,
    AdapterError,
)
```

And add all six names to `__all__`.

**Acceptance**
- `from models.pipeline_events import StepEvent, PipelineRunResult, PipelineStepError, AdapterStepEvent, AdapterResult, AdapterError` succeeds in a plain Python interpreter (no Flask context needed).
- `python -c "from models import AdapterResult"` succeeds from `backend/`.
- No circular import errors (`python -c "import models"` from `backend/`).

**Commit**
```
feat(sp07): add models/pipeline_events.py with typed pipeline and adapter event dataclasses
```

---

### Task 07.2: Add `iter_steps()` to `CarePlanV1_2Pipeline` and rewrite `run()` as a thin wrapper

**Goal**
Add the new canonical step-by-step generator method `iter_steps()` to `CarePlanV1_2Pipeline`. This replaces the duplicated step chain in `routes/care_plan.py`. The existing `run()` method is rewritten as a three-line wrapper that calls `iter_steps()` — it no longer duplicates step logic. The name `iter_steps` is chosen because it honestly describes what the method does (iterates over steps); there is no HTTP streaming of any kind.

> Note: The PRD calls this method `run_streaming`. It has been renamed to `iter_steps` throughout SP07 to eliminate the word "streaming" from a method that communicates purely via in-process Python generators.

**Files**
- Edit: `backend/care_plan/v1_2/pipeline.py`

**Steps**

1. Add the following imports at the top of `pipeline.py` (after existing imports):

```python
from typing import Any, Callable, Generator
from models.pipeline_events import (
    StepEvent,
    PipelineRunResult,
    PipelineStepError,
)

WrapStepFn = Callable[[int, str, Callable[[], Any]], Any]
```

2. Add the `iter_steps` method to `CarePlanV1_2Pipeline` (insert before the existing `run()` method):

```python
def iter_steps(
    self,
    text: str,
    wrap_step: WrapStepFn | None = None,
) -> Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]:
    """
    Run the full V1.2 pipeline, yielding step progress and the final result.

    Yields StepEvent(step, "active") before each step and StepEvent(step, "done")
    after each step. On success, yields a single PipelineRunResult. On an
    unrecoverable step failure, yields PipelineStepError and returns.

    Args:
        text:      Plain text to process.
        wrap_step: Optional hook — called as wrap_step(step_num, label, fn) and
                   must return fn(). The adapter uses this to attach Markers,
                   JunoContext, and tracing spans without the pipeline importing
                   Flask or g. If None, steps are called directly.
    """

    def _call(step: int, label: str, fn: Callable[[], Any]) -> Any:
        if wrap_step is not None:
            return wrap_step(step, label, fn)
        return fn()

    # Step 2: term detection (deterministic, no LLM)
    yield StepEvent(step=2, status="active", label=Constants.STEPS[2])
    try:
        term_data = _call(2, Constants.STEPS[2], lambda: detect_terms(text))
    except Exception:
        logger.exception("pipeline: term detection failed — continuing with empty terms")
        term_data = {
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        }
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
    except Exception:
        logger.exception("pipeline: clarify step failed — using simplified text")
        clarified = simplified   # non-fatal: fall back to simplified
    yield StepEvent(step=4, status="done", label=Constants.STEPS[4])

    # Step 5: structure appointment note
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
        "raw": {
            "text": text,
            "simplified_text": simplified,
            "clarified_text": clarified,
        },
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

3. Replace the body of the existing `run()` method (lines 139–176) with a thin three-line delegation:

```python
def run(self, text: str) -> CarePlanV1_2:
    """Run the full pipeline without instrumentation. Used in tests and batch pre-checks."""
    for event in self.iter_steps(text):
        if isinstance(event, PipelineRunResult):
            return event.care_plan
        if isinstance(event, PipelineStepError):
            raise event.exc
    raise RuntimeError("iter_steps completed without yielding a result")
```

4. Remove the now-unused import of `build_glossary_from_simplified_text` from the `run()` path — it is still used inside `iter_steps`, so keep it in the module-level imports. Remove `detect_terms` from module-level imports only if it is no longer called at module scope (it is now called inside `iter_steps`'s lambda, so keep it).

**Acceptance**
- `python -c "from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline"` succeeds.
- The existing test `tests/care_plan/test_pipeline_schema.py::test_run_returns_care_plan_model_without_internal_scores` passes without modification (calls `pipeline.run("original note")`).
- `iter_steps` is visible as a method: `assert hasattr(CarePlanV1_2Pipeline, 'iter_steps')`.

**Commit**
```
feat(sp07): add CarePlanV1_2Pipeline.iter_steps() and rewrite run() as a thin wrapper
```

---

### Task 07.3: Update `care_plan/interface.py` — add `iter_steps` default to ABC

**Goal**
Update the `CarePlanPipeline` ABC to declare `iter_steps` as a non-abstract default that calls `run()`. Future pipeline versions that do not need step-level granularity inherit a working default; `CarePlanV1_2Pipeline` overrides it with the full implementation added in Task 07.2.

**Files**
- Edit: `backend/care_plan/interface.py`

**Steps**

1. Add the following imports to `interface.py`:

```python
from typing import TYPE_CHECKING, Generator, Any, Callable

if TYPE_CHECKING:
    from models.pipeline_events import StepEvent, PipelineRunResult, PipelineStepError
    WrapStepFn = Callable[[int, str, Callable[[], Any]], Any]
```

2. Update the class docstring and add the `iter_steps` default method:

```python
class CarePlanPipeline(ABC):
    """
    Contract for all care plan pipeline versions.

    Each version must implement run(text) returning the typed CarePlan model.
    Versions that support step-level progress should override iter_steps();
    the default falls back to run() and yields a single PipelineRunResult.
    """

    @abstractmethod
    def run(self, text: str) -> "CarePlan":
        """Run the full pipeline; returns typed CarePlan. No instrumentation."""
        pass

    def iter_steps(
        self,
        text: str,
        wrap_step: "WrapStepFn | None" = None,
    ) -> "Generator[StepEvent | PipelineRunResult | PipelineStepError, None, None]":
        """
        Default: delegates to run() without emitting step events.
        Subclasses override this to yield StepEvent progress.
        """
        from models.pipeline_events import PipelineRunResult, PipelineStepError
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

> Note: The `from models.pipeline_events import ...` is a local import inside the method body to avoid a circular import at module load time (interface.py is imported by pipeline.py which is imported by models/).

**Acceptance**
- `from care_plan.interface import CarePlanPipeline` succeeds.
- A minimal subclass that only implements `run()` can be instantiated and `iter_steps()` returns a generator that yields `PipelineRunResult`.
- `tests/care_plan/test_pipeline_interface.py` passes (read it first and update any assertions about the ABC's interface if needed).

**Commit**
```
feat(sp07): add iter_steps() default to CarePlanPipeline ABC
```

---

### Task 07.4: Rewrite `run_care_plan_pipeline` as a thin adapter in `routes/care_plan.py`

**Goal**
Replace the ~160-line `run_care_plan_pipeline` function (which currently contains all five step bodies, SSE formatting, and Marker wiring) with a thin adapter that:
- Instantiates `CarePlanV1_2Pipeline`
- Builds a `wrap_step` hook that attaches Markers, JunoContext, and tracing spans
- Calls `pipeline.iter_steps(text, wrap_step=wrap_step)` and dispatches on typed events
- Yields `AdapterStepEvent`, `AdapterResult`, or `AdapterError`
- Contains zero step logic

Also delete the four SSE helpers (`_sse`, `_sse_error`, `_sse_error_rich`, and the `care_plan_sse_deprecated` 410 stub route) and remove the dead `RESULT_SENTINEL` import. Add section-header comments to the file.

**Files**
- Edit: `backend/routes/care_plan.py`

**Steps**

1. Remove the `POST /care_plan` stub route (lines 49–55, `care_plan_sse_deprecated`).

2. Remove the three SSE helper functions:
   - `_sse` (currently around line 90–92)
   - `_sse_error` (currently around line 95–97)
   - `_sse_error_rich` (currently around line 100–109)

3. Remove the `RESULT_SENTINEL` assignment on line 21 (`RESULT_SENTINEL = Constants.RESULT_SENTINEL`). Also remove `RESULT_SENTINEL` from the `from utils.constants import Constants` usage if it was the only reason for that line (keep `Constants` itself; it is used for other constants in the file).

4. Remove the `json` import if it is now unused (it was only used by `_sse`).

5. Remove the `detect_terms` import from the module-level imports — after the rewrite, term detection is called inside `pipeline.iter_steps()`, not directly in this file. Also remove `build_glossary_from_simplified_text` from the module-level imports for the same reason. Verify no other call site in this file references these before removing.

6. Add imports for the new typed events and the pipeline:

```python
from models.pipeline_events import (
    StepEvent,
    PipelineRunResult,
    PipelineStepError,
    AdapterStepEvent,
    AdapterResult,
    AdapterError,
)
```

(`CarePlanV1_2Pipeline` is already imported.)

7. Replace the body of `run_care_plan_pipeline` entirely with the thin adapter. The signature remains identical:

```python
def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]:
    """
    Thin adapter: wraps CarePlanV1_2Pipeline.iter_steps() with Markers, JunoContext,
    and tracing spans. Yields typed AdapterStepEvent, AdapterResult, or AdapterError.
    Contains zero step logic.
    """
    try:
        try:
            pipeline = CarePlanV1_2Pipeline()
        except Exception as e:
            yield AdapterError(
                error_data=build_error_data_from_exc(e)
            )
            return

        # Map step numbers to their Marker, JunoContext function name, and span name.
        # Step 2 (term detection) is deterministic but still tracked via its Marker.
        _STEP_MARKER_MAP = {
            2: (Markers.CarePlan.FindMedicalTerms, "find_medical_terms", None),
            3: (Markers.CarePlan.SimplifyLanguage, "simplify_language", "care_plan.simplify_language"),
            4: (Markers.CarePlan.ClarifyActions,   "clarify_actions",   "care_plan.clarify_actions"),
            5: (Markers.CarePlan.StructureNote,    "structure_note",    "care_plan.structure_note"),
        }

        def wrap_step(step: int, label: str, fn):
            marker, juno_fn, span_name = _STEP_MARKER_MAP.get(step, (None, None, None))
            if marker is None:
                return fn()

            def _inner(scope):
                JunoContext.from_g(function=juno_fn).apply(scope)
                if step == 2:
                    # Record term counts after detect_terms returns (set inside iter_steps).
                    pass
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

        for event in pipeline.iter_steps(text, wrap_step=wrap_step):
            if isinstance(event, StepEvent):
                yield AdapterStepEvent(
                    step=event.step, status=event.status, label=event.label
                )

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

> Note: The `term_count` and `substitution_count` dimensions that were previously recorded inside `_find` in the old adapter are now recorded inside `iter_steps()` via the `wrap_step` hook's `_inner` scope. The `wrap_step` for step 2 receives `fn = lambda: detect_terms(text)`; after `fn()` returns, the scope only has access to what the caller adds. To preserve these dimensions, update the `wrap_step` for step 2 to accept and record them: after `fn()` returns its `term_data`, extract counts and call `scope.add("term_count", ...)` and `scope.add("substitution_count", ...)`. Update the lambda in `_inner` to capture the result and add dimensions:

```python
def _inner(scope):
    JunoContext.from_g(function=juno_fn).apply(scope)
    result = fn()
    if step == 2:
        substitution_count = len((result or {}).get("substitution_candidates", []))
        preserve_count = len((result or {}).get("preserve_and_define_terms", []))
        scope.add("term_count", substitution_count + preserve_count)
        scope.add("substitution_count", substitution_count)
    if step == 3:
        scope.add("input_chars", len(text))
    if span_name:
        with get_tracer().start_as_current_span(span_name) as span:
            try:
                span.set_attribute("session.id", g.session_id)
            except (AttributeError, RuntimeError):
                span.set_attribute("session.id", "")
        return result
    return result
```

Wait — `fn()` is called by `iter_steps` via `_call`, and `wrap_step` wraps it, so `wrap_step` must call `fn()` and return its value. The `_inner` scope receives the marker's scope argument, calls `fn()` once inside it, records dimensions, then returns the result. The tracing span must wrap the actual `fn()` call. Revise step 2's `_inner` to call `fn()` directly and record dimensions from the return value.

8. Add section-header comments to the file before each logical block:

```python
# ── Imports & blueprint setup ──────────────────────────────────────────────────
# ── GCS upload helpers ─────────────────────────────────────────────────────────
# ── Input resolution helpers ───────────────────────────────────────────────────
# ── Scoring helpers ────────────────────────────────────────────────────────────
# ── Pipeline adapter ───────────────────────────────────────────────────────────
```

**Acceptance**
- `from routes.care_plan import run_care_plan_pipeline, AdapterStepEvent, AdapterResult, AdapterError` succeeds.
- `_sse`, `_sse_error`, `_sse_error_rich`, and `care_plan_sse_deprecated` are absent from the file (`grep -n "_sse\|care_plan_sse_deprecated" routes/care_plan.py` returns nothing).
- `RESULT_SENTINEL` is absent from this file.
- The source-level assertions in `tests/utils/test_care_plan_markers.py` still pass (they check for `Markers.CarePlan`, `Markers.Grading.Run`, `CARE_PLAN_VERSION`, `GRADING_VERSION`, `INPUT_VERSION`, `is_batch`, `source_kind`, `term_count`, `substitution_count`, `file_count`, `file_types`). Verify these strings still appear in the rewritten file.

**Commit**
```
feat(sp07): rewrite run_care_plan_pipeline as thin adapter yielding typed events; delete SSE helpers and 410 stub
```

---

### Task 07.5: Rewrite the worker's pipeline-consuming loop to use typed events

**Goal**
Replace the SSE-string-parsing + sentinel-tuple-unpacking loop in `routes/worker.py` (lines 269–312) with a typed `isinstance` dispatch loop. Remove the `json` import if it has no other usages after this change. Add section-header comments to the file.

**Files**
- Edit: `backend/routes/worker.py`

**Steps**

1. Add the typed event imports to the top of `worker.py`:

```python
from routes.care_plan import (
    run_care_plan_pipeline,
    _fetch_from_gcs,
    _extract_text_from_bytes,
    AdapterStepEvent,
    AdapterResult,
    AdapterError,
)
```

(The first three are already imported; add the three new names.)

2. Replace the pipeline-consuming loop (currently lines 269–292 in `execute_job`):

**Before:**
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

**After:**
```python
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

3. Replace the result-unpacking line (currently line 312):

**Before:**
```python
_, care_plan, grading, _raw_text, _clarified_text = pipeline_result
```

**After:**
```python
care_plan = pipeline_result.care_plan
grading   = pipeline_result.grading
```

4. Update the `pipeline_result is None` guard check: it remains structurally the same; `pipeline_result` is now typed as `AdapterResult | None` instead of `tuple | None`. No logic change needed.

5. Update the error-data guard (currently lines 294–303):

**Before:**
```python
if pipeline_error_data is not None:
    if pipeline_error_data.get("code") or pipeline_error_data.get("message"):
        fail_job(job_id, pipeline_error_data)
    else:
        fail_job(job_id, _build_error_data(
            PipelineErrorCode.UNKNOWN_ERROR, "Pipeline failed without an error message"
        ))
    return "", 200
```

This logic stays identical — `pipeline_error_data` is still a `dict` (the `AdapterError.error_data` field). No change needed here.

6. Remove the `json` import at the top of `worker.py` if no other usage of `json` remains in the file. Search for `json.` in the file first; if found elsewhere, keep the import.

7. Add section-header comments to `worker.py` before each logical block:

```python
# ── Imports & blueprint setup ──────────────────────────────────────────────────
# ── Configuration constants ────────────────────────────────────────────────────
# ── Input resolution ───────────────────────────────────────────────────────────
# ── OIDC token verification ────────────────────────────────────────────────────
# ── Job execution handler ──────────────────────────────────────────────────────
# ── Name derivation ────────────────────────────────────────────────────────────
```

**Acceptance**
- `from routes.worker import execute_job` succeeds.
- `"data: "` does not appear in `worker.py` (`grep "data: " routes/worker.py` returns nothing).
- `RESULT_SENTINEL` does not appear in `worker.py`.
- `json.loads` does not appear in `worker.py` (or if `json` is still imported for another reason, that reason is documented with a comment).

**Commit**
```
feat(sp07): rewrite worker pipeline loop to consume typed AdapterStepEvent/AdapterResult/AdapterError
```

---

### Task 07.6: Delete the `POST /care_plan/batch` 410 stub from `routes/batch_utils.py`

**Goal**
Delete the `care_plan_batch_sse_deprecated` 410 stub route and update the `_pipeline_for_version` return type annotation to reflect the new typed generator.

> Note: This task targets `routes/batch_utils.py` — the post-SP06 name. If the file is still named `batch.py` at implementation time, apply changes there instead.

**Files**
- Edit: `backend/routes/batch_utils.py` (post-SP06 name; may still be `routes/batch.py`)

**Steps**

1. Delete the `care_plan_batch_sse_deprecated` function and its route decorator (currently lines 19–25 of `batch.py`):

```python
@batch_bp.route("/care_plan/batch", methods=["POST"])
def care_plan_batch_sse_deprecated():
    """Deprecated SSE batch endpoint — use POST /care_plan/batch/jobs instead."""
    from flask import jsonify
    return jsonify({
        "error": "This SSE endpoint has been removed. Use POST /care_plan/batch/jobs instead."
    }), 410
```

2. Update the return type annotation of `_pipeline_for_version`:

**Before:**
```python
def _pipeline_for_version(version: str) -> Callable[..., Generator[str | tuple, None, None]]:
```

**After:**
```python
def _pipeline_for_version(version: str) -> Callable[..., Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]]:
```

Add the import for the three adapter types at the top of the file:

```python
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
```

3. Verify that `test_route_rewire.py::test_routes_package_registers_care_plan_blueprints_and_new_paths_only` still expects `/care_plan/batch` in `expected_care_plan_rules`. The route `/care_plan/batch` is registered by `batch_jobs.py` (the `POST /care_plan/batch/jobs` handler registers a blueprint that includes this prefix — confirm). If `test_route_rewire.py` currently expects `/care_plan/batch` as a rule (meaning the 410 stub is the only route providing this rule), then remove `/care_plan/batch` from `expected_care_plan_rules` in that test. Read the test carefully before deciding.

**Acceptance**
- `care_plan_batch_sse_deprecated` does not appear anywhere in the file.
- `from routes.batch_utils import _pipeline_for_version` (or `from routes.batch import _pipeline_for_version`) succeeds.
- `test_batch_route_uses_care_plan_pipeline_and_save_helper_surface` in `test_route_rewire.py` passes.

**Commit**
```
feat(sp07): delete POST /care_plan/batch 410 stub and update _pipeline_for_version return type
```

---

### Task 07.7: Rewrite `tests/care_plan/test_pipeline_executors.py` for typed events

**Goal**
The existing test asserts SSE string events and a `__result__` sentinel tuple. Rewrite it to assert typed `AdapterStepEvent` and `AdapterResult` objects. Remove the `_events_from_chunks` SSE-parsing helper.

**Files**
- Edit: `backend/tests/care_plan/test_pipeline_executors.py`

**Steps**

1. Remove the `import json` and `_events_from_chunks` helper function — they parse SSE strings that no longer exist.

2. Add imports for the new typed events:

```python
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
```

3. Rename (or replace) the existing test to:

```python
@patch("routes.care_plan.score_text", ...)  # keep existing patch args
@patch("routes.care_plan.build_glossary_from_simplified_text", return_value={})
@patch("routes.care_plan.detect_terms", return_value={...})  # keep existing
@patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline())
def test_run_care_plan_pipeline_yields_typed_step_events(_pipeline, _detect_terms, _glossary, _score):
    metrics = Metrics.start(session_id="session-1", pipeline_version="v1-2", input_type="text")

    events = list(care_plan_module.run_care_plan_pipeline(
        "plain note", metrics, grading_enabled=False
    ))

    step_events = [e for e in events if isinstance(e, AdapterStepEvent)]
    assert [(e.step, e.status) for e in step_events] == [
        (2, "active"), (2, "done"),
        (3, "active"), (3, "done"),
        (4, "active"), (4, "done"),
        (5, "active"), (5, "done"),
    ]
```

4. Add a second test for `AdapterResult`:

```python
@patch("routes.care_plan.score_text", ...)
@patch("routes.care_plan.build_glossary_from_simplified_text", return_value={})
@patch("routes.care_plan.detect_terms", return_value={...})
@patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FakePipeline())
def test_run_care_plan_pipeline_yields_adapter_result(_pipeline, _detect_terms, _glossary, _score):
    from unittest.mock import patch as mpatch
    metrics = Metrics.start(session_id="session-2", pipeline_version="v1-2", input_type="text")

    events = list(care_plan_module.run_care_plan_pipeline(
        "plain note", metrics, grading_enabled=False
    ))

    result_events = [e for e in events if isinstance(e, AdapterResult)]
    assert len(result_events) == 1
    result = result_events[0]
    assert result.raw_text == "plain note"
    assert result.care_plan is not None
    assert isinstance(result.grading, Grading)
```

5. Add a third test for step errors:

```python
def test_run_care_plan_pipeline_step_error_yields_adapter_error():
    from unittest.mock import MagicMock, patch
    from models.pipeline_events import PipelineStepError

    metrics = Metrics.start(session_id="session-3", pipeline_version="v1-2", input_type="text")

    class FailingPipeline:
        def iter_steps(self, text, wrap_step=None):
            yield PipelineStepError(step=3, exc=RuntimeError("fail"))

    with patch("routes.care_plan.CarePlanV1_2Pipeline", return_value=FailingPipeline()):
        events = list(care_plan_module.run_care_plan_pipeline(
            "text", metrics, grading_enabled=False
        ))

    error_events = [e for e in events if isinstance(e, AdapterError)]
    assert len(error_events) == 1
```

> Note: The `FakePipeline` in the existing test implements `simplify_language_with_term_plan`, `clarify_and_action`, and `structure_appointment_note` as separate methods called by the old adapter. After the rewrite, the adapter calls `pipeline.iter_steps()` — so `FakePipeline` must implement `iter_steps()` instead of (or in addition to) the individual step methods. Update `FakePipeline` accordingly, or replace it with a mock that yields appropriate `PipelineRunResult` events.

**Acceptance**
- All tests in `test_pipeline_executors.py` pass.
- `_events_from_chunks` does not appear in the file.
- `"__result__"` does not appear in the file.
- `"data: "` does not appear in the file.

**Commit**
```
test(sp07): rewrite test_pipeline_executors.py for typed AdapterStepEvent/AdapterResult/AdapterError
```

---

### Task 07.8: Update `tests/utils/test_care_plan_markers.py` for typed events

**Goal**
The marker tests call `_exhaust(run_care_plan_pipeline(...))` and rely on it not crashing when the generator yields mixed chunks. After the rewrite, the generator yields typed objects — `_exhaust` needs no change (it already just calls `list(gen)`), but the patches applied in each test must be updated: they currently patch `routes.care_plan.detect_terms` and `routes.care_plan.build_glossary_from_simplified_text` directly, but after the rewrite those are called inside `pipeline.iter_steps()`, not in the adapter. Update the patches to go through the pipeline mock.

**Files**
- Edit: `backend/tests/utils/test_care_plan_markers.py`

**Steps**

1. Read the current test file carefully (already done — lines 104–302). Identify that the four InMemorySink tests (lines 104, 145, 213, 256) each patch:
   - `routes.care_plan.CarePlanV1_2Pipeline` — returns a `pipeline_stub` `MagicMock`
   - `routes.care_plan.detect_terms` — direct patch (now unreachable via adapter)
   - `routes.care_plan.build_glossary_from_simplified_text` — direct patch (unreachable)
   - `routes.care_plan._score_or_none` — still in adapter, keep this patch
   - `routes.care_plan.build_grading` — still in adapter, keep this patch
   - `routes.care_plan.CarePlan.from_pipeline_result` — now called inside `iter_steps()`, no longer in adapter

2. After the rewrite, `CarePlanV1_2Pipeline` is mocked by returning a `MagicMock` stub. The adapter will call `stub.iter_steps(text, wrap_step=...)`. The stub's `iter_steps` must yield a `PipelineRunResult`. Update `_make_pipeline_stub()` to configure `iter_steps` to return a generator:

```python
def _make_pipeline_stub():
    from models.pipeline_events import PipelineRunResult, StepEvent
    from unittest.mock import MagicMock

    stub = MagicMock()
    care_plan_mock = MagicMock()

    def fake_iter_steps(text, wrap_step=None):
        for step in (2, 3, 4, 5):
            yield StepEvent(step=step, status="active", label=f"Step {step}")
            if wrap_step is not None:
                wrap_step(step, f"Step {step}", lambda: None)
            yield StepEvent(step=step, status="done", label=f"Step {step}")
        yield PipelineRunResult(
            care_plan=care_plan_mock,
            term_data={
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            },
            simplified="simplified text",
            clarified="clarified text",
            raw_text=text,
        )

    stub.iter_steps.side_effect = fake_iter_steps
    return stub
```

3. Remove the `patch("routes.care_plan.detect_terms", ...)` and `patch("routes.care_plan.build_glossary_from_simplified_text", ...)` and `patch("routes.care_plan.CarePlan.from_pipeline_result", ...)` context managers from all four InMemorySink tests — these are no longer in the adapter's code path.

4. The `_exhaust` helper (currently `return list(gen)`) needs no change.

5. The source-level assertion tests (lines 17–60) check for strings in `routes/care_plan.py` source. Verify these strings still appear after the rewrite:
   - `Markers.CarePlan` — yes, in `wrap_step`
   - `Markers.Grading.Run` — yes, in `PipelineRunResult` branch
   - `CARE_PLAN_VERSION` — check; if removed from the file, remove this assertion
   - `GRADING_VERSION` — same
   - `INPUT_VERSION` — same
   - `is_batch`, `source_kind`, `term_count`, `substitution_count`, `file_count`, `file_types` — verify each appears in the new file; update assertions that no longer hold. `term_count` and `substitution_count` move into `wrap_step`'s `_inner` for step 2, so they still appear. `file_count` and `file_types` are in `_resolve_uploaded_files` (unchanged). Keep those assertions.

6. The test `test_batch_passes_is_batch_true_and_source_kind` on line 298 reads `routes/batch.py` by name. After SP06 renames it to `batch_utils.py`, update the path reference:

```python
batch_src = pathlib.Path(__file__).parent.parent.parent / "routes" / "batch_utils.py"
```

**Acceptance**
- All tests in `test_care_plan_markers.py` pass.
- No test patches `routes.care_plan.detect_terms` or `routes.care_plan.build_glossary_from_simplified_text` (those are now internal to `iter_steps`).

**Commit**
```
test(sp07): update test_care_plan_markers.py for typed pipeline events and iter_steps adapter
```

---

### Task 07.9: Update `tests/routes/test_worker.py` for typed events

**Goal**
The worker tests currently have `fake_pipeline` functions that yield SSE strings and sentinel tuples. Rewrite those fakes to yield typed `AdapterStepEvent`, `AdapterResult`, and `AdapterError` objects.

**Files**
- Edit: `backend/tests/routes/test_worker.py`

**Steps**

1. Add import for typed events:

```python
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
```

2. Update `test_happy_path_completes_job`: the existing `fake_pipeline` yields a sentinel tuple. Replace with:

```python
def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
    yield AdapterStepEvent(step=2, status="active", label="Terms")
    yield AdapterStepEvent(step=2, status="done", label="Terms")
    yield AdapterResult(
        care_plan=care_plan_mock,
        grading=grading_mock,
        raw_text=text,
        clarified_text="clarified",
    )
```

Remove `result_tuple = (Constants.RESULT_SENTINEL, ...)` and the `from utils.constants import Constants` import if it is only used for `RESULT_SENTINEL` in this test.

3. Update `test_pipeline_error_fails_job`: currently yields an SSE error string. Replace with:

```python
def fake_pipeline_error(text, metrics, grading_enabled, source_kind="text", is_batch=False):
    yield AdapterError(error_data={
        "code": "PIPELINE_ERROR",
        "message": "Pipeline error",
        "details": "Pipeline exploded",
        "timestamp": "2026-06-22T00:00:00+00:00",
        "path": "/care_plan",
    })
```

4. Update `test_timeout_fails_job_with_job_timeout_code`: currently yields an SSE step string. Replace with:

```python
def fake_pipeline_slow(text, metrics, grading_enabled, source_kind="text", is_batch=False):
    yield AdapterStepEvent(step=2, status="active", label="Terms")
```

5. Check the rest of `test_worker.py` for any other pipeline fakes that yield SSE strings or sentinel tuples and update each one similarly.

**Acceptance**
- All tests in `test_worker.py` pass.
- `"data: "` does not appear in `test_worker.py`.
- `RESULT_SENTINEL` does not appear in `test_worker.py`.
- `json.dumps({"step": "error"` does not appear in `test_worker.py`.

**Commit**
```
test(sp07): update test_worker.py to use typed AdapterStepEvent/AdapterResult/AdapterError fakes
```

---

### Task 07.10: Add new test file `tests/care_plan/test_pipeline_streaming.py`

**Goal**
Add unit tests that directly exercise `CarePlanV1_2Pipeline.iter_steps()` — step event ordering, `wrap_step` invocation, per-step failure modes, and `run()` delegation.

**Files**
- Create: `backend/tests/care_plan/test_pipeline_streaming.py`

**Steps**

Create the file with the following tests:

```python
"""
Tests for CarePlanV1_2Pipeline.iter_steps() — the canonical step-by-step generator.
"""
import pytest
from unittest.mock import MagicMock, patch
from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
from models.pipeline_events import StepEvent, PipelineRunResult, PipelineStepError
from models.care_plan_versions.v1_2 import CarePlanV1_2


def _make_pipeline(monkeypatch, pipeline_module):
    """Return a CarePlanV1_2Pipeline with all LLM methods mocked."""
    p = CarePlanV1_2Pipeline.__new__(CarePlanV1_2Pipeline)
    p.simplify_language_with_term_plan = MagicMock(return_value="simplified")
    p.clarify_and_action = MagicMock(return_value="clarified")
    p.structure_appointment_note = MagicMock(return_value={
        "doc_type": "care_plan",
        "version": "1.2",
        "summary": "summary",
    })
    monkeypatch.setattr(pipeline_module, "detect_terms", lambda text: {
        "substitution_candidates": [],
        "preserve_and_define_terms": [],
        "abbreviations": [],
    })
    monkeypatch.setattr(pipeline_module, "build_glossary_from_simplified_text",
                        lambda *a: {})
    return p


def test_iter_steps_yields_step_events_in_order(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)

    events = list(p.iter_steps("input text"))

    step_events = [e for e in events if isinstance(e, StepEvent)]
    assert [(e.step, e.status) for e in step_events] == [
        (2, "active"), (2, "done"),
        (3, "active"), (3, "done"),
        (4, "active"), (4, "done"),
        (5, "active"), (5, "done"),
    ]


def test_iter_steps_yields_pipeline_run_result(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)

    events = list(p.iter_steps("input text"))

    result_events = [e for e in events if isinstance(e, PipelineRunResult)]
    assert len(result_events) == 1
    assert result_events[0].simplified == "simplified"
    assert result_events[0].clarified == "clarified"
    assert result_events[0].raw_text == "input text"


def test_iter_steps_wrap_step_called_per_step(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)

    calls = []

    def wrap_step(step, label, fn):
        calls.append(step)
        return fn()

    list(p.iter_steps("text", wrap_step=wrap_step))

    # wrap_step is called for steps 2, 3, 4, 5 (all four mapped steps)
    assert calls == [2, 3, 4, 5]


def test_iter_steps_step3_failure_yields_step_error(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)
    p.simplify_language_with_term_plan = MagicMock(side_effect=RuntimeError("simplify failed"))

    events = list(p.iter_steps("text"))

    error_events = [e for e in events if isinstance(e, PipelineStepError)]
    assert len(error_events) == 1
    assert error_events[0].step == 3
    assert "simplify failed" in str(error_events[0].exc)

    # No PipelineRunResult after a fatal error
    assert not [e for e in events if isinstance(e, PipelineRunResult)]


def test_iter_steps_step4_failure_falls_back_to_simplified(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)
    p.clarify_and_action = MagicMock(side_effect=RuntimeError("clarify failed"))

    events = list(p.iter_steps("text"))

    # Step 4 is non-fatal: falls back to simplified; no PipelineStepError
    assert not [e for e in events if isinstance(e, PipelineStepError)]

    result_events = [e for e in events if isinstance(e, PipelineRunResult)]
    assert len(result_events) == 1
    # clarified falls back to simplified when step 4 fails
    assert result_events[0].clarified == "simplified"


def test_iter_steps_step5_failure_yields_step_error(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)
    p.structure_appointment_note = MagicMock(side_effect=RuntimeError("structure failed"))

    events = list(p.iter_steps("text"))

    error_events = [e for e in events if isinstance(e, PipelineStepError)]
    assert len(error_events) == 1
    assert error_events[0].step == 5


def test_run_delegates_to_iter_steps(monkeypatch):
    import care_plan.v1_2.pipeline as pipeline_module
    p = _make_pipeline(monkeypatch, pipeline_module)

    result = p.run("text")

    assert isinstance(result, CarePlanV1_2)
```

**Acceptance**
- All tests in `test_pipeline_streaming.py` pass.
- `pytest tests/care_plan/test_pipeline_streaming.py -v` exits 0.

**Commit**
```
test(sp07): add test_pipeline_streaming.py for CarePlanV1_2Pipeline.iter_steps()
```

---

### Task 07.11: Update `tests/routes/test_route_rewire.py` for deleted 410 routes

**Goal**
The route rewire test currently asserts that `/care_plan` and `/care_plan/batch` appear in `expected_care_plan_rules`. After deleting the 410 stubs, these rules will no longer be registered (unless another blueprint registers them). Remove them from the assertion if no other route provides these paths.

**Files**
- Edit: `backend/tests/routes/test_route_rewire.py`

**Steps**

1. Run the test before making changes: `pytest tests/routes/test_route_rewire.py -v`. Observe which specific assertions fail after the stub deletions.

2. If `/care_plan` (exact path, `POST`) is no longer registered by any blueprint after deleting `care_plan_sse_deprecated`, remove it from `expected_care_plan_rules`.

3. If `/care_plan/batch` (exact path, `POST`) is no longer registered by any blueprint after deleting `care_plan_batch_sse_deprecated`, remove it from `expected_care_plan_rules`.

4. The test `test_batch_route_uses_care_plan_pipeline_and_save_helper_surface` on line 47 asserts `batch._pipeline_for_version("v1-2") is batch.run_care_plan_pipeline`. This assertion remains valid after SP07 (the function is still registered). Keep it.

> Note: If `batch_jobs.py` registers a `/care_plan/batch/jobs` route, that blueprint may also register `/care_plan/batch` as a prefix — check. If so, `/care_plan/batch` stays in `expected_care_plan_rules`.

**Acceptance**
- `pytest tests/routes/test_route_rewire.py -v` passes with 0 failures.

**Commit**
```
test(sp07): update test_route_rewire.py after deletion of POST /care_plan and POST /care_plan/batch stubs
```

---

## Verification

Run the full test suite from `backend/`:

```bash
cd /root/projects/juno/backend
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

Run the specific SP07-affected test files in isolation first to debug failures:

```bash
python -m pytest tests/care_plan/test_pipeline_streaming.py tests/care_plan/test_pipeline_executors.py tests/care_plan/test_pipeline_schema.py tests/utils/test_care_plan_markers.py tests/routes/test_worker.py tests/routes/test_route_rewire.py -v --tb=short
```

Run a lint/import check:

```bash
python -c "
from models.pipeline_events import StepEvent, PipelineRunResult, PipelineStepError, AdapterStepEvent, AdapterResult, AdapterError
from care_plan.v1_2.pipeline import CarePlanV1_2Pipeline
from care_plan.interface import CarePlanPipeline
from routes.care_plan import run_care_plan_pipeline, AdapterStepEvent, AdapterResult, AdapterError
from routes.worker import execute_job
print('All imports OK')
"
```

Verify SSE protocol is gone:

```bash
grep -rn "\"data: \"\|removeprefix\|RESULT_SENTINEL\|_sse\b\|care_plan_sse_deprecated\|care_plan_batch_sse_deprecated" backend/routes/ backend/care_plan/ backend/models/ backend/tests/
```

Expected: zero matches (the only acceptable hits are in test files' import strings, if any).

**Definition of Done**

- All `pytest tests/` pass.
- Zero SSE protocol references in production code (`routes/`, `care_plan/`, `models/`).
- `models/pipeline_events.py` exists and exports all six dataclasses.
- `CarePlanV1_2Pipeline.iter_steps()` exists and `run()` is a thin wrapper.
- `run_care_plan_pipeline` in `routes/care_plan.py` contains no step logic (no calls to `detect_terms`, `simplify_language_with_term_plan`, `clarify_and_action`, or `structure_appointment_note`).
- `routes/worker.py` contains no `json.loads`, no `"data: "` parsing, no `RESULT_SENTINEL`.
- Both 410 stub routes deleted.
- Section-header comments present in both `routes/care_plan.py` and `routes/worker.py`.
