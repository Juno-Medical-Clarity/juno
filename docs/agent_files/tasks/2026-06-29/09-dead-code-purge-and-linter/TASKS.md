# SP09 Dead-Code Purge + Linter — TASKS

## Prerequisites

Install and configure `ruff` as the backend linter, then delete all confirmed-dead symbols and stale comments left behind after SP01–SP08. This SP assumes SP01–SP08 are fully merged and deployed; run every grep in the steps below from a branch that includes all upstream SP merges.

---

## Tasks

### Task 09.1: Install ruff and configure pyproject.toml

**Goal:** Add `ruff` to `requirements-dev.txt` and add a minimal `[tool.ruff]` section to `pyproject.toml` so `ruff check` is runnable. No code changes yet.

**Files:**
- `backend/requirements-dev.txt`
- `backend/pyproject.toml`

**Steps:**
1. Open `backend/requirements-dev.txt`. Append a new line: `ruff>=0.4,<0.5`
2. Open `backend/pyproject.toml`. After the existing `[tool.pytest.ini_options]` block, append:

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
exclude = [".venv", "__pycache__", "tests"]

[tool.ruff.lint]
select = ["F"]
ignore = []
```

3. From `backend/`, install the dev requirements: `pip install -r requirements-dev.txt`
4. Run the baseline check: `ruff check . --config pyproject.toml`
5. Record every violation reported. Each violation that is not covered by a later task in this list must be fixed in this task (add a `# noqa: F401` inline comment only where the import is legitimately needed but ruff cannot see the usage, e.g. `TYPE_CHECKING`-guarded imports).

> Note: The `tests/` directory is excluded from linting; test files legitimately import symbols for fixture use and must not be suppressed.

**Acceptance:**
- `ruff check . --config pyproject.toml` exits 0 with no violations (after all fixes in steps 4–5 are applied).
- `pytest tests/ -x -q` still passes (no production code changed yet).

**Commit:** `chore: add ruff linter with F ruleset to backend`

---

### Task 09.2: Add pre-commit hook for ruff

**Goal:** Add `.pre-commit-config.yaml` at repo root so `ruff check` runs automatically on staged `.py` files in `backend/` before every commit.

**Files:**
- `.pre-commit-config.yaml` (new file at repo root, i.e. `/root/projects/juno/.pre-commit-config.yaml`)

**Steps:**
1. Check whether `.pre-commit-config.yaml` already exists at the repo root: `ls /root/projects/juno/.pre-commit-config.yaml`. If it exists, append the ruff hook to it rather than overwriting.
2. Create (or append to) `.pre-commit-config.yaml` with:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--config, backend/pyproject.toml]
        files: ^backend/.*\.py$
```

3. Install pre-commit into the repo: `pip install pre-commit && pre-commit install`
4. Smoke-test: stage any `.py` file under `backend/` (e.g. `git add backend/utils/constants.py`) and run `pre-commit run ruff --files backend/utils/constants.py`. Confirm it exits 0.

> Note: If the team does not use pre-commit in CI, also document the ruff run command in `backend/README.md` (see Task 09.9). The hook is still created here regardless; it is the local-dev enforcement point.

**Acceptance:**
- `.pre-commit-config.yaml` exists at repo root with the ruff hook entry.
- `pre-commit run ruff --files backend/utils/constants.py` exits 0.

**Commit:** `chore: add pre-commit ruff hook for backend Python files`

---

### Task 09.3: Delete dead constants — ALLOWED_VERSIONS, SUMMARY_SCHEMA_VERSION_1_3, SUMMARY_SCHEMA_VERSION_1_4

**Goal:** Remove three unused constants from `Constants` in `utils/constants.py`.

**Files:**
- `backend/utils/constants.py`

**Steps:**
1. Confirm zero external references (run from `backend/`):
   ```
   grep -rn "ALLOWED_VERSIONS" . --include="*.py" | grep -v constants.py
   grep -rn "SUMMARY_SCHEMA_VERSION_1_3\|SUMMARY_SCHEMA_VERSION_1_4" . --include="*.py" | grep -v constants.py
   ```
   Both greps must return zero lines. If either returns a hit, stop and report — do not delete.
2. In `backend/utils/constants.py`, delete line 13: `SUMMARY_SCHEMA_VERSION_1_3 = "1.3"`
3. Delete line 14: `SUMMARY_SCHEMA_VERSION_1_4 = "1.4"`
4. Delete line 38: `ALLOWED_VERSIONS: frozenset[str] = frozenset({"v1-2"})`
5. Also delete the comment on the line immediately above `ALLOWED_VERSIONS` (`# ── Pipeline registry ─────────────────────────────────────────────────`) only if `PIPELINE_VERSION_V1_2` (line 37) now stands alone under that heading and the heading still makes sense. If `PIPELINE_VERSION_V1_2` remains, keep the section comment.
6. Run `ruff check . --config pyproject.toml` — must exit 0.
7. Run `pytest tests/ -x -q` — must pass.

