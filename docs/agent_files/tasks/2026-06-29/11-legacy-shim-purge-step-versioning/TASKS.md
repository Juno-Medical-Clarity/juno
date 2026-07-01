# Tasks: SP11 — Legacy Shim Purge & Pipeline Step Versioning

## Prerequisites

Purpose: delete three classes of dead/compat code from the backend (flat `Constants` shims,
`_score_or_none`, `_juno_error_logger`), replace `Constants.Pipeline.STEPS` with a typed,
version-qualified `Enum`, and rename `build_grading` for clarity — all per PRD
`docs/agent_files/tasks/2026-06-29/11-legacy-shim-purge-step-versioning/PRD.md`. This is a
test-only codebase: every change is a hard cutover in this PR, no deprecation shims, no
feature flags.

All §9 decisions (Q1–Q4) are `[RESOLVED]` — there is no `[OPEN]` item blocking any task below.

All work is under `backend/`. After every task, `pytest backend/` must stay green. Each task
is its own commit for clean review and bisectability.

> Note on line numbers: line numbers cited below were verified directly against the current
> file contents at task-authoring time (via `grep -n`/`cat -n`) and match the PRD's citations
> exactly for every file in this sub-project. Still, always confirm with `grep -n` before
> editing — do not blindly trust a line number if the surrounding text doesn't match what's
> quoted here, in case the working tree has changed since this file was written.

---

## Tasks

### Task 1 — Add `PIPELINE_V1_2_STEPS` enum and delete the flat-shim block in `utils/constants.py`

   - **Files:** `backend/utils/constants.py`
   - **Goal:** (PRD §4a + §4b) Replace the bare `STEPS: dict[int, str]` with a typed `Enum`
     carrying `.number`/`.label`, and delete the entire "Backward-compat flat shims" block at
     the end of the file. Doing both in one task because the shim block's `Constants.STEPS =
     Constants.Pipeline.STEPS` line and the `Pipeline` class are edited together.
   - **Changes:**
     1. Replace the `Pipeline` class body (currently lines 25–33, ending right before the
        `# ── SSE stream result sentinel ──` comment) — i.e. remove the bare `STEPS: dict[int,
        str] = {...}` block:
        ```python
        # Before
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
        ```python
        # After
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
     2. Delete the entire flat-shim block at the end of the file (currently lines 139–162,
        from the `# ----...` banner comment through the final
        `Constants.ATHENA_CLIENT_SECRET_ENV_VAR = ...` line) — every one of these 18
        assignment lines plus the 3-line banner/TODO comment above them. The file must end
        right after the `Observability` class's last attribute
        (`DIM_CORRELATION_ID: str = "CorrelationId"`), with no trailing shim code.
   - **Acceptance criteria:**
     - `grep -n "STEPS\s*=\s*Constants.Pipeline.STEPS\|Backward-compat flat shims" backend/utils/constants.py` returns no matches.
     - `python -c "from utils.constants import Constants; s = Constants.Pipeline.PIPELINE_V1_2_STEPS.DETECT_TERMS; assert s.number == 2 and s.label == 'Finding difficult and medical terms'"` (run from `backend/`) succeeds with no error.
     - `python -c "from utils.constants import Constants; Constants.RESULT_SENTINEL"` (run from `backend/`) raises `AttributeError` (the flat shim is gone — this is the *expected*, correct post-state; full re-wiring of consumers happens in Tasks 2–3).
     - The file has no bare `STEPS` dict anywhere (`grep -n "STEPS: dict" backend/utils/constants.py` returns no matches).

---

