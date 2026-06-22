# PRD: Show Original & Input Display Redesign (SP-11)

Sub-project 11 of the Juno initiative, Phase 5. **Depends on SP-08** (Input type discrimination with
discriminated union and `FileInput.pdf_gcs_url` stub). This sub-project lands **after SP-08** and
covers the full round-trip: storing the PDF GCS URL inside the input envelope, removing the stale
top-level Firestore field, and updating the frontend to make display decisions entirely from the
typed input model — PDF iframe for file inputs, inline text for text/batch inputs.

## 1. Problem

The current "Show Original" flow has two architectural problems that SP-08's discriminated union is
designed to fix, but SP-08 only adds the stub field. SP-11 closes the loop.

**Backend storage mismatch.** The combined input PDF's GCS URI is saved as a top-level Firestore
field `input_pdf_gcs` (written at `firebase.py:123`, read at `saved_outputs.py:136`). This is
separate from the `output_data.input` envelope that SP-08 redesigned as a typed discriminated union.
`FileInput.pdf_gcs_url` is the right place for this URL — it belongs to the file input, not to the
document root — but SP-08 only stubs the field (`pdf_gcs_url: str | None = None`). SP-11 populates
it and stops writing the top-level field.

**Frontend display decisions derived from wrong signals.** The "Show Original" button condition at
`CarePlanPage.tsx:51-55` checks `input.files` for PDF file metadata — a file-name heuristic — rather
than the authoritative `pdf_gcs_url` that SP-08 gives us. Worse, `SplitView.tsx` always calls the
signed-URL API (`getInputPdfUrl`) and always renders an iframe; for text/batch inputs there is no
PDF and no signed URL, so the button correctly never appears, but the display logic is not
generalized: text inputs cannot show their original text in a split view at all. SP-11 makes the
input model the single source of truth for both cases.

## 2. Goals

1. Populate `FileInput.pdf_gcs_url` on the `Input` model **before** saving, so the GCS URI lives
   inside the envelope at `output_data.input.pdf_gcs_url`.
2. Remove `input_pdf_gcs` from the Firestore document root (`firebase.py` signature + write).
3. Update `get_input_pdf_url` (signed URL endpoint) to read from `output_data.input.pdf_gcs_url`
   with a tolerant fallback to the legacy top-level `input_pdf_gcs` for existing documents.
4. Update `routes/batch.py` so the `input_pdf_gcs=None` kwarg is removed from the
   `save_care_plan_output` call (the kwarg no longer exists after goal 2).