> Note: `SUMMARY_SCHEMA_VERSION_1_2` is NOT deleted here; it may be referenced by SP03 models. Leave it.

**Acceptance:**
- The three constants are absent from `constants.py`.
- The greps in step 1 return zero lines.
- `ruff check` and `pytest` both pass.

**Commit:** `refactor: remove unused ALLOWED_VERSIONS and SUMMARY_SCHEMA_VERSION_1_3/1_4 constants`

---

### Task 09.4: Delete dead dataset constants — DATASETS_BUCKET_NAME_DEFAULT, DATASETS_BUCKET_ENV_VAR, DATASETS_BUCKET_NAME_ENV_VAR

**Goal:** Remove three unused dataset-related constants from `Constants`. Per user decision Q2, delete all three (including `DATASETS_BUCKET_NAME_ENV_VAR`).

**Files:**
- `backend/utils/constants.py`

**Steps:**
1. Confirm zero external references (run from `backend/`):
   ```
   grep -rn "DATASETS_BUCKET_NAME_DEFAULT\|DATASETS_BUCKET_ENV_VAR\b\|DATASETS_BUCKET_NAME_ENV_VAR" . --include="*.py" | grep -v constants.py
   ```
   Must return zero lines. If any hit is found, stop and report.
2. In `backend/utils/constants.py`, delete lines 26–28:
   ```python
   DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
   DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
   DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"
   ```
3. Also delete the section comment on the line immediately above (`# ── Dataset GCS config ─────────────────────────────────────────────────────`) since it now has no entries beneath it.
4. Run `ruff check . --config pyproject.toml` — must exit 0.
5. Run `pytest tests/ -x -q` — must pass.

**Acceptance:**
- `DATASETS_BUCKET_NAME_DEFAULT`, `DATASETS_BUCKET_ENV_VAR`, and `DATASETS_BUCKET_NAME_ENV_VAR` are absent from `constants.py`.
- The grep in step 1 returns zero lines.
- `ruff check` and `pytest` both pass.

**Commit:** `refactor: remove unused dataset bucket constants from Constants`

---

### Task 09.5: Delete dead input models — InputFile, FileInput, BatchDatasetInput

**Goal:** Remove the three dead input model classes from `models/input.py` and shrink the `Input` discriminated union. Per user decision Q1, SP05 is complete before SP09 — verify no reference exists in `models/job.py` before deleting.

**Files:**
- `backend/models/input.py`
- `backend/models/__init__.py`

**Steps:**
1. Confirm zero external references (run from `backend/`):
   ```
   grep -rn "InputFile\|FileInput\|BatchDatasetInput\|from_file_uploads" . --include="*.py" \
     | grep -v "models/input.py" \
     | grep -v "models/__init__.py" \
     | grep -v "tests/"
   ```
   Must return zero lines. Pay special attention to `models/job.py` (SP05 output). If any hit is found, stop and report.
