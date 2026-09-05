# PRD: SP1 — Image Input Support

**Sub-project:** SP1
**Branch context:** users/tejitpabari/trial-app
**Date:** 2026-09-04
**Status:** Draft
**Dependencies:** None

---

## 1. Problem

Juno's care-plan ingestion pipeline only accepts `pdf`, `txt`, `docx`, `html`, and `htm`
(`Constants.Uploads.ALLOWED_EXTENSIONS`, `backend/utils/constants.py:19`). A large share of
real-world care-plan intake is a phone photo of a printed after-visit summary or a
whiteboard/handwritten discharge note — none of that is accepted today. Per the
brainstorm's **D5 (locked)**, the user has approved adding `png/jpg/jpeg/webp/heic` input
support to the **shared** extraction path in `backend/services/care_plan_input.py`, so both
the main app and the forthcoming public trial (SP2/SP3) gain it for free, rather than
scoping it to the trial only.

Today there is no multimodal call anywhere in the backend — `LLMClient.generate_text`
(`backend/utils/llm.py:60`) only ever sends a bare string to
`GenerativeModel.generate_content()`. Adding image support requires:
1. A multimodal LLM call (Vertex `Part.from_data` + prompt) that coexists with the
   existing text-only call without changing its signature or behavior.
2. A new OCR-style extraction function wired into `extract_text_from_bytes`'s dispatch.
3. A decision on what happens to the "combined original document" PDF (used by the
   Show-Original viewer and the PDF report) when one of the inputs is an image.
4. Frontend acceptance of image files in the upload widget.

---

## 2. Goals

