# Tasks: SP1 — Image Input Support

Source PRD: `.dev/trial-simplify/01-image-input/PRD.md`. All decisions below trace to
PRD §4 (Architecture Decisions); §9 is fully `[RESOLVED]` — no open questions block this
work. Order matches dependency order; each task is committable on its own.

---

### Task 1 — Add image-processing dependencies to `backend/requirements.txt`

   - Files: `backend/requirements.txt`
   - Changes: Add two lines. `Pillow` is currently only a transitive dependency (via
     `reportlab`, confirmed `Pillow==12.2.0` present in `backend/.venv`); pin it directly
     since `utils/pdf.py` and `utils/image_ocr.py` will import it directly after this SP.
     Add `pillow-heif` (new, for HEIC/HEIF decode support — PRD §4.6).
     ```
     Pillow
     pillow-heif
     ```
     Place both near the existing `reportlab` / `python-docx` block.
   - Acceptance criteria:
     - `backend/requirements.txt` contains `Pillow` and `pillow-heif` as top-level entries.
     - `cd backend && pip install -r requirements.txt` completes with no dependency
       conflicts.

---

### Task 2 — Verify `pillow-heif` decodes HEIC on the `python:3.11-slim` deploy image (§9 Q1)

   **Do this before Task 10 (the HEIC-specific test).** This is a build-time empirical
   check the PRD explicitly defers to implementation (§9 Q1: "discover at implementation
   time... still worth confirming early in implementation, before writing the HEIC-specific
   test").

   - Files: none (verification only); `backend/Dockerfile` only if the fallback below is
     needed.
   - Changes:
     1. Build the backend image locally: `cd backend && docker build -t juno-backend-heic-check .`
     2. Run a one-off container and confirm HEIC decode works:
        ```bash
        docker run --rm juno-backend-heic-check python -c "
        import pillow_heif; pillow_heif.register_heif_opener()
        from PIL import Image
        import io, urllib.request
        # any small real .heic test fixture works; a hand-crafted minimal HEIC also works
        print('pillow_heif import + register: OK')
        "
        ```
        (A full round-trip decode of a real `.heic` file is preferable if a sample file is
        available; the import + `register_heif_opener()` call succeeding without
        `ImportError`/`OSError` is the minimum bar for this check.)
     3. **If the wheel does not cover this base image/architecture** (import or decode
        fails), add the documented fallback to `backend/Dockerfile`, alongside the existing
        `ffmpeg` install:
        ```dockerfile
        RUN apt-get update && \
            apt-get install -y --no-install-recommends ffmpeg libheif1 && \
            apt-get clean && \
            rm -rf /var/lib/apt/lists/*
        ```
        Re-run steps 1–2 to confirm the fallback fixes it.
   - Acceptance criteria:
     - The Docker build succeeds.
     - The verification command above prints `pillow_heif import + register: OK` with no
       exception, either with the wheel alone or after adding `libheif1` to the Dockerfile.
     - If `libheif1` was added, `backend/Dockerfile` reflects it and this is noted in the
       Task 10 test (see below) rather than silently assumed.

---

### Task 3 — Add image extensions and OCR prompt constant (`backend/utils/constants.py`)

   - Files: `backend/utils/constants.py`
   - Changes: Widen `class Uploads` and add a prompt constant under `class Llm`, exactly
     per PRD §4.2 and §4.5.
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
         MAX_FILE_BYTES: int = 10 * 1024 * 1024        # unchanged, PRD §4.7
         MAX_FILE_COUNT: int = 10                       # unchanged
         MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
         UPLOAD_PREFIX: str = "care_plan-uploads"
     ```
     Under `class Llm:` (currently at `constants.py:61-66`), add the verbatim prompt from
     PRD §4.2:
     ```python
     class Llm:
         MODEL_DEFAULT: str = "gemini-1.5-pro"
         MAX_TOKENS: int = 8192
         MAX_TOKENS_LONG_FORM: int = 65536
         TEMPERATURE_TEXT: float = 0.3
         TEMPERATURE_JSON: float = 0.2
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
   - Acceptance criteria:
     - `python -c "from utils.constants import Constants; print(sorted(Constants.Uploads.ALLOWED_EXTENSIONS))"`
       (run from `backend/`) prints all 10 extensions: `docx, heic, htm, html, jpeg, jpg,
       pdf, png, txt, webp`.
     - `Constants.Uploads.IMAGE_EXTENSIONS == frozenset({"png", "jpg", "jpeg", "webp", "heic"})`.
     - `Constants.Llm.IMAGE_OCR_PROMPT` contains the exact string `"NO_TEXT_FOUND"`.
     - No other test in `backend/tests/` that asserts the old 5-member
       `ALLOWED_EXTENSIONS` set breaks (grep `ALLOWED_EXTENSIONS` under `backend/tests/`
       first; if such a test exists, update it to expect the widened set as part of this
       task).

---

### Task 4 — Extract `_generate_content` and add `generate_text_from_image` (`backend/utils/llm.py`)

   - Files: `backend/utils/llm.py`
   - Changes: Per PRD §4.1. Add `Part` to the existing import, extract the shared body of
     `generate_text` into a private `_generate_content`, make `generate_text` a thin
     wrapper, and add the new multimodal method. `generate_json` is untouched (it still
     calls `self.generate_text(...)`).
     ```python
     # old import (llm.py:19-25)
     from vertexai.preview.generative_models import (
         FinishReason,
         GenerationConfig as VertexGenerationConfig,
         GenerativeModel,
         HarmBlockThreshold,
         HarmCategory,
     )
     ```
     ```python
     # new import
     from vertexai.preview.generative_models import (
         FinishReason,
         GenerationConfig as VertexGenerationConfig,
         GenerativeModel,
         HarmBlockThreshold,
         HarmCategory,
         Part,
     )
     ```
     Replace the body of `generate_text` (lines 60-114) with:
     ```python
     def _generate_content(self, contents, temperature: float, max_tokens: int) -> str:
         """Shared Vertex call + response handling for both text-only and
         multimodal (image + prompt) generation. `contents` is passed straight
         through to GenerativeModel.generate_content, which accepts a bare str
         or a list of [Part, str, ...]."""
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
             try:
                 from google.api_core import exceptions as _gexc
                 if isinstance(api_exc, _gexc.GoogleAPICallError):
                     raise VertexAPIError(api_exc) from api_exc
             except ImportError:
                 pass
             raise JunoError(
                 ErrorCode.UNKNOWN_ERROR,
                 detail=f"Vertex AI generate_content raised an unexpected error: {api_exc}",
                 original=api_exc,
             ) from api_exc

         if not response.candidates:
             raise JunoError(
                 ErrorCode.LLM_NO_CANDIDATES,
                 detail="Model response contained no candidates; generation may have been fully blocked.",
             )

         candidate = response.candidates[0]
         if hasattr(candidate, "finish_reason") and candidate.finish_reason == self._FinishReason.MAX_TOKENS:
             raise JunoError(
                 ErrorCode.LLM_MAX_TOKENS,
                 detail=(
                     f"LLM generation hit token limit before completing. "
                     f"Consider reducing prompt size or increasing max_tokens. "
                     f"finish_reason={candidate.finish_reason!r}"
                 ),
             )

         if not getattr(candidate, "content", None) or not getattr(candidate.content, "parts", None):
             finish_reason = getattr(candidate, "finish_reason", None)
             finish_reason_name = finish_reason.name if finish_reason is not None else "OTHER"
             error_code = classify_finish_reason(finish_reason_name)
             raise JunoError(
                 error_code,
                 detail=(
                     f"LLM response candidate has no content parts. "
                     f"finish_reason={finish_reason!r}"
                 ),
             )

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
     ```
   - Acceptance criteria:
     - `generate_json` is byte-for-byte unchanged (still calls `self.generate_text(...)`).
     - `_generate_content`'s body is identical in behavior to the old `generate_text` body
       (same exception classification, same `MAX_TOKENS`/no-candidates/no-content-parts
       checks, same `response.text.strip()` return).
     - `generate_text_from_image` calls `Part.from_data(data=image_bytes,
       mime_type=mime_type)` then `self._generate_content([part, prompt], ...)`.
     - `python -m py_compile backend/utils/llm.py` succeeds.

---

### Task 5 — Update `backend/tests/utils/test_llm.py` for the refactor and new method

   - Files: `backend/tests/utils/test_llm.py`
   - Changes:
     1. In the `vertex_env` fixture, add a `Part` mock to `mock_preview_models` (alongside
        the existing `GenerativeModel`/`HarmCategory`/etc. mocks) so
        `from vertexai.preview.generative_models import ..., Part` resolves under the
        mocked `sys.modules` patch:
        ```python
        mock_Part = MagicMock()
        mock_preview_models.Part = mock_Part
        ```
        Add `mock_Part` to the fixture's `yield` tuple (or expose it however the other
        mocks are exposed) so tests can configure `mock_Part.from_data.return_value`.
     2. Add regression test `test_generate_text_still_works_after_refactor` — copy the
        existing `test_generate_text_returns_stripped_text` body verbatim (proves the
        `_generate_content` extraction didn't change the text-only path).
     3. Add `test_generate_text_from_image_calls_generate_content_with_part_and_prompt`:
        set `mock_Part.from_data.return_value = "the-part-object"` (or a `MagicMock()`
        sentinel), set up `mock_model_instance.generate_content` to return a valid
        response (candidates present, `finish_reason` not `MAX_TOKENS`, `content.parts`
        non-empty, `text = "  extracted  "`), call
        `client.generate_text_from_image(b"imgbytes", "image/png", "prompt text")`, then
        assert:
        - `mock_Part.from_data.assert_called_once_with(data=b"imgbytes", mime_type="image/png")`
        - `mock_model_instance.generate_content.call_args[0][0] == ["the-part-object", "prompt text"]`
        - the returned value is `"extracted"` (stripped).
     4. Add `test_generate_text_from_image_shares_response_handling` — reuse the existing
        `test_generate_text_max_tokens_logs_warning` / `test_generate_text_no_candidates_raises`
        / `test_generate_text_vertex_failure_raises_vertex_api_error` scenarios but invoke
        `client.generate_text_from_image(b"x", "image/png", "p")` instead of
        `client.generate_text("test prompt")`; assert identical `ErrorCode`/exception-type
        outcomes for each of the three scenarios (parametrize or write as three separate
        test functions — match the existing file's style, which uses separate functions).
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_llm.py -v` passes, including the
       pre-existing tests (no regressions) and the ≥4 new/updated tests above.

---

### Task 6 — New module `backend/utils/image_ocr.py`

   - Files: `backend/utils/image_ocr.py` (new file)
   - Changes: Per PRD §4.3. One small module, mirroring `utils/pdf.py`'s /
     `utils/misc.py::extract_text_from_html`'s per-format-extractor convention.
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
         dispatcher in care_plan_input.py stays format-agnostic.
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
     `LLMClient()` is instantiated per call (matches the existing
     `care_plan/v1_2/pipeline.py` pattern — no shared client caching exists today).

     Do **not** add the optional downscale helper here — that is Task 7, kept separate so
     it can be dropped independently without touching this task's diff.
   - Acceptance criteria:
     - `python -c "from utils.image_ocr import extract_text_from_image, IMAGE_EXT_TO_MIME"`
       (run from `backend/`) exits 0.
     - `set(IMAGE_EXT_TO_MIME) == {"png", "jpg", "jpeg", "webp", "heic"}`.
     - Calling `extract_text_from_image` with an `ext` not in `IMAGE_EXT_TO_MIME` raises
       `JunoError` with `ErrorCode.UNSUPPORTED_FILE_TYPE` before any `LLMClient` is
       constructed.

---

### Task 7 (OPTIONAL — may be dropped) — Backend image downscale in `image_ocr.py` (§9 Q3)

   Per PRD §9 Q3, this is explicitly optional: "if it turns out to add real complexity...
   the implementing agent has permission to drop it entirely." Implement it only if it
   stays this cheap; do not spend more than one short pass on it. If dropped, skip this
   task and do not add its associated test in Task 8.

   - Files: `backend/utils/image_ocr.py`
   - Changes: Add a best-effort resize helper and call it from `extract_text_from_image`
     before the Vertex call:
     ```python
     import io
     import PIL.Image

     _MAX_LONG_EDGE_PX = 2048

     def _maybe_downscale(image_bytes: bytes, ext: str) -> bytes:
         """Resize an image to a max long-edge dimension before sending to Vertex.
         Best-effort: on any decode error, returns the original bytes unchanged."""
         try:
             image = PIL.Image.open(io.BytesIO(image_bytes))
             if max(image.size) <= _MAX_LONG_EDGE_PX:
                 return image_bytes
             image.thumbnail((_MAX_LONG_EDGE_PX, _MAX_LONG_EDGE_PX))
             buf = io.BytesIO()
             image.save(buf, format=image.format or "JPEG")
             return buf.getvalue()
         except Exception:
             return image_bytes
     ```
     In `extract_text_from_image`, after the `mime_type` lookup and before constructing
     `LLMClient()`, add: `image_bytes = _maybe_downscale(image_bytes, ext)`.
   - Acceptance criteria (only if implemented):
     - An image already under 2048px on its long edge is returned byte-identical from
       `_maybe_downscale`.
     - A corrupted/non-image byte string passed to `_maybe_downscale` returns the original
       bytes unchanged (no exception propagates).
     - `extract_text_from_image` still passes all Task 8 tests with this call wired in.

---

### Task 8 — New test file `backend/tests/utils/test_image_ocr.py`

   - Files: `backend/tests/utils/test_image_ocr.py` (new file)
   - Changes: Per PRD §7. Mock `utils.image_ocr.LLMClient` (patch the class, configure
     `generate_text_from_image` on the mock instance) — no real Vertex/network calls.
     - `test_extract_text_from_image_returns_model_text` — mock
       `LLMClient().generate_text_from_image` to return `"Patient note text"`; assert
       `extract_text_from_image(b"bytes", "png")` returns `"Patient note text"` unchanged.
     - `test_extract_text_from_image_no_text_sentinel_raises_empty_document` — mock the
       client to return `"NO_TEXT_FOUND"`; assert `JunoError` with
       `ErrorCode.EMPTY_DOCUMENT`.
     - `test_extract_text_from_image_unknown_extension_raises_unsupported_file_type` — call
       `extract_text_from_image(b"bytes", "gif")` (not in `IMAGE_EXT_TO_MIME`); assert
       `JunoError` with `ErrorCode.UNSUPPORTED_FILE_TYPE`, and that `LLMClient` was never
       instantiated (patch it and assert `mock_llm_client.assert_not_called()`).
     - `test_image_ext_to_mime_covers_all_image_extensions` — assert
       `set(IMAGE_EXT_TO_MIME) == Constants.Uploads.IMAGE_EXTENSIONS` (imports
       `Constants` from `utils.constants`) — regression guard against the two sets
       silently drifting apart.
     - If Task 7 was implemented, also add
       `test_extract_text_from_image_downscales_before_sending` — mock
       `_maybe_downscale` and assert it is called with the original `image_bytes`/`ext`
       before `generate_text_from_image` is invoked. If Task 7 was dropped, skip this test.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_image_ocr.py -v` passes, all 4 (or
       5) tests green.

---

### Task 9 — `backend/utils/pdf.py`: HEIC registration, `_image_to_pdf`, `merge_pdfs` wiring

   - Files: `backend/utils/pdf.py`
   - Changes: Per PRD §4.6. Depends on Task 2's verification having passed (pillow-heif
     decodes on the deploy target, with or without the `libheif1` Dockerfile fallback).
     1. Add imports at the top: `from utils.constants import Constants` and register the
        HEIF opener at import time:
        ```python
        import pillow_heif
        pillow_heif.register_heif_opener()
        ```
     2. Add `_image_to_pdf`:
        ```python
        def _image_to_pdf(file_bytes: bytes, filename: str) -> bytes:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
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
     3. In `merge_pdfs`'s per-file dispatch (currently lines 78-88), add one `elif` branch
        before the final `else`:
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
        elif ext in Constants.Uploads.IMAGE_EXTENSIONS:
            merged_pages += _append_pdf(writer, _image_to_pdf(file_bytes, filename), filename)
        else:
            logger.warning("pdf_merge: skipping unsupported file %s", filename)
        ```
        (The surrounding per-file `try/except Exception: logger.exception(...)` block is
        unchanged and now also covers `_image_to_pdf` decode failures.)
   - Acceptance criteria:
     - `python -m py_compile backend/utils/pdf.py` succeeds.
     - `import utils.pdf` does not raise even if `pillow_heif` is missing from the
       environment at runtime in a way that breaks other formats (i.e., the
       `register_heif_opener()` call itself must not be wrapped in a way that silently
       swallows real import errors — if `pillow-heif` is a hard requirement per Task 1,
       a missing package should surface as an `ImportError` at import time, matching the
       existing hard-dependency pattern for `reportlab`/`pypdf` in this file).
     - `merge_pdfs` still raises `ValueError("No mergeable PDF pages found")` when given
       only genuinely undecodable bytes (see Task 10's regression check).

---

### Task 10 — Extend `backend/tests/utils/test_pdf.py` with image coverage

   - Files: `backend/tests/utils/test_pdf.py`
   - Changes: Per PRD §7.
     - `test_image_to_pdf_produces_one_page` — build a tiny in-memory PNG via
       `PIL.Image.new("RGB", (100, 100), color="white")` saved to a `BytesIO`; call
       `_image_to_pdf(png_bytes, "photo.png")`; assert `PdfReader(io.BytesIO(result))` has
       exactly 1 page.
     - `test_image_to_pdf_respects_exif_rotation` — construct a Pillow image, set an EXIF
       orientation tag (e.g. via `img.getexif()[0x0112] = 6` before saving, or use
       `piexif`/manual EXIF bytes if simpler — whatever the test author finds cleanest with
       Pillow's own EXIF-writing API), save with that EXIF block, run it through
       `_image_to_pdf`, and assert the resulting page's drawn-image aspect ratio matches
       the *corrected* (post-`exif_transpose`) orientation rather than the raw stored
       orientation (e.g. compare width/height ratio of the source image `img.size` after
       `ImageOps.exif_transpose` against a rendered check, or at minimum assert
       `ImageOps.exif_transpose` was invoked via a `mock.patch` spy if a pixel-level
       assertion proves too fragile).
     - `test_merge_pdfs_embeds_image_alongside_pdf_and_txt` — call `merge_pdfs` with a
       1-page PDF (`_one_page_pdf`), a `.txt` entry, and a tiny real PNG's bytes (3
       entries); assert `PdfReader(io.BytesIO(merged)).pages` has exactly 3 pages.
     - `test_merge_pdfs_handles_heic_via_pillow_heif` — guard with
       `@pytest.mark.skipif` on a successful `import pillow_heif` check (per PRD §7: "if
       this proves environment-fragile in CI... mark it skipif"). If a real tiny `.heic`
       fixture is available, feed it through `merge_pdfs`/`_image_to_pdf` and assert 1
       page is produced; if not, skip this test with a clear reason string rather than
       fabricating fixture bytes that may not be valid HEIC.
     - **Regression check (must not skip):** re-run the existing
       `test_merge_pdfs_raises_when_no_pages_are_mergeable` test (which merges
       `(b"not supported", "image.png")`) after Task 9's change and confirm it **still
       passes** — `.png` is now a *recognized* extension routed through
       `_image_to_pdf`, but `b"not supported"` is not decodable image data, so
       `_image_to_pdf` raises inside `merge_pdfs`'s existing per-file
       `try/except Exception: logger.exception(...)` block, the file is still skipped,
       `merged_pages` stays 0, and `ValueError` is still raised — same observable
       behavior via a different code path. No edit to that test should be needed; if it
       fails, that is a signal `_image_to_pdf` or the dispatch branch has a bug, not that
       the test needs relaxing.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_pdf.py -v` passes, including the
       pre-existing `test_merge_pdfs_raises_when_no_pages_are_mergeable` unmodified and
       green, plus the new tests (the HEIC test may report `skipped`, not `failed`, if
       `pillow_heif` genuinely can't be validated in this environment).

---

### Task 11 — `backend/services/care_plan_input.py`: dispatch and merge-candidate wiring

   - Files: `backend/services/care_plan_input.py`
   - Changes: Per PRD §4.4 and §4.6. Two edits in this file.
     1. Add the import: `from utils.image_ocr import extract_text_from_image`
     2. In `extract_text_from_bytes`, add one `elif` branch before the final `raise`:
        ```python
        # old (end of function)
        if ext in {"html", "htm"}:
            return extract_text_from_html(file_bytes)

        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")
        ```
        ```python
        # new
        if ext in {"html", "htm"}:
            return extract_text_from_html(file_bytes)

        if ext in Constants.Uploads.IMAGE_EXTENSIONS:
            return extract_text_from_image(file_bytes, ext)

        raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")
        ```
        Also update the function's docstring from `"""Extract plain text from PDF, TXT,
        DOCX, or HTML bytes."""` to `"""Extract plain text from PDF, TXT, DOCX, HTML, or
        image bytes."""`.
     3. In `resolve_uploaded_files`, widen the raw-bytes merge-candidate branch:
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
        if ext in {"pdf", "txt"} or ext in Constants.Uploads.IMAGE_EXTENSIONS:
            merge_candidates.append((file_bytes, filename))
        elif ext in {"docx", "html", "htm"} and extracted_text.strip():
            merge_candidates.append(
                (extracted_text.encode("utf-8"), text_artifact_filename(filename))
            )
        ```
        This is deliberately unconditional (no `extracted_text.strip()` guard for
        images) — if `extract_text_from_image` raised `EMPTY_DOCUMENT` for a given file,
        the `for upload in files:` loop already exited via that exception before reaching
        this line, so this branch never sees a "failed OCR" image (PRD §4.6).
     4. Also update the error message raised at line 97
        (`raise ValueError("File must be PDF, TXT, DOCX, or HTML")`) to mention images,
        for consistency with Task 13's `care_plan_jobs.py` change:
        ```python
        raise ValueError("File must be PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC)")
        ```
   - Acceptance criteria:
     - `extract_text_from_bytes(some_png_bytes, "photo.png")` calls
       `utils.image_ocr.extract_text_from_image` (verify via Task 12's mock-based test)
       and returns its result.
     - `resolve_uploaded_files` places image files' **raw original bytes** (not their
       OCR'd text) into `merge_candidates`.
     - `is_allowed_extension` needs no code change (already checks membership in the
       now-widened `Constants.Uploads.ALLOWED_EXTENSIONS`) — confirm no edit was made to
       that function.

---

### Task 12 — Extend `backend/tests/services/test_care_plan_input.py`

   - Files: `backend/tests/services/test_care_plan_input.py`
   - Changes: Per PRD §7.
     - `test_extract_text_from_bytes_dispatches_image_extensions_to_ocr` — patch
       `services.care_plan_input.extract_text_from_image` (the name imported into
       `care_plan_input`'s module namespace, not `utils.image_ocr`'s), configure it to
       return `"ocr text"`, call `extract_text_from_bytes(b"bytes", "photo.png")`, assert
       it was called with `(b"bytes", "png")` and the function returns `"ocr text"`.
     - `test_is_allowed_extension_accepts_all_image_extensions` — parametrize over
       `png/jpg/jpeg/webp/heic`, assert `is_allowed_extension(f"x.{ext}")` is `True` for
       each.
     - `test_resolve_uploaded_files_image_becomes_raw_merge_candidate` — build a fake
       upload object (matching whatever minimal interface `resolve_uploaded_files` expects
       — `.filename` and `.read()`; check the existing test file or `care_plan_jobs.py`
       route tests for the exact fake-upload shape already used elsewhere in this repo,
       and reuse it) wrapping a real tiny PNG's bytes (a 1x1 PNG literal is fine — no
       network), patch `services.care_plan_input.extract_text_from_image` to return known
       text, call `resolve_uploaded_files([fake_upload])`, and assert:
       - the returned `ResolvedInput.text` contains the known OCR'd text
       - the returned `combined_pdf_bytes` is not `None` (the real PNG bytes flow through
         the real `merge_pdfs` → `_image_to_pdf` path, producing an actual 1-page PDF —
         no need to mock `merge_pdfs` itself since Task 9 already covers that path
         directly).
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/services/test_care_plan_input.py -v` passes,
       including the 3 pre-existing dotless-filename tests unmodified, plus the 3 new
       tests above.

---

### Task 13 — Cosmetic error-string update in `backend/routes/care_plan_jobs.py`

   - Files: `backend/routes/care_plan_jobs.py`
   - Changes: Per PRD §4.8. Validation logic itself needs no change (already driven by
     the now-widened `Constants.Uploads.ALLOWED_EXTENSIONS` via `is_allowed_extension`) —
     this is a one-line message update only, at line 80:
     ```python
     # old
     raise ValueError("Stored file must be PDF, TXT, or DOCX")
     ```
     ```python
     # new
     raise ValueError("Stored file must be PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC)")
     ```
   - Acceptance criteria:
     - The `doc_id` re-processing path's error message mentions images.
     - No other line in `care_plan_jobs.py` changes (the actual acceptance/rejection
       behavior is unchanged — this is text only).

---

### Task 14 — Extend `backend/tests/routes/test_care_plan_jobs.py`

   - Files: `backend/tests/routes/test_care_plan_jobs.py`
   - Changes: Add `test_create_care_plan_job_accepts_image_upload`, following the existing
     `test_post_text_returns_202_and_job_id` pattern (same `@patch.dict` env vars, same
     `@patch("routes.care_plan_jobs.enqueue_job_safe", ...)` /
     `@patch("routes.care_plan_jobs.create_job_doc")` decorators, same `client_jobs` /
     `auth_ok` fixtures). Also patch
     `services.care_plan_input.extract_text_from_image` (or
     `routes.care_plan_jobs.extract_text_from_bytes` at whichever import boundary is
     cleanest — prefer patching `extract_text_from_image` so the real dispatch/merge code
     in `care_plan_input.py` still runs) to avoid any real Vertex call, returning fixed
     text. POST a real tiny PNG's bytes as a multipart `files` field:
     ```python
     resp = client_jobs.post(
         "/care_plan/jobs",
         data={"files": (io.BytesIO(<tiny_png_bytes>), "photo.png")},
         content_type="multipart/form-data",
         headers=auth_ok,
     )
     assert resp.status_code == 202
     ```
     Assert the response is `202` (not the old `400 INPUT_VALIDATION_ERROR` a `.png`
     upload would have produced before this SP).
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/routes/test_care_plan_jobs.py -v` passes,
       including all pre-existing tests plus the new image-upload test.

---

### Task 15 — Live smoke test against the deployed Vertex model (§9 Q2)

   PRD §9 Q2 requires this as an explicit pre-"done" gate, not just a design assumption:
   "Implementation should still do a live smoke test against a real HEIC file through the
   actual deployed model before considering this SP done, so the fallback path is
   exercised for real if the assumption turns out wrong." Do this after Tasks 3–12 are
   merged (real code path must exist end-to-end) and with real Vertex AI credentials
   available (this machine has GCP access per its standing configuration).

   - Files: none required if the assumption holds. If it does not hold, add the fallback
     to `backend/utils/image_ocr.py` described below.
   - Changes / steps:
     1. Obtain (or synthesize, e.g. by converting a JPEG to HEIC with a tool that produces
        a real, valid HEIC file) one small real `.heic` image containing legible printed
        text.
     2. With real `GCP_PROJECT_ID`/`GCP_LOCATION` env vars and real Vertex AI credentials
        configured (same as any other manual Vertex-hitting script in this repo), run:
        ```python
        from utils.image_ocr import extract_text_from_image
        with open("test.heic", "rb") as f:
            print(extract_text_from_image(f.read(), "heic"))
        ```
        against both models named in `deploy.yml` (`gemini-1.5-pro` default and whatever
        production model `deploy.yml` sets, e.g. `gemini-3.5-flash`) by setting
        `VERTEX_AI_MODEL` accordingly before each run.
     3. **If both calls succeed** (return transcribed text, no exception): the PRD's
        assumption holds — no code change needed. Record the confirmation (e.g. in the
        PR description) so this isn't silently re-litigated later.
     4. **If Vertex rejects `mime_type="image/heic"`** (a `GoogleAPICallError`/400-class
        error referencing the MIME type): implement the documented fallback in
        `backend/utils/image_ocr.py` — decode via the same `pillow-heif`-registered
        `PIL.Image.open()` used in `utils/pdf.py`, re-encode to JPEG in-memory, and retry
        once with `mime_type="image/jpeg"`:
        ```python
        def extract_text_from_image(image_bytes: bytes, ext: str) -> str:
            mime_type = IMAGE_EXT_TO_MIME.get(ext)
            if mime_type is None:
                raise JunoError(ErrorCode.UNSUPPORTED_FILE_TYPE, detail=f"extension: {ext}")

            client = LLMClient()
            try:
                text = client.generate_text_from_image(
                    image_bytes=image_bytes, mime_type=mime_type,
                    prompt=Constants.Llm.IMAGE_OCR_PROMPT,
                    temperature=Constants.Llm.TEMPERATURE_TEXT,
                    max_tokens=Constants.Llm.MAX_TOKENS,
                )
            except VertexAPIError:
                if ext != "heic":
                    raise
                # Fallback: Vertex rejected image/heic inline data — re-encode to JPEG.
                import io
                import pillow_heif
                pillow_heif.register_heif_opener()
                from PIL import Image
                img = Image.open(io.BytesIO(image_bytes))
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG")
                text = client.generate_text_from_image(
                    image_bytes=buf.getvalue(), mime_type="image/jpeg",
                    prompt=Constants.Llm.IMAGE_OCR_PROMPT,
                    temperature=Constants.Llm.TEMPERATURE_TEXT,
                    max_tokens=Constants.Llm.MAX_TOKENS,
                )
            if text.strip().upper() == _NO_TEXT_SENTINEL:
                raise JunoError(ErrorCode.EMPTY_DOCUMENT, detail="...")
            return text
        ```
        then re-run step 2 to confirm the fallback actually produces correct text, and add
        a corresponding unit test to `backend/tests/utils/test_image_ocr.py`
        (`test_extract_text_from_image_heic_falls_back_to_jpeg_on_vertex_rejection`) mocking
        `generate_text_from_image` to raise `VertexAPIError` on the first (HEIC) call and
        succeed on the second (JPEG) call.
   - Acceptance criteria:
     - A real run against both deployed models is confirmed (pass, or pass-with-fallback)
       and recorded — this task cannot be marked done from unit tests alone.
     - If the fallback was needed, `backend/tests/utils/test_image_ocr.py` covers it and
       `cd backend && python -m pytest tests/utils/test_image_ocr.py -v` still passes.

---

### Task 16 — `frontend/src/constants.ts`: add `ALLOWED_UPLOAD_EXTENSIONS`

   - Files: `frontend/src/constants.ts`
   - Changes: Per PRD §6 / §9 Q4. Add one new export alongside the existing
     `DEFAULT_VERSION` etc.:
     ```ts
     export const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic'];
     ```
   - Acceptance criteria:
     - `ALLOWED_UPLOAD_EXTENSIONS` is exported from `frontend/src/constants.ts` and
       contains exactly these 10 lowercase extension strings, in an order matching the
       PRD (order doesn't affect behavior but keep it consistent for diff-review clarity).

---

### Task 17 — `frontend/src/pages/care-plan/CarePlanPage.tsx`: accept images

   - Files: `frontend/src/pages/care-plan/CarePlanPage.tsx`
   - Changes: Per PRD §6. Three edits, depends on Task 16.
     1. Add the import: `import { ALLOWED_UPLOAD_EXTENSIONS } from '../../constants';`
        (verify the exact relative path from this file to `src/constants.ts` — adjust if
        the file's actual nesting depth differs from the PRD's `../../constants`).
     2. Update `handleFiles` (currently lines 53-64):
        ```tsx
        // old
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
     3. Update the file input's `accept` attribute (line 186):
        ```tsx
        // old
        accept=".pdf,.txt,.docx,.html,.htm"
        ```
        ```tsx
        // new
        accept=".pdf,.txt,.docx,.html,.htm,.png,.jpg,.jpeg,.webp,.heic"
        ```
     4. Update the upload-hint copy (line 202):
        ```tsx
        // old
        <p className="upload-hint">PDF, TXT, DOCX, or HTML · Multiple files = one combined process</p>
        ```
        ```tsx
        // new
        <p className="upload-hint">PDF, TXT, DOCX, HTML, or image (PNG/JPG/WEBP/HEIC) · Multiple files = one combined process</p>
        ```
   - Acceptance criteria:
     - Selecting a `.png`/`.jpg`/`.jpeg`/`.webp`/`.heic` file in the browser no longer
       triggers the "Unsupported file type" error.
     - `grep -n "pdf.*txt.*docx" frontend/src/pages/care-plan/CarePlanPage.tsx` shows no
       remaining hardcoded 5-extension array (confirms `ALLOWED_UPLOAD_EXTENSIONS` is
       actually being used, not left alongside a stale inline list).
     - `cd frontend && npm run build` (or the project's standard type-check/build command)
       succeeds with no new TypeScript errors.
     - No new test file is required (per PRD §7, this file has no existing test coverage
       and this SP does not introduce one — optional follow-up only, not required here).

---

### Task 18 — Run the full backend test suite and fix any regressions

   - Files: any file that fails — diagnose before editing; do not touch files outside
     this SP's scope (Tasks 1–15's files) without a clear regression reason.
   - Changes / steps:
     1. `cd backend && python -m pytest --tb=short -q`
     2. For every failure, identify whether it's a regression introduced by this SP
        (most likely: a test elsewhere in the suite hardcodes the old 5-member
        `ALLOWED_EXTENSIONS` set, the old `generate_text` internals, or the old
        `merge_pdfs` "always skip non-pdf/txt" behavior) and fix with a minimal targeted
        edit.
     3. Re-run until green.
   - Acceptance criteria:
     - `cd backend && python -m pytest --tb=short -q` exits 0.
     - `cd backend && python -c "from utils.image_ocr import extract_text_from_image; from services.care_plan_input import extract_text_from_bytes; from utils.pdf import _image_to_pdf; print('ok')"`
       succeeds.
     - No test file outside the ones listed in Tasks 5, 8, 10, 12, 14, and 15 was modified
       (confirm via `git diff --stat` before committing).

---

## Summary of what requires you (not a dev agent)

1. **Review Task 2's HEIC/Docker build-verification output.** The implementing agent can
   run the `docker build` + decode check directly (this machine has Docker/GCP access per
   its standing config), but if the `libheif1` apt fallback is triggered, take note that
   `backend/Dockerfile` changed — a one-line, low-risk addition, not something that needs
   your sign-off before merge, but worth a glance in the diff.
2. **Task 15's live smoke test needs a real `.heic` file and real Vertex credentials.**
   The implementing agent has GCP access on this machine and can run it directly and
   record the pass/fail result; you do not need to personally obtain the HEIC file or run
   the script, but if no `.heic` test image is readily available in the environment, you
   may need to supply one (e.g. from a phone) or confirm it's acceptable to synthesize one
   via a conversion tool.
3. **No other manual/owner-only step exists in this PRD.** PRD §8 explicitly states "None
   required to land this SP's code" beyond the two items above (build verification and
   cost awareness, the latter being informational only — every image upload adds one
   Vertex vision call per image on top of the existing 5 text-generation calls per
   pipeline run; no budget/quota action requested).
4. **Task 7 (backend downscale) is optional** — if the implementing agent drops it, no
   action needed from you; it was pre-approved as droppable in the PRD itself (§9 Q3).
