# PRD: SP04 — Athena External API (client relocation + typed responses + metrics)

**Sub-project:** SP04  
**Series:** 2026-06-29 backend cleanup (SP01–SP10)  
**Date:** 2026-06-29  
**Status:** Planning — no implementation started  
**Dependencies:** SP01 (JunoError), SP02 (Constants.Athena + AthenaSourceKind), SP03 (models/external_api/ folder)

---

## 1. Problem

`utils/athena_client.py` has four distinct correctness and architecture problems that compound as the codebase grows:

**1. Wrong layer.** `utils/` is a toolbox of pure-logic helpers. `AthenaClient` makes outbound HTTP calls to an external REST API — it is IO, not a utility. Placing it in `utils/` hides the fact that importing it brings in a live network dependency, making it harder to mock in tests and impossible to locate by convention.

**2. AthenaAPIError bypasses the unified error system.** `AthenaAPIError(Exception)` (line 24) inherits from bare `Exception`. SP01 established `JunoError` carrying a typed `ErrorCode` and structured metadata. Athena failures surface as untyped exceptions, losing `user_hint`, `retryable`, and error-code routing that every other failure path already provides.

**3. Typed models exist but are completely wired off.** `models/athena.py` defines `AthenaTokenResponse`, `AthenaEncounterSummaryResponse`, and `AthenaClinicalDocumentContentResponse` — but `AthenaClient` never uses them. Token parsing is `resp.json()["access_token"]` (KeyError on any shape change). Encounter summary is `data.get("summaryhtml", "")` (silent `""` on shape change). Clinical doc is `data.get("documentdata", "")` (same). Pydantic validation is entirely absent; the models exist but provide zero protection.

**4. Tunables are scattered and duplicated.** `BATCH_SIZE = 2` and `BATCH_SLEEP_S = 30` live at module level. `TOKEN_TTL_S = 300` and `TOKEN_REFRESH_BUFFER_S = 20` live as class attributes. Timeouts (30s token, 60s GET), retry count (3), OAuth scope literal (`"athena/service/Athenanet.MDP.*"`), base URL, and practice ID live inline. SP02 establishes `Constants.Athena` precisely to hold these; none of them are wired to it yet.

**5. Dead method `fetch_items_with_rate_limit`.** The method (lines 115–156) is never called from `routes/worker.py` or anywhere else in the codebase. It has two test cases in `tests/utils/test_athena_client.py`. It adds ~45 lines and two test files of dead surface area.

**6. No metrics.** The three live Athena HTTP operations (token fetch, encounter summary, clinical doc) emit no Markers events. Failed calls, retries, and latency are invisible to the observability stack.

---

## 2. Goals