### Task 2 — Migrate flat `Constants.<NAME>` consumers to namespaced form (production files)

   - **Files:**
     - `backend/routes/batch_jobs.py`
     - `backend/routes/care_plan.py`
     - `backend/routes/care_plan_jobs.py`
     - `backend/routes/worker.py`
     - `backend/models/batch_requests.py`
     - `backend/models/care_plan/versions/v1_2.py`
     - `backend/models/grading.py`
     - `backend/utils/scoring_methods.py`
     - `backend/services/external_api/athena_client.py`
   - **Goal:** (PRD §4a) After Task 1 deletes the flat-shim block, every production
     consumer of a flat `Constants.<NAME>` must be updated to its namespaced form, or the
     app will raise `AttributeError` at import/call time. This task does **not** touch
     `Constants.STEPS`/`Constants.Pipeline.STEPS` call sites — those are handled separately
     in Task 3 (full enum redesign, not a 1:1 rename).
   - **Changes** (verified current line numbers as of task authoring — re-`grep` first if
     your tree has drifted):
     1. `backend/routes/batch_jobs.py:77,81` — `Constants.MAX_BATCH_RUNS` → `Constants.Batch.MAX_BATCH_RUNS` (both occurrences, inside the same `if`/error-payload block).
     2. `backend/routes/care_plan.py:58` and `:174` — `Constants.GCS_BUCKET_ENV_VAR` → `Constants.Storage.GCS_BUCKET_ENV_VAR` (both `os.environ.get(...)` call sites).
     3. `backend/routes/care_plan.py:73` — `Constants.ALLOWED_EXTENSIONS` → `Constants.Uploads.ALLOWED_EXTENSIONS` (the `_allowed`-style extension-check line).
     4. `backend/routes/care_plan.py:117,118` — `Constants.MAX_FILE_COUNT` → `Constants.Uploads.MAX_FILE_COUNT` (both occurrences in the `if len(files) > ...` / error-message f-string).
     5. `backend/routes/care_plan.py:131` — `Constants.MAX_FILE_BYTES` → `Constants.Uploads.MAX_FILE_BYTES` (line 134–135 in this file already use the namespaced form for `MAX_AGGREGATE_FILE_BYTES` — leave those untouched, they need no change).
     6. `backend/routes/care_plan_jobs.py:81` — `Constants.MAX_FILE_BYTES` → `Constants.Uploads.MAX_FILE_BYTES` in the `if len(file_bytes) > ...` comparison (line 82's f-string already uses the namespaced form — leave it).
     7. `backend/routes/worker.py:33` — `Constants.PIPELINE_VERSION_V1_2` → `Constants.Pipeline.PIPELINE_VERSION_V1_2` in `PIPELINES = {...: run_care_plan_pipeline}`.
     8. `backend/routes/worker.py:232` — `Constants.ATHENA_PRACTICE_ID` → `Constants.Athena.PRACTICE_ID` in `practice_id = job.athena_practice_id or ...`.
     9. `backend/models/batch_requests.py:73,85` — `Constants.PIPELINE_VERSION_V1_2` → `Constants.Pipeline.PIPELINE_VERSION_V1_2` (both `version: str = ...` default-value fields, in `BatchJobsRequest` and `SingleJobRequest`).
     10. `backend/models/care_plan/versions/v1_2.py` — replace **all 5** occurrences each of `Constants.IMPORTANCE` and `Constants.SOURCE` (currently lines 43/44, 55/56, 65/66, 76/77, 91/92) with `Constants.Enums.IMPORTANCE` and `Constants.Enums.SOURCE` respectively, e.g.:
         ```python
         # Before
         importance: Constants.IMPORTANCE = Constants.IMPORTANCE.LOW
         source: Constants.SOURCE | None = None

         # After
         importance: Constants.Enums.IMPORTANCE = Constants.Enums.IMPORTANCE.LOW
         source: Constants.Enums.SOURCE | None = None
         ```
         Note: this file's lines 109/112 already use `Constants.CARE_PLAN_VERSIONS` — that flat name is migrated separately in Task 3 (it's bundled with the `Pipeline.STEPS` redesign per PRD §4a/§4b note), so leave 109/112 for Task 3.
     11. `backend/models/grading.py:42` — `Constants.GRADING_METHODS` → `Constants.Grading.GRADING_METHODS` in `for method in Constants.GRADING_METHODS:`.
     12. `backend/utils/scoring_methods.py:97–102` — prefix `Constants.Grading.` onto all 6 `Constants.GRADING_METHODS.<X>:` dict keys (`SMOG`, `FLESCH_KINCAID`, `DALE_CHALL`, `PEMAT`, `SAM`, `CDC_CCI`).
     13. `backend/services/external_api/athena_client.py:39,40` — `Constants.ATHENA_CLIENT_ID_ENV_VAR` → `Constants.EnvVars.ATHENA_CLIENT_ID`, `Constants.ATHENA_CLIENT_SECRET_ENV_VAR` → `Constants.EnvVars.ATHENA_CLIENT_SECRET`. (Note: this file already uses `Constants.Athena.BASE_URL` directly elsewhere — no change needed there.)
   - **Acceptance criteria:**
     - `python -m pytest backend/routes backend/models backend/utils backend/services -x -q` (or the equivalent full suite) does not fail with `AttributeError: type object 'Constants' has no attribute ...` for any of: `MAX_BATCH_RUNS`, `GCS_BUCKET_ENV_VAR`, `ALLOWED_EXTENSIONS`, `MAX_FILE_COUNT`, `MAX_FILE_BYTES`, `PIPELINE_VERSION_V1_2`, `ATHENA_PRACTICE_ID`, `IMPORTANCE`, `SOURCE`, `GRADING_METHODS`, `ATHENA_CLIENT_ID_ENV_VAR`, `ATHENA_CLIENT_SECRET_ENV_VAR`.
     - `grep -rn "Constants\.\(MAX_BATCH_RUNS\|GCS_BUCKET_ENV_VAR\|ALLOWED_EXTENSIONS\|MAX_FILE_COUNT\|MAX_FILE_BYTES\|PIPELINE_VERSION_V1_2\|ATHENA_PRACTICE_ID\|IMPORTANCE\|SOURCE\|GRADING_METHODS\|ATHENA_CLIENT_ID_ENV_VAR\|ATHENA_CLIENT_SECRET_ENV_VAR\)\b" backend/routes backend/models backend/utils backend/services --include="*.py"` returns zero matches (i.e. every remaining reference is already namespaced, e.g. `Constants.Batch.MAX_BATCH_RUNS`).

