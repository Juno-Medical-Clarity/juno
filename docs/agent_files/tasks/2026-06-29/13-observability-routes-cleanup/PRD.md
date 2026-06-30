# PRD: SP13 — Observability/Logging Reconciliation & Routes-Utils-Services Boundary Cleanup

**Sub-project:** SP13
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-29
**Status:** Planning — no implementation started

**Dependencies:**
- SP11 (Legacy Shim Purge) — deletes the `_score_or_none` wrapper and `_juno_error_logger` secondary logger (`routes/care_plan.py` lines ~42–52) before SP13 lands. SP13 treats those lines as already gone and does not redesign them.
- SP12 (Error System & Athena Consolidation) — touches `routes/worker.py` lines ~230–250 (the `athena_client.fetch_encounter_summary`/`fetch_clinical_doc` call site, inside `execute_job`'s body). SP13 does not move or edit `execute_job` itself, only the free-standing helper functions above it, so there is no line overlap — see §3.

---

## 1. Problem

Three distinct issues have accumulated in the backend's observability and layering:

**A. Two parallel structured-output systems cover the same events.** `utils/markers/` (`Markers`/`CodeMarker`/`JunoContext`) is the house instrumentation system: a marker's `execute()` times an action, and on completion `JunoSink.emit()` writes both a metric line (`juno.metrics` logger) and a timeline log line (`juno.markers` logger), enriched with the standard dimension set (`session_id`, `user_id`, `function`, `care_plan_version`, `grading_version`, `input_version`, `service`, `environment`) via `JunoContext.apply()` (`utils/markers/context.py:59-67`). `utils/juno_logger.py`'s `JunoLogger` class independently re-implements the *exact same* field extraction in `_base_fields()` (`utils/juno_logger.py:72-83`) — both pull the same eight fields from `flask.g` through separately-written code. `app.py`'s `before_request`/`after_request` handlers instantiate both: `JunoLogger(function="http_request")` for `log_request_start`/`log_request_end` (lines 114-118, 137-141) AND `Markers.Http.Request.execute(...)` via `JunoContext.from_g(function="http_request")` (lines 144-152) — for the identical request lifecycle event. Confirmed via grep: `JunoLogger` has zero call sites outside `app.py` in production code (only test files reference the class). `app.py` is also the only place `monotonic_ms()` (also defined in `juno_logger.py`) is used.

  A second-order finding: `observability/logging_config.py`'s `SessionIdFilter` (lines 36-50) *already* auto-injects `session_id` into every log record from `flask.g`, independent of `JunoLogger` or `Markers`. And `Constants.Observability.LOG_EXTRA_KEYS` (`utils/constants.py:126-133`) already whitelists every field `JunoContext`/`Markers` emit (`user_id`, `function`, `care_plan_version`, `grading_version`, `input_version`, `http_method`, `http_path`, `http_status`, `duration_ms`, `service`, `environment`, etc.) for `StructuredJsonFormatter` to surface. So the logging pipeline was already built around a Markers-only world; `JunoLogger` is the only thing still depending on the old pattern.

**B. `routes/` contains modules that are not routes at all.** Beyond the two items already flagged in the initiative brief (`routes/batch_utils.py`'s helpers + an unused `batch_bp` Blueprint), my own scan of `routes/` turned up a larger instance of the same pattern:

  - **`routes/care_plan.py` has zero `@care_plan_bp.route` decorators.** `grep -n "@care_plan_bp" routes/care_plan.py` returns nothing. The file's own docstring explains why: *"The SSE streaming route (POST /care_plan) has been removed; use POST /care_plan/jobs instead."* — a prior refactor (SP07, per the file's docstring and `models.pipeline_events` plumbing) deleted the only route this file ever served, and left behind ~290 lines of helper functions plus a now-inert `care_plan_bp = Blueprint("care_plan", __name__)` (line 46). `care_plan_bp` is imported into `routes/__init__.py` and registered onto the Flask app exactly like `batch_bp` — registering a `Blueprint` with no `@bp.route` calls and no `template_folder`/`static_folder` configured has zero runtime effect. This is the same dead-Blueprint pattern called out for `batch_utils.py`, just bigger: the entire file is misplaced business logic (a pipeline-execution adapter plus input-resolution helpers) wearing a "routes" label.
  - `routes/worker.py:49-151` has six free functions above the one real route handler (`execute_job`, line 155): `_canonical_input_type`, `_is_batch_item`, `_resolve_input_from_job_doc`, `_build_error_data`, `_extract_text_from_downloaded`, `_verify_oidc_token`.
  - No other `routes/*.py` file exhibits this pattern (`admin.py`, `datasets.py`, `grading.py`, `saved_outputs.py`, `care_plan_jobs.py`, `batch_jobs.py` were scanned; their module-level helpers are either trivial private closures inside a single route handler or already-thin and route-appropriate).

**C. Two small GCS files duplicate client construction, and several genuinely single-function utility files clutter `utils/`.** `utils/gcs_helpers.py` (`get_gcs_bucket`, generic bucket accessor) and `utils/gcs_datasets.py` (`download_dataset_inputs`/`cleanup_dataset_inputs`/`sweep_stale_dataset_dirs`, batch-dataset-specific) each construct their own `gcs.Client` instead of sharing one constructor. Separately, `utils/output_helpers.py` (`derive_output_name`, 1 function), `utils/html.py` (`extract_text_from_html`, 1 function), and `utils/env.py` (`get_env`, 1 function — and, per my own grep, currently has **zero production call sites**; only its own test file imports it) are each a single-function file.

---

## 2. Goals

1. Delete `JunoLogger` (class + `utils/juno_logger.py` file) entirely. `app.py`'s `before_request`/`after_request` emit request-lifecycle structured output through `Markers`/`JunoContext` only.
2. Merge `utils/gcs_helpers.py` + `utils/gcs_datasets.py` into one `utils/gcs.py`, deduping client construction.
3. Merge `utils/output_helpers.py`, `utils/html.py`, and `utils/env.py` into one `utils/misc.py`.
4. Delete `routes/batch_utils.py` as a routes file: move `_batch_timestamp`/`_resolve_requested_runs` into `utils/batch.py`; remove the dead `batch_bp` Blueprint and its registration.
5. Delete `routes/care_plan.py` as a routes file: move its pipeline-adapter logic into `services/care_plan_pipeline.py` and its input-resolution logic into `services/care_plan_input.py`; remove the dead `care_plan_bp` Blueprint and its registration.
6. Relocate the six non-route helper functions in `routes/worker.py` into `utils/job_helpers.py` (pure mapping helpers), `services/care_plan_input.py` (input-resolution helpers, joining the ones moved from `care_plan.py`), or `utils/firebase.py` (OIDC auth helper) per function — see §4e.
7. After 1–6, every file under `routes/` contains only Flask blueprint setup and `@bp.route`-decorated handlers.

---

## 3. Non-Goals

- No changes to `models/metrics.py`, `observability/telemetry.py`, `observability/logging_config.py` — all kept as-is per the initiative's locked decisions.
- No changes inside `execute_job`'s body in `routes/worker.py` (lines ~155-348) beyond updating its imports for the functions that moved out from above it. In particular, lines ~230-250 (the Athena `source_kind` branch calling `athena_client.fetch_encounter_summary`/`fetch_clinical_doc`) are SP12's territory — SP13 does not touch that branch's logic, only the import statement at the top of the file that brings in the now-relocated helper functions used elsewhere in the same handler.
- No changes to `routes/care_plan.py` lines ~42-52 (`_score_or_none` wrapper, `_juno_error_logger`) — SP11 deletes these first; SP13 assumes they are already gone and does not redesign them.
- No new GCS buckets, Cloud Run env vars, or Firestore schema changes.
- No broader adoption of `utils/env.py`'s `get_env()` across the codebase (replacing raw `os.environ.get()` calls elsewhere) — out of scope; see §9 Q5.
- No renaming of `utils/firebase.py` to something more generic (e.g. `utils/auth.py`) even though §4e adds a non-Firebase OIDC helper to it — flagged as a future consideration, not done here.
- No pruning of now-superfluous `Constants.Observability.LOG_EXTRA_KEYS` entries (`step_name`, `http_status_code`, `total_duration_ms` were added for `JunoLogger`'s field names and become unused once it's deleted) — harmless to leave; not required for correctness. Noted as an optional follow-up, not designed here.

---

## 4. Architecture Decisions

### 4a. Delete `JunoLogger`; `app.py` uses `Markers`/`JunoContext` only

**Delete:** `backend/utils/juno_logger.py` (entire file — class, `monotonic_ms()`, both).

`monotonic_ms()` is a genuine one-line generic utility (`time.monotonic() * 1000`) independent of `JunoLogger`; it moves into the new `utils/misc.py` (§4c) rather than being deleted, since `app.py` still needs a monotonic millisecond timestamp to compute request duration.

**`backend/app.py` — before:**

```python
from utils.juno_logger import JunoLogger, monotonic_ms
...
@app.before_request
def extract_session_id():
    session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())
    g.session_id = session_id
    g.request_start_ms = monotonic_ms()
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("session.id", session_id)
        current_span.set_attribute("http.route", request.path)
    if request.path != "/health":
        juno_logger = JunoLogger(function="http_request")
        juno_logger.log_request_start(method=request.method, path=request.path)


@app.after_request
def attach_session_id_header(response):
    session_id = getattr(g, "session_id", None)
    if session_id:
        response.headers["X-Session-Id"] = session_id
    span_ctx = trace.get_current_span().get_span_context()
    if span_ctx and span_ctx.is_valid:
        response.headers["X-Trace-Id"] = format(span_ctx.trace_id, "032x")
    if request.path != "/health":
        start_ms = getattr(g, "request_start_ms", None)
        duration_ms = (monotonic_ms() - start_ms) if start_ms is not None else 0.0
        juno_logger = JunoLogger(function="http_request")
        juno_logger.log_request_end(status_code=response.status_code, duration_ms=duration_ms)
        if request.path != "/health" and response.content_type != "text/event-stream":
            def _emit(scope):
                JunoContext.from_g(function="http_request").apply(scope)
                scope.add("http_method", request.method)
                scope.add("http_path", request.path)
                scope.add("http_status", str(response.status_code))
                scope.add("duration_ms_observed", round(duration_ms, 1))
                if response.status_code >= 500:
                    scope.mark_failed()
            Markers.Http.Request.execute(_emit)
    return response
```

**`backend/app.py` — after:**

```python
from utils.misc import monotonic_ms
...
@app.before_request
def extract_session_id():
    """
    Determine the session_id for this request and store it on flask.g
    for use in route handlers, structured logging, and Cloud Trace.

    Source: X-Session-Id request header, or a generated UUID if absent.
    SP4 boundary: session_id never falls back to user_id.
    """
    session_id = request.headers.get("X-Session-Id", "") or str(uuid.uuid4())
    g.session_id = session_id
    g.request_start_ms = monotonic_ms()

    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("session.id", session_id)
        current_span.set_attribute("http.route", request.path)


@app.after_request
def attach_session_id_header(response):
    """Echo the session ID back to the client and emit the request-lifecycle marker."""
    session_id = getattr(g, "session_id", None)
    if session_id:
        response.headers["X-Session-Id"] = session_id

    span_ctx = trace.get_current_span().get_span_context()
    if span_ctx and span_ctx.is_valid:
        response.headers["X-Trace-Id"] = format(span_ctx.trace_id, "032x")

    # Record request-level metrics + timeline log via Markers (skip health checks
    # and SSE routes — the latter emit their own per-chunk markers).
    if request.path != "/health" and response.content_type != "text/event-stream":
        start_ms = getattr(g, "request_start_ms", None)
        duration_ms = (monotonic_ms() - start_ms) if start_ms is not None else 0.0

        def _emit(scope):
            JunoContext.from_g(function="http_request").apply(scope)
            scope.add("http_method", request.method)
            scope.add("http_path", request.path)
            scope.add("http_status", str(response.status_code))
            scope.add("duration_ms_observed", round(duration_ms, 1))
            if response.status_code >= 500:
                scope.mark_failed()
        Markers.Http.Request.execute(_emit)

    return response
```

**Behavioral consequence, stated explicitly:** the standalone `"request_start"` log line is dropped — there is no equivalent under `Markers`, because `CodeMarker.execute()` only emits once, at completion (`finally` block in `marker.py:86-87`), not at the start of an action. `Markers.Http.Request.execute()` retains both outputs `JunoLogger` provided for the *end* of the request (a metric line via `JunoSink`'s `_metric_logger` and a timeline log line via `_event_logger`, both carrying `session_id`/`user_id`/`function`/version fields/`http_status`/`duration_ms`), so no information is lost for request completion — only the separate start-of-request breadcrumb is removed, on the basis that Cloud Trace already marks span start via `init_telemetry(app)`'s Flask instrumentation, and the prior `request_start` log line carried no information beyond what the trace span and the `request_end`/marker event already capture (method + path, both static per-request and present in the marker's dimensions).

**Verification that `JunoLogger` is dead:** `grep -rn "JunoLogger" backend --include="*.py"` (excluding `utils/juno_logger.py` itself) hits only `app.py` (4 lines) and two test files: `tests/utils/test_juno_logger.py` (a dedicated contract-test file for the class) and a comment in `tests/utils/test_care_plan_markers.py`. Both test files are deleted/updated per §7 — this is a test-only codebase, so no compatibility shim is kept.

---

### 4b. Merge `utils/gcs_helpers.py` + `utils/gcs_datasets.py` → `utils/gcs.py`

**New file: `backend/utils/gcs.py`**

```python
"""utils/gcs.py — GCS client construction, generic bucket access, and the
batch-dataset download/cleanup workflow (merged from gcs_helpers.py + gcs_datasets.py)."""

import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google.cloud import storage as gcs

from utils.constants import Constants

logger = logging.getLogger(__name__)

_DEFAULT_BUCKET = os.environ.get("GCP_BUCKET_NAME", "")
# Module-level constant so tests can monkeypatch it.
TEMP_BASE: Path = Path(Constants.Storage.TEMP_BASE)


def _gcs_client() -> gcs.Client:
    """Single construction point for the GCS client (project from GCP_PROJECT_ID env)."""
    return gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)


# ---------------------------------------------------------------------------
# Generic bucket access
# ---------------------------------------------------------------------------

def get_gcs_bucket(bucket_name: str | None = None):
    """Return a GCS Bucket for the given name (default: GCP_BUCKET_NAME env)."""
    name = bucket_name or _DEFAULT_BUCKET
    return _gcs_client().bucket(name)


# ---------------------------------------------------------------------------
# Batch dataset download / cleanup workflow (SP2)
# ---------------------------------------------------------------------------

def download_dataset_inputs(
    group: str, input_id: str, files: list[str], job_id: str,
) -> Path:
    """Download selected files from GCS to a job-scoped temp directory.
    ... (body unchanged from gcs_datasets.py, using _gcs_client() instead of
    a locally-constructed gcs.Client) ...
    """
    bucket_name = os.environ.get("DATASETS_BUCKET_NAME")
    if not bucket_name:
        raise RuntimeError("DATASETS_BUCKET_NAME is not configured")
    bucket = _gcs_client().bucket(bucket_name)
    # ... rest unchanged ...


def cleanup_dataset_inputs(job_id: str) -> None:
    # ... unchanged ...


def sweep_stale_dataset_dirs(max_age_seconds: int = 86400) -> None:
    # ... unchanged ...
```

`download_dataset_inputs` previously took `bucket_name`/`project_id` and built `gcs.Client(project=project_id)` then `client.bucket(bucket_name)` inline (`gcs_datasets.py:41-43`); the merged version reuses `_gcs_client()` (the same constructor `get_gcs_bucket` uses), eliminating the duplicated client-construction code path described in the initiative brief. The two responsibility groups (generic bucket access vs. batch-dataset workflow) stay as clearly section-divided, separate functions in the one file — they were already cleanly separable, only the client constructor was duplicated.

**Delete:** `backend/utils/gcs_helpers.py`, `backend/utils/gcs_datasets.py`.

**Import-site updates:**

| File | Old | New |
|---|---|---|
| `routes/saved_outputs.py:21` | `from utils.gcs_helpers import get_gcs_bucket` | `from utils.gcs import get_gcs_bucket` |
| `services/care_plan_input.py` (new — formerly `routes/care_plan.py:18`) | `from utils.gcs_helpers import get_gcs_bucket` | `from utils.gcs import get_gcs_bucket` |
| `routes/worker.py:217-218` | `from utils.gcs_datasets import download_dataset_inputs` | `from utils.gcs import download_dataset_inputs` |
| `routes/worker.py:345-346` | `from utils.gcs_datasets import cleanup_dataset_inputs` | `from utils.gcs import cleanup_dataset_inputs` |
| `app.py:81-82` | `from utils.gcs_datasets import sweep_stale_dataset_dirs` | `from utils.gcs import sweep_stale_dataset_dirs` |
| `tests/utils/test_gcs_datasets.py` | imports from `utils.gcs_datasets` | rename file to `tests/utils/test_gcs.py` (or keep filename, update imports to `utils.gcs`) — see §7 |
| `tests/routes/test_worker_gcs_dataset.py` | imports/monkeypatches `utils.gcs_datasets.*` | update to `utils.gcs.*` |

---

### 4c. Merge `utils/output_helpers.py` + `utils/html.py` + `utils/env.py` → `utils/misc.py`

**Filename choice and justification:** `utils/misc.py`. These three files share no domain (output-name derivation is care-plan-specific, HTML extraction is a generic parsing helper, `get_env` is a generic env-var accessor) and each is exactly one function. Forcing them under an invented shared domain name would be misleading; "misc" is an honest signal that this is an intentional, narrowly-scoped catch-all for small, side-effect-light, single-purpose helpers — consistent with the brief's own suggested example name. `monotonic_ms` (rescued from the deleted `juno_logger.py`, §4a) and the two pure string-formatting helpers extracted from `routes/care_plan.py` (`_source_separator`, `_text_artifact_filename`, see §4e) join it for the same reason: each is a tiny, generic, reusable function with no business logic and no natural single-function-file justification of its own.

**New file: `backend/utils/misc.py`**

```python
"""utils/misc.py — small, single-purpose, side-effect-light helpers that don't
share a cohesive domain (merged from output_helpers.py, html.py, env.py, plus
generic helpers rescued from juno_logger.py and routes/care_plan.py)."""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment variable access
# ---------------------------------------------------------------------------

def get_env(key: str, default: Optional[str] = None, *, required: bool = False) -> Optional[str]:
    """Return os.environ.get(key, default); raise if required and absent."""
    value = os.environ.get(key)
    if required and not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. Set it before starting the server."
        )
    return value if value is not None else default


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def monotonic_ms() -> float:
    """Return current time in milliseconds (monotonic clock). Use for measuring elapsed durations."""
    return time.monotonic() * 1000


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------

def derive_output_name(
    care_plan_data: dict, source_filename: str = "", group_fallback: str = "",
) -> str:
    """Derive a human-readable output name from care plan data. (body unchanged
    from output_helpers.py)"""
    ...


# ---------------------------------------------------------------------------
# HTML text extraction
# ---------------------------------------------------------------------------

def extract_text_from_html(html_content: bytes) -> str:
    """Extract plain text from HTML bytes. (body unchanged from html.py)"""
    ...


# ---------------------------------------------------------------------------
# String formatting (rescued from routes/care_plan.py — see §4e)
# ---------------------------------------------------------------------------

def source_separator(filename: str) -> str:
    return f"\n\n--- Source: {filename} ---\n"


def text_artifact_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem}.txt"
```

**Delete:** `backend/utils/output_helpers.py`, `backend/utils/html.py`, `backend/utils/env.py`.

**Import-site updates:**

| File | Old | New |
|---|---|---|
| `routes/worker.py:26` | `from utils.output_helpers import derive_output_name` | `from utils.misc import derive_output_name` |
| `services/care_plan_input.py` (new — formerly `routes/care_plan.py:98-99`) | `from utils.html import extract_text_from_html` | `from utils.misc import extract_text_from_html` |
| `app.py` | `from utils.juno_logger import JunoLogger, monotonic_ms` | `from utils.misc import monotonic_ms` |
| `tests/utils/test_output_helpers.py`, `tests/utils/test_html.py`, `tests/utils/test_env.py` | import from the three old modules | consolidate into `tests/utils/test_misc.py` (or update each file's import to `utils.misc` and keep them separate — see §7) |

---

### 4d. `routes/batch_utils.py` → `utils/batch.py`; delete the dead `batch_bp` Blueprint

**Verification that `batch_bp` registration is a no-op:** `grep -n "@batch_bp" backend -r` returns zero matches — no route is ever attached to it. `Blueprint("batch", __name__)` is constructed with no `template_folder`/`static_folder`/`url_prefix` side effects either. `routes/__init__.py` imports it (`from routes.batch_utils import batch_bp`, line 2) and includes it in `API_BLUEPRINTS` (line 13), and `app.py`'s blueprint-registration loop (`for bp in _blueprints: app.register_blueprint(bp)`) registers it. Registering a Blueprint with zero routes adds zero URL rules to the Flask app — this is confirmed dead with no live effect. **Resolved:** remove it entirely (not an open question).

**New file: `backend/utils/batch.py`**

```python
"""Batch-job business helpers: timestamp formatting and dataset-selection
resolution (moved from routes/batch_utils.py)."""

from datetime import datetime, timezone

from utils.preset_data import list_datasets


def batch_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def resolve_requested_runs(selections: list[dict]) -> list[tuple[str, str, list[str]]]:
    """(body unchanged from routes/batch_utils.py's _resolve_requested_runs)"""
    ...
```

Both functions drop their leading underscore — they move from being private implementation details of a routes module to the public API of a `utils/` module.

**Justification for `utils/` over `services/`:** `batch_timestamp` is a trivial, generic formatter — uncontroversially `utils/`. `resolve_requested_runs` is more business-logic-flavored (it validates a batch request's dataset selections against `list_datasets()` and raises domain-specific `ValueError`/`FileNotFoundError`), which on its own might argue for `services/`. It is kept alongside `batch_timestamp` in `utils/batch.py` per the initiative brief's explicit direction, and because it has no IO of its own (it delegates to `utils/preset_data.py`, itself a `utils/` module) and is closer in nature to validation/lookup than to orchestration — consistent with co-locating it next to the other preset-dataset utility code.

**Delete:** `backend/routes/batch_utils.py` (file is removed entirely, not left as an empty stub — see §7 for the test-file consequence).

**`routes/__init__.py` — before:**
```python
from routes.care_plan import care_plan_bp
from routes.batch_utils import batch_bp
from routes.saved_outputs import saved_outputs_bp
...
API_BLUEPRINTS = [
    care_plan_bp,
    batch_bp,
    care_plan_jobs_bp,
    batch_jobs_bp,
    saved_outputs_bp,
    datasets_bp,
    grading_bp,
    admin_bp,
]
```

**`routes/__init__.py` — after:**
```python
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.grading import grading_bp
from routes.care_plan_jobs import care_plan_jobs_bp
from routes.batch_jobs import batch_jobs_bp
from routes.worker import worker_bp
from routes.admin import admin_bp

API_BLUEPRINTS = [
    care_plan_jobs_bp,
    batch_jobs_bp,
    saved_outputs_bp,
    datasets_bp,
    grading_bp,
    admin_bp,
]

WORKER_BLUEPRINTS = [
    worker_bp,
]
```

(`care_plan_bp` removed too, per §4e — both dead Blueprints fall in the same change.)

**Import-site updates:**

| File | Old | New |
|---|---|---|
| `routes/batch_jobs.py:11` | `from routes.batch_utils import _resolve_requested_runs, _batch_timestamp` | `from utils.batch import resolve_requested_runs, batch_timestamp` |
| `routes/batch_jobs.py` (call sites) | `_resolve_requested_runs(...)`, `_batch_timestamp()` | `resolve_requested_runs(...)`, `batch_timestamp()` |

---

### 4e. `routes/care_plan.py` → delete; logic moves to `services/care_plan_pipeline.py` + `services/care_plan_input.py`

This is the largest change in this PRD: `routes/care_plan.py` is not a routes file (§1.B) — every function in it is either pipeline-adapter business logic or input-resolution business logic, imported piecemeal by three other route modules (`routes/care_plan_jobs.py`, `routes/worker.py`, `routes/datasets.py`) — i.e. routes already import private (underscore-prefixed) helpers from another routes module, itself a layering smell this move fixes.

**New file: `backend/services/care_plan_pipeline.py`** — the pipeline-execution adapter.

Houses `run_care_plan_pipeline()` (formerly `routes/care_plan.py:193-289`), unchanged in body, with its existing imports (`CarePlanV1_2Pipeline`, `Markers`, `JunoContext`, `get_tracer`, `build_grading`, `build_error_data_from_exc`, etc.). **Justification:** this function orchestrates the multi-step pipeline (`care_plan/v1_2/pipeline.py`), wires `Markers`/`JunoContext` instrumentation around each step, and runs grading and scoring — genuine service-layer business logic, not a generic helper. It is distinct from the existing `care_plan/v1_2/pipeline.py` package: that package holds the pure step *algorithm* implementations; `services/care_plan_pipeline.py` is the *adapter* that turns the algorithm's step events into `Adapter*` events for the job worker, with instrumentation and grading orchestration layered on top.

**New file: `backend/services/care_plan_input.py`** — input resolution and storage.

| Function (old location) | New name | Justification: services (business logic) vs. the alternative |
|---|---|---|
| `upload_combined_pdf` (`care_plan.py:56-68`) | `upload_combined_pdf` | services — decides the domain-specific GCS path convention (`care_plan/{user_id}/inputs/{uuid}.pdf`) for storing a care-plan input artifact; not a generic upload helper. |
| `_allowed` (`care_plan.py:72-73`) | `is_allowed_extension` | services — encodes the product rule "which file types does care-plan input accept" (reads `Constants.ALLOWED_EXTENSIONS`); kept beside `extract_text_from_bytes` since it's part of the same input-validation flow, not a reusable generic check. |
| `_extract_text_from_bytes` (`care_plan.py:76-101`) | `extract_text_from_bytes` | services — dispatches extraction strategy per extension (PDF/TXT/DOCX/HTML) and encodes which extensions are supported; this is the core "turn an uploaded file into text" business rule, used by 3 different routes. |
| `_resolve_uploaded_files` (`care_plan.py:113-169`) | `resolve_uploaded_files` | services — orchestrates per-file validation (size/type/count limits from `Constants`), extraction, and PDF merging into one `ResolvedInput`; this is the core multi-step input-resolution workflow. |
| `_fetch_from_gcs` (`care_plan.py:172-189`) | `fetch_from_gcs` | services — GCS IO plus the domain-specific "most recently updated blob under this doc_id's upload prefix wins" business rule. |
| `_resolve_input_from_job_doc` (`routes/worker.py:58-62`) | `resolve_input_from_job_doc` | services — dispatches on `JobDoc.input_source_kind` to decide whether to fetch-and-extract from GCS or use the job's stored text; same domain as the functions above, now consolidated with them rather than duplicated reasoning in two files. |
| `_extract_text_from_downloaded` (`routes/worker.py:74-85`) | `extract_text_from_downloaded` | services — assembles pipeline input text from a batch dataset's downloaded files, reusing `extract_text_from_bytes`'s per-extension dispatch; same domain as the other input-resolution functions. |

`_source_separator` and `_text_artifact_filename` (`care_plan.py:104-110`) are **not** moved into `services/care_plan_input.py` — they are pure string formatting with no business meaning (no domain rule, no IO, no validation), so they go to `utils/misc.py` instead (§4c) as `source_separator`/`text_artifact_filename`, and `resolve_uploaded_files` imports them from there.

`AdapterStepEvent`, `AdapterResult`, `AdapterError` were imported into `routes/care_plan.py` from `models/pipeline_events.py` purely as a pass-through (re-exported, never defined there). Callers that did `from routes.care_plan import AdapterStepEvent, ...` switch to importing directly from `models.pipeline_events`.

**Delete:** `backend/routes/care_plan.py` (file removed entirely, including the dead `care_plan_bp` Blueprint — same reasoning as `batch_bp` in §4d: zero `@care_plan_bp.route` decorators, registration is a confirmed no-op).

**Import-site updates:**

| File | Old | New |
|---|---|---|
| `routes/care_plan_jobs.py:15-21` | `from routes.care_plan import (_resolve_uploaded_files, upload_combined_pdf, _fetch_from_gcs, _extract_text_from_bytes, _allowed)` | `from services.care_plan_input import (resolve_uploaded_files, upload_combined_pdf, fetch_from_gcs, extract_text_from_bytes, is_allowed_extension)` |
| `routes/care_plan_jobs.py` (call sites) | `_resolve_uploaded_files(...)`, `_fetch_from_gcs(...)`, `_extract_text_from_bytes(...)`, `_allowed(...)` | renamed (no-underscore) equivalents |
| `routes/worker.py:13-20` | `from routes.care_plan import (run_care_plan_pipeline, _fetch_from_gcs, _extract_text_from_bytes, AdapterStepEvent, AdapterResult, AdapterError)` | `from services.care_plan_pipeline import run_care_plan_pipeline`<br>`from services.care_plan_input import fetch_from_gcs, extract_text_from_bytes`<br>`from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError` |
| `routes/datasets.py:3` | `from routes.care_plan import _extract_text_from_bytes` | `from services.care_plan_input import extract_text_from_bytes` |
| `routes/__init__.py:1` | `from routes.care_plan import care_plan_bp` | (line removed; see §4d's combined before/after) |

---

### 4f. `routes/worker.py` helpers — destinations and per-function justification

After §4e relocates `_resolve_input_from_job_doc` and `_extract_text_from_downloaded` into `services/care_plan_input.py`, the remaining four functions in `routes/worker.py:49-151`:

| Function | Destination | Justification |
|---|---|---|
| `_canonical_input_type` + `_INPUT_TYPE_MAP` (lines 38-50) | `utils/job_helpers.py` (new), as `canonical_input_type` | Pure dict lookup, no IO, no orchestration — a stateless data-shape translation between `JobDoc.input_source_kind` and `Metrics.input_type`. Textbook `utils/`. |
| `_is_batch_item` (lines 53-54) | `utils/job_helpers.py`, as `is_batch_item` | `return job.batch_group_id is not None` — pure predicate on a `JobDoc`, no IO. `utils/`. |
| `_build_error_data` (lines 65-71) | **Deleted**, not relocated | It is a one-line pass-through to `errors.build_error_data(code, detail)` already imported directly in `worker.py` (`from errors import ErrorCode, build_error_data, build_error_data_from_exc`). The wrapper adds a docstring but zero logic; per the initiative's "no legacy/no shims" rule this is dead indirection. All 4 call sites (`_build_error_data(ErrorCode.JOB_TIMEOUT, ...)`, `_build_error_data(ErrorCode.EMPTY_DOCUMENT)`, `_build_error_data(ErrorCode.UNKNOWN_ERROR, ...)` ×2) become direct `build_error_data(...)` calls. |
| `_verify_oidc_token` (lines 89-151) | `utils/firebase.py`, as `verify_oidc_token` | Pure authentication/authorization helper — verifies a Google-signed OIDC JWT against the Cloud Tasks worker URL — structurally the same kind of thing as `verify_firebase_token`/`require_admin`, which already live in `utils/firebase.py`'s "Auth decorators" section. Co-locating keeps all request-authentication logic in one place. (`utils/firebase.py` is Firebase-Admin-SDK-named but already hosts non-Firebase-SDK auth helpers in spirit; renaming the file to something more generic, e.g. `utils/auth.py`, is a reasonable future cleanup but out of scope here — see Non-Goals.) |

**New file: `backend/utils/job_helpers.py`**

```python
"""Pure, stateless helpers for translating between JobDoc and Metrics shapes."""

_INPUT_TYPE_MAP = {
    "upload": "file",
    "batch_dataset": "text",
    "gcs_batch_dataset": "text",
    "doc_id": "doc_id",
    "text": "text",
    "athena_encounter": "text",
    "athena_clinical_doc": "text",
}


def canonical_input_type(source_kind: str) -> str:
    return _INPUT_TYPE_MAP.get(source_kind, "text")


def is_batch_item(job) -> bool:  # job: models.job.JobDoc
    return job.batch_group_id is not None
```

**`routes/worker.py` — resulting import block (replacing the old block at lines 12-28):**

```python
from utils.firebase import get_job_doc, update_job_stage, complete_job, fail_job, verify_oidc_token
from services.care_plan_pipeline import run_care_plan_pipeline
from services.care_plan_input import (
    fetch_from_gcs,
    extract_text_from_bytes,
    resolve_input_from_job_doc,
    extract_text_from_downloaded,
)
from models.pipeline_events import AdapterStepEvent, AdapterResult, AdapterError
from models.care_plan.envelope import CarePlanInternal
from models.job import JobDoc
from models.input import TextInput, DocIdInput
from models.metrics import Metrics
from utils.constants import Constants
from utils.misc import derive_output_name
from utils.gcs import download_dataset_inputs, cleanup_dataset_inputs
from utils.job_helpers import canonical_input_type, is_batch_item
from utils.markers import Markers, JunoContext
from errors import ErrorCode, build_error_data, build_error_data_from_exc
```

After this, `routes/worker.py` contains only: the `PIPELINES` route-wiring dict (legitimate route-level configuration — it decides which service-layer pipeline function the `execute_job` handler dispatches to), and the `execute_job` route handler itself. No free-standing business-logic helpers remain.

---

## 5. API Change Summary

No HTTP-visible behavior changes. This is a pure internal reorganization (file moves, renames, one deleted log line, two deleted dead Blueprints). The one observable change is operational, not API-shaped: the standalone `"request_start"` structured log line (previously emitted by `JunoLogger.log_request_start`) no longer appears in Cloud Logging; request completion continues to be observable via the `Markers.Http.Request` metric + timeline log line (§4a).

---

## 6. Frontend Change Summary

N/A. No frontend files are touched by SP13.

---

## 7. Testing

This sub-project deletes several files and renames many functions; the test suite needs corresponding updates (file moves/renames, not new test logic):

- **`tests/utils/test_juno_logger.py`** — delete entirely (tests a class that no longer exists).
- **`tests/utils/test_care_plan_markers.py`** — the comment referencing "JunoMetrics / JunoLogger boilerplate" becomes stale prose; the file's actual assertions (grep-the-source tests against `routes/care_plan.py`) need their target path updated to `services/care_plan_pipeline.py` once `run_care_plan_pipeline` moves (the four tests do `from routes.care_plan import run_care_plan_pipeline` and read `_SRC = .../routes/care_plan.py` — both need the new path).
- **`tests/utils/test_gcs_datasets.py`** + **`tests/routes/test_worker_gcs_dataset.py`** — update imports/monkeypatch targets from `utils.gcs_datasets` to `utils.gcs`.
- **`tests/utils/test_output_helpers.py`**, **`tests/utils/test_html.py`**, **`tests/utils/test_env.py`** — update imports to `utils.misc`; consider consolidating into one `tests/utils/test_misc.py` to mirror the source merge (not required — three files importing from one module is also fine).
- **`tests/routes/test_batch_utils.py`** — rename/move to `tests/utils/test_batch.py`; update imports from `routes.batch_utils` to `utils.batch` and call sites from `_resolve_requested_runs`/`_batch_timestamp` to `resolve_requested_runs`/`batch_timestamp`.
- **`tests/models/test_envelope.py:126-127`** — `test_model_consuming_routes_import_without_removed_aliases` does `import routes.batch_utils` and `import routes.care_plan` to assert those modules still import cleanly. Once both files are deleted, these two lines must be removed from the test (the assertion they support — "no route file references removed model aliases" — still holds for the remaining files in the loop: `routes/grading.py`, `routes/saved_outputs.py`, plus now `services/care_plan_pipeline.py` and `services/care_plan_input.py` could reasonably be added to the `SimplifiedCarePlan`/`SimplifyOutput` substring-absence loop instead, since that's where the relevant code lives now).
- **New test file suggestion:** `tests/utils/test_job_helpers.py` for `canonical_input_type`/`is_batch_item` (currently untested as standalone functions, only indirectly via worker route tests).
- **`tests/routes/test_worker.py`** — imports `AdapterStepEvent, AdapterResult, AdapterError` from `routes.care_plan`; update to `models.pipeline_events`.
- **`tests/utils/test_save_output.py`** — imports `upload_combined_pdf` from `routes.care_plan`; update to `services.care_plan_input`.
- **`tests/care_plan/test_pipeline_executors.py`** — imports `run_care_plan_pipeline` from `routes.care_plan`; update to `services.care_plan_pipeline`.
- **Manual/integration check:** after the `app.py` change (§4a), trigger a request locally and confirm exactly one structured log line + one log-based metric appear for it (via the dev console formatter), with no `request_start`/`request_end` step-named lines remaining in the output.
- **Blueprint-registration regression check:** after deleting `care_plan_bp`/`batch_bp` from `routes/__init__.py`, run the full route list (`app.url_map`) and confirm the same set of live URL rules as before (since both Blueprints contributed zero rules, the URL map should be byte-for-byte identical).

---

## 8. Manual Intervention Required From You

None. This is a pure code-reorganization sub-project: no new infra, no env vars, no Firestore/GCS schema changes, no Cloud Run config changes, no deploy-time migration steps.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Is `JunoLogger` truly dead in production code? | [RESOLVED: confirmed via grep — only `app.py` (4 call sites) and two test files reference it; no `routes/` or other `utils/` call sites.] |
| Q2 | Does `batch_bp`'s Blueprint registration in `routes/__init__.py`/`app.py` have any live effect? | [RESOLVED: no — zero `@batch_bp.route` decorators exist anywhere, and the Blueprint has no `template_folder`/`static_folder` configured, so registering it adds zero URL rules. Confirmed safe to delete entirely, not just deprecate.] |
| Q3 | Does `routes/care_plan.py`'s `care_plan_bp` have the same dead-Blueprint issue? | [RESOLVED — new finding beyond the original brief: yes, confirmed via grep (zero `@care_plan_bp.route` decorators). The entire file is non-route logic; deleted per §4e, not just trimmed.] |
| Q4 | Merged-file naming: `utils/gcs.py`, `utils/misc.py`, `utils/batch.py`, `utils/job_helpers.py`, `services/care_plan_pipeline.py`, `services/care_plan_input.py`. | [RESOLVED: names chosen and justified in §4b–§4f. Open to bikeshedding at task-generation time but no functional ambiguity remains.] |
| Q5 | `utils/env.py`'s `get_env()` has zero production call sites today — is it dead code that should be deleted instead of merged forward? | [OPEN: it is unused today, but its docstring describes a deliberate "single patch point for test mocking" design intended for future adoption across the codebase (replacing raw `os.environ.get()` calls). Recommendation: keep it (merged into `utils/misc.py`, §4c) rather than delete, since deleting a clearly-intentional-but-not-yet-adopted utility is a different kind of cleanup than deleting genuinely obsolete code (`JunoLogger`, dead Blueprints) — but flagging for an explicit decision since "delete dead code outright" is a locked initiative-wide rule and this is, by call-site count, currently dead. Broader adoption of `get_env()` elsewhere is explicitly out of scope regardless (Non-Goals).] |
| Q6 | `_verify_oidc_token` destination: `utils/firebase.py` (chosen) vs. a new `utils/auth.py`/`utils/oidc.py`. | [RESOLVED for this PRD: `utils/firebase.py`, to co-locate with the existing `verify_firebase_token`/`require_admin` auth decorators rather than fragment auth logic across more files. The naming mismatch (`firebase.py` hosting non-Firebase-SDK OIDC logic) is a known minor wart, captured as a non-blocking future rename candidate, not redesigned here.] |
| Q7 | `resolve_requested_runs`'s placement in `utils/batch.py` vs. `services/` given it's validation-flavored business logic. | [RESOLVED: follows the initiative brief's explicit direction to put `batch_utils.py`'s logic in `utils/`. Noted as a borderline call in §4d; not blocking.] |
| Q8 | `tests/models/test_envelope.py`'s `test_model_consuming_routes_import_without_removed_aliases` directly imports `routes.batch_utils` and `routes.care_plan` — both files are deleted by this PRD. | [RESOLVED: this test must be updated (remove those two `import` lines; optionally extend the `SimplifiedCarePlan`/`SimplifyOutput` substring-absence scan to the new `services/care_plan_pipeline.py`/`services/care_plan_input.py` files). Captured in §7 Testing as required task work, not a blocker to the design — but called out here because it's a concrete pre-existing test that *will* fail (ImportError) if the task implementation deletes the files without updating this test in the same change.] |
