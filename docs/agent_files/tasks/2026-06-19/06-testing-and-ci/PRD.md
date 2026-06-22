# PRD: Testing & CI Pipeline (SP6)

Sub-project 6 of 6. **Phase 3 — lands LAST.** This sub-project locks in the final shapes produced
by SP1–SP5 by reorganizing the test suite, filling coverage gaps, and adding a required CI gate on
every PR to `main`.

**Hard dependency on the FINAL shapes of:**
- **SP1** — Pydantic models (`care_plan`, `grading`, `input`, `metrics`, `base`). Tests target the
  final Pydantic API (`model_validate` / `model_dump`, `extra="forbid"`), not the current
  dataclass `to_dict`/`from_dict`. **Assumption:** SP1 keeps `JsonModel`/`VersionedJsonModel` as the
  base names (current code uses these); if SP1 renames them, update imports in `tests/models/`.
- **SP2** — consolidated care-plan route. Tests must target **`/care_plan`** (and whatever the final
  blueprint/handler names are), NOT `/simplify`. The route mounts at `/care_plan` with a single SSE
  handler replacing `simplify.py` + `simplify_v1_1.py` + `simplify_v1_2.py`.
  **[RESOLVED — owner: SP2 route paths are LOCKED.]** Use the SP2-defined paths exactly as SP2 defines
  them; do not re-litigate or change them. The assumed `/care_plan*` paths are settled.
- **SP3** — utils deleted/merged. **Do NOT write tests for `vertex_ai`, `ocr`, `storage`** (deleted).
  `pdf_extract` + `pdf_merge` → merged into a single `pdf` util; `gemini_client` → `llm`/`gemini`;
  `firebase` helper consolidated. Tests target the merged modules.
- **SP4** — code-markers module + sink. Tested via an **`InMemorySink`** (pattern from
  `/root/projects/code_marker_sample/sinks.py`) so emitted events can be asserted without a live sink.
- **SP5** — frontend pages renamed/removed. Test the care-plan pages; **drop** any test that targets
  the removed `v1`/`v1_1`/`v1_2` page components. `router.test.ts` already only tests `versionPath`
  (a pure helper) — keep but revisit once SP5 finalizes the route table.

## 1. Problem

The backend `tests/` folder is **flat** (~16 files, mixed `unittest.TestCase` style) and several files
reference the soon-to-be-removed `simplify`/`v1`/`v1_1` surface (`test_simplify_auth.py`,
`test_simplify_version_dispatch.py`, `test_simplify_pipeline_executors.py`,
`test_simplify_v1_2_persistence.py`). There is **no pytest config** (no `pytest.ini`/`pyproject.toml`/
`setup.cfg`), **no `conftest.py`** in the project, and every test re-implements the same `sys.path`
bootstrap and `create_app()` helper by hand. Coverage is uneven — some models/utils/routes are well
tested, others (e.g. `text_normalization`, `term_detection`, `jargon_db`, `health`, the SP4
code-markers) have none.

The frontend uses **Vitest** (3 existing `.test.ts` files) but has **no React Testing Library**, **no
jsdom**, and **no `vitest.setup`** — so it cannot currently test components, only pure functions.

There is **no CI workflow that runs tests.** `.github/workflows/` has only deploy/rollback/tag
workflows (all triggered on `push` to `deploy`). Nothing gates a PR to `main`. Bugs in the refactor
land in `main` unverified.

## 2. Goals

1. **Group** `backend/tests/` into folders mirroring source layout: `tests/models/`, `tests/routes/`,
   `tests/utils/`, `tests/simplify/` (the care-plan pipeline), `tests/integration/`, plus a shared
   `tests/conftest.py` and `tests/fixtures/`.
2. **Every model tested** (post-SP1 Pydantic): round-trip serialize/deserialize, strict
   `extra="forbid"` rejection, per-version dispatch (for `VersionedJsonModel`), validation errors.
   Models: `care_plan` (CarePlan/CarePlanInternal), `grading`, `input`, `metrics`, `base`.
3. **Every (surviving) util tested**: `pdf` (merged), `firebase`, `llm`/`gemini`, `scoring`,
   `scoring_methods`, `term_detection`, `text_normalization`, `jargon_db`, `preset_data`, and the
   **code-markers module + sink (via `InMemorySink`)**. Explicitly **no** tests for deleted
   `vertex_ai`/`ocr`/`storage`.
