# SP04 Athena External API — TASKS

## Prerequisites

**Purpose:** Relocate the Athena Health HTTP client out of `utils/` into a proper `services/external_api/` package, fold `AthenaAPIError` into the unified `JunoError` system, wire the existing Pydantic response models into every parse, add Markers metrics around the three live HTTP operations, and delete the dead batch method — all with zero backward-compat shims.

This SP assumes **SP01, SP02, SP03 are complete and deployed**:
- **SP01** — unified error system exists: `JunoError` (carries an `ErrorCode`, `detail`, `original`) and the `ErrorCode` enum already contains `ATHENA_AUTH_FAILED`, `ATHENA_API_ERROR`, `ATHENA_RATE_LIMIT_ERROR` (and their `ERROR_CATALOG`/registry entries). Do **not** recreate the error system; consume it.
- **SP02** — `Constants.Athena` inner class exists in `utils/constants.py` with the tunables listed in Task 04.3, plus `Constants.Athena.AthenaSourceKind` (an enum whose members `.ENCOUNTER` / `.CLINICAL_DOC` carry the string values `"athena_encounter"` / `"athena_clinical_doc"`). Do **not** add these constants here.
- **SP03** — `models/external_api/` package exists with `athena_models.py` containing `AthenaTokenResponse`, `AthenaEncounterSummaryResponse`, `AthenaClinicalDocumentContentResponse` (relocated from `models/athena.py`), and an empty `__init__.py`. Do **not** recreate these models.

> Note: At the time these tasks were written the SP01–SP03 artifacts were not yet landed in the working tree (`Constants.Athena`, `models/external_api/`, and the consolidated `ErrorCode`/`ERROR_CATALOG` entries for Athena were absent; two `error_codes.py` files — `backend/error_codes.py` and `backend/utils/error_codes.py` — coexist). Per the ship-in-order rule, SP04 **assumes** these are present. Before starting, verify each import below resolves; if any is missing, that SP has not actually shipped and SP04 is blocked on it. Bind `JunoError` to `utils.pipeline_errors.JunoError` and `ErrorCode` to the module that `JunoError` reads its `ERROR_CATALOG` from (PRD Q7).

## Tasks

### Task 04.1: Create the `services/` package skeleton

- **Goal:** Establish `backend/services/` and `backend/services/external_api/` as importable packages so the client has a home.
- **Files:**
  - `backend/services/__init__.py` (new, empty)
  - `backend/services/external_api/__init__.py` (new — populated in Task 04.6, create empty for now)
- **Steps:**
  1. Create `backend/services/__init__.py` with a one-line module docstring: `"""services/ — Juno's outbound IO clients for external systems."""`.
  2. Create `backend/services/external_api/__init__.py` empty (a placeholder; Task 04.6 fills in the re-exports). Leaving it empty now avoids importing modules that don't exist yet.
- **Acceptance:** `python -c "import services, services.external_api"` succeeds from `backend/`.
- **Commit:** `chore(services): add services/external_api package skeleton`

### Task 04.2: Add `AthenaAPIError(JunoError)` in `models/external_api/athena_errors.py`

- **Goal:** Move the Athena exception into SP03's model folder and make it inherit the unified `JunoError`, defaulting to `ErrorCode.ATHENA_API_ERROR` while preserving `.status_code` and `.body`.
- **Files:** `backend/models/external_api/athena_errors.py` (new)
- **Steps:**
  1. Create the file with this body (bind imports to the real SP01 locations — `JunoError` from `utils.pipeline_errors`, `ErrorCode` from wherever `JunoError` reads `ERROR_CATALOG`):
     ```python
     """models/external_api/athena_errors.py — Athena-specific exception type."""
     from __future__ import annotations

     from utils.pipeline_errors import JunoError
     from error_codes import ErrorCode  # same module JunoError uses for ERROR_CATALOG


     class AthenaAPIError(JunoError):
         """Raised when an Athena API call returns a non-200 HTTP status.

         Inherits JunoError so pipeline callers catch it uniformly. The
         status_code and body attributes are Athena-specific and remain
         available directly; the detail string also encodes them.
         """

         def __init__(
             self,
             status_code: int,
             body: str,
             code: ErrorCode = ErrorCode.ATHENA_API_ERROR,
         ) -> None:
             self.status_code = status_code
             self.body = body
             super().__init__(code, detail=f"status={status_code}: {body[:200]}")
     ```
  2. Confirm `JunoError.__init__` accepts `(error_code, detail=...)` positionally; pass `code` as the first positional arg as above.
