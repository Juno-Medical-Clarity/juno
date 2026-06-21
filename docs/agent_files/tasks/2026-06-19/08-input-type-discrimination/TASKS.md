# Tasks: Input Type Discrimination (SP-08)

Read `PRD.md` in this folder first. **This sub-project has no dependencies (Phase 4)** — it can
land independently. Every task below is grounded in the current source files; exact line references
are noted where they matter.

---

### Task 1 — Rewrite `models/input.py` with four concrete types + union alias

**Files:** `backend/models/input.py`

Replace the single `Input` class (lines 30–127) with four concrete `JsonModel` subclasses and a
module-level union alias. Keep `INPUT_VERSION = "1.0"` and `InputFile` exactly as they are.

Full replacement of the file body below `InputFile`:

```python
from __future__ import annotations
from typing import Annotated, Any, Literal, Union
from pydantic import Field
from .base import JsonModel

INPUT_VERSION = "1.0"


class InputFile(JsonModel):
    """Metadata about a single uploaded file (unchanged)."""
    filename: str
    content_type: str
    size_bytes: int


class FileInput(JsonModel):
    """Input from one or more uploaded files."""
    mode: Literal["file"] = "file"
    files: list[InputFile] = Field(default_factory=list)
    pdf_gcs_url: str | None = None   # stub for SP-11 (Show Original)

    @classmethod
    def from_file_uploads(cls, uploads: list[Any]) -> "FileInput":
        """Create a FileInput from a list of werkzeug FileStorage objects.

        Reads each upload's stream to determine size_bytes, then resets
        the stream position with seek(0) so downstream code can still read
        the bytes.
        """
        input_files: list[InputFile] = []
        for upload in uploads:
            raw = upload.read()
            size_bytes = len(raw)
            upload.seek(0)
            input_files.append(
                InputFile(
                    filename=upload.filename or "",
                    content_type=upload.content_type or "",
                    size_bytes=size_bytes,
                )
            )
        return cls(files=input_files)


class TextInput(JsonModel):
    """Input from plain text."""
    mode: Literal["text"] = "text"
    text: str | None = None


class DocIdInput(JsonModel):
    """Input referencing a stored GCS document."""
    mode: Literal["doc_id"] = "doc_id"
    doc_id: str


class BatchDatasetInput(JsonModel):
    """Input derived from a preset batch dataset."""
    mode: Literal["batch_dataset"] = "batch_dataset"
    text: str
    dataset_group: str
    dataset_input: str
    selected_files: list[str]
    batch_group_id: str


# Type alias — the discriminated union IS "Input" for all type annotations.
# Use pydantic.TypeAdapter(Input) to validate a raw dict outside model_validate.
Input = Annotated[
    Union[FileInput, TextInput, DocIdInput, BatchDatasetInput],
    Field(discriminator="mode"),
]
```

**Remove** the old `Input` class entirely — no alias or shim (§9.6 RESOLVED).
**Remove** all four old classmethods (`from_text`, `from_doc_id`, `from_file_uploads`,
`from_batch_dataset`) that lived on the old `Input` class.
Keep the `if TYPE_CHECKING:` block for `werkzeug.datastructures.FileStorage` — it is still used by
`FileInput.from_file_uploads`'s runtime body, so move the import out of `TYPE_CHECKING` (or keep
the pattern used by current code — `TYPE_CHECKING` is fine here since werkzeug is always installed
and the runtime `upload.read()` / `upload.seek()` calls don't require the type annotation).

**Acceptance criteria:**
- `python -c "from models.input import Input, FileInput, TextInput, DocIdInput, BatchDatasetInput, InputFile, INPUT_VERSION"` exits 0.
- `python -c "from pydantic import TypeAdapter; from models.input import Input; a = TypeAdapter(Input); print(a.validate_python({'mode': 'text', 'text': 'x'}))"` prints a `TextInput` repr.
- `python -c "from models.input import Input; Input(mode='text')"` raises `TypeError` (union alias is not callable as a class).

---

