# PRD: SP14 — Test Infra Fix & CI Lint Gate

**Sub-project:** SP14
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-30
**Status:** Planning — no implementation started
**Dependencies:** None. Fully independent of SP11/SP12/SP13; touches no files any other sub-project owns.

---

## 1. Problem

Two unrelated gaps, bundled into one SP because both are test-infra/CI hygiene and both are small:

**A. Missing test package markers, omitted as a workaround instead of fixed.**
SP04 (`04-athena-external-api`) was supposed to add `tests/services/__init__.py` and
`tests/services/external_api/__init__.py` as part of relocating the Athena client test
suite to `tests/services/external_api/test_athena_client.py` (PRD §7a of SP04). The
implementer deliberately skipped both files, recording in
`docs/agent_files/tasks/2026-06-29/04-athena-external-api/code-2026-06-30-0000.md:20`
and `REVIEW-2026-06-30.md:39-40` that creating them collides with the real
`backend/services` production package under pytest's `--import-mode=importlib` and
raises `ModuleNotFoundError`. This is a workaround-by-omission, not a fix — it leaves
`tests/services/` and `tests/services/external_api/` as the only test directories in the
tree (besides the pre-existing `tests/errors/`) without an `__init__.py`, an
inconsistency with no structural justification once the real cause is understood and
fixed. Per the initiative's "no legacy/no workaround shims" rule, this must be fixed at
the root, not left omitted.

**B. No CI lint gate.** `ruff` has been installed as a dev dependency and configured
(`backend/pyproject.toml`, `backend/requirements-dev.txt`, `.pre-commit-config.yaml`)
since SP09, but enforcement is local-only (pre-commit hook, which any contributor can
skip with `--no-verify` or simply not install). `.github/workflows/ci.yml` runs pytest
but never runs ruff, so a lint regression cannot block a PR. `cloudbuild.yaml` /
`cloudbuild-build.yaml` are deploy-only (docker build/push/`gcloud run deploy` — 4 and 2
steps respectively, confirmed by reading both files; no lint or test step exists in
either, so there is nothing there to extend).

This PRD designs the fix for both, including the empirical root-cause work needed to
make sure (A) is actually safe and not just "moved" to a different latent failure mode.

---

## 2. Goals

1. Add `backend/tests/__init__.py` to root the entire test tree as a single package
   (`tests`), eliminating the import-collision failure class at its source rather than
   continuing to omit specific markers.
2. Add `backend/tests/services/__init__.py` and
   `backend/tests/services/external_api/__init__.py` — the markers SP04 was supposed to
   add — now that (1) makes them safe.
3. Verify, empirically, that `backend/tests/errors/__init__.py` (which already exists
   and predates this SP) is brought under the same safety net by (1), and is not merely
   "not yet observed to fail."
4. Add a Ruff step to the existing `backend` job in `.github/workflows/ci.yml`, using the
   exact same invocation convention already documented in `backend/README.md` and used by
   `.pre-commit-config.yaml`, so a lint regression blocks the PR the same way a test
   failure does.

---

## 3. Non-Goals

- Changing the Ruff rule set (`select = ["F"]`) or scope (`exclude = [".venv",
  "__pycache__", "tests"]`). The existing pyflakes-only scope stays as-is; broadening it
  is future work per SP09's documented escalation path (`backend/README.md:126`).
- Adding `__init__.py` to every other `tests/` subdirectory (`care_plan`, `fixtures`,
  `integration`, `models`, `routes`, `utils`). They are not part of this SP's scope
  because they are not currently broken and adding markers to them is not required to
  fix (A) — see §4 for why they're safe today and §9 for the discussion of whether they
  *should* eventually get markers for consistency.
- Moving the Ruff step into `cloudbuild.yaml`/`cloudbuild-build.yaml`. Confirmed
  deploy-only; CI (`.github/workflows/ci.yml`) is the only place a lint/test gate
  currently exists or should exist.
- Enforcing pre-commit installation. The hook already exists (`.pre-commit-config.yaml`)
  and stays as the local-dev fast-feedback layer; CI is the backstop, not a replacement.
- Any change to `backend/requirements-dev.txt`'s ruff pin (`ruff>=0.4,<0.5`) — already
  correct and matches `.pre-commit-config.yaml`'s `rev: v0.4.10`.

---

## 4. Architecture Decisions

### 4A. Root-cause verification (empirical, performed against the real repo — not the prior scratchpad reproduction)