1. Move `AthenaClient` and the module singleton `athena_client` to a new `backend/services/external_api/athena_client.py` package. This is the single consumer-visible entry point; all imports go here.
2. Move `AthenaAPIError` to `models/external_api/athena_errors.py` (SP03's folder), inheriting `JunoError` (SP01) with `ErrorCode.ATHENA_API_ERROR` as the default code. Token failures carry `ErrorCode.ATHENA_AUTH_FAILED`; rate limit exhaustion carries `ErrorCode.ATHENA_RATE_LIMIT_ERROR`.
3. Wire the typed models (relocated to `models/external_api/athena_models.py` by SP03) into every HTTP response parse: `AthenaTokenResponse`, `AthenaEncounterSummaryResponse`, `AthenaClinicalDocumentContentResponse`. No remaining raw-dict `.get()` calls on Athena responses.
4. Replace all inline tunables with `Constants.Athena.*` references (SP02).
5. Add a `Markers.Athena` inner class to `utils/markers/markers.py` with three leaves — `GetToken`, `FetchEncounterSummary`, `FetchClinicalDoc` — and wrap each corresponding HTTP operation. Record `status_code`, `retries`, and `source_kind` dimensions where applicable.
6. Delete `fetch_items_with_rate_limit` and its two test cases.
7. Update `routes/worker.py:220` import from `utils.athena_client` → `services.external_api`.
8. Move `tests/utils/test_athena_client.py` → `tests/services/external_api/test_athena_client.py`; update all patch targets and remove dead-method tests; add new typed-model and Markers tests.

---

## 3. Non-Goals

- No changes to the OAuth2 flow logic, retry behavior, or HTML-stripping algorithm — only the packaging and parse layer changes.
- No new Athena API endpoints (patient search, appointment fetch, push document). `AthenaPushDocumentRequest/Response` and `AthenaClinicalDocumentList*` models exist in `models/athena.py` but are not wired; they remain as-is after SP03 relocates them.
- No changes to `routes/worker.py` beyond the import path update at line 220. The error-handling logic in `worker.py` (lines 234–243) is unchanged.
- `tests/models/test_athena_manifest.py` is deleted by SP03, not SP04.
- `extra="allow"` → `extra="forbid"` tightening on Athena models is a SP03 coordination question; SP04 consumes models as-is. See §9 Q4.
- No dependency injection or factory pattern for `AthenaClient`. The module singleton remains. See §9 Q5.
- No changes to `routes/worker.py:219` source-kind string literals (`"athena_encounter"`, `"athena_clinical_doc"`). Migrating those to `Constants.Athena.AthenaSourceKind` is SP02's scope.

---

## 4. Architecture Decisions

### 4a. Package Layout (old → new)

**Before:**
```
backend/
  utils/
    athena_client.py          # AthenaClient + AthenaAPIError + singleton
  models/
    athena.py                 # typed models (extra="allow"; completely unused)
    athena_manifest.py        # manifest models (deleted by SP03)
```

**After** (SP04 creates `services/`; SP03 creates `models/external_api/`):
```
backend/
  services/
    __init__.py               # empty — marks services as a package
    external_api/
      __init__.py             # re-exports: athena_client, AthenaClient, AthenaAPIError
      athena_client.py        # AthenaClient + singleton (SP04)
  models/
    external_api/
      __init__.py             # SP03
      athena_models.py        # AthenaTokenResponse, AthenaEncounterSummaryResponse, etc. (SP03)
      athena_errors.py        # AthenaAPIError(JunoError) (SP04)
  utils/
    athena_client.py          # DELETED by SP04
```

**Import direction (no cycles):**
```
routes/worker.py
  → services/external_api/athena_client.py
      → models/external_api/athena_models.py   (Pydantic models)
      → models/external_api/athena_errors.py   (AthenaAPIError)
          → [SP01 JunoError location]           (JunoError base)
          → utils/error_codes.py               (ErrorCode.ATHENA_*)
              → models/errors.py               (ApiResponse, ErrorDetail)
      → utils/constants.py                     (Constants.Athena)
      → utils/markers/markers.py               (Markers.Athena)
```

`models/errors.py` has no upstream imports into `utils/` or `services/`, so no cycle is introduced.

---

### 4b. AthenaAPIError → `models/external_api/athena_errors.py`

**Old** (`utils/athena_client.py`, lines 24–30):
```python
class AthenaAPIError(Exception):
    """Raised when an Athena API call returns a non-200 status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Athena API error {status_code}: {body[:200]}")
```

**New** (`models/external_api/athena_errors.py`):
```python
"""models/external_api/athena_errors.py — Athena-specific exception type."""
from __future__ import annotations

from utils.error_codes import ErrorCode
from [SP01_JUNO_ERROR_MODULE] import JunoError  # resolved by SP01


class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 HTTP status.

    Inherits JunoError so callers in the pipeline can catch it uniformly.
    The `status_code` and `body` attributes are Athena-specific; they are
    also available via JunoError's `detail` string.
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

Callers that currently catch `AthenaAPIError` and access `.status_code` and `.body` are unaffected — those attributes remain on the class.

---

### 4c. Constants.Athena (SP02 dependency — consumed, not defined here)

SP02 creates a `Constants.Athena` inner class in `utils/constants.py`. SP04 consumes the following entries:

| SP04 usage | SP02 constant | Current hardcoded value |
|---|---|---|
| Token POST timeout | `Constants.Athena.TOKEN_TIMEOUT_S` | `30` (inline in `requests.post`) |
| GET timeout | `Constants.Athena.REQUEST_TIMEOUT_S` | `60` (inline in `requests.get`) |
| Token TTL | `Constants.Athena.TOKEN_TTL_S` | `AthenaClient.TOKEN_TTL_S = 300` |
| Refresh buffer | `Constants.Athena.TOKEN_REFRESH_BUFFER_S` | `AthenaClient.TOKEN_REFRESH_BUFFER_S = 20` |
| Default retries | `Constants.Athena.DEFAULT_RETRIES` | `retries: int = 3` (default arg) |
| OAuth scope | `Constants.Athena.OAUTH_SCOPE` | `"athena/service/Athenanet.MDP.*"` (inline) |
| Base URL | `Constants.Athena.BASE_URL` | `Constants.ATHENA_BASE_URL` (top-level) |
| Practice ID | `Constants.Athena.PRACTICE_ID` | `Constants.ATHENA_PRACTICE_ID` (top-level) |

The class-level `TOKEN_TTL_S` and `TOKEN_REFRESH_BUFFER_S` attributes are removed from `AthenaClient` entirely. The module-level `BATCH_SIZE` and `BATCH_SLEEP_S` are also removed (they belonged to the deleted `fetch_items_with_rate_limit`).

---

### 4d. AthenaClient Relocation — Full File Diff

**New file:** `services/external_api/athena_client.py`

The class is structurally identical to the current one with five targeted changes:
1. Class attributes `TOKEN_TTL_S` and `TOKEN_REFRESH_BUFFER_S` removed; replaced by `Constants.Athena.*` lookups.
2. `get_token()` wraps the HTTP POST in `Markers.Athena.GetToken.execute()`; parses response with `AthenaTokenResponse.model_validate()`.
3. `_get()` accepts an optional `scope: Scope | None = None` parameter; calls `scope.add(DIM_STATUS_CODE, ...)` when provided.
4. `fetch_encounter_summary()` and `fetch_clinical_doc()` wrapped in Markers; parse responses with typed models.
5. `fetch_items_with_rate_limit()` deleted.

**Old class signature area** (`utils/athena_client.py`, lines 33–68):
```python
class AthenaClient:
    TOKEN_TTL_S: int = 300
    TOKEN_REFRESH_BUFFER_S: int = 20

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - self.TOKEN_REFRESH_BUFFER_S:
            return self._token
        client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
        client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]
        resp = requests.post(
            f"{Constants.ATHENA_BASE_URL}/oauth2/v1/token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials", "scope": "athena/service/Athenanet.MDP.*"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]
        self._token_expires_at = now + self.TOKEN_TTL_S
        return self._token
