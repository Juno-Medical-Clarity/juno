# Tasks: HTML File Support (01-html-file-support)

Read `PRD.md` in this folder first. This sub-project is **standalone** — no sibling sub-projects, no
cross-branch dependencies. All 7 tasks are backend + frontend input-handling changes only. The LLM
pipeline, grading, and GCS artifact format are untouched.

All §9 open questions are [RESOLVED]. No blocking items.

---

### Task 1 — Add `beautifulsoup4` to `backend/requirements.txt`

- **Files:** `backend/requirements.txt`
- **Changes:**
  Insert one line after `python-docx` (currently line 16):
  ```
  # Before
  python-docx
  textstat

  # After
  python-docx
  beautifulsoup4
  textstat
  ```
  No other changes to this file. Do not pin a version — match the unpinned style of `python-docx`
  and `textstat` already in the file.

- **Acceptance criteria:**
  - `grep -n 'beautifulsoup4' backend/requirements.txt` returns exactly one line, positioned between
    `python-docx` and `textstat`.
  - `pip install -r backend/requirements.txt` completes without error (no native extensions needed;
    `beautifulsoup4` ships a pure-Python `html.parser`).

---

### Task 2 — Extend `ALLOWED_EXTENSIONS` in `backend/utils/constants.py`

- **Files:** `backend/utils/constants.py`
- **Changes:**
  Line 17: expand the frozenset to include `"html"` and `"htm"`:
  ```python
  # Before
  ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx"})

  # After
  ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
  ```
  This is the single source of truth consumed by `_allowed()` in `care_plan.py` (line 100).
  No other file references `ALLOWED_EXTENSIONS` and needs updating.

- **Acceptance criteria:**
  - `python -c "from utils.constants import Constants; assert 'html' in Constants.ALLOWED_EXTENSIONS; assert 'htm' in Constants.ALLOWED_EXTENSIONS"` exits 0.
  - `frozenset` still contains `"pdf"`, `"txt"`, and `"docx"` — no existing extensions removed.

---

### Task 3 — Create `backend/utils/html.py`

_Depends on Task 1 (beautifulsoup4 must be installed)._

- **Files:** `backend/utils/html.py` *(new file)*
- **Changes:**
  Create this file from scratch. Mirror the structure of `backend/utils/pdf.py`: module-level
  docstring, `from __future__ import annotations`, `logging`, one public function.

  Full content:
  ```python
  """Utilities for HTML text extraction."""

  from __future__ import annotations

  import logging

  logger = logging.getLogger(__name__)


  def extract_text_from_html(html_content: bytes) -> str:
      """Extract plain text from HTML bytes.

      Strategy:
      1. Parse with BeautifulSoup using stdlib html.parser (no lxml needed).
      2. Decompose all <script> and <style> tags and their contents.
      3. Target the <body> element if present; fall back to the full document.
      4. Call .get_text(separator="\\n", strip=True) to produce readable text.
      """
      try:
          from bs4 import BeautifulSoup
      except ImportError as exc:
          raise RuntimeError(
              "beautifulsoup4 is not installed. Add 'beautifulsoup4' to requirements.txt."
          ) from exc

      soup = BeautifulSoup(html_content, "html.parser")

      # Remove non-content tags entirely (including their inner text).
      for tag in soup.find_all(["script", "style"]):
          tag.decompose()

      # Prefer the <body> element; fall back to the full document.
      target = soup.body if soup.body else soup

      text = target.get_text(separator="\n", strip=True)
      logger.info("html_extract: %d chars extracted", len(text))
      return text
  ```

  Design notes (do not change):
  - `tag.decompose()` removes the tag **and** all children — script/style text never bleeds into output.
  - `separator="\n"` preserves paragraph structure without tag-specific handling.
  - `strip=True` trims per-node whitespace — avoids large blank-line blocks from indented HTML.
  - The `ImportError` guard mirrors the `python-docx` guard in `_extract_text_from_bytes`.

- **Acceptance criteria:**
  - File exists at `backend/utils/html.py`.
  - `python -c "from utils.html import extract_text_from_html; print(extract_text_from_html(b'<html><body><p>hello</p></body></html>'))"` prints `hello`.
  - `python -c "from utils.html import extract_text_from_html; r = extract_text_from_html(b'<p>V</p><script>secret=1</script>'); assert 'secret' not in r"` exits 0.

---

### Task 4 — Add HTML/HTM branch in `_extract_text_from_bytes`

_Depends on Task 3 (utils/html.py must exist)._