- **Acceptance:** `python -c "from models.external_api.athena_errors import AthenaAPIError; e=AthenaAPIError(503,'x'); assert e.status_code==503 and e.error_code.value=='ATHENA_API_ERROR' and isinstance(e, __import__('utils.pipeline_errors', fromlist=['JunoError']).JunoError)"` succeeds.
- **Commit:** `feat(models): add AthenaAPIError(JunoError) under models/external_api`

> Note: `JunoError` exposes the code as `.error_code` (not `.code`). Tests in Task 04.8 assert `exc.error_code == ErrorCode.ATHENA_*`. The PRD's §7c prose says `error_code`; follow that, not the `.code` arg name.

### Task 04.3: Create `services/external_api/athena_client.py` with the relocated client

- **Goal:** Port `AthenaClient` + the `athena_client` singleton into the new package with all tunables read from `Constants.Athena.*`, typed-model parsing, Markers wrapping, scope-aware retries, and **no** dead method. This is the bulk of SP04.
- **Files:** `backend/services/external_api/athena_client.py` (new)
- **Steps:**
  1. Start the file with imports:
     ```python
     """services/external_api/athena_client.py — Athena Health REST client (OAuth2, retry, typed parse, metrics)."""
     import html
     import logging
     import os
     import re
     import time

     import requests

     from utils.constants import Constants
     from utils.markers.markers import Markers
     from utils.markers.marker import Scope, DIM_STATUS_CODE
     from models.external_api.athena_models import (
         AthenaTokenResponse,
         AthenaEncounterSummaryResponse,
         AthenaClinicalDocumentContentResponse,
     )
     from models.external_api.athena_errors import AthenaAPIError
     from error_codes import ErrorCode  # same module AthenaAPIError uses

     logger = logging.getLogger(__name__)
     ```
     Do **not** copy over `BATCH_SIZE`, `BATCH_SLEEP_S`, or the `concurrent.futures` imports — they belonged only to the deleted method.
  2. Define `class AthenaClient:` with **no class-level tunables** (no `TOKEN_TTL_S`, no `TOKEN_REFRESH_BUFFER_S`). Keep `__init__` exactly: `self._token: str | None = None` and `self._token_expires_at: float = 0.0`.
  3. Implement `get_token()` wrapping the POST in `Markers.Athena.GetToken.execute(_fetch)`. Inside `_fetch(scope: Scope) -> str`: read env vars via `Constants.ATHENA_CLIENT_ID_ENV_VAR` / `Constants.ATHENA_CLIENT_SECRET_ENV_VAR`; POST to `f"{Constants.Athena.BASE_URL}/oauth2/v1/token"` with `data={"grant_type": "client_credentials", "scope": Constants.Athena.OAUTH_SCOPE}` and `timeout=Constants.Athena.TOKEN_TIMEOUT_S`; call `scope.add(DIM_STATUS_CODE, resp.status_code)`; on non-200 raise `AthenaAPIError(resp.status_code, resp.text, code=ErrorCode.ATHENA_AUTH_FAILED)`; parse with `AthenaTokenResponse.model_validate(resp.json())` and store `.access_token`; set `self._token_expires_at = now + Constants.Athena.TOKEN_TTL_S`. The early-return cache check uses `Constants.Athena.TOKEN_REFRESH_BUFFER_S`. (See PRD §4d for the exact code.)
  4. Implement `_get(self, path, retries: int | None = None, scope: Scope | None = None) -> dict`: default `retries` to `Constants.Athena.DEFAULT_RETRIES` when `None`; loop `range(retries + 1)`; GET `f"{Constants.Athena.BASE_URL}{path}"` with `timeout=Constants.Athena.REQUEST_TIMEOUT_S`; on 429 retry honoring `Retry-After`, and on the final attempt add `scope.add(DIM_STATUS_CODE, 429)` + `scope.add("retries", attempt)` (guarded by `if scope:`) then raise `AthenaAPIError(429, ..., code=ErrorCode.ATHENA_RATE_LIMIT_ERROR)`; on any response, when `scope` is set, `scope.add(DIM_STATUS_CODE, resp.status_code)` and `scope.add("retries", attempt)`; non-200 (non-429) raises default `AthenaAPIError(resp.status_code, resp.text)`; trailing unreachable raise also uses `ErrorCode.ATHENA_RATE_LIMIT_ERROR`. (See PRD §4e for exact code.)
  5. Implement `fetch_encounter_summary(self, practice_id, encounter_id) -> str` wrapping a `_do(scope)` in `Markers.Athena.FetchEncounterSummary.execute`. Inside: `scope.add("source_kind", Constants.Athena.AthenaSourceKind.ENCOUNTER.value)`; call `self._get(path, scope=scope)`; parse `AthenaEncounterSummaryResponse.model_validate(data)`; return `self._strip_html(summary.summaryhtml)`.
  6. Implement `fetch_clinical_doc(self, practice_id, patient_id, document_id) -> str` analogously with `Markers.Athena.FetchClinicalDoc.execute`, `source_kind` = `Constants.Athena.AthenaSourceKind.CLINICAL_DOC.value`, parse `AthenaClinicalDocumentContentResponse.model_validate(data)`, return `doc.documentdata or ""`.
  7. Keep `@staticmethod _strip_html(raw_html_str)` byte-for-byte identical to the current implementation (`html.unescape` → strip tags → collapse blank lines → `.strip()`).
  8. End the module with `athena_client = AthenaClient()`.
