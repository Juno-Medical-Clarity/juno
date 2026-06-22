# Tasks: Pipeline Prompts as Text Files (SP-09)

**Dependency:** SP-09 must land **on top of SP-07** (which renames `simplify/` → `care_plan/` and
`V1_2Pipeline` → `CarePlanV1_2Pipeline`). All paths below use the **post-SP-07** tree. If SP-07 is not
yet merged, develop on a branch based on SP-07's branch and rebase before merging.

**Scope:** one Python file edited, three `.txt` files created, one test file created. No route, model,
or public API changes.

**Docker note (verified):** `backend/Dockerfile` uses `COPY . .` with no `.dockerignore`, so all
subdirectories including `care_plan/v1_2/prompts/*.txt` are automatically included in the image.
No Dockerfile change is needed.

---

### Task 1 — Create the `prompts/` directory and three `.txt` files

**Files:**
- `backend/care_plan/v1_2/prompts/simplify_language.txt` (NEW)
- `backend/care_plan/v1_2/prompts/clarify_and_action.txt` (NEW)
- `backend/care_plan/v1_2/prompts/structure_note.txt` (NEW)

Create the directory `backend/care_plan/v1_2/prompts/`. No `__init__.py` is needed — this is a
data directory, not a Python package.

**`simplify_language.txt`** — copy the static text exactly from the current inline f-string in
`simplify_language_with_term_plan` (lines 85–113 of the current `simplify/v1_2/pipeline.py`,
which becomes `care_plan/v1_2/pipeline.py` after SP-07). Replace each runtime value with a
`str.format()`-style placeholder:

```
You are a health literacy expert helping rewrite a provider note for a patient.

Rewrite the note so it is easier to understand at about a 6th-grade reading level.

Use these plain-language replacement suggestions when they fit naturally in context:
{sub_block}

Preserve these medical terms exactly. Do not define them inline. They will be explained separately in the UI:
{medical_block}

Expand these abbreviations when they appear:
{abbrev_block}

Rules:
1. Keep all medical facts from the source accurate.
2. Do not add diagnosis, medical advice, urgency, prognosis, or treatment interpretation.
3. Do not remove important information.
4. Use short sentences (under 20 words where possible).
5. Use active voice.
6. Use "you" and "your."
7. Do not include the patient's name, date of birth, address, insurance details, or other identifiers.
8. Do not add parenthetical definitions.
9. Do not return term annotations or spans.
10. Output only the rewritten text; no preamble, no commentary.

SOURCE NOTE:
{text}

REWRITTEN NOTE:
```

Placeholders: `{sub_block}`, `{medical_block}`, `{abbrev_block}`, `{text}`.

**`clarify_and_action.txt`** — copy the static text from `clarify_and_action` (lines 127–142 of
current pipeline). Place `{abbreviation_section}` on its own line between rule 8 and `TEXT:`,
exactly as below:

```
You are a health literacy expert helping patients understand what they need to do.

Review the text below and:
1. Use active voice throughout.
2. Address the patient as "you."
3. Start every patient action with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop.
4. Do not fabricate numbers. Do not convert vague wording into exact numbers unless the source contains the exact number.
5. Do not add urgency unless the source implies urgency.
6. Do not create new medical advice.
7. Break multi-step instructions into separate steps.
8. Output only the improved text; no commentary, no headings.
{abbreviation_section}
TEXT:
{text}

IMPROVED TEXT:
```

Placeholders: `{abbreviation_section}`, `{text}`. When no abbreviations are present, the caller
passes `abbreviation_section=""` (empty string), which collapses the blank to zero characters —
identical to the current f-string behaviour.

**`structure_note.txt`** — copy the static text from `structure_appointment_note` (lines 146–169
of current pipeline). Replace `{_STRUCTURING_SCHEMA}` with `{schema}` and `{text}` stays as-is:

```
You are structuring a simplified provider note for a patient.

Return JSON only. Use this schema:
{schema}

Rules:
1. Use only information found in the source text.
2. Do not add diagnosis, urgency, prognosis, or medical advice not in the source.
3. If the source does not contain a field, use an empty string or empty array.
4. Every medication must have a 'why' field explaining the reason for this specific patient.
5. Every warning sign must have a 'what_to_do' field: specific instruction (call doctor, go to ER, or normal side effect).
6. Classify warning sign urgency as: emergency, call_doctor, monitor, or normal_side_effect.
7. Use active voice. Address the patient as 'you'. No abbreviations.
8. Write one idea per sentence. Maximum 20 words per sentence.
9. The summary must be exactly 3 sentences: (1) why came in, (2) main conclusion, (3) most important next step.
10. Generate exactly 3 questions that help the patient understand or manage their care.
11. Put low-priority details in low_priority array.
12. Do not return term annotations or spans.
13. Output only valid JSON; no markdown, no commentary.

SOURCE TEXT:
{text}

JSON OUTPUT:
```

Placeholders: `{schema}`, `{text}`. Note: `{schema}` is filled at runtime with
`_STRUCTURING_SCHEMA`, a JSON string. Python's `str.format()` substitutes this as a value and
does not re-scan the result for braces, so no escaping of the JSON is needed.

**Acceptance:**
- `backend/care_plan/v1_2/prompts/` directory exists with exactly three `.txt` files.
- Each file is saved as UTF-8 (no BOM).
- `grep -c '{' backend/care_plan/v1_2/prompts/simplify_language.txt` returns 4 (the four
  placeholder lines); same pattern for the other two files shows the expected placeholder count.
- Files are tracked by git (`git status` shows them as new files, not ignored).

---

### Task 2 — Refactor `pipeline.py`: add `pathlib` import + module-level constants

**Files:**
- `backend/care_plan/v1_2/pipeline.py` (EDIT — post-SP-07 path)

**Step 1 — Add `pathlib` import.** In the import block at the top of the file, add:
```python
from pathlib import Path
```
Place it with the stdlib imports, above the third-party/local imports.

**Step 2 — Add module-level prompt constants.** Immediately after the existing
`_STRUCTURING_SCHEMA` constant (which is unchanged), add:

```python
_PROMPTS_DIR = Path(__file__).parent / "prompts"

_SIMPLIFY_PROMPT  = (_PROMPTS_DIR / "simplify_language.txt").read_text(encoding="utf-8")
_CLARIFY_PROMPT   = (_PROMPTS_DIR / "clarify_and_action.txt").read_text(encoding="utf-8")
_STRUCTURE_PROMPT = (_PROMPTS_DIR / "structure_note.txt").read_text(encoding="utf-8")
```

The `encoding="utf-8"` argument is required (PRD §9.1 RESOLVED) to guarantee portability across
platforms where the system default encoding may differ.

`_STRUCTURING_SCHEMA` itself is NOT changed — it remains the `json.dumps(...)` call.

**Acceptance:**
- `from pathlib import Path` appears in the import block.
- The four new names (`_PROMPTS_DIR`, `_SIMPLIFY_PROMPT`, `_CLARIFY_PROMPT`,
  `_STRUCTURE_PROMPT`) exist at module level.
- `python -c "from care_plan.v1_2 import pipeline; print(len(pipeline._SIMPLIFY_PROMPT))"` from
  `backend/` prints a positive integer (file was read successfully).

---

### Task 3 — Refactor `simplify_language_with_term_plan` method body

**Files:**
- `backend/care_plan/v1_2/pipeline.py` (EDIT)

Replace the inline f-string in `simplify_language_with_term_plan` with a `.format()` call on
`_SIMPLIFY_PROMPT`. The block-building lines (`sub_block`, `medical_block`, `abbrev_block`) and
the `_generate_text` call are unchanged.

**Before (current lines 81–114 region):**
```python
        prompt = f"""You are a health literacy expert helping rewrite a provider note for a patient.
...
REWRITTEN NOTE:"""
        return self._generate_text(prompt, temperature=0.3, max_tokens=16384)
```

