# PRD: HTML File Support

**Sub-project:** 01-html-file-support
**Date:** 2026-06-26
**Status:** Approved — ready for implementation

---

## 1. Problem

Juno currently accepts PDF, TXT, and DOCX as document input types. HTML is a common format for exported medical records, patient portal downloads, and appointment summaries from EHR systems. Users who receive care documents as `.html` or `.htm` files cannot use Juno without first converting them, creating friction and potential data loss during manual conversion.

---

## 2. Goals

- Accept `.html` and `.htm` files anywhere a PDF, TXT, or DOCX file is accepted today (single upload, multi-file upload, batch).
- Extract readable plain text from HTML by stripping markup, scripts, and styles — preserving the human-readable content.
- Include HTML-derived text in the combined PDF artifact stored in GCS (same behavior as DOCX).
- Update all user-facing copy (error messages, hints, file input restrictions) to mention HTML.
- Add unit tests for the new HTML extraction utility following existing test conventions.

---

## 3. Non-Goals

- No support for HTML with external CSS/JS references that require a browser to render (e.g., JavaScript-rendered single-page apps). Only static HTML byte content is in scope.
- No support for `.mhtml` / `.mht` (MIME HTML) archives.
- No change to the LLM pipeline, grading, scoring, or output format — this is purely an input-handling change.
- No new API endpoints or response fields.
- No changes to the merge PDF rendering fidelity (HTML text is re-encoded to UTF-8 and rendered as plain text in the PDF, the same as DOCX today).
- No lxml or other native HTML parser library. Only `beautifulsoup4` with Python's stdlib `html.parser`.

---

## 4. Architecture Decisions

### 4.1 New dependency: `beautifulsoup4`

**File:** `backend/requirements.txt`

Add one line after `python-docx`:

```
# Before
python-docx
textstat

# After
python-docx
beautifulsoup4
textstat
```

`beautifulsoup4` ships a pure-Python `html.parser` backend via the Python standard library — no native extensions required. `lxml` is explicitly excluded to avoid a native dependency.

---

### 4.2 Extend allowed extensions

**File:** `backend/utils/constants.py`

```python
# Before
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx"})

# After
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
```

This is the single source of truth consumed by `_allowed()` in `care_plan.py`. No other file needs to be changed for the allowlist.

---

### 4.3 New utility module: `backend/utils/html.py`

Create this file from scratch. It follows the exact same structure as `backend/utils/pdf.py`: one public function, named `extract_text_from_html`, that accepts `bytes` and returns `str`. No class, no state.

**Full implementation:**

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

Key design points:
- `tag.decompose()` removes the tag **and** all its children from the parse tree, so script/style text does not bleed into the output.
- `separator="\n"` inserts a newline between block-level tags, preserving paragraph structure without requiring tag-specific handling.
- `strip=True` trims leading/trailing whitespace from each text node — avoids large blocks of blank lines from heavily-indented HTML.
- The `ImportError` guard mirrors the pattern in `_extract_text_from_bytes` for `python-docx`.

---

### 4.4 Update text extractor dispatch

**File:** `backend/routes/care_plan.py`

The function `_extract_text_from_bytes` currently has three branches (`txt`, `pdf`, `docx`) and raises `ValueError` on anything else. Add a fourth branch for `html`/`htm` before the final `raise`.

```python
# Before
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

The import is deferred (inside the `if` block) for consistency with the `docx` branch — it keeps top-level imports lean and mirrors the existing pattern in this file.

Also add the import at the top of `care_plan.py` is NOT required here because the import is intentionally deferred. No change to top-level imports is necessary.

---

### 4.5 Update merge candidates and error message

**File:** `backend/routes/care_plan.py`

Two changes inside `_resolve_uploaded_files`:

**Change 1 — error message** (line 151 area):

```python
# Before
raise ValueError("File must be PDF, TXT, or DOCX")

# After
raise ValueError("File must be PDF, TXT, DOCX, or HTML")
```

**Change 2 — merge candidates block** (lines 165–171 area):

HTML files are handled identically to DOCX: extracted text is re-encoded to UTF-8 and inserted into the merge list as a `.txt` artifact. This means HTML content IS included in the combined PDF stored in GCS.

```python
# Before
ext = filename.rsplit(".", 1)[1].lower()
if ext in {"pdf", "txt"}:
    merge_candidates.append((file_bytes, filename))
elif ext == "docx" and extracted_text.strip():
    merge_candidates.append(
        (extracted_text.encode("utf-8"), _text_artifact_filename(filename))
    )

# After
ext = filename.rsplit(".", 1)[1].lower()
if ext in {"pdf", "txt"}:
    merge_candidates.append((file_bytes, filename))
elif ext in {"docx", "html", "htm"} and extracted_text.strip():
    merge_candidates.append(
        (extracted_text.encode("utf-8"), _text_artifact_filename(filename))
    )
```

The only change is expanding the `elif` condition from `ext == "docx"` to `ext in {"docx", "html", "htm"}`. The rest of the logic is unchanged — `_text_artifact_filename` already strips the original extension and appends `.txt`, so `report.html` becomes `report.txt` in the merged PDF.

---

### 4.6 Frontend: file input and validation

**File:** `frontend/src/pages/care-plan/CarePlanPage.tsx`

Three targeted changes. All are string/array literal updates — no logic changes.

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
<input type="file" accept=".pdf,.txt,.docx" multiple ...>

// After
<input type="file" accept=".pdf,.txt,.docx,.html,.htm" multiple ...>
```

