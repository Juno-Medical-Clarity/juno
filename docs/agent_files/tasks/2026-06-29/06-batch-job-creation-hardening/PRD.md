# PRD: SP06 — Batch + Job-Creation Route Hardening

**Sub-project:** SP06  
**Branch context:** `users/tejitpabari/llm-code-check`  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started

---

## 1. Problem

The two primary job-creation routes (`POST /care_plan/batch/jobs` in `routes/batch_jobs.py` and `POST /care_plan/jobs` in `routes/care_plan_jobs.py`) parse request bodies manually using raw dict access, duplicate validation logic, and inconsistent error handling. The supporting module `routes/batch.py` has drifted into a utilities role but retains a dead route stub and five helper functions with zero external callers.

**Specific issues as verified in the source files:**

1. **Raw body parsing and isinstance ladders.** `create_care_plan_batch_jobs` (batch_jobs.py:22-41) uses `request.get_json() or {}`, then `body.get("selections")` with a manual `isinstance` check, then inline `body.get("version", "v1-2")` with a hardcoded string that should reference `Constants.PIPELINE_VERSION_V1_2`. Per-selection field access continues raw inside the loop (batch_jobs.py:147-151). There is no validated schema; any malformed selection silently passes the outer check and surfaces as a `KeyError` or wrong-type value deeper in the handler.

2. **`grading_enabled` bool-coercion is duplicated three times.** The truthy-set pattern `str(raw).strip().lower() in {"1","true","yes","on"}` appears at:
   - `routes/batch.py:32-35` (`_grading_enabled`)
   - `routes/care_plan.py:241-248` (`_grading_enabled_from_request`)
   - `routes/batch_jobs.py:39-41` (inline)

3. **No outer try/except on either handler.** `create_care_plan_batch_jobs` and `create_care_plan_job` have inner try/except blocks only around `_resolve_requested_runs` and `enqueue_job`. Code between those points — including `create_job_doc`, `_batch_timestamp`, and the athena required-field block — can raise and surface as a bare 500 with an unstructured Flask traceback response.

4. **No Markers instrumentation at the entry point.** Neither route records a Markers event. There is no observability data on batch size, source-kind mix (athena vs. GCS), grading flag, or pipeline version at the HTTP layer.

5. **Job doc construction uses raw inline dicts.** `batch_jobs.py:89-119` (GCS doc) and `batch_jobs.py:171-202` (Athena doc) each construct a 20-key dict inline. `care_plan_jobs.py:101-120` does the same. SP05 introduces `JobDoc.for_gcs_dataset()`, `JobDoc.for_athena()`, and `JobDoc.for_single()` factories specifically to replace these constructions.

6. **Needless single-use pass-through locals.** `batch_jobs.py:147-151` extracts `practice_id`, `patient_id`, `api_path`, `encounter_id`, `document_id` into local variables that are used only to construct the inline job_doc dict on the very next statement. These disappear naturally when the Selection model and JobDoc factory are introduced.

7. **`ATHENA_KINDS` function-local set.** `batch_jobs.py:44` defines `ATHENA_KINDS = {"athena_encounter", "athena_clinical_doc"}` as a function-local constant. SP02 introduces `Constants.Athena.AthenaSourceKind` for exactly this purpose.

8. **`batch.py` is a utilities module masquerading as a route file.** Its only live route (`/care_plan/batch`) is a 410 deprecated stub (removal owned by SP07). The file exports `_resolve_requested_runs` and `_batch_timestamp` (live, used by batch_jobs.py) alongside five dead helpers with no external references: `_pipeline_for_version`, `_combined_text_for_dataset_input`, `_output_name`, `_batch_progress_error`, `_pipeline_kwargs_for_batch`. The file should be renamed to `routes/batch_utils.py` to signal its utility role, and the dead helpers should be deleted.

---

## 2. Goals