### Task 2 — Update `models/__init__.py` to export the four concrete types

**Files:** `backend/models/__init__.py`

Change line 7:
```python
# OLD
from .input import Input, InputFile

# NEW
from .input import Input, InputFile, FileInput, TextInput, DocIdInput, BatchDatasetInput
```

Extend `__all__` to include the four new names after `"InputFile"`:
```python
__all__ = [
    "JsonModel",
    "VersionedModel",
    "CarePlan",
    "CarePlanV1_2",
    "CarePlanV1_2StructuredLLM",
    "CarePlanInternal",
    "is_legacy_shape",
    "Grading",
    "GradingEntry",
    "build_grading",
    "Input",
    "InputFile",
    "FileInput",
    "TextInput",
    "DocIdInput",
    "BatchDatasetInput",
    "Metrics",
]
```

**Acceptance criteria:**
- `python -c "from models import FileInput, TextInput, DocIdInput, BatchDatasetInput"` exits 0.
- `python -c "import models; print(models.__all__)"` output contains all four new names plus the existing ones.

---

### Task 3 — Update `models/envelope.py` — `CarePlanInternal.input` field annotation

**Files:** `backend/models/envelope.py`

The `input` field (line 18) is already declared as `input: Input`. The only change needed is the
**import line** — Pydantic v2 dispatches the discriminated union automatically at
`model_validate` time; no `field_validator` on `input` is needed (§4.3 RESOLVED).

Change line 10:
```python
# OLD
from .input import Input

# NEW
from .input import Input  # union alias; concrete types available via models package if needed
```

No further change is required in this file. The `field_validator` on `care_plan` and the
`field_serializer` on `care_plan` remain untouched.

**Acceptance criteria:**
- `python -c "from models.envelope import CarePlanInternal"` exits 0.
- Constructing `CarePlanInternal(metrics=..., input=TextInput(text='x'), grading=..., care_plan=...)`
  succeeds (tested implicitly by Task 6 tests).
- `CarePlanInternal.model_validate(d)` where `d["input"] = {"mode": "text", "text": "hi"}` returns
  an instance with `.input` being a `TextInput` (tested in Task 6).

> Note: This task may be a no-op for the import line itself if `envelope.py` imports `Input`
> from `.input` and Task 1 left the name `Input` exported. The key confirmation is that the
> discriminated union annotation works end-to-end.

---

### Task 4 — Update `routes/care_plan.py` — `_input_model_from_resolved`

**Files:** `backend/routes/care_plan.py`

1. **Change the import** at line 38:
   ```python
   # OLD
   from models.input import Input, INPUT_VERSION

   # NEW
   from models.input import FileInput, TextInput, DocIdInput, INPUT_VERSION
   ```

2. **Rewrite `_input_model_from_resolved`** (lines 269–286) to use the concrete types:
   ```python
   def _input_model_from_resolved(resolved: ResolvedInput) -> FileInput | TextInput | DocIdInput:
       if resolved.source_kind == "text":
           return TextInput(text=resolved.text)
       if resolved.source_kind == "doc_id":
           raw_doc_id = resolved.source_description.removeprefix("doc:")
           return DocIdInput(doc_id=raw_doc_id)

       # file upload: reconstruct from request files (streams may be exhausted,
       # from_file_uploads seeks them back to 0 after reading)
       uploads = request.files.getlist("files")
       if not uploads and "file" in request.files:
           uploads = [request.files["file"]]
       for upload in uploads:
           try:
               upload.seek(0)
           except Exception:
               pass
       return FileInput.from_file_uploads(uploads)
   ```

No other references to `Input` exist in `care_plan.py` (confirmed by grep). `INPUT_VERSION`
usage elsewhere in the file is unchanged.

**Acceptance criteria:**
- `python -c "from routes.care_plan import _input_model_from_resolved"` exits 0 (no import errors
  from the `Input` removal).
- The function returns a `TextInput` when `resolved.source_kind == "text"`, a `DocIdInput` for
  `"doc_id"`, and a `FileInput` for `"file"` (tested by route-level tests in Task 6).

