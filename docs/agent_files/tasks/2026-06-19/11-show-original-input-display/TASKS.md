# Tasks: Show Original & Input Display Redesign (SP-11)

**Prerequisites — do NOT start SP-11 until both are merged:**

- **SP-08** must be merged first. SP-11 relies on `FileInput.pdf_gcs_url: str | None = None`
  existing on the `FileInput` model in `backend/models/input.py`, and on the four-variant
  discriminated union (`FileInput | TextInput | DocIdInput | BatchDatasetInput`) already being
  in place in both the backend and `frontend/src/types/envelope.ts`.
- **SP-13** (Frontend Code Organization) must be merged first if it moves
  `frontend/src/components/SplitView.tsx` → `frontend/src/components/SplitView/SplitView.tsx`.
  All SP-11 file paths below assume SP-13 has landed; if SP-13 has not yet moved SplitView,
  work on the file at its current location (`frontend/src/components/SplitView.tsx`) and note
  that SP-13 will move it afterward.

---

### Task 1 — Drop `input_pdf_gcs` from `firebase.py` `save_care_plan_output`

**Files:** `backend/utils/firebase.py`

**Changes:**

In `save_care_plan_output` (line 101), remove the `input_pdf_gcs` parameter and the line that
writes it to the Firestore payload.

Before (lines 101–123):
```python
def save_care_plan_output(
    *,
    user_id: str,
    name: str,
    source_filename: str,
    input_pdf_gcs: str | None,     # REMOVE this line
    output_data: dict,
    dataset_group: str | None = None,
    batch_group_id: str | None = None,
) -> str:
    ...
    payload = {
        ...
        "input_pdf_gcs": input_pdf_gcs or "",   # REMOVE this line
        "output_data": output_data,
    }
```

After:
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
    ...
    payload = {
        ...
        # "input_pdf_gcs" line removed entirely — URL now lives in output_data["input"]["pdf_gcs_url"]
        "output_data": output_data,
    }
```

No other change to `firebase.py`.

**Acceptance criteria:**
- `save_care_plan_output` no longer has an `input_pdf_gcs` parameter.
- Calling it with `input_pdf_gcs=None` raises `TypeError: unexpected keyword argument`.
- The Firestore payload dict written by the function does not contain an `"input_pdf_gcs"` key.
- All existing unit tests for `save_care_plan_output` (in `backend/tests/utils/test_firebase.py`)
  pass after removing the kwarg from test call sites.

---

### Task 2 — Remove `input_pdf_gcs=None` from `batch.py`

**Files:** `backend/routes/batch.py`

**Changes:**

At line 255, remove the `input_pdf_gcs=None` keyword argument from the `save_care_plan_output`
call (this kwarg no longer exists after Task 1).

Before (lines 251–259):
```python
saved_id = save_care_plan_output(
    user_id=user_id,
    name=_output_name(result_data, group, input_id),
    source_filename=source_filename,
    input_pdf_gcs=None,           # REMOVE
    output_data=result_data,
    dataset_group=group,
    batch_group_id=batch_group_id,
)
```

After:
```python
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

**Acceptance criteria:**
- `batch.py` contains no reference to `input_pdf_gcs`.
- The batch route integration test passes (batch saves complete without `TypeError`).

---

### Task 3 — Populate `pdf_gcs_url` in `care_plan.py` save block; remove `input_pdf_gcs` kwarg

**Files:** `backend/routes/care_plan.py`

**Changes:**

The current save block (lines 560–591) does the following in order:
1. Calls `payload = envelope.to_dict()` at line 560 (before `_save`).
2. Inside `_save`, uploads the PDF and sets `input_pdf_gcs` local variable.
3. Passes `input_pdf_gcs=input_pdf_gcs` to `save_care_plan_output`.

This must be restructured so:
1. `payload = envelope.to_dict()` is moved **inside** `_save`, called **after** setting
   `input_model.pdf_gcs_url = gcs_uri`.
2. The `input_pdf_gcs` local variable and the `input_pdf_gcs=...` kwarg are removed.
3. `payload` is still referenced by the final `yield _sse({"step": "result", "data": payload})`
   at line 593 — after restructuring, `payload` must be assigned in an outer scope that is visible
   to the `yield`. Use a one-element list `[None]` or a `nonlocal` binding to propagate it out of
   the nested `_save` function, or use a mutable dict. The simplest pattern:

```python
# Outside _save — initialize payload holder
_payload_holder: list[dict] = []

if resolved.source_kind != "doc_id":
    def _save(scope):
        JunoContext.from_g(function="save_output").apply(scope)
        try:
            if resolved.combined_pdf_bytes:
                gcs_uri = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
                input_model.pdf_gcs_url = gcs_uri   # FileInput only; safe because combined_pdf_bytes is non-None only for file inputs

            # Serialize AFTER mutating input_model so pdf_gcs_url is included
            payload = envelope.to_dict()
            _payload_holder.append(payload)

            care_plan_data = payload.get("care_plan", {})
            saved_id = save_care_plan_output(
                user_id=user_id,
                name=_derive_output_name(care_plan_data, resolved),
                source_filename=resolved.source_filename,
                output_data=payload,              # no input_pdf_gcs kwarg
            )
            metrics.saved_id = saved_id
            payload["metrics"]["saved_id"] = metrics.saved_id
            scope.add("saved_id", saved_id)
        except Exception as exc:
            logger.exception("care_plan: failed to save output - continuing without saved_id")
            _juno_error_logger.error("care_plan: failed to save output - continuing without saved_id: %s", exc)
            scope.mark_failed()
    Markers.CarePlan.SaveOutput.execute(_save)
else:
    # doc_id path: serialize normally (no PDF upload, no save)
    _payload_holder.append(envelope.to_dict())

payload = _payload_holder[0] if _payload_holder else envelope.to_dict()
yield _sse({"step": "result", "data": payload})
```

Also remove the now-unnecessary `elif resolved.source_kind not in ("text", "doc_id"):` warning
block (lines 569–574) that logged about missing `combined_pdf_bytes`.

**Acceptance criteria:**
- For a file-upload care plan run, `output_data["input"]["pdf_gcs_url"]` in the saved Firestore
  document equals the `gs://` URI returned by `upload_combined_pdf`.
- The Firestore document root does not contain an `"input_pdf_gcs"` key.
- The SSE `result` event payload also contains `input.pdf_gcs_url` (non-null for file inputs).
- `care_plan.py` contains no reference to `input_pdf_gcs`.
- For text/batch-dataset inputs (no PDF upload), `output_data["input"]["pdf_gcs_url"]` is absent
  (those variants have no such field).

---

### Task 4 — Tolerant read in `saved_outputs.py` `get_input_pdf_url` (and `delete_saved`)

**Files:** `backend/routes/saved_outputs.py`

**Changes:**

Two places read `input_pdf_gcs` from the Firestore document:

**A. `get_input_pdf_url` (line 136):**

Before:
```python
gcs_uri = data.get('input_pdf_gcs', '')
```

After (try new envelope location first; fall back to legacy top-level field):
```python
# Try new envelope location first (SP-11+); fall back to legacy top-level field for old docs.
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)
```

**B. `delete_saved` (line 110):** This reads `input_pdf_gcs` to delete the GCS file when a
document is deleted. Apply the same tolerant read here so old documents still have their GCS
files cleaned up:

Before:
```python
gcs_uri = data.get('input_pdf_gcs', '')
```

After:
```python
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)
```

**C. `get_saved` (line 74):** This returns `input_pdf_gcs` in the JSON response body. This
field is being removed from the FE `SavedOutput` interface (Task 6). Remove it from the
response dict:

Before:
```python
return jsonify({
    'id': doc.id,
    ...
    'input_pdf_gcs': data.get('input_pdf_gcs', ''),
})
```

After:
```python
return jsonify({
    'id': doc.id,
    ...
    # 'input_pdf_gcs' removed — URL now lives in output_data.input.pdf_gcs_url
})
```

**Acceptance criteria:**
- `GET /care_plan/saved/<id>/input-pdf-url` returns a signed URL for a **new** document (URL
  read from `output_data.input.pdf_gcs_url`).
- Same endpoint returns a signed URL for a **legacy** document that only has the top-level
  `input_pdf_gcs` field (fallback path).
- Deleting a new document triggers GCS file deletion (tolerant read finds the URI).
- `GET /care_plan/saved/<id>` response body no longer includes `"input_pdf_gcs"` key.

---

### Task 5 — Update `frontend/src/types/envelope.ts` with four-variant discriminated union

**Files:** `frontend/src/types/envelope.ts`

