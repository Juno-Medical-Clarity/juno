# PRD: SP09 — Dead-Code Purge + Linter

**Sub-project:** SP09  
**Branch context:** `users/tejitpabari/llm-code-check`  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started

---

## 1. Problem

The Juno backend has accumulated dead code and stale comments across the cleanup sprint. Each upstream SP (SP01–SP08) deletes code it directly owns, but the residual falls into two buckets this SP catches:

1. **No linter installed.** The venv has no ruff, pyflakes, or any static-analysis tool. Unused imports and unreferenced identifiers accumulate silently. Without a linter in the dev workflow and CI there is no structural guard against future dead code.

2. **Leftover dead symbols after upstream SP deletions.** Several constants, model classes, route variables, and imports remain unreferenced in the current codebase and will remain so after every upstream SP merges. These were either orphaned during earlier sprints or were always unused. The upstream SPs are responsible for deleting code they introduced or own; this SP sweeps the remainder.

**Specific dead-code inventory (current state, pre-SP merges):**

| Location | Symbol / Code | Dead since |
|---|---|---|
| `utils/constants.py` | `Constants.ALLOWED_VERSIONS` | Never referenced outside its own file |
| `utils/constants.py` | `Constants.SUMMARY_SCHEMA_VERSION_1_3` | No reference anywhere in backend |
| `utils/constants.py` | `Constants.SUMMARY_SCHEMA_VERSION_1_4` | No reference anywhere in backend |
| `utils/constants.py` | `Constants.DATASETS_BUCKET_NAME_DEFAULT` | `gcs_datasets.py` reads `os.environ.get("DATASETS_BUCKET_NAME")` directly; constant unused |
| `utils/constants.py` | `Constants.DATASETS_BUCKET_ENV_VAR` | Duplicate of `DATASETS_BUCKET_NAME_ENV_VAR`; neither is used outside `constants.py` itself |
| `models/input.py` | `InputFile`, `FileInput`, `FileInput.from_file_uploads` | Worker constructs only `TextInput`/`DocIdInput`; no production code imports these |
| `models/input.py` | `BatchDatasetInput` | Worker resolves batch runs via raw `job_doc` dict, never constructs this model; no production route imports it |
| `models/__init__.py` | Re-exports of `InputFile`, `FileInput`, `BatchDatasetInput` | Follows from the model deletions above |
| `routes/__init__.py:26` | `ADMIN_BLUEPRINTS = [admin_bp]` | `admin_bp` moved into `API_BLUEPRINTS`; `ADMIN_BLUEPRINTS` never imported |
| `models/grading.py:1` | `import enum` | The word `enum` does not appear anywhere else in that file |
| `routes/datasets.py:36` | Comment `"GCS fetch not yet implemented (SP2)"` | SP02 is complete; comment is stale |
| `routes/__init__.py:19` | Comment `# ← added; was only in ADMIN_BLUEPRINTS before` | Scaffolding note; migration is done |
| `utils/jargon_db.py:6` | Comment `"no longer opens or queries a generated database"` | Migration complete; comment documents the past, not the present |
| `models/care_plan.py:8` | Comment `"Concrete versions live in care_plan/v*/models.py"` | Misleading now that the directory structure is settled; add value or remove |

**Note — constants that are NOT dead:**

- `Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR` and `CARE_PLAN_DEFAULT_VERSION_FALLBACK` — both are read by `config.py:14–16`. Keep.
- `Constants.SUMMARY_SCHEMA_VERSION_1_2` — verify across SP03 models after merge; keep if referenced.
- `Constants.RESULT_SENTINEL` — referenced as `RESULT_SENTINEL` in `routes/care_plan.py`. Keep.

---

## 2. Goals

1. **Install ruff** as the project linter: add it to `requirements-dev.txt`, add a `[tool.ruff]` section to `backend/pyproject.toml`, enable at minimum the F (pyflakes) rule set covering unused imports and undefined names. Run it and fix every violation it surfaces in backend source files.

