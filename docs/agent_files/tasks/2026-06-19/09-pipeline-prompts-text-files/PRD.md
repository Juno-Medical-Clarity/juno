# PRD: Pipeline Prompts as Text Files (SP-09)

Sub-project 9 of the Juno backend refactor. Logically follows **SP-07** (which renames
`simplify/` → `care_plan/` and `V1_2Pipeline` → `CarePlanV1_2Pipeline`). SP-09 can be written
in parallel with SP-07 but must land on top of SP-07's folder rename. All paths in this
document refer to the **post-SP-07** tree.

## 1. Problem

Three LLM prompts live as multi-line f-strings **inside method bodies** in
`care_plan/v1_2/pipeline.py`:

1. `simplify_language_with_term_plan` — a ~30-line system+instructions block with four
   interpolated values (`{sub_block}`, `{medical_block}`, `{abbrev_block}`, `{text}`).
2. `clarify_and_action` — a ~15-line block with two interpolated values (`{abbreviation_section}`,
   `{text}`), where `abbreviation_section` is an empty string when no abbreviations are present.
3. `structure_appointment_note` — a ~20-line block with two interpolated values
   (`{_STRUCTURING_SCHEMA}`, `{text}`).

Inline prompts are hard to review, version-control, compare across runs, or hand to a
non-engineer for editing. When a prompt changes, the Python diff noise obscures what actually
changed. There is no single place to read "what does Juno ask the LLM to do?"

## 2. Goals

1. Extract all three prompts into standalone `.txt` files under
   `care_plan/v1_2/prompts/` — one file per prompt method.
2. Each `.txt` file is the **complete prompt string** with `{placeholder}` markers (Python
   `str.format()` syntax) wherever a runtime value is spliced in.
3. `pipeline.py` loads each `.txt` file **once at module init** using `pathlib.Path`, storing
   the result in a module-level `str` constant.
4. Each pipeline method becomes a thin caller: build the runtime values, call
   `_PROMPT_CONSTANT.format(var=val, ...)`, pass to `_generate_text` / `_generate_json`.
5. `_STRUCTURING_SCHEMA` (a JSON string computed from `CarePlanV1_2StructuredLLM.model_json_schema()`)
   remains a Python module-level constant — it is not a prompt; it is a Python-computed value
   inserted into `structure_note.txt` via `{schema}`.
6. Zero behavior change — the prompt strings produced at runtime must be byte-for-byte identical
   to what the current inline f-strings produce.

## 3. Non-Goals

- **Not** changing prompt content, wording, rules, or parameters. This is a pure
  structural extraction with no semantic changes.
- **Not** adding a templating library (Jinja2, etc.). Python's `str.format()` is sufficient and
  is the locked initiative-wide convention.
- **Not** adding any hot-reload, caching layer, or config-driven prompt override. Files are
  read once at import time; a process restart picks up edits.
- **Not** moving the `_STRUCTURING_SCHEMA` computation into a text file — it is derived
  programmatically from a Pydantic model and must stay in Python.
- **Not** touching any other pipeline version, route, or utility file.
- **Not** changing the `run()` method or the pipeline's public contract.

## 4. Architecture Decisions

### 4.1 Directory layout

```
backend/
  care_plan/
    v1_2/
      pipeline.py          ← refactored (module-level loads + thin method bodies)
      prompts/
        simplify_language.txt
        clarify_and_action.txt
        structure_note.txt
```

The `prompts/` directory sits **next to** `pipeline.py` (sibling, not sub-package — no
`__init__.py` needed). Pathlib's `Path(__file__).parent` resolves correctly when the file is
imported from anywhere on the Python path.

### 4.2 Module-level loading in `pipeline.py`

Replace the inline f-strings with three module-level constants loaded at import time.
`_STRUCTURING_SCHEMA` stays as-is (Python-computed, not a file read).

```python
# care_plan/v1_2/pipeline.py  — top of file, after imports

_PROMPTS_DIR = Path(__file__).parent / "prompts"

_SIMPLIFY_PROMPT    = (_PROMPTS_DIR / "simplify_language.txt").read_text()
_CLARIFY_PROMPT     = (_PROMPTS_DIR / "clarify_and_action.txt").read_text()
_STRUCTURE_PROMPT   = (_PROMPTS_DIR / "structure_note.txt").read_text()
```

`pathlib` must be added to the imports at the top of the file:

```python
from pathlib import Path
```

`_STRUCTURING_SCHEMA` remains unchanged:

```python
_STRUCTURING_SCHEMA = json.dumps(
    CarePlanV1_2StructuredLLM.model_json_schema(),
    indent=2,
)
```

### 4.3 Refactored method bodies

Each method builds its runtime values, then delegates to a single `.format()` call.

#### `simplify_language_with_term_plan`

**Old → New (method body only):**

