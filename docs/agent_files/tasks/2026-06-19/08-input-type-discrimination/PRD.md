# PRD: Input Type Discrimination (SP-08)

Sub-project 8 of the Juno backend refactor. Phase 4 (no dependencies). The **current `Input`
model** is a single class with `mode: str` and six optional fields — a design that allows
structurally invalid instances (`mode="file"` with `text` set, `mode="text"` with `files`
populated, etc.) and cannot express per-variant contracts to Pydantic's strict validator. This
sub-project replaces it with a **type-discriminated Pydantic union** where each variant carries
exactly the fields it needs.

## 1. Problem

`models/input.py` defines one `Input` class:

```python
class Input(JsonModel):
    mode: str  # "file" | "text" | "doc_id"
    text: str | None = None
    doc_id: str | None = None
    files: list[InputFile] = Field(default_factory=list)
    dataset_group: str | None = None
    dataset_input: str | None = None
    selected_files: list[str] | None = None
    batch_group_id: str | None = None
```

Every optional field appears in the serialized dict for every variant. `Input.from_text("x").to_dict()`
emits `doc_id: null, files: [], dataset_group: null, ...` — six irrelevant keys for a text input.
`CarePlanInternal.input` is typed as `Input`, so the envelope stores and passes this over-specified
dict to Firestore and to the frontend.

Three concrete problems:

1. **No per-variant validation.** Pydantic cannot enforce that `mode="file"` has `files` populated,
   or that `mode="doc_id"` has `doc_id` set, because they are all `Optional` on one class.
2. **Stray Nones everywhere.** Every serialized input dict carries nulls for every field that doesn't
   apply to the current mode. The frontend `Input` interface and the tests are written around this
   shape — every assertion checks `doc_id: null, dataset_group: null, ...` explicitly.
3. **Flat classmethods on a single class.** `Input.from_text`, `Input.from_doc_id`,
   `Input.from_file_uploads`, `Input.from_batch_dataset` are convenience constructors but share one
   model, so there is no type-level guarantee which variant you hold.

Additionally, the current tests in `tests/models/test_input_metrics.py` hard-code the "all-Nones"
shape — they will break as written when SP-08 lands and must be rewritten.

## 2. Goals

1. Define **four concrete `Input` variant models**, each a `JsonModel` subclass with only the fields
   it needs and a `Literal` discriminator on `mode`.
2. Define **`Input`** as a Pydantic v2 type-discriminated union:
   `Annotated[Union[FileInput, TextInput, DocIdInput, BatchDatasetInput], Field(discriminator="mode")]`.
3. Update **`models/envelope.py`** so `CarePlanInternal.input` is typed as the union and
   deserializes correctly via a `field_validator`.
4. Update **`routes/care_plan.py`** (`_input_model_from_resolved`) to construct the right concrete
   type directly.
5. Update **`routes/batch.py`** (`Input.from_batch_dataset` call) to use `BatchDatasetInput(...)`.
6. Update **`frontend/src/types/envelope.ts`** `Input` interface to a TypeScript discriminated union.
7. Rewrite **`tests/models/test_input_metrics.py`** to test each concrete type's own shape (no stray
   Nones in assertions).
8. Keep **`INPUT_VERSION = "1.0"`** and **`InputFile`** unchanged.
9. Stub **`pdf_gcs_url: str | None = None`** on `FileInput` for SP-11 (Show Original).

## 3. Non-Goals

- **Not** changing `InputFile` — filename metadata model is correct as-is.
- **Not** changing `INPUT_VERSION` — the constant stays at `"1.0"`.
- **Not** adding any Firestore migration or legacy-read shims — per the locked initiative decision,
  no old data concern exists. Reads stay tolerant only where explicitly noted (see §4.3).
- **Not** populating `pdf_gcs_url` — SP-11 owns that; SP-08 only adds the stub field.
- **Not** changing the `Metrics` model, `CarePlan`, or any grading logic.
- **Not** changing the `__init__.py` exports list — `Input` and `InputFile` remain exported by the
  same names; the union alias replaces the old class transparently.
- **Not** touching the frontend beyond `types/envelope.ts` — `CarePlanPage.tsx`'s
  `outputHasInputPdf` already accesses `output.input.mode` and `output.input.files`, which remain
  valid on the `FileInput` branch (no code change needed there; see §6).

