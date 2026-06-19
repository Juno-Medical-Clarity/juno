# Tasks: Testing & CI Pipeline (SP6)

Read `PRD.md` in this folder first. **This sub-project lands LAST (Phase 3)** — every task assumes
the FINAL shapes from SP1–SP5 are merged. Where a name is uncertain (esp. SP2 route paths, SP1 model
API), the task notes the assumption; if reality differs, the fix is a one-line path/import edit.

**SP6 only adds/moves test files + one workflow + dev-dep/config changes. No source edits.**

---

### Task 1 — Add pytest config + shared `conftest.py` + fixtures dir

**Files:** `backend/pyproject.toml` (NEW), `backend/tests/conftest.py` (NEW),
`backend/tests/fixtures/__init__.py` + `backend/tests/fixtures/care_plan.py` (NEW),
`backend/tests/__init__.py` if needed.

1. Create `backend/pyproject.toml` with a `[tool.pytest.ini_options]` block:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   python_files = ["test_*.py"]
   addopts = "-ra"
   markers = [
     "integration: slower tests that exercise multiple layers",
   ]
   ```
2. Create `backend/tests/conftest.py` exactly per PRD §4.3 (sys.path bootstrap once; fixtures
   `app`, `client`, `auth_ok`, `fake_firestore`) **plus** the `parse_sse` helper from PRD §4.4.
   Import `all_blueprints` from `routes` (SP2 final list).
3. Create `backend/tests/fixtures/care_plan.py` exporting canonical sample dicts: a pipeline output
   dict, a `before_score`/`after_score` score dict (shape from `utils/scoring.score_text`), and a
   helper `fixed_output(label)` (lift the one in current `test_batch_route.py`).

**Acceptance:** `cd backend && python -m pytest tests/ -q` collects with no import errors from the new
folder layout; `parse_sse`, `app`, `client`, `auth_ok`, `fake_firestore` importable in tests.

---

### Task 2 — Create the `tests/` folder structure and MOVE existing files

**Action:** create `tests/models/`, `tests/utils/`, `tests/routes/`, `tests/simplify/`,
`tests/integration/` (each with `__init__.py` if the project uses package-style test dirs — match
whatever collection works after Task 1). Move files per the PRD §4.2 mapping table:

- `test_models_base.py` → `tests/models/test_base.py`
- `test_models.py` → split into `tests/models/test_metrics.py` + `tests/models/test_input.py`
- `test_grading_model.py` → `tests/models/test_grading_model.py`
- `test_scoring_methods.py` → `tests/utils/test_scoring_methods.py`
- `test_pdf_merge.py` → `tests/utils/test_pdf.py`
- `test_preset_data.py` → `tests/utils/test_preset_data.py`
- `test_save_output.py` → `tests/utils/test_save_output.py`
- `test_simplify_auth.py` → `tests/routes/test_care_plan_auth.py`
- `test_batch_route.py` → `tests/routes/test_batch_route.py`
- `test_dataset_routes.py` → `tests/routes/test_datasets_route.py`
- `test_saved_outputs_route.py` → `tests/routes/test_saved_outputs_route.py`
- `test_simplify_pipeline_executors.py` → `tests/simplify/test_pipeline_executors.py`
- `test_simplify_v1_2_persistence.py` → `tests/integration/test_care_plan_persistence.py`
- `test_container_startup.py` → `tests/integration/test_container_startup.py`
- **DELETE** `test_simplify_version_dispatch.py` (stale — SP2 removes per-version dispatch).

After moving, **fix the `sys.path` bootstrap** in each moved file: replace the per-file
`Path(__file__).resolve().parents[1]` blocks with reliance on `conftest.py` (delete the block, or
update `parents[N]` to the new depth). `parents` index changes because files are now one level deeper.

**Acceptance:** `python -m pytest tests/ -q` passes (same set of tests as before, just relocated);
`test_simplify_version_dispatch.py` is gone.

---

### Task 3 — Retarget moved route/pipeline tests to SP2 final names

**Files:** `tests/routes/test_care_plan_auth.py`, `tests/routes/test_batch_route.py`,
`tests/simplify/test_pipeline_executors.py`, `tests/integration/test_care_plan_persistence.py`.

1. Replace `/simplify` → `/care_plan` (and `/simplify/batch` → `/care_plan/batch` etc.) per SP2's
   final paths. **Assumption:** `/care_plan*`. If SP2 differs, use its paths.
2. In `test_care_plan_auth.py` keep the "legacy version endpoints 404" check, retargeted to assert
   `/simplify`, `/simplify/v1`, `/simplify/v1-1`, `/simplify/v1-2` all return 404 (proves SP2 removed
   them).
3. Update module-patch targets (`routes.simplify.*`) to the SP2 consolidated module name.
4. Use the `client` / `auth_ok` / `fake_firestore` / `parse_sse` fixtures instead of local helpers.

**Acceptance:** these tests pass against the SP2 route surface; no references to `simplify_v1`/`v1_1`/
`v1_2` route modules remain.

---

### Task 4 — Model tests to Pydantic (SP1) + new `care_plan` model test

**Files:** `tests/models/test_base.py`, `test_care_plan.py` (NEW), `test_grading_model.py`,
`test_input.py`, `test_metrics.py`.

For EVERY model add/confirm: (a) round-trip serialize↔deserialize, (b) `extra="forbid"` rejects an
unknown field (expect `ValidationError`), (c) a validation error on a bad field type, (d) for
`VersionedJsonModel` subclasses (`care_plan`): per-version dispatch (1.0/1.1/1.2 resolve to the right
class/shape). Use SP1's final API — `model_validate(...)` / `model_dump()` if Pydantic v2.

`tests/models/test_care_plan.py` is **NEW**: cover `CarePlan` + `CarePlanInternal` (SP1 names),
`from_pipeline_result`, version flattening on dump.

**Assumption:** SP1 keeps `JsonModel`/`VersionedJsonModel` base names. If renamed, update imports.

**Acceptance:** all 5 model test files pass; each model has the 4 assertion classes above; round-trip
is exact (`model_validate(model_dump()) == original`).

---

### Task 5 — New util tests (firebase, llm, scoring, term_detection, text_normalization, jargon_db)

**Files (all NEW):** `tests/utils/test_firebase.py`, `test_llm.py`, `test_scoring.py`,
`test_term_detection.py`, `test_text_normalization.py`, `test_jargon_db.py`. Also retarget
`tests/utils/test_pdf.py` to the merged `pdf` util (SP3) and add a `pdf_extract` case alongside the
existing merge case.

- **`test_firebase.py`** — patch `firebase_admin.firestore.client`; assert the helper returns the
  mocked db; cover the ownership/`_get_doc_or_403` helper (403 for wrong uid, doc for right uid).
- **`test_llm.py`** — patch the Gemini SDK call site (e.g. `google.genai` `models.generate_content`
  or SP3's wrapper); assert request shaping (prompt/model/params) and that a canned response parses to
  the expected dict; cover an error/exception path. **No network.**
- **`test_scoring.py`** — `score_text()` returns the documented dimension dict; `_grade_to_score`
  boundary values.
- **`test_term_detection.py`** — detects a known jargon term in sample text; empty list on plain text.
- **`test_text_normalization.py`** — normalization is idempotent; collapses whitespace/casing as specified.
- **`test_jargon_db.py`** — known-term lookup hit, unknown miss, DB loads without error.

**DO NOT** create tests for `vertex_ai`, `ocr`, `storage` (deleted by SP3).

**Acceptance:** all new util tests pass with zero network/credential access; deleted utils have no
test files.

---

### Task 6 — Code-markers test via `InMemorySink` (SP4)

**File:** `tests/utils/test_code_markers.py` (NEW).

Follow the `InMemorySink` pattern from `/root/projects/code_marker_sample/sinks.py`:
```python
def test_marker_emits_success_event():
    from <sp4_module> import CodeMarker          # SP4 final module path
    from <sp4_module>.sinks import InMemorySink
    sink = InMemorySink()
    marker = CodeMarker(name="care_plan.run", sink=sink)
    with marker:            # or marker.measure(...) / decorator — match SP4 API
        pass
    assert len(sink.events) == 1
    evt = sink.events[0]
    assert evt["name"] == "care_plan.run"
    assert evt["success"] is True
    assert "duration_ms" in evt and "dimensions" in evt