- **Files:** `backend/routes/care_plan.py`
- **Changes:**
  In `_extract_text_from_bytes` (starts at line 103), add a fourth `if` branch for `html`/`htm`
  **before** the final `raise ValueError`. Insert after the `docx` block (currently ends at line 122):

  ```python
  # Before (lines 103–124)
  def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
      """Extract plain text from PDF, TXT, or DOCX bytes."""
      ext = filename.rsplit(".", 1)[1].lower()

      if ext == "txt":
          return file_bytes.decode("utf-8", errors="replace")

      if ext == "pdf":
          return extract_text_from_pdf(file_bytes)

      if ext == "docx":
          try:
              from docx import Document
          except ImportError as exc:
              raise RuntimeError(
                  "python-docx is not installed. Add 'python-docx' to requirements.txt."
              ) from exc

          doc = Document(io.BytesIO(file_bytes))
          return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

      raise ValueError(f"Unsupported file extension: {ext}")


  # After
  def _extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
      """Extract plain text from PDF, TXT, DOCX, or HTML bytes."""
      ext = filename.rsplit(".", 1)[1].lower()

      if ext == "txt":
          return file_bytes.decode("utf-8", errors="replace")

      if ext == "pdf":
          return extract_text_from_pdf(file_bytes)

      if ext == "docx":
          try:
              from docx import Document
          except ImportError as exc:
              raise RuntimeError(
                  "python-docx is not installed. Add 'python-docx' to requirements.txt."
              ) from exc

          doc = Document(io.BytesIO(file_bytes))
          return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

      if ext in {"html", "htm"}:
          from utils.html import extract_text_from_html
          return extract_text_from_html(file_bytes)

      raise ValueError(f"Unsupported file extension: {ext}")
  ```

  The import of `extract_text_from_html` is intentionally deferred (inside the `if` block),
  consistent with the `docx` branch. No change to top-level imports is needed.
  Also update the docstring from `"PDF, TXT, or DOCX"` to `"PDF, TXT, DOCX, or HTML"`.

- **Acceptance criteria:**
  - Calling `_extract_text_from_bytes(b"<p>hi</p>", "note.html")` returns a string containing `"hi"`.
  - Calling `_extract_text_from_bytes(b"<p>hi</p>", "note.htm")` also returns a string containing `"hi"`.
  - Calling `_extract_text_from_bytes(b"irrelevant", "note.png")` still raises `ValueError`.
  - The `docx` branch behaviour is unchanged.

---

### Task 5 — Update error message and merge candidates in `_resolve_uploaded_files`

_Depends on Task 2 (ALLOWED_EXTENSIONS already extended). No dependency on Tasks 3–4._

- **Files:** `backend/routes/care_plan.py`
- **Changes:**
  Two targeted edits inside `_resolve_uploaded_files` (lines 136–191):

  **Change 1 — error message** (line 151):
  ```python
  # Before
  raise ValueError("File must be PDF, TXT, or DOCX")

  # After
  raise ValueError("File must be PDF, TXT, DOCX, or HTML")
  ```

  **Change 2 — merge candidates `elif` condition** (line 168):
  ```python
  # Before
  elif ext == "docx" and extracted_text.strip():

  # After
  elif ext in {"docx", "html", "htm"} and extracted_text.strip():
  ```

  The rest of the merge candidates block (lines 169–171) is unchanged:
  ```python
  merge_candidates.append(
      (extracted_text.encode("utf-8"), _text_artifact_filename(filename))
  )
  ```
  `_text_artifact_filename` already strips the original extension and appends `.txt`, so
  `report.html` becomes `report.txt` in the merged PDF. No further changes needed.

- **Acceptance criteria:**
  - Uploading a file with an unsupported extension triggers: `"File must be PDF, TXT, DOCX, or HTML"`.
  - An `.html` file with non-empty extracted text appears in `merge_candidates` as
    `(utf8_bytes, "stem.txt")`, exactly as a `.docx` file does today.
  - An `.html` file whose extracted text is empty/whitespace is **not** added to `merge_candidates`
    (the `and extracted_text.strip()` guard applies equally).
  - The `.pdf` and `.txt` direct-bytes path is unchanged.

---

### Task 6 — Update frontend validation, error message, file input, and hint text

_No backend dependency. Standalone frontend change._

- **Files:** `frontend/src/pages/care-plan/CarePlanPage.tsx`
- **Changes:**
  Four targeted string/array literal edits. No logic changes.

  **Change 1 — validation allowlist** (line 53):
  ```tsx
  // Before
  return !['pdf', 'txt', 'docx'].includes(ext ?? '');

  // After
  return !['pdf', 'txt', 'docx', 'html', 'htm'].includes(ext ?? '');
  ```

  **Change 2 — error message** (line 56):
  ```tsx
  // Before
  setError(`Unsupported file type: ${invalid.map(f => f.name).join(', ')}. Use PDF, TXT, or DOCX.`);

  // After
  setError(`Unsupported file type: ${invalid.map(f => f.name).join(', ')}. Use PDF, TXT, DOCX, or HTML.`);
  ```

  **Change 3 — file input `accept` attribute** (line 164):
  ```tsx
  // Before
  <input type="file" accept=".pdf,.txt,.docx" multiple

  // After
  <input type="file" accept=".pdf,.txt,.docx,.html,.htm" multiple
  ```

  **Change 4 — hint text** (line 180):
  ```tsx
  // Before
  <p className="upload-hint">PDF, TXT, or DOCX · Multiple files = one combined process</p>

  // After
  <p className="upload-hint">PDF, TXT, DOCX, or HTML · Multiple files = one combined process</p>
  ```