```

**New class signature area** (`services/external_api/athena_client.py`):
```python
class AthenaClient:
    # No class-level tunables — all via Constants.Athena

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if within TOKEN_REFRESH_BUFFER_S of expiry."""
        now = time.time()
        if (
            self._token
            and now < self._token_expires_at - Constants.Athena.TOKEN_REFRESH_BUFFER_S
        ):
            return self._token

        def _fetch(scope: Scope) -> str:
            client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
            client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]
            resp = requests.post(
                f"{Constants.Athena.BASE_URL}/oauth2/v1/token",
                auth=(client_id, client_secret),
                data={
                    "grant_type": "client_credentials",
                    "scope": Constants.Athena.OAUTH_SCOPE,
                },
                timeout=Constants.Athena.TOKEN_TIMEOUT_S,
            )
            scope.add(DIM_STATUS_CODE, resp.status_code)
            if resp.status_code != 200:
                raise AthenaAPIError(
                    resp.status_code, resp.text, code=ErrorCode.ATHENA_AUTH_FAILED
                )
            token_response = AthenaTokenResponse.model_validate(resp.json())
            self._token = token_response.access_token
            self._token_expires_at = now + Constants.Athena.TOKEN_TTL_S
            logger.info(
                "athena_client: obtained new access token (expires in %ds)",
                Constants.Athena.TOKEN_TTL_S,
            )
            return self._token

        return Markers.Athena.GetToken.execute(_fetch)
```

---

### 4e. `_get()` — Scope-aware Retry Method

**Old** (`utils/athena_client.py`, lines 70–92):
```python
def _get(self, path: str, retries: int = 3) -> dict:
    for attempt in range(retries + 1):
        token = self.get_token()
        resp = requests.get(
            f"{Constants.ATHENA_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            if attempt == retries:
                raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
            logger.warning("athena_client: rate limited ...", path, attempt+1, retries, wait)
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        return resp.json()
    raise AthenaAPIError(429, "Rate limit: max retries exhausted")
```

**New** (`services/external_api/athena_client.py`):
```python
def _get(
    self,
    path: str,
    retries: int | None = None,
    scope: Scope | None = None,
) -> dict:
    """GET with retry on 429; raises AthenaAPIError on other non-200.

    Args:
        path: URL path relative to Constants.Athena.BASE_URL.
        retries: Max retry attempts on 429. Defaults to Constants.Athena.DEFAULT_RETRIES.
        scope: Optional Marker scope — receives status_code and retries dimensions.
    """
    if retries is None:
        retries = Constants.Athena.DEFAULT_RETRIES
    for attempt in range(retries + 1):
        token = self.get_token()
        resp = requests.get(
            f"{Constants.Athena.BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=Constants.Athena.REQUEST_TIMEOUT_S,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            if attempt == retries:
                if scope:
                    scope.add(DIM_STATUS_CODE, 429)
                    scope.add("retries", attempt)
                raise AthenaAPIError(
                    429,
                    f"Rate limit exceeded after {retries} retries",
                    code=ErrorCode.ATHENA_RATE_LIMIT_ERROR,
                )
            logger.warning(
                "athena_client: rate limited on %s (attempt %d/%d), sleeping %ds",
                path, attempt + 1, retries, wait,
            )
            time.sleep(wait)
            continue
        if scope:
            scope.add(DIM_STATUS_CODE, resp.status_code)
            scope.add("retries", attempt)
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        return resp.json()
    raise AthenaAPIError(429, "Rate limit: max retries exhausted", code=ErrorCode.ATHENA_RATE_LIMIT_ERROR)
```

---

### 4f. Typed Response Wiring in fetch methods

**Old** (`utils/athena_client.py`, lines 94–105):
```python
def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
    path = f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary"
    data = self._get(path)
    raw_html_str = data.get("summaryhtml", "")    # raw dict, silent on shape change
    return self._strip_html(raw_html_str)

def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
    path = f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
    data = self._get(path)
    return data.get("documentdata", "")            # raw dict, silent None
```

**New** (`services/external_api/athena_client.py`):
```python
def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
    """Fetch encounter summary HTML and return as stripped plain text."""
    def _do(scope: Scope) -> str:
        path = f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary"
        scope.add("source_kind", Constants.Athena.AthenaSourceKind.ENCOUNTER.value)
        data = self._get(path, scope=scope)
        summary = AthenaEncounterSummaryResponse.model_validate(data)
        return self._strip_html(summary.summaryhtml)
    return Markers.Athena.FetchEncounterSummary.execute(_do)

def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
    """Fetch SOAP-note clinical document and return documentdata string."""
    def _do(scope: Scope) -> str:
        path = f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
        scope.add("source_kind", Constants.Athena.AthenaSourceKind.CLINICAL_DOC.value)
        data = self._get(path, scope=scope)
        doc = AthenaClinicalDocumentContentResponse.model_validate(data)
        return doc.documentdata or ""
    return Markers.Athena.FetchClinicalDoc.execute(_do)
```

Key behavior changes:
- `fetch_encounter_summary`: If `summaryhtml` is absent from the Athena response, Pydantic raises a `ValidationError` (field is required in `AthenaEncounterSummaryResponse`) rather than silently returning `""`.
- `fetch_clinical_doc`: `AthenaClinicalDocumentContentResponse.documentdata` is `str | None`. The `or ""` preserves the existing return contract (never `None`).

---

### 4g. Markers.Athena leaf — `utils/markers/markers.py`

**Old** (no Athena group):
```python
class Markers:
    class CarePlan:
        ...
    class Grading:
        ...
    class Http:
        ...
```

**New** (add `Athena` inner class):
```python
class Markers:
    class CarePlan:
        ...
    class Grading:
        ...
    class Http:
        ...

    class Athena:
        @code_marker("athena.get_token")
        class GetToken(CodeMarker): pass

        @code_marker("athena.fetch_encounter_summary")
        class FetchEncounterSummary(CodeMarker): pass

        @code_marker("athena.fetch_clinical_doc")
        class FetchClinicalDoc(CodeMarker): pass
```

**Ownership decision:** SP04 adds this leaf. Rationale: the three Athena operations are SP04's primary deliverable; the Markers are meaningless without their callers. Waiting on SP08 (Metrics registry) would leave SP04's operations unmonitored and create an unnecessary inter-SP dependency. SP08 may reorganize the registry layout broadly but must not remove these three leaves.

**Emitted event shape** (per `CodeMarker._emit`):
```json
{
  "name": "athena.fetch_encounter_summary",
  "duration_ms": 412,
  "success": true,
  "dimensions": {
    "OpOutcome": "Succeeded",
    "StatusCode": 200,
    "retries": 0,
    "source_kind": "athena_encounter"
  }
}
```

---

### 4h. services/external_api/__init__.py

```python
"""services/external_api — Juno's outbound HTTP clients for external APIs."""
from .athena_client import athena_client, AthenaClient
from models.external_api.athena_errors import AthenaAPIError