---

### Task 5 — Update `routes/batch.py` — replace `Input.from_batch_dataset`

**Files:** `backend/routes/batch.py`

1. **Change the import** at line 11:
   ```python
   # OLD
   from models.input import Input

   # NEW
   from models.input import BatchDatasetInput
   ```

2. **Replace the construction block** at lines 189–195:
   ```python
   # OLD
   input_model = Input.from_batch_dataset(
       text=text,
       dataset_group=group,
       dataset_input=input_id,
       selected_files=files,
       batch_group_id=batch_group_id,
   )

   # NEW
   input_model = BatchDatasetInput(
       text=text,
       dataset_group=group,
       dataset_input=input_id,
       selected_files=files,
       batch_group_id=batch_group_id,
   )
   ```

No other references to `Input` exist in `batch.py` — the `input_model` variable is passed
directly into `CarePlanInternal(input=input_model, ...)` which accepts any member of the union.

**Acceptance criteria:**
- `python -c "from routes.batch import batch_bp"` exits 0.
- A `BatchDatasetInput` instance serializes with `mode: "batch_dataset"` (not `"text"`) — verified
  by the unit test in Task 6.

---

### Task 6 — Rewrite `tests/models/test_input_metrics.py`

**Files:** `backend/tests/models/test_input_metrics.py`

Replace the existing file entirely. The old tests assert the all-Nones flat shape which no longer
exists. New tests must cover:

**FileInput:**
```python
from io import BytesIO
import pytest
from pydantic import TypeAdapter, ValidationError
from werkzeug.datastructures import FileStorage
import models.input as input_models
from models.input import (
    Input, FileInput, TextInput, DocIdInput, BatchDatasetInput, InputFile,
)

_input_adapter = TypeAdapter(Input)


def test_input_version_constant():
    assert input_models.INPUT_VERSION == "1.0"


def test_file_input_from_file_uploads_exact_shape_and_resets_stream():
    upload = FileStorage(
        stream=BytesIO(b"pdf bytes"),
        filename="visit.pdf",
        content_type="application/pdf",
    )
    model = FileInput.from_file_uploads([upload])
    assert model.to_dict() == {
        "mode": "file",
        "files": [{"filename": "visit.pdf", "content_type": "application/pdf", "size_bytes": 9}],
        "pdf_gcs_url": None,
    }
    assert upload.read() == b"pdf bytes"   # stream was reset


def test_file_input_default_pdf_gcs_url_is_none():
    assert FileInput(files=[]).to_dict()["pdf_gcs_url"] is None


def test_file_input_rejects_stray_text_field():
    with pytest.raises(ValidationError):
        FileInput(mode="file", text="oops")
```

**TextInput:**
```python
def test_text_input_exact_shape():
    assert TextInput(text="Patient note").to_dict() == {
        "mode": "text",
        "text": "Patient note",
    }


def test_text_input_text_defaults_to_none():
    assert TextInput().to_dict() == {"mode": "text", "text": None}


def test_text_input_rejects_stray_doc_id():
    with pytest.raises(ValidationError):
        TextInput(text="x", doc_id="y")
```

**DocIdInput:**
```python
def test_doc_id_input_exact_shape():
    assert DocIdInput(doc_id="gs://bucket/x.pdf").to_dict() == {
        "mode": "doc_id",
        "doc_id": "gs://bucket/x.pdf",
    }


def test_doc_id_input_rejects_stray_files():
    with pytest.raises(ValidationError):
        DocIdInput(doc_id="x", files=[])
```

**BatchDatasetInput:**
```python
def test_batch_dataset_input_exact_shape_and_mode_is_batch_dataset():
    result = BatchDatasetInput(
        text="Combined text",
        dataset_group="cardiology",
        dataset_input="sample-1",
        selected_files=["a.pdf", "b.txt"],
        batch_group_id="batch-123",
    ).to_dict()
    assert result == {
        "mode": "batch_dataset",
        "text": "Combined text",
        "dataset_group": "cardiology",
        "dataset_input": "sample-1",
        "selected_files": ["a.pdf", "b.txt"],
        "batch_group_id": "batch-123",
    }


def test_batch_dataset_input_requires_all_fields():
    with pytest.raises(ValidationError):
        BatchDatasetInput(text="x", dataset_group="g")   # missing dataset_input etc.
```