2. **Add a pre-commit hook** (`.pre-commit-config.yaml` at repo root or `backend/`) that runs `ruff check` on staged `.py` files in `backend/`, so violations are caught before commit.

3. **Delete the confirmed-dead constants** listed in the inventory above from `utils/constants.py`. Each deletion is gated on a post-SP-merge grep verification (see section 4B).

4. **Delete the confirmed-dead input models** from `models/input.py` and their re-exports from `models/__init__.py`, contingent on SP05 JobDoc confirmation that none of these classes are referenced by the new `JobDoc` model (see section 4B, open question Q1).

5. **Delete `ADMIN_BLUEPRINTS`** from `routes/__init__.py`.

6. **Remove the unused `import enum`** from `models/grading.py`.

7. **Remove or rewrite stale comments** at the five locations listed in the inventory.

8. **Document the ruff config and pre-commit setup** with a brief note in `backend/README.md` so future contributors know to run `ruff check` locally.

---

## 3. Non-Goals

- Deleting file-level dead code owned by upstream SPs: `athena_manifest.py` (SP03), `fetch_items_with_rate_limit` (SP04), the five `batch.py` helpers (SP06), `CarePlanV1_2Pipeline.run()` and SSE scaffolding (SP07), the two legacy error files (SP01). Those deletions belong in their owning SPs.
- Enabling style rules (E, W) or type-annotation rules (ANN, UP) in the initial ruff config. Start minimal; aggressive rules can be layered in separately.
- Auto-fixing all ruff violations with `--fix`. Run `ruff check`, review the output, apply fixes deliberately.
- Frontend linting. SP10 covers the frontend.
- Adding type annotations to existing functions (not in scope).
- Any change to the Firestore wire format or HTTP API surface.

---

## 4. Architecture Decisions

### 4A. Ruff Configuration

**Install:** add `ruff` to `backend/requirements-dev.txt` (pinned to a minor version, e.g. `ruff>=0.4,<0.5`).

**Config location:** add a `[tool.ruff]` section to `backend/pyproject.toml` (already exists for pytest). Do not create a separate `ruff.toml`.

**Minimal initial config:**

```toml
[tool.ruff]
line-length = 120
target-version = "py312"
exclude = [".venv", "__pycache__", "tests"]

[tool.ruff.lint]
select = ["F"]   # pyflakes: undefined names, unused imports, unused variables
ignore = []
```

`F401` (unused import) and `F811` (redefinition of unused name) are the primary rules that catch dead imports. `F841` (local variable assigned but never used) catches unused local vars. The `tests/` directory is excluded from linting; test files legitimately import symbols for fixture use.

**Escalation path (not in scope for SP09):** Once SP09 merges and the codebase is clean under `F`, a follow-up task can add `E` (pycodestyle errors) and selectively enable `I` (isort) and `UP` (pyupgrade) as the team decides.

**Pre-commit hook:** add `.pre-commit-config.yaml` at repo root:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10          # pin to match requirements-dev.txt
    hooks:
      - id: ruff
        args: [--config, backend/pyproject.toml]
        files: ^backend/.*\.py$