**Baseline.** `cd backend && python -m pytest --collect-only -q` on the untouched repo
collects **457 tests, 0 errors**. `find tests -name __init__.py` shows exactly one file
in the whole `tests/` tree: `tests/errors/__init__.py` (empty). No `tests/__init__.py`
exists. `tests/services/` and `tests/services/external_api/` exist (containing
`test_athena_client.py`) but have no `__init__.py` today.

**Reproducing the SP04 finding on the real repo.** In an isolated copy (not the live
repo), adding only `tests/services/__init__.py` +
`tests/services/external_api/__init__.py` (no `tests/__init__.py`) reproduces the exact
failure SP04 reported:

```
ERROR collecting tests/services/external_api/test_athena_client.py
ImportError while importing test module '.../tests/services/external_api/test_athena_client.py'.
Traceback:
tests/services/external_api/test_athena_client.py:8: in <module>
    from services.external_api.athena_client import AthenaClient
E   ModuleNotFoundError: No module named 'services.external_api.athena_client'
437 tests collected, 1 error in 0.91s
```

This confirms the prior investigation's reproduction was accurate, not an artifact of
the scratchpad's isolation. The mechanism, traced through pytest's actual source
(`_pytest/pathlib.py`, installed at
`backend/.venv/lib/python3.12/site-packages/_pytest/pathlib.py`):

- `resolve_pkg_root_and_module_name()` (line 847) calls `resolve_package_path()` (line
  830), which walks **upward** from the test file's directory as long as each ancestor
  has an `__init__.py`, and stops at the first ancestor that doesn't. The directory
  *above* the stopping point becomes `pkg_root`; the dotted module name is built from
  the package-bearing directories only.
- Today, `tests/` itself has no `__init__.py`, so this walk stops immediately at
  `tests/services/external_api` → `tests/services` (once those markers exist) and
  produces dotted name **`services.external_api.test_athena_client`** — identical to the
  real production package path, with `tests` excluded from the name entirely.
- In `_import_module_using_spec()` (line 644), pytest checks `sys.modules.get(parent_module_name)`
  (i.e. `sys.modules.get("services.external_api")`). If that's already the **real**
  production package (because something imported it first), pytest reuses it and just
  attaches the test module as an extra attribute — harmless. If it's **not yet
  imported**, pytest synthesizes a fake package rooted at the *test* directory and
  caches it in `sys.modules["services.external_api"]`. Any subsequent `import
  services.external_api.athena_client` (real submodule) then resolves against the fake
  package's `__path__` (`tests/services/external_api/`), which has no `athena_client.py`
  → `ModuleNotFoundError`.
- **Why this is a race, not a guarantee either way:** whether the real package wins
  depends entirely on whether something imports it before pytest's collection walk
  reaches the colliding test directory. Traced via grep: `backend/routes/__init__.py` is
  imported eagerly by `tests/conftest.py` (`from routes import API_BLUEPRINTS`, loaded
  before any test collection in the whole run). `routes/__init__.py` imports
  `routes.worker`, which imports `from errors import ErrorCode, build_error_data,
  build_error_data_from_exc` **at module level** (`routes/worker.py:28`) — so the real
  `errors` package is always cached in `sys.modules` before collection starts. But
  `routes/worker.py`'s only reference to `services.external_api` is a **local import
  inside a function body** (`routes/worker.py:231`, indented under a route handler), so
  `services`/`services.external_api` are never imported at collection time. That is the
  exact and only reason `tests/errors/__init__.py` is silently safe today while
  `tests/services/__init__.py` is not — it is an accident of which imports happen to be
  eager vs. lazy in `routes/worker.py`, not a structural guarantee.

**Confirming the fix.** Adding `backend/tests/__init__.py` (in addition to the two new
`tests/services*/__init__.py` markers) and re-running collection:

```
457 tests collected in 0.16s   # 0 errors — same count as baseline
```

Verified directly via `_pytest.pathlib.resolve_pkg_root_and_module_name()`:

| Test file | Module name **before** fix | Module name **after** `tests/__init__.py` |
|---|---|---|
| `tests/services/external_api/test_athena_client.py` | `services.external_api.test_athena_client` (collides with prod `services.external_api`) | `tests.services.external_api.test_athena_client` |
| `tests/errors/test_codes.py` | `errors.test_codes` (collides with prod `errors`, currently masked by import-order luck) | `tests.errors.test_codes` |