1. Replace manual body parsing in `create_care_plan_batch_jobs` with a strict Pydantic request model (`BatchJobsRequest`) that validates the complete request in one place.
2. Replace manual input resolution in `create_care_plan_job` with a Pydantic request model (`SingleJobRequest`) that covers the JSON-body path; multipart/form-data path remains delegated to `_resolve_input_for_job` (no change to that flow).
3. Model the `selections` list as a discriminated union (`Selection`) on `input_source_kind`, with per-kind validators enforcing required Athena fields — eliminating the manual checks at batch_jobs.py:153-168.
4. Introduce one shared Pydantic field validator for `grading_enabled` on the request models; delete the three copies in batch.py, care_plan.py (coordinated with SP07/SP08), and the inline version in batch_jobs.py.
5. Wrap the full handler body in an outer try/except in both handlers, mapping to `make_error_response(ErrorCode.INTERNAL_ERROR)` (SP01); preserve the existing inner try/except blocks around `_resolve_requested_runs` and `enqueue_job`.
6. Add a `Markers.Batch` leaf in `utils/markers/markers.py` and instrument both handlers with dimensions: `batch_size`, `athena_count`, `gcs_count`, `grading_enabled`, `version`.
7. Replace all three inline job-doc dict constructions with `JobDoc.for_gcs_dataset()`, `JobDoc.for_athena()`, and `JobDoc.for_single()` factories from SP05.
8. Replace the `ATHENA_KINDS` function-local set with `Constants.Athena.AthenaSourceKind` from SP02.
9. Rename `routes/batch.py` to `routes/batch_utils.py`; delete five dead helpers; update `routes/__init__.py` to import `batch_bp` from the new path. Add section-header comments to `batch_jobs.py` to delineate GCS and Athena sections.

---

## 3. Non-Goals

- No changes to the 410 stub route in `batch.py` / `batch_utils.py` — that removal is owned by SP07.
- No changes to `_resolve_requested_runs` or `_batch_timestamp` logic — they are working and stay in `batch_utils.py` as-is.
- No changes to the multipart/form-data handling path in `care_plan_jobs.py` (`_resolve_input_for_job`, `_resolve_uploaded_files`, `upload_combined_pdf`, etc.).
- No changes to `care_plan.py`'s `_grading_enabled_from_request` if SP07 or SP08 already owns that file in the same sprint. The dependency is noted in section 9; coordination is required.
- No SSE-related changes. The deprecated SSE endpoint is SP07's scope.
- No changes to the frontend request shape. The JSON schema for `POST /care_plan/batch/jobs` and `POST /care_plan/jobs` must remain byte-for-byte identical from the caller's perspective.
- No new `ErrorCode` values — this SP uses existing codes (`INPUT_VALIDATION_ERROR`, `BATCH_INVALID_SELECTION`, `BATCH_TOO_LARGE`, `INTERNAL_ERROR`) already in the registry.
- No changes to how `enqueue_job` is called or what arguments it receives.

---

## 4. Architecture Decisions

### 4a. Selection Discriminated Union and BatchJobsRequest

**File:** `backend/routes/batch_jobs.py` (new models, or a companion `backend/models/batch_requests.py`)

The request body for `POST /care_plan/batch/jobs` becomes a strict Pydantic model. The `selections` list is a discriminated union over `input_source_kind`. Pydantic v2 `model_validator` enforces required Athena fields per kind, replacing the manual checks at batch_jobs.py:153-168.

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, model_validator
from utils.constants import Constants

# ── Grading-enabled shared validator ─────────────────────────────────────────

_TRUTHY = {"1", "true", "yes", "on"}

