# Tasks: SP14 — Test Infra Fix & CI Lint Gate

## Prerequisites

Purpose: (A) fix the root cause behind SP04's `tests/services/__init__.py` /
`tests/services/external_api/__init__.py` omission by rooting `backend/tests/` as a
single package, then add the two markers that were skipped; (B) add a Ruff lint step to
the existing `backend` job in `.github/workflows/ci.yml` so a lint regression blocks the
PR the same way a test failure does.

This SP has no dependency on SP11/SP12/SP13 and touches no files any other sub-project
owns. All work is under `backend/` plus one line of `.github/workflows/ci.yml`.

Confirmed against the live repo before writing these tasks:
- `backend/tests/` has exactly one `__init__.py` today: `backend/tests/errors/__init__.py`
  (empty). No `backend/tests/__init__.py` exists. `backend/tests/services/` and
  `backend/tests/services/external_api/` exist (the latter containing
  `test_athena_client.py`) with no `__init__.py` in either.
- `cd backend && python -m pytest --collect-only -q` reports **457 tests collected, 0
  errors** on the untouched tree — this is the baseline every task below must preserve.
- `.github/workflows/ci.yml`'s `backend` job (lines 12–38) installs
  `requirements.txt`+`requirements-dev.txt` (which already pulls in `ruff>=0.4,<0.5` via
  `requirements-dev.txt`), then runs only `python -m pytest tests/ -q`. No ruff step
  exists today.
- `backend/pyproject.toml`'s `[tool.ruff] exclude = [".venv", "__pycache__", "tests"]` —
  `tests/` is already excluded from linting, so none of the new `__init__.py` files are
  ever linted.
- `backend/README.md:117-126` documents the exact invocation `ruff check . --config
  pyproject.toml`, run from `backend/`, matching `.pre-commit-config.yaml`'s
  `args: [--config, backend/pyproject.toml]` (expressed relative to repo root there).

After every task, run `cd backend && python -m pytest --collect-only -q` and confirm the
reported count is still 457 with 0 errors (or the current count at the time you run this,
if other in-flight SPs have changed it — the point is **no drop and no new errors**, not
the literal number 457).

---

## Tasks

### Task 14.1 — Add `backend/tests/__init__.py` to root the test package