## 4. Architecture Decisions

### 4.1 `models/input.py` — four concrete types + union alias

Replace the single `Input` class with four concrete `JsonModel` subclasses, each with a `Literal`
`mode` discriminator. Define `Input` as a module-level union alias using Pydantic v2's
`Annotated[Union[...], Field(discriminator="mode")]`.

```python
# backend/models/input.py
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
        """Create a FileInput from a list of werkzeug FileStorage objects."""
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
    text: str


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
Input = Annotated[
    Union[FileInput, TextInput, DocIdInput, BatchDatasetInput],
    Field(discriminator="mode"),
]
```

**Key decisions explained:**

- `mode` is a `Literal` on each concrete type — Pydantic v2's discriminated union dispatch requires
  the discriminator field to be present on each member, which `Literal["file"]` etc. satisfy.
- The constructor classmethods move to the concrete type where they belong:
  `FileInput.from_file_uploads`, with `TextInput(text=...)` and `DocIdInput(doc_id=...)` and
  `BatchDatasetInput(...)` used directly at call-sites (no classmethods needed there — direct
  construction is cleaner and fully explicit).
- `BatchDatasetInput.mode` is `"batch_dataset"`, not `"text"`. The old `Input.from_batch_dataset`
  set `mode="text"` — a semantic error: batch dataset runs are a distinct input kind, not plain
  text. Now they are distinguishable. **This is a breaking change to the serialized shape** (old
  `mode: "text"` → new `mode: "batch_dataset"`), intentional per the no-legacy-data decision.
- All fields on each concrete type are **required** (no `Optional`, no `None` defaults) except
  `files` on `FileInput` (defaults to `[]` to allow the empty-list case before uploads are
  attached) and `pdf_gcs_url` (SP-11 stub, optional by design).
- `Input` is a type alias, not a class. `isinstance(x, Input)` will not work — use
  `isinstance(x, (FileInput, TextInput, DocIdInput, BatchDatasetInput))` when needed. In practice,
  call-sites construct concrete types and the envelope holds the union, so no `isinstance` check on
  the union itself exists today.

**Removed classmethods on the old `Input`:**

| Old | New |
|---|---|
| `Input.from_text(text)` | `TextInput(text=text)` |
| `Input.from_doc_id(doc_id)` | `DocIdInput(doc_id=doc_id)` |
| `Input.from_file_uploads(uploads)` | `FileInput.from_file_uploads(uploads)` |
| `Input.from_batch_dataset(text, ...)` | `BatchDatasetInput(text=text, ...)` |

### 4.2 Serialized shapes — old vs. new

The key change is **no stray Nones** and **exact fields per variant**.

**FileInput (was `mode="file"`):**
```jsonc
// OLD
{ "mode": "file", "text": null, "doc_id": null, "files": [...],
  "dataset_group": null, "dataset_input": null, "selected_files": null, "batch_group_id": null }

// NEW
{ "mode": "file", "files": [...], "pdf_gcs_url": null }
```

**TextInput (was `mode="text"` with no dataset fields):**
```jsonc
// OLD
{ "mode": "text", "text": "Patient note", "doc_id": null, "files": [],
  "dataset_group": null, "dataset_input": null, "selected_files": null, "batch_group_id": null }

// NEW
{ "mode": "text", "text": "Patient note" }
```

**DocIdInput (was `mode="doc_id"`):**
```jsonc
// OLD
{ "mode": "doc_id", "text": null, "doc_id": "gs://bucket/x.pdf", "files": [],
  "dataset_group": null, "dataset_input": null, "selected_files": null, "batch_group_id": null }

// NEW
{ "mode": "doc_id", "doc_id": "gs://bucket/x.pdf" }
```

**BatchDatasetInput (was `mode="text"` with dataset fields):**
```jsonc
// OLD
{ "mode": "text", "text": "...", "doc_id": null, "files": [],
  "dataset_group": "cardiology", "dataset_input": "sample-1",
  "selected_files": ["a.pdf"], "batch_group_id": "cardiology-20260621" }

// NEW — mode is now "batch_dataset", not "text"
{ "mode": "batch_dataset", "text": "...",
  "dataset_group": "cardiology", "dataset_input": "sample-1",
  "selected_files": ["a.pdf"], "batch_group_id": "cardiology-20260621" }
```

### 4.3 `models/envelope.py` — `CarePlanInternal.input` deserialization