1. Accept `png`, `jpg`, `jpeg`, `webp`, `heic` files through the exact same upload paths
   PDFs/TXT/DOCX/HTML already use (`resolve_uploaded_files`, `resolve_input_from_job_doc`,
   `extract_text_from_downloaded`, `care_plan_jobs.py`'s `doc_id` path) — no new routes, no
   new request shape.
2. Extract clinical text from the image via Gemini vision on Vertex AI (never Google AI
   Studio / `GEMINI_API_KEY` — HIPAA BAA constraint, see `backend/utils/llm.py:1-11`).
3. Preserve the "Show Original" / PDF-report promise: an uploaded image is embedded as an
   actual image page in the combined PDF, not silently dropped or replaced by re-typeset
   text.
4. Fail predictably and cheaply for blurry photos, no-text images, unsupported MIME types,
   and Vertex safety-filter blocks — reusing existing `JunoError`/`ErrorCode` machinery
   wherever an existing code already fits.
5. Update the main app's file-picker (`CarePlanPage.tsx`) to allow selecting images, with
   matching client-side validation and hint copy.

---

## 3. Non-Goals

- The trial route, per-IP rate limiting, and trial-specific size/count caps — that's SP2.
  This PRD only touches the shared extraction path and the main app's frontend.
- OCR quality tuning beyond a single well-specified prompt (no multi-pass refinement, no
  bounding-box/handwriting-specific model).
- Client-side image compression/resizing before upload. Out of scope; see §9 Q3.
- Adding a general-purpose MIME-sniffing library (`python-magic`) — see §4.3 for the
  extension-based decision and its rationale.
- Any change to `google-cloud-vision` (already an unused, pre-existing dependency in
  `backend/requirements.txt` — not used anywhere in the codebase today, and not used by
  this design either; we go through Vertex's Gemini multimodal API, not the Cloud Vision
  OCR API, to stay on the single already-approved LLM path).

---

## 4. Architecture Decisions

### 4.1 `backend/utils/llm.py` — multimodal method, coexisting with `generate_text`

**Current shape** (verified, `llm.py:60-114`): `generate_text(self, prompt: str, ...)` builds
`self._model.generate_content(prompt, generation_config=..., safety_settings=...)`, then
does shared response handling (no-candidates check, `MAX_TOKENS` check, safety/finish-reason
classification, `response.text.strip()`).

Verified via `vertexai.generative_models._generative_models.GenerativeModel.generate_content`
(`backend/.venv/.../vertexai/generative_models/_generative_models.py:667-676`): `contents:
ContentsType` accepts `str`, `Image`, `Part`, or `List[Union[str, Image, Part]]` — a list
of `[Part, str]` is a directly supported call shape, no SDK/model change needed. Also
verified `Part.from_data(data: bytes, mime_type: str) -> Part` exists at
`vertexai.preview.generative_models.Part` (same import surface `llm.py` already uses).

**Decision:** extract the current body of `generate_text` into a private
`_generate_content(self, contents: str | list, temperature, max_tokens) -> str` that accepts
either shape, then make both `generate_text` and the new multimodal method thin wrappers
around it. This is the entire coexistence strategy — zero behavioral change for existing
callers (`generate_json` calls `generate_text`, `care_plan/v1_2/pipeline.py` is the only
other caller of `LLMClient`, confirmed via repo-wide grep — both are untouched).

```python
# backend/utils/llm.py — old
def generate_text(self, prompt: str, temperature: float = ..., max_tokens: int = ...) -> str:
    """Generate text from a prompt. Returns the text string directly."""
    try:
        response = self._model.generate_content(
            prompt,
            generation_config=self._VertexGenerationConfig(...),
            safety_settings=self._safety,
        )
    except Exception as api_exc:
        ...
    if not response.candidates:
        ...
    candidate = response.candidates[0]
    if ...MAX_TOKENS...:
        ...
    if not getattr(candidate, "content", None) or ...:
        ...
    return response.text.strip()
```

```python
# backend/utils/llm.py — new
from vertexai.preview.generative_models import (
    FinishReason,
    GenerationConfig as VertexGenerationConfig,
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
    Part,                      # NEW import
)

def _generate_content(
    self,
    contents: str | list,
    temperature: float,
    max_tokens: int,
) -> str:
    """Shared Vertex call + response handling for both text-only and
    multimodal (image + prompt) generation. `contents` is passed straight
    through to GenerativeModel.generate_content, which accepts a bare str
    or a list of [Part, str, ...] — see ContentsType."""
    try:
        response = self._model.generate_content(
            contents,
            generation_config=self._VertexGenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
            safety_settings=self._safety,
        )
    except Exception as api_exc:
        # unchanged — see current generate_text body
        ...
    if not response.candidates:
        raise JunoError(ErrorCode.LLM_NO_CANDIDATES, ...)  # unchanged
    candidate = response.candidates[0]
    if hasattr(candidate, "finish_reason") and candidate.finish_reason == self._FinishReason.MAX_TOKENS:
        raise JunoError(ErrorCode.LLM_MAX_TOKENS, ...)  # unchanged
    if not getattr(candidate, "content", None) or not getattr(candidate.content, "parts", None):
        ...  # unchanged, uses classify_finish_reason
    return response.text.strip()

def generate_text(self, prompt: str, temperature: float = Constants.Llm.TEMPERATURE_TEXT, max_tokens: int = Constants.Llm.MAX_TOKENS) -> str:
    """Generate text from a prompt. Returns the text string directly."""
    return self._generate_content(prompt, temperature, max_tokens)

def generate_text_from_image(
    self,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    temperature: float = Constants.Llm.TEMPERATURE_TEXT,
    max_tokens: int = Constants.Llm.MAX_TOKENS,
) -> str:
    """Generate text from an image + instruction prompt (Gemini vision).
    Shares all response/error handling with generate_text via _generate_content."""
    part = Part.from_data(data=image_bytes, mime_type=mime_type)
    return self._generate_content([part, prompt], temperature, max_tokens)

def generate_json(self, prompt: str, temperature: ... = ..., max_tokens: int = ...) -> dict | list:
    """UNCHANGED — still calls self.generate_text(prompt, ...)."""
```

No change to `__init__`, safety settings, or the `gemini-1.5-pro` / `gemini-3.5-flash`
model selection — both are natively multimodal, confirmed by Google's Gemini API image-
understanding documentation (accepts `image/png`, `image/jpeg`, `image/webp`, `image/heic`,
`image/heif` as inline-data MIME types for both model families).

### 4.2 OCR extraction prompt (verbatim)

New constant in `backend/utils/constants.py` under a new `class Llm` addition (or inline in
the new module — placed as `Constants.Llm.IMAGE_OCR_PROMPT` for consistency with how other
prompt-adjacent constants live under `Constants`):

```python
IMAGE_OCR_PROMPT: str = (
    "You are extracting clinical text from a photographed or scanned medical "
    "document image.\n\n"
    "Transcribe ALL visible text from the image exactly as written, preserving:\n"
    "- Section headers and structure, as plain text (no markdown, no HTML)\n"
    "- Medication names, dosages, frequencies, and instructions verbatim\n"
    "- Dates, numbers, units, and clinician/patient names exactly as they appear\n"
    "- Line breaks between distinct sections, list items, or table rows\n\n"
    "Do not summarize, interpret, correct, or add any text that is not visibly "
    "present in the image. Do not describe the image (for example, never write "
    "\"this is a photo of...\"). Output ONLY the transcribed text.\n\n"
    "If the image contains no legible text at all (blank, illegibly blurry, or a "
    "non-document photo), respond with exactly this token and nothing else:\n"
    "NO_TEXT_FOUND"
)
```

The `NO_TEXT_FOUND` sentinel is the mechanism for failure mode "image with no readable
text" (§4.6) — it lets the extraction function distinguish "model ran fine but found
nothing" from every other failure class, without inventing a new Vertex response field.

### 4.3 New module: `backend/utils/image_ocr.py`

Mirrors the existing per-format extractor modules (`utils/pdf.py`,
`utils/misc.py::extract_text_from_html`) — one small, single-purpose module per input
format, imported by `care_plan_input.py`'s dispatcher.

```python
"""utils/image_ocr.py — image → clinical text extraction via Gemini vision (Vertex AI)."""

from utils.constants import Constants
from utils.llm import LLMClient
from errors import ErrorCode, JunoError

_NO_TEXT_SENTINEL = "NO_TEXT_FOUND"

IMAGE_EXT_TO_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "heic": "image/heic",
}


def extract_text_from_image(image_bytes: bytes, ext: str) -> str:
    """Extract clinical text from image bytes via Gemini vision on Vertex AI.

    `ext` is the already-lowercased file extension (as produced by
    care_plan_input._get_extension); mapped to a MIME type here so the
    dispatcher in care_plan_input.py stays format-agnostic, matching the
    (bytes) -> str shape of the other extractors.
    """
    mime_type = IMAGE_EXT_TO_MIME.get(ext)
    if mime_type is None:
        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")

    client = LLMClient()
    text = client.generate_text_from_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        prompt=Constants.Llm.IMAGE_OCR_PROMPT,
        temperature=Constants.Llm.TEMPERATURE_TEXT,
        max_tokens=Constants.Llm.MAX_TOKENS,
    )
    if text.strip().upper() == _NO_TEXT_SENTINEL:
        raise JunoError(
            ErrorCode.EMPTY_DOCUMENT,
            detail="Image contained no readable text (model returned NO_TEXT_FOUND).",
        )
    return text
```

`LLMClient()` is instantiated per call here (same pattern as `care_plan/v1_2/pipeline.py`
already uses — no shared client caching exists today, so this introduces no new pattern).

**Why a new module instead of adding to `care_plan_input.py` directly:** every other format
extractor (`extract_text_from_pdf`, `extract_text_from_html`) lives in `utils/`, not in
`services/care_plan_input.py` itself — that file only *dispatches* to them. Following the
existing convention keeps `care_plan_input.py`'s dispatch table thin and testable in
isolation (mock `LLMClient`, no Flask/Firestore/GCS fixtures needed).

### 4.4 `backend/services/care_plan_input.py` — dispatch wiring

```python
# old (care_plan_input.py:52-79)
from utils.misc import extract_text_from_html, source_separator, text_artifact_filename
from utils.pdf import merge_pdfs, extract_text_from_pdf

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, DOCX, or HTML bytes."""
    ext = _get_extension(filename)
    if not ext:
        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"filename has no extension: {filename}")
    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == "docx":
        ...
    if ext in {"html", "htm"}:
        return extract_text_from_html(file_bytes)
    raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")
```

```python
# new
from utils.image_ocr import extract_text_from_image

def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, DOCX, HTML, or image bytes."""
    ext = _get_extension(filename)
    if not ext:
        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"filename has no extension: {filename}")
    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == "docx":
        ...  # unchanged
    if ext in {"html", "htm"}:
        return extract_text_from_html(file_bytes)
    if ext in Constants.Uploads.IMAGE_EXTENSIONS:          # NEW
        return extract_text_from_image(file_bytes, ext)    # NEW
    raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")
```

This one dispatch point is the reason all four call sites (`resolve_uploaded_files:108`,
`resolve_input_from_job_doc:164`, `extract_text_from_downloaded:176`,
`care_plan_jobs.py:83`) automatically gain image support — confirmed unchanged, no edits
needed at any of those call sites for the text-extraction behavior itself. `is_allowed_extension`
(`care_plan_input.py:47-49`) also needs no code change — it already checks membership in
`Constants.Uploads.ALLOWED_EXTENSIONS`, which §4.5 extends.

### 4.5 `backend/utils/constants.py` — new upload extensions

```python
# old
class Uploads:
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
    MAX_FILE_BYTES: int = 10 * 1024 * 1024
    MAX_FILE_COUNT: int = 10
    MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
    UPLOAD_PREFIX: str = "care_plan-uploads"
```

```python
# new
class Uploads:
    IMAGE_EXTENSIONS: frozenset[str] = frozenset({"png", "jpg", "jpeg", "webp", "heic"})
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
        {"pdf", "txt", "docx", "html", "htm"} | IMAGE_EXTENSIONS
    )
    MAX_FILE_BYTES: int = 10 * 1024 * 1024        # unchanged — see §4.7 rationale
    MAX_FILE_COUNT: int = 10                       # unchanged
    MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
    UPLOAD_PREFIX: str = "care_plan-uploads"
```

Also add, under `class Llm:` (`constants.py:61-66`):

```python
class Llm:
    MODEL_DEFAULT: str = "gemini-1.5-pro"
    MAX_TOKENS: int = 8192
    MAX_TOKENS_LONG_FORM: int = 65536
    TEMPERATURE_TEXT: float = 0.3
    TEMPERATURE_JSON: float = 0.2
    IMAGE_OCR_PROMPT: str = ( ... )   # §4.2, full text
```

Note this is **not** a trial-scoped change — per D5, the widened `ALLOWED_EXTENSIONS` is
shared by both the main app and the future trial route. The brainstorm's stated risk ("the
trial route must pass its own allowed-extension set rather than mutating the shared
constant") is about the trial *narrowing* this same shared set later (SP2's concern, e.g. if
the trial wants a stricter cap) — not about SP1, which is explicitly the shared widening the
user approved.

