# PRD: SP11 — Legacy Shim Purge & Pipeline Step Versioning

**Sub-project:** SP11
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-29
**Status:** Planning — no implementation started
**Dependencies:** None

---

## 1. Problem

Three independent classes of "kept around for compatibility" code accumulated in the backend during the incremental SP0x migration to namespaced `Constants` and to the `Markers`/`JunoContext` observability layer. None of them carry any present-day justification — this is a test-only codebase, so there is no legacy traffic to bridge — but all three are still in the tree:

1. **`utils/constants.py:139–162`** carries an explicit, self-documenting "Backward-compat flat shims" block (`# TODO(SP03+): remove each shim once its consumer migrates to Constants.<Namespace>.<NAME>.`) that re-exports 18 namespaced constants as flat `Constants.<NAME>` attributes. Some of these flat names still have live consumers scattered across routes, models, and utils; others (`MAX_AGGREGATE_FILE_BYTES`, `CARE_PLAN_DEFAULT_VERSION_ENV_VAR`, `CARE_PLAN_DEFAULT_VERSION_FALLBACK`, `ATHENA_BASE_URL`) have zero production consumers left and exist only because the shim block itself and one test (`test_flat_shims_still_work`) reference them.

2. **`Constants.Pipeline.STEPS`** (`utils/constants.py:27–33`) is a bare `dict[int, str]` whose content (`"Reading your note"`, `"Finding difficult and medical terms"`, …) is v1_2-pipeline-specific, yet the name `STEPS` implies it is pipeline-version-agnostic. Every consumer (`care_plan/v1_2/pipeline.py`) also indexes into it with bare int literals (`Constants.STEPS[2]`, `Constants.STEPS[3]`, …), so the step number is duplicated as a magic number at every call site instead of being a single named, typed value.

3. **Two delegating/compatibility shims in `routes/care_plan.py`:**
   - `_score_or_none` (lines 50–52) — a one-line wrapper around `score_text_safe` that exists only "so tests can patch scoring without touching the import."
   - `_juno_error_logger` (lines 42–44) — a logger bound to the name `"utils.juno_logger"`, whose docstring claims it exists "for compatibility with existing log-assertion tests that predate the Markers migration." Investigation (below) shows it is **dead on arrival**: nothing in the file ever calls `_juno_error_logger.<anything>`, and no test asserts against the logger name `"utils.juno_logger"`. It is pure unused code, not an active compatibility bridge.

None of these three problems are hard to fix individually, but the constants shim has a wide, easy-to-miss blast radius (uploads, batch, grading, Athena, storage, env vars, pipeline versioning all flow through one flat namespace), which is why this PRD enumerates every consumer explicitly with file:line evidence rather than asserting "grep and fix."

---

## 2. Goals

1. Delete the `utils/constants.py:139–162` flat-shim block in its entirety (including the `TODO(SP03+)` comment header) and migrate every real consumer to the namespaced form (`Constants.<Namespace>.<NAME>`).
2. Rename `Constants.Pipeline.STEPS` to a version-qualified, typed construct — `Constants.Pipeline.PIPELINE_V1_2_STEPS`, an `Enum` whose members carry both `.number` (int) and `.label` (str) — and update every pipeline call site in `care_plan/v1_2/pipeline.py` to reference named enum members instead of bare int literals.
3. Delete `_score_or_none` from `routes/care_plan.py`; call `score_text_safe` directly at both call sites; rewrite the 4 test patch targets in `tests/utils/test_care_plan_markers.py` to patch `routes.care_plan.score_text_safe` instead of `routes.care_plan._score_or_none`.
4. Delete the dead `_juno_error_logger` shim from `routes/care_plan.py`. No test changes are required (verified below — nothing references it).
5. Capture the `build_grading` rename as an explicit `[OPEN]` item (§9) — not decided in this PRD.

The codebase must continue to pass the full backend test suite (`pytest backend/`) after every change, with zero references to any deleted flat constant name, `_score_or_none`, `_juno_error_logger`, or `Constants.Pipeline.STEPS` remaining anywhere in `backend/`.

---

## 3. Non-Goals

- **No removal of the `JunoLogger` class or `utils/juno_logger.py` module.** That is SP13's scope (Observability/Logging Reconciliation). SP11 only removes the *logger-name compatibility shim* (`_juno_error_logger = logging.getLogger("utils.juno_logger")`) inside `routes/care_plan.py` — a one-line local variable, not the underlying logger infrastructure.
- **No change to `app.py`'s logging/metrics wiring.** SP13 handles routing `app.py` through `Markers`/`JunoContext` only.
- **No relocation of helper functions out of `routes/care_plan.py`** (e.g. `upload_combined_pdf`, `_resolve_uploaded_files`, `_fetch_from_gcs`). That restructuring is SP13's "routes-utils-services boundary cleanup" scope. SP11 only touches the specific lines enumerated in §4 below.
- **No decision on renaming `build_grading`.** Captured as `[OPEN]` in §9; this PRD does not touch `models/grading.py`'s function name or any of its call sites.
- **No changes to `Constants.Athena`, `Constants.Storage`, `Constants.Grading`, `Constants.Enums`, etc. namespace *contents*** — only the flat top-level aliases pointing at them are deleted. The namespaced values themselves are untouched.
- **No deprecation period, feature flag, or compatibility shim for any of the above.** This is a test-only codebase; every change here is a hard cutover in a single PR.
- **No change to `StepEvent`, `AdapterStepEvent`, `PipelineRunResult`, `PipelineStepError`, or `AdapterError` dataclass shapes** (`models/pipeline_events.py`). `StepEvent.step` remains a plain `int` — the new `Step` enum produces an `int` via `.number`, it does not change the dataclass field's type.

