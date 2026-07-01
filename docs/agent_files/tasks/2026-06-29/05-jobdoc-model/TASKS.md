# SP05 JobDoc Pydantic Model — TASKS

## Prerequisites

Introduces a typed `JobDoc` Pydantic model for the Firestore job document and migrates
`routes/worker.py`'s read path from raw-dict `.get()` calls to typed attribute access.
Assumes SP01 (error types + `StatusEnum`), SP02 (`Constants.Athena.AthenaSourceKind`),
SP03 (models folder layout), and SP04 (Athena external API) are fully complete and merged.

---

## Tasks

### Task 05.1: Add `JobDoc` Pydantic model in `backend/models/job.py`

**Goal:** Create the single source-of-truth typed model for the Firestore
`care_plan_outputs` job document. All field names must exactly match current
Firestore wire keys. Model config overrides `JsonModel`'s `extra="forbid"` with
`extra="ignore"` (per Q3 user decision) so unknown Firestore fields are silently
dropped rather than raising `ValidationError` at worker parse time.

Per Q2 (user decision: "make them TYPED SUB-MODELS"), `output_data` and
`error_data` are typed Pydantic sub-models, NOT `dict[str, Any]`:
- `error_data: Optional[ErrorDetail]` — the SP01 unified error model in
  `models/errors.py`. The `build_error_data()` dict shape
  (`code`, `message`, `user_hint`, `retryable`, `details`, `timestamp`) maps
  exactly onto `ErrorDetail`'s fields (`path` is Optional and absent on
  worker-written errors).
- `output_data: Optional[CarePlanInternal]` — the strongly-typed care-plan
  output composite in `models/envelope.py`. The worker's post-serialisation
  enrichments (`metrics.saved_id`, `care_plan.additional_info`) are both
  declared model fields (`Metrics.saved_id`, care-plan `additional_info`), so
  the enriched dict still validates as a `CarePlanInternal`.

> Note: `input_source_kind` is typed as `Constants.Athena.AthenaSourceKind` (a
> `StrEnum`), since SP02 is assumed complete. Because `AthenaSourceKind` is a
> `StrEnum`, its values compare equal to plain strings, so no conversion is needed
> at read sites. The `for_athena` factory accepts `source_kind: AthenaSourceKind`
> for strong typing at creation time (Q6 — strongly-typed casting).

**Files:**
- `backend/models/job.py` (new file)
- `backend/models/__init__.py` (add `JobDoc` export)

**Steps:**

1. Create `backend/models/job.py` with the following structure:

   ```python
   """Typed Pydantic model for the Firestore care_plan_outputs job document."""
   from __future__ import annotations

   from datetime import datetime
   from typing import Optional

   from pydantic import ConfigDict

   from .base import JsonModel
   from .errors import ErrorDetail, StatusEnum
   from .envelope import CarePlanInternal
   from utils.constants import Constants

   AthenaSourceKind = Constants.Athena.AthenaSourceKind


   class JobDoc(JsonModel):
       """Typed representation of a Firestore care_plan_outputs job document.

       Field names are the exact Firestore wire keys — do NOT rename without
       coordinating with the frontend (SP10) and Firestore security rules.

       extra="ignore" is intentional: unknown keys written to Firestore
       out-of-band are silently dropped rather than raising ValidationError.
       """

       model_config = ConfigDict(extra="ignore")

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
       output_data: Optional[CarePlanInternal] = None   # typed sub-model (Q2)
       error_data: Optional[ErrorDetail] = None         # SP01 typed error model (Q2)

       # ── Batch grouping ────────────────────────────────────────────────────
       batch_run_id: Optional[str] = None
       batch_group_id: Optional[str] = None

       # ── Input provenance ──────────────────────────────────────────────────
       input_source_kind: AthenaSourceKind
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
       shared: Optional[bool] = None
       comment: Optional[str] = None
       trace_id: Optional[str] = None
   ```

