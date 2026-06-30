# PRD: SP05 — JobDoc Pydantic Model

**Sub-project:** SP05  
**Branch context:** `users/tejitpabari/llm-code-check`  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started

---

## 1. Problem

The Firestore job document — the most important structured object in the Juno system — is a raw `dict` everywhere. It is hand-built as an inline dict literal in three separate locations and consumed via dozens of `.get()` calls:

1. **`routes/batch_jobs.py:89–119`** — GCS-dataset job doc (~29 fields). Nulls out all five `athena_*` fields explicitly.
2. **`routes/batch_jobs.py:171–202`** — Athena job doc (~29 fields). Nulls out all four `dataset_*` fields explicitly.
3. **`routes/care_plan_jobs.py:101–120`** — Single-job doc (~20 fields, some spread from `**input_fields`). Adds `shared`, `comment`, and `trace_id` which the batch paths lack entirely.

**`routes/worker.py`** reads the same document as a raw dict with approximately 29 `.get()` calls (lines 49–59, 200–254) and mutates `output_data` as a raw dict (lines 329–334). Any new field, rename, or optional/required change must be manually tracked across all four files with no compile-time safety.

**Consequences today:**

- `input_doc_id` is absent from both batch job dicts but present in the single-job dict (via `_resolve_input_for_job`). The worker reads it with `.get("input_doc_id")` and silently gets `None` for batch jobs — this is correct behaviour, but is invisible to the type checker.
- `shared`, `comment`, and `trace_id` are single-job-only fields written to Firestore; they are never present on batch docs. The worker never reads them, but Firestore rules and the frontend must tolerate their absence.
- The GCS path null-pads `athena_practice_id`, `athena_patient_id`, `athena_encounter_id`, `athena_document_id`, `athena_api_path`. The Athena path null-pads `dataset_group`, `dataset_input_id`, `dataset_files`. This mutual null-padding is a contract that exists only in comments (`# Athena fields null for GCS jobs`).
- `source_filename` is set twice per doc — once directly from a derived string and once as `input_source_filename` with the same value. These two fields are set identically in all three creation sites but have no enforcement.
- `updated_at` / `created_at` are Firestore `datetime` objects written directly by the route but the worker updates `status` and `stage` via `firestore_client().document(job_id).update({...})` rather than through any model — the model boundary SP05 introduces will not own those partial-update paths (that is SP06 scope).

---

## 2. Goals

1. Introduce `backend/models/job.py` containing a single `JobDoc(JsonModel)` class with the full typed field set for the Firestore job document.
2. Provide three factory classmethods that encapsulate the GCS-vs-Athena-vs-single field logic, eliminating all manual null-padding.
3. Migrate `routes/worker.py`'s read path: parse the raw Firestore dict into a `JobDoc` once at the top of `execute_job()`, then replace all ~29 `.get()` calls with typed attribute access.
4. Type the `output_data` mutation in the worker using `CarePlanInternal.to_dict()` (already happening) and ensure the model boundary is clear.
5. Preserve all existing Firestore field names exactly — no wire renames. The frontend and any Firestore security rules depend on the current field names.
6. Make the model the single source of truth for what fields a job document contains, so SP06 (which swaps the inline-dict construction to the factories) and SP10 (frontend type generation) have a stable reference.

---

## 3. Non-Goals

- **SP05 does NOT change the job-creation code** in `routes/batch_jobs.py` or `routes/care_plan_jobs.py`. Those routes continue to build raw dicts until SP06 swaps them to the factories.
- **SP05 does NOT change the partial-update paths** (`update_job_stage`, `complete_job`, `fail_job` in `utils/firebase.py`). Those write only specific fields via Firestore `.update()` and remain raw dicts; SP06 may or may not tighten them.
- **SP05 does NOT rename or remove any Firestore field** — even fields whose names are awkward (e.g., the dual `source_filename` / `input_source_filename`).
- **SP05 does NOT add any new API routes** or change any HTTP response shapes.
- **SP05 does NOT touch the frontend** — TypeScript type coordination is SP10's scope.
- **SP05 does NOT change `utils/firebase.py`'s `create_job_doc()`** — it still accepts a raw `dict` payload. SP06 will pass `job_doc.to_firestore()` there.