5. Update the FE `Input` discriminated union in `envelope.ts` to carry `pdf_gcs_url: string | null`
   on the `FileInput` variant (mirroring SP-08's backend type).
6. Update `outputHasInputPdf` in `CarePlanPage.tsx` to check `input.pdf_gcs_url != null` instead of
   scanning filenames.
7. Extend "Show Original" to text and batch-dataset inputs: display `input.text` in an inline panel
   (no API call, no iframe).
8. Rework `SplitView.tsx` to accept either a signed PDF URL (file input) or raw text (text/batch
   input), removing the hardcoded `getInputPdfUrl` call from the component.

## 3. Non-Goals

- No Firestore data migration. Existing documents have `input_pdf_gcs` at top level only. The
  endpoint falls back to the legacy field (tolerant read); no backfill runner or migration path is
  needed (nothing meaningful is in production).
- No change to the signed URL expiry (30 minutes, `v4`) or the endpoint URL path.
- No change to the upload logic (`upload_combined_pdf`); it continues to return a `gs://` URI.
- No change to grading, care plan schema, pipeline steps, or observability.
- `doc_id` input mode is deferred — see §9 [DEFERRED].
- No change to the batch route's pipeline invocation or dataset resolution logic; only the
  `save_care_plan_output` call signature is touched.

## 4. Architecture Decisions

### 4.1 `backend/models/input.py` — SP-08 owns this file

SP-08 defines the discriminated union with three (or four) concrete variants:

| Variant class      | `mode` literal      | Has `pdf_gcs_url` |
|--------------------|---------------------|-------------------|
| `FileInput`        | `"file"`            | yes — `str \| None = None` (stub from SP-08; SP-11 populates it) |
| `TextInput`        | `"text"`            | no                |
| `DocIdInput`       | `"doc_id"`          | no                |
| `BatchDatasetInput`| `"batch_dataset"` * | no                |

*SP-08 may fold batch into `TextInput` with extra fields. SP-11 is agnostic to that detail: the
rule is "if the input has `pdf_gcs_url` and it is non-null, fetch a signed URL; otherwise read
`.text` for inline display."

SP-11 does **not** touch `models/input.py` itself. It only relies on `FileInput.pdf_gcs_url`
being present and settable, which SP-08 guarantees.

### 4.2 `backend/routes/care_plan.py` — populate `pdf_gcs_url`; remove `input_pdf_gcs` kwarg

Current save block (lines 562–591):

```python
# BEFORE (SP-11)
input_pdf_gcs = None
if resolved.combined_pdf_bytes:
    input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
...
saved_id = save_care_plan_output(
    user_id=user_id,
    name=_derive_output_name(care_plan_data, resolved),
    source_filename=resolved.source_filename,
    input_pdf_gcs=input_pdf_gcs,       # <-- top-level field
    output_data=payload,
)
```

New approach — set the URL on the input model **before** `envelope.to_dict()` is called, so it
lands inside `output_data.input.pdf_gcs_url`:

```python
# AFTER (SP-11)
if resolved.combined_pdf_bytes:
    gcs_uri = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
    input_model.pdf_gcs_url = gcs_uri      # FileInput; set before serialization

# Re-serialize the envelope AFTER mutating input_model so pdf_gcs_url is in payload.
# (If envelope.to_dict() was already called above, call it again here, or defer
# the first to_dict() call until after this mutation — implementer's choice.)
payload = envelope.to_dict()

...
saved_id = save_care_plan_output(
    user_id=user_id,
    name=_derive_output_name(care_plan_data, resolved),
    source_filename=resolved.source_filename,
    output_data=payload,               # no input_pdf_gcs kwarg
)
```

Key constraints:
- `input_model.pdf_gcs_url = gcs_uri` is only valid when `input_model` is a `FileInput` instance.
  The route already knows `resolved.combined_pdf_bytes` is non-None only for file uploads, so the
  branch is safe without an `isinstance` guard; adding one for clarity is acceptable.
- The `envelope.to_dict()` call must happen **after** the mutation. Currently the route calls
  `payload = envelope.to_dict()` at line 560 before entering the `_save` closure. The dev must move
  `envelope.to_dict()` to inside the closure, or reconstruct the envelope dict from `input_model`
  after mutation. The simplest fix: call `payload = envelope.to_dict()` inside `_save` after
  setting `pdf_gcs_url`.
- The `elif resolved.source_kind not in ("text", "doc_id"):` warning block is removed; the new
  logic has no concept of `input_pdf_gcs` at the route level.

### 4.3 `backend/utils/firebase.py` — drop `input_pdf_gcs` parameter

Current signature (lines 101–110):

```python
def save_care_plan_output(
    *,
    user_id: str,
    name: str,
    source_filename: str,
    input_pdf_gcs: str | None,     # <-- remove
    output_data: dict,
    dataset_group: str | None = None,
    batch_group_id: str | None = None,
) -> str:
```

New signature (remove the parameter and the payload line that writes it):

```python
def save_care_plan_output(
    *,
    user_id: str,
    name: str,
    source_filename: str,
    output_data: dict,
    dataset_group: str | None = None,
    batch_group_id: str | None = None,
) -> str:
```

The payload dictionary inside this function currently includes:

```python
"input_pdf_gcs": input_pdf_gcs or "",   # line 123 — REMOVE
```

Remove that line entirely. The URL now lives inside `output_data["input"]["pdf_gcs_url"]` (the
serialized `FileInput`). No other change to `firebase.py`.

### 4.4 `backend/routes/batch.py` — remove `input_pdf_gcs=None` kwarg

The batch route calls `save_care_plan_output` at approximately line 251 with `input_pdf_gcs=None`.
After 4.3, this kwarg no longer exists; simply remove it:

```python
# BEFORE
saved_id = save_care_plan_output(
    user_id=user_id,
    name=_output_name(result_data, group, input_id),
    source_filename=source_filename,
    input_pdf_gcs=None,           # <-- remove
    output_data=result_data,
    dataset_group=group,
    batch_group_id=batch_group_id,
)

# AFTER
saved_id = save_care_plan_output(
    user_id=user_id,
    name=_output_name(result_data, group, input_id),
    source_filename=source_filename,
    output_data=result_data,
    dataset_group=group,
    batch_group_id=batch_group_id,
)
```

No other change to `batch.py`.

### 4.5 `backend/routes/saved_outputs.py` — tolerant read in `get_input_pdf_url`

Current read (line 136):

```python
gcs_uri = data.get('input_pdf_gcs', '')
```

New read — try the new location first, fall back to the legacy top-level field for documents saved
before SP-11:

```python
# Try new envelope location first (SP-11+); fall back to legacy top-level field for old docs.
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)
```

The rest of the function (bucket validation, blob extraction, signed URL generation) is unchanged.
The fallback means old documents continue to work without any migration.

### 4.6 `frontend/src/types/envelope.ts` — discriminated Input union with `pdf_gcs_url`

Replace the current flat `Input` interface with the discriminated union that mirrors SP-08:

```typescript
// BEFORE
export interface InputFile {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface Input {
  mode: string;  // "file" | "text" | "doc_id"
  text: string | null;
  doc_id: string | null;
  files: InputFile[];
}
```

```typescript
// AFTER
export interface InputFile {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface FileInput {
  mode: 'file';
  files: InputFile[];
  pdf_gcs_url: string | null;   // populated by SP-11; null for old saved docs
}

export interface TextInput {
  mode: 'text';
  text: string;
  // batch-dataset inputs also use mode="text" with optional dataset_group etc.
  dataset_group?: string | null;
  dataset_input?: string | null;
  selected_files?: string[] | null;
  batch_group_id?: string | null;
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

`CarePlanInternal.input` changes from `Input` (old flat) to the new `Input` union. All callers that
read `input.text`, `input.files`, or `input.mode` must narrow with a type guard or discriminant
check.

SP-08 confirms `BatchDatasetInput` is a fourth distinct variant with `mode: "batch_dataset"`.
The FE `Input` union includes all four variants to match the backend wire exactly.

### 4.7 `frontend/src/pages/care-plan/CarePlanPage.tsx` — update show-original conditions

**`outputHasInputPdf` (line 51–55) — replace heuristic with authoritative check:**

```typescript
// BEFORE
function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.files.some(file => (
    file.content_type === 'application/pdf' || file.filename.toLowerCase().endsWith('.pdf')
  ));
}
```

```typescript
// AFTER
function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.pdf_gcs_url != null;
}
```

**Add a helper for text/batch inputs:**

```typescript
function outputHasInputText(output: CarePlanInternal): boolean {
  return (output.input.mode === 'text' || output.input.mode === 'batch_dataset')
    && typeof output.input.text === 'string'
    && output.input.text.length > 0;
}
```

**Update the "Show Original" button rendering (lines 518–530):**

Replace the single condition block with two cases:

```tsx
{/* Case A: file input with PDF — fetch signed URL → iframe via SplitView */}
{activeSavedId && result && outputHasInputPdf(result) && (
  <button onClick={() => setShowSplitView(true)} ...>
    Show Original
  </button>
)}