**After:**
```python
        prompt = _SIMPLIFY_PROMPT.format(
            sub_block=sub_block,
            medical_block=medical_block,
            abbrev_block=abbrev_block,
            text=text,
        )
        return self._generate_text(prompt, temperature=0.3, max_tokens=16384)
```

**Acceptance:**
- The multi-line f-string starting with `f"""You are a health literacy expert helping rewrite`
  is gone from the method body.
- `grep -n 'f"""' backend/care_plan/v1_2/pipeline.py` returns no results.
- The method still calls `self._generate_text(prompt, temperature=0.3, max_tokens=16384)`.

---

### Task 4 — Refactor `clarify_and_action` method body

**Files:**
- `backend/care_plan/v1_2/pipeline.py` (EDIT)

The conditional `abbreviation_section` build block stays as-is, but the triple-quoted f-string
inside it changes. Replace the f-string (lines 123–126) and the outer prompt f-string
(lines 127–142) with a plain string assignment and a `.format()` call.

**Before:**
```python
            abbreviation_section = f"""
If any of these abbreviations remain in the text, expand them:
{abbrev_list}
"""
        prompt = f"""You are a health literacy expert helping patients understand what they need to do.
...
IMPROVED TEXT:"""
        return self._generate_text(prompt, temperature=0.2, max_tokens=16384)
```

**After:**
```python
            abbreviation_section = (
                f"\nIf any of these abbreviations remain in the text, expand them:\n{abbrev_list}\n"
            )
        prompt = _CLARIFY_PROMPT.format(
            abbreviation_section=abbreviation_section,
            text=text,
        )
        return self._generate_text(prompt, temperature=0.2, max_tokens=16384)
```

The `abbreviation_section` value when abbreviations are present must start with `\n` and end with
`\n` to preserve the exact whitespace produced by the current triple-quoted f-string block
(PRD §9.2 RESOLVED). The empty-string branch (`abbreviation_section = ""`) is unchanged.

**Acceptance:**
- No multi-line f-string beginning with `f"""You are a health literacy expert helping patients`
  remains in the method.
- The method still calls `self._generate_text(prompt, temperature=0.2, max_tokens=16384)`.
- `abbreviation_section` is still initialised to `""` at the top of the method.

---

### Task 5 — Refactor `structure_appointment_note` method body

**Files:**
- `backend/care_plan/v1_2/pipeline.py` (EDIT)

Replace the inline f-string in `structure_appointment_note` with a single `.format()` call.
The validation and `model_dump` lines below the `raw` / `_generate_json` call are unchanged.

**Before:**
```python
        prompt = f"""You are structuring a simplified provider note for a patient.
...
JSON OUTPUT:"""
        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
```

**After:**
```python
        prompt = _STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)
        raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
```

**Acceptance:**
- No multi-line f-string starting with `f"""You are structuring` remains.
- `grep -n 'f"""' backend/care_plan/v1_2/pipeline.py` returns no results (confirms all three
  inline f-strings are gone).
- `_STRUCTURING_SCHEMA` is still referenced in the method (via `_STRUCTURE_PROMPT.format(...)`).

---

### Task 6 — Add tests for prompt file loading and placeholder correctness

**Files:**
- `backend/tests/simplify/test_pipeline_prompts.py` (NEW)

Create this file with the following test cases. All tests operate on string values only —
no `LLMClient`, no Firestore, no network.