2. Add three factory classmethods to `JobDoc` (inside the class body, after
   field declarations):

   ```python
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
           """Build a job doc for a GCS-batch-dataset item."""
           return cls(
               uid=user_id,
               name=now.strftime("%b %d, %Y %H:%M"),
               source_filename=source_filename,
               created_at=now,
               updated_at=now,
               status=StatusEnum.not_started,
               input_source_kind=AthenaSourceKind.GCS_BATCH_DATASET,
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
           source_kind: AthenaSourceKind,
           source_filename: str,
           practice_id: str,
           patient_id: str,
           encounter_id: Optional[str],
           document_id: Optional[str],
           api_path: str,
       ) -> "JobDoc":
           """Build a job doc for an Athena Health batch item."""
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
           input_fields: dict,
       ) -> "JobDoc":
           """Build a job doc for a single (non-batch) care-plan job.

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

3. Add two persistence helpers to `JobDoc`:

   ```python
       def to_firestore(self) -> dict:
           """Serialise to a Firestore-ready dict.

           Uses mode="python" so datetime fields stay as native datetime
           objects (Firestore SDK converts them to Timestamps automatically).
           The typed sub-models output_data (CarePlanInternal) and error_data
           (ErrorDetail) are recursively dumped to plain dicts by model_dump,
           so the Firestore wire shape is byte-for-byte identical to today's.
           exclude_none=False is intentional — batch fields (shared, comment,
           trace_id) are written as null on batch docs; SP10 must type them
           as T | null, not T | undefined.
           """
           return self.model_dump(mode="python", exclude_none=False)

       @classmethod
       def from_firestore(cls, data: dict) -> "JobDoc":
           """Parse a raw Firestore document dict into a typed JobDoc.

           extra="ignore" (set on model_config) means unknown Firestore fields
           are silently dropped. If a required field is missing, ValidationError
           is raised — that IS a hard error that should surface.

           Nested output_data / error_data dicts read back from Firestore are
           re-validated into CarePlanInternal / ErrorDetail sub-models here.
           """
           return cls.model_validate(data)
   ```

   > Note (Q4 wire format preserved): because the sub-models serialise to the
   > same dict shape via `model_dump`, `to_firestore()` still emits the exact
   > Firestore keys/values written today. The only behavioural change is that
   > a malformed `output_data`/`error_data` blob in Firestore now raises a
   > `ValidationError` in `from_firestore()` instead of silently passing
   > through as a raw dict. The worker already wraps `execute_job()` in a
   > try/except that calls `fail_job(...)`, so a parse failure is surfaced as
   > a failed job rather than a silent corruption.

4. Open `backend/models/__init__.py`. If it exists and imports from other
   model files, add `from .job import JobDoc` alongside them. If it is empty
   or does not exist, create/update it to contain:
   ```python
   from .job import JobDoc
   ```

> Note: `AthenaSourceKind` is accessed as `Constants.Athena.AthenaSourceKind`
> per SP02's layout. The alias `AthenaSourceKind = Constants.Athena.AthenaSourceKind`
> at the top of `job.py` keeps the rest of the file readable. `GCS_BATCH_DATASET`
> is the expected enum member name per SP02 PRD (value `"gcs_batch_dataset"`);
> confirm the exact member names against `utils/constants.py` after SP02 is
> merged — adjust the factory if the member is named differently (e.g.,
> `AthenaSourceKind.gcs_batch_dataset`).

**Acceptance:**
- `python -c "from models.job import JobDoc"` exits 0 with no errors.
- `JobDoc.model_fields.keys()` includes all 29 fields listed in the PRD field table.
- `JobDoc.model_config["extra"] == "ignore"`.
- `JobDoc.for_gcs_dataset(...)` returns a `JobDoc` instance without error when
  called with valid inputs.
- The annotation of `output_data` is `Optional[CarePlanInternal]` and of
  `error_data` is `Optional[ErrorDetail]` — NOT `dict[str, Any]`. Verify with
  `JobDoc.model_fields["error_data"].annotation` and
  `JobDoc.model_fields["output_data"].annotation`.

**Commit:**
```
feat(models): add typed JobDoc Pydantic model with factory classmethods and Firestore helpers
```

---

### Task 05.2: Write unit tests for `JobDoc` — `backend/tests/models/test_job.py`

**Goal:** Verify every factory, the persistence helpers, and edge-case behaviour
of the model. Tests must pass without any network calls (pure in-process).

**Files:**
- `backend/tests/models/test_job.py` (new file)

**Steps:**

1. Create `backend/tests/models/test_job.py`. Import `datetime`, `timezone`,
   `pytest`, `ValidationError` from `pydantic`, `JobDoc` from `models.job`,
   and `StatusEnum` from `models.errors`.

2. Add a shared `now` fixture:
   ```python
   @pytest.fixture
   def now():
       from datetime import datetime, timezone
       return datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
   ```

3. Add a shared `gcs_kwargs` fixture returning the minimal keyword arguments for
   `JobDoc.for_gcs_dataset(...)`:
   ```python
   @pytest.fixture
   def gcs_kwargs(now):
       return dict(
           user_id="u1",
           now=now,
           version="v1-2",
           grading_enabled=False,
           batch_run_id="run-1",
           batch_group_id="grp-1",
           dataset_group="GroupA",
           dataset_input_id="input-1",
           dataset_files=["a.txt", "b.txt"],
           source_filename="a.txt",
       )
   ```

4. Write the following test functions (one assertion block per function; use
   `assert` statements, not `unittest.TestCase`):

   **`test_for_gcs_dataset_sets_correct_fields(gcs_kwargs)`**
   - Call `job = JobDoc.for_gcs_dataset(**gcs_kwargs)`.
   - Assert `job.input_source_kind == "gcs_batch_dataset"`.
   - Assert all five `athena_*` fields are `None`.
   - Assert `job.dataset_group == "GroupA"`, `job.dataset_input_id == "input-1"`,
     `job.dataset_files == ["a.txt", "b.txt"]`.
   - Assert `job.shared is None`, `job.comment is None`, `job.trace_id is None`.
   - Assert `job.batch_run_id == "run-1"`, `job.batch_group_id == "grp-1"`.
   - Assert `job.status == StatusEnum.not_started`.

   **`test_for_athena_encounter_sets_correct_fields(now)`**
   - Call `job = JobDoc.for_athena(user_id="u1", now=now, version="v1-2",
     grading_enabled=False, batch_run_id="run-2", batch_group_id="grp-2",
     source_kind=<AthenaSourceKind.ATHENA_ENCOUNTER or the correct enum member>,
     source_filename="enc.pdf", practice_id="195900", patient_id="P1",
     encounter_id="E42", document_id=None, api_path="/api/enc")`.
   - Assert all four `dataset_*` fields are `None`.
   - Assert `job.athena_encounter_id == "E42"`.
   - Assert `job.athena_document_id is None`.
   - Assert `job.input_source_kind == "athena_encounter"`.

   **`test_for_athena_clinical_doc_sets_correct_fields(now)`**
   - Same pattern, passing `source_kind=<ATHENA_CLINICAL_DOC enum member>`,
     `encounter_id=None`, `document_id="D99"`.
   - Assert `job.athena_document_id == "D99"`, `job.athena_encounter_id is None`.
   - Assert `job.input_source_kind == "athena_clinical_doc"`.

   **`test_for_single_sets_shared_comment_trace(now)`**
   - Build `input_fields = {"input_source_kind": "text", "input_text": "hello",
     "input_doc_id": None, "input_source_filename": "note.txt",
     "input_pdf_gcs_uri": None, "input_version": "v1-2",
     "grading_enabled": False}`.
   - Call `job = JobDoc.for_single(user_id="u2", now=now, trace_id="abc123",
     input_fields=input_fields)`.
   - Assert `job.shared is False`, `job.comment == ""`,
     `job.trace_id == "abc123"`.
   - Assert `job.batch_run_id is None`, `job.batch_group_id is None`.

   **`test_to_firestore_returns_datetime_objects(gcs_kwargs)`**
   - Build `job = JobDoc.for_gcs_dataset(**gcs_kwargs)`.
   - Call `d = job.to_firestore()`.
   - Assert `isinstance(d["created_at"], datetime)`.
   - Assert `isinstance(d["updated_at"], datetime)`.
   - Assert `"status"` in `d` and `d["status"]` is not an instance of `StatusEnum`
     — it is the raw string value (mode="python" serialises enums to their
     `.value`).

   > Note: Pydantic v2's `model_dump(mode="python")` serialises `StrEnum` /
   > `str` enums as their string value by default. Verify this assumption in
   > the test and adjust the assertion if the actual type is `StatusEnum`.

   **`test_from_firestore_roundtrip(gcs_kwargs)`**
   - Build `job = JobDoc.for_gcs_dataset(**gcs_kwargs)`.
   - Call `d = job.to_firestore()`.
   - Call `job2 = JobDoc.from_firestore(d)`.
   - Assert `job2.uid == job.uid`, `job2.dataset_files == job.dataset_files`,
     `job2.created_at == job.created_at`.

   **`test_from_firestore_ignores_extra_field(gcs_kwargs)`**
   - Build `d = JobDoc.for_gcs_dataset(**gcs_kwargs).to_firestore()`.
   - Add `d["unexpected_field"] = "surprise"` to the dict.
   - Call `JobDoc.from_firestore(d)` — assert it does NOT raise (extra="ignore").
   - Assert the returned `JobDoc` does not have an `unexpected_field` attribute.

   **`test_error_data_typed_submodel(gcs_kwargs)`** (Q2 — typed sub-models)
   - Import `ErrorDetail` from `models.errors` and
     `build_error_data` from `utils.pipeline_errors`, and any valid
     `ErrorCode` member from `error_codes`.
   - Build `err = build_error_data(<some ErrorCode>, "boom")` — the raw dict
     the worker writes today.
   - Construct a fresh `JobDoc(...)` passing `error_data=err` alongside the
     other required fields (use the `gcs_kwargs`-equivalent direct fields, or
     start from `JobDoc.for_gcs_dataset(**gcs_kwargs).to_firestore()`, set
     `d["error_data"] = err`, then `JobDoc.from_firestore(d)`).
     Do NOT use `model_copy(update=...)` — it does not re-validate, so the raw
     dict would not be coerced into `ErrorDetail`. Validation only happens on
     construction / `model_validate`.
   - Assert `isinstance(job.error_data, ErrorDetail)`.
   - Assert `job.error_data.code == err["code"]` and
     `job.error_data.message == err["message"]`.
   - Call `d = job.to_firestore()` and assert `d["error_data"]` is a plain
     `dict` whose `"code"`/`"message"`/`"timestamp"` keys match the original.

   **`test_output_data_typed_submodel(gcs_kwargs)`** (Q2 — typed sub-models)
   - Build a minimal valid `CarePlanInternal` instance (use the same
     construction helper that `tests/models/test_envelope.py` uses; import
     it or replicate the minimal valid kwargs). If building a full
     `CarePlanInternal` is heavy, instead assert via a roundtrip:
     `out = CarePlanInternal(...).to_dict()`, construct
     `JobDoc(..., output_data=out)`, and assert
     `isinstance(job.output_data, CarePlanInternal)`.
   - Call `d = job.to_firestore()` and assert `d["output_data"]` is a plain
     `dict` (recursively serialised), and that its nested keys
     (`care_plan`, `metrics`, `input`, `grading`) are present — confirming the
     Firestore wire shape is unchanged from a raw `envelope.to_dict()`.

   > Note: if assembling a valid `CarePlanInternal` in the test proves
   > excessive, gate this test behind the shared envelope fixture already used
   > in `tests/models/test_envelope.py` rather than hand-rolling deep nested
   > data. The goal is only to prove `output_data` is parsed into the typed
   > sub-model and dumps back to the identical dict — not to re-test
   > `CarePlanInternal` itself.

   **`test_status_enum_default(gcs_kwargs)`**
   - Call `job = JobDoc.for_gcs_dataset(**gcs_kwargs)`.
   - Assert `job.status == StatusEnum.not_started`.

5. Add a minimal import-smoke test at the top of the file:
   ```python
   def test_import():
       from models.job import JobDoc  # noqa: F401
   ```

**Acceptance:**
- `cd backend && python -m pytest tests/models/test_job.py -v` exits 0 with all
  tests passing, no warnings from Pydantic.

**Commit:**
```
test(models): add unit tests for JobDoc factories, roundtrip, and extra-field handling
```

---

### Task 05.3: Migrate `routes/worker.py` read path from raw dict to `JobDoc`

**Goal:** Parse the raw Firestore dict into a `JobDoc` instance once, at the
top of `execute_job()`, then replace all ~29 `.get()` / `[]` dict accesses with
typed attribute access. Update helper function signatures from `dict` to `JobDoc`.
The `output_data` mutation block (lines 329–334) is NOT changed — it remains raw
dict operations after `envelope.to_dict()`, written to Firestore via
`complete_job()`'s partial `.update()`. That write path does NOT round-trip
through `JobDoc` and is explicitly out of SP05 scope (PRD §3, §4e); the typed
`JobDoc.output_data` / `error_data` sub-models only govern the read path
(`from_firestore`) and the SP06 factory write path (`to_firestore`).

> Note: at worker read time the job is not yet completed, so `output_data` and
> `error_data` in the freshly-read Firestore doc are normally `None`. The
> typed sub-models therefore do not add validation cost to the common worker
> read; they only validate if a doc already carries those fields. A malformed
> blob surfaces as a `ValidationError` caught by the existing `execute_job()`
> try/except, which calls `fail_job(...)`.

**Files:**
- `backend/routes/worker.py`

**Steps:**

1. At the top of `worker.py`, add the import:
   ```python
   from models.job import JobDoc
   ```
   Place it alongside the other `models.*` imports (after the existing
   `from models.envelope import CarePlanInternal` line).

2. Update `_is_batch_item` signature and body:
   ```python
   def _is_batch_item(job: JobDoc) -> bool:
       return job.batch_group_id is not None
   ```

3. Update `_resolve_input_from_job_doc` signature and body:
   ```python
   def _resolve_input_from_job_doc(job: JobDoc) -> str:
       if job.input_source_kind == "doc_id":
           file_bytes, filename = _fetch_from_gcs(job.input_doc_id)
           return _extract_text_from_bytes(file_bytes, filename)
       return job.input_text or ""
   ```

4. Inside `execute_job()`, immediately after the `if job_doc is None:` guard
   block (currently around line 164–167), add the parse step:
   ```python
   job = JobDoc.from_firestore(job_doc)
   ```
   The variable `job_doc` (raw dict returned by `get_job_doc()`) is kept for
   the `if job_doc is None` guard only. All subsequent accesses switch to `job`.

5. Replace every dict access below the parse step according to the table in
   PRD section 4e. The complete substitution list:

   | Line (approx.) | Old expression | New expression |
   |---|---|---|
   | 169 | `job_doc.get("status") in (...)` | `job.status in (...)` |
   | 170 | `job_doc["status"]` | `job.status` |
   | 173 | `job_doc.get("uid")` | `job.uid` |
   | 174 | `job_doc.get("batch_run_id")` | `job.batch_run_id` |
   | 187 | `_is_batch_item(job_doc)` | `_is_batch_item(job)` |
   | 200 | `job_doc.get("input_source_kind", "text")` | `job.input_source_kind` |
   | 208 | `job_doc["dataset_group"]` | `job.dataset_group` |
   | 209 | `job_doc["dataset_input_id"]` | `job.dataset_input_id` |
   | 210 | `job_doc["dataset_files"]` | `job.dataset_files` |
   | 214 | `job_doc["dataset_group"]` | `job.dataset_group` |
   | 215 | `job_doc["dataset_input_id"]` | `job.dataset_input_id` |
   | 216 | `job_doc["dataset_files"]` | `job.dataset_files` |
   | 221 | `job_doc.get("athena_practice_id") or Constants.ATHENA_PRACTICE_ID` | `job.athena_practice_id or Constants.ATHENA_PRACTICE_ID` |
   | 222 | `job_doc.get("athena_api_path", "")` | `job.athena_api_path or ""` |
   | 225 | `job_doc["athena_encounter_id"]` | `job.athena_encounter_id` |
   | 229 | `job_doc["athena_patient_id"]` | `job.athena_patient_id` |
   | 230 | `job_doc["athena_document_id"]` | `job.athena_document_id` |
   | 247 | `_resolve_input_from_job_doc(job_doc)` | `_resolve_input_from_job_doc(job)` |
   | 253 | `job_doc.get("input_version", "v1-2")` | `job.input_version` |
   | 254 | `job_doc.get("grading_enabled", False)` | `job.grading_enabled` |
   | 255 | `_is_batch_item(job_doc)` | `_is_batch_item(job)` |
   | 314 | `job_doc["input_doc_id"]` | `job.input_doc_id` |
   | 333 | `job_doc.get("input_source_filename", "")` | `job.input_source_filename` |

   After each replacement, the variable `job_doc` should no longer appear in
   `execute_job()` body except in the `is None` guard at the top.

6. Verify no remaining `job_doc.get(` or `job_doc["` calls exist below the
   parse step by searching the file:
   ```bash
   grep -n 'job_doc\.get\|job_doc\[' backend/routes/worker.py
   ```
   Only the two `job_doc` lines in the guard block (`if job_doc is None`,
   `logger.warning`) should remain above the parse step.

**Acceptance:**
- `grep -n 'job_doc\.get\|job_doc\[' backend/routes/worker.py` returns no
  lines below the `JobDoc.from_firestore(job_doc)` parse line.
- `_is_batch_item` and `_resolve_input_from_job_doc` both declare `job: JobDoc`
  as their parameter type (not `dict`).
- Existing test suite `cd backend && python -m pytest tests/routes/test_worker.py
  tests/routes/test_worker_gcs_dataset.py -v` passes (tests may need fixture
  updates per Task 05.4 — run after 05.4 is complete).

**Commit:**
```
refactor(worker): migrate execute_job read path from raw dict to typed JobDoc attributes
```

---

### Task 05.4: Update existing worker tests to pass `JobDoc`-compatible dicts

**Goal:** The existing `_make_job_doc()` helpers in `test_worker.py` and
`test_worker_gcs_dataset.py` return raw dicts that `get_job_doc` returns.
After Task 05.3, `execute_job()` calls `JobDoc.from_firestore(job_doc)` on
that dict. The raw dicts must contain all required `JobDoc` fields (no missing
required fields) so `from_firestore()` does not raise `ValidationError`.
Also update helper function call-sites if any test directly calls
`_is_batch_item(job_doc)` or `_resolve_input_from_job_doc(job_doc)` with a
raw dict.

**Files:**
- `backend/tests/routes/test_worker.py`
- `backend/tests/routes/test_worker_gcs_dataset.py`

**Steps:**

1. Open `test_worker.py`. Find `_make_job_doc()`. Verify the dict it returns
   contains all required (non-Optional) `JobDoc` fields:
   - Required: `uid`, `name`, `source_filename`, `created_at`, `updated_at`,
     `input_source_kind`, `input_source_filename`.
   - Add any missing required fields with sensible defaults:
     - `name`: e.g., `"Jan 15, 2026 10:00"`
     - `source_filename`: e.g., `"text_input"`
     - `created_at`: `datetime.now(timezone.utc)` (import `datetime`, `timezone`
       from `datetime` at the top of the test file)
     - `updated_at`: same as `created_at`
   - Leave all Optional fields (`stage`, `batch_run_id`, etc.) as `None` where
     they already are.

2. Open `test_worker_gcs_dataset.py`. Find `_make_gcs_job_doc()`. Apply the
   same audit: add `name`, `source_filename`, `created_at`, `updated_at` if
   they are missing.

3. Search both test files for any direct calls to `_is_batch_item` or
   `_resolve_input_from_job_doc` that pass a raw dict. If found, update
   those calls to first build a `JobDoc` from the dict:
   ```python
   from models.job import JobDoc
   job = JobDoc.from_firestore(raw_doc)
   result = _is_batch_item(job)
   ```

4. Run the full suite to confirm:
   ```bash
   cd backend && python -m pytest tests/routes/test_worker.py tests/routes/test_worker_gcs_dataset.py -v
   ```

**Acceptance:**
- All tests in `test_worker.py` and `test_worker_gcs_dataset.py` pass without
  any `ValidationError` or `KeyError`.
- No test patches `_is_batch_item` or `_resolve_input_from_job_doc` with a
  `dict` argument.

**Commit:**
```
test(worker): update test fixtures to supply required JobDoc fields for from_firestore parsing
```

---

### Task 05.5: Run full backend test suite and fix any remaining failures

**Goal:** Confirm SP05 does not break any other test in the backend suite.
Fix any failures introduced by the model import or the worker refactor.

**Files:**
- Any file that fails — diagnose before editing.

**Steps:**

1. Run the full backend test suite:
   ```bash
   cd backend && python -m pytest --tb=short -q
   ```

2. For each failure, read the traceback. Common failure modes to watch for:
   - `ImportError` on `from models.job import JobDoc` — check `models/__init__.py`
     was updated in Task 05.1.
   - `ValidationError: extra fields not permitted` — means some test dict was
     passed to `from_firestore()` with an unrecognised key but you've already
     set `extra="ignore"`, so this should not occur; if it does, verify the
     `model_config` override is in place.
   - `ValidationError: field required` on `input_source_kind` — the test dict
     is missing a required field; add it (see Task 05.4 pattern).
   - `AttributeError: 'dict' object has no attribute 'uid'` — a call site was
     missed in Task 05.3; find it with `grep -n 'job_doc\.' backend/routes/worker.py`.

3. Fix each failure with a minimal targeted edit (do not refactor unrelated code).

4. Re-run until the full suite is green:
   ```bash
   cd backend && python -m pytest --tb=short -q
   ```

**Acceptance:**
- `python -m pytest --tb=short -q` exits 0 (all tests pass).
- No new `# type: ignore` comments introduced unless the underlying issue is a
  known Pydantic/mypy limitation and is annotated with the reason.

**Commit:**
```
fix(models/worker): resolve test failures after JobDoc migration
```

> Note: This task may be a no-op if Tasks 05.1–05.4 were implemented cleanly.
> Commit only if there are actual fixes to make.

---

## Verification

### Lint / type check
```bash
cd backend && python -m py_compile models/job.py
cd backend && python -c "from models.job import JobDoc; print('import ok')"
```

### Unit tests (new)
```bash
cd backend && python -m pytest tests/models/test_job.py -v
```

### Worker integration tests (existing, must stay green)
```bash
cd backend && python -m pytest tests/routes/test_worker.py tests/routes/test_worker_gcs_dataset.py -v
```

### Full suite
```bash
cd backend && python -m pytest --tb=short -q
```

### Definition of Done
- All 5 tasks have their acceptance criteria met.
- `python -m pytest --tb=short -q` exits 0.
- `grep -n 'job_doc\.get\|job_doc\[' backend/routes/worker.py` returns only
  lines inside the null-guard at the top of `execute_job()` (before the
  `JobDoc.from_firestore` call).
- `models/job.py` exists and is importable.
- `_is_batch_item` and `_resolve_input_from_job_doc` both accept `JobDoc`, not
  `dict`.
- No file other than those listed in each task's **Files** section was modified.