{/* Case B: text/batch input — inline text via SplitView (no API call) */}
{activeSavedId && result && outputHasInputText(result) && (
  <button onClick={() => setShowSplitView(true)} ...>
    Show Original
  </button>
)}
```

Or, equivalently, combine into one condition:

```tsx
{activeSavedId && result && (outputHasInputPdf(result) || outputHasInputText(result)) && (
  <button onClick={() => setShowSplitView(true)} ...>Show Original</button>
)}
```

**Pass the display data downward.** A new prop — `originalContent` — is added to `SplitView`
(see §4.8). At the `SplitView` render site (line 623–628), derive it before rendering:

```tsx
{showSplitView && result && activeSavedId && (
  <SplitView
    savedId={result.input.mode === 'file' ? activeSavedId : null}
    originalText={result.input.mode === 'text' ? result.input.text : null}
    simplifiedContent={<CarePlanView result={result.care_plan} grading={result.grading} />}
    onClose={() => setShowSplitView(false)}
  />
)}
```

`savedId` is now `string | null`; when null, `SplitView` skips the API call and uses
`originalText` instead. When both are null (should not happen in practice), `SplitView` shows an
error state.

### 4.8 `frontend/src/components/SplitView.tsx` — accept text OR signed URL

Current props:

```typescript
interface SplitViewProps {
  savedId: string;
  simplifiedContent: React.ReactNode;
  onClose: () => void;
}
```

New props:

```typescript
interface SplitViewProps {
  savedId: string | null;          // non-null → fetch signed URL for PDF iframe
  originalText: string | null;     // non-null → render inline text (no API call)
  simplifiedContent: React.ReactNode;
  onClose: () => void;
}
```

Invariant: exactly one of `savedId` or `originalText` is non-null at render time. (Both null is a
bug; both non-null is ambiguous — `savedId` takes priority.)

Updated component logic:

```tsx
export default function SplitView({ savedId, originalText, simplifiedContent, onClose }: SplitViewProps) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [loading, setLoading] = useState(savedId != null);  // only load if PDF mode

  useEffect(() => {
    if (!savedId) return;   // text mode: nothing to fetch
    setLoading(true);
    getInputPdfUrl(savedId)
      .then(url => { setPdfUrl(url); setLoading(false); })
      .catch(e => { setPdfError((e as Error).message); setLoading(false); });
  }, [savedId]);

  const panelTitle = savedId ? 'Original Document' : 'Original Text';

  return (
    <div className="split-view-overlay">
      <div className="split-view-toolbar">
        <span className="split-view-title">Compare: Original vs Care Plan</span>
        <button className="split-view-close" onClick={onClose}>✕ Close</button>
      </div>
      <div className="split-view-panels">
        <div className="split-view-panel">
          <div className="split-view-panel-header">{panelTitle}</div>

          {/* PDF mode */}
          {savedId && loading && <div className="split-view-loading">Loading PDF...</div>}
          {savedId && pdfError && (
            <div className="split-view-loading" style={{ color: '#DC2626' }}>
              Could not load PDF: {pdfError}
            </div>
          )}
          {savedId && pdfUrl && !loading && (
            <iframe src={pdfUrl} title="Original document" />
          )}

          {/* Text mode */}
          {!savedId && originalText && (
            <div className="split-view-text-content">
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {originalText}
              </pre>
            </div>
          )}

          {/* Error: neither mode available */}
          {!savedId && !originalText && (
            <div className="split-view-loading" style={{ color: '#DC2626' }}>
              No original content available.
            </div>
          )}
        </div>

        <div className="split-view-panel">
          <div className="split-view-panel-header">Care Plan</div>
          <div className="split-view-simplified">{simplifiedContent}</div>
        </div>
      </div>
    </div>
  );
}
```

The `split-view-text-content` CSS class needs to be added to `SplitView.css` with appropriate
`overflow-y: auto` and `padding` so the text panel scrolls independently, matching the iframe panel
behavior.

### 4.9 `frontend/src/api/savedOutputs.ts` — minor type cleanup

`SavedOutput` currently declares `input_pdf_gcs: string` as a top-level field (line 15). Remove it:

```typescript
// BEFORE
export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
  input_pdf_gcs: string;        // <-- remove
}