---

## 4. Architecture Decisions

### 4a. Delete the flat-shim block in `utils/constants.py`

**File:** `backend/utils/constants.py`

**Before (lines 139–163, end of file):**
```python
# ---------------------------------------------------------------------------
# Backward-compat flat shims — kept for callsites not yet migrated.
# TODO(SP03+): remove each shim once its consumer migrates to Constants.<Namespace>.<NAME>.
# ---------------------------------------------------------------------------
Constants.RESULT_SENTINEL               = Constants.Pipeline.RESULT_SENTINEL
Constants.MAX_BATCH_RUNS               = Constants.Batch.MAX_BATCH_RUNS
Constants.ALLOWED_EXTENSIONS           = Constants.Uploads.ALLOWED_EXTENSIONS
Constants.MAX_FILE_BYTES               = Constants.Uploads.MAX_FILE_BYTES
Constants.MAX_FILE_COUNT               = Constants.Uploads.MAX_FILE_COUNT
Constants.MAX_AGGREGATE_FILE_BYTES     = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES
Constants.PIPELINE_VERSION_V1_2        = Constants.Pipeline.PIPELINE_VERSION_V1_2
Constants.STEPS                        = Constants.Pipeline.STEPS
Constants.CARE_PLAN_VERSIONS           = Constants.Pipeline.CARE_PLAN_VERSIONS
Constants.GRADING_METHODS              = Constants.Grading.GRADING_METHODS
Constants.SOURCE                       = Constants.Enums.SOURCE
Constants.IMPORTANCE                   = Constants.Enums.IMPORTANCE
Constants.ATHENA_BASE_URL              = Constants.Athena.BASE_URL
Constants.ATHENA_PRACTICE_ID           = Constants.Athena.PRACTICE_ID
Constants.GCS_BUCKET_ENV_VAR           = Constants.Storage.GCS_BUCKET_ENV_VAR

Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR     = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION
Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK    = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION_FALLBACK
Constants.ATHENA_CLIENT_ID_ENV_VAR     = Constants.EnvVars.ATHENA_CLIENT_ID
Constants.ATHENA_CLIENT_SECRET_ENV_VAR = Constants.EnvVars.ATHENA_CLIENT_SECRET
```