4. **Every route tested**: consolidated `/care_plan` (SP2), `batch`, `datasets`, `grading`,
   `saved_outputs`, `health`. SSE routes use a streaming-aware test approach (below).
5. **Ample backend coverage** of the full care-plan pipeline: happy path + error/fallback paths.
6. **Frontend basic testing** — Vitest + React Testing Library (NON-Playwright, per owner). Cover key
   components, utils (`normalizeOutput`, `groupSavedOutputs`, grading selectors), api client, router.
7. **CI**: a new GitHub Actions workflow running backend (pytest) + frontend (vitest) on **every PR
   to `main`**, designed to be made a **required** check (the branch-protection toggle itself is a
   manual step — see §8).

## 3. Non-Goals

- **No Playwright / e2e / browser tests** (owner: "non-playwright testing, just basic testing").
- **No live external services in CI** — Gemini/Vertex, Firebase/Firestore, and GCS are all mocked or
  faked; CI uses no real credentials (see §4 mocking strategy + §9). **Unit tests only — no live
  integration tests now** (RESOLVED §9.2). The `tests/integration/` folder holds mock-based,
  multi-layer tests (firebase patched, no network), not live-service tests.
- **Not rewriting source.** This is planning + test/CI only. (SP6 only adds/moves/rewrites test files,
  one workflow, and dev-dep/config — no app-logic source edits. The import-style standardization
  RESOLVED §9.4 is the one exception: it normalizes import statements across source + tests to the
  `8095933` convention.)
- **Not enforcing a hard coverage % threshold** — coverage is REPORTING ONLY (RESOLVED §9.3).
- **No load/perf testing.**

## 4. Architecture Decisions

### 4.1 New `tests/` folder layout

```
backend/
├── pyproject.toml            # NEW — pytest config (testpaths, markers, rootdir)
└── tests/
    ├── conftest.py           # NEW — shared fixtures: app/client, auth bypass, firestore mock, fake LLM
    ├── fixtures/             # NEW — sample care-plan dicts, pipeline outputs, score dicts, PDFs
    │   ├── __init__.py
    │   ├── care_plan.py
    │   └── sample.pdf
    ├── models/
    │   ├── test_base.py
    │   ├── test_care_plan.py
    │   ├── test_grading_model.py
    │   ├── test_input.py
    │   └── test_metrics.py
    ├── utils/
    │   ├── test_pdf.py
    │   ├── test_firebase.py
    │   ├── test_llm.py
    │   ├── test_scoring.py
    │   ├── test_scoring_methods.py
    │   ├── test_term_detection.py
    │   ├── test_text_normalization.py
    │   ├── test_jargon_db.py
    │   ├── test_preset_data.py
    │   ├── test_save_output.py
    │   └── test_code_markers.py     # NEW (SP4) — InMemorySink assertions
    ├── routes/
    │   ├── test_care_plan_route.py  # was test_simplify_* (renamed/rewritten for SP2)
    │   ├── test_care_plan_auth.py
    │   ├── test_batch_route.py
    │   ├── test_datasets_route.py
    │   ├── test_grading_route.py
    │   ├── test_saved_outputs_route.py
    │   └── test_health_route.py     # NEW
    ├── simplify/                    # the care-plan PIPELINE (utils/simplify/v1_2)
    │   ├── test_pipeline_happy_path.py
    │   ├── test_pipeline_errors.py     # error/fallback paths
    │   └── test_pipeline_executors.py  # was test_simplify_pipeline_executors
    └── integration/
        ├── test_care_plan_persistence.py  # was test_simplify_v1_2_persistence
        └── test_container_startup.py      # was test_container_startup
```

### 4.2 Old → new test-file mapping

