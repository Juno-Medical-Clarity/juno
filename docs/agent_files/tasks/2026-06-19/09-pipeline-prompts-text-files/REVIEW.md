# Review: Pipeline Prompts as Text Files (SP-09)

**Date:** 2026-06-21
**Status:** COMPLETE — all tasks already implemented and passing

---

## What Exists

All six tasks from TASKS.md were already fully implemented before this review session:

### Task 1 — `prompts/` directory and `.txt` files
- `backend/care_plan/v1_2/prompts/simplify_language.txt` — present, correct content, 4 placeholders (`{sub_block}`, `{medical_block}`, `{abbrev_block}`, `{text}`)
- `backend/care_plan/v1_2/prompts/clarify_and_action.txt` — present, correct content, 2 placeholders (`{abbreviation_section}`, `{text}`)
- `backend/care_plan/v1_2/prompts/structure_note.txt` — present, correct content, 2 placeholders (`{schema}`, `{text}`)
- No `__init__.py` in the prompts directory (correct — data directory, not a package)

### Task 2 — `pathlib` import + module-level constants in `pipeline.py`
- `from pathlib import Path` present in the import block (was already added as part of SP-07)
- `_PROMPTS_DIR`, `_SIMPLIFY_PROMPT`, `_CLARIFY_PROMPT`, `_STRUCTURE_PROMPT` all defined at module level with `encoding="utf-8"` as required
- `_STRUCTURING_SCHEMA` unchanged (uses `_llm_schema(CarePlanV1_2, ...)`)

### Task 3 — `simplify_language_with_term_plan` refactored
- Uses `_SIMPLIFY_PROMPT.format(sub_block=..., medical_block=..., abbrev_block=..., text=...)` — no inline f-string

### Task 4 — `clarify_and_action` refactored
- Conditional `abbreviation_section` builds correctly with leading/trailing `\n`
- Uses `_CLARIFY_PROMPT.format(abbreviation_section=..., text=...)` — no inline f-string

### Task 5 — `structure_appointment_note` refactored
- Uses `_STRUCTURE_PROMPT.format(schema=_STRUCTURING_SCHEMA, text=text)` — no inline f-string

### Task 6 — Tests
- `backend/tests/simplify/test_pipeline_prompts.py` — present, 15 tests covering all four groups (smoke, format-key, abbreviation_section, whitespace-parity)
- All 15 tests pass: `15 passed, 1 warning in 1.13s`

---

## Verification

- `grep -n 'f"""' backend/care_plan/v1_2/pipeline.py` — returns zero results (all inline f-strings removed)
- All placeholder counts match spec: simplify=4, clarify=2, structure=2
- `python3 -m pytest tests/simplify/test_pipeline_prompts.py -v` — 15/15 green

---

## Blockers

None.

---

## Manual Steps Required

None. This sub-project had no human-only steps per PRD §8. The Docker `COPY . .` instruction in `backend/Dockerfile` automatically includes `care_plan/v1_2/prompts/*.txt`; no `.dockerignore` exists, confirmed by TASKS.md.

---

## Notes

SP-07 (Care Plan Model and Folder Restructure) was completed before this review, which is why `pathlib` was already imported in `pipeline.py` as part of that rename. SP-09 implementation landed cleanly on top of SP-07's tree.