def _coerce_grading_enabled(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in _TRUTHY


# ── Per-kind selection models ─────────────────────────────────────────────────

class AthenaEncounterSelection(BaseModel):
    input_source_kind: Literal["athena_encounter"]
    athena_practice_id: str = ""
    athena_patient_id: str = ""
    athena_encounter_id: str
    athena_document_id: str | None = None
    athena_api_path: str = ""

    @model_validator(mode="after")
    def _require_encounter_id(self) -> "AthenaEncounterSelection":
        if not self.athena_encounter_id:
            raise ValueError("athena_encounter requires athena_encounter_id")
        return self


class AthenaClinicalDocSelection(BaseModel):
    input_source_kind: Literal["athena_clinical_doc"]
    athena_practice_id: str = ""
    athena_patient_id: str = ""
    athena_encounter_id: str | None = None
    athena_document_id: str
    athena_api_path: str = ""

    @model_validator(mode="after")
    def _require_document_id(self) -> "AthenaClinicalDocSelection":
        if not self.athena_document_id:
            raise ValueError("athena_clinical_doc requires athena_document_id")
        return self


class GcsDatasetSelection(BaseModel):
    input_source_kind: Literal["gcs_dataset"]
    group: str
    files: list[str]
    inputs: str | list[str]   # "all" or list of input_ids

    @model_validator(mode="after")
    def _validate_fields(self) -> "GcsDatasetSelection":
        if not self.group:
            raise ValueError("Selection is missing group")
        if not self.files or not all(isinstance(f, str) and f for f in self.files):
            raise ValueError(f"Selection for {self.group} must include files")
        if self.inputs != "all" and not (
            isinstance(self.inputs, list)
            and all(isinstance(i, str) for i in self.inputs)
        ):
            raise ValueError(f"Selection for {self.group} must include inputs")
        return self


Selection = Annotated[
    Union[AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection],
    Field(discriminator="input_source_kind"),
]


# ── Top-level request model ───────────────────────────────────────────────────

class PipelineVersion(str):
    pass

class BatchJobsRequest(BaseModel):
    selections: list[Selection] = Field(min_length=1)
    version: str = Constants.PIPELINE_VERSION_V1_2
    grading_enabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_grading(cls, data):
        if isinstance(data, dict) and "grading_enabled" in data:
            data["grading_enabled"] = _coerce_grading_enabled(data["grading_enabled"])
        return data
```

**Old vs. new in the handler:**

| Before | After |
|---|---|
| `body = request.get_json(silent=True) or {}` + isinstance checks (lines 22-36) | `BatchJobsRequest.model_validate(request.get_json(silent=True) or {})` inside outer try/except; `ValidationError` → `make_error_response(ErrorCode.INPUT_VALIDATION_ERROR)` |
| `version = body.get("version", "v1-2")` (line 38, hardcoded string) | `req.version` — default lives in the model, references `Constants.PIPELINE_VERSION_V1_2` |
| `grading_enabled` inline coercion (lines 39-41) | `req.grading_enabled` — coerced in model validator |
| `ATHENA_KINDS = {"athena_encounter","athena_clinical_doc"}` (line 44) | Partition via `isinstance(sel, (AthenaEncounterSelection, AthenaClinicalDocSelection))` |
| Manual per-field access (lines 147-151) + required-field checks (153-168) | Eliminated — fields come from typed model attributes; validation happens at model parse time |

---

### 4b. SingleJobRequest for care_plan_jobs.py

**File:** `backend/routes/care_plan_jobs.py`

The `POST /care_plan/jobs` endpoint accepts multipart form data or JSON. The JSON-body path (`text`, `doc_id`) does not currently have a model. Add a lightweight model to cover the JSON fields shared by both paths:

```python
class SingleJobRequest(BaseModel):
    version: str = Constants.PIPELINE_VERSION_V1_2
    grading_enabled: bool = True   # Note: default is True here (matches existing _grading_enabled_from_request default)

    @model_validator(mode="before")
    @classmethod
    def _coerce_grading(cls, data):
        if isinstance(data, dict) and "grading_enabled" in data:
            data["grading_enabled"] = _coerce_grading_enabled(data["grading_enabled"])
        return data
```

`_resolve_input_for_job` continues to handle the multipart dispatch (files, text, doc_id). The `grading_enabled` value it currently reads via `_grading_enabled_from_request()` is replaced by reading `SingleJobRequest.grading_enabled` from a parsed model instead. The import of `_grading_enabled_from_request` from `care_plan.py` is removed from `care_plan_jobs.py`.

---

### 4c. Shared `_coerce_grading_enabled` and Deletion of Three Copies

**Canonical location:** `backend/models/batch_requests.py` (or inline at top of the request model file, imported by whoever needs it).

The `_TRUTHY` set and `_coerce_grading_enabled` function are defined once. The three copies to delete:

| File | Symbol | Action |
|---|---|---|
| `routes/batch.py` (→ `batch_utils.py`) | `_grading_enabled` (lines 32-35) | Delete. Not called externally. |
| `routes/care_plan.py` | `_grading_enabled_from_request` (lines 241-248) | Delete **only if SP07/SP08 do not touch this file first** — see section 9, Q2. |
| `routes/batch_jobs.py` | Inline coercion (lines 39-41) | Replaced by model validator. |

---

### 4d. Outer try/except on Both Handlers

**Files:** `backend/routes/batch_jobs.py`, `backend/routes/care_plan_jobs.py`

Wrap the entire handler body (after authentication) in:

```python
try:
    # ... all existing handler logic ...
except Exception:
    logger.exception("<handler_name>: unexpected error")
    return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
```

The existing inner try/except blocks around `_resolve_requested_runs` and `enqueue_job` are kept as-is — they provide more specific error codes (`BATCH_INVALID_SELECTION`, `INTERNAL_ERROR` with job-specific log context). The outer try/except is a safety net for everything else.

In `create_care_plan_job`, the existing try/except around `_resolve_input_for_job` (lines 86-93) is folded into the outer block; its catch clause is preserved as a local catch with `INPUT_VALIDATION_ERROR`.

---

### 4e. Markers.Batch Leaf

**File:** `backend/utils/markers/markers.py`

Add a `Batch` class alongside the existing `CarePlan`, `Grading`, and `Http` classes:

```python
class Batch:
    @code_marker("batch.create_jobs")
    class CreateJobs(CodeMarker): pass

    @code_marker("batch.create_single_job")
    class CreateSingleJob(CodeMarker): pass
```

SP08 owns the broader Markers registry for sweep-level metrics. SP06 owns this `Batch` leaf. SP08 should not add a `Batch` leaf; SP06 adds it first.

**Instrumentation in `create_care_plan_batch_jobs`:**

```python
def create_care_plan_batch_jobs(user_id: str):
    def _handler(scope: Scope):
        req = ...  # parse + validate
        scope.add_many({
            "batch_size": total_count,
            "athena_count": len(athena_selections),
            "gcs_count": len(runs),
            "grading_enabled": req.grading_enabled,
            "version": req.version,
        })
        # ... rest of handler ...
        return jsonify({...}), 202
    return Markers.Batch.CreateJobs.execute(_handler)
```

Dimensions are added to the scope after selections are partitioned so that counts are accurate. `Markers.Batch.CreateSingleJob` is used in `create_care_plan_job` with dimensions `grading_enabled` and `version`.

---

### 4f. JobDoc Factory Substitution

**Files:** `backend/routes/batch_jobs.py`, `backend/routes/care_plan_jobs.py`

Depends on SP05. The three inline dict constructions are replaced:

| Location | Before | After |
|---|---|---|
| `batch_jobs.py:89-119` | 20-key inline dict for GCS dataset | `JobDoc.for_gcs_dataset(user_id, batch_run_id, batch_group_id, group, input_id, files, version, grading_enabled, now)` |
| `batch_jobs.py:171-202` | 20-key inline dict for Athena | `JobDoc.for_athena(user_id, batch_run_id, athena_batch_group_id, sel, version, grading_enabled, now)` where `sel` is the typed `Selection` model |
| `care_plan_jobs.py:101-120` | Spread `**input_fields` dict with metadata | `JobDoc.for_single(user_id, trace_id, input_fields, now)` |

The exact factory signatures are defined by SP05. SP06's implementation should import from `models.job` and call whichever signatures SP05 exposes. If SP05 signatures differ from what is listed above, the SP06 implementor adjusts the call sites — the factory approach is locked, the exact parameter names are SP05's decision.

---

### 4g. Rename batch.py → batch_utils.py

**Files affected:**
- `routes/batch.py` → `routes/batch_utils.py` (rename)
- `routes/__init__.py` line 2: `from routes.batch import batch_bp` → `from routes.batch_utils import batch_bp`
- `routes/batch_jobs.py` line 11: `from routes.batch import _resolve_requested_runs, _batch_timestamp` → `from routes.batch_utils import _resolve_requested_runs, _batch_timestamp`

**Dead helpers to delete from `batch_utils.py`** (verify zero external refs before deleting):

| Function | Lines | External callers (verified) |
|---|---|---|
| `_pipeline_for_version` | 38-41 | None |
| `_combined_text_for_dataset_input` | 89-97 | None |
| `_output_name` | 100-109 | None |
| `_batch_progress_error` | 112-121 | None |
| `_pipeline_kwargs_for_batch` | 124-133 | None |

The 410 stub route `care_plan_batch_sse_deprecated` (lines 19-25) is **kept** — its removal is SP07's scope.

Add a file-level docstring update: `"""Batch utilities: timestamp helper, GCS selection resolver, and deprecated 410 stub (removal: SP07)."""`

---

### 4h. Section-Header Comments in batch_jobs.py

Add section-header comments at the GCS and Athena loop boundaries for readability:

```python
# ── Parse and validate request ───────────────────────────────────────────────
# ── Partition selections ─────────────────────────────────────────────────────
# ── Resolve GCS runs ────────────────────────────────────────────────────────
# ── Check total job count ───────────────────────────────────────────────────
# ── GCS dataset job docs ────────────────────────────────────────────────────
# ── Athena job docs ─────────────────────────────────────────────────────────
```

(The GCS and Athena headers already exist in the current file for some sections. Standardize all of them.)

---

## 5. API Change Summary

The external JSON request shape is **unchanged**. All changes are internal parsing and validation. The response shape for success cases is unchanged. The response shape for error cases becomes more specific for malformed selection objects (previously some invalid selections caused vague 500s; now they return structured 400s via the model validator).

**`POST /care_plan/batch/jobs` — request body schema:**

```json
{
  "selections": [
    {
      "input_source_kind": "athena_encounter",
      "athena_practice_id": "195900",
      "athena_patient_id": "1",
      "athena_encounter_id": "12345",
      "athena_api_path": "/v1/..."
    },
    {
      "input_source_kind": "athena_clinical_doc",
      "athena_practice_id": "195900",
      "athena_patient_id": "1",
      "athena_document_id": "67890",
      "athena_api_path": "/v1/..."
    },
    {
      "input_source_kind": "gcs_dataset",
      "group": "sp1",
      "files": ["question.txt", "note.txt"],
      "inputs": "all"
    }
  ],
  "version": "v1-2",
  "grading_enabled": false
}
```

The only behavioral change visible to callers: previously, a selection with `input_source_kind: "athena_encounter"` and a missing `athena_encounter_id` would pass the outer body check, then fail mid-loop returning a 400 from the manual check at line 155. Under the new model, the same input fails at model parse time with `INPUT_VALIDATION_ERROR` and the same 400 status — message is slightly different but the HTTP contract (400, structured error response) is identical.

**`POST /care_plan/jobs` — request body schema (JSON path only):**

```json
{
  "text": "...",
  "version": "v1-2",
  "grading_enabled": true
}
```

or

```json
{
  "doc_id": "abc123",
  "version": "v1-2",
  "grading_enabled": "true"
}
```

String values for `grading_enabled` continue to be accepted (coerced via the model validator). Multipart form data path is unchanged.

---

## 6. Frontend Change Summary

No frontend code changes are required. The request JSON shape accepted by both endpoints is identical to the current shape. The response JSON shape for success cases (`{"batch_run_id": "...", "job_ids": [...]}` and `{"job_id": "..."}`) is unchanged.

The only frontend-visible behavior improvement: error responses for malformed requests are now consistently structured `ApiResponse` objects with `INPUT_VALIDATION_ERROR` or `BATCH_INVALID_SELECTION` codes rather than bare Flask 500 tracebacks. This benefits error display in `CarePlanJobPage.tsx` but requires no code changes there.

---

## 7. Testing

### Backend unit tests

**`backend/tests/routes/test_batch_jobs.py`** — add or update:

- `test_missing_selections_returns_400`: POST with `{}` body; assert 400, `error.code == "INPUT_VALIDATION_ERROR"`.
- `test_empty_selections_returns_400`: POST with `{"selections": []}` body; assert 400.
- `test_athena_encounter_missing_encounter_id_returns_400`: POST with a selection of kind `athena_encounter` but no `athena_encounter_id`; assert 400, `error.code == "INPUT_VALIDATION_ERROR"`.
- `test_athena_clinical_doc_missing_document_id_returns_400`: same for `athena_clinical_doc` + missing `athena_document_id`.
- `test_grading_enabled_string_coercion`: POST with `{"grading_enabled": "yes", "selections": [...]}` (valid selection); assert the job doc written to Firestore has `grading_enabled: True`.
- `test_version_defaults_to_v1_2`: POST with no `version` key; assert job doc has `input_version == "v1-2"`.
- `test_unhandled_exception_returns_500_json`: mock `create_job_doc` to raise an unexpected `RuntimeError`; assert response is 500 with `ApiResponse` envelope, not a Flask HTML traceback.

**`backend/tests/routes/test_care_plan_jobs.py`** — add:

- `test_grading_enabled_false_string_coercion`: POST JSON `{"text": "hello", "grading_enabled": "false"}`; assert job doc has `grading_enabled: False`.
- `test_unhandled_exception_returns_500_json`: mock `create_job_doc` to raise; assert structured 500 response.

**`backend/tests/utils/test_markers.py`** — add:

- `test_batch_create_jobs_marker_registered`: assert `Markers.Batch.CreateJobs.name() == "batch.create_jobs"`.
- `test_batch_create_single_job_marker_registered`: assert `Markers.Batch.CreateSingleJob.name() == "batch.create_single_job"`.

**`backend/tests/routes/test_batch_utils.py`** (rename from `test_batch.py` if it exists) — verify:

- `_pipeline_for_version`, `_combined_text_for_dataset_input`, `_output_name`, `_batch_progress_error`, `_pipeline_kwargs_for_batch` no longer exist in the module (import attempts raise `ImportError` or `AttributeError`).
- `_resolve_requested_runs` and `_batch_timestamp` are still importable from `routes.batch_utils`.

### Manual integration tests

1. POST `/care_plan/batch/jobs` with an `athena_encounter` selection missing `athena_encounter_id`; confirm 400 response with `error.code: "INPUT_VALIDATION_ERROR"` and a clear `details` message.
2. POST `/care_plan/batch/jobs` with `"grading_enabled": "on"`; confirm jobs are created with `grading_enabled: true` in Firestore.
3. POST `/care_plan/batch/jobs` with a valid mixed selection (one GCS + one Athena); confirm both job docs are created in Firestore and both are enqueued.
4. POST `/care_plan/jobs` with JSON body `{"text": "hello"}` (no grading_enabled); confirm the job doc's `grading_enabled` matches the `SingleJobRequest` default (`true`).
5. Confirm that `GET /care_plan/batch` still returns 410 (the deprecated stub in `batch_utils.py` is still live).

---

## 8. Manual Intervention Required

None. All changes are code-only. No GCS bucket configuration, no Cloud Run env vars, no Firestore schema migration. The rename of `batch.py` → `batch_utils.py` is a file system rename with import updates — no deploy-time coordination needed.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Whether `BatchJobsRequest` and related models live in `routes/batch_jobs.py` directly or in a new `backend/models/batch_requests.py`. | [RESOLVED: place in `backend/models/batch_requests.py` for consistency with the models/ folder reorg (SP03). Import into `routes/batch_jobs.py` and `routes/care_plan_jobs.py`.] |
| Q2 | Whether to delete `care_plan.py`'s `_grading_enabled_from_request` as part of this SP. | [OPEN: if SP07 or SP08 also modifies `routes/care_plan.py`, the deletion must be coordinated. Preferred: SP06 removes the import from `care_plan_jobs.py` and leaves the function in `care_plan.py` as a stub for SP07/SP08 to clean up. Mark with a `# TODO(SP07): remove` comment.] |
| Q3 | Whether the external request shape for `gcs_dataset` selections changes. Current raw selection fields are `group`, `files`, `inputs` (no `input_source_kind`). | [OPEN: the frontend currently sends GCS selections without an `input_source_kind` field. The discriminated union requires `input_source_kind` to be present. Two options: (a) add `input_source_kind: "gcs_dataset"` to GCS selections on the frontend (breaking change to request shape); (b) treat GCS selections as the fallback (any selection without a recognized `input_source_kind` is treated as a GCS selection). Option (b) keeps the frontend contract unchanged. Confirm with frontend before implementation.] |
| Q4 | Exact factory signatures for `JobDoc.for_gcs_dataset()`, `JobDoc.for_athena()`, and `JobDoc.for_single()`. | [DEFERRED to SP05. SP06 must read SP05's final `models/job.py` before wiring the factory calls. If SP05 and SP06 are implemented concurrently, use stub wrappers and merge at the end.] |
| Q5 | Whether `Markers.Batch` dimensions should include `source_kind` as a string (e.g. `"mixed"`, `"all_athena"`, `"all_gcs"`) in addition to raw counts. | [OPEN: raw counts (`athena_count`, `gcs_count`) are sufficient for SP06. A derived `source_kind` dimension can be added by SP08 during the metrics sweep if needed.] |
| Q6 | Whether the outer try/except in `create_care_plan_job` should catch `ValueError` from `_resolve_input_for_job` separately (400) before the outer catch (500). | [RESOLVED: yes. The existing inner try/except at care_plan_jobs.py:86-93 is preserved as a local catch that returns 400. It remains inside the outer try/except so that the outer catch only fires for truly unexpected exceptions.] |