**Union dispatch via TypeAdapter:**
```python
def test_type_adapter_dispatches_file():
    result = _input_adapter.validate_python({"mode": "file", "files": []})
    assert isinstance(result, FileInput)


def test_type_adapter_dispatches_text():
    result = _input_adapter.validate_python({"mode": "text", "text": "x"})
    assert isinstance(result, TextInput)


def test_type_adapter_dispatches_doc_id():
    result = _input_adapter.validate_python({"mode": "doc_id", "doc_id": "gs://x"})
    assert isinstance(result, DocIdInput)


def test_type_adapter_dispatches_batch_dataset():
    result = _input_adapter.validate_python({
        "mode": "batch_dataset", "text": "t", "dataset_group": "g",
        "dataset_input": "i", "selected_files": ["a.pdf"], "batch_group_id": "g-ts",
    })
    assert isinstance(result, BatchDatasetInput)


def test_type_adapter_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        _input_adapter.validate_python({"mode": "unknown"})
```

**CarePlanInternal round-trip (one per variant):**
```python
from models.envelope import CarePlanInternal
from models.grading import Grading
from models.metrics import Metrics
from models.care_plan import CarePlan

def _make_internal(input_obj):
    """Helper: build a minimal CarePlanInternal for round-trip tests."""
    ...  # use fixtures or minimal valid Metrics/Grading/CarePlan instances

def test_care_plan_internal_round_trips_text_input():
    c = _make_internal(TextInput(text="hi"))
    restored = CarePlanInternal.model_validate(c.to_dict())
    assert isinstance(restored.input, TextInput)
    assert restored.input.text == "hi"

# Repeat for FileInput, DocIdInput, BatchDatasetInput
```

> Implementation note: for the round-trip helper, construct minimal `Metrics`, `Grading`, and
> `CarePlan` instances using real model constructors (not raw dicts), or import from a shared
> fixture if the project's `conftest.py` provides one.

**Acceptance criteria:**
- All new tests pass: `python -m pytest backend/tests/models/test_input_metrics.py -v` exits 0.
- No test asserts stray Nones (`doc_id: None`, `files: []`, `dataset_group: None`, etc.) on
  variants that don't own those fields.
- The `mode: "batch_dataset"` assertion confirms the old `"text"` mode string is gone.

---

### Task 7 — Update `tests/models/test_exports.py`

**Files:** `backend/tests/models/test_exports.py`

1. **Add the four concrete type names** to the existing import smoke-test block at lines 7–21:
   ```python
   from models import (  # noqa: F401
       CarePlan,
       CarePlanInternal,
       CarePlanV1_2,
       CarePlanV1_2StructuredLLM,
       FileInput,        # NEW
       Grading,
       GradingEntry,
       Input,
       InputFile,
       JsonModel,
       Metrics,
       TextInput,        # NEW
       DocIdInput,       # NEW
       BatchDatasetInput, # NEW
       VersionedModel,
       build_grading,
       is_legacy_shape,
   )
   ```

2. **Update the `__all__` assertion** at lines 23–37 to match the new list from §4.6:
   ```python
   assert models.__all__ == [
       "JsonModel",
       "VersionedModel",
       "CarePlan",
       "CarePlanV1_2",
       "CarePlanV1_2StructuredLLM",
       "CarePlanInternal",
       "is_legacy_shape",
       "Grading",
       "GradingEntry",
       "build_grading",
       "Input",
       "InputFile",
       "FileInput",
       "TextInput",
       "DocIdInput",
       "BatchDatasetInput",
       "Metrics",
   ]
   ```

Keep `test_models_do_not_export_removed_aliases` unchanged.