2. In `backend/models/input.py`:
   a. Remove the `TYPE_CHECKING` import block (lines 11–12: `if TYPE_CHECKING:` and `    from werkzeug.datastructures import FileStorage`) — this block only existed to type `FileInput.from_file_uploads`.
   b. Remove `Any` from the `from typing import ...` line (it was used only in `from_file_uploads`). The remaining imports needed are `Annotated, Literal, Union`. Adjust the import line accordingly.
   c. Delete the entire `InputFile` class (lines 18–28).
   d. Delete the entire `FileInput` class including `from_file_uploads` (lines 30–49).
   e. Delete the entire `BatchDatasetInput` class (lines 62–68).
   f. Rewrite the `Input` union (lines 71–74) to:
      ```python
      Input = Annotated[
          Union[TextInput, DocIdInput],
          Field(discriminator="mode"),
      ]
      ```
3. In `backend/models/__init__.py`:
   a. On line 8, change:
      ```python
      from .input import Input, InputFile, FileInput, TextInput, DocIdInput, BatchDatasetInput
      ```
      to:
      ```python
      from .input import Input, TextInput, DocIdInput
      ```
   b. In the `__all__` list, remove `"InputFile"`, `"FileInput"`, and `"BatchDatasetInput"` entries (lines 25–26 and 29).
4. Run `ruff check . --config pyproject.toml` — must exit 0.
5. Run `pytest tests/ -x -q` — expect failures in `tests/models/test_input_metrics.py`; those are fixed in Task 09.6.

**Acceptance:**
- `InputFile`, `FileInput`, `BatchDatasetInput` are absent from `models/input.py` and `models/__init__.py`.
- `Input` union contains only `TextInput` and `DocIdInput`.
- `ruff check` exits 0.

**Commit:** `refactor: delete InputFile, FileInput, BatchDatasetInput dead input models`

---

### Task 09.6: Update test_input_metrics.py after model deletions

**Goal:** Remove all test code that references the now-deleted `InputFile`, `FileInput`, and `BatchDatasetInput` classes. This task must follow Task 09.5 immediately.

**Files:**
- `backend/tests/models/test_input_metrics.py`

**Steps:**
1. Open `backend/tests/models/test_input_metrics.py`.
2. Remove the following imports (lines 3, 7, 11–12, 15–16):
   - `from io import BytesIO`
   - `from werkzeug.datastructures import FileStorage`
   - `BatchDatasetInput`
   - `FileInput`
   - `InputFile`
   Keep: `DocIdInput`, `Input`, `TextInput`, `Metrics`, `TypeAdapter`, `ValidationError`, `pytest`, `input_models`.
3. Delete the entire `FileInput` test section (lines 31–52: `test_file_input_from_file_uploads_exact_shape_and_resets_stream`, `test_file_input_default_pdf_gcs_url_is_none`, `test_file_input_rejects_stray_text_field`).
4. Delete the entire `BatchDatasetInput` test section (lines 95–115: `test_batch_dataset_input_exact_shape_and_mode_is_batch_dataset`, `test_batch_dataset_input_requires_all_fields`).
5. Delete `test_type_adapter_dispatches_file` (lines 122–124) and `test_type_adapter_dispatches_batch_dataset` (lines 137–146).
6. Delete `test_type_adapter_rejects_unknown_mode`'s `"batch_dataset"` dispatch (line 138 section is already deleted in step 5).
7. Delete the `CarePlanInternal` round-trip tests for `FileInput` and `BatchDatasetInput`:
   - `test_care_plan_internal_round_trips_file_input` (lines 184–190)
   - `test_care_plan_internal_round_trips_batch_dataset_input` (lines 202–211)
8. Keep intact: `test_input_version_constant`, `test_text_input_*`, `test_doc_id_input_*`, `test_type_adapter_dispatches_text`, `test_type_adapter_dispatches_doc_id`, `test_type_adapter_rejects_unknown_mode`, `test_care_plan_internal_round_trips_text_input`, `test_care_plan_internal_round_trips_doc_id_input`, all `test_metrics_*` tests, and the `_make_internal` helper.
9. Run `pytest tests/ -x -q` — must pass with zero failures.
10. Run `ruff check . --config pyproject.toml` — must exit 0.