```

If pre-commit is not in the team's workflow, a CI note is sufficient: add a step to `backend/cloudbuild.yaml` (or document in `README.md`) to run `ruff check backend/` after installing dev requirements. At minimum the hook gives the linter a durable enforcement point.

---

### 4B. Residual Dead-Code List and Verification Method

For each deletion, the verification command and a note on re-running after all SP branches merge:

**All greps below must be run from `/root/projects/juno/backend/` with upstream SPs merged. This SP runs last.**

---

#### B1. `Constants.ALLOWED_VERSIONS`

**File:** `backend/utils/constants.py`  
**Grep:** `grep -rn "ALLOWED_VERSIONS" backend/ --include="*.py" | grep -v constants.py`  
**Expected result:** zero matches.  
**Current state:** zero matches (confirmed pre-SP-merge; no SP introduces a reference).  
**Action:** Delete the line from `Constants`.

---

#### B2. `Constants.SUMMARY_SCHEMA_VERSION_1_3` and `SUMMARY_SCHEMA_VERSION_1_4`

**File:** `backend/utils/constants.py`  
**Grep:** `grep -rn "SUMMARY_SCHEMA_VERSION_1_3\|SUMMARY_SCHEMA_VERSION_1_4" backend/ --include="*.py" | grep -v constants.py`  
**Expected result:** zero matches.  
**Current state:** zero matches.  
**Note:** `SUMMARY_SCHEMA_VERSION_1_2` is a separate constant; verify it separately against SP03 models — if also unreferenced, it is a candidate for a follow-up task. SP09 does not delete it without explicit verification.  
**Action:** Delete both lines from `Constants`.

---

#### B3. `Constants.DATASETS_BUCKET_NAME_DEFAULT` and `Constants.DATASETS_BUCKET_ENV_VAR`

**File:** `backend/utils/constants.py`  
**Grep:** `grep -rn "DATASETS_BUCKET_NAME_DEFAULT\|DATASETS_BUCKET_ENV_VAR\b" backend/ --include="*.py" | grep -v constants.py`  
**Expected result:** zero matches.  
**Current state:** `gcs_datasets.py` reads `os.environ.get("DATASETS_BUCKET_NAME")` directly as a string literal; `Constants.DATASETS_BUCKET_NAME_DEFAULT` is never passed as a fallback argument; `Constants.DATASETS_BUCKET_ENV_VAR` is a duplicate of `DATASETS_BUCKET_NAME_ENV_VAR` and also unused outside its own definition. Zero references confirmed.  
**Note:** `Constants.DATASETS_BUCKET_NAME_ENV_VAR` is a separate constant at line 26; it is also unused in production code (same raw string used). Decide whether to delete it too or leave it as documentation. Recommendation: delete; the raw string `"DATASETS_BUCKET_NAME"` is clear enough at its one usage site.  
**Action:** Delete `DATASETS_BUCKET_NAME_DEFAULT` and `DATASETS_BUCKET_ENV_VAR` from `Constants`. Optionally also delete `DATASETS_BUCKET_NAME_ENV_VAR` after confirming zero references.

---

#### B4. `InputFile`, `FileInput`, `FileInput.from_file_uploads`, `BatchDatasetInput`

**Files:** `backend/models/input.py`, `backend/models/__init__.py`  
**Grep:** `grep -rn "InputFile\|FileInput\|BatchDatasetInput\|from_file_uploads" backend/ --include="*.py" | grep -v models/input.py | grep -v models/__init__.py | grep -v tests/`  
**Expected result:** zero matches.  
**Current state (pre-SP05):** Only `routes/worker.py` imports from `models.input`, and it imports only `TextInput, DocIdInput`. No production code imports or instantiates `FileInput`, `InputFile`, or `BatchDatasetInput`. Tests reference all three, but tests are excluded from the lint check and the test file will need to be updated after deletion.  
**SP05 dependency — OPEN (see Q1):** SP05 introduces `JobDoc(JsonModel)` in `backend/models/job.py`. Before deleting, verify: `grep -n "FileInput\|InputFile\|BatchDatasetInput" backend/models/job.py`. If SP05 references any of these as a type hint for `input_type` or `input_model`, keep the referenced class.  
**Note on the `Input` union:** `Input = Annotated[Union[FileInput, TextInput, DocIdInput, BatchDatasetInput], ...]` becomes `Input = Annotated[Union[TextInput, DocIdInput], ...]` after deletion. Verify no route or utility depends on the `Input` union accepting `FileInput` or `BatchDatasetInput` variants.  
**Action (conditional on SP05 check):** Delete `InputFile`, `FileInput`, and `BatchDatasetInput` class definitions from `models/input.py`; shrink the `Input` union; remove them from `models/__init__.py` exports; update `tests/models/test_input_metrics.py` to remove the now-irrelevant test cases.

---

#### B5. `ADMIN_BLUEPRINTS` in `routes/__init__.py`

**File:** `backend/routes/__init__.py`  
**Grep:** `grep -rn "ADMIN_BLUEPRINTS" backend/ --include="*.py" | grep -v routes/__init__.py`  
**Expected result:** zero matches.  
**Current state:** `ADMIN_BLUEPRINTS = [admin_bp]` at line 26; `admin_bp` is already in `API_BLUEPRINTS`. No file imports `ADMIN_BLUEPRINTS`.  
**Action:** Delete lines 26–28 (`ADMIN_BLUEPRINTS = [admin_bp]`).

---

#### B6. `import enum` in `models/grading.py`

**File:** `backend/models/grading.py`, line 1  
**Grep:** `grep -n "^import enum\|\benum\." backend/models/grading.py`  
**Expected result:** only the import line; no `enum.` usage.  
**Current state:** confirmed — `import enum` at line 1; no other occurrence of `enum` in the file. The `Enum` base class used in `Constants` is in `utils/constants.py` and is not related.  
**Action:** Delete `import enum` from line 1 of `models/grading.py`.

---

#### B7. Stale Comments

Five comments to remove or rewrite. Grep before deleting to confirm no other file references the comment as documentation.

| File | Line (approx.) | Current comment | Action |
|---|---|---|---|
| `routes/datasets.py` | ~36 | `"GCS fetch not yet implemented (SP2)"` in the 503 error response dict | Update to `"On-demand GCS fetch unavailable"` or remove the human-readable hint — SP02 is shipped; the 503 path can remain for resilience but the comment is stale. |
| `routes/__init__.py` | ~19 | `# ← added; was only in ADMIN_BLUEPRINTS before` | Delete inline comment; the context it documents is gone. |
| `utils/constants.py` | ~47 | `# SSE sentinel` on the `RESULT_SENTINEL` line | Rewrite to `# Internal sentinel value separating SSE stream chunks from the final pipeline result tuple` — the word "SSE" is accurate but terse; either expand or drop. Do not delete the constant itself. |
| `utils/jargon_db.py` | ~6 | `"no longer opens or queries a generated database"` in the module docstring | Remove that sentence; the rest of the docstring accurately describes what the module does. |
| `models/care_plan.py` | ~8 | `"Concrete versions live in care_plan/v*/models.py"` docstring on `CarePlan` | Replace with a factually current description, e.g.: `"Version-agnostic base model for all care plan outputs. The concrete version schema is CarePlanV1_2 in care_plan/v1_2/models.py."` |