**Acceptance criteria:**
- `python -m pytest backend/tests/models/test_exports.py -v` exits 0.
- `from models import FileInput, TextInput, DocIdInput, BatchDatasetInput` succeeds without error.

---

### Task 8 — Update `frontend/src/types/envelope.ts` — TypeScript discriminated union

**Files:** `frontend/src/types/envelope.ts`

Replace the flat `Input` interface (lines 12–17) with four concrete interfaces and a union type:

```typescript
// REMOVE the old flat Input interface entirely, then add:

export interface FileInput {
  mode: 'file';
  files: InputFile[];
  pdf_gcs_url: string | null;  // stub for SP-11 (Show Original)
}

export interface TextInput {
  mode: 'text';
  text: string | null;
}

export interface DocIdInput {
  mode: 'doc_id';
  doc_id: string;
}

export interface BatchDatasetInput {
  mode: 'batch_dataset';
  text: string;
  dataset_group: string;
  dataset_input: string;
  selected_files: string[];
  batch_group_id: string;
}

export type Input = FileInput | TextInput | DocIdInput | BatchDatasetInput;
```

`CarePlanInternal.input: Input` (line 50) needs no change — the alias now resolves to the union.
`InputFile` (lines 6–10) stays unchanged.

Do NOT remove `step_durations_ms` from the `Metrics` interface — that cleanup is deferred to
SP-13 (§9.8 DEFERRED).

After editing, verify `CarePlanPage.tsx` needs no change: the existing `outputHasInputPdf` function
narrows on `output.input.mode === 'file'` before accessing `.files`, which TypeScript will now
resolve correctly to `FileInput` via discriminated union narrowing (§4.7).

**Acceptance criteria:**
- `cd frontend && npx tsc --noEmit` exits 0 with no type errors related to `Input`.
- `CarePlanPage.tsx` produces no TypeScript errors on its `output.input.mode === 'file'` and
  `output.input.files.some(...)` access (TypeScript narrows correctly).

---

### Task 9 — Frontend TypeScript type-error sweep

**Files:** Any `frontend/src/**/*.ts` or `frontend/src/**/*.tsx` that accesses `input.text`,
`input.doc_id`, `input.files`, `input.dataset_group`, `input.dataset_input`,
`input.selected_files`, or `input.batch_group_id` without a prior `mode` guard.

Run the sweep command:
```bash
grep -rn "\.input\.\(text\|doc_id\|files\|dataset_group\|dataset_input\|selected_files\|batch_group_id\)" frontend/src/
```

For each hit, either:
- Add a `mode` guard before the access (`if (output.input.mode === 'file') { ... }`), or
- Use optional chaining if appropriate for that branch.

Based on the current codebase read, only `CarePlanPage.tsx:52` accesses `input` sub-fields, and
it already has a `mode === 'file'` guard — so this task may be a no-op. Run it anyway to confirm
no hidden consumers were missed.

Then confirm the full TypeScript build is clean:
```bash
cd frontend && npx tsc --noEmit
```

**Acceptance criteria:**
- `npx tsc --noEmit` exits 0.
- Zero TypeScript errors of the form "Property 'X' does not exist on type 'Input'".

---

## Summary of what requires you (not a dev agent)

1. **`mode: "batch_dataset"` breaking change confirmed (§8.1).** No old data exists; the mode
   string change from `"text"` to `"batch_dataset"` for batch dataset runs is explicitly approved.
   No action needed — a dev agent implements it; you have pre-confirmed it.

2. **Frontend TypeScript build sweep (§8.2).** After Task 8 lands, run `cd frontend && npx tsc
   --noEmit`. If any component other than `CarePlanPage.tsx` accesses `input.*` fields without a
   `mode` guard, TypeScript will surface the error here. Fix those access sites with a `mode` check
   before the PR is marked green. Task 9 codifies this but you should verify the tsc output
   yourself since hidden consumers could exist in components added after the last codebase read.

3. **`models/__init__.py` / `test_exports.py` kept in lockstep (§8.3).** Both are updated in
   Tasks 2 and 7 — no further action needed unless new model types are added later.