```
Add an exception case (`success is False` when the wrapped block raises) and a dimensions/nesting case.

**Assumption:** SP4 exposes a `CodeMarker` + a `sinks.InMemorySink` mirroring the sample. Match SP4's
final constructor/context-manager API.

**Acceptance:** events are captured in `sink.events` and asserted; no real sink/exporter invoked.

---

### Task 7 — New route tests: grading + health; pipeline happy-path + error tests

**Files (NEW):** `tests/routes/test_grading_route.py`, `tests/routes/test_health_route.py`,
`tests/simplify/test_pipeline_happy_path.py`, `tests/simplify/test_pipeline_errors.py`.

- **`test_grading_route.py`** (`POST /care_plan/grade`): (1) `grading_enabled=false` → response
  `grading.entries == []`, `enabled == false`; (2) `saved_id` path → `fake_firestore` doc's
  `output_data.grading` overwritten, returned; (3) `text`/`clarified_text` path → returns Grading,
  **no** Firestore write attempted (assert `db.collection(...).document(...).update` not called);
  (4) two runs → two different `graded_at`, second overwrites (no array growth).
- **`test_health_route.py`** — `GET /health` → 200 and expected body. **Assumption:** a `/health`
  route exists or is added by another SP; if not present, mark `@pytest.mark.skip` with a TODO and
  flag in the summary.
- **`test_pipeline_happy_path.py`** — inject a `FakePipeline` (pattern from
  `test_pipeline_executors.py`), run the consolidated route via SSE, `parse_sse`, assert terminal
  event has a valid `simplified_care_plan` + `grading`; progress events appear in order.
- **`test_pipeline_errors.py`** — force a stage to raise; assert an **error event** is streamed (not a
  500 mid-stream) and the fallback path behaves as designed.

**Acceptance:** all four files pass; grading overwrite + no-write assertions hold; SSE error path
produces a structured error event.

---

### Task 8 — Frontend: install RTL/jsdom, wire Vitest, add component + util + api tests

**Files:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/vitest.setup.ts` (NEW), plus
the test files in PRD §6.