__all__ = ["athena_client", "AthenaClient", "AthenaAPIError"]
```

This re-export lets `routes/worker.py` use a single import:
```python
from services.external_api import athena_client, AthenaAPIError
```

---

### 4i. Consumer update — `routes/worker.py:220`

**Old** (line 220):
```python
from utils.athena_client import athena_client, AthenaAPIError
```

**New**:
```python
from services.external_api import athena_client, AthenaAPIError
```

No other changes to `worker.py`. The `except AthenaAPIError as exc` block at line 234 and the `.status_code` attribute access remain intact — `AthenaAPIError` still has `status_code` after the refactor.

---

### 4j. File Deletion

`utils/athena_client.py` is **deleted** after SP04 is complete. No other file imports from it (verified: `routes/worker.py:220` is the sole consumer; `tests/utils/test_athena_client.py` is moved, not deleted separately).

---

## 5. API Change Summary

No HTTP API contract changes. SP04 is a pure internal refactor.

| Change | Visible to callers? |
|---|---|
| `AthenaClient` moved to `services/external_api/athena_client.py` | No — re-exported via `__init__.py` |
| `AthenaAPIError` now inherits `JunoError` | No — still raises `AthenaAPIError`; `.status_code` and `.body` unchanged |
| Typed model parse instead of `.get()` | No — return types of `fetch_encounter_summary` (str) and `fetch_clinical_doc` (str) unchanged |
| Metrics emission via Markers | No — side-effect only, no return value change |
| `fetch_items_with_rate_limit` deleted | Breaking for any caller — but confirmed zero callers in codebase |

---

## 6. Frontend

N/A. SP04 is entirely backend Python. No TypeScript or HTTP contract changes.

---

## 7. Testing

### 7a. File move and patch target updates

Move `tests/utils/test_athena_client.py` → `tests/services/external_api/test_athena_client.py`.  
Create `tests/services/__init__.py` and `tests/services/external_api/__init__.py` (empty).

All `patch()` targets update from `utils.athena_client.*` → `services.external_api.athena_client.*`:

| Old patch target | New patch target |
|---|---|
| `utils.athena_client.requests.post` | `services.external_api.athena_client.requests.post` |
| `utils.athena_client.requests.get` | `services.external_api.athena_client.requests.get` |
| `utils.athena_client.time.sleep` | `services.external_api.athena_client.time.sleep` |

Import line update:
```python
# Old:
from utils.athena_client import AthenaClient, AthenaAPIError, BATCH_SIZE, BATCH_SLEEP_S