With `tests/__init__.py` present, `resolve_package_path()`'s upward walk no longer stops
at `tests/` — it continues one level further and finds no `__init__.py` above `tests/`
(there is none in `backend/`), so `pkg_root` = `backend/` and every nested test package's
dotted name is correctly prefixed with `tests.`, structurally guaranteeing no collision
with any top-level production package, regardless of import order or which routes/
services happen to be eagerly vs. lazily imported elsewhere. This removes the fragility
for `tests/errors/__init__.py` too — it stops being a lucky accident and becomes
actually safe.

**Full-suite confirmation (not just collection).** Ran the entire suite (`pytest -q
--no-cov`) with the fix applied in the isolated copy: `449 passed, 8 failed`. The 8
failures are all in `tests/utils/test_html.py` (`RuntimeError`); confirmed by running the
same file against the **untouched real repo** that these 8 failures are pre-existing and
unrelated to this change (same failures, same count, with zero of the SP14 changes
applied). No new failures, no new errors, no count regression anywhere else in the
suite.

**Why other same-named directories (`care_plan`, `models`, `routes`, `utils` — all of
which exist as real top-level production packages too) are not at risk today:** none of
them have their own `__init__.py` under `tests/`, so `resolve_package_path()` finds no
package boundary at all for them and pytest falls back to
`module_name_from_path(path, root=config.rootpath)` (`_pytest/pathlib.py:768`), which
always derives the dotted name relative to the pytest rootdir (`backend/`) — i.e.
`tests.care_plan.test_x`, always safely prefixed. The collision class only exists for a
`tests/<name>/` directory that **has its own `__init__.py`** while `tests/` itself
doesn't. Today that set is `{errors, services, services/external_api}`. Adding
`tests/__init__.py` neutralizes the whole class permanently — including for any future
SP that adds an `__init__.py` to a new test subpackage sharing a name with a production
package.

### 4B. File changes

| File | Change |
|---|---|
| `backend/tests/__init__.py` | **New, empty file.** Roots the `tests` package so all nested test packages resolve as `tests.<subpkg>.<module>` instead of colliding with same-named top-level production packages. |
| `backend/tests/services/__init__.py` | **New, empty file.** The marker SP04 should have added; now safe because of the file above. |
| `backend/tests/services/external_api/__init__.py` | **New, empty file.** Same as above, one level deeper. |
| `backend/tests/errors/__init__.py` | **No change.** Already exists (empty, added in `062f7fcf`). Confirmed safe both before (by accident of import order) and after (structurally) this fix. Left in place — no reason to touch it. |
| `.github/workflows/ci.yml` | Add a `Run ruff lint` step in the existing `backend` job, sibling to the existing `Run backend tests` step (see §4C). |

No production code changes. No changes to `backend/pyproject.toml`'s `[tool.pytest.ini_options]`
or `[tool.ruff]` sections — `exclude = [".venv", "__pycache__", "tests"]` already excludes
`tests/` from ruff, so the new `__init__.py` files (and the existing one) are never linted;
adding them does not introduce any ruff surface to manage.

### 4C. CI Lint Gate

Add a step to `.github/workflows/ci.yml`'s `backend` job (currently lines 12-38), placed
immediately before the existing `Run backend tests` step so a lint failure surfaces
before the (slower) test run — same ordering principle as the rest of the job
(install → fast checks → tests):

```yaml
      - name: Run ruff lint
        working-directory: backend
        run: ruff check . --config pyproject.toml

      - name: Run backend tests
        working-directory: backend
        run: python -m pytest tests/ -q
```