1. Add devDependencies: `@testing-library/react`, `@testing-library/jest-dom`,
   `@testing-library/user-event`, `jsdom`. Run `npm install` in `frontend/` to update the lockfile
   (CI uses `npm ci`, so the lockfile MUST be committed).
2. Add the `test` block to `vite.config.ts` (`environment: 'jsdom'`, `globals: true`,
   `setupFiles: ['./vitest.setup.ts']`) per PRD §4.6. Add `vitest.setup.ts` importing
   `@testing-library/jest-dom/vitest`.
3. New util tests: `src/utils/grading.test.ts` (selectors — combined→PatientScore, 6 method entries,
   empty→null/[]), `src/utils/outputVersion.test.ts`, `src/utils/buildPdfHtml.test.ts`.
4. New api tests: `src/api/apiClient.test.ts` (throws when signed-out via mocked `firebaseAuth`; sets
   `Authorization: Bearer <token>`; mock `fetch`), `src/api/savedOutputs.test.ts`.
5. New component tests (RTL): `src/components/ConfigurationCard.test.tsx`,
   `src/components/OutputGradingCard.test.tsx`, `src/components/AppointmentNoteV12View.test.tsx`
   (smoke: combined + method cards render when grading present; nothing when entries empty). Mock
   `./api/firebase` and `fetch` globally so no real SDK loads.