---

### Task 3 — Update `care_plan/v1_2/pipeline.py` to use `PIPELINE_V1_2_STEPS` enum members

   - **Files:** `backend/care_plan/v1_2/pipeline.py`
   - **Depends on:** Task 1 (the `PIPELINE_V1_2_STEPS` enum must exist first).
   - **Goal:** (PRD §4b) Replace every `Constants.STEPS[N]` indexing call and every bare-int
     `step=N` literal in `StepEvent`/`PipelineStepError` construction with named enum members
     via a new `_STEP` module alias. Also fix the `Constants.CARE_PLAN_VERSIONS` flat
     reference at the bottom of `iter_steps`.
   - **Changes:**
     1. Directly below the existing `from utils.constants import Constants` import (currently
        line 47), add:
        ```python
        from utils.constants import Constants

        _STEP = Constants.Pipeline.PIPELINE_V1_2_STEPS
        ```
     2. Replace the full step-emission block inside `iter_steps` (currently lines 174–228,
        covering Steps 2 through 5) — every `Constants.STEPS[2]` → `_STEP.DETECT_TERMS.label`
        (for the `label=` kwarg) / `_STEP.DETECT_TERMS.number` (for the `step=` kwarg and the
        first two positional args to `_call(...)`), and similarly `Constants.STEPS[3]` →
        `_STEP.SIMPLIFY_LANGUAGE`, `Constants.STEPS[4]` → `_STEP.CLARIFY_AND_ACTION`,
        `Constants.STEPS[5]` → `_STEP.STRUCTURE_DOCUMENT`. Exact before/after:
        ```python
        # Before
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
        ```python
        # After
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
     3. Fix the `CARE_PLAN_VERSIONS` flat reference (currently line 242):
        ```python
        # Before
        care_plan = CarePlan.from_pipeline_result(Constants.CARE_PLAN_VERSIONS.V1_2.value, result)

        # After
        care_plan = CarePlan.from_pipeline_result(Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2.value, result)
        ```
     4. Do not modify `models/pipeline_events.py` — `StepEvent.step` stays a plain `int`;
        `_STEP.<NAME>.number` already produces an `int`, so the dataclass contract is
        unchanged. Do not touch `routes/care_plan.py`'s `_STEP_MARKER_MAP` (a separate,
        unrelated int-keyed dict of `(Marker, function_name, span_name)` tuples).
   - **Acceptance criteria:**
     - `grep -n "Constants\.STEPS\|Constants\.CARE_PLAN_VERSIONS\b" backend/care_plan/v1_2/pipeline.py` returns no matches (the only `CARE_PLAN_VERSIONS` reference left should read `Constants.Pipeline.CARE_PLAN_VERSIONS`).
     - `grep -n "step=2\|step=3\|step=4\|step=5\|STEPS\[" backend/care_plan/v1_2/pipeline.py` returns no matches — every step reference goes through `_STEP.<NAME>`.
     - `python -m pytest backend/tests/care_plan -x -q` passes, and any test asserting `event.step == 2` (etc.) still passes unchanged (step numbers are numerically identical to before).