```python
# BEFORE (inline f-string, lines 81-114)
sub_block = format_substitution_candidates_for_prompt(substitution_candidates)
medical_block = format_medical_terms_for_prompt(preserve_and_define_terms)
abbrev_block = format_abbreviations_for_prompt(abbreviations)
prompt = f"""You are a health literacy expert..."""
return self._generate_text(prompt, temperature=0.3, max_tokens=16384)

# AFTER
sub_block = format_substitution_candidates_for_prompt(substitution_candidates)
medical_block = format_medical_terms_for_prompt(preserve_and_define_terms)
abbrev_block = format_abbreviations_for_prompt(abbreviations)
prompt = _SIMPLIFY_PROMPT.format(
    sub_block=sub_block,
    medical_block=medical_block,
    abbrev_block=abbrev_block,
    text=text,
)
return self._generate_text(prompt, temperature=0.3, max_tokens=16384)
```

#### `clarify_and_action`

The `abbreviation_section` conditional block moves **into the caller** (it already lived there)
and is reduced to a plain string assigned before `.format()`. The `.txt` file always contains
the `{abbreviation_section}` placeholder; when there are no abbreviations the caller passes an
empty string `""`.

```python
# BEFORE (inline f-string, lines 117-143)
abbreviation_section = ""
if abbreviations:
    abbrev_list = "\n".join(
        f"- \"{a['term']}\" -> \"{a['expansion']}\""
        for a in abbreviations[:30]
    )
    abbreviation_section = f"""
If any of these abbreviations remain in the text, expand them:
{abbrev_list}
"""
prompt = f"""You are a health literacy expert...\n{abbreviation_section}\nTEXT:\n{text}..."""
return self._generate_text(prompt, temperature=0.2, max_tokens=16384)

# AFTER
abbreviation_section = ""
if abbreviations:
    abbrev_list = "\n".join(
        f"- \"{a['term']}\" -> \"{a['expansion']}\""
        for a in abbreviations[:30]
    )
    abbreviation_section = (
        f"\nIf any of these abbreviations remain in the text, expand them:\n{abbrev_list}\n"
    )
prompt = _CLARIFY_PROMPT.format(
    abbreviation_section=abbreviation_section,
    text=text,
)
return self._generate_text(prompt, temperature=0.2, max_tokens=16384)
```

#### `structure_appointment_note`

```python
# BEFORE (inline f-string, lines 146-169)
prompt = f"""You are structuring...\n{_STRUCTURING_SCHEMA}\n...\n{text}\n..."""
raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
...

# AFTER
prompt = _STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)
raw = self._generate_json(prompt, temperature=0.2, max_tokens=8192)
...
```

The remainder of `structure_appointment_note` (validation, model_dump) is unchanged.

### 4.4 Prompt file contents

Each file is shown in full. Placeholder markers use single curly braces as required by
Python's `str.format()`. Any literal `{` or `}` in the prompt text that are NOT placeholders
must be escaped as `{{` and `}}` — review the originals: none of the three prompts contain
literal braces in their static text, so no escaping is needed.

---

#### `care_plan/v1_2/prompts/simplify_language.txt`

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

---

#### `care_plan/v1_2/prompts/clarify_and_action.txt`

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

Placeholders: `{abbreviation_section}`, `{text}`.

When no abbreviations are present, `abbreviation_section=""` is passed and the placeholder
expands to an empty string, producing the same output as the current f-string where
`abbreviation_section` is `""`.

When abbreviations are present, `abbreviation_section` is a string that begins with `\n` and
ends with `\n` — for example:

```
\nIf any of these abbreviations remain in the text, expand them:\n- "HTN" -> "high blood pressure"\n
```

This preserves the exact whitespace produced by the current inline f-string (which wraps the
block in a leading `\n` via the triple-quoted interpolation and a trailing `\n` from the final
newline before the closing `"""`).

---

#### `care_plan/v1_2/prompts/structure_note.txt`

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

Placeholders: `{schema}`, `{text}`.

`{schema}` is filled by `_STRUCTURING_SCHEMA` (the Python-computed JSON string from
`CarePlanV1_2StructuredLLM.model_json_schema()`). The JSON schema itself is multi-line text
with no `{` or `}` characters in its values, so no escaping is needed.

### 4.5 Import change

Add `from pathlib import Path` to the existing import block in `pipeline.py`. No other
import changes are needed.

### 4.6 Old → new summary table

| Location | Before | After |
|---|---|---|
| `pipeline.py` module level | `_STRUCTURING_SCHEMA` only | `_STRUCTURING_SCHEMA` + `_PROMPTS_DIR` + `_SIMPLIFY_PROMPT` + `_CLARIFY_PROMPT` + `_STRUCTURE_PROMPT` |
| `simplify_language_with_term_plan` body | inline f-string ~30 lines | `.format(sub_block=..., medical_block=..., abbrev_block=..., text=...)` one call |
| `clarify_and_action` body | inline f-string with conditional interpolation | conditional builds `abbreviation_section` str; `.format(abbreviation_section=..., text=...)` one call |
| `structure_appointment_note` body | inline f-string with `_STRUCTURING_SCHEMA` + `text` | `.format(schema=_STRUCTURING_SCHEMA, text=text)` one call |
| `care_plan/v1_2/prompts/` | (directory does not exist) | three `.txt` files created |