**Acceptance:**
- No reference to `InputFile`, `FileInput`, `BatchDatasetInput`, `BytesIO`, or `FileStorage` remains in the test file.
- `pytest tests/ -x -q` passes.
- `ruff check` exits 0.

**Commit:** `test: remove FileInput/BatchDatasetInput test cases after model deletion`

---

### Task 09.7: Delete ADMIN_BLUEPRINTS and all_blueprints from routes/__init__.py

**Goal:** Remove the unused `ADMIN_BLUEPRINTS` variable and the `all_blueprints` alias. Per user decision Q6, delete `all_blueprints` too.

**Files:**
- `backend/routes/__init__.py`

**Steps:**
1. Confirm zero external references (run from `backend/`):
   ```
   grep -rn "ADMIN_BLUEPRINTS\|all_blueprints" . --include="*.py" | grep -v "routes/__init__.py"
   ```
   Must return zero lines. If any hit is found, stop and report.
2. In `backend/routes/__init__.py`, delete lines 26–28:
   ```python
   ADMIN_BLUEPRINTS = [
       admin_bp,
   ]
   ```
3. Delete line 30: `all_blueprints = API_BLUEPRINTS`
4. Also remove the inline comment `# ← added; was only in ADMIN_BLUEPRINTS before` from line 19 (the `admin_bp,` line in `API_BLUEPRINTS`), leaving just `    admin_bp,`.
5. Run `ruff check . --config pyproject.toml` — must exit 0.
6. Run `pytest tests/ -x -q` — must pass.

**Acceptance:**
- `ADMIN_BLUEPRINTS`, `all_blueprints`, and the stale inline comment are absent from `routes/__init__.py`.
- The greps in step 1 return zero lines.
- `ruff check` and `pytest` both pass.

**Commit:** `refactor: remove ADMIN_BLUEPRINTS, all_blueprints alias, and stale blueprint comment`

---

### Task 09.8: Remove unused import enum from models/grading.py

**Goal:** Delete the `import enum` statement at line 1 of `models/grading.py`.

**Files:**
- `backend/models/grading.py`

**Steps:**
1. Confirm `enum` is not used anywhere in the file:
   ```
   grep -n "^import enum\|\benum\." backend/models/grading.py
   ```
   Must return only the import line itself (line 1). If `enum.` appears elsewhere, do not delete the import.
2. Delete line 1 of `backend/models/grading.py`: `import enum`
3. Run `ruff check . --config pyproject.toml` — must exit 0.
4. Run `pytest tests/ -x -q` — must pass.

**Acceptance:**
- `import enum` is absent from `models/grading.py`.
- `ruff check` and `pytest` both pass.

**Commit:** `fix: remove unused import enum from models/grading.py`

---

### Task 09.9: Remove stale comments and update docstrings

**Goal:** Remove or rewrite five stale comments identified in the dead-code inventory.

**Files:**
- `backend/routes/datasets.py` (line ~36)
- `backend/utils/jargon_db.py` (line 6)
- `backend/models/care_plan.py` (line 8)
- `backend/utils/constants.py` (line 47 comment)

> Note: The `routes/__init__.py` stale comment is handled in Task 09.7. The `constants.py` `RESULT_SENTINEL` comment is updated here, not deleted — the constant itself is kept.

**Steps:**

**routes/datasets.py (~line 36):**
1. Find the `"detail": "GCS fetch not yet implemented (SP2)"` string in the 503 error response dict.
2. Change it to: `"detail": "On-demand GCS fetch unavailable"`

**utils/jargon_db.py (line 6):**
3. In the module docstring, remove the sentence `but no longer opens or queries a generated database.` The docstring should end at `runtime.` — so the second sentence of the docstring becomes: `This module keeps the public lookup helpers used by term_detection.` Rewrite the docstring to:
   ```python
   """
   jargon_db.py - JSON-backed helpers for deterministic jargon term detection.

   The source data is small enough to load directly from data/jargon/*.json at
   runtime. This module provides the public lookup helpers used by term_detection.
   """
   ```

