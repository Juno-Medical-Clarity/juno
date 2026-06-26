# Juno Feature Initiative — Sub-Project Index

**Date:** 2026-06-26
**Source proposal:** Add HTML (.html/.htm) as a supported document input type
**Status:** PRD authored. All open questions resolved. Ready for `dev-tasks`.

## Sub-projects & phasing

| # | Sub-project | Phase | Depends on |
|---|-------------|-------|------------|
| 01 | [HTML File Support](01-html-file-support/) | 1 | — |

```
Phase 1: SP01 (independent — no dependencies)
```

## Cross-cutting locked decisions

- **Parser library**: `beautifulsoup4` with stdlib `html.parser`. No lxml or native extensions.
- **Both extensions**: Both `.html` and `.htm` supported everywhere — constants, backend dispatch, frontend accept attribute and validation.
- **GCS merge behavior**: HTML treated like DOCX — extracted text re-encoded to UTF-8 and merged into the combined PDF artifact as a `.txt` artifact.
- **New utility module**: `backend/utils/html.py` mirrors `backend/utils/pdf.py` — one public function, no state.
- **Deferred import**: `extract_text_from_html` is imported inside the `if ext in {"html", "htm"}` branch, consistent with the `docx` pattern.

## Owner decisions — all RESOLVED

| # | Question | Decision |
|---|---|---|
| SP01-1 | HTML parser library | RESOLVED: `beautifulsoup4` with stdlib `html.parser` |
| SP01-2 | Strip script/style tags | RESOLVED: Yes — decomposed before `.get_text()` |
| SP01-3 | Target body vs full document | RESOLVED: `soup.body` if present, fallback to `soup` |
| SP01-4 | GCS merge handling | RESOLVED: Same as DOCX — re-encoded as `.txt` artifact |
| SP01-5 | `.htm` support | RESOLVED: Yes — both extensions everywhere |
| SP01-6 | Utility module location | RESOLVED: New `backend/utils/html.py` |
| SP01-7 | Frontend extension handling | RESOLVED: Both `.html` and `.htm` in accept + validation |

## Manual steps required

None.
