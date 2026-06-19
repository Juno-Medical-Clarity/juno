# Task 03: Fix "Show Original" 404 Error + Split-Screen on Same Page

**Date:** 2026-06-15
**Effort estimate:** 2–4 hours
**Status:** Ready to implement

---

## Goal

Two things need to be fixed:

1. **Bug:** Clicking "Show Original" shows the error `Could not load PDF: Failed to get PDF URL: 404 Error` instead of the original PDF. Fix the root cause so the PDF URL is correctly generated.
2. **UX (already done — verify):** The split-screen view should appear on the same page (not a new window/tab). This is already implemented via `SplitView.tsx` and wired up in `V1_2Page.tsx`. Your job is to confirm it works correctly once the 404 is fixed.

---

## Current Error

When a user clicks "Show Original" on a result:

```
Could not load PDF: Failed to get PDF URL: 404 Error
```

This message is produced in `/root/projects/juno/frontend/src/components/SplitView.tsx` at line 20:

```tsx
.catch(e => { setPdfError(e.message); setLoading(false); });
```

And the error message `"Failed to get PDF URL: 404 Error"` is thrown in `/root/projects/juno/frontend/src/api/savedOutputs.ts` at line 48:

```ts
if (!res.ok) throw new Error(`Failed to get PDF URL: ${res.status}`);
```

---

## Root Cause Analysis

### The full call chain

1. User clicks "Show Original" button (`V1_2Page.tsx`, line 333).
2. React state `showSplitView` is set to `true`, mounting `<SplitView>` with `savedId={activeSavedId}`.
3. `SplitView.tsx` calls `getInputPdfUrl(savedId)` (line 18).
4. `savedOutputs.ts` sends `GET /simplify/saved/<doc_id>/input-pdf-url` (line 47).
5. Backend endpoint `get_input_pdf_url` in `saved_outputs.py` (line 142) reads the Firestore doc.
6. It fetches `data.get('input_pdf_gcs', '')` from the Firestore document (line 152).
7. **If this field is empty or missing, it returns 404** (line 153–154):
   ```python
   if not gcs_uri or not _BUCKET_NAME:
       return jsonify({'error': 'No input PDF stored for this output'}), 404
   ```

### Why `input_pdf_gcs` is empty

Trace back to `simplify_v1_2.py` where the output is saved (lines 336–347):

```python
try:
    input_pdf_gcs = None
    if resolved.combined_pdf_bytes:
        input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)

    saved_id = save_simplify_output(
        ...
        input_pdf_gcs=input_pdf_gcs,
        ...
    )
```

`input_pdf_gcs` is only set if `resolved.combined_pdf_bytes` is not `None`. There are **three scenarios** where `combined_pdf_bytes` ends up as `None`, causing `input_pdf_gcs=None` to be stored in Firestore:

**Scenario A — Text input (most common):** When a user pastes text directly (not uploading a file), `_resolve_input()` returns early at line 191–197 with `source_kind="text"` and `combined_pdf_bytes` defaults to `None` (see `ResolvedInput` dataclass at line 62). There is no file to store, so `input_pdf_gcs` is `None`. This is expected — the "Show Original" button should not be shown in this case.

**Scenario B — Upload merge failure:** When files are uploaded but `merge_pdfs()` throws an exception, the error is swallowed (lines 147–150 of `simplify_v1_2.py`), `combined_pdf_bytes` stays `None`, and the save still proceeds with `input_pdf_gcs=None`. This is a silent failure.

**Scenario C — `GCP_BUCKET_NAME` not set:** `upload_combined_pdf` in `save_output.py` (line 16–18) raises `RuntimeError` if `GCP_BUCKET_NAME` is empty. This exception is caught at line 349 in `simplify_v1_2.py` and logged, but execution continues with `input_pdf_gcs=None`. The GCS field ends up as `None` in Firestore. **This is the most likely cause of the bug in production if the env var is misconfigured.**

**Scenario D — `input_pdf_gcs` saved as `None` in Firestore:** `save_simplify_output` in `save_output.py` (line 58) stores `"input_pdf_gcs": input_pdf_gcs` directly. If `input_pdf_gcs` is Python `None`, Firestore stores it as a null value. `data.get('input_pdf_gcs', '')` returns `None` (not `''`), which is falsy, so the 404 fires.

### Summary of the bug