---

### Task 4 — Migrate flat `Constants.<NAME>` references in test files + delete `test_flat_shims_still_work`

   - **Files:**
     - `backend/tests/routes/test_worker_gcs_dataset.py`
     - `backend/tests/care_plan/test_pipeline_schema.py`
     - `backend/tests/models/test_care_plan.py`
     - `backend/tests/utils/test_scoring_methods.py`
     - `backend/tests/models/test_grading_model.py`
     - `backend/tests/utils/test_constants.py`
   - **Depends on:** Tasks 1–3 (the namespaced constants and the new enum must exist; the
     dict-based `Constants.STEPS` is gone, so any leftover flat reference would now error).
   - **Goal:** (PRD §4a, final test-file paragraph + §7) Apply the identical
     namespace-prefix mechanical substitution to test files, and delete the now-obsolete
     `test_flat_shims_still_work` test.
   - **Changes:**
     1. `backend/tests/routes/test_worker_gcs_dataset.py:74` — `Constants.RESULT_SENTINEL` → `Constants.Pipeline.RESULT_SENTINEL`.
     2. `backend/tests/care_plan/test_pipeline_schema.py:30,68` — `Constants.CARE_PLAN_VERSIONS` → `Constants.Pipeline.CARE_PLAN_VERSIONS` (both occurrences).
     3. `backend/tests/models/test_care_plan.py:42,45,66,71,77,80,86` — `Constants.CARE_PLAN_VERSIONS` → `Constants.Pipeline.CARE_PLAN_VERSIONS` (all 7 occurrences).
     4. `backend/tests/utils/test_scoring_methods.py:178,194,195` — `Constants.GRADING_METHODS` → `Constants.Grading.GRADING_METHODS` (all 3 occurrences).
     5. `backend/tests/models/test_grading_model.py:107–119` — prefix `Constants.Grading.` onto all 12 `Constants.GRADING_METHODS.<X>.value.value` references (`SMOG`, `FLESCH_KINCAID`, `DALE_CHALL`, `PEMAT`, `SAM`, `CDC_CCI`, each appearing once for "before" and once for "after"). (Note: this file's `build_grading` import/call at lines 7 and 104 is handled separately in Task 5 — do not rename it here.)
     6. `backend/tests/utils/test_constants.py` — delete the `test_flat_shims_still_work` function (currently lines 63–67) entirely:
        ```python
        # Delete entirely:
        def test_flat_shims_still_work():
            assert Constants.RESULT_SENTINEL == Constants.Pipeline.RESULT_SENTINEL
            assert Constants.MAX_BATCH_RUNS == Constants.Batch.MAX_BATCH_RUNS
            assert Constants.GRADING_METHODS is Constants.Grading.GRADING_METHODS
            assert Constants.ATHENA_BASE_URL == Constants.Athena.BASE_URL
        ```
        Leave all other test functions in this file untouched (`test_schema_namespace`,
        `test_uploads_namespace`, `test_deadlines_namespace`, `test_llm_namespace`,
        `test_athena_namespace`, `test_athena_source_kind_enum`, `test_storage_namespace`,
        `test_observability_namespace`, `test_env_vars_namespace_deduplicated`) — they already
        test namespaced access and need no change.
     7. In the same file, add one new lightweight test locking the new enum's shape (PRD §7
        recommendation):
        ```python
        def test_pipeline_v1_2_steps_enum():
            steps = Constants.Pipeline.PIPELINE_V1_2_STEPS
            assert steps.DETECT_TERMS.number == 2
            assert steps.DETECT_TERMS.label == "Finding difficult and medical terms"
            assert steps.READ_NOTE.number == 1
            assert steps.SIMPLIFY_LANGUAGE.number == 3
            assert steps.CLARIFY_AND_ACTION.number == 4
            assert steps.STRUCTURE_DOCUMENT.number == 5
        ```
   - **Acceptance criteria:**
     - `grep -rn "test_flat_shims_still_work" backend/tests` returns no matches.
     - `grep -n "test_pipeline_v1_2_steps_enum" backend/tests/utils/test_constants.py` shows the new test present.
     - `python -m pytest backend/tests/routes/test_worker_gcs_dataset.py backend/tests/care_plan/test_pipeline_schema.py backend/tests/models/test_care_plan.py backend/tests/utils/test_scoring_methods.py backend/tests/models/test_grading_model.py backend/tests/utils/test_constants.py -q` passes (note: `test_grading_model.py` will still reference `build_grading` until Task 5 renames it — that's expected at this point in the sequence, since Task 5 is independent and may land before or after this task; run the suite again after Task 5 to confirm everything together, per Task 7).

---

### Task 5 — Delete `_score_or_none` in `routes/care_plan.py` and rewrite its 4 test patch targets

   - **Files:**
     - `backend/routes/care_plan.py`
     - `backend/tests/utils/test_care_plan_markers.py`
   - **Goal:** (PRD §4c) Remove the one-line `_score_or_none` wrapper; call `score_text_safe`
     directly at its 2 call sites; repoint the 4 `unittest.mock.patch` targets in the test
     file from the deleted symbol to `routes.care_plan.score_text_safe`.
   - **Changes:**
     1. In `backend/routes/care_plan.py`, delete the function and its section comment
        (currently lines 49–52):
        ```python
        # Before
        # ── Scoring helpers ────────────────────────────────────────────────────────────
        def _score_or_none(text: str, label: str):
            """Thin wrapper so tests can patch scoring without touching the import."""
            return score_text_safe(text, label)
        ```
        Delete entirely — no replacement. (`score_text_safe` is already imported at line 22:
        `from utils.scoring import score_text_safe`.)
     2. In the same file, update the 2 call sites inside `run_care_plan_pipeline` (currently
        lines 253–254):
        ```python
        # Before
                        if grading_enabled:
                            before_score = _score_or_none(text, "before")
                            after_score  = _score_or_none(event.clarified, "after")

        # After
                        if grading_enabled:
                            before_score = score_text_safe(text, "before")
                            after_score  = score_text_safe(event.clarified, "after")
        ```
     3. In `backend/tests/utils/test_care_plan_markers.py`, rewrite all 4 patch targets
        (currently lines 140, 173, 235, 270 — each one is `patch("routes.care_plan._score_or_none", ...)` with a different `return_value`):
        ```python
        # Before (4 occurrences, differing only in return_value)
                patch("routes.care_plan._score_or_none", return_value={"composite": 72.5, "dimensions": {}}),
                patch("routes.care_plan._score_or_none", return_value=None),
                patch("routes.care_plan._score_or_none", return_value={"composite": 85.0, "dimensions": {}}),
                patch("routes.care_plan._score_or_none", return_value=None),

        # After
                patch("routes.care_plan.score_text_safe", return_value={"composite": 72.5, "dimensions": {}}),
                patch("routes.care_plan.score_text_safe", return_value=None),
                patch("routes.care_plan.score_text_safe", return_value={"composite": 85.0, "dimensions": {}}),
                patch("routes.care_plan.score_text_safe", return_value=None),
        ```
        Only the patched dotted path changes — leave every other line in
        `test_pipeline_marker_has_source_kind_grading_enabled_is_batch`,
        `test_pipeline_marker_batch_dimensions`,
        `test_grading_run_marker_fired_when_grading_enabled`, and
        `test_grading_run_marker_not_fired_when_grading_disabled` untouched (do not change the
        adjacent `build_grading` patch lines in this same file — those are handled in Task 6).
   - **Acceptance criteria:**
     - `grep -rn "_score_or_none" backend --include="*.py"` returns zero matches anywhere in the repo.
     - `grep -n "patch(\"routes.care_plan.score_text_safe\"" backend/tests/utils/test_care_plan_markers.py` shows exactly 4 matches.
     - `python -m pytest backend/tests/utils/test_care_plan_markers.py -q` passes.

---

### Task 6 — Delete the dead `_juno_error_logger` shim in `routes/care_plan.py`

   - **Files:** `backend/routes/care_plan.py`
   - **Goal:** (PRD §4d) Remove the unused logger-name compatibility shim. Verified dead:
     `grep -n "_juno_error_logger" backend/routes/care_plan.py` returns only its own
     definition line, and no test anywhere asserts against the logger name
     `"utils.juno_logger"`. No test changes are required for this task.
   - **Changes:**
     1. Replace (currently lines 41–44):
        ```python
        # Before
        logger = logging.getLogger(__name__)
        # Secondary error logger routed to utils.juno_logger for compatibility with existing
        # log-assertion tests that predate the Markers migration.
        _juno_error_logger = logging.getLogger("utils.juno_logger")
        ```
        with:
        ```python
        # After
        logger = logging.getLogger(__name__)
        ```
     2. Do not touch anything else nearby — the `care_plan_bp = Blueprint(...)` line and
        everything below it stays as-is. Do not touch `JunoLogger`, `utils/juno_logger.py`,
        or `app.py` (out of scope per PRD §3 Non-Goals — that is SP13's territory).
   - **Acceptance criteria:**
     - `grep -rn "_juno_error_logger\|utils\.juno_logger" backend --include="*.py"` returns zero matches.
     - `python -m pytest backend/tests/routes/test_care_plan.py backend/tests/utils/test_care_plan_markers.py -q` (or the relevant test files covering `routes/care_plan.py`) passes unchanged.

---

### Task 7 — Rename `build_grading` to `build_grading_with_before_after_score` (all 14 sites)

   - **Files:**
     - `backend/models/grading.py`
     - `backend/models/__init__.py`
     - `backend/routes/care_plan.py`
     - `backend/routes/grading.py`
     - `backend/tests/models/test_grading_model.py`
     - `backend/tests/routes/test_grading_route.py`
     - `backend/tests/utils/test_care_plan_markers.py`
   - **Goal:** (PRD §4e, `[RESOLVED]` per §9 Q1) Pure rename, no behavior/signature/location
     change. This task is independent of Tasks 1–6 (touches a disjoint set of symbols) and
     can be done in parallel with them, but is listed last for commit-ordering clarity.
   - **Changes** (verified current line numbers — re-`grep "build_grading" backend -r
     --include="*.py"` before editing to confirm none have drifted):
     1. `backend/models/grading.py:28` — definition: `def build_grading(` → `def build_grading_with_before_after_score(`.
     2. `backend/models/__init__.py:7` — import: `from .grading import Grading, GradingEntry, build_grading` → `from .grading import Grading, GradingEntry, build_grading_with_before_after_score`.
     3. `backend/models/__init__.py:31` — `__all__` entry: `"build_grading",` → `"build_grading_with_before_after_score",`.
     4. `backend/routes/care_plan.py:24` — import: `from models.grading import Grading, build_grading, GRADING_VERSION  # noqa: F401` → `from models.grading import Grading, build_grading_with_before_after_score, GRADING_VERSION  # noqa: F401`.
     5. `backend/routes/care_plan.py:258` — call: `result = build_grading(before_score, text, after_score, event.clarified)` → `result = build_grading_with_before_after_score(before_score, text, after_score, event.clarified)`.
     6. `backend/routes/grading.py:11` — import: `from models.grading import build_grading` → `from models.grading import build_grading_with_before_after_score`.
     7. `backend/routes/grading.py:68` — call: `grading = build_grading(before_score, raw_text, after_score, clarified_text or None)` → `grading = build_grading_with_before_after_score(before_score, raw_text, after_score, clarified_text or None)`.
     8. `backend/routes/grading.py:90` — call: `grading = build_grading(before_score, text, after_score, clarified_text or None)` → `grading = build_grading_with_before_after_score(before_score, text, after_score, clarified_text or None)`.
     9. `backend/tests/models/test_grading_model.py:7` — import: `from models.grading import Grading, GradingEntry, build_grading` → `from models.grading import Grading, GradingEntry, build_grading_with_before_after_score`.
     10. `backend/tests/models/test_grading_model.py:104` — call: `grading = build_grading(before_score, FIXTURE_TEXT, after_score, FIXTURE_CLARIFIED)` → `grading = build_grading_with_before_after_score(before_score, FIXTURE_TEXT, after_score, FIXTURE_CLARIFIED)`. (Optional, non-load-bearing cosmetic follow-up: the enclosing test function name at line 100, `test_build_grading_returns_same_entries_and_no_descriptions`, may also be renamed to `test_build_grading_with_before_after_score_returns_same_entries_and_no_descriptions` — pytest discovers it by file/prefix regardless, so this is not required for correctness.)
     11. `backend/tests/routes/test_grading_route.py:185` — patch target: `patch("routes.grading.build_grading", return_value=mock_grading):` → `patch("routes.grading.build_grading_with_before_after_score", return_value=mock_grading):`.
     12. `backend/tests/utils/test_care_plan_markers.py:141,174,236,271` — 4 patch targets, e.g. `patch("routes.care_plan.build_grading", return_value=grading_stub),` → `patch("routes.care_plan.build_grading_with_before_after_score", return_value=grading_stub),` (lines 141 and 236 use `return_value=grading_stub`; lines 174 and 271 use `return_value=MagicMock()` — keep each line's existing `return_value` unchanged, only repoint the dotted patch path).
   - **Acceptance criteria:**
     - `grep -rn "\bbuild_grading\b" backend --include="*.py"` returns zero matches (every occurrence is now `build_grading_with_before_after_score`).
     - `grep -rn "build_grading_with_before_after_score" backend --include="*.py" | wc -l` reports 14 (1 def + 2 imports/`__all__` in `models/__init__.py` + 1 import + 1 call in `care_plan.py` + 1 import + 2 calls in `routes/grading.py` + 1 import + 1 call in `test_grading_model.py` + 1 patch in `test_grading_route.py` + 4 patches in `test_care_plan_markers.py` = 14).
     - `python -m pytest backend/tests/models/test_grading_model.py backend/tests/routes/test_grading_route.py backend/tests/utils/test_care_plan_markers.py -q` passes.

---

### Task 8 — Final verification sweep: full suite + PRD §7 grep checks

   - **Files:** none (verification only — no edits in this task).
   - **Depends on:** Tasks 1–7, all complete.
   - **Goal:** Confirm the full backend test suite is green and the two mandatory grep
     sweeps from PRD §7 "Manual checks" #3 and #4 return zero matches, proving no flat
     constant name, `_score_or_none`, or `_juno_error_logger` reference survives anywhere in
     `backend/`.
   - **Steps:**
     1. Run the full backend test suite from the repo root (or `backend/`, matching the
        project's existing pytest invocation convention):
        ```bash
        python -m pytest backend/
        ```
        Must exit 0 with no failures and, specifically, no
        `AttributeError: type object 'Constants' has no attribute ...` anywhere in the
        output (PRD §7 manual check #2).
     2. Run the flat-constants grep sweep (PRD §7 manual check #3) — must return **zero**
        matches:
        ```bash
        grep -rn "Constants\.\(RESULT_SENTINEL\|MAX_BATCH_RUNS\|ALLOWED_EXTENSIONS\|MAX_FILE_BYTES\|MAX_FILE_COUNT\|MAX_AGGREGATE_FILE_BYTES\|PIPELINE_VERSION_V1_2\|STEPS\|CARE_PLAN_VERSIONS\|GRADING_METHODS\|SOURCE\|IMPORTANCE\|ATHENA_BASE_URL\|ATHENA_PRACTICE_ID\|GCS_BUCKET_ENV_VAR\|CARE_PLAN_DEFAULT_VERSION_ENV_VAR\|CARE_PLAN_DEFAULT_VERSION_FALLBACK\|ATHENA_CLIENT_ID_ENV_VAR\|ATHENA_CLIENT_SECRET_ENV_VAR\)\b" backend --include="*.py"
        ```
     3. Run the dead-shim grep sweep (PRD §7 manual check #4) — must return **zero**
        matches:
        ```bash
        grep -rn "_score_or_none\|_juno_error_logger" backend --include="*.py"
        ```
     4. (Optional but recommended, mirrors PRD §7 manual check #1) Exercise
        `CarePlanV1_2Pipeline().run(<sample text>)` (or run the existing pipeline tests under
        `backend/tests/care_plan/`) and confirm step progress events still report steps 2–5
        with the unchanged labels `"Finding difficult and medical terms"`,
        `"Simplifying language"`, `"Clarifying actions and numbers"`,
        `"Organizing your care plan"`.
   - **Acceptance criteria:**
     - `pytest backend/` exits 0, full suite green.
     - Both grep commands in steps 2 and 3 produce empty output.
     - No new `build_grading` (non-suffixed) matches remain (sanity cross-check with Task 7's
       acceptance criteria): `grep -rn "\bbuild_grading\b" backend --include="*.py"` is empty.

---

## Summary of what requires you (not a dev agent)

None. Per PRD §8 ("Manual Intervention Required From You"), this is a fully self-contained
internal refactor — no environment variables, secrets, GCP console actions, deploy steps, or
data migrations are involved anywhere in this sub-project. Every change is source-only
(`backend/`) and fully verifiable by `pytest backend/` plus the two grep sweeps in Task 8.
There is nothing in SP11 that needs a human to click a button, approve a manual step, or
provide an external credential/value.