## 5. API Change Summary

None. This sub-project makes no changes to request/response shapes, route signatures,
Firestore keys, or the public pipeline contract. The `run()` method is untouched. Prompt
strings produced at runtime are identical.

## 6. Frontend Change Summary

N/A. No frontend files are touched.

## 7. Testing

- **Smoke / import test.** Import `care_plan.v1_2.pipeline` in a test; assert all three module-level
  prompt constants (`_SIMPLIFY_PROMPT`, `_CLARIFY_PROMPT`, `_STRUCTURE_PROMPT`) are non-empty
  strings. This ensures the files exist and are readable at import time.
- **Format-key tests.** For each prompt constant, assert that calling `.format(**full_kwargs)` with
  all expected placeholder keys produces a string that contains the injected values. This ensures
  the `.txt` placeholder names exactly match what the method passes to `.format()`. A missing or
  misspelled key raises `KeyError`; an extra key in the `.format()` call is silently ignored by
  Python's `str.format()`, so tests must check both directions:
  - Call with all expected keys → no exception, output contains each injected string.
  - Call with a missing key → `KeyError` (documents the required interface).
- **`abbreviation_section` empty-string test.** Call `_CLARIFY_PROMPT.format(abbreviation_section="", text="sample")`
  and assert the result does not contain the literal string `{abbreviation_section}` (verifies the
  placeholder was consumed, not left as a literal). Also call with a non-empty `abbreviation_section`
  and assert the expansion text appears in the output.
- **Whitespace parity test (optional but recommended).** Construct the prompt string using both the
  old inline f-string and the new `.format()` path with identical inputs; assert equality. This is
  the strongest guarantee of zero behavior change and should be kept in CI.
- No mocking of `LLMClient` is required for these tests; they operate only on the prompt string
  construction path.

## 8. Manual Intervention Required From You

None. This sub-project creates new `.txt` files and edits one Python file. There are no
dependency changes, Firestore schema changes, or environment variable changes. No deploy
configuration changes are needed; the `prompts/` directory is co-located with the Python
source and is included in the Docker image automatically via the existing `COPY` step.

> Confirm that the Docker build step (Cloud Run) copies the full `backend/` source tree (including
> subdirectories). If any `.dockerignore` rule excludes `*.txt` files, add an explicit exception
> for `care_plan/v1_2/prompts/*.txt`. This is a one-line verification, not a blocking concern.

## 9. Open Questions & Decisions

1. **Encoding of `.txt` files.**
   `[RESOLVED: UTF-8. Python's `Path.read_text()` defaults to the platform encoding on some
   systems; pass `encoding="utf-8"` explicitly to guarantee portability:
   `(_PROMPTS_DIR / "simplify_language.txt").read_text(encoding="utf-8")`.
   All three load calls must include this argument.]`

2. **Trailing newline behavior in `clarify_and_action`'s `abbreviation_section`.**
   `[RESOLVED: The `.txt` file contains `{abbreviation_section}` on its own line between rule 8
   and "TEXT:". When abbreviations are present, the caller builds `abbreviation_section` as a
   string starting with `\n` and ending with `\n`, which matches the whitespace produced by the
   current triple-quoted f-string block. When absent, the empty string `""` is passed, collapsing
   that gap to zero characters — identical to the current f-string where `abbreviation_section`
   is `""`. Tests must verify parity for both branches.]`

3. **`.txt` files under version control vs. ignored.**
   `[RESOLVED: `.txt` files are committed to the repo. They are source — they define behavior —
   and must be diffable and reviewable. No `.gitignore` entry should exclude them.]`

4. **Hot-reload / runtime editing of prompts.**
   `[DEFERRED: Not in scope for SP-09. Files are read at module import time. Editing a prompt
   requires a process restart (local) or a redeploy (Cloud Run). A future sub-project could
   add a config-driven override or Firestore-backed prompt store, but that is out of scope here.]`

5. **`{schema}` placeholder in `structure_note.txt` — brace escaping.**
   `[RESOLVED: The JSON schema emitted by `CarePlanV1_2StructuredLLM.model_json_schema()` is
   a JSON string. JSON object syntax uses `{` and `}`, which Python's `str.format()` would
   interpret as placeholders unless escaped as `{{` and `}}`. However, the schema is passed as
   a runtime value via `.format(schema=_STRUCTURING_SCHEMA, text=text)` — `_STRUCTURING_SCHEMA`
   is substituted as a value, not parsed as a template. The `{schema}` placeholder in the `.txt`
   file is replaced by the full JSON string, after which `str.format()` is done. Python does not
   re-scan the substituted value for braces, so no escaping of the schema JSON is needed.]`