**After:** the file ends at line 136 (the `Observability` namespace's closing lines); the entire block above is deleted, no replacement.

Note: `Constants.STEPS` and `Constants.PIPELINE_VERSION_V1_2`/`Constants.CARE_PLAN_VERSIONS` lines above are superseded by §4b/§4c — they are deleted here as part of the same block removal, and their consumers are migrated per the tables below (STEPS via the new `Step` enum design in §4b, the others via direct namespace-qualification).

#### Full old→new consumer table (grep-verified)

Every flat name below was searched with `grep -rn "Constants\.<NAME>" backend --include="*.py"` excluding `constants.py` itself. The table lists every real consumer found; "no consumers" means the name is dead and is simply deleted with no migration needed.

| Flat name | New namespaced form | Consumers (file:line) | Action |
|---|---|---|---|
| `Constants.RESULT_SENTINEL` | `Constants.Pipeline.RESULT_SENTINEL` | `backend/tests/routes/test_worker_gcs_dataset.py:74` | Update test to namespaced form |
| `Constants.MAX_BATCH_RUNS` | `Constants.Batch.MAX_BATCH_RUNS` | `backend/routes/batch_jobs.py:77`, `:81` | Update both call sites |
| `Constants.ALLOWED_EXTENSIONS` | `Constants.Uploads.ALLOWED_EXTENSIONS` | `backend/routes/care_plan.py:73` | Update call site |
| `Constants.MAX_FILE_BYTES` | `Constants.Uploads.MAX_FILE_BYTES` | `backend/routes/care_plan.py:131`, `backend/routes/care_plan_jobs.py:81` | Update both call sites |
| `Constants.MAX_FILE_COUNT` | `Constants.Uploads.MAX_FILE_COUNT` | `backend/routes/care_plan.py:117`, `:118` | Update both call sites |
| `Constants.MAX_AGGREGATE_FILE_BYTES` | `Constants.Uploads.MAX_AGGREGATE_FILE_BYTES` | **None** — `care_plan.py:134–135` already uses the namespaced form | Delete only; no migration needed |
| `Constants.PIPELINE_VERSION_V1_2` | `Constants.Pipeline.PIPELINE_VERSION_V1_2` | `backend/routes/worker.py:33`, `backend/models/batch_requests.py:73`, `:85` | Update all 3 call sites |
| `Constants.STEPS` | `Constants.Pipeline.PIPELINE_V1_2_STEPS` (new enum — see §4b) | `backend/care_plan/v1_2/pipeline.py:175,177,185,188,191,203,206,209,215,218,221,228` | Full redesign per §4b, not a 1:1 rename |
| `Constants.CARE_PLAN_VERSIONS` | `Constants.Pipeline.CARE_PLAN_VERSIONS` | `backend/care_plan/v1_2/pipeline.py:242`; `backend/models/care_plan/versions/v1_2.py:109,112`; `backend/tests/care_plan/test_pipeline_schema.py:30,68`; `backend/tests/models/test_care_plan.py:42,45,66,71,77,80,86` | Update all 11 call sites |
| `Constants.GRADING_METHODS` | `Constants.Grading.GRADING_METHODS` | `backend/models/grading.py:42`; `backend/utils/scoring_methods.py:97–102` (6 lines); `backend/tests/utils/test_scoring_methods.py:178,194,195`; `backend/tests/models/test_grading_model.py:107–119` (12 lines) | Update all call sites |
| `Constants.SOURCE` | `Constants.Enums.SOURCE` | `backend/models/care_plan/versions/v1_2.py:44,56,66,77,92` | Update all 5 field annotations |
| `Constants.IMPORTANCE` | `Constants.Enums.IMPORTANCE` | `backend/models/care_plan/versions/v1_2.py:43,55,65,76,91` | Update all 5 field annotations/defaults |
| `Constants.ATHENA_BASE_URL` | `Constants.Athena.BASE_URL` | **None in production code** — `backend/services/external_api/athena_client.py` already uses `Constants.Athena.BASE_URL` directly; the only consumer of the flat form is `backend/tests/utils/test_constants.py:67` (the shim-existence test itself, deleted in §4a below) | Delete only; no production migration needed |
| `Constants.ATHENA_PRACTICE_ID` | `Constants.Athena.PRACTICE_ID` | `backend/routes/worker.py:232` | Update call site |
| `Constants.GCS_BUCKET_ENV_VAR` | `Constants.Storage.GCS_BUCKET_ENV_VAR` | `backend/routes/care_plan.py:58`, `:174` | Update both call sites |
| `Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR` | `Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION` | **None** | Delete only; no migration needed |
| `Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK` | `Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION_FALLBACK` | **None** | Delete only; no migration needed |
| `Constants.ATHENA_CLIENT_ID_ENV_VAR` | `Constants.EnvVars.ATHENA_CLIENT_ID` | `backend/services/external_api/athena_client.py:39` | Update call site |
| `Constants.ATHENA_CLIENT_SECRET_ENV_VAR` | `Constants.EnvVars.ATHENA_CLIENT_SECRET` | `backend/services/external_api/athena_client.py:40` | Update call site |

Frontend (`frontend/`) was also grepped for every flat name above — zero matches. This is a backend-only Python concern; no frontend changes are in scope for SP11.

#### Representative before/after snippets for the table above

`backend/routes/batch_jobs.py:77,81`
```python
# Before
if total_count > Constants.MAX_BATCH_RUNS:
    return make_error_response(
        ErrorCode.BATCH_TOO_LARGE, request.path,
        {"count": total_count, "max_runs": Constants.MAX_BATCH_RUNS},
    ).to_dict(), 400

# After
if total_count > Constants.Batch.MAX_BATCH_RUNS:
    return make_error_response(
        ErrorCode.BATCH_TOO_LARGE, request.path,
        {"count": total_count, "max_runs": Constants.Batch.MAX_BATCH_RUNS},
    ).to_dict(), 400
```

`backend/routes/care_plan.py:58,73,117–118,131,174`
```python
# Before
bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")
...
return "." in filename and filename.rsplit(".", 1)[1].lower() in Constants.ALLOWED_EXTENSIONS
...
if len(files) > Constants.MAX_FILE_COUNT:
    raise ValueError(f"Upload supports at most {Constants.MAX_FILE_COUNT} files")
...
if len(file_bytes) > Constants.MAX_FILE_BYTES:
...
_gcs_bucket_name = os.environ.get(Constants.GCS_BUCKET_ENV_VAR, "")

# After
bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
...
return "." in filename and filename.rsplit(".", 1)[1].lower() in Constants.Uploads.ALLOWED_EXTENSIONS
...
if len(files) > Constants.Uploads.MAX_FILE_COUNT:
    raise ValueError(f"Upload supports at most {Constants.Uploads.MAX_FILE_COUNT} files")
...
if len(file_bytes) > Constants.Uploads.MAX_FILE_BYTES:
...
_gcs_bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
```

`backend/routes/care_plan_jobs.py:81–82`
```python
# Before
if len(file_bytes) > Constants.MAX_FILE_BYTES:
    raise ValueError(f"Stored file exceeds {Constants.Uploads.MAX_FILE_BYTES // (1024 * 1024)} MB limit")

# After
if len(file_bytes) > Constants.Uploads.MAX_FILE_BYTES:
    raise ValueError(f"Stored file exceeds {Constants.Uploads.MAX_FILE_BYTES // (1024 * 1024)} MB limit")
```
(Note: the f-string already used the namespaced form — only the `if` comparison needs the prefix added.)

`backend/routes/worker.py:33,232`
```python
# Before
PIPELINES = {Constants.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}
...
practice_id = job.athena_practice_id or Constants.ATHENA_PRACTICE_ID

# After
PIPELINES = {Constants.Pipeline.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}
...
practice_id = job.athena_practice_id or Constants.Athena.PRACTICE_ID
```

`backend/models/batch_requests.py:73,85`
```python
# Before
class BatchJobsRequest(BaseModel):
    ...
    version: str = Constants.PIPELINE_VERSION_V1_2
...
class SingleJobRequest(BaseModel):
    version: str = Constants.PIPELINE_VERSION_V1_2

# After
class BatchJobsRequest(BaseModel):
    ...
    version: str = Constants.Pipeline.PIPELINE_VERSION_V1_2
...
class SingleJobRequest(BaseModel):
    version: str = Constants.Pipeline.PIPELINE_VERSION_V1_2
```

`backend/services/external_api/athena_client.py:39–40`
```python
# Before
client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]

# After
client_id = os.environ[Constants.EnvVars.ATHENA_CLIENT_ID]
client_secret = os.environ[Constants.EnvVars.ATHENA_CLIENT_SECRET]
```

`backend/models/care_plan/versions/v1_2.py` (5 fields use `Constants.IMPORTANCE`/`Constants.SOURCE`, e.g. lines 43–44)
```python
# Before
importance: Constants.IMPORTANCE = Constants.IMPORTANCE.LOW
source: Constants.SOURCE | None = None

# After
importance: Constants.Enums.IMPORTANCE = Constants.Enums.IMPORTANCE.LOW
source: Constants.Enums.SOURCE | None = None
```
Apply the same substitution at all 5 occurrences each (lines 43/44, 55/56, 65/66, 76/77, 91/92).

`backend/models/grading.py:42`
```python
# Before
for method in Constants.GRADING_METHODS:

# After
for method in Constants.Grading.GRADING_METHODS:
```

`backend/utils/scoring_methods.py:97–102`
```python
# Before
return {
    Constants.GRADING_METHODS.SMOG:           score_smog(text),
    Constants.GRADING_METHODS.FLESCH_KINCAID: score_flesch_kincaid(text),
    Constants.GRADING_METHODS.DALE_CHALL:     score_dale_chall(text),
    Constants.GRADING_METHODS.PEMAT:          score_pemat(dimensions),
    Constants.GRADING_METHODS.SAM:            score_sam(dimensions),
    Constants.GRADING_METHODS.CDC_CCI:        score_cdc_cci(dimensions),
}

# After
return {
    Constants.Grading.GRADING_METHODS.SMOG:           score_smog(text),
    Constants.Grading.GRADING_METHODS.FLESCH_KINCAID: score_flesch_kincaid(text),
    Constants.Grading.GRADING_METHODS.DALE_CHALL:     score_dale_chall(text),
    Constants.Grading.GRADING_METHODS.PEMAT:          score_pemat(dimensions),
    Constants.Grading.GRADING_METHODS.SAM:            score_sam(dimensions),
    Constants.Grading.GRADING_METHODS.CDC_CCI:        score_cdc_cci(dimensions),
}
```

Test files (`test_worker_gcs_dataset.py:74`, `test_pipeline_schema.py:30,68`, `test_care_plan.py:42,45,66,71,77,80,86`, `test_scoring_methods.py:178,194,195`, `test_grading_model.py:107–119`) get the identical mechanical substitution — prefix the namespace (`.Pipeline.`, `.Grading.`) onto each `Constants.<FLAT_NAME>` occurrence. These are not reproduced line-by-line here since the substitution pattern is identical to the production-code examples above; the task executor should grep-and-replace each file per the table.

**Also delete `backend/tests/utils/test_constants.py`'s `test_flat_shims_still_work` function (lines 63–67) in its entirety** — it exists solely to assert the shim block works, and the shim block no longer exists:
```python
# Delete entirely:
def test_flat_shims_still_work():
    assert Constants.RESULT_SENTINEL == Constants.Pipeline.RESULT_SENTINEL
    assert Constants.MAX_BATCH_RUNS == Constants.Batch.MAX_BATCH_RUNS
    assert Constants.GRADING_METHODS is Constants.Grading.GRADING_METHODS
    assert Constants.ATHENA_BASE_URL == Constants.Athena.BASE_URL
```

---

### 4b. Version-qualify `Constants.Pipeline.STEPS` with a typed `Step` enum

**File:** `backend/utils/constants.py`

**Problem recap:** `Constants.Pipeline.STEPS` is `dict[int, str]` — a bare number→label map — and its content is implicitly v1_2-specific even though nothing in the name says so. Every consumer indexes it with a bare int literal (`Constants.STEPS[2]`), duplicating the step number as a magic number at each call site.

**Before (lines 25–39):**
```python
class Pipeline:
    PIPELINE_VERSION_V1_2: str = "v1-2"
    STEPS: dict[int, str] = {
        1: "Reading your note",
        2: "Finding difficult and medical terms",
        3: "Simplifying language",
        4: "Clarifying actions and numbers",
        5: "Organizing your care plan",
    }
    # ── SSE stream result sentinel ───────────────────────────────────
    RESULT_SENTINEL: str = "__result__"

    class CARE_PLAN_VERSIONS(Enum):
        V1_2 = "1.2"
```

**After:**
```python
class Pipeline:
    PIPELINE_VERSION_V1_2: str = "v1-2"

    class PIPELINE_V1_2_STEPS(Enum):
        """Named steps of the v1_2 care-plan pipeline. Each member carries its
        1-based step number (`.number`) and its user-facing progress label
        (`.label`); replaces the old bare `dict[int, str]` so call sites
        reference named members instead of int literals."""
        READ_NOTE          = (1, "Reading your note")
        DETECT_TERMS       = (2, "Finding difficult and medical terms")
        SIMPLIFY_LANGUAGE  = (3, "Simplifying language")
        CLARIFY_AND_ACTION = (4, "Clarifying actions and numbers")
        STRUCTURE_DOCUMENT = (5, "Organizing your care plan")

        def __new__(cls, number: int, label: str):
            obj = object.__new__(cls)
            obj._value_ = number
            obj.number = number
            obj.label = label
            return obj

    # ── SSE stream result sentinel ───────────────────────────────────
    RESULT_SENTINEL: str = "__result__"

    class CARE_PLAN_VERSIONS(Enum):
        V1_2 = "1.2"
```

Design notes:
- This follows the existing house convention in this same file: `Constants.Pipeline.CARE_PLAN_VERSIONS`, `Constants.Grading.GRADING_METHODS`, `Constants.Enums.SOURCE`/`IMPORTANCE`, and `Constants.Athena.AthenaSourceKind` are all already `Enum`/`StrEnum` classes nested directly under their namespace and named in the same constant-like style — `PIPELINE_V1_2_STEPS` as an `Enum` class name matches that precedent exactly (rather than introducing a new dataclass type that would be the only one of its kind in the file).
- `PIPELINE_V1_2_STEPS(2) == PIPELINE_V1_2_STEPS.DETECT_TERMS` works out of the box via the custom `__new__` (the member's `.value` *is* the step number), so any future code that needs "look up step by number" can do `Constants.Pipeline.PIPELINE_V1_2_STEPS(step_num)` without a separate dict.
- `READ_NOTE` (step 1) is retained even though no `StepEvent` is ever emitted for step 1 today (confirmed — no call site references step 1; `routes/worker.py:270` just initializes `current_stage = 1` as the implicit pre-pipeline stage). Keeping it preserves the original dict's full 1–5 range and costs nothing.

**File:** `backend/care_plan/v1_2/pipeline.py`

Add a module-level alias for readability, then replace every bare-int-literal call site (12 sites at lines 175,177,185,188,191,203,206,209,215,218,221,228, plus 2 additional `PipelineStepError(step=N, ...)` sites at lines 201 and 226 that carry the same bare-int problem and are fixed for consistency even though they weren't in the original STEPS-indexing list):

**Before (line 47, import block):**
```python
from utils.constants import Constants
```

**After (add directly below it):**
```python
from utils.constants import Constants

_STEP = Constants.Pipeline.PIPELINE_V1_2_STEPS
```

**Before (lines 174–228, full step-emission block):**
```python
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
```

**After:**
```python
        # Step 2: term detection (deterministic, no LLM)
        yield StepEvent(step=_STEP.DETECT_TERMS.number, status="active", label=_STEP.DETECT_TERMS.label)
        try:
            term_data = _call(
                _STEP.DETECT_TERMS.number, _STEP.DETECT_TERMS.label,
                lambda: detect_terms(text),
            )
        except Exception:
            logger.exception("pipeline: term detection failed — continuing with empty terms")
            term_data = {
                "substitution_candidates": [],
                "preserve_and_define_terms": [],
                "abbreviations": [],
            }
        yield StepEvent(step=_STEP.DETECT_TERMS.number, status="done", label=_STEP.DETECT_TERMS.label)

        # Step 3: simplify language
        yield StepEvent(step=_STEP.SIMPLIFY_LANGUAGE.number, status="active", label=_STEP.SIMPLIFY_LANGUAGE.label)
        try:
            simplified = _call(
                _STEP.SIMPLIFY_LANGUAGE.number, _STEP.SIMPLIFY_LANGUAGE.label,
                lambda: self.simplify_language_with_term_plan(
                    text,
                    term_data["substitution_candidates"],
                    term_data["preserve_and_define_terms"],
                    term_data["abbreviations"],
                ),
            )
        except Exception as exc:
            logger.exception("pipeline: simplification failed")
            yield PipelineStepError(step=_STEP.SIMPLIFY_LANGUAGE.number, exc=exc)
            return
        yield StepEvent(step=_STEP.SIMPLIFY_LANGUAGE.number, status="done", label=_STEP.SIMPLIFY_LANGUAGE.label)

        # Step 4: clarify and action
        yield StepEvent(step=_STEP.CLARIFY_AND_ACTION.number, status="active", label=_STEP.CLARIFY_AND_ACTION.label)
        try:
            clarified = _call(
                _STEP.CLARIFY_AND_ACTION.number, _STEP.CLARIFY_AND_ACTION.label,
                lambda: self.clarify_and_action(simplified, term_data["abbreviations"]),
            )
        except Exception:
            logger.exception("pipeline: clarify step failed — using simplified text")
            clarified = simplified   # non-fatal: fall back to simplified
        yield StepEvent(step=_STEP.CLARIFY_AND_ACTION.number, status="done", label=_STEP.CLARIFY_AND_ACTION.label)

        # Step 5: structure appointment note
        yield StepEvent(step=_STEP.STRUCTURE_DOCUMENT.number, status="active", label=_STEP.STRUCTURE_DOCUMENT.label)
        try:
            structured = _call(
                _STEP.STRUCTURE_DOCUMENT.number, _STEP.STRUCTURE_DOCUMENT.label,
                lambda: self.structure_appointment_note(clarified),
            )
        except Exception as exc:
            logger.exception("pipeline: structuring failed")
            yield PipelineStepError(step=_STEP.STRUCTURE_DOCUMENT.number, exc=exc)
            return
        yield StepEvent(step=_STEP.STRUCTURE_DOCUMENT.number, status="done", label=_STEP.STRUCTURE_DOCUMENT.label)
```

**Also update line 242** (the `CARE_PLAN_VERSIONS` flat-shim consumer noted in the §4a table):
```python
# Before
care_plan = CarePlan.from_pipeline_result(Constants.CARE_PLAN_VERSIONS.V1_2.value, result)

# After
care_plan = CarePlan.from_pipeline_result(Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, result)
```

No changes are needed to `models/pipeline_events.py` — `StepEvent.step` stays `int`, and `_STEP.<NAME>.number` is an `int`, so the dataclass contract is unchanged. No changes are needed to `routes/care_plan.py`'s `_STEP_MARKER_MAP` (it is keyed by int already and is unrelated to the `Constants.Pipeline.STEPS` dict — it maps step number to `(Marker, function_name, span_name)` tuples, a separate concern).

---

### 4c. Delete `_score_or_none` in `routes/care_plan.py`

**File:** `backend/routes/care_plan.py`

**Before (lines 49–52):**
```python
# ── Scoring helpers ────────────────────────────────────────────────────────────
def _score_or_none(text: str, label: str):
    """Thin wrapper so tests can patch scoring without touching the import."""
    return score_text_safe(text, label)
```

**After:** delete the function entirely (including the `# ── Scoring helpers ──` section comment, since nothing else lives under it).

**Before (lines 252–254, the two call sites inside `run_care_plan_pipeline`):**
```python
                if grading_enabled:
                    before_score = _score_or_none(text, "before")
                    after_score  = _score_or_none(event.clarified, "after")
```

**After:**
```python
                if grading_enabled:
                    before_score = score_text_safe(text, "before")
                    after_score  = score_text_safe(event.clarified, "after")
```

`score_text_safe` is already imported at the top of the file (`from utils.scoring import score_text_safe`, line 22) and has the exact same signature `(text: str, label: str) -> dict | None` (`backend/utils/scoring.py:307`), so this is a pure substitution with no signature drift.

**File:** `backend/tests/utils/test_care_plan_markers.py` — rewrite all 4 patch targets

All four patch sites currently do `patch("routes.care_plan._score_or_none", return_value=...)`. Since `score_text_safe` is imported directly into the `routes.care_plan` module namespace (`from utils.scoring import score_text_safe`), patching `routes.care_plan.score_text_safe` is the correct equivalent target (patches the name as bound in that module, exactly like the original pattern did for `_score_or_none`).

**Before (line 140):**
```python
        patch("routes.care_plan._score_or_none", return_value={"composite": 72.5, "dimensions": {}}),
```
**After:**
```python
        patch("routes.care_plan.score_text_safe", return_value={"composite": 72.5, "dimensions": {}}),
```

**Before (line 173):**
```python
        patch("routes.care_plan._score_or_none", return_value=None),
```
**After:**
```python
        patch("routes.care_plan.score_text_safe", return_value=None),
```

**Before (line 235):**
```python
        patch("routes.care_plan._score_or_none", return_value={"composite": 85.0, "dimensions": {}}),
```
**After:**
```python
        patch("routes.care_plan.score_text_safe", return_value={"composite": 85.0, "dimensions": {}}),
```

**Before (line 270):**
```python
        patch("routes.care_plan._score_or_none", return_value=None),
```
**After:**
```python
        patch("routes.care_plan.score_text_safe", return_value=None),
```

No other lines in these 4 test functions (`test_pipeline_marker_has_source_kind_grading_enabled_is_batch`, `test_pipeline_marker_batch_dimensions`, `test_grading_run_marker_fired_when_grading_enabled`, `test_grading_run_marker_not_fired_when_grading_disabled`) need to change — they only reference the patched name, not `_score_or_none`'s internals.

---

### 4d. Delete the dead `_juno_error_logger` shim in `routes/care_plan.py`

**File:** `backend/routes/care_plan.py`

**Investigation result:** `grep -n "_juno_error_logger" backend/routes/care_plan.py` returns only the single definition line (44) — there is no `_juno_error_logger.error(...)`, `.exception(...)`, `.warning(...)`, or any other usage anywhere in the file. A repo-wide search for the literal string `"utils.juno_logger"` (the logger name it binds) also returns only that same line — no test in `backend/tests/` asserts against a logger named `"utils.juno_logger"` via `caplog`, `getLogger`, or any other mechanism. The shim is not an active compatibility bridge for any test; it is simply unused dead code that was never wired to anything after being introduced.

**Before (lines 41–44):**
```python
logger = logging.getLogger(__name__)
# Secondary error logger routed to utils.juno_logger for compatibility with existing
# log-assertion tests that predate the Markers migration.
_juno_error_logger = logging.getLogger("utils.juno_logger")
```

**After:**
```python
logger = logging.getLogger(__name__)
```

No test changes are required for this deletion — confirmed via the grep above that nothing depends on it. (Contrast with §4c, where 4 tests do actively patch the deleted symbol and must be rewritten.)

---

### 4e. Rename `build_grading` to `build_grading_with_before_after_score`

**Decision:** `[RESOLVED]` (see §9 Q1). Pure rename for clarity — no behavior, signature, or location change.

**File (unchanged):** `backend/models/grading.py:28` — `build_grading` is already correctly colocated with the `Grading`/`GradingEntry` models in this file; the rename does not move it.

**Rationale for the chosen name:** the function's body (`backend/models/grading.py:28-68`) takes exactly two `(score, text)` pairs — `(before_score, before_text)` and `(after_score, after_text)` — and builds a `Grading` whose entries are tagged `target="before"` / `target="after"`. `build_grading_with_before_after_score` accurately names both the before/after pairing and the fact that the `score` dicts (not just the texts) are the primary structured input driving the output (`score["dimensions"]`, `score["composite"]`, `score["grade_estimate"]`, etc., all flow directly into the returned entries). No more accurate alternative was found, so the originally floated name is adopted as-is.

**Old → new call-site table (grep-verified via `grep -rn "build_grading" backend/`):**

| File:Line | Kind | Old | New |
|---|---|---|---|
| `backend/models/grading.py:28` | definition | `def build_grading(` | `def build_grading_with_before_after_score(` |
| `backend/models/__init__.py:7` | import | `from .grading import Grading, GradingEntry, build_grading` | `from .grading import Grading, GradingEntry, build_grading_with_before_after_score` |
| `backend/models/__init__.py:31` | `__all__` entry | `"build_grading",` | `"build_grading_with_before_after_score",` |
| `backend/routes/care_plan.py:24` | import | `from models.grading import Grading, build_grading, GRADING_VERSION  # noqa: F401` | `from models.grading import Grading, build_grading_with_before_after_score, GRADING_VERSION  # noqa: F401` |
| `backend/routes/care_plan.py:258` | call | `result = build_grading(before_score, text, after_score, event.clarified)` | `result = build_grading_with_before_after_score(before_score, text, after_score, event.clarified)` |
| `backend/routes/grading.py:11` | import | `from models.grading import build_grading` | `from models.grading import build_grading_with_before_after_score` |
| `backend/routes/grading.py:68` | call | `grading = build_grading(before_score, raw_text, after_score, clarified_text or None)` | `grading = build_grading_with_before_after_score(before_score, raw_text, after_score, clarified_text or None)` |
| `backend/routes/grading.py:90` | call | `grading = build_grading(before_score, text, after_score, clarified_text or None)` | `grading = build_grading_with_before_after_score(before_score, text, after_score, clarified_text or None)` |
| `backend/tests/models/test_grading_model.py:7` | import | `from models.grading import Grading, GradingEntry, build_grading` | `from models.grading import Grading, GradingEntry, build_grading_with_before_after_score` |
| `backend/tests/models/test_grading_model.py:104` | call | `grading = build_grading(before_score, FIXTURE_TEXT, after_score, FIXTURE_CLARIFIED)` | `grading = build_grading_with_before_after_score(before_score, FIXTURE_TEXT, after_score, FIXTURE_CLARIFIED)` |
| `backend/tests/routes/test_grading_route.py:185` | patch target | `patch("routes.grading.build_grading", return_value=mock_grading):` | `patch("routes.grading.build_grading_with_before_after_score", return_value=mock_grading):` |
| `backend/tests/utils/test_care_plan_markers.py:141` | patch target | `patch("routes.care_plan.build_grading", return_value=grading_stub),` | `patch("routes.care_plan.build_grading_with_before_after_score", return_value=grading_stub),` |
| `backend/tests/utils/test_care_plan_markers.py:174` | patch target | `patch("routes.care_plan.build_grading", return_value=MagicMock()),` | `patch("routes.care_plan.build_grading_with_before_after_score", return_value=MagicMock()),` |
| `backend/tests/utils/test_care_plan_markers.py:236` | patch target | `patch("routes.care_plan.build_grading", return_value=grading_stub),` | `patch("routes.care_plan.build_grading_with_before_after_score", return_value=grading_stub),` |
| `backend/tests/utils/test_care_plan_markers.py:271` | patch target | `patch("routes.care_plan.build_grading", return_value=MagicMock()),` | `patch("routes.care_plan.build_grading_with_before_after_score", return_value=MagicMock()),` |

That is 14 sites total (1 definition + 4 imports + 4 call sites + 5 patch targets) across 6 files (2 production, 4 test). Optional, non-required cosmetic follow-up: `backend/tests/models/test_grading_model.py:100`'s test function name `test_build_grading_returns_same_entries_and_no_descriptions` may also be renamed to match (e.g. `test_build_grading_with_before_after_score_returns_same_entries_and_no_descriptions`), but this is not load-bearing since pytest discovers it by file/prefix, not by the symbol it calls.

No other files reference `build_grading` (confirmed via repo-wide grep above — Production code: `models/grading.py`, `models/__init__.py`, `routes/care_plan.py`, `routes/grading.py`. Tests: `test_grading_model.py`, `test_grading_route.py`, `test_care_plan_markers.py`).

---

## 5. API Change Summary

No HTTP API, request/response schema, or Firestore document shape changes. This is a pure internal refactor:
- `Constants.<FLAT_NAME>` attribute removals are a Python-internal API change (any external script importing `from utils.constants import Constants` and reading `Constants.MAX_FILE_COUNT` etc. directly would break) — but per the locked decision, no deprecation period applies; grep confirms all real consumers are inside this repo and are migrated as part of this PRD.
- `StepEvent.step` and `AdapterStepEvent.step` remain plain `int` on the wire (SSE/job-stage updates unaffected) — `_STEP.<NAME>.number` produces the identical int values 1–5 that `Constants.STEPS[n]`/literal `n` produced before.

---

## 6. Frontend Change Summary

N/A. Grep confirmed zero frontend references to any of the 18 flat constant names, `Constants.STEPS`, `_score_or_none`, or `_juno_error_logger`. The frontend's own copies of step labels (`frontend/src/pages/care-plan/CarePlanPage.tsx`) are independently maintained TypeScript string literals, not generated from or coupled to `backend/utils/constants.py` — out of scope for SP11 and untouched by this change.

---

## 7. Testing

### Automated tests (pytest)

- **Full backend suite must stay green** (`pytest backend/`) after every change in §4a–§4d.
- **`backend/tests/utils/test_constants.py`**: delete `test_flat_shims_still_work` (§4a); all other namespace tests (`test_schema_namespace`, `test_uploads_namespace`, etc.) are unaffected since they already test namespaced access.
- **`backend/tests/utils/test_care_plan_markers.py`**: the 4 rewritten patch targets (§4c) must continue to pass with identical assertions — only the patched dotted path changes, not the test logic or expected event/dimension values.
- **New/updated assertions for the `Constants.Pipeline.PIPELINE_V1_2_STEPS` enum**: no test currently references `Constants.STEPS` or `Constants.Pipeline.STEPS` directly (confirmed via grep — zero hits in `backend/tests/`), so no existing test needs updating for the rename itself. Recommend adding one new lightweight test asserting `Constants.Pipeline.PIPELINE_V1_2_STEPS.DETECT_TERMS.number == 2` and `.label == "Finding difficult and medical terms"` (and similarly for the other 4 members) to `test_constants.py`, to lock the enum's shape now that call sites depend on `.number`/`.label` rather than dict indexing.
- **Pipeline behavior tests** (e.g. `backend/tests/care_plan/test_pipeline_schema.py`, any test exercising `CarePlanV1_2Pipeline.iter_steps`/`run`): must continue to pass unchanged — the `StepEvent.step` values yielded are numerically identical (1–5) before and after, so any test asserting `event.step == 2` etc. keeps working without modification. Verify this assumption holds by running the existing pipeline tests after the migration; do not preemptively rewrite them.
- **`test_worker_gcs_dataset.py:74`**, **`test_pipeline_schema.py:30,68`**, **`test_care_plan.py:42,45,66,71,77,80,86`**, **`test_scoring_methods.py:178,194,195`**, **`test_grading_model.py:107–119`**: mechanical namespace-prefix updates per the §4a table; re-run each file to confirm.

### Manual checks

1. Run a real (or stubbed) v1_2 pipeline end-to-end (`CarePlanV1_2Pipeline().run(text)` or via the `/care_plan/jobs` route) and confirm step progress events still report steps 2–5 with the same labels as before (`"Finding difficult and medical terms"`, `"Simplifying language"`, `"Clarifying actions and numbers"`, `"Organizing your care plan"`).
2. Confirm `pytest backend/` is fully green with zero `AttributeError: type object 'Constants' has no attribute ...` failures (would indicate a missed flat-name migration).
3. `grep -rn "Constants\.\(RESULT_SENTINEL\|MAX_BATCH_RUNS\|ALLOWED_EXTENSIONS\|MAX_FILE_BYTES\|MAX_FILE_COUNT\|MAX_AGGREGATE_FILE_BYTES\|PIPELINE_VERSION_V1_2\|STEPS\|CARE_PLAN_VERSIONS\|GRADING_METHODS\|SOURCE\|IMPORTANCE\|ATHENA_BASE_URL\|ATHENA_PRACTICE_ID\|GCS_BUCKET_ENV_VAR\|CARE_PLAN_DEFAULT_VERSION_ENV_VAR\|CARE_PLAN_DEFAULT_VERSION_FALLBACK\|ATHENA_CLIENT_ID_ENV_VAR\|ATHENA_CLIENT_SECRET_ENV_VAR\)\b" backend --include="*.py"` returns zero matches as a final sweep (the flat names should no longer resolve at all since the shim block is gone).
4. `grep -rn "_score_or_none\|_juno_error_logger" backend --include="*.py"` returns zero matches.

---

## 8. Manual Intervention Required From You

None. This is a self-contained internal refactor with no environment variables, secrets, GCP console actions, deploy steps, or data migrations involved. All changes are source-only and verifiable by the test suite.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Should `build_grading` (`backend/models/grading.py:28`) be renamed for clarity, e.g. to `build_grading_with_before_after_score`? Call sites that would need updating if renamed: `backend/routes/care_plan.py:258` (call) and `:24` (import); `backend/routes/grading.py:68,90` (calls) and `:11` (import); tests in `backend/tests/models/test_grading_model.py`, `backend/tests/routes/test_grading_route.py:185`, `backend/tests/utils/test_care_plan_markers.py:141,174,236,271`. | `[RESOLVED: rename build_grading to build_grading_with_before_after_score; the name now states what the function actually builds (a Grading) and from what (a before/after pair of score+text), matching its signature and the before/after target tagging in its output — see §4e for the full call-site table]` |
| Q2 | Naming of the new pipeline-step construct: this PRD proposes `Constants.Pipeline.PIPELINE_V1_2_STEPS` as an `Enum` class (matching the existing `CARE_PLAN_VERSIONS`/`GRADING_METHODS` house style of SCREAMING_SNAKE `Enum` class names nested in `Constants`). | `[RESOLVED: use Enum class named PIPELINE_V1_2_STEPS with `.number`/`.label` per-member attributes, as designed in §4b]` |
| Q3 | Should `READ_NOTE` (step 1, "Reading your note") be retained in the new enum even though no pipeline call site emits a `StepEvent` for it today? | `[RESOLVED: yes, retain it — it preserves the full 1–5 range of the original dict at zero cost, and `routes/worker.py:270`'s implicit `current_stage = 1` pre-pipeline stage conceptually corresponds to it]` |
| Q4 | Overlap with SP13 (Observability/Logging Reconciliation & Routes-Utils-Services Boundary Cleanup): SP13 also touches `routes/care_plan.py` (relocating non-route helper functions out of it, and separately deleting the `JunoLogger` class). SP11 deletes exactly 3 things from that file: the `_juno_error_logger` line (44, plus its 2-line comment, lines 42–43), the `_score_or_none` function (lines 49–52, plus its 1-line section comment), and the two `_score_or_none(...)` call sites inside `run_care_plan_pipeline` (lines 253–254, content only, not structural). SP11 does **not** move, rename, or relocate any other function in this file (`upload_combined_pdf`, `_allowed`, `_extract_text_from_bytes`, `_resolve_uploaded_files`, `_fetch_from_gcs`, `run_care_plan_pipeline` itself) — those remain exactly where SP13 will find them. Whichever sub-project lands second should rebase past the other's diff in this file; the line ranges above should make that low-risk. | `[RESOLVED: scope boundary stated for SP13's author — see exact line ranges above]` |