The `input_pdf_gcs` field ends up as `None` in Firestore whenever:
- The upload PDF merge fails silently, OR
- `GCP_BUCKET_NAME` is not set, OR
- The user submitted text (no file — in which case the button should not be shown)

---

## Fix Plan

### Fix 1: Hide "Show Original" button when no PDF was stored

The `activeSavedId` state is set whenever any result is saved — even text-input results that have no PDF. The button guard at `V1_2Page.tsx` line 331 only checks `activeSavedId`, not whether a PDF actually exists.

**Change:** Also track whether a PDF was uploaded. The backend already returns `input_pdf_gcs` in the Firestore document. The cleanest fix is: when the pipeline result arrives, also check whether `input_pdf_gcs` is truthy, and only set a new state flag `hasInputPdf` to `true` if so.

However, the SSE result payload (`result` event) does NOT currently include `input_pdf_gcs`. The simplest fix is:

**Option A (preferred):** Include `has_input_pdf` in the SSE result payload from the backend, and use it in the frontend to gate the button.

**Option B (simpler):** Only show "Show Original" when `inputMode === 'file'` (i.e., the user uploaded files, not pasted text). This is already tracked in the `inputMode` React state (`V1_2Page.tsx` line 30).

Use **Option B** — it requires a one-line change and handles the text-input case. For upload failures, the user will still see the 404 error in the SplitView, which is acceptable as a fallback.

### Fix 2: Ensure the GCS upload does not silently fail

In `simplify_v1_2.py` lines 336–350, the upload is attempted inside a try/except that catches all exceptions silently. Add a log-level warning that distinguishes between "no PDF to upload" and "upload failed":

```python
try:
    input_pdf_gcs = None
    if resolved.combined_pdf_bytes:
        input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
    elif resolved.source_kind not in ("text", "doc_id"):
        logger.warning("simplify_v1_2: combined_pdf_bytes is None for source_kind=%s", resolved.source_kind)
    ...
except Exception:
    logger.exception("simplify_v1_2: failed to save output - continuing without saved_id")
```

### Fix 3: Store `input_pdf_gcs` as empty string when None

In `save_output.py` line 58, change `input_pdf_gcs` from `None` to `""` when it is `None`. This makes the Firestore field consistently a string (easier to query):

```python
"input_pdf_gcs": input_pdf_gcs or "",
```

### Fix 4 (already working — verify): Split-screen on same page

The split-screen is already implemented. `SplitView.tsx` renders as a full-screen overlay (`position: fixed; inset: 0; z-index: 500`) with:
- Left panel: original PDF in an `<iframe>` loaded from a signed GCS URL
- Right panel: `<AppointmentNoteV12View result={result} />` (the simplified output)

`V1_2Page.tsx` already mounts `<SplitView>` when `showSplitView && result && activeSavedId` (lines 391–397). There is no `window.open` involved. Once the 404 is fixed and the PDF URL is returned, the iframe will load the PDF in-place. No changes to `SplitView.tsx` or `SplitView.css` are needed.

---

## Exact Changes Required

### File 1: `/root/projects/juno/frontend/src/pages/v1_2/V1_2Page.tsx`

**Change the "Show Original" button guard to also require `inputMode === 'file'`.**

Find line 331:
```tsx
{activeSavedId && (
  <button
    onClick={() => setShowSplitView(true)}
```

Replace with:
```tsx
{activeSavedId && inputMode === 'file' && (
  <button
    onClick={() => setShowSplitView(true)}
```

This ensures the button only appears when the user uploaded a file, not when they pasted text (since text inputs have no original PDF to show).

---

### File 2: `/root/projects/juno/backend/utils/save_output.py`

**Change `input_pdf_gcs` storage to use `""` instead of `None`.**

Find line 58 (inside `save_simplify_output`):
```python
            "input_pdf_gcs": input_pdf_gcs,
```

Replace with:
```python
            "input_pdf_gcs": input_pdf_gcs or "",
```

This prevents a Firestore null value from being stored when there is no PDF, ensuring the 404 condition at `saved_outputs.py` line 153 behaves consistently (`not gcs_uri` is `True` for both `""` and `None`).

---

### File 3: `/root/projects/juno/backend/routes/simplify_v1_2.py`

**Add a warning log when `combined_pdf_bytes` is unexpectedly `None` for a file upload.**

Find lines 336–339:
```python
        try:
            input_pdf_gcs = None
            if resolved.combined_pdf_bytes:
                input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
```