`CarePlanInternal.input` is declared as `Input` (the union alias). When Pydantic deserializes
`CarePlanInternal` from a Firestore dict, it must dispatch the raw `input` sub-dict to the right
concrete type. Pydantic v2 handles this **automatically via the `discriminator="mode"` annotation**
on the `Input` union — `model_validate` reads `data["input"]["mode"]` and picks the right member.

**No `field_validator` on `input` is needed** for the happy path. The current `field_validator` on
`care_plan` exists because `CarePlan` is a `VersionedModel` whose `from_dict` does version dispatch
— `Input` is a plain discriminated union that Pydantic v2 dispatches natively.

The `field_validator` should be **left on `care_plan` unchanged**. For `input`, the field
declaration alone is sufficient:

```python
# models/envelope.py — only the changed field declaration shown
class CarePlanInternal(JsonModel):
    metrics: Metrics
    input: Input          # union; Pydantic dispatches via mode discriminator automatically
    grading: Grading
    care_plan: CarePlan
    before_score: dict | None = None
    after_score: dict | None = None
    # ... existing field_validator on care_plan and field_serializer on care_plan unchanged
```

The import in `envelope.py` changes from `from .input import Input` to
`from .input import Input, FileInput, TextInput, DocIdInput, BatchDatasetInput` — import
`Input` (the union alias) for the field annotation; the concrete types are available if needed
downstream but need not all be imported here. Practically, only `Input` is needed for the type
annotation; concrete types are imported at call-sites.

**Tolerant read note:** Existing Firestore documents with the old `Input` shape (all-Nones, `mode:
"text"` for batch) will **fail deserialization** if ever re-validated through `CarePlanInternal`.
Per the initiative's locked no-legacy-data decision this is fine — GET /care_plan/saved/:id
reads `output_data` as a raw dict and does not re-validate through `CarePlanInternal`. No tolerant
read shim is needed or written.

### 4.4 `routes/care_plan.py` — `_input_model_from_resolved`

Update `_input_model_from_resolved` (line 269) to return a concrete type, not `Input.from_*`:

```python
# routes/care_plan.py
from models.input import FileInput, TextInput, DocIdInput, InputFile

def _input_model_from_resolved(resolved: ResolvedInput) -> FileInput | TextInput | DocIdInput:
    if resolved.source_kind == "text":
        return TextInput(text=resolved.text)
    if resolved.source_kind == "doc_id":
        raw_doc_id = resolved.source_description.removeprefix("doc:")
        return DocIdInput(doc_id=raw_doc_id)

    # file upload: reconstruct from request files
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

The return type annotation is now the union of concrete types (`FileInput | TextInput | DocIdInput`)
rather than `Input`. This is fine — each is a valid member of the `Input` union alias and
`CarePlanInternal(input=...)` accepts any of them.

The `import` at the top of `care_plan.py` changes from `from models.input import Input` to
`from models.input import FileInput, TextInput, DocIdInput`.

### 4.5 `routes/batch.py` — BatchDatasetInput construction

The batch route currently calls `Input.from_batch_dataset(...)` (line 189). Replace with direct
`BatchDatasetInput` construction:

```python
# routes/batch.py — updated import and construction
from models.input import BatchDatasetInput   # replaces: from models.input import Input

# inside generate(), replacing lines 189-195:
input_model = BatchDatasetInput(
    text=text,
    dataset_group=group,
    dataset_input=input_id,
    selected_files=files,
    batch_group_id=batch_group_id,
)
```

No other logic in `batch.py` references `Input` — `input_model` is passed directly into
`CarePlanInternal(input=input_model, ...)` which accepts the union.

### 4.6 `models/__init__.py` — export the concrete types

Add `FileInput`, `TextInput`, `DocIdInput`, `BatchDatasetInput` to the module exports alongside the
existing `Input` alias and `InputFile`. This lets call-sites do
`from models import FileInput, TextInput, DocIdInput, BatchDatasetInput` without importing from
the sub-module directly. Update `__all__` accordingly:

```python
# models/__init__.py — updated input exports
from .input import Input, InputFile, FileInput, TextInput, DocIdInput, BatchDatasetInput

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

`tests/models/test_exports.py` must be updated to assert the new `__all__` list (add the four
concrete type names; `Input` and `InputFile` stay).