- **Acceptance criteria:**
  - Dragging an `.html` file onto the upload zone passes `handleFiles` validation (no error set).
  - Dragging an `.htm` file onto the upload zone also passes validation.
  - Dragging a `.png` file triggers the error message containing `"Use PDF, TXT, DOCX, or HTML."`.
  - The `<input>` element's `accept` attribute includes `.html` and `.htm` (visible in browser DevTools).
  - The hint text below the upload zone reads `"PDF, TXT, DOCX, or HTML · Multiple files = one combined process"`.
  - TypeScript compiles with no errors (`tsc --noEmit` passes).

---

### Task 7 — Create unit test file `backend/tests/utils/test_html.py`

_Depends on Task 3 (utils/html.py must exist) and Task 1 (beautifulsoup4 installed)._

- **Files:** `backend/tests/utils/test_html.py` *(new file)*
- **Changes:**
  Create this file from scratch. Mirror the structure of `backend/tests/utils/test_pdf.py`:
  module-level helper(s) followed by individual `test_*` functions, each with a docstring.
  All imports from `utils.html` are deferred (inside each test function), matching `test_pdf.py` style.

  Full content:
  ```python
  def _html(body: str, *, with_body_tag: bool = True) -> bytes:
      if with_body_tag:
          return f"<html><body>{body}</body></html>".encode()
      return f"<html>{body}</html>".encode()


  def test_extract_text_returns_visible_text():
      """Basic content in a paragraph is included in output."""
      from utils.html import extract_text_from_html
      html = _html("<p>Hello patient</p>")
      result = extract_text_from_html(html)
      assert "Hello patient" in result


  def test_extract_text_strips_script_tags():
      """Content inside <script> is NOT included in output."""
      from utils.html import extract_text_from_html
      html = _html("<p>Visible</p><script>var secret = 1;</script>")
      result = extract_text_from_html(html)
      assert "secret" not in result
      assert "Visible" in result


  def test_extract_text_strips_style_tags():
      """Content inside <style> is NOT included in output."""
      from utils.html import extract_text_from_html
      html = _html("<style>body { color: red; }</style><p>Styled text</p>")
      result = extract_text_from_html(html)
      assert "color" not in result
      assert "Styled text" in result


  def test_extract_text_without_body_tag():
      """Falls back to full document when no <body> element exists."""
      from utils.html import extract_text_from_html
      html = b"<p>No body wrapper</p>"
      result = extract_text_from_html(html)
      assert "No body wrapper" in result


  def test_extract_text_returns_string():
      """Return type is always str, even for empty input."""
      from utils.html import extract_text_from_html
      result = extract_text_from_html(b"<html></html>")
      assert isinstance(result, str)


  def test_extract_text_empty_document_returns_empty_string():
      """An empty or whitespace-only document returns an empty or near-empty string."""
      from utils.html import extract_text_from_html
      result = extract_text_from_html(b"<html><body>   </body></html>")
      assert result.strip() == ""


  def test_extract_text_multiline_content():
      """Multiple paragraphs produce multi-line output with content preserved."""
      from utils.html import extract_text_from_html
      html = _html("<p>Take this medication daily.</p><p>Follow up in 2 weeks.</p>")
      result = extract_text_from_html(html)
      assert "Take this medication daily." in result
      assert "Follow up in 2 weeks." in result
  ```

- **Acceptance criteria:**
  - `pytest backend/tests/utils/test_html.py -v` passes all 7 tests with zero failures.
  - No test imports `pytest` or any fixture — all assertions use plain `assert` (matching
    `test_pdf.py` convention for this module).
  - The file does NOT import from `utils.pdf`, `routes`, or any other module.

---

## Summary of what requires you (not a dev agent)

PRD §8 states: **None.** All changes are in tracked source files. The `beautifulsoup4` dependency
is picked up automatically on the next `pip install -r requirements.txt`. No environment variables,
secrets, GCP configurations, or deployment scripts require manual changes.

**Manual verification checklist** (PRD §7.3) — run these after the agent completes:

- Upload a `.html` file via the drag-and-drop UI — should pass frontend validation and be accepted
  by the backend.
- Upload a `.htm` file — same result.
- Upload a `.html` file alongside a `.pdf` — both processed; combined PDF in GCS includes content
  from both files.
- Upload an unsupported type (e.g., `.png`) — error message now reads `"...Use PDF, TXT, DOCX, or HTML."`.
- Upload an HTML file with `<script>` and `<style>` blocks — script/style text must not appear in
  the extracted output or the final care plan.