---

## 5. API Change Summary

None. SP09 makes no changes to any HTTP endpoint, response shape, or Firestore document structure.

---

## 6. Frontend

N/A. SP10 covers all frontend changes.

---

## 7. Testing

### Ruff baseline run

After installing ruff and before making any code changes, run:

```bash
cd backend
pip install -r requirements-dev.txt
ruff check . --config pyproject.toml
```

Capture the full output. Every reported violation becomes a task item. Fix violations in file order; re-run after each file to confirm no regressions.

### Per-deletion smoke tests

For each deletion:

1. Run `ruff check .` immediately after the change — it should report zero new violations.
2. Run the existing test suite: `pytest tests/ -x -q`. The dead-code deletions should not break any passing test except `tests/models/test_input_metrics.py`, which must be updated in the same commit as the model deletions (B4).

### `test_input_metrics.py` update (B4)

When `FileInput`, `InputFile`, and `BatchDatasetInput` are deleted from production code, the corresponding test fixtures and test functions in `tests/models/test_input_metrics.py` must be removed or rewritten:

- Delete import lines for the three removed classes.
- Delete test functions that construct or assert on `FileInput`, `InputFile`, or `BatchDatasetInput` instances.
- Retain and verify tests for `TextInput`, `DocIdInput`, and the `Input` discriminated union.
- Retain any test that validates `Metrics` or `CarePlanInternal` round-trips that happen to use those classes as factories — replace the factory with a `TextInput` equivalent.