### 4.6 Merge-candidate decision — images in the combined "original document" PDF

**The wrinkle, verified:** `resolve_uploaded_files` (`care_plan_input.py:82-138`) builds
`merge_candidates` — `pdf`/`txt` go in as-is; `docx`/`html`/`htm` degrade to a "text
artifact" (their *extracted text*, re-typeset as a PDF page via `text_artifact_filename` +
`_txt_to_pdf`) because there is no faithful way to reconstruct their original visual layout
as a PDF page anyway. `merge_pdfs` (`backend/utils/pdf.py:73-95`) then dispatches purely by
extension: `pdf` → `_append_pdf`, `txt` → `_txt_to_pdf` + `_append_pdf`, anything else →
skipped with a warning.

**Options considered:**
- **(A) Skip merging entirely.** Images never become merge candidates. Simplest, but the
  Show-Original viewer and PDF report would show *nothing* for an image-only submission,
  or silently drop the photo from a mixed submission — the user uploaded a real document
  and "Show Original" would not show it. Rejected: breaks an existing user-facing promise
  for no implementation savings (the merge/skip logic already exists and tolerates partial
  failure).
- **(B) Embed the image as an actual PDF page.** Decode the image, draw it on a
  letter-sized page (scaled to fit, preserving aspect ratio), append as a real PDF page —
  the same visual object the user uploaded. Requires Pillow (already present transitively
  via `reportlab`, confirmed installed: `Pillow==12.2.0` in `backend/.venv`) plus
  `reportlab`'s `canvas.drawImage`, both zero-new-dependency for `png`/`jpg`/`jpeg`/`webp`.