---

## 4. Architecture Decisions

### 4a. New File: `backend/models/job.py`

Location follows the SP03 models-reorg layout: top-level models live in `backend/models/`. (`models/job.py` is not inside `care_plan/` or `external_api/` because `JobDoc` is infrastructure-level, not domain-specific.)

**Dependencies (imported into `models/job.py`):**

| Import | Source | SP dependency |
|---|---|---|
| `JsonModel` | `models/base.py` | none (top-level, locked) |
| `StatusEnum` | `models/errors.py` | SP01 (already implemented) |
| `AthenaSourceKind` | `utils/constants.py` (enum added by SP02) | SP02 |

`AthenaSourceKind` is expected to be a `StrEnum` in `Constants` covering: `"gcs_batch_dataset"`, `"athena_encounter"`, `"athena_clinical_doc"`, `"upload"`, `"text"`, `"doc_id"`, `"batch_dataset"` (legacy). If SP02 has not been merged when SP05 is implemented, the field type falls back to `str` with a comment noting the pending upgrade. [OPEN Q1]

---

### 4b. `JobDoc` Field Specification

All field names match the exact Firestore keys written today. The table below lists every field seen across all three creation sites.

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from .base import JsonModel
from .errors import StatusEnum


class JobDoc(JsonModel):
    """Typed representation of a Firestore care_plan_outputs job document.

    Field names are the exact Firestore wire keys — do NOT rename without
    coordinating with the frontend (SP10) and Firestore security rules.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    uid: str
    name: str
    source_filename: str          # display name; mirrors input_source_filename on creation

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime

    # ── Lifecycle ─────────────────────────────────────────────────────────
    status: StatusEnum = StatusEnum.not_started
    stage: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_data: Optional[dict[str, Any]] = None   # CarePlanInternal.to_dict() shape on completion
    error_data: Optional[dict[str, Any]] = None    # FirestoreJobError shape on failure (see SP01)

    # ── Batch grouping ────────────────────────────────────────────────────
    batch_run_id: Optional[str] = None
    batch_group_id: Optional[str] = None

    # ── Input provenance ──────────────────────────────────────────────────
    input_source_kind: str        # AthenaSourceKind value; typed as str pending SP02
    input_text: Optional[str] = None
    input_doc_id: Optional[str] = None
    input_source_filename: str
    input_pdf_gcs_uri: Optional[str] = None
    input_version: str = "v1-2"
    grading_enabled: bool = False

    # ── GCS-dataset-specific ──────────────────────────────────────────────
    dataset_group: Optional[str] = None
    dataset_input_id: Optional[str] = None
    dataset_files: Optional[list[str]] = None

    # ── Athena-specific ───────────────────────────────────────────────────
    athena_practice_id: Optional[str] = None
    athena_patient_id: Optional[str] = None
    athena_encounter_id: Optional[str] = None
    athena_document_id: Optional[str] = None
    athena_api_path: Optional[str] = None

    # ── Single-job-only extras ────────────────────────────────────────────
    shared: Optional[bool] = None          # False on single-job docs; absent on batch
    comment: Optional[str] = None          # "" on single-job docs; absent on batch
    trace_id: Optional[str] = None         # OTel trace_id; absent on batch
```

**Old vs. new field accounting:**

| Old dict key | `JobDoc` field | Type change | Notes |
|---|---|---|---|
| `uid` | `uid` | `str` | unchanged |
| `name` | `name` | `str` | unchanged |
| `source_filename` | `source_filename` | `str` | unchanged |
| `created_at` | `created_at` | `datetime` | unchanged |
| `updated_at` | `updated_at` | `datetime` | unchanged |
| `status` | `status` | `StatusEnum` | was bare string `"not_started"` |
| `stage` | `stage` | `Optional[int]` | was `None` |
| `started_at` | `started_at` | `Optional[datetime]` | was `None` |
| `completed_at` | `completed_at` | `Optional[datetime]` | was `None` |
| `output_data` | `output_data` | `Optional[dict[str, Any]]` | was `None`; shape is `CarePlanInternal.to_dict()` |
| `error_data` | `error_data` | `Optional[dict[str, Any]]` | was `None`; shape is `FirestoreJobError` from SP01 |
| `batch_run_id` | `batch_run_id` | `Optional[str]` | was `None` for single-job |
| `batch_group_id` | `batch_group_id` | `Optional[str]` | was `None` for single-job |
| `input_source_kind` | `input_source_kind` | `str` | will become `AthenaSourceKind` post-SP02 |
| `input_text` | `input_text` | `Optional[str]` | was `None` on GCS-dataset before worker resolves it |
| `input_doc_id` | `input_doc_id` | `Optional[str]` | present in single-job dict only (via `_resolve_input_for_job`) |
| `input_source_filename` | `input_source_filename` | `str` | unchanged |
| `input_pdf_gcs_uri` | `input_pdf_gcs_uri` | `Optional[str]` | unchanged |
| `input_version` | `input_version` | `str` | unchanged |
| `grading_enabled` | `grading_enabled` | `bool` | unchanged |
| `dataset_group` | `dataset_group` | `Optional[str]` | `None` on Athena/single |
| `dataset_input_id` | `dataset_input_id` | `Optional[str]` | `None` on Athena/single |
| `dataset_files` | `dataset_files` | `Optional[list[str]]` | `None` on Athena/single |
| `athena_practice_id` | `athena_practice_id` | `Optional[str]` | `None` on GCS/single |
| `athena_patient_id` | `athena_patient_id` | `Optional[str]` | `None` on GCS/single |
| `athena_encounter_id` | `athena_encounter_id` | `Optional[str]` | `None` on GCS/single |
| `athena_document_id` | `athena_document_id` | `Optional[str]` | `None` on GCS/single |
| `athena_api_path` | `athena_api_path` | `Optional[str]` | `None` on GCS/single |
| `shared` | `shared` | `Optional[bool]` | absent from batch dicts; `False` on single |
| `comment` | `comment` | `Optional[str]` | absent from batch dicts; `""` on single |
| `trace_id` | `trace_id` | `Optional[str]` | absent from batch dicts; OTel id or `None` on single |

**Note on `output_data` and `error_data` typing:** Both fields are `Optional[dict[str, Any]]` in the model (not strongly typed sub-models). This is intentional:

- `output_data` holds a `CarePlanInternal.to_dict()` serialisation. Validating it inside `JobDoc` would re-parse a large nested structure on every worker read. The worker already has the full `CarePlanInternal` type at the point of creation; reading sites only need specific keys.
- `error_data` holds the `FirestoreJobError` dict shape defined by SP01 (`build_error_data`). Embedding `ErrorDetail` as a sub-model would couple `job.py` tightly to `models/errors.py` and require every partial-update path (`fail_job`) to also validate. [OPEN Q2]

Both fields may be promoted to typed sub-models in a later cleanup SP if the read sites benefit from it.

---

### 4c. Factory Classmethods

Three classmethods encapsulate the field-logic that the three creation sites currently implement as bespoke dicts. SP06 will call these; SP05 must define them precisely so SP06 has zero ambiguity.

```python
    # ── Factories ─────────────────────────────────────────────────────────

    @classmethod
    def for_gcs_dataset(
        cls,
        *,
        user_id: str,
        now: datetime,
        version: str,
        grading_enabled: bool,
        batch_run_id: str,
        batch_group_id: str,
        dataset_group: str,
        dataset_input_id: str,
        dataset_files: list[str],
        source_filename: str,
    ) -> "JobDoc":
        """Build a job doc for a GCS-batch-dataset item.

        All five athena_* fields default to None (Optional); all four dataset_*
        fields are populated. shared/comment/trace_id are absent (None).
        """
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=source_filename,
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            input_source_kind="gcs_batch_dataset",
            input_source_filename=source_filename,
            input_version=version,
            grading_enabled=grading_enabled,
            batch_run_id=batch_run_id,
            batch_group_id=batch_group_id,
            dataset_group=dataset_group,
            dataset_input_id=dataset_input_id,
            dataset_files=dataset_files,
        )

    @classmethod
    def for_athena(
        cls,
        *,
        user_id: str,
        now: datetime,
        version: str,
        grading_enabled: bool,
        batch_run_id: str,
        batch_group_id: str,
        source_kind: str,          # "athena_encounter" | "athena_clinical_doc"
        source_filename: str,
        practice_id: str,
        patient_id: str,
        encounter_id: Optional[str],
        document_id: Optional[str],
        api_path: str,
    ) -> "JobDoc":
        """Build a job doc for an Athena Health batch item.

        All four dataset_* fields default to None (Optional); Athena fields are
        populated. shared/comment/trace_id are absent (None).
        """
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=source_filename,
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            input_source_kind=source_kind,
            input_source_filename=source_filename,
            input_version=version,
            grading_enabled=grading_enabled,
            batch_run_id=batch_run_id,
            batch_group_id=batch_group_id,
            athena_practice_id=practice_id,
            athena_patient_id=patient_id,
            athena_encounter_id=encounter_id,
            athena_document_id=document_id,
            athena_api_path=api_path,
        )

    @classmethod
    def for_single(
        cls,
        *,
        user_id: str,
        now: datetime,
        trace_id: Optional[str],
        input_fields: dict,        # output of _resolve_input_for_job()
    ) -> "JobDoc":
        """Build a job doc for a single (non-batch) care-plan job.

        Populates shared=False, comment="", and trace_id from the OTel span.
        All batch/athena/dataset fields default to None.
        input_fields dict must contain:
          input_source_kind, input_text, input_doc_id,
          input_source_filename, input_pdf_gcs_uri,
          input_version, grading_enabled
        """
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=input_fields["input_source_filename"],
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            shared=False,
            comment="",
            trace_id=trace_id,
            **input_fields,
        )
```

---

### 4d. Persistence Helpers

```python
    # ── Persistence ───────────────────────────────────────────────────────

    def to_firestore(self) -> dict:
        """Serialise to a Firestore-ready dict.

        Uses model_dump(mode="python") so datetime objects are kept as native
        datetime (Firestore SDK converts them to Timestamps). Use to_dict()
        (mode="json") only when producing JSON API responses.
        """
        return self.model_dump(mode="python", exclude_none=False)

    @classmethod
    def from_firestore(cls, data: dict) -> "JobDoc":
        """Parse a raw Firestore document dict into a typed JobDoc.

        Firestore returns datetime objects for Timestamp fields; Pydantic
        accepts them directly. Unknown extra keys are forbidden (extra="forbid"
        from JsonModel) — if this raises, a field was added to Firestore
        without updating the model.
        """
        return cls.model_validate(data)
```

**Important:** `to_firestore()` uses `mode="python"` (not `mode="json"`) so that `datetime` fields remain Python `datetime` objects. The Firestore Python SDK converts these to `google.cloud.firestore.SERVER_TIMESTAMP`-compatible `datetime` objects automatically. If `mode="json"` were used, datetimes would be ISO strings and Firestore would store them as strings, breaking date-range queries.

`from_firestore()` wraps `model_validate()`. Because `JsonModel` has `extra="forbid"`, any Firestore field not declared in `JobDoc` will raise a `ValidationError` at parse time. This is intentional — it surfaces undeclared fields immediately rather than silently dropping them. [OPEN Q3]

---

### 4e. Worker Read-Path Migration

**File:** `routes/worker.py`

Today's read pattern (excerpt):

```python
# worker.py — current (lines 49–59, 173–254)
job_doc = get_job_doc(job_id)          # returns dict | None

uid          = job_doc.get("uid")
batch_run_id = job_doc.get("batch_run_id")
source_kind  = job_doc.get("input_source_kind", "text")
version      = job_doc.get("input_version", "v1-2")
grading_enabled = job_doc.get("grading_enabled", False)
# ... ~24 more .get() calls ...

def _is_batch_item(job_doc: dict) -> bool:
    return job_doc.get("batch_group_id") is not None

def _resolve_input_from_job_doc(job_doc: dict) -> str:
    source_kind = job_doc.get("input_source_kind", "text")
    if source_kind == "doc_id":
        doc_id = job_doc["input_doc_id"]
        ...
    return job_doc.get("input_text") or ""
```

After SP05 migration:

```python
# worker.py — after SP05
from models.job import JobDoc

job_doc_raw = get_job_doc(job_id)      # still returns dict | None
if job_doc_raw is None:
    ...
job = JobDoc.from_firestore(job_doc_raw)

uid          = job.uid
batch_run_id = job.batch_run_id
source_kind  = job.input_source_kind
version      = job.input_version
grading_enabled = job.grading_enabled

def _is_batch_item(job: JobDoc) -> bool:
    return job.batch_group_id is not None

def _resolve_input_from_job_doc(job: JobDoc) -> str:
    if job.input_source_kind == "doc_id":
        file_bytes, filename = _fetch_from_gcs(job.input_doc_id)
        return _extract_text_from_bytes(file_bytes, filename)
    return job.input_text or ""
```

Full list of `.get()` reads to convert (verified in `routes/worker.py`):

| Location | Old expression | New attribute |
|---|---|---|
| line 49 | `job_doc.get("batch_group_id") is not None` | `job.batch_group_id is not None` |
| line 54 | `job_doc.get("input_source_kind", "text")` | `job.input_source_kind` |
| line 57 | `job_doc["input_doc_id"]` | `job.input_doc_id` |
| line 59 | `job_doc.get("input_text") or ""` | `job.input_text or ""` |
| line 169 | `job_doc.get("status") in (...)` | `job.status in (...)` |
| line 173 | `job_doc.get("uid")` | `job.uid` |
| line 174 | `job_doc.get("batch_run_id")` | `job.batch_run_id` |
| line 200 | `job_doc.get("input_source_kind", "text")` | `job.input_source_kind` |
| line 208 | `job_doc["dataset_group"]` | `job.dataset_group` |
| line 209 | `job_doc["dataset_input_id"]` | `job.dataset_input_id` |
| line 210 | `job_doc["dataset_files"]` | `job.dataset_files` |
| line 214 | `job_doc["dataset_group"]` | `job.dataset_group` |
| line 215 | `job_doc["dataset_input_id"]` | `job.dataset_input_id` |
| line 216 | `job_doc["dataset_files"]` | `job.dataset_files` |
| line 221 | `job_doc.get("athena_practice_id") or Constants.ATHENA_PRACTICE_ID` | `job.athena_practice_id or Constants.ATHENA_PRACTICE_ID` |
| line 222 | `job_doc.get("athena_api_path", "")` | `job.athena_api_path or ""` |
| line 225 | `job_doc["athena_encounter_id"]` | `job.athena_encounter_id` |
| line 229 | `job_doc["athena_patient_id"]` | `job.athena_patient_id` |
| line 230 | `job_doc["athena_document_id"]` | `job.athena_document_id` |
| line 253 | `job_doc.get("input_version", "v1-2")` | `job.input_version` |
| line 254 | `job_doc.get("grading_enabled", False)` | `job.grading_enabled` |
| line 255 | `_is_batch_item(job_doc)` | `_is_batch_item(job)` |
| line 314 | `job_doc["input_doc_id"]` | `job.input_doc_id` |
| line 333 | `job_doc.get("input_source_filename", "")` | `job.input_source_filename` |

The two helper functions `_is_batch_item(job_doc: dict)` and `_resolve_input_from_job_doc(job_doc: dict)` have their signatures updated to accept `JobDoc` instead of `dict`.

The `output_data` mutation block (lines 329–334) is already `output_data = envelope.to_dict()` followed by dict key mutations. This remains as raw dict operations — the `CarePlanInternal` model is already strongly typed at the point it is created; the subsequent injections (`care_plan_dict["additional_info"]`, `output_data["metrics"]["saved_id"]`) are post-serialisation enrichments. No change required here for SP05.

---

### 4f. SP Boundary with SP06

| Responsibility | SP05 (this SP) | SP06 (Batch+Job-Creation Hardening) |
|---|---|---|
| Defines `JobDoc` model and factories | Yes | No |
| Migrates worker read path to `JobDoc` | Yes | No |
| Swaps inline-dict construction in `batch_jobs.py` to `JobDoc.for_gcs_dataset()` / `JobDoc.for_athena()` | No | Yes |
| Swaps inline-dict construction in `care_plan_jobs.py` to `JobDoc.for_single()` | No | Yes |
| Tightens `create_job_doc()` to accept `JobDoc` | No | Yes (optional) |

The factories in SP05 must therefore be complete and match the exact field logic used by the existing creation sites, so SP06 can perform a mechanical swap with no business-logic changes.

---

## 5. API Change Summary

SP05 makes no changes to any HTTP endpoint signature, request shape, or response shape. All changes are internal to the backend Python layer.

The Firestore document shape is unchanged — the same field names and values are written and read. The only observable difference is that `from_firestore()` will raise a `ValidationError` at runtime if the Firestore document contains a field not declared in `JobDoc`. In practice this cannot happen unless a field was written manually to Firestore out-of-band.

---

## 6. Frontend Considerations

The Firestore `care_plan_outputs` document shape is read directly by the frontend via the Firestore SDK (not through the Flask API). SP05 makes no changes to the Firestore wire format, so no frontend changes are required by this SP.

However, SP05 is the **canonical reference** for the TypeScript `JobDoc` interface that SP10 will generate. SP10 must declare every field listed in section 4b as a TypeScript field with the correct optionality:

- `shared`, `comment`, `trace_id` must be `T | undefined` (not `T | null`) in TypeScript because batch docs never write these keys to Firestore. [OPEN Q4]
- `output_data` and `error_data` must be typed as `CarePlanInternal` and `FirestoreJobError` respectively (both defined by SP01 / existing types), not as `any`.
- `status` must use the `StatusEnum` string union (`"not_started" | "processing" | "completed" | "error" | "success"`).

SP10 should import this PRD as the authoritative field list. Any field rename in `JobDoc` requires a coordinated SP10 change.

---

## 7. Testing

### Unit tests — `backend/tests/models/test_job.py` (new file)

- `test_for_gcs_dataset_sets_correct_fields`: call `JobDoc.for_gcs_dataset(...)` with sample inputs; assert `input_source_kind == "gcs_batch_dataset"`, all five `athena_*` fields are `None`, `dataset_group` / `dataset_input_id` / `dataset_files` match inputs, `shared` is `None`, `batch_run_id` matches.
- `test_for_athena_sets_correct_fields`: call `JobDoc.for_athena(...)` with an `athena_encounter` kind; assert all four `dataset_*` fields are `None`, `athena_encounter_id` matches, `athena_document_id` is `None`, `input_source_kind == "athena_encounter"`.
- `test_for_athena_clinical_doc`: same pattern for `athena_clinical_doc`; assert `athena_document_id` matches, `athena_encounter_id` is `None`.
- `test_for_single_sets_shared_comment_trace`: call `JobDoc.for_single(...)` with a non-None `trace_id`; assert `shared is False`, `comment == ""`, `trace_id` matches, `batch_run_id is None`.
- `test_to_firestore_returns_datetime_objects`: call `job.to_firestore()` on a `for_gcs_dataset` doc; assert `created_at` is a `datetime` instance (not a string).
- `test_from_firestore_roundtrip`: create a `for_gcs_dataset` doc, call `.to_firestore()`, then `JobDoc.from_firestore(result)`; assert all fields match.
- `test_from_firestore_rejects_extra_field`: pass a dict with an unknown key `"unexpected_field": "x"` to `JobDoc.from_firestore()`; assert `ValidationError` is raised (enforces `extra="forbid"`).
- `test_status_enum_default`: assert a freshly constructed `JobDoc.for_gcs_dataset(...)` has `status == StatusEnum.not_started`.

### Integration tests — worker read-path

- `test_execute_job_uses_typed_attributes`: mock `get_job_doc()` to return a GCS-dataset dict; assert `_is_batch_item()` returns `True` and `_resolve_input_from_job_doc()` returns the expected text. (These are existing tests; update signatures from `dict` to `JobDoc`.)
- `test_execute_job_athena_path_uses_typed_attributes`: mock `get_job_doc()` returning an Athena dict; assert `job.athena_encounter_id` is passed to `athena_client.fetch_encounter_summary`.

### Manual integration test

1. Submit a single care-plan job (text input). Observe via Firestore console that the doc has the same field set as before — no missing or extra fields.
2. Submit a GCS-batch job. Confirm `athena_*` fields are absent (not null) after SP05 migration — this is a wire change if SP06 is not yet merged. [OPEN Q5]
3. Trigger a worker execution for each job type; confirm the job reaches `completed` status with `output_data` populated.
4. Deliberately corrupt a test Firestore doc with an unknown field; verify the worker logs a `ValidationError` and marks the job as `error` rather than crashing silently.

---

## 8. Manual Intervention Required

None. SP05 is a pure code change:

- No new GCS buckets, environment variables, or Cloud Run configuration.
- No Firestore schema migration — the document shape is identical to today's.
- No Firestore security rule changes — field names are preserved exactly.
- No deployment sequencing constraint beyond the normal code review + deploy cycle (SP05 can deploy independently of SP06 because creation sites still build raw dicts until SP06 lands).

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | `input_source_kind` type: use `str` now and upgrade to `AthenaSourceKind` once SP02 is merged, or block SP05 on SP02? | [OPEN — recommended: merge SP02 first; if sequencing forces SP05 earlier, use `str` with a `# TODO(SP02): upgrade to AthenaSourceKind` comment.] |
| Q2 | Should `output_data` and `error_data` be strongly typed sub-models (`CarePlanInternal` / `ErrorDetail`) inside `JobDoc`, or remain `Optional[dict[str, Any]]`? | [OPEN — current recommendation: keep as `dict` to avoid re-validation overhead on the worker read path and to decouple `job.py` from the full `CarePlanInternal` dependency chain. Revisit in a later cleanup SP.] |
| Q3 | `extra="forbid"` on `from_firestore()` means a field manually written to Firestore out-of-band will crash the worker. Is this the right trade-off, or should `extra="ignore"` be used for the parse path only? | [OPEN — recommendation: keep `extra="forbid"` to surface undeclared fields as bugs. A try/except around `from_firestore()` in the worker can log the error and fall back to raw-dict reads temporarily while the model is updated.] |
| Q4 | Frontend field optionality: should `shared`, `comment`, `trace_id` be `T | undefined` (field absent on batch docs) or `T | null` (field present but null)? | [OPEN — SP05 uses `Optional[T] = None` in Python, which Firestore serialises as field absent when using `exclude_none=True` or as `null` when using `exclude_none=False`. Current `to_firestore()` uses `exclude_none=False`, meaning batch docs will write `"shared": null`. Coordinate with SP10 on which is preferred; recommend switching to `exclude_none=True` for cleaner Firestore docs, but that requires SP10 to use `T | undefined`.] |
| Q5 | After SP05 (worker migrated) but before SP06 (creation sites migrated): the creation sites still write raw dicts with explicit `"athena_*": None` nulls on GCS docs. This is fine — `from_firestore()` accepts them as `Optional[str] = None`. No wire incompatibility. | [RESOLVED — no action needed; SP05 and SP06 can deploy in any order.] |
| Q6 | Should `JobDoc` implement `__init_subclass__` or a discriminated-union pattern for GCS vs. Athena vs. single, rather than one flat model with many Optionals? | [DEFERRED — a discriminated union would give stronger typing (e.g., `GCSJobDoc` guarantees `dataset_group` is non-None) but would require the worker to branch on type rather than on `input_source_kind`. The flat model matches the current Firestore reality. Revisit if the SP06/SP07 read path becomes unwieldy.] |
| Q7 | Dependencies on SP01 (error payload shape for `error_data`), SP02 (`AthenaSourceKind`), SP03 (models layout). | [RESOLVED — SP05 depends on SP01 (done) for `StatusEnum` import; SP02 for `AthenaSourceKind` (see Q1); SP03 for models directory layout. SP05 should be implemented after SP03 to land in the correct directory.] |