Replace with:
```python
        try:
            input_pdf_gcs = None
            if resolved.combined_pdf_bytes:
                input_pdf_gcs = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
            elif resolved.source_kind not in ("text", "doc_id"):
                logger.warning(
                    "simplify_v1_2: combined_pdf_bytes is None for source_kind=%s — "
                    "input PDF will not be stored",
                    resolved.source_kind,
                )
```

This adds visibility into the silent failure case so it shows up in logs.

---

## Files NOT to Change

- `/root/projects/juno/frontend/src/components/SplitView.tsx` — the component is complete and correct. Do not touch it.
- `/root/projects/juno/frontend/src/components/SplitView.css` — styling is correct. Do not touch it.
- `/root/projects/juno/frontend/src/api/savedOutputs.ts` — the API call is correct. Do not touch it.
- `/root/projects/juno/backend/routes/saved_outputs.py` — the backend endpoint logic is correct; the 404 return is intentional when `input_pdf_gcs` is missing. Do not touch it.
- `/root/projects/juno/backend/utils/pdf_merge.py` — PDF merge utility is correct. Do not touch it.

---

## Testing Steps

### 1. Verify the fix for text input (the most common 404 case)

1. Open the app and select the **text paste** input mode.
2. Paste any medical text and run simplification.
3. When the result appears, confirm the "Show Original" button is **not shown** (because `inputMode === 'file'` is false).
4. This verifies the button guard fix.

### 2. Verify the fix for file upload (the core fix)

1. Upload a PDF file (any medical PDF).
2. Run simplification.
3. When the result appears, confirm the "Show Original" button IS shown.
4. Click "Show Original".
5. The split-screen overlay should open. The left panel should show "Loading PDF..." briefly, then render the original PDF in the iframe.
6. The right panel should show the simplified appointment note.
7. Click "✕ Close" — the overlay should close, returning to the normal result view.

### 3. Verify GCS is configured (pre-condition check)

If you still see a 404 after the frontend fix, check that the backend environment has `GCP_BUCKET_NAME` set:

```bash
# In the backend container / Cloud Run environment
echo $GCP_BUCKET_NAME
```

If this is empty, the `upload_combined_pdf` call raises `RuntimeError("GCP_BUCKET_NAME is not configured")`, which is caught silently in the `try/except` at line 349, and `input_pdf_gcs` stays `None`. Set the env var in your deploy config (Cloud Run environment variables or `.env` file for local dev).

### 4. Verify the Firestore field after a new upload

After completing a new file upload with the fix applied:
1. Go to the Firebase Console → Firestore → `simplify_outputs` collection.
2. Find the newly created document (sort by `created_at` descending).
3. Confirm the `input_pdf_gcs` field is a non-empty string starting with `gs://` (e.g. `gs://your-bucket/simplify/uid/inputs/some-uuid.pdf`).
4. If it is `""` or `null`, the GCS upload is failing — check backend logs for the new warning message added in File 3.

### 5. Check backend logs if the PDF still fails to load

If the "Show Original" button appears but the iframe still shows an error:
- Look for `"get_input_pdf_url: failed to generate signed URL"` in the backend logs (`saved_outputs.py` line 168). This would indicate a GCS permissions issue (the service account needs `roles/storage.objectViewer` or `roles/storage.admin` on the bucket).
- Look for `"simplify_v1_2: failed to save output"` in the backend logs. This would indicate the save itself failed.
- Look for `"simplify_v1_2: combined_pdf_bytes is None"` — the new warning added in File 3.

---

## Architecture Notes (for context)

- `SplitView.tsx` fetches a **signed URL** (30-minute expiry) from the backend and loads it in an `<iframe>`. The PDF is served directly from GCS, not proxied through the backend. The signed URL is generated server-side in `saved_outputs.py` lines 161–165 using `blob.generate_signed_url(version="v4", expiration=timedelta(minutes=30))`.
- The GCS path for stored input PDFs is: `simplify/{user_id}/inputs/{uuid}.pdf` (see `save_output.py` line 22).
- The `doc_id` route segment in `GET /simplify/saved/<doc_id>/input-pdf-url` is the Firestore document ID, which is the same as `saved_id` returned in the SSE result payload.
- `activeSavedId` in `V1_2Page.tsx` is set at line 130 when the `result` SSE event contains a `saved_id` field. If `saved_id` is absent (e.g. the save failed), `activeSavedId` stays `null` and the "Show Original" button never appears.