// AFTER
export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
}
```

`getInputPdfUrl` is unchanged in implementation; it is now only called by `SplitView` when
`savedId` is non-null (file input mode). The function signature stays the same.

## 5. API Change Summary

| Endpoint | Change |
|---|---|
| `GET /care_plan/saved/{id}/input-pdf-url` | Reads `output_data.input.pdf_gcs_url` first; falls back to top-level `input_pdf_gcs` for legacy docs. Behavior is identical from the caller's perspective. |
| All other endpoints | Unchanged. |

**Firestore document shape** — new vs. old for file input documents:

```jsonc
// BEFORE SP-11 (Firestore document root)
{
  "uid": "...",
  "input_pdf_gcs": "gs://bucket/care_plan/uid/inputs/uuid.pdf",   // top-level
  "output_data": {
    "input": { "mode": "file", "files": [...], "pdf_gcs_url": null },
    ...
  }
}

// AFTER SP-11 (Firestore document root)
{
  "uid": "...",
  // input_pdf_gcs field absent entirely
  "output_data": {
    "input": { "mode": "file", "files": [...], "pdf_gcs_url": "gs://bucket/.../uuid.pdf" },
    ...
  }
}
```

For text and batch-dataset documents, `pdf_gcs_url` was always absent and remains absent. The
`input_pdf_gcs` field is also absent from their Firestore roots after SP-11 (it was written as `""`
before; now the field is not written at all).

## 6. Frontend Change Summary

| File | Change |
|---|---|
| `frontend/src/types/envelope.ts` | `Input` becomes a discriminated union: `FileInput \| TextInput \| DocIdInput`. `FileInput` carries `pdf_gcs_url: string \| null`. |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | `outputHasInputPdf` reads `pdf_gcs_url != null`. New `outputHasInputText` helper. "Show Original" button and `SplitView` render site updated to pass `savedId`/`originalText` props. |
| `frontend/src/components/SplitView.tsx` | Props widened: `savedId: string \| null`, `originalText: string \| null`. Component conditionally fetches signed URL (PDF mode) or renders `<pre>` (text mode). `getInputPdfUrl` call moved inside the conditional effect. |
| `frontend/src/api/savedOutputs.ts` | `SavedOutput.input_pdf_gcs` field removed. `getInputPdfUrl` is unchanged. |
| `frontend/src/components/SplitView.css` | Add `.split-view-text-content` with `overflow-y: auto`, `padding`, `height: 100%`, matching panel scroll behavior. |

**No change** to `OutputGradingCard.tsx`, `CarePlanView.tsx`, or any other consumer of the result.

## 7. Testing

### Backend

- **`test_firebase.py`** — `save_care_plan_output` no longer accepts `input_pdf_gcs`:
  - Calling it with `input_pdf_gcs=...` raises `TypeError` (kwarg removed).
  - The saved Firestore document does **not** contain an `input_pdf_gcs` key.
  - `output_data` is persisted verbatim (including `input.pdf_gcs_url`).

- **`test_saved_outputs.py`** — `get_input_pdf_url` tolerant read:
  - Document with only `output_data.input.pdf_gcs_url` set → uses new path.
  - Document with only top-level `input_pdf_gcs` set (legacy) → uses fallback.
  - Document with both set → uses new path (new takes priority).
  - Document with neither set → returns 404 with `"No input PDF stored"` error.

- **`test_care_plan_route.py`** — save block:
  - After a successful file upload, the saved `output_data.input.pdf_gcs_url` equals the GCS URI
    returned by `upload_combined_pdf`.
  - No `input_pdf_gcs` key at the Firestore document root.

- **`test_batch_route.py`** — `save_care_plan_output` called without `input_pdf_gcs` kwarg.

### Frontend

- **`SplitView.test.tsx`**:
  - With `savedId` non-null and `originalText` null: calls `getInputPdfUrl`, renders iframe on
    success, renders error text on failure.
  - With `savedId` null and `originalText` non-null: does **not** call `getInputPdfUrl`, renders
    `<pre>` with text content.
  - With both null: renders "No original content available" error state.

- **`CarePlanPage.test.tsx`** (or Vitest equivalent):
  - `outputHasInputPdf`: returns `true` when `input.mode === 'file'` and `pdf_gcs_url` is a
    non-null string; returns `false` when `pdf_gcs_url` is `null`; returns `false` for text mode.
  - `outputHasInputText`: returns `true` when `input.mode === 'text'` and `text` is a non-empty
    string; returns `false` for file mode.
  - Button renders when `outputHasInputPdf` or `outputHasInputText` is true and `activeSavedId` is
    set.
  - Button does not render when both helpers return false.

- **`envelope.ts` types**: TypeScript compilation verifies discriminated union narrowing — accessing
  `input.pdf_gcs_url` is a type error unless `input.mode === 'file'` is asserted first.

## 8. Manual Intervention Required From You

1. **`input_pdf_gcs` removal — CONFIRMED SAFE.** No other system reads this field directly.
   Removal is approved; the tolerant fallback read in `saved_outputs.py` covers existing docs.

2. **Timing relative to SP-08 — CONFIRMED.** SP-11 lands after SP-08. Task ordering in TASKS.md
   must reflect this; implementer to ensure SP-08 tasks are marked complete before SP-11 begins.

3. **`SplitView.css` addition — APPROVED.** Use suggested styles (`height: 100%; overflow-y: auto;
   padding: 16px; font-size: 0.875rem; line-height: 1.6;`) as the default.

## 9. Open Questions & Decisions

1. **`doc_id` input mode in Show Original.**
   `[DEFERRED]` — `DocIdInput.doc_id` references a GCS-stored document. Showing the original would
   require the signed URL endpoint to look up and serve that stored file (different from the
   combined-PDF flow). This mode is rarely used in practice and the lookup logic is non-trivial
   (the doc path convention for stored docs differs from the upload convention). Deferred to a later
   sub-project. For now, the "Show Original" button does not appear for `doc_id` inputs
   (`outputHasInputPdf` and `outputHasInputText` both return false for that mode).

2. **`batch_dataset` as a distinct mode vs. `TextInput` with extra fields.**
   `[RESOLVED: SP-08 introduces `mode: "batch_dataset"` as its own discriminant via `BatchDatasetInput`. The FE union must include `BatchDatasetInput` as a fourth variant alongside `FileInput`, `TextInput`, and `DocIdInput`. `outputHasInputText` in SP-11 must check BOTH `mode === 'text'` AND `mode === 'batch_dataset'` to show "Show Original" for both plain-text and batch-dataset inputs. The `Input` type alias in `envelope.ts` becomes `FileInput | TextInput | DocIdInput | BatchDatasetInput`.]`

3. **Re-serialization timing in `care_plan.py` save block.**
   `[RESOLVED: Defer `envelope.to_dict()` into the `_save` closure. Move the `payload = envelope.to_dict()` call to inside `_save`, after setting `input_model.pdf_gcs_url = gcs_uri`. This produces the full payload (including `pdf_gcs_url`) atomically with the save. The SSE result event must also use this deferred payload — verify that the `yield _sse({"step": "result", "data": payload})` at the end of the route references the same payload object produced inside `_save`.]`

4. **SplitView CSS panel height for text mode.**
   `[RESOLVED: Use the styles suggested in §4.8: `height: 100%; overflow-y: auto; padding: 16px; font-size: 0.875rem; line-height: 1.6;` for `.split-view-text-content`. This mirrors the iframe panel's scroll behavior. Will be reviewed after first deploy.]`

5. **`SavedOutput.input_pdf_gcs` type in `savedOutputs.ts` for legacy reads.**
   `[RESOLVED: REMOVE IT]` — The FE `SavedOutput` interface had `input_pdf_gcs: string` as a
   top-level field (line 15 of `savedOutputs.ts`). This field is removed from the interface because:
   (a) it will not be written by new saves, (b) the FE does not read it directly — the backend
   endpoint abstracts it away. The FE reads `output_data.input.pdf_gcs_url` only via the typed
   `CarePlanInternal.input` shape, not by reaching into `SavedOutput.output_data` directly.

6. **SSE result payload includes updated `pdf_gcs_url` — does the live session show "Show Original"?**
   `[RESOLVED: YES, it should]` — When a user generates a new care plan from a file upload in the
   live session, the SSE result payload (`step: "result"`) contains the full envelope including
   `input.pdf_gcs_url` (populated by the route before yielding the result SSE). So `result.input.pdf_gcs_url`
   is non-null immediately after generation, and `activeSavedId` is set as soon as the save
   completes. The "Show Original" button should therefore appear for file-upload care plans in the
   same session, without requiring a page reload. The dev should verify that the
   `payload["metrics"]["saved_id"]` mutation (line 585 of `care_plan.py`) and the `pdf_gcs_url`
   mutation both happen before the final `yield _sse({"step": "result", "data": payload})`.