**models/care_plan.py (line 8):**
4. Update the `CarePlan` class docstring from:
   `"""Version-agnostic care-plan family base. Concrete versions live in care_plan/v*/models.py."""`
   to:
   `"""Version-agnostic base model for all care plan outputs. The concrete version schema is CarePlanV1_2 in care_plan/v1_2/models.py."""`

**utils/constants.py (line 47):**
5. Update the `RESULT_SENTINEL` section comment from:
   `# ── SSE sentinel ──────────────────────────────────────────────────────`
   to:
   `# ── SSE stream result sentinel ───────────────────────────────────────`
   (Keeps the comment accurate and slightly more descriptive without over-expanding.)

6. Run `ruff check . --config pyproject.toml` — must exit 0.
7. Run `pytest tests/ -x -q` — must pass.

**Acceptance:**
- All five comment locations are updated as described.
- `ruff check` and `pytest` both pass.

**Commit:** `docs: remove stale SP2/migration comments and update stale docstrings`

---

### Task 09.10: Document ruff in backend/README.md

**Goal:** Add a brief "Linting" section to `backend/README.md` so contributors know how to run `ruff check` locally and that it also runs as a pre-commit hook.

**Files:**
- `backend/README.md`

**Steps:**
1. Read the current `backend/README.md` to find a natural insertion point (after the "Testing" section if one exists, or at the end).
2. Add a "## Linting" section with the following content:

```markdown
## Linting

The backend uses [ruff](https://docs.astral.sh/ruff/) for static analysis (pyflakes F rules).

Run locally from `backend/`:

```bash
pip install -r requirements-dev.txt
ruff check . --config pyproject.toml
```

A pre-commit hook (`.pre-commit-config.yaml` at repo root) runs `ruff check` automatically on staged `.py` files before every commit. Install it once with:

```bash
pip install pre-commit
pre-commit install
```

To add stricter rules (E, I, UP) in the future, update the `select` list in `[tool.ruff.lint]` inside `pyproject.toml`.
```

3. Run `ruff check . --config pyproject.toml` — must exit 0 (README change does not affect linting).
4. Run `pytest tests/ -x -q` — must pass.

**Acceptance:**
- `backend/README.md` contains a "Linting" section with the `ruff check` command and pre-commit instructions.
- `ruff check` and `pytest` both pass.

**Commit:** `docs: add ruff linting instructions to backend README`

---

## Verification

Run all commands from `backend/` after SP01–SP08 are merged and all tasks above are complete.

**Install dev dependencies:**
```bash
pip install -r requirements-dev.txt
```

**Linter — must exit 0 with no violations:**
```bash
ruff check . --config pyproject.toml
```

**Test suite — must pass with zero failures:**
```bash
pytest tests/ -x -q
```

**Pre-commit hook smoke test:**
```bash
git add backend/utils/constants.py
pre-commit run ruff --files backend/utils/constants.py
```

**Dead-symbol confirmation greps — each must return zero lines:**
```bash
grep -rn "ALLOWED_VERSIONS\|SUMMARY_SCHEMA_VERSION_1_3\|SUMMARY_SCHEMA_VERSION_1_4" . --include="*.py" | grep -v constants.py
grep -rn "DATASETS_BUCKET_NAME_DEFAULT\|DATASETS_BUCKET_ENV_VAR\b\|DATASETS_BUCKET_NAME_ENV_VAR" . --include="*.py" | grep -v constants.py
grep -rn "InputFile\|FileInput\|BatchDatasetInput\|from_file_uploads" . --include="*.py" | grep -v "tests/"
grep -rn "ADMIN_BLUEPRINTS\|all_blueprints" . --include="*.py"
grep -n "^import enum" models/grading.py
```

**Definition of done:**
- `ruff check` exits 0.
- `pytest tests/ -x -q` exits 0.
- All dead-symbol greps above return zero lines.
- `.pre-commit-config.yaml` exists at repo root.
- `backend/README.md` contains a Linting section.
- No upstream SP's symbols have been touched (only the inventory items listed in PRD section 4B).