# New:
from services.external_api.athena_client import AthenaClient
from models.external_api.athena_errors import AthenaAPIError
```

`BATCH_SIZE` and `BATCH_SLEEP_S` imports are dropped (constants deleted with dead method).

### 7b. Tests to remove (dead method deleted)

- `test_fetch_items_rate_limit_sleeps_between_batches_not_after_last`
- `test_fetch_items_no_sleep_for_single_batch`

### 7c. Tests to add

**Typed model wiring:**

- `test_get_token_uses_typed_model`: mock POST to return `{"access_token": "tok", "token_type": "Bearer", "expires_in": 3600, "extra": "ignored"}`; assert `get_token()` returns `"tok"` (model_validate correctly extracts `access_token`; extra field silently ignored with `extra="allow"`).
- `test_fetch_encounter_summary_uses_typed_model`: mock `_get` to return `{"summaryhtml": "<p>Gary</p>", "extra_field": "irrelevant"}`; assert result is `"Gary"`.
- `test_fetch_encounter_summary_raises_on_missing_summaryhtml`: mock `_get` to return `{}` (no `summaryhtml` key); assert `ValidationError` is raised (field is required in `AthenaEncounterSummaryResponse`).
- `test_fetch_clinical_doc_uses_typed_model`: mock `_get` to return `{"documentdata": "SOAP text", "pages": []}`; assert result is `"SOAP text"`.
- `test_fetch_clinical_doc_returns_empty_string_when_documentdata_none`: mock `_get` to return `{"pages": []}` (documentdata absent, field is `str | None = None`); assert result is `""` (not `None`).

**Error code specificity:**

- `test_get_token_raises_auth_failed_error_code`: mock POST to return 401; assert `AthenaAPIError` is raised and `exc.error_code == ErrorCode.ATHENA_AUTH_FAILED`.
- `test_get_raises_rate_limit_error_code_after_exhausted_retries`: mock GET to always return 429; assert `AthenaAPIError` raised with `exc.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR`.
- `test_get_raises_athena_api_error_on_non_200`: mock GET to return 503; assert `AthenaAPIError` with `status_code == 503` and `error_code == ErrorCode.ATHENA_API_ERROR` (default).

**Constants.Athena wiring:**

- `test_aтhena_client_has_no_token_ttl_class_attr`: assert `AthenaClient.TOKEN_TTL_S` does not exist (`not hasattr(AthenaClient, "TOKEN_TTL_S")`). This catches regression if class attrs are accidentally left in.
- `test_get_uses_constants_request_timeout`: using `patch("services.external_api.athena_client.requests.get", ...)`, assert `timeout=Constants.Athena.REQUEST_TIMEOUT_S` in the call kwargs.

**Markers integration:**

- `test_fetch_encounter_summary_emits_marker`: register a test sink; call `fetch_encounter_summary`; assert the sink received an event with `name == "athena.fetch_encounter_summary"` and `dimensions["source_kind"] == "athena_encounter"`.
- `test_fetch_clinical_doc_emits_marker`: same pattern; assert `source_kind == "athena_clinical_doc"`.

### 7d. Existing tests that pass through unchanged

- `test_get_token_success`
- `test_get_token_cached_within_ttl`
- `test_get_token_refresh_when_expiry_within_buffer`
- `test_get_token_does_not_refresh_when_fresh`
- `test_strip_html_removes_tags`
- `test_strip_html_unescapes_entities`
- `test_fetch_encounter_summary_calls_correct_path` (update patch target only)
- `test_fetch_clinical_doc_calls_correct_path` (update patch target only)

### 7e. Dead-code removal test

`tests/integration/test_dead_code_removed.py` — add assertion that `utils.athena_client` no longer exists as a module (i.e., `import utils.athena_client` raises `ModuleNotFoundError`).

---

## 8. Manual Intervention Required

None. SP04 is entirely Python module moves and rewires:
- No GCS bucket config changes
- No Cloud Run environment variable changes
- No Firestore schema migration
- No deployment config changes

The singleton `athena_client` is recreated at module import time from the new path; no warm-instance migration is needed.

---

## 9. Open Questions & Decisions

| # | Status | Item |
|---|---|---|
| Q1 | [RESOLVED] | `AthenaClient` + singleton → `services/external_api/athena_client.py`. `AthenaAPIError` → `models/external_api/athena_errors.py`. Typed models wired in. `fetch_items_with_rate_limit` deleted. |
| Q2 | [RESOLVED] | `AthenaAPIError` inherits `JunoError` (SP01) with default `ErrorCode.ATHENA_API_ERROR`. Token POST failure raises with `ErrorCode.ATHENA_AUTH_FAILED`. Rate-limit exhaustion raises with `ErrorCode.ATHENA_RATE_LIMIT_ERROR`. Non-200 GET (other than 429) uses default `ATHENA_API_ERROR`. |
| Q3 | [RESOLVED] | `Markers.Athena` leaf added by SP04, not SP08. Three leaves: `GetToken`, `FetchEncounterSummary`, `FetchClinicalDoc`. SP08 may reorganize but must preserve these metric names. |
| Q4 | [OPEN] | `extra="allow"` → `extra="forbid"` on `AthenaTokenResponse`, `AthenaEncounterSummaryResponse`, `AthenaClinicalDocumentContentResponse`. SP03 owns the model files; should SP03 tighten to `forbid` as part of relocation, or defer? SP04 ships with `extra="allow"` as inherited from SP03's relocation. Tightening to `forbid` would catch future Athena API additions earlier but could break integration tests that replay saved response payloads with extra fields. **Recommendation:** defer to a follow-up; keep `extra="allow"` for now. |
| Q5 | [DEFERRED] | `AthenaClient` module singleton makes constructor-injection testing awkward. A factory or DI container would allow per-test isolation without patching. Not in SP04 scope — tests continue to use `patch.object`. |
| Q6 | [RESOLVED] | Import cycle analysis: `models/external_api/athena_errors.py` → `utils/error_codes.py` → `models/errors.py`. No cycle: `models/errors.py` imports only from `models/base.py` and stdlib. |
| Q7 | [RESOLVED] | `SP01_JUNO_ERROR_MODULE` placeholder in §4b: SP04 binds to wherever SP01 places `JunoError`. Current codebase has it at `utils.pipeline_errors.JunoError` — SP04 uses this path; if SP01 moves it, SP04 implementation must update the import. |