- **Acceptance:** `python -c "from services.external_api.athena_client import AthenaClient, athena_client"` imports cleanly; `not hasattr(AthenaClient, 'TOKEN_TTL_S')` and `not hasattr(AthenaClient, 'TOKEN_REFRESH_BUFFER_S')`; the module defines no `BATCH_SIZE`/`BATCH_SLEEP_S` and no `fetch_items_with_rate_limit` attribute on the class.
- **Commit:** `feat(services): relocate AthenaClient with typed parse, constants, and markers`

> Note: `Scope.add` silently drops `None` values, so always pass concrete ints/strings (e.g. `attempt`, not a possibly-`None` value) for the `retries` dimension.

### Task 04.4: Add the `Markers.Athena` leaf

- **Goal:** Register the three Athena operation markers so `athena_client.py` can wrap its HTTP calls.
- **Files:** `backend/utils/markers/markers.py`
- **Steps:**
  1. After the existing `Http` inner class, add a new inner class:
     ```python
     class Athena:
         @code_marker("athena.get_token")
         class GetToken(CodeMarker): pass

         @code_marker("athena.fetch_encounter_summary")
         class FetchEncounterSummary(CodeMarker): pass

         @code_marker("athena.fetch_clinical_doc")
         class FetchClinicalDoc(CodeMarker): pass
     ```
  2. Do not alter existing leaves.
- **Acceptance:** `python -c "from utils.markers.markers import Markers; assert Markers.Athena.GetToken.name()=='athena.get_token' and Markers.Athena.FetchEncounterSummary.name()=='athena.fetch_encounter_summary' and Markers.Athena.FetchClinicalDoc.name()=='athena.fetch_clinical_doc'"` passes.
- **Commit:** `feat(markers): add Markers.Athena get_token/encounter_summary/clinical_doc leaves`

### Task 04.5: Update the consumer import in `routes/worker.py`

- **Goal:** Point the sole consumer at the new package path; change nothing else.
- **Files:** `backend/routes/worker.py`
- **Steps:**
  1. At line ~220, replace `from utils.athena_client import athena_client, AthenaAPIError` with `from services.external_api import athena_client, AthenaAPIError`.
  2. Leave everything else untouched — the `except AthenaAPIError as exc:` block, `exc.status_code` access (line ~238), the `build_error_data(ErrorCode.ATHENA_API_ERROR, ...)` call, and the `"athena_encounter"`/`"athena_clinical_doc"` literals at line 219 all stay as-is (literal migration is SP02 scope per PRD §3).
- **Acceptance:** `grep -n "utils.athena_client" backend/routes/worker.py` returns nothing; `grep -n "from services.external_api import athena_client, AthenaAPIError" backend/routes/worker.py` returns one line.
- **Commit:** `refactor(worker): import athena_client from services.external_api`

### Task 04.6: Populate `services/external_api/__init__.py` re-exports

- **Goal:** Make `from services.external_api import athena_client, AthenaClient, AthenaAPIError` work as the single consumer-facing entry point.
- **Files:** `backend/services/external_api/__init__.py`
- **Steps:**
  1. Replace the empty placeholder with:
     ```python
     """services/external_api — Juno's outbound HTTP clients for external APIs."""
     from .athena_client import athena_client, AthenaClient
     from models.external_api.athena_errors import AthenaAPIError

     __all__ = ["athena_client", "AthenaClient", "AthenaAPIError"]
     ```
- **Acceptance:** `python -c "from services.external_api import athena_client, AthenaClient, AthenaAPIError"` succeeds.
- **Commit:** `feat(services): re-export athena_client/AthenaClient/AthenaAPIError from package init`