6. **Drop / do not write** tests against `pages/v1`, `pages/v1_1`, `pages/v1_2` (removed by SP5). Keep
   `router.test.ts`, `normalizeOutput.test.ts`, `groupSavedOutputs.test.ts`.

**Acceptance:** `cd frontend && npm run test` runs all `.test.ts(x)` green under jsdom; component tests
render via RTL without a real Firebase/network call; lockfile updated and committed.

---

### Task 9 — CI workflow: `ci.yml` (backend pytest + frontend vitest on PR to main)

**File:** `.github/workflows/ci.yml` (NEW). Conventions matched from existing workflows: Ubuntu,
`actions/checkout@v4`, Node 20 + npm cache (from `deploy-frontend.yml`), Python 3.12 (repo venv).

```yaml
name: CI

on:
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    env:
      # Dummy values so import-time config reads don't crash. NO real creds — all
      # external services (Firestore, Gemini, GCS) are mocked in the tests.
      GEMINI_API_KEY: test-key
      GCP_PROJECT_ID: test-project
      GCP_LOCATION: us-central1
      FIRESTORE_DATABASE_ID: "(default)"
      SIMPLIFY_DEFAULT_VERSION: v1-2
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          # test-only deps (move to requirements-dev.txt if preferred):
          pip install pytest pytest-cov reportlab pypdf

      - name: Run backend tests
        working-directory: backend
        run: python -m pytest tests/ -q

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: frontend

      - name: Run frontend tests
        run: npm run test
        working-directory: frontend
```

Notes:
- Two parallel jobs → both check names (`backend`, `frontend`) become selectable as required checks.
- `reportlab`/`pypdf` are needed by `test_pdf.py` — confirm they're in `requirements.txt`; if not,
  either add them there or to a new `backend/requirements-dev.txt` and `pip install -r` it.
- No `secrets:` block — tests need none.

**Acceptance:** opening a PR to `main` triggers `CI` with both jobs; both go green on a clean tree;
introducing a failing test turns the relevant job red and blocks (once branch protection is on).

---

### Task 10 — (Optional) coverage reporting

**Files:** `backend/pyproject.toml`, `frontend/vite.config.ts`, `ci.yml`.

If the owner wants coverage (Open Q §3): add `--cov=. --cov-report=term-missing` to the pytest
`addopts` and Vitest `coverage` (`@vitest/coverage-v8` devDep). Start **reporting-only** (no
`--cov-fail-under`); ratchet a threshold in a later PR once a baseline exists.

**Acceptance:** coverage summary printed in CI logs for both jobs; no build fails purely on coverage
(until a threshold is intentionally added).

---

## Summary of what requires you (not a dev agent)

1. **Enable branch protection on `main`** and mark the `CI` workflow's `backend` + `frontend` jobs as
   **required** status checks (GitHub → Settings → Branches). The workflow file cannot make itself
   required — this toggle is yours. Merge `ci.yml` first so the check names appear in the dropdown.
2. **Confirm CI needs no secrets** (default: all external services mocked, no Firebase emulator). Say
   so if you want CI to hit real Firebase/Gemini instead (adds secrets + scope).
3. **Confirm CI target versions** — Python 3.12, Node 20 (matched from repo venv +
   `deploy-frontend.yml`). And confirm whether test deps (`pytest`, `pytest-cov`, `reportlab`,
   `pypdf`) go in `requirements.txt` or a new `requirements-dev.txt`.
4. **Confirm SP2 final route paths** (assumed `/care_plan*`) — if different, route-test path strings
   need a one-line update (Tasks 3, 7).
5. **Decide coverage policy** (Task 10): reporting-only now, or enforce a threshold.