| Current flat file (`backend/tests/`)     | New location                                    | Action |
|------------------------------------------|-------------------------------------------------|--------|
| `test_models_base.py`                    | `tests/models/test_base.py`                      | Move; update to Pydantic (SP1) |
| `test_models.py` (Metrics + Input)       | split → `tests/models/test_metrics.py`, `tests/models/test_input.py` | Split + move; update to Pydantic |
| `test_grading_model.py`                  | `tests/models/test_grading_model.py`             | Move; keep `build_grading` tests; Pydantic round-trip |
| *(no care_plan model test today)*        | `tests/models/test_care_plan.py`                 | **NEW** — CarePlan/CarePlanInternal (SP1) |
| `test_scoring_methods.py`                | `tests/utils/test_scoring_methods.py`            | Move (no change) |
| *(no scoring test today)*                | `tests/utils/test_scoring.py`                    | **NEW** — `score_text`, `_grade_to_score` |
| `test_pdf_merge.py`                      | `tests/utils/test_pdf.py`                        | Move + rename → merged `pdf` util (SP3); add pdf_extract cases |
| `test_preset_data.py`                    | `tests/utils/test_preset_data.py`                | Move (no change) |
| `test_save_output.py`                    | `tests/utils/test_save_output.py`                | Move (no change) |
| *(none)*                                 | `tests/utils/test_firebase.py`                   | **NEW** — firebase helper (SP3) |
| *(none)*                                 | `tests/utils/test_llm.py`                        | **NEW** — `llm`/`gemini` client (SP3), mocked |
| *(none)*                                 | `tests/utils/test_term_detection.py`             | **NEW** |
| *(none)*                                 | `tests/utils/test_text_normalization.py`         | **NEW** |
| *(none)*                                 | `tests/utils/test_jargon_db.py`                  | **NEW** |
| *(none)*                                 | `tests/utils/test_code_markers.py`               | **NEW** (SP4) — InMemorySink |
| `test_simplify_auth.py`                  | `tests/routes/test_care_plan_auth.py`            | Move + retarget `/simplify`→`/care_plan` (SP2) |
| `test_simplify_version_dispatch.py`      | **DELETE** (or fold a "legacy paths 404" check into `test_care_plan_auth.py`) | Stale — version dispatch removed by SP2 |
| `test_batch_route.py`                    | `tests/routes/test_batch_route.py`               | Move; retarget paths if SP2 renames `/simplify/batch` |
| `test_dataset_routes.py`                 | `tests/routes/test_datasets_route.py`            | Move (no change) |
| `test_saved_outputs_route.py`            | `tests/routes/test_saved_outputs_route.py`       | Move (no change) |
| *(none)*                                 | `tests/routes/test_grading_route.py`             | **NEW** — `POST /care_plan/grade` (SP-grading) |
| *(none)*                                 | `tests/routes/test_health_route.py`              | **NEW** |
| `test_simplify_pipeline_executors.py`    | `tests/simplify/test_pipeline_executors.py`      | Move; retarget to SP2 module names |
| *(none)*                                 | `tests/simplify/test_pipeline_happy_path.py`     | **NEW** |
| *(none)*                                 | `tests/simplify/test_pipeline_errors.py`         | **NEW** — error/fallback |
| `test_simplify_v1_2_persistence.py`      | `tests/integration/test_care_plan_persistence.py`| Move + retarget to SP2 module |
| `test_container_startup.py`              | `tests/integration/test_container_startup.py`    | Move (no change) |

> **Stale-test flag:** `test_simplify_version_dispatch.py` exists only to prove `/simplify` dispatches
> by `version` form field to `simplify_v1`/`v1_1`/`v1_2`. SP2 collapses those into one route, so this
> test becomes meaningless and is **deleted**. `test_simplify_auth.py`'s
> `test_old_version_endpoints_do_not_exist` (asserts `/simplify/v1` → 404) is still valuable — keep it,
> retargeted, to prove the legacy paths stay gone.

### 4.3 Shared `conftest.py` — eliminate the per-file bootstrap

Every current test repeats this:
```python
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
```
With nested folders the `parents[1]` index breaks. Centralize it. `tests/conftest.py` (pytest auto-
discovers it at the package root; `rootdir` set via `pyproject.toml`) puts `BACKEND_DIR` and
`PROJECT_DIR` on `sys.path` once, and exposes shared fixtures:

```python
# backend/tests/conftest.py
import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for p in (PROJECT_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from flask import Flask
from routes import all_blueprints   # SP2 final blueprint list


@pytest.fixture
def app():
    app = Flask(__name__)
    for bp in all_blueprints:
        app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_ok(monkeypatch):
    """Bypass Firebase auth: any Bearer token resolves to a fixed uid."""
    monkeypatch.setattr("utils.auth.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def fake_firestore(monkeypatch):
    """Patch firestore.client() to a MagicMock; return it for per-test wiring."""
    from unittest.mock import MagicMock
    db = MagicMock()
    monkeypatch.setattr("firebase_admin.firestore.client", lambda *a, **k: db)
    return db
```