**Context:** SP-08 already defines the four-variant discriminated union in `envelope.ts`. If SP-08
has been merged, `envelope.ts` already has `FileInput`, `TextInput`, `DocIdInput`,
`BatchDatasetInput` defined. In that case, this task is just a verification + the addition of
`BatchDatasetInput` to the union if it was omitted.

**Changes (if SP-08 has NOT yet touched this file — apply the full replacement):**

Replace the current flat `Input` interface (lines 12–17) with:

```typescript
export interface FileInput {
  mode: 'file';
  files: InputFile[];
  pdf_gcs_url: string | null;   // populated by SP-11 for new docs; null for legacy docs
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

The `InputFile` interface (lines 6–10) is unchanged.

**Verify SP-08 match:** The TypeScript `BatchDatasetInput.mode` must be `'batch_dataset'` (not
`'text'`) — this mirrors SP-08's backend `BatchDatasetInput.mode: Literal["batch_dataset"]`.

**Acceptance criteria:**
- `npx tsc --noEmit` from `frontend/` passes with no errors after this change.
- Accessing `input.pdf_gcs_url` without first narrowing on `input.mode === 'file'` is a
  TypeScript type error.
- Accessing `input.text` without narrowing on `mode === 'text'` or `mode === 'batch_dataset'`
  is a TypeScript type error.

---

### Task 6 — Remove `input_pdf_gcs` from `SavedOutput` in `savedOutputs.ts`

**Files:** `frontend/src/api/savedOutputs.ts`

**Changes:**

Remove the `input_pdf_gcs: string` field from the `SavedOutput` interface (line 15):

Before:
```typescript
export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
  input_pdf_gcs: string;        // REMOVE
}
```

After:
```typescript
export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
}
```

`getInputPdfUrl` (line 47) is unchanged — it still calls the signed URL endpoint; its
implementation is not affected.

**Acceptance criteria:**
- `npx tsc --noEmit` passes.
- No TypeScript code in `frontend/src/` references `savedOutput.input_pdf_gcs` or
  `output.input_pdf_gcs` (run `grep -r 'input_pdf_gcs' frontend/src/` — must return nothing).

---

### Task 7 — Update `outputHasInputPdf`, add `outputHasInputText`, update `SplitView` render in `CarePlanPage.tsx`

**Files:** `frontend/src/pages/care-plan/CarePlanPage.tsx`

**Changes:**

**A. Replace `outputHasInputPdf` (lines 51–55):**

Before:
```typescript
function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.files.some(file => (
    file.content_type === 'application/pdf' || file.filename.toLowerCase().endsWith('.pdf')
  ));
}
```

After:
```typescript
function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.pdf_gcs_url != null;
}
```

**B. Add `outputHasInputText` immediately after `outputHasInputPdf`:**

```typescript
function outputHasInputText(output: CarePlanInternal): boolean {
  return (output.input.mode === 'text' || output.input.mode === 'batch_dataset')
    && typeof output.input.text === 'string'
    && output.input.text.length > 0;
}
```

**C. Update "Show Original" button condition (line 518):**

Before:
```tsx
{activeSavedId && result && outputHasInputPdf(result) && (
  <button onClick={() => setShowSplitView(true)} ...>
    Show Original
  </button>
)}
```

After (combine both cases into one condition):
```tsx
{activeSavedId && result && (outputHasInputPdf(result) || outputHasInputText(result)) && (
  <button
    onClick={() => setShowSplitView(true)}
    style={{
      background: 'none', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-pill)', padding: '6px 14px',
      fontSize: '0.8rem', cursor: 'pointer',
      color: 'var(--text-secondary)', fontFamily: 'Inter, sans-serif',
    }}
  >
    Show Original
  </button>
)}
```

**D. Update the `SplitView` render site (lines 623–629):**

Before:
```tsx
{showSplitView && result && activeSavedId && (
  <SplitView
    savedId={activeSavedId}
    simplifiedContent={<CarePlanView result={result.care_plan} grading={result.grading} />}
    onClose={() => setShowSplitView(false)}
  />
)}
```

After:
```tsx
{showSplitView && result && (
  <SplitView
    savedId={result.input.mode === 'file' ? activeSavedId : null}
    originalText={
      (result.input.mode === 'text' || result.input.mode === 'batch_dataset')
        ? result.input.text ?? null
        : null
    }
    simplifiedContent={<CarePlanView result={result.care_plan} grading={result.grading} />}
    onClose={() => setShowSplitView(false)}
  />
)}
```

Note: the outer `activeSavedId &&` guard is removed from the `SplitView` render condition because
text-mode "Show Original" does not require a saved ID. `SplitView` itself handles the case where
both props are null (error state — see Task 8).

**Acceptance criteria:**
- `npx tsc --noEmit` passes.
- For a file input with `pdf_gcs_url != null`, "Show Original" button appears and opens `SplitView`
  with `savedId` set (PDF mode).
- For a file input with `pdf_gcs_url == null` (legacy doc without URL), button does NOT appear.
- For a text input with non-empty `text`, button appears and opens `SplitView` with `originalText`
  set (text mode).
- For a `batch_dataset` input with non-empty `text`, button appears and opens `SplitView` with
  `originalText` set.
- For a `doc_id` input, button does NOT appear.

---

### Task 8 — Rework `SplitView.tsx` to accept `savedId | null` and `originalText | null`

**Files:** `frontend/src/components/SplitView.tsx` (or `SplitView/SplitView.tsx` if SP-13 has moved it)

**Changes:**

Replace the entire component with the updated implementation that handles both PDF (signed URL)
and text (inline) modes:

```tsx
import { useEffect, useState } from 'react';
import './SplitView.css';
import { getInputPdfUrl } from '../api/savedOutputs';