### 4.7 `frontend/src/types/envelope.ts` — TypeScript discriminated union

Replace the flat `Input` interface with a TypeScript discriminated union. The existing
`CarePlanInternal.input: Input` field type stays but now refers to the union.

```typescript
// frontend/src/types/envelope.ts — updated Input section

export interface InputFile {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface FileInput {
  mode: 'file';
  files: InputFile[];
  pdf_gcs_url: string | null;  // stub for SP-11
}

export interface TextInput {
  mode: 'text';
  text: string;
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

`CarePlanInternal` in the same file needs no change — `input: Input` already uses the type alias;
the alias just now resolves to a union instead of a flat interface.

**Impact on `CarePlanPage.tsx`:** `outputHasInputPdf` (line 51–55) narrows via `output.input.mode
=== 'file'` — TypeScript will narrow `output.input` to `FileInput` inside that branch, making
`.files` directly accessible. The code as written is already correct; no change needed in
`CarePlanPage.tsx`.

```typescript
// CarePlanPage.tsx:51-55 — NO CHANGE NEEDED; already narrows correctly
function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.files.some(file => (
    file.content_type === 'application/pdf' || file.filename.toLowerCase().endsWith('.pdf')
  ));
}
```

Any other frontend code that currently accesses `output.input.text` or `output.input.doc_id`
without first narrowing on `mode` will produce a **TypeScript type error** — this is the intended
outcome; it surfaces unsound access patterns. Search for `input.text`, `input.doc_id`,
`input.files`, `input.dataset_group` across `frontend/src/` and add `mode` narrows where needed.
(Based on the read of `CarePlanPage.tsx` only `outputHasInputPdf` accesses `input` fields
directly; other pages that render input details may need similar treatment.)

### 4.8 Pydantic v2 discriminated union mechanics — how deserialization works

Pydantic v2 discriminated unions via `Annotated[Union[...], Field(discriminator="mode")]` work as
follows:

- On `model_validate(data)` of a model that has a field annotated as the union, Pydantic reads
  `data["input"]["mode"]` and selects the matching `Literal` member.
- Each member's `extra="forbid"` (inherited from `JsonModel`) applies **after** the member is
  selected — so a `FileInput` dict with a `text` key will raise `ValidationError` even though
  `TextInput` would accept it.
- On `model_dump(mode="json")`, Pydantic serializes the concrete instance's fields only — no stray
  Nones from sibling variants appear.
- `CarePlanInternal.model_validate({"input": {"mode": "file", "files": [...]}, ...})` works without
  any custom validator on `input` — Pydantic dispatches automatically.

One subtlety: `Input` is a **type alias** (`= Annotated[Union[...], ...]`), not a class. You
cannot do `Input.model_validate(data)` directly. To validate a raw dict into an `Input` union
member, use `pydantic.TypeAdapter`:

```python
from pydantic import TypeAdapter
_input_adapter = TypeAdapter(Input)
parsed_input = _input_adapter.validate_python({"mode": "text", "text": "..."})
# -> TextInput instance
```

Call-sites that construct inputs directly (routes, tests) do not need `TypeAdapter` — they
construct the concrete type. `TypeAdapter` is only needed if code somewhere deserializes a raw
`input` dict outside of a `CarePlanInternal.model_validate` call. No such site exists today, but
document the pattern for future use.

## 5. API Change Summary

SP-08 changes the **serialized `input` sub-dict** shape in all endpoints that return
`CarePlanInternal.to_dict()`:

```
POST /care_plan        — response["input"] shape changes (no stray Nones; mode="batch_dataset" for batch runs)
POST /care_plan/batch  — same; BatchDatasetInput now uses mode="batch_dataset"
GET  /care_plan/saved/:id — raw dict pass-through; no re-validation; no shape change on read
```

The wire change is **backward-incompatible** by design (stray Nones removed; batch mode
string changed). Nothing is in production; no compatibility shim is written.

Firestore `simplify_outputs.output_data.input` key shape changes:

| Variant | Old persisted shape | New persisted shape |
|---|---|---|
| file | 8-key dict with 5 Nones | `{mode, files, pdf_gcs_url}` |
| text | 8-key dict with 6 Nones | `{mode, text}` |
| doc_id | 8-key dict with 6 Nones | `{mode, doc_id}` |
| batch_dataset | 8-key dict, `mode: "text"` | `{mode: "batch_dataset", text, dataset_group, dataset_input, selected_files, batch_group_id}` |

## 6. Frontend Change Summary

One file changes: **`frontend/src/types/envelope.ts`** — replace the flat `Input` interface with
the four-member discriminated union (§4.7).

No change to `CarePlanPage.tsx` — `outputHasInputPdf` already narrows on `mode === 'file'` before
accessing `.files`; TypeScript narrows `FileInput` automatically via the discriminated union.

If any other frontend component accesses `input.text`, `input.doc_id`, `input.dataset_group`, etc.
without first narrowing on `mode`, TypeScript will now surface a type error. Those access sites
must add a `mode` check (or use optional chaining if the field is truly optional for that branch).
A project-wide search for `\.input\.(text|doc_id|files|dataset_group|dataset_input|selected_files|batch_group_id)`
in `frontend/src/` before the PR merge is recommended.

`Metrics.step_durations_ms` is still present in the frontend `Metrics` interface
(`envelope.ts:39`) but was removed from the backend model in SP-01. This is a pre-existing
discrepancy outside SP-08's scope; SP-13 (Frontend Code Organization) or a targeted follow-up
should remove it from the TS interface.

## 7. Testing

### 7.1 Rewrite `tests/models/test_input_metrics.py`

The existing tests assert the old all-Nones shape and must be replaced. New tests per concrete type:

**FileInput:**
- `FileInput.from_file_uploads([...]).to_dict()` equals `{"mode": "file", "files": [...], "pdf_gcs_url": null}` — exactly three keys, no stray Nones.
- `FileInput(files=[]).to_dict()` has `pdf_gcs_url: null` (SP-11 stub default).
- `FileInput(mode="file", text="x")` raises `ValidationError` (`text` is an unknown field).
- Stream seek behavior preserved: after `from_file_uploads`, upload stream is readable again.

**TextInput:**
- `TextInput(text="Patient note").to_dict()` equals `{"mode": "text", "text": "Patient note"}` — exactly two keys.
- `TextInput(text="x", doc_id="y")` raises `ValidationError`.
- `TextInput(mode="text")` raises `ValidationError` (missing required `text`).

**DocIdInput:**
- `DocIdInput(doc_id="gs://bucket/x.pdf").to_dict()` equals `{"mode": "doc_id", "doc_id": "gs://bucket/x.pdf"}`.
- `DocIdInput(doc_id="x", files=[])` raises `ValidationError`.

**BatchDatasetInput:**
- `BatchDatasetInput(text="...", dataset_group="g", dataset_input="i", selected_files=["a.pdf"], batch_group_id="g-ts").to_dict()` equals the expected six-key dict with `mode: "batch_dataset"`.
- Missing any required field raises `ValidationError`.

**Union dispatch (TypeAdapter):**
- `_input_adapter.validate_python({"mode": "file", "files": []})` returns a `FileInput`.
- `_input_adapter.validate_python({"mode": "text", "text": "x"})` returns a `TextInput`.
- `_input_adapter.validate_python({"mode": "doc_id", "doc_id": "x"})` returns a `DocIdInput`.
- `_input_adapter.validate_python({"mode": "batch_dataset", ...})` returns a `BatchDatasetInput`.
- `_input_adapter.validate_python({"mode": "unknown"})` raises `ValidationError`.

**CarePlanInternal round-trip:**
- A `CarePlanInternal` with `input=TextInput(text="x")` round-trips: `CarePlanInternal.model_validate(c.to_dict()).input` is a `TextInput` with `text="x"`.
- Same for `FileInput`, `DocIdInput`, `BatchDatasetInput`.

**`INPUT_VERSION` constant:**
- `assert input_models.INPUT_VERSION == "1.0"` — preserved.

### 7.2 Update `tests/models/test_exports.py`

The `__all__` assertion must include the four new concrete type names:

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

Also add import smoke-tests for each new concrete type.

## 8. Manual Intervention Required From You

1. **Review `mode: "batch_dataset"` breaking change.** The old `Input.from_batch_dataset` stored
   `mode: "text"` in Firestore. After SP-08, `BatchDatasetInput` stores `mode: "batch_dataset"`.
   Any existing Firestore documents that encode `mode: "text"` with dataset fields cannot be
   re-validated through `CarePlanInternal` after this change. Per the locked no-legacy-data
   decision this is intentional, but confirm you are comfortable with the batch-mode string flip
   before merging.

2. **Frontend type-error sweep.** After updating `frontend/src/types/envelope.ts`, run
   `npx tsc --noEmit` from `frontend/`. If any component accesses `input.text` or `input.doc_id`
   without a `mode` guard, TypeScript will error. Fix those sites before the PR is considered
   green. (Based on reading `CarePlanPage.tsx`, `outputHasInputPdf` is already safe; confirm no
   other component has bare `input.doc_id` or `input.text` access.)

3. **No `models/__init__.py` `__all__` auto-sync.** The `__all__` in `models/__init__.py` and the
   assertion in `tests/models/test_exports.py` must be kept in lockstep manually — adding a new
   input type later requires updating both. Note this for the project README or a future lint rule.

## 9. Open Questions & Decisions

1. **Should `TextInput.text` be `str` (required) or `str | None`?**
   `[RESOLVED: str, required. TextInput only exists when there is text; an empty or null text
   input is a caller error, not a valid state. If the pipeline produces empty text it should raise
   before constructing TextInput. BatchDatasetInput.text is similarly required — the batch route
   already guards for empty text before constructing the input model (batch.py:174-182).]`

2. **`mode="batch_dataset"` — is this an API contract change the frontend needs to handle?**
   `[RESOLVED: Yes, but the frontend does not currently branch on mode="batch_dataset". The
   frontend Input union includes BatchDatasetInput for type completeness; no existing frontend code
   path switches on batch_dataset. The batch route's output is consumed by the batch results panel
   (CarePlanPage.tsx:batchOutputs), which does not inspect input.mode. The frontend TypeScript
   union correctly includes BatchDatasetInput, and the mode string change is wire-clean because
   batch and non-batch outputs are never mixed in the same consumer path today.]`

3. **Should `FileInput.from_file_uploads` remain a classmethod or become a module-level function?**
   `[RESOLVED: Keep as @classmethod on FileInput. It constructs a FileInput instance, reads
   werkzeug streams, and is logically bound to the type. Moving it to a module-level function
   gains nothing and breaks the symmetry with the old Input.from_file_uploads call-site pattern.]`

4. **Should the `Input` union alias be defined in a `TYPE_CHECKING` block only, or as a real
   runtime alias?**
   `[RESOLVED: Real runtime alias. Pydantic's TypeAdapter and field annotation both require the
   union to be resolvable at runtime, not just at type-check time. Define Input as a module-level
   assignment, not inside TYPE_CHECKING.]`

5. **Does `CarePlanInternal`'s `field_validator` on `input` need to be added for Firestore
   deserialization?**
   `[RESOLVED: No. Pydantic v2 natively dispatches discriminated union fields via the discriminator
   annotation during model_validate. The existing field_validator on care_plan is needed because
   CarePlan is a VersionedModel with custom from_dict dispatch — not because of a Pydantic
   limitation on union fields. The input field requires no field_validator; Pydantic handles it.]`

6. **Should SP-08 remove the old `Input` class entirely or keep it for a transition window?**
   `[RESOLVED: Remove entirely. No alias, no shim. Per the locked initiative decision, nothing is
   in production and breaking changes are fine. The module exports `Input` as the union alias
   under the same name — import sites that do `from models.input import Input` continue to work;
   only code that calls `Input(mode="text", ...)` or `Input.from_text(...)` breaks and must be
   updated.]`

7. **SP-11 `pdf_gcs_url` stub — should it be on `FileInput` only or on all variants?**
   `[RESOLVED: FileInput only. The GCS URL for the input PDF only makes sense when the input is a
   file upload. TextInput and DocIdInput have no associated PDF file. BatchDatasetInput assembles
   text from preset data, not from a GCS-stored PDF. SP-11 will populate pdf_gcs_url on FileInput
   instances where a PDF was uploaded and stored.]`

8. **`frontend/src/types/envelope.ts` — should `step_durations_ms` be removed from `Metrics`
   as part of this SP?**
   `[DEFERRED to SP-13 (Frontend Code Organization). It is a pre-existing discrepancy between the
   frontend Metrics interface and the backend model (which dropped step_durations_ms in SP-01).
   SP-08 touches envelope.ts only for the Input change; removing step_durations_ms is a separate
   cleanup.]`