> **[RESOLVED — owner: convert ALL tests to pytest style.]** Existing tests are `unittest.TestCase`
> style. They are **all converted** to pytest function style (no `unittest.TestCase` subclasses
> remain): `setUp` → fixtures, `self.assertEqual(a, b)` → `assert a == b`, `assertRaises` →
> `pytest.raises`, etc. New and converted tests use the shared fixtures (`app`, `client`, `auth_ok`,
> `fake_firestore`, `parse_sse`).
>
> **[RESOLVED — owner: import-style standard.]** Standardize the whole codebase/tests on the
> convention adopted in commit `8095933` ("Cors issue fix", which fixed a container/deploy import
> failure): import from the **ROOT package path** — `from models.X import …` and `from utils.X import …`
> (NEVER `from backend.models.X`/`from backend.utils.X`) — and use **relative imports within a
> package** (e.g. inside `backend/models/envelope.py`: `from .base import JsonModel`). `conftest.py`
> puts `BACKEND_DIR` on `sys.path` so `models.*`/`utils.*` resolve. All `from backend.…` imports in
> tests are rewritten to this convention.

### 4.4 Testing approach for SSE-streaming routes

The care-plan route (SP2) and `batch` stream Server-Sent Events. The existing `test_batch_route.py`
already nails the pattern — **reuse and promote it to `conftest.py`** as a shared helper:

```python
# in conftest.py
import json

def parse_sse(response):
    """Split an SSE response body into a list of parsed JSON event payloads."""
    text = response.get_data(as_text=True) if hasattr(response, "get_data") else response
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: ")
        events.append(json.loads(block.removeprefix("data: ")))
    return events
```

Approach: Flask's `test_client()` buffers the full streamed response, so a test issues the POST,
reads `response.get_data()`, runs `parse_sse`, and asserts on the **sequence** of events (e.g.
progress events → final result event; or an error event on the fallback path). The pipeline itself is
replaced by a `FakePipeline` (see `test_simplify_pipeline_executors.py` / `..._persistence.py` —
they already inject fakes via `patch`), so no LLM call happens. This keeps SSE tests deterministic and
fast. Assert: (a) the terminal event carries the expected `simplified_care_plan`/`grading` shape,
(b) intermediate progress events appear in order, (c) on a forced pipeline exception, an error event
is emitted rather than a 500 with a half-stream.

### 4.5 Mocking external services (CRITICAL — no live creds in CI)

| Service | How it's mocked in tests |
|---------|--------------------------|
| **Firebase Auth** (`utils.auth.auth.verify_id_token`) | `auth_ok` fixture / `@patch` returning `{"uid": ...}`. Already the established pattern. |
| **Firestore** (`firebase_admin.firestore.client`) | `fake_firestore` fixture → `MagicMock`; tests wire `db.collection().where().order_by().stream.return_value = iter([...])` and `.document().get()/.set()/.update()`. Established in `test_saved_outputs_route.py` / `test_save_output.py`. |
| **Gemini / LLM** (SP3 `llm`/`gemini`) | Patch the client call site to a fake returning canned text/JSON. Pipeline tests inject a `FakePipeline` so no client is constructed. `tests/utils/test_llm.py` patches the SDK transport (e.g. `google.genai` `models.generate_content`) and asserts request shaping + response parsing, never hitting the network. |
| **Vertex AI** | N/A — `vertex_ai` util is **deleted by SP3**. No tests. |
| **GCS / Storage** | N/A — `storage` util **deleted by SP3**. (If any surviving code touches a bucket, patch `google.cloud.storage.Client`.) |
| **Firebase app init** (`config.initialize_firebase`) | `@patch("config.initialize_firebase", return_value=None)` — already used in `test_container_startup.py`. |
| **Code-markers sink** (SP4) | Construct the marker with an `InMemorySink`; assert `sink.events` contains the expected `{name, duration_ms, success, dimensions}` dicts. No external sink. |

**Net:** CI needs **no GCP/Firebase/Gemini credentials at all.** Set dummy env vars in CI so any
import-time config read doesn't crash (e.g. `GEMINI_API_KEY=test`, `GCP_PROJECT_ID=test`,
`FIRESTORE_DATABASE_ID=(default)`).

> **[RESOLVED — owner: unit tests only; mock/stub all external services; NO live calls and NO
> integration tests now.]** Gemini/Vertex and Firestore are always mocked/stubbed — tests make **no**
> real API/network calls. Live integration tests are explicitly out of scope for now (may revisit
> later).
> **[RESOLVED — owner: Firebase emulator NOT required now]** (may add later). Pure mocks only; no
> emulator step in CI.
> **[RESOLVED — owner: no CI secrets now]** (maybe later). No secret-dependent CI steps.