```python
"""Tests for SP-09: prompt .txt files load correctly and placeholders match callers."""

import pytest

import care_plan.v1_2.pipeline as pipeline_module
from care_plan.v1_2.pipeline import (
    _CLARIFY_PROMPT,
    _SIMPLIFY_PROMPT,
    _STRUCTURE_PROMPT,
    _STRUCTURING_SCHEMA,
)


# ---------------------------------------------------------------------------
# 1. Smoke / import tests — files exist and are non-empty
# ---------------------------------------------------------------------------

def test_simplify_prompt_is_non_empty_string():
    assert isinstance(_SIMPLIFY_PROMPT, str) and len(_SIMPLIFY_PROMPT) > 0


def test_clarify_prompt_is_non_empty_string():
    assert isinstance(_CLARIFY_PROMPT, str) and len(_CLARIFY_PROMPT) > 0


def test_structure_prompt_is_non_empty_string():
    assert isinstance(_STRUCTURE_PROMPT, str) and len(_STRUCTURE_PROMPT) > 0


# ---------------------------------------------------------------------------
# 2. Format-key tests — all expected placeholders are present
# ---------------------------------------------------------------------------

def test_simplify_prompt_accepts_all_keys():
    result = _SIMPLIFY_PROMPT.format(
        sub_block="sub",
        medical_block="med",
        abbrev_block="abbr",
        text="note text",
    )
    assert "sub" in result
    assert "med" in result
    assert "abbr" in result
    assert "note text" in result


def test_simplify_prompt_raises_on_missing_key():
    with pytest.raises(KeyError):
        _SIMPLIFY_PROMPT.format(sub_block="s", medical_block="m", abbrev_block="a")
        # missing `text`


def test_clarify_prompt_accepts_all_keys():
    result = _CLARIFY_PROMPT.format(abbreviation_section="", text="patient text")
    assert "patient text" in result


def test_clarify_prompt_raises_on_missing_key():
    with pytest.raises(KeyError):
        _CLARIFY_PROMPT.format(text="patient text")
        # missing `abbreviation_section`


def test_structure_prompt_accepts_all_keys():
    result = _STRUCTURE_PROMPT.format(schema='{"type":"object"}', text="structured text")
    assert "structured text" in result
    assert '{"type":"object"}' in result


def test_structure_prompt_raises_on_missing_key():
    with pytest.raises(KeyError):
        _STRUCTURE_PROMPT.format(schema='{"type":"object"}')
        # missing `text`


# ---------------------------------------------------------------------------
# 3. abbreviation_section empty-string test (PRD §9.2)
# ---------------------------------------------------------------------------

def test_clarify_prompt_with_empty_abbreviation_section_consumes_placeholder():
    result = _CLARIFY_PROMPT.format(abbreviation_section="", text="sample")
    assert "{abbreviation_section}" not in result


def test_clarify_prompt_with_abbreviation_section_present():
    abbrev_text = "\nIf any of these abbreviations remain in the text, expand them:\n- \"HTN\" -> \"high blood pressure\"\n"
    result = _CLARIFY_PROMPT.format(abbreviation_section=abbrev_text, text="sample")
    assert "HTN" in result
    assert "high blood pressure" in result


# ---------------------------------------------------------------------------
# 4. Whitespace-parity tests — new .format() path matches old inline f-string
# ---------------------------------------------------------------------------

def test_simplify_prompt_parity_with_inline_fstring():
    sub_block = "- hypertension → high blood pressure"
    medical_block = "- HTN"
    abbrev_block = "- BP → blood pressure"
    text = "Patient has HTN."

    # Reproduce the original inline f-string exactly (copied from pre-SP-09 source)
    expected = f"""You are a health literacy expert helping rewrite a provider note for a patient.

Rewrite the note so it is easier to understand at about a 6th-grade reading level.

Use these plain-language replacement suggestions when they fit naturally in context:
{sub_block}

Preserve these medical terms exactly. Do not define them inline. They will be explained separately in the UI:
{medical_block}

Expand these abbreviations when they appear:
{abbrev_block}

Rules:
1. Keep all medical facts from the source accurate.
2. Do not add diagnosis, medical advice, urgency, prognosis, or treatment interpretation.
3. Do not remove important information.
4. Use short sentences (under 20 words where possible).
5. Use active voice.
6. Use "you" and "your."
7. Do not include the patient's name, date of birth, address, insurance details, or other identifiers.
8. Do not add parenthetical definitions.
9. Do not return term annotations or spans.
10. Output only the rewritten text; no preamble, no commentary.

SOURCE NOTE:
{text}

REWRITTEN NOTE:"""

    actual = _SIMPLIFY_PROMPT.format(
        sub_block=sub_block,
        medical_block=medical_block,
        abbrev_block=abbrev_block,
        text=text,
    )
    assert actual == expected


def test_clarify_prompt_parity_no_abbreviations():
    text = "Take your medication daily."
    abbreviation_section = ""

    expected = f"""You are a health literacy expert helping patients understand what they need to do.

Review the text below and:
1. Use active voice throughout.
2. Address the patient as "you."
3. Start every patient action with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop.
4. Do not fabricate numbers. Do not convert vague wording into exact numbers unless the source contains the exact number.
5. Do not add urgency unless the source implies urgency.
6. Do not create new medical advice.
7. Break multi-step instructions into separate steps.
8. Output only the improved text; no commentary, no headings.
{abbreviation_section}
TEXT:
{text}

IMPROVED TEXT:"""

    actual = _CLARIFY_PROMPT.format(abbreviation_section=abbreviation_section, text=text)
    assert actual == expected


def test_clarify_prompt_parity_with_abbreviations():
    text = "Take your medication daily."
    abbrev_list = '- "HTN" -> "high blood pressure"'
    abbreviation_section = f"\nIf any of these abbreviations remain in the text, expand them:\n{abbrev_list}\n"

    expected = f"""You are a health literacy expert helping patients understand what they need to do.

Review the text below and:
1. Use active voice throughout.
2. Address the patient as "you."
3. Start every patient action with a clear verb: Take / Call / Schedule / Ask / Bring / Watch / Avoid / Continue / Stop.
4. Do not fabricate numbers. Do not convert vague wording into exact numbers unless the source contains the exact number.
5. Do not add urgency unless the source implies urgency.
6. Do not create new medical advice.
7. Break multi-step instructions into separate steps.
8. Output only the improved text; no commentary, no headings.
{abbreviation_section}
TEXT:
{text}

IMPROVED TEXT:"""

    actual = _CLARIFY_PROMPT.format(abbreviation_section=abbreviation_section, text=text)
    assert actual == expected


def test_structure_prompt_parity_with_inline_fstring():
    text = "Patient is stable."

    expected = f"""You are structuring a simplified provider note for a patient.

Return JSON only. Use this schema:
{_STRUCTURING_SCHEMA}

Rules:
1. Use only information found in the source text.
2. Do not add diagnosis, urgency, prognosis, or medical advice not in the source.
3. If the source does not contain a field, use an empty string or empty array.
4. Every medication must have a 'why' field explaining the reason for this specific patient.
5. Every warning sign must have a 'what_to_do' field: specific instruction (call doctor, go to ER, or normal side effect).
6. Classify warning sign urgency as: emergency, call_doctor, monitor, or normal_side_effect.
7. Use active voice. Address the patient as 'you'. No abbreviations.
8. Write one idea per sentence. Maximum 20 words per sentence.
9. The summary must be exactly 3 sentences: (1) why came in, (2) main conclusion, (3) most important next step.
10. Generate exactly 3 questions that help the patient understand or manage their care.
11. Put low-priority details in low_priority array.
12. Do not return term annotations or spans.
13. Output only valid JSON; no markdown, no commentary.

SOURCE TEXT:
{text}

JSON OUTPUT:"""

    actual = _STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)
    assert actual == expected
```

**Acceptance:**
- `python -m pytest backend/tests/simplify/test_pipeline_prompts.py -v` from the repo root
  passes all tests green.
- All four test groups (smoke, format-key, abbreviation_section, parity) pass.
- No `LLMClient` or network call is made during the test run.

---

## Summary of what requires you (not a dev agent)

Per PRD §8, there are **no human-only steps** for this sub-project. Everything is automated:

- The `prompts/` directory and `.txt` files are created by a dev agent (Task 1).
- `pipeline.py` edits are made by a dev agent (Tasks 2–5).
- Tests are written by a dev agent (Task 6).
- No dependency changes, environment variable changes, or Firestore schema changes exist.
- No Docker / Cloud Run configuration changes are needed (`COPY . .` in `Dockerfile` already
  picks up the new `prompts/` subdirectory; confirmed — no `.dockerignore` file exists).
- No `.gitignore` changes are needed (PRD §9.3 RESOLVED: `.txt` files are committed as source).