interface SplitViewProps {
  savedId: string | null;          // non-null → fetch signed URL for PDF iframe
  originalText: string | null;     // non-null → render inline text (no API call)
  simplifiedContent: React.ReactNode;
  onClose: () => void;
}

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

If SP-13 has moved SplitView to a subfolder, update the import paths for `SplitView.css` and
`getInputPdfUrl` accordingly.

**Acceptance criteria:**
- `npx tsc --noEmit` passes.
- Rendered with `savedId="abc"` and `originalText=null`: calls `getInputPdfUrl("abc")`, shows
  iframe on success, shows error text on failure, does NOT render `<pre>`.
- Rendered with `savedId=null` and `originalText="Patient note..."`: does NOT call
  `getInputPdfUrl`, renders a `<pre>` containing the text, panel header says "Original Text".
- Rendered with both null: shows "No original content available." error in red.
- Panel header says "Original Document" for PDF mode, "Original Text" for text mode.

---

### Task 9 — Add `.split-view-text-content` to `SplitView.css`

**Files:** `frontend/src/components/SplitView.css` (or `SplitView/SplitView.css` if SP-13 has moved it)

**Changes:**

Append the new CSS class at the end of the file:

```css
.split-view-text-content {
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  font-size: 0.875rem;
  line-height: 1.6;
}

.split-view-text-content pre {
  margin: 0;
  font-family: inherit;
  color: var(--text-primary);
}
```

The `height: 100%` and `overflow-y: auto` mirror the scroll behavior of the iframe panel (the
`.split-view-panel` already has `overflow-y: auto`; the inner `.split-view-text-content` needs
`height: 100%` so it fills the panel and `overflow-y: auto` ensures independent scroll if the
panel height is constrained).

**Acceptance criteria:**
- The text panel scrolls independently when the original text is long enough to overflow.
- Font size and line height are consistent with the care plan panel's body text.
- No visual regression on the PDF (iframe) panel — existing CSS classes are unchanged.

---

### Task 10 — Backend tests for SP-11 changes

**Files:**
- `backend/tests/utils/test_firebase.py`
- `backend/tests/routes/test_saved_outputs_route.py`
- `backend/tests/routes/test_care_plan_route.py` (add / update the save block test)
- `backend/tests/routes/test_batch_route.py`

**Changes:**

**`test_firebase.py` — update `save_care_plan_output` call sites:**

- Remove `input_pdf_gcs` from all `save_care_plan_output` calls in the test file.
- Add test: calling `save_care_plan_output` with `input_pdf_gcs=None` raises `TypeError`.
- Add test: the Firestore payload written by a successful call does NOT contain `"input_pdf_gcs"`.
- Add test: `output_data` is persisted verbatim in the payload (including any nested
  `"input": {"pdf_gcs_url": "gs://..."}` value).

**`test_saved_outputs_route.py` — tolerant read tests for `get_input_pdf_url`:**