### 4.6 Frontend test stack

Frontend already has Vitest 4 and `"test": "vitest run"`. To test components we add (devDeps):
`@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`. Then
wire Vitest into `vite.config.ts` (merge a `test` block) and add a setup file:

```ts
// vite.config.ts  — add a test block (uses vitest's defineConfig augmentation)
/// <reference types="vitest/config" />
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    css: false,
  },
  // ...existing server/build
})
```
```ts
// frontend/vitest.setup.ts  — NEW
import '@testing-library/jest-dom/vitest';
```
Firebase is mocked with `vi.mock('./api/firebase', ...)` so `apiClient`/auth tests never touch a real
SDK. `fetch` is stubbed via `vi.spyOn(globalThis, 'fetch')`.

### 4.7 CI workflow design

New workflow `.github/workflows/ci.yml`, trigger `pull_request` → `main`, two parallel jobs
(`backend`, `frontend`) matching existing-workflow conventions (Ubuntu runner, `actions/checkout@v4`,
`npm ci` + npm cache keyed on `frontend/package-lock.json` per `deploy-frontend.yml`).
Backend job adds `actions/setup-python@v5` (Python **3.12**, matching the repo's `.venv/.../python3.12`)
with pip cache. Full sample YAML in §7 / TASKS Task 9. Concurrency-cancel stale runs per branch. No
secrets needed — all external services mocked; only dummy env vars set inline.

> **[RESOLVED — owner: use Node 24 in CI.]** The owner repeatedly sees GitHub Actions' "Node.js 20 is
> deprecated" warning (actions/checkout@v4, google-github-actions/auth@v2, deploy-cloudrun@v2,
> setup-gcloud@v2 run on the Node 24 runtime). Target **Node 24** in `ci.yml`'s `actions/setup-node@v4`
> (`node-version: '24'`). Python stays **3.12**.

## 5. API Change Summary

**N/A — confirmed.** SP6 introduces no API changes. It only consumes the final API surface from SP2
(`/care_plan`, `/care_plan/grade`, `/care_plan/batch`, `/care_plan/saved`, `/datasets`, `/health`).
Route tests assert the *final* paths; if SP2's final names differ from the assumed `/care_plan*`,
update the path strings in `tests/routes/` (single-line edits, flagged in Open Questions).

## 6. Frontend Change Summary

Test-only additions (no app source changes). Plan:

| Target | File | What's covered |
|--------|------|----------------|
| `versionPath` router helper | `src/router.test.ts` *(exists)* | Keep; revisit after SP5 finalizes routes |
| `normalizeSimplifyOutput` | `src/utils/normalizeOutput.test.ts` *(exists)* | Keep |
| `groupSavedOutputs` | `src/utils/groupSavedOutputs.test.ts` *(exists)* | Keep |
| grading selectors (`patientScoreFromGrading`, `methodEntriesFromGrading`) | `src/utils/grading.test.ts` **NEW** | combined→PatientScore reconstruction; 6 method entries per target; empty-entries → null/[] |
| `outputVersion` helper | `src/utils/outputVersion.test.ts` **NEW** | version normalization |
| `buildPdfHtml` | `src/utils/buildPdfHtml.test.ts` **NEW** | HTML assembled from a sample output |
| `apiClient.authenticatedFetch` | `src/api/apiClient.test.ts` **NEW** | throws when signed-out; sets `Authorization: Bearer <token>`; mock `firebaseAuth` + `fetch` |
| `savedOutputs` api | `src/api/savedOutputs.test.ts` **NEW** | request shaping + response parse (mock fetch) |
| `ConfigurationCard` | `src/components/ConfigurationCard.test.tsx` **NEW** (RTL) | renders fields; grading checkbox toggles `onGradingEnabledChange` |
| `OutputGradingCard` | `src/components/OutputGradingCard.test.tsx` **NEW** (RTL) | "Run Grading" button renders; click calls fetch + `onGraded` with mocked response |
| `AppointmentNoteV12View` | `src/components/AppointmentNoteV12View.test.tsx` **NEW** (RTL, smoke) | renders combined + method cards when grading present; nothing when entries empty |
| router (top-level) | `src/router.tsx` covered by smoke render of `App` | care-plan route resolves; **drop** v1/v1_1/v1_2 page assertions (SP5 removes those pages) |