### Task 04.7: Delete the legacy `utils/athena_client.py`

- **Goal:** Remove the old module entirely — no shim, no re-export stub.
- **Files:** `backend/utils/athena_client.py` (deleted)
- **Steps:**
  1. `git rm backend/utils/athena_client.py`.
  2. Verify no remaining references: `grep -rn "utils.athena_client\|utils/athena_client" backend/` must return nothing (the moved test file is updated in Task 04.8; run this grep after that task if ordering it earlier surfaces the test).
- **Acceptance:** `python -c "import utils.athena_client"` raises `ModuleNotFoundError`; repo-wide grep for `utils.athena_client` is empty (excluding this TASKS.md and docs).
- **Commit:** `refactor(utils): delete legacy utils/athena_client.py`

### Task 04.8: Move and rewrite the test suite

- **Goal:** Relocate the tests under `tests/services/external_api/`, fix all patch targets and imports, drop the dead-method tests, and add typed-model / error-code / Markers tests.
- **Files:**
  - `backend/tests/services/__init__.py` (new, empty)
  - `backend/tests/services/external_api/__init__.py` (new, empty)
  - `backend/tests/services/external_api/test_athena_client.py` (moved from `backend/tests/utils/test_athena_client.py`)
- **Steps:**
  1. `git mv backend/tests/utils/test_athena_client.py backend/tests/services/external_api/test_athena_client.py` and create the two empty `__init__.py` package markers.
  2. Replace the import line `from utils.athena_client import AthenaClient, AthenaAPIError, BATCH_SIZE, BATCH_SLEEP_S` with:
     ```python
     from services.external_api.athena_client import AthenaClient
     from models.external_api.athena_errors import AthenaAPIError
     ```
     Drop the `BATCH_SIZE` / `BATCH_SLEEP_S` imports entirely.
  3. Update every `patch(...)` target: `utils.athena_client.requests.post` → `services.external_api.athena_client.requests.post`; `utils.athena_client.requests.get` → `services.external_api.athena_client.requests.get`; `utils.athena_client.time.sleep` → `services.external_api.athena_client.time.sleep`.
  4. Update `_mock_token_response` to include all required fields so `AthenaTokenResponse.model_validate` passes: `{"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}`. (The current mock only sets `access_token`; the typed model also requires `token_type` and `expires_in`.)
  5. Delete the two dead-method tests: `test_fetch_items_rate_limit_sleeps_between_batches_not_after_last` and `test_fetch_items_no_sleep_for_single_batch`.
  6. Keep the unchanged pass-through tests (`test_get_token_success`, `test_get_token_cached_within_ttl`, `test_get_token_refresh_when_expiry_within_buffer`, `test_get_token_does_not_refresh_when_fresh`, `test_strip_html_*`, `test_fetch_encounter_summary_calls_correct_path`, `test_fetch_clinical_doc_calls_correct_path`) — only their patch targets change.
  7. Add the typed-model tests:
     - `test_get_token_uses_typed_model` — POST returns `{"access_token":"tok","token_type":"Bearer","expires_in":3600,"extra":"ignored"}`; assert `get_token()=="tok"` (extra field tolerated, `extra="allow"`).
     - `test_fetch_encounter_summary_uses_typed_model` — `patch.object(client,"_get",return_value={"summaryhtml":"<p>Gary</p>","extra_field":"x"})`; assert result `"Gary"`.
     - `test_fetch_encounter_summary_raises_on_missing_summaryhtml` — `_get` returns `{}`; assert `pydantic.ValidationError` raised (`summaryhtml` is required).
     - `test_fetch_clinical_doc_uses_typed_model` — `_get` returns `{"documentdata":"SOAP text","pages":[]}`; assert `"SOAP text"`.
     - `test_fetch_clinical_doc_returns_empty_string_when_documentdata_none` — `_get` returns `{"pages":[]}`; assert result `""`.
  8. Add the error-code tests (assert on `exc.error_code`):
     - `test_get_token_raises_auth_failed_error_code` — POST returns 401; assert `AthenaAPIError` with `exc.error_code == ErrorCode.ATHENA_AUTH_FAILED`.
     - `test_get_raises_rate_limit_error_code_after_exhausted_retries` — GET always 429 (patch `time.sleep`); assert `exc.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR`.
     - `test_get_raises_athena_api_error_on_non_200` — GET returns 503; assert `exc.status_code == 503` and `exc.error_code == ErrorCode.ATHENA_API_ERROR`.
     - Import `ErrorCode` from the same module the client uses.
  9. Add the Constants-wiring tests:
     - `test_athena_client_has_no_token_ttl_class_attr` — `assert not hasattr(AthenaClient, "TOKEN_TTL_S")`.
     - `test_get_uses_constants_request_timeout` — patch `requests.get` (return 200 + valid body), call a fetch, assert the call kwargs include `timeout == Constants.Athena.REQUEST_TIMEOUT_S`.
  10. Add the Markers tests (register an `InMemorySink`, assert event name + dimensions, then re-register `None` in teardown):
      ```python
      from utils.markers.registry import register_sink
      from utils.markers.sinks import InMemorySink
      ```
      - `test_fetch_encounter_summary_emits_marker` — sink captures event with `name=="athena.fetch_encounter_summary"` and `dimensions["source_kind"]=="athena_encounter"`.
      - `test_fetch_clinical_doc_emits_marker` — `name=="athena.fetch_clinical_doc"`, `dimensions["source_kind"]=="athena_clinical_doc"`.