Add four test cases (mock `firestore_client` and the GCS signed-URL call):
1. Document with only `output_data.input.pdf_gcs_url` set → endpoint uses new path; returns URL.
2. Document with only top-level `input_pdf_gcs` set (legacy) → endpoint uses fallback; returns URL.
3. Document with both set → new path takes priority.
4. Document with neither set → returns 404 with `"No input PDF stored"` in error body.

**`test_care_plan_route.py` — save block test:**

Add or update the SSE happy-path test:
- After a simulated file-upload run where `upload_combined_pdf` returns a mock URI, assert that
  the saved Firestore doc's `output_data["input"]["pdf_gcs_url"]` equals the mock URI.
- Assert the Firestore doc root does NOT contain `"input_pdf_gcs"`.
- Assert the SSE `result` event payload also contains `input.pdf_gcs_url` equal to the mock URI.

**`test_batch_route.py`:**

- Verify `save_care_plan_output` is called without `input_pdf_gcs` kwarg (no `TypeError` raised
  on the batch save path).

**Acceptance criteria:**
- All backend tests pass: `cd backend && python -m pytest tests/ -q`.
- The four `get_input_pdf_url` tolerant-read cases are tested and pass.
- No reference to `input_pdf_gcs` remains in test call sites to `save_care_plan_output`.

---

### Task 11 — Frontend tests for SP-11 changes

**Files:**
- `frontend/src/components/SplitView.test.tsx` (NEW)
- `frontend/src/pages/care-plan/CarePlanPage.test.tsx` (NEW or update if exists)

**Changes:**

**`SplitView.test.tsx`** — create with three test cases using Vitest + RTL:

```tsx
// mock getInputPdfUrl
vi.mock('../api/savedOutputs', () => ({
  getInputPdfUrl: vi.fn(),
}));

test('PDF mode: calls getInputPdfUrl, renders iframe on success', async () => { ... });
test('PDF mode: shows error text when getInputPdfUrl rejects', async () => { ... });
test('Text mode: does NOT call getInputPdfUrl; renders <pre> with text', async () => { ... });
test('Both null: renders "No original content available." error', async () => { ... });
```

Key assertions:
- PDF mode success: `getInputPdfUrl` called with `savedId`; `<iframe>` in DOM; no `<pre>`.
- PDF mode error: error text visible; no `<iframe>`.
- Text mode: `getInputPdfUrl` NOT called; `<pre>` contains the `originalText` string; panel header
  reads "Original Text".
- Both null: error text "No original content available." visible.

**`CarePlanPage.test.tsx`** — add unit tests for the two helpers (can be imported if extracted,
or tested via inline logic):

```typescript
// helpers can be tested via rendering CarePlanPage with mock props,
// or extracted to a separate util file and tested directly.

test('outputHasInputPdf: true when mode=file and pdf_gcs_url is non-null', ...);
test('outputHasInputPdf: false when mode=file and pdf_gcs_url is null', ...);
test('outputHasInputPdf: false for text mode', ...);
test('outputHasInputText: true when mode=text and text is non-empty', ...);
test('outputHasInputText: true when mode=batch_dataset and text is non-empty', ...);
test('outputHasInputText: false for file mode', ...);
test('outputHasInputText: false when text is empty string', ...);
```

**Acceptance criteria:**
- `cd frontend && npm run test` passes with all new test cases green.
- `SplitView.test.tsx` covers all four render modes.
- `CarePlanPage.test.tsx` covers both helpers with all described cases.

---

## Summary of what requires you (not a dev agent)

1. **Merge order.** Confirm SP-08 and SP-13 are merged before cutting the SP-11 branch. The dev
   agent must not begin Task 5 (envelope.ts) until SP-08's four-variant union is already in place.

2. **SSE timing verification.** After Task 3 is implemented, manually test a file-upload care plan
   run in the browser: generate a care plan from a PDF, then click "Show Original" in the same
   session (without reloading). Confirm the button appears immediately after generation (not just
   after a page reload), which would verify that the deferred `envelope.to_dict()` call inside
   `_save` produces `pdf_gcs_url` in the SSE result payload.

3. **Visual review of `.split-view-text-content`.** After Task 9 is deployed, open "Show Original"
   for a text input and confirm the text panel scrolls independently, the font size reads well, and
   the two panels are visually balanced. The CSS is approved as a starting point (§8 item 3
   APPROVED) but will be reviewed after first deploy.