This matches, verbatim, the invocation already documented in `backend/README.md:117-126`
(`ruff check . --config pyproject.toml`, run from `backend/`) and the args used by
`.pre-commit-config.yaml` (`--config, backend/pyproject.toml`, just expressed relative to
`backend/` since the step's `working-directory` is already `backend`). `ruff` is already
installed by the existing `Install dependencies` step (`pip install -r requirements.txt
-r requirements-dev.txt`, which includes `requirements-dev.txt:5`'s `ruff>=0.4,<0.5`) — no
new install step needed.

**Verified the gate would currently pass:** installed `ruff==0.4.10` (the exact pin) into
the backend venv and ran `ruff check . --config pyproject.toml` from `backend/` against
the real, current repo: `All checks passed!` (exit 0). The gate is safe to add today
without first having to fix any pre-existing violations.

---

## 5. API Change Summary

None. No route, request/response shape, or Firestore document changes.

---

## 6. Frontend Change Summary

N/A. This SP is backend-only (test infra + CI workflow).

---

## 7. Testing

**What to verify, not a task list:**

1. **Collection-count parity.** `pytest --collect-only -q` before and after must report
   the same total (457 today, plus any tests added by other in-flight SPs by the time
   this lands) with **0 errors**. A drop in count or any new collection error is a hard
   regression signal.
2. **No import shadowing regression for the production `services`/`errors` packages.**
   After adding the markers, run something that imports
   `services.external_api.athena_client` directly in a fresh interpreter (e.g. via
   `tests/services/external_api/test_athena_client.py` itself) and confirm it resolves
   to the real production module's `__file__` path (under `backend/services/`, not
   `backend/tests/`).
3. **Full suite run, not just collection.** `pytest tests/ -q` (matching CI's exact
   invocation) before and after — confirm identical pass/fail set. (Today's baseline has
   8 pre-existing, unrelated `tests/utils/test_html.py` failures; the fix must not change
   that set.)
4. **Ruff gate dry run.** `ruff check . --config pyproject.toml` from `backend/` must
   exit 0 against the current tree before merging the CI change — already confirmed
   (§4C). Re-verify at merge time in case other in-flight SPs (11/12/13) introduce
   violations; if so, fix those violations as part of landing this gate (do not weaken
   the rule set to paper over them).
5. **CI dry run.** After editing `ci.yml`, the next PR's CI run is the real integration
   test — confirm both the new `Run ruff lint` step and the existing `Run backend tests`
   step appear and pass in the Actions log.

No new test *files* are required by this SP — the deliverable is two empty `__init__.py`
markers plus a CI workflow edit. (`tests/services/external_api/test_athena_client.py`
already exists from SP04 and continues to exercise the path.)

---

## 8. Manual Intervention Required From You

None. This SP requires no environment variables, secrets, GCP console steps, or
migrations. The `__init__.py` additions are empty files; the CI edit takes effect on the
next push with no repo settings changes — confirmed (see §9 Q5) that no branch-protection
/ required-status-check configuration names individual CI steps, so no action is needed
since the `backend` job name is unchanged.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Should `tests/care_plan/`, `tests/models/`, `tests/routes/`, `tests/utils/`, `tests/integration/`, `tests/fixtures/` also get `__init__.py` markers for consistency with `tests/errors/` and the new `tests/services/`? | **[RESOLVED: no, not in this SP]** — they are not broken (no `__init__.py` today means no collision risk, per §4A), and `pyproject.toml`'s `testpaths = ["tests"]` + `--import-mode=importlib` works fine with the current mix of package and non-package test directories. Adding markers everywhere is a pure consistency nice-to-have with no functional benefit once `tests/__init__.py` exists, since the collision class is already closed for every current and future subdirectory. Leaving as [DEFERRED] for a future cleanup pass if a fully-uniform `tests/` package layout is ever desired. |
| Q2 | Does adding `backend/tests/__init__.py` interact with `pytest-cov`'s `--cov=.` addopt (e.g. could it now also try to measure coverage of the empty `__init__.py` files themselves, or change coverage roots)? | **[RESOLVED: no impact]** — `--cov=.` measures source under the invocation directory (`backend/`) including `tests/`; the new empty `__init__.py` files contribute 0 executable lines and do not change any existing module's coverage percentage. `[tool.ruff] exclude` already excludes `tests` so there's no ruff interaction either. |
| Q3 | Order of the new Ruff CI step relative to `Run backend tests` — lint-then-test vs. test-then-lint? | **[RESOLVED: lint before test]** — fast-fail principle; a lint error is cheaper to detect and fix than waiting for the full pytest run (~13s locally with coverage) to complete. No other ordering constraint exists since neither step depends on the other's output. |
| Q4 | Should the Ruff CI step also run for the `frontend` job (e.g. ESLint) as part of this SP? | **[RESOLVED: no]** — out of scope per Non-Goals; frontend linting is SP10's territory (already shipped/in-flight separately), and the task explicitly scopes this SP to the Ruff/backend gate only. |
| Q5 | Is there any branch-protection / required-status-check configuration outside this repo that names individual CI steps (rather than the job) that would need updating when this step is added? | **[RESOLVED: No — confirmed by the user, no branch-protection / required-status-check configuration names individual CI steps; nothing needs updating when the Ruff step is added.]** |

**Dependencies:** None — this SP is fully self-contained and can land independently of
SP11/SP12/SP13.