- **(C) Reuse the text-artifact path** (treat the OCR'd text like docx/html). Rejected:
  this discards the actual photographed page and replaces it with re-typeset OCR text in
  the "original document" viewer — actively misleading for a feature whose entire point is
  showing the user their unmodified original.

**Decision: (B).** Add `_image_to_pdf(file_bytes: bytes, filename: str) -> bytes` to
`backend/utils/pdf.py`, mirroring the existing `_txt_to_pdf` shape:

```python
# backend/utils/pdf.py — new
def _image_to_pdf(file_bytes: bytes, filename: str) -> bytes:
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)          # respect phone-camera EXIF rotation
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    page_w, page_h = letter
    margin = 36
    max_w, max_h = page_w - 2 * margin, page_h - 2 * margin
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    draw_w, draw_h = img.width * scale, img.height * scale

    pdf = canvas.Canvas(buffer, pagesize=letter)
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2
    pdf.drawImage(ImageReader(img), x, y, width=draw_w, height=draw_h)
    pdf.save()
    return buffer.getvalue()
```

(`from reportlab.lib.utils import ImageReader` added to the existing `reportlab` imports
inside the lazy `_txt_to_pdf`-style try/except-guarded import block.)

`merge_pdfs`'s dispatch (`backend/utils/pdf.py:78-88`) gets one new branch:

```python
# old
if ext == "pdf":
    merged_pages += _append_pdf(writer, file_bytes, filename)
elif ext == "txt":
    merged_pages += _append_pdf(writer, _txt_to_pdf(file_bytes, filename), filename)
else:
    logger.warning("pdf_merge: skipping unsupported file %s", filename)
```

```python
# new
if ext == "pdf":
    merged_pages += _append_pdf(writer, file_bytes, filename)
elif ext == "txt":
    merged_pages += _append_pdf(writer, _txt_to_pdf(file_bytes, filename), filename)
elif ext in Constants.Uploads.IMAGE_EXTENSIONS:          # NEW
    merged_pages += _append_pdf(writer, _image_to_pdf(file_bytes, filename), filename)
else:
    logger.warning("pdf_merge: skipping unsupported file %s", filename)
```

(`pdf.py` gains `from utils.constants import Constants`.)

And `resolve_uploaded_files` (`care_plan_input.py:111-117`) gets one new branch alongside
the existing pdf/txt vs. docx/html split:

```python
# old
ext = _get_extension(filename)
if ext in {"pdf", "txt"}:
    merge_candidates.append((file_bytes, filename))
elif ext in {"docx", "html", "htm"} and extracted_text.strip():
    merge_candidates.append(
        (extracted_text.encode("utf-8"), text_artifact_filename(filename))
    )
```

```python
# new
ext = _get_extension(filename)
if ext in {"pdf", "txt"} or ext in Constants.Uploads.IMAGE_EXTENSIONS:   # NEW: images join this branch
    merge_candidates.append((file_bytes, filename))
elif ext in {"docx", "html", "htm"} and extracted_text.strip():
    merge_candidates.append(
        (extracted_text.encode("utf-8"), text_artifact_filename(filename))
    )
```

Images pass their **raw original bytes** into `merge_candidates` (like pdf/txt), not their
extracted text — `merge_pdfs`'s new branch is what converts those raw bytes to a PDF page.
This is deliberately unconditional (no `and extracted_text.strip()` guard) — even if OCR
extraction raised `EMPTY_DOCUMENT` for a given image, the caller never reaches this line for
that file (the exception propagates out of the `for upload in files:` loop in
`resolve_uploaded_files` before `merge_candidates.append` runs — see §4.7 for confirmation
this loop-abort-on-first-error behavior is pre-existing and unchanged).

**HEIC-specific gap:** stock Pillow (no plugin) cannot `Image.open()` a HEIC file — HEIF/HEIC
codec support is patent-encumbered and excluded from Pillow core. This affects **only the
merge/embed path (B)**, not the OCR path — `extract_text_from_image` sends raw HEIC bytes
straight to Vertex via `Part.from_data(mime_type="image/heic")`, which per Gemini API's
documented image-understanding support accepts `image/heic` natively (no local decode).
**Decision:** add `pillow-heif` (`backend/requirements.txt`) and call
`pillow_heif.register_heif_opener()` once at import time in `backend/utils/pdf.py`, which
transparently teaches `PIL.Image.open()` to decode HEIC/HEIF — no code path changes needed
beyond that one registration call, `_image_to_pdf` works unmodified for HEIC once
registered. `pillow-heif` ships prebuilt manylinux wheels (bundled libheif) for the
`python:3.11-slim` base image's target platform — **flagged for a build-time check in §9**
since we cannot install/verify this from the design phase, not a design blocker (fallback:
`apt-get install libheif1` in `backend/Dockerfile` if the wheel doesn't cover the base image).

### 4.7 Size / count limits for images

**Decision: no new image-specific limits — reuse the existing shared caps unchanged**
(`MAX_FILE_BYTES` 10MB per file, `MAX_FILE_COUNT` 10 files, `MAX_AGGREGATE_FILE_BYTES` 25MB
total). Rationale:
- A typical smartphone photo of a document is 2–8MB (varies by resolution/compression) —
  comfortably under the existing 10MB single-file cap. A scenario requiring a *smaller*
  image-specific cap doesn't arise in normal use.
- Gemini's inline-data image limit (base64-encoded in the request) is well above 10MB per
  image in current Vertex AI quota docs, so the existing cap is the binding constraint, not
  Vertex's.
- Introducing a second, image-specific byte/count cap adds a validation branch with no
  concrete problem it solves today; if usage data post-launch shows images are
  disproportionately larger/costlier, a follow-up SP can add `MAX_IMAGE_FILE_BYTES`
  without touching this SP's design.
- Cost/latency scales with image resolution and count, not byte size directly — see §8.
  The existing `MAX_FILE_COUNT=10` already bounds worst-case cost per job.

This closes survey question 5 as **[RESOLVED]** (§9).

### 4.8 File-by-file change summary

| File | Change |
|---|---|
| `backend/utils/llm.py` | Extract `_generate_content` (shared body); `generate_text` becomes a thin wrapper; add `generate_text_from_image`. Add `Part` to the existing `vertexai.preview.generative_models` import. |
| `backend/utils/image_ocr.py` | **New file.** `extract_text_from_image(image_bytes, ext) -> str`, `IMAGE_EXT_TO_MIME` map, `NO_TEXT_FOUND` sentinel handling → `ErrorCode.EMPTY_DOCUMENT`. |
| `backend/utils/constants.py` | Add `Uploads.IMAGE_EXTENSIONS`; widen `Uploads.ALLOWED_EXTENSIONS`; add `Llm.IMAGE_OCR_PROMPT`. |
| `backend/services/care_plan_input.py` | `extract_text_from_bytes`: one new `elif` branch dispatching to `extract_text_from_image`. `resolve_uploaded_files`: images join the raw-bytes merge-candidate branch. Import `extract_text_from_image`. |
| `backend/utils/pdf.py` | Add `_image_to_pdf` (Pillow decode + reportlab page draw); add one new `elif` branch in `merge_pdfs`; add `pillow_heif.register_heif_opener()` at import time; import `Constants`, `ImageReader`. |
| `backend/requirements.txt` | Add `pillow-heif`. (`Pillow` itself already present transitively via `reportlab` — pin it explicitly here too since we now depend on it directly, not just transitively: add `Pillow` alongside.) |
| `backend/routes/care_plan_jobs.py` | Update the two hardcoded error strings ("File must be PDF, TXT, DOCX, or HTML" / "Stored file must be PDF, TXT, or DOCX") to mention images — cosmetic, not behavioral (validation itself is driven by the now-widened `Constants.Uploads.ALLOWED_EXTENSIONS` via `is_allowed_extension`, no logic change needed there). |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | §6. |

---

## 5. API Change Summary

**None.** No new routes, no request/response shape changes, no new query params. The
`POST /care_plan/jobs` multipart `files` field simply now accepts image MIME types/
extensions it previously rejected with `INPUT_VALIDATION_ERROR` (400). Response shapes for
success and every existing error path are unchanged. The `doc_id` re-processing path
(`care_plan_jobs.py:76-92`) and `resolve_input_from_job_doc` (batch/job-doc replay) also
gain image support automatically since both route through `extract_text_from_bytes`.

---

## 6. Frontend Change Summary

Single file, `frontend/src/pages/care-plan/CarePlanPage.tsx` (main app, not the not-yet-built
trial app):

```tsx
// old (line 53-64)
const handleFiles = useCallback((selectedFiles: File[]) => {
  const invalid = selectedFiles.filter(f => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    return !['pdf', 'txt', 'docx', 'html', 'htm'].includes(ext ?? '');
  });
  if (invalid.length > 0) {
    setError(`Unsupported file type: ${invalid.map(f => f.name).join(', ')}. Use PDF, TXT, DOCX, or HTML.`);
    return;
  }
  setError(null);
  setFiles(selectedFiles);
}, []);
```

```tsx
// new
const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic'];

const handleFiles = useCallback((selectedFiles: File[]) => {
  const invalid = selectedFiles.filter(f => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    return !ALLOWED_UPLOAD_EXTENSIONS.includes(ext ?? '');
  });
  if (invalid.length > 0) {
    setError(`Unsupported file type: ${invalid.map(f => f.name).join(', ')}. Use PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC).`);
    return;
  }
  setError(null);
  setFiles(selectedFiles);
}, []);
```

```tsx
// old (line 186)
accept=".pdf,.txt,.docx,.html,.htm"
```
```tsx
// new
accept=".pdf,.txt,.docx,.html,.htm,.png,.jpg,.jpeg,.webp,.heic"
```

```tsx
// old (line 202)
<p className="upload-hint">PDF, TXT, DOCX, or HTML · Multiple files = one combined process</p>
```
```tsx
// new
<p className="upload-hint">PDF, TXT, DOCX, HTML, or image (PNG/JPG/WEBP/HEIC) · Multiple files = one combined process</p>
```

No other frontend file references the extension allowlist or `accept` attribute (confirmed
via repo-wide grep for `.pdf,.txt` and `accept=` across `frontend/src` — this is the only
file-input widget in the main app). No changes needed to `useJobStatuses`, `createCarePlanJob`,
job status polling, the results page, or `buildPdfHtml.ts` — none of them branch on input
file type; they all consume the already-resolved text/PDF the backend produces.

---

## 7. Testing

Mirrors `backend/tests/` structure (pytest, existing conventions from
`backend/tests/utils/test_llm.py` and `backend/tests/services/test_care_plan_input.py`).

**`backend/tests/utils/test_llm.py`** (extend existing file, same `vertex_env` fixture
pattern used throughout):
- `test_generate_text_from_image_calls_generate_content_with_part_and_prompt` — mock
  `Part.from_data`, assert `generate_content` is called with `[mock_part, prompt]`.
- `test_generate_text_from_image_shares_response_handling` — reuse the existing
  `test_generate_text_max_tokens_logs_warning` / `test_generate_text_no_candidates_raises`
  / `test_generate_text_vertex_failure_raises_vertex_api_error` scenarios, but invoking
  `generate_text_from_image` instead of `generate_text`, asserting identical `ErrorCode`
  outcomes — this is the regression test proving `_generate_content` extraction didn't
  change behavior for either caller.
- `test_generate_text_still_works_after_refactor` — re-run the existing `generate_text`
  happy-path test unmodified to confirm the extraction didn't regress the text-only path.

**`backend/tests/utils/test_image_ocr.py`** (new file):
- `test_extract_text_from_image_returns_model_text` — mock `LLMClient.generate_text_from_image`,
  assert the returned text passes through unchanged for ordinary output.
- `test_extract_text_from_image_no_text_sentinel_raises_empty_document` — mock the client
  to return `"NO_TEXT_FOUND"`, assert `JunoError` with `ErrorCode.EMPTY_DOCUMENT`.
- `test_extract_text_from_image_unknown_extension_raises_unsupported_file_type` — call with
  an `ext` not in `IMAGE_EXT_TO_MIME` (defensive; dispatch should never reach here in
  practice since `care_plan_input.py` already filters, but the function must fail safely
  if called directly).
- `test_image_ext_to_mime_covers_all_image_extensions` — assert
  `set(IMAGE_EXT_TO_MIME) == Constants.Uploads.IMAGE_EXTENSIONS`, so the two data
  structures can never silently drift apart.

**`backend/tests/services/test_care_plan_input.py`** (extend existing file):
- `test_extract_text_from_bytes_dispatches_image_extensions_to_ocr` — mock
  `utils.image_ocr.extract_text_from_image`, assert `extract_text_from_bytes(bytes, "photo.png")`
  calls it with `(bytes, "png")` and returns its result.
- `test_is_allowed_extension_accepts_all_image_extensions` — parametrize over
  `png/jpg/jpeg/webp/heic`, assert `is_allowed_extension` is `True` for each.
- `test_resolve_uploaded_files_image_becomes_raw_merge_candidate` — construct a fake upload
  with a tiny real PNG's bytes (a 1x1 PNG literal is fine — no network), mock
  `extract_text_from_image` to return known text, assert the returned combined-PDF bytes
  are non-`None` and mock `merge_pdfs`/`_image_to_pdf` interaction is exercised (or assert
  `merge_candidates` construction directly if refactored to be testable in isolation).

**`backend/tests/utils/test_pdf.py`** (extend existing file):
- `test_image_to_pdf_produces_one_page` — feed a real tiny in-memory PNG (generate via
  `PIL.Image.new(...)`, no fixture file needed), assert `_image_to_pdf` returns bytes that
  `PdfReader` can open with exactly one page.
- `test_image_to_pdf_respects_exif_rotation` — construct an image with EXIF orientation
  metadata (via Pillow), assert output page dimensions reflect the *corrected* orientation.
- `test_merge_pdfs_embeds_image_alongside_pdf_and_txt` — merge a real 1-page PDF + a tiny
  PNG together via `merge_pdfs`, assert the result has 2 pages.
- `test_merge_pdfs_handles_heic_via_pillow_heif` — **requires the `pillow-heif` dependency
  to be installed and its wheel to actually decode on the test runner's platform**; if this
  proves environment-fragile in CI, mark it `@pytest.mark.skipif` guarded by a successful
  `import pillow_heif` (do not skip the PNG/JPG/WEBP coverage, only the HEIC-specific case
  if the dependency truly can't be validated in CI — see §9 Q1 for why this is flagged
  rather than pre-decided).

**`backend/tests/routes/test_care_plan_jobs.py`** (extend existing file, if it already
covers the `_resolve_input_for_job` upload path — confirmed it exists, likely already
exercises `resolve_uploaded_files` end-to-end with mocked GCS/Firestore):
- `test_create_care_plan_job_accepts_image_upload` — POST a fake image file through the
  existing test client fixture, assert 202 (not the old 400 `INPUT_VALIDATION_ERROR`).

No new integration test infra needed — everything above uses existing fixtures/mocking
conventions (`vertex_env`, in-memory bytes, no real GCP calls).

**Frontend:** no existing test file covers `CarePlanPage.tsx`'s `handleFiles` directly
(confirmed no `CarePlanPage.test.tsx` exists) — this SP does not introduce one either,
consistent with the file's current untested state; the change is a 3-line extension-list
edit with no new logic branch worth a dedicated new test file. If reviewers want coverage,
the natural home would be `frontend/src/pages/care-plan/CarePlanPage.test.tsx` asserting
`handleFiles` accepts each new extension and rejects e.g. `.gif` — flagged as optional in
§9, not required by this PRD.

---

## 8. Manual Intervention Required From You

None required to land this SP's code. Two items to be aware of, not blocking:

1. **`pillow-heif` wheel compatibility with `python:3.11-slim`** — needs a one-time build
   verification (`docker build` locally or watch the first CI/deploy build) once the
   dependency is added. If the prebuilt wheel doesn't cover this base image's architecture,
   `backend/Dockerfile` needs one added line (`apt-get install -y --no-install-recommends
   libheif1`) alongside the existing `ffmpeg` install. This is a build-time check, not a
   GCP console/credentials action — flagged here per instructions but does not require you
   personally; the implementing agent can verify it directly.
2. **Cost awareness (not an action item):** every image upload now costs one additional
   Vertex vision call per image (§8-cost below) on top of the existing 5 text-generation
   calls per pipeline run. No budget/quota change is being requested in this SP — flagging
   only so you're not surprised by a small per-job cost increase for image-heavy jobs.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Can `pillow-heif`'s prebuilt wheel actually decode HEIC on the `python:3.11-slim` deploy target, or does it need `libheif1` via apt? | **[OPEN]** — cannot be verified from the design phase without a build; blocks nothing in this PRD's code design (the fallback — one apt-get line — is fully specified in §4.6/§8) but should be verified as the first thing done in implementation, before writing the HEIC-specific test in §7. |
| Q2 | Does Vertex's Gemini API actually accept `mime_type="image/heic"` for inline data on the specific deployed models (`gemini-1.5-pro` default, `gemini-3.5-flash` in production per `deploy.yml:56,68`), or does it need conversion to JPEG first? | **[OPEN]** — based on Google's published Gemini API image-understanding documentation, `image/heic` and `image/heif` are listed as natively supported inline-data MIME types for Gemini vision models generally; this PRD's design (§4.1, §4.3) sends raw HEIC bytes directly with no local conversion, relying on that documented support. Not independently verified against a live Vertex call in this sandbox (no network/live-credential access during design). **Fallback if wrong:** `extract_text_from_image` can decode via the same `pillow-heif`-registered `PIL.Image.open()` used in §4.6, re-encode to JPEG in-memory, and retry once with `mime_type="image/jpeg"` — a small, localized addition to `image_ocr.py` if Q2 resolves "no." Implementation must do a live smoke test against a real HEIC file through the actual deployed model before considering this SP done. |
| Q3 | Should the frontend downscale/compress large images client-side before upload (to cut latency/cost for e.g. an uncompressed 20MB camera-RAW-adjacent photo)? | **[DEFERRED]** — out of scope for this SP (see Non-Goals §3); the existing 10MB cap already bounds worst-case size, and client-side image resizing is a meaningful independent feature (canvas resize, format re-encode) better scoped as its own follow-up if usage data shows it's needed. |
| Q4 | Should `frontend/src/constants.ts` host a shared `ALLOWED_UPLOAD_EXTENSIONS` constant instead of the inline array added directly in `CarePlanPage.tsx` (§6), given SP3's trial frontend will need the same list? | **[DEFERRED]** — `constants.ts` currently holds only path-builder helpers (confirmed by reading the file), no extension lists; introducing a new shared constant is a reasonable dedup but not required for SP1's own correctness, since `CarePlanPage.tsx` is the only file-input in the main app today. Leave as inline in this SP; revisit when SP3 (`frontend-trial/`) is built and needs the same list, at which point sharing it becomes an actual (not speculative) duplication problem. |
| Q5 | Should `_image_to_pdf`'s per-image page size be letter (matching `_txt_to_pdf`'s existing convention) or should it preserve the image's native aspect ratio as a variable page size? | **[RESOLVED: letter, scaled-to-fit with aspect ratio preserved]** — matches `_txt_to_pdf`'s existing fixed-letter-page convention (§4.6 code), so the combined PDF's pages are visually consistent regardless of source format; the image itself is drawn at its native aspect ratio *within* that page (never stretched/distorted), just centered with margins. |
| Q6 | Image size/count caps — reuse existing or add image-specific limits? | **[RESOLVED: reuse existing `MAX_FILE_BYTES`/`MAX_FILE_COUNT`/`MAX_AGGREGATE_FILE_BYTES` unchanged]** — see §4.7 for full rationale (typical photo size well under cap, Vertex's own inline-data limit is not the binding constraint, no concrete problem a new cap would solve today). |
| Q7 | MIME detection — extension-based or magic-byte sniffing? | **[RESOLVED: extension-based]** — consistent with every other format in this codebase (`_get_extension` + `ALLOWED_EXTENSIONS` membership, no sniffing anywhere today); avoids a new `python-magic`/`libmagic1` dependency for a problem (mislabeled extension) that already exists identically for every other supported format and simply surfaces as a Vertex-side error instead of an upload-time one. |
| Q8 | Error code for "image contained no readable text" — reuse `EMPTY_DOCUMENT` or add a new code? | **[RESOLVED: reuse `ErrorCode.EMPTY_DOCUMENT`]** — its existing message ("may be a scanned image without OCR, an empty file, or all-whitespace content") and `user_hint` ("make sure the file contains selectable text... not just a scanned image") already describe this exact scenario near-verbatim; no new `ErrorInfo` catalog entry needed. |
| Q9 | Vertex safety-filter block on image content — new error handling needed? | **[RESOLVED: no new handling — reuses `ErrorCode.LLM_SAFETY_BLOCKED` via `classify_finish_reason`, already wired through `_generate_content` for free]** since the multimodal call shares 100% of `generate_text`'s response-classification code path (§4.1). |
| Q10 | Is D5 (image support scope — main app + trial, not trial-only) still the locked decision, or could this PRD narrow it back to trial-only? | **[RESOLVED per brainstorm D5, locked]** — not re-litigated here; this PRD implements the shared-widening design D5 specifies. |

**Dependencies:** None — this SP is fully self-contained (per the initiative's phasing,
§7 "Riskiest items" in `brainstorm.md` names this as one of two highest-risk items, the
other being the Hosting split in SP4/P3) and can land independently of SP2–SP5.