- **Goal:** Close the import-collision failure class at its source (PRD §4A) by giving
  `backend/tests/` its own `__init__.py`, so pytest's upward package-root walk
  (`_pytest/pathlib.py`'s `resolve_package_path()`) no longer stops at `tests/` and
  instead resolves every nested test module as `tests.<subpkg>.<module>` — structurally
  distinct from any top-level production package of the same name.
- **Files:**
  - `backend/tests/__init__.py` (new, empty)
- **Steps:**
  1. Create `backend/tests/__init__.py` as a completely empty file (0 bytes, matching the
     existing convention in `backend/tests/errors/__init__.py`).
  2. Do not add any content, docstring, or `__all__` — every other `__init__.py` in this
     tree is empty and this one must match.
- **Acceptance criteria:**
  - `backend/tests/__init__.py` exists and is empty (`wc -c backend/tests/__init__.py` →
    `0`).
  - `cd backend && python -m pytest --collect-only -q` still reports the same test count
    as the pre-task baseline, with 0 errors (this file alone introduces no behavior
    change yet — `tests/services/` still has no `__init__.py` at this point).
- **Commit:** `fix(backend): root tests/ as a package to prevent import collisions`

---

### Task 14.2 — Add `backend/tests/services/__init__.py` and `backend/tests/services/external_api/__init__.py`

- **Goal:** Add the two markers SP04 was supposed to add (PRD Goal 2) — now safe because
  Task 14.1 already roots the package tree, so these no longer collide with the real
  `backend/services` / `backend/services/external_api` production packages.
- **Files:**
  - `backend/tests/services/__init__.py` (new, empty)
  - `backend/tests/services/external_api/__init__.py` (new, empty)
- **Steps:**
  1. **Do this task after Task 14.1** — adding these two markers without
     `backend/tests/__init__.py` already present reproduces the exact
     `ModuleNotFoundError: No module named 'services.external_api.athena_client'`
     collision documented in PRD §4A. The order matters.
  2. Create `backend/tests/services/__init__.py`, empty.
  3. Create `backend/tests/services/external_api/__init__.py`, empty.
  4. Do not touch `backend/tests/errors/__init__.py` — it already exists, predates this
     SP, and needs no change (PRD §4B: "No change").
- **Acceptance criteria:**
  - Both new files exist and are empty.
  - `cd backend && python -m pytest --collect-only -q` reports the same test count as the
    pre-SP baseline (457 on the unmodified repo, or the current count if it has drifted),
    with **0 errors** — specifically, no
    `ModuleNotFoundError: No module named 'services...'` collection error for
    `tests/services/external_api/test_athena_client.py`.
  - `cd backend && python -m pytest tests/services/external_api/test_athena_client.py -q`
    passes.
  - In a fresh Python shell from `backend/`, `import services.external_api.athena_client
    as m; print(m.__file__)` resolves to a path under `backend/services/`, not
    `backend/tests/` (confirms the real production module wins, not a synthesized fake
    package — PRD §7 item 2).
- **Commit:** `fix(backend): add tests/services and tests/services/external_api package markers`

---

### Task 14.3 — Run the full backend suite and confirm no regression

- **Goal:** Verify Tasks 14.1–14.2 changed only collection mechanics, not test outcomes —
  a full-suite run, not just collection (PRD §7 item 3).
- **Files:** None (verification only; no file changes in this task).
- **Steps:**
  1. From `backend/`, run `python -m pytest tests/ -q` (the exact invocation CI uses)
     twice: once mentally/logically compared against the documented pre-SP baseline (8
     pre-existing failures, all in `tests/utils/test_html.py`, unrelated to this change),
     and confirm the pass/fail set after Tasks 14.1–14.2 is identical — same failures,
     same count, no new failures or errors anywhere else.
  2. If the failure set differs from the documented baseline in any way other than the 8
     known `tests/utils/test_html.py` failures, stop and treat it as a regression to
     investigate before proceeding to Task 14.4 — do not paper over it.
- **Acceptance criteria:**
  - `python -m pytest tests/ -q` from `backend/` shows no new failures or errors compared
    to the pre-SP baseline; the only failing tests, if any, are the pre-existing
    `tests/utils/test_html.py` ones.
  - No commit required for this task (verification-only); if no code changes are needed,
    proceed directly to Task 14.4.

---

### Task 14.4 — Add the Ruff lint step to `.github/workflows/ci.yml`

- **Goal:** Add a `Run ruff lint` step to the existing `backend` job, immediately before
  the existing `Run backend tests` step, so a lint regression blocks the PR the same way
  a test failure does (PRD Goal 4, §4C, §9 Q3: lint-before-test for fast-fail).
- **Files:**
  - `.github/workflows/ci.yml`
- **Steps:**
  1. In `.github/workflows/ci.yml`, locate the `backend` job's existing step:
     ```yaml
       - name: Run backend tests
         working-directory: backend
         run: python -m pytest tests/ -q
     ```
  2. Immediately before it, insert:
     ```yaml
       - name: Run ruff lint
         working-directory: backend
         run: ruff check . --config pyproject.toml
     ```
     so the two steps read, in order:
     ```yaml
       - name: Run ruff lint
         working-directory: backend
         run: ruff check . --config pyproject.toml

       - name: Run backend tests
         working-directory: backend
         run: python -m pytest tests/ -q
     ```
  3. Do not add a separate `pip install ruff` step — `ruff` is already installed by the
     existing `Install dependencies` step (`pip install -r requirements.txt
     -r requirements-dev.txt`), since `requirements-dev.txt` already pins
     `ruff>=0.4,<0.5`.
  4. Do not touch the `frontend` job (PRD §9 Q4: out of scope) or
     `cloudbuild.yaml`/`cloudbuild-build.yaml` (PRD Non-Goals: deploy-only, no lint/test
     step exists there to extend).
- **Acceptance criteria:**
  - `.github/workflows/ci.yml`'s `backend` job contains a `Run ruff lint` step, ordered
    immediately before `Run backend tests`, using exactly `working-directory: backend`
    and `run: ruff check . --config pyproject.toml`.
  - Locally, from `backend/` with `requirements-dev.txt` installed, `ruff check . --config
    pyproject.toml` exits 0 (re-verify at merge time — PRD §7 item 4 — in case other
    in-flight SPs introduced violations; if so, fix those violations as part of landing
    this gate, do not weaken the rule set).
  - No other step, job, or file in `.github/workflows/ci.yml` is modified.
  - The YAML is valid (e.g. `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
    parses without error, or equivalent linting).
- **Commit:** `ci(backend): add ruff lint gate to backend CI job`

---

### Task 14.5 — Final verification sweep

- **Goal:** Confirm the full SP is correct end-to-end before merge, covering every PRD §7
  testing point in one pass.
- **Files:** None (verification only).
- **Steps:**
  1. From `backend/`: `python -m pytest --collect-only -q` — confirm 0 errors and the
     same count as the documented baseline (or current count if other in-flight SPs have
     added tests since).
  2. From `backend/`: `python -m pytest tests/ -q` — confirm the pass/fail set matches the
     pre-SP baseline (only the 8 known `tests/utils/test_html.py` failures, if any).
  3. From `backend/`: `ruff check . --config pyproject.toml` — confirm exit code 0.
  4. Confirm `find backend/tests -maxdepth 3 -name __init__.py` lists exactly
     `backend/tests/__init__.py`, `backend/tests/errors/__init__.py`,
     `backend/tests/services/__init__.py`, and
     `backend/tests/services/external_api/__init__.py` — no markers were added to
     `care_plan`, `fixtures`, `integration`, `models`, `routes`, or `utils` (PRD §9 Q1:
     resolved as out of scope for this SP).
  5. Push the branch and open/update the PR; watch the Actions log for the `backend` job
     and confirm both the new `Run ruff lint` step and the existing `Run backend tests`
     step appear and pass (PRD §7 item 5 — this is the one verification step that cannot
     be done locally and requires an actual CI run).
- **Acceptance criteria:**
  - All four local commands in steps 1–3 above pass as specified.
  - The `find` output in step 4 matches exactly (4 files, no more, no fewer).
  - The CI Actions log for the PR's `backend` job shows `Run ruff lint` passing,
    immediately followed by `Run backend tests` passing.
  - No commit required for this task unless step 5 surfaces a problem, in which case fix
    it under the relevant earlier task's commit scope (do not create a new ad hoc fix
    commit outside the task structure) and re-push.

---

## Summary of what requires you (not a dev agent)

Per PRD §8, this SP requires **no manual intervention** for the file changes themselves:
no environment variables, secrets, GCP console steps, or migrations, and no
branch-protection / required-status-check reconfiguration (PRD §9 Q5, already confirmed
by you: no such configuration names individual CI steps).

The one step in this task list that a dev agent cannot complete unattended is **Task
14.5, step 5**: after the branch is pushed, **you** need to open or update the PR and
glance at the GitHub Actions log to confirm the `Run ruff lint` step actually appears and
passes in a real CI run (this is the PR's own integration test for the workflow-file
edit — it cannot be simulated locally). If it fails for a reason unrelated to this SP's
changes (e.g. a lint violation introduced by another in-flight SP merged in the
meantime), flag it back rather than having the dev agent silently loosen the Ruff rule
set to work around it.