> **SP5 dependency:** `pages/v1`, `pages/v1_1`, `pages/v1_2` are removed by SP5. Do not write tests
> against them. Component tests target `pages/simplify/SimplifyPage.tsx` and the care-plan view.

## 7. Testing (coverage matrix)

### Models (SP1 — Pydantic; each: round-trip, `extra="forbid"` reject, validation error; versioned: per-version dispatch)
| Model | Test file | Key assertions |
|-------|-----------|----------------|
| `base` (JsonModel/VersionedJsonModel) | `tests/models/test_base.py` | round-trip; unknown field rejected; version registry dispatch |
| `care_plan` (CarePlan/CarePlanInternal) | `tests/models/test_care_plan.py` | round-trip; per-version (1.0/1.1/1.2) dispatch; extra forbidden; from_pipeline_result |
| `grading` (Grading/GradingEntry) | `tests/models/test_grading_model.py` | empty `Grading()` default; round-trip; `build_grading` → 14 entries; combined has `dimensions` |
| `input` (Input/InputFile) | `tests/models/test_input.py` | round-trip; file list; validation error on bad shape |
| `metrics` (Metrics) | `tests/models/test_metrics.py` | `Metrics.start()` shape; round-trip; tz-aware timestamps |

### Utils (deleted: `vertex_ai`, `ocr`, `storage` — NO tests)
| Util | Test file | Key assertions |
|------|-----------|----------------|
| `pdf` (merged extract+merge, SP3) | `tests/utils/test_pdf.py` | merge pdf+txt → combined; extract text from generated PDF |
| `firebase` (SP3) | `tests/utils/test_firebase.py` | client helper returns mocked db; ownership/`_get_doc_or_403` helper |
| `llm`/`gemini` (SP3) | `tests/utils/test_llm.py` | request shaping; parse JSON response; error path — all mocked, no network |
| `scoring` | `tests/utils/test_scoring.py` | `score_text` shape; `_grade_to_score` boundaries |
| `scoring_methods` | `tests/utils/test_scoring_methods.py` | 6 method keys; scores in [0,100]; SMOG <30 sentences → insufficient_sample |
| `term_detection` | `tests/utils/test_term_detection.py` | detects known jargon; empty on plain text |
| `text_normalization` | `tests/utils/test_text_normalization.py` | whitespace/casing normalization idempotent |
| `jargon_db` | `tests/utils/test_jargon_db.py` | lookup hit/miss; DB loads |
| `preset_data` | `tests/utils/test_preset_data.py` | groups DocConv inputs (existing test) |
| `save_output` | `tests/utils/test_save_output.py` | strips raw; tz-aware datetimes; uuid id (existing) |
| **code-markers + sink (SP4)** | `tests/utils/test_code_markers.py` | with `InMemorySink`: success path emits `{name,duration_ms,success:True,dimensions}`; exception path emits `success:False`; nesting/context |

### Routes (SSE via `parse_sse`)
| Route | Test file | Key assertions |
|-------|-----------|----------------|
| `/care_plan` (SP2) | `tests/routes/test_care_plan_route.py`, `test_care_plan_auth.py` | 401 w/o auth; legacy `/simplify/v1*` → 404; SSE event sequence; final event shape |
| `/care_plan/batch` | `tests/routes/test_batch_route.py` | 401 w/o auth; SSE per-item events; batch_group_id |
| `/datasets` | `tests/routes/test_datasets_route.py` | list/serve preset datasets |
| `/care_plan/grade` | `tests/routes/test_grading_route.py` | `grading_enabled=false`→empty entries; saved_id path overwrites Firestore; text/clarified_text path no write; 2 runs → 2 graded_at |
| `/care_plan/saved` | `tests/routes/test_saved_outputs_route.py` | list w/ + w/o batch_group_id; ownership 403 |
| `/health` | `tests/routes/test_health_route.py` | 200 + `{"status":"ok"}` (or final shape) |

### Pipeline (care-plan)
| Path | Test file | Key assertions |
|------|-----------|----------------|
| executors | `tests/simplify/test_pipeline_executors.py` | each stage executor called with right args (FakePipeline) |
| happy path | `tests/simplify/test_pipeline_happy_path.py` | end-to-end FakePipeline → valid `simplified_care_plan` + grading |
| error/fallback | `tests/simplify/test_pipeline_errors.py` | stage exception → fallback/error event, not crash |
| persistence | `tests/integration/test_care_plan_persistence.py` | result saved to (mock) Firestore w/ correct doc shape; doc_id source not persisted |
| startup | `tests/integration/test_container_startup.py` | `app` imports under backend workdir w/ firebase init patched |