### Pre-commit hook smoke test

```bash
pip install pre-commit
pre-commit install
# stage any .py file and attempt a commit; ruff should run and pass
```

---

## 8. Manual Intervention

**Run order is critical:** this SP must be implemented after ALL upstream SPs (SP01–SP08) have merged into the branch. The verification greps in section 4B assume the upstream deletions are already in the tree.

Steps in sequence:

1. **Merge SP01–SP08** (or confirm their feature branches are present on the working branch).
2. **Re-run every grep in section 4B.** Do not rely solely on pre-merge checks. Some upstream SPs may introduce a new reference to a symbol that looked dead before the SP was written.
3. **Install ruff** and run the baseline. Record the full output before touching any code.
4. **Apply deletions** in the order B1 → B2 → B3 → B4 → B5 → B6 → B7. Run `pytest` after each step.
5. **Run ruff** after each deletion step; it may surface secondary unused imports that became dead after the primary deletion.
6. **Update `tests/models/test_input_metrics.py`** in the same commit as B4.
7. **Install pre-commit hook** and verify it runs clean.
8. **Commit** all changes in a single logical commit per deletion group, or one omnibus commit with a clear message.

No GCP credentials, environment variables, or deployed infrastructure changes are required for this SP.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Do `InputFile`, `FileInput`, or `BatchDatasetInput` survive SP05? SP05 introduces `JobDoc(JsonModel)` and may type the `input` field or a `from_job_doc()` factory using one of these classes. Grep `backend/models/job.py` after SP05 merges before deleting. | [OPEN — depends on SP05 implementation] |
| Q2 | Should `Constants.DATASETS_BUCKET_NAME_ENV_VAR` also be deleted? It is currently unused in production (the raw string `"DATASETS_BUCKET_NAME"` is used directly in `gcs_datasets.py`). Alternatives: (a) delete and use the raw string; (b) keep as documentation; (c) make `gcs_datasets.py` read via the constant. | [OPEN — recommend delete for consistency once zero-reference confirmed] |
| Q3 | Ruff rule strictness: start with `F` only (pyflakes) vs. also enabling `E` (pycodestyle errors). Starting narrow reduces friction for the first linter run. | [RESOLVED: start with `F` only; escalate in a follow-up task] |
| Q4 | Pre-commit vs. CI-only enforcement. Pre-commit is lowest-friction for individual developers; CI is the backstop for any branch that bypasses hooks. | [RESOLVED: add both — pre-commit hook for local dev, document `ruff check` in CI/cloudbuild] |
| Q5 | Should `Constants.SUMMARY_SCHEMA_VERSION_1_2` also be deleted? It appears unused, but SP03 touches models and may introduce a reference. Verify post-SP03 merge. | [DEFERRED — verify post-SP03; if still zero references, add to deletion list in this SP] |
| Q6 | `all_blueprints = API_BLUEPRINTS` alias at the bottom of `routes/__init__.py` — is it referenced anywhere? If not, it can also be removed. | [OPEN — quick grep needed: `grep -rn "all_blueprints" backend/ --include="*.py"`; if zero hits, delete] |
| Q7 | File-level vs. line-level ruff suppression. If any legitimate suppression is needed (e.g., a `TYPE_CHECKING`-guarded import), use `# noqa: F401` inline rather than a blanket `ignore` in config. | [RESOLVED: inline `noqa` only; no blanket ignores] |

**Dependencies:** SP01 (error system), SP02 (constants), SP03 (models), SP04 (Athena), SP05 (JobDoc), SP06 (batch hardening), SP07 (pipeline consolidation), SP08 (sweep). SP09 runs after all of the above are merged.