**Change 4 — hint text** (line 180):

```tsx
// Before
<p className="upload-hint">PDF, TXT, or DOCX · Multiple files = one combined process</p>

// After
<p className="upload-hint">PDF, TXT, DOCX, or HTML · Multiple files = one combined process</p>
```

---

## 5. API Change Summary

No new endpoints. No response schema changes. The only externally observable API change is:

| Endpoint | Before | After |
|---|---|---|
| `POST /care_plan/jobs` — file upload | Rejects `.html`/`.htm` with 400 and `"File must be PDF, TXT, or DOCX"` | Accepts `.html`/`.htm`; processes successfully |
| `POST /care_plan/jobs` — file upload | Rejects `.html`/`.htm` with 400 and `"File must be PDF, TXT, or DOCX"` | If rejected for other reason, error message reads `"File must be PDF, TXT, DOCX, or HTML"` |

The combined PDF artifact stored in GCS will include HTML-derived content (as plain-text pages), which matches the existing DOCX behavior.

---

## 6. Frontend Change Summary

| Location | Before | After |
|---|---|---|
| `handleFiles` validation array | `['pdf', 'txt', 'docx']` | `['pdf', 'txt', 'docx', 'html', 'htm']` |
| Error message shown to user | `"...Use PDF, TXT, or DOCX."` | `"...Use PDF, TXT, DOCX, or HTML."` |
| `<input accept>` attribute | `".pdf,.txt,.docx"` | `".pdf,.txt,.docx,.html,.htm"` |
| Upload hint text | `"PDF, TXT, or DOCX · Multiple files = one combined process"` | `"PDF, TXT, DOCX, or HTML · Multiple files = one combined process"` |

The frontend changes are purely cosmetic/declarative. The file-picker OS dialog will now offer `.html` and `.htm` as selectable types. Drag-and-drop of an HTML file will pass validation rather than be rejected.

---

## 7. Testing

### 7.1 New unit test file: `backend/tests/utils/test_html.py`

Follow the exact structure of `backend/tests/utils/test_pdf.py`: a module-level helper to create fixture bytes, then individual test functions that import from `utils.html`.

**Test cases to implement:**

```python
# Helper — build minimal valid HTML bytes
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

### 7.2 Existing tests: no changes required

`test_pdf.py` is unaffected. The `_extract_text_from_bytes` dispatch change is additive (new branch, no modification to existing branches), so no existing test for PDF/TXT/DOCX extraction needs updating.

### 7.3 Manual verification checklist

After implementation, verify these scenarios manually or via integration test:

- Upload a `.html` file via the drag-and-drop UI — should pass frontend validation and be accepted by the backend.
- Upload a `.htm` file — same result.
- Upload a `.html` file alongside a `.pdf` — both processed; combined PDF in GCS includes content from both.
- Upload an unsupported type (e.g., `.png`) — error message now reads `"...Use PDF, TXT, DOCX, or HTML."`.
- HTML file with `<script>` and `<style>` blocks — script/style text must not appear in the extracted output or the final care plan.

---

## 8. Manual Intervention Required From You

None. All changes are in tracked source files. The `beautifulsoup4` dependency is added to `requirements.txt` and will be picked up on next `pip install -r requirements.txt`. No environment variables, secrets, GCP configurations, or deployment scripts require manual changes.

---

## 9. Open Questions & Decisions

| # | Question | Status |
|---|---|---|
| 1 | Which HTML parser library to use? | [RESOLVED: `beautifulsoup4` with stdlib `html.parser`. No lxml or other native parser.] |
| 2 | Should `<script>` and `<style>` content be excluded from extracted text? | [RESOLVED: Yes. Both tag types are decomposed (tag + inner content removed) before calling `.get_text()`.] |
| 3 | Should the extraction target `<body>` specifically or the full document? | [RESOLVED: Target `soup.body` if present; fall back to `soup` (full document) if no `<body>` tag exists.] |
| 4 | How should HTML files be handled in the merge/GCS pipeline? | [RESOLVED: Same as DOCX — extracted text is re-encoded to UTF-8 and appended to the merge list as `{stem}.txt`. HTML content IS included in the combined PDF.] |
| 5 | Should `.htm` (legacy extension) be supported in addition to `.html`? | [RESOLVED: Yes. Both `html` and `htm` are added everywhere: `ALLOWED_EXTENSIONS`, `_extract_text_from_bytes`, merge candidates, and the frontend accept/validation list.] |
| 6 | Should `extract_text_from_html` live in a new file or be added to an existing utility? | [RESOLVED: New file `backend/utils/html.py`, mirroring the structure of `backend/utils/pdf.py`. One public function per utility module.] |
| 7 | Does the frontend need to handle `.html` and `.htm` separately? | [RESOLVED: Yes, both extensions are added to the validation array and the `accept` attribute explicitly, since browser OS dialogs treat them as distinct MIME types.] |