- **Acceptance:** `pytest backend/tests/services/external_api/test_athena_client.py -q` passes; no test references `utils.athena_client`, `BATCH_SIZE`, `BATCH_SLEEP_S`, or `fetch_items_with_rate_limit`.
- **Commit:** `test(athena): move suite to services/external_api, wire typed-model/error-code/markers tests`

> Note: For the Markers tests, restore the sink with `register_sink(None)` in a fixture/teardown so captured events don't leak across tests. Source-kind dimension values come from `Constants.Athena.AthenaSourceKind` (SP02); if those enum values differ from `"athena_encounter"`/`"athena_clinical_doc"`, assert against `Constants.Athena.AthenaSourceKind.ENCOUNTER.value` rather than hardcoded strings.

### Task 04.9: Add dead-module regression assertion

- **Goal:** Lock in that the legacy module is gone for good.
- **Files:** `backend/tests/integration/test_dead_code_removed.py`
- **Steps:**
  1. If the file exists, add a test; otherwise create it. Add:
     ```python
     import pytest

     def test_utils_athena_client_module_is_gone():
         with pytest.raises(ModuleNotFoundError):
             import utils.athena_client  # noqa: F401
     ```
- **Acceptance:** `pytest backend/tests/integration/test_dead_code_removed.py -q` passes.
- **Commit:** `test(integration): assert utils.athena_client module is removed`

## Verification

Run from `backend/`:

1. Targeted tests: `pytest tests/services/external_api/test_athena_client.py tests/integration/test_dead_code_removed.py -q`
2. Full backend suite (no regressions in worker import path): `pytest -q`
3. Lint/type (whatever the repo uses): `ruff check .` and, if configured, `mypy services/ models/external_api/`
4. Import sanity:
   - `python -c "from services.external_api import athena_client, AthenaClient, AthenaAPIError"`
   - `python -c "import utils.athena_client"` → must raise `ModuleNotFoundError`
5. Grep cleanups (all must return nothing under `backend/`, excluding docs):
   - `grep -rn "utils.athena_client" backend/ --include=*.py`
   - `grep -rn "BATCH_SIZE\|BATCH_SLEEP_S\|fetch_items_with_rate_limit" backend/ --include=*.py`
   - `grep -rn "\.get(\"summaryhtml\"\|\.get(\"documentdata\"" backend/services backend/models`

**Definition of done:**
- `AthenaClient` + `athena_client` live only at `services/external_api/athena_client.py`; `utils/athena_client.py` is deleted.
- `AthenaAPIError` inherits `JunoError`, defaults to `ErrorCode.ATHENA_API_ERROR`, raises `ATHENA_AUTH_FAILED` on token failure and `ATHENA_RATE_LIMIT_ERROR` on retry exhaustion, and still carries `.status_code` / `.body`.
- All three HTTP responses parse through their Pydantic models — zero raw `.get()` on Athena responses.
- Every tunable resolves through `Constants.Athena.*`; no class-level `TOKEN_TTL_S`/`TOKEN_REFRESH_BUFFER_S` and no module-level `BATCH_*`.
- `Markers.Athena.{GetToken,FetchEncounterSummary,FetchClinicalDoc}` wrap their operations and emit `status_code` + `retries` + `source_kind` dimensions.
- `fetch_items_with_rate_limit` and its two tests are gone; new typed-model/error-code/markers tests pass.
- `routes/worker.py` imports from `services.external_api`; no other worker logic changed. The `extra="allow"` config on Athena models is retained (PRD Q4).