### Frontend — see §6 matrix.

## 8. Manual Intervention Required From You

1. **Enable branch protection on `main`** — **[RESOLVED: DONE. Owner has already enabled branch
   protection on `main`.]** Kept here for reference as an already-completed step. Once `ci.yml` has run
   at least once on a PR, the `backend` / `frontend` check names appear in the GitHub Settings →
   Branches dropdown and can be marked **required** (the protection rule itself is in place). No
   further human action needed beyond selecting the new check names after the first CI run.
2. **No CI secrets needed** — **[RESOLVED: confirmed, no secrets now (maybe later).]** All external
   services are mocked; there are **no secret-dependent CI steps**. (If real Firebase/Gemini in CI is
   ever wanted, that adds `GEMINI_API_KEY` / `firebase-service-account` secrets and is out of scope.)
3. **Firebase emulator** — **[RESOLVED: NOT required now (maybe later).]** Default plan = pure mocks;
   no emulator step in CI.
4. **CI target versions** — **[RESOLVED: Python 3.12 + Node 24.]** Python 3.12 (repo venv); Node 24
   (resolves the recurring "Node.js 20 is deprecated" Actions warning).
5. **Test-dependency location** — **[RESOLVED (2026-06-20): separate `backend/requirements-dev.txt`.]**
   Test/dev-only deps (`pytest`, `pytest-cov`, `reportlab`, `pypdf`) live in a new
   `backend/requirements-dev.txt`, **not** in `backend/requirements.txt`. This keeps the Cloud Run
   production image lean (test + PDF-generation deps are never shipped to prod). CI installs both
   (`pip install -r requirements.txt -r requirements-dev.txt`); the deploy build installs only
   `requirements.txt`.

## 9. Open Questions & Decisions

1. **Final SP2 route paths.** Assumed `/care_plan`, `/care_plan/grade`, `/care_plan/batch`,
   `/care_plan/saved`.
   **[RESOLVED — owner: SP2 route paths are LOCKED. Do not re-litigate or change them; proceed exactly
   as SP2 defines. The assumed `/care_plan*` paths are settled.]**
2. **Mocking Gemini/Vertex + Firestore in CI (no live creds).** Plan = monkeypatch SDK call sites +
   `MagicMock` Firestore (§4.5). Alternative: Firebase emulator.
   **[RESOLVED — owner: mock/stub all external services; NO live calls and NO integration (live) tests
   now (maybe later). Unit tests only. No Firebase emulator. No CI secrets.]**
3. **Coverage threshold.** Add `--cov-fail-under=N` gate, or just report?
   **[RESOLVED — owner: REPORTING ONLY for now — no enforced gate/threshold. Coverage is printed but
   never fails the build.]**
4. **Import-style standardization.** Current tests mix `from backend.models...` and `from models...`.
   **[RESOLVED — owner: standardize on the convention from commit `8095933`: ROOT package path
   `from models.X` / `from utils.X` (NOT `backend.models.X`/`backend.utils.X`), and RELATIVE imports
   within a package (`from .base import JsonModel`). Adopt/streamline across codebase + tests; rewrite
   all `from backend.…` test imports. A dedicated task enforces/verifies this (incl. the
   `test_container_startup.py` added in that commit, which catches the container/deploy import break
   this convention fixes).]**
5. **Test data / fixtures.** `tests/fixtures/` shared across model/route/pipeline tests.
   **[RESOLVED — owner: approach is good — keep. Canonical sample dicts + sample PDF live in
   `tests/fixtures/`.]**
6. **`unittest` vs pytest style.**
   **[RESOLVED — owner: CONVERT ALL tests to pytest function style. No `unittest.TestCase` subclasses
   remain.]**
7. **SSE in CI determinism.** Flask `test_client` buffers the full stream, so `parse_sse` is reliable;
   no async timing involved.
   **[RESOLVED — owner: yes, use the proposed deterministic approach (buffered `test_client` +
   `parse_sse`, FakePipeline injection so no LLM call). SP2's route uses Flask generator-based SSE, so
   this holds.]**
