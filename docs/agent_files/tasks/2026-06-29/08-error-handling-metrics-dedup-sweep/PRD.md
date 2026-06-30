# PRD: SP08 — Cross-Cutting Error-Handling + Metrics + Dedup Sweep

**Sub-project:** SP08
**Branch context:** `users/tejitpabari/llm-code-check`
**Date:** 2026-06-29
**Status:** Planning — no implementation started

**Dependencies (must land before or alongside):**
- SP01 (unified errors / `make_error_response`) — already merged per code inspection
- SP02 (Constants namespacing / `ErrorCode`) — already merged
- SP05 (JobDoc shape) — coordinate field names
- SP04 (Athena client) — coordinates `Markers.Athena` leaf ownership (see §9)
- SP06 (Batch entry-point) — coordinates `batch_utils.py` rename and enqueue helper
- SP07 (Pipeline + SSE) — owns edits to `care_plan.py` and `worker.py` orchestration; SP08 only wraps around those, does not rewrite internals

---

## 1. Problem

The backend has four distinct reliability gaps that have accumulated as each sub-project added surface area without a sweep pass:

**A. Unguarded Firestore / GCS surfaces.** The saved-outputs, admin, grading, and firebase-wrapper layers have routes and helper functions that throw unhandled exceptions to Flask's 500 handler instead of returning structured `ApiResponse` errors. Specifically:
- `routes/saved_outputs.py`: `list_saved` (collection stream), `get_saved` (dict access after `get_owned_doc_or_403`), and the Firestore `update()` calls inside `rename_saved` and `toggle_share` are all unguarded.
- `routes/admin.py`: `get_admin_stats` streams the entire collection and sorts in Python with no try/except.
- `routes/grading.py`: `doc.to_dict()` / `output_data` dict traversal and `doc.reference.update()` are unguarded.
- `utils/firebase.py` (lines 181–221): `create_job_doc`, `update_job_stage`, `complete_job`, `fail_job`, `get_job_doc` — thin wrappers with zero error handling; their callers (worker, care_plan_jobs) assume they never throw.

**B. Metrics framework is nearly unused.** The `Markers` registry has 9 leaves (`CarePlan.*` × 7, `Grading.Run`, `Http.Request`) but only two files use them (`app.py` wires `Http.Request`; the pipeline wires `CarePlan.*` and `Grading.Run`). The job-lifecycle worker, saved-outputs CRUD, grading route, admin, datasets, and the job-creation handlers emit no structured metrics at all. The registry has no `Firestore`, `Batch`, `SavedOutputs`, or `Worker` namespaces.

**C. Duplicated logic across files.** Four patterns appear verbatim in two or more places:
1. Output-name derivation (`worker.py:354 _derive_name` vs `batch.py:100 _output_name`).
2. Safe-scoring wrapper (`care_plan.py:233 _score_or_none` vs `grading.py:76 _score_safe`).
3. Bearer-token parse boilerplate inside `verify_firebase_token` and `require_admin` (90% identical).
4. GCS client/bucket construction repeated inline in `care_plan.py` and `saved_outputs.py`.
5. `enqueue_job` + `MissingJobConfigError` / bare `Exception` try/except blocks copy-pasted 3× across `care_plan_jobs.py` and `batch_jobs.py`.

**D. isinstance-ladder request validation** in `rename_saved` (54 lines of manual field checks, lines 87–159) and `grading.py` (no model at all) — both should use Pydantic models that SP03 (Models SP) establishes as the house pattern.

**E. Legacy Firestore field fallback** still present in `saved_outputs.py` lines 176–179 and 206–209 (`or data.get('input_pdf_gcs', '')`). The new envelope location has existed since SP-11+; the fallback silently masks missing data for new writes.

**F. Large flat files** (`saved_outputs.py` ~258 lines; `firebase.py` ~221 lines; `jargon_db.py` ~279 lines) lack section-header comments, making navigation slow.

---

## 2. Goals

1. Every Firestore read/write in `saved_outputs.py`, `admin.py`, `grading.py`, and the five `utils/firebase.py` wrappers is wrapped in a try/except that returns a structured `make_error_response` / logs the exception.
2. `Markers` registry gains four new namespaces (`Worker`, `SavedOutputs`, `Batch`, `Firestore`) with leaf entries wired into at least the job-lifecycle and saved-outputs surfaces.
3. Output-name derivation, safe-scoring, Bearer-parse boilerplate, GCS client construction, and enqueue error blocks each exist in exactly one place; all call sites updated.
4. `rename_saved` and `run_care_plan_grading` use Pydantic request-body models; the isinstance ladders are removed.
5. Legacy `input_pdf_gcs` top-level fallback removed from `saved_outputs.py` (coordinate with SP10 for frontend impact).
6. Section-header comments added to the three large flat files.

---

## 3. Non-Goals

- No changes to the pipeline internals (`care_plan/v1_2/pipeline.py`, SSE chunking) — that is SP07.
- No rewrite of `worker.py`'s orchestration logic — SP07 owns that; SP08 only adds try/except around Firestore helpers and wires markers at the entry/exit of `execute_job`.
- No changes to how `build_error_data` / `build_error_data_from_exc` work in `utils/pipeline_errors.py` — SP01 owns that shape.
- No new GCS buckets, Cloud Run env vars, or Firestore schema migrations.
- No TypeScript / frontend changes except removing the legacy fallback (which is backend-only; frontend reads the same `output_data.input.pdf_gcs_url` path it already uses).
- No changes to `utils/jargon_db.py` logic — only section-header comments are added (Goal 6).
- No changes to `batch.py` orchestration logic — SP06 is the owner; SP08 provides registry leaves for SP06 to reference.

---

## 4. Architecture Decisions

### 4a. Error handling: `utils/firebase.py` Firestore wrappers

**File:** `backend/utils/firebase.py` (lines 181–221)

All five wrappers currently have no try/except. Each should catch `google.cloud.exceptions.GoogleCloudError` (the base for `NotFound`, `DeadlineExceeded`, `ServiceUnavailable`, etc.) and re-raise as a named exception so callers can decide whether to surface it as HTTP 500 or log-and-continue.

Add a thin sentinel exception to `utils/firebase.py` (at top of file, after imports):

```python
class FirestoreError(RuntimeError):
    """Raised when a Firestore operation fails in a firebase wrapper function."""
```

Wrap each of the five wrappers:

```python
def create_job_doc(*, user_id: str, job_id: str, payload: dict) -> None:
    try:
        db = firestore_client()
        db.collection("care_plan_outputs").document(job_id).set(payload)
    except Exception as exc:
        logger.exception("firebase: create_job_doc failed for job_id=%s", job_id)
        raise FirestoreError(f"create_job_doc failed: {exc}") from exc


def update_job_stage(job_id: str, stage: int) -> None:
    try:
        db = firestore_client()
        db.collection("care_plan_outputs").document(job_id).update({
            "stage": stage,
            "updated_at": datetime.now(timezone.utc),
        })
    except Exception as exc:
        logger.exception("firebase: update_job_stage failed for job_id=%s stage=%d", job_id, stage)
        raise FirestoreError(f"update_job_stage failed: {exc}") from exc


def complete_job(job_id: str, output_data: dict, name: str) -> None:
    try:
        now = datetime.now(timezone.utc)
        db = firestore_client()
        db.collection("care_plan_outputs").document(job_id).update({
            "status": "completed",
            "stage": 5,
            "output_data": output_data,
            "name": name,
            "completed_at": now,
            "updated_at": now,
        })
    except Exception as exc:
        logger.exception("firebase: complete_job failed for job_id=%s", job_id)
        raise FirestoreError(f"complete_job failed: {exc}") from exc


def fail_job(job_id: str, error_data: dict) -> None:
    try:
        now = datetime.now(timezone.utc)
        db = firestore_client()
        db.collection("care_plan_outputs").document(job_id).update({
            "status": "error",
            "error_data": error_data,
            "completed_at": now,
            "updated_at": now,
        })
    except Exception as exc:
        logger.exception("firebase: fail_job failed for job_id=%s", job_id)
        raise FirestoreError(f"fail_job failed: {exc}") from exc


def get_job_doc(job_id: str) -> dict | None:
    try:
        db = firestore_client()
        doc = db.collection("care_plan_outputs").document(job_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as exc:
        logger.exception("firebase: get_job_doc failed for job_id=%s", job_id)
        raise FirestoreError(f"get_job_doc failed: {exc}") from exc
```

**Caller impact:**
- `worker.py` (`execute_job`): already has a top-level `except Exception` that calls `fail_job`; that outer handler also catches `FirestoreError` from the wrappers. No caller-side changes needed; the outer handler is sufficient.
- `care_plan_jobs.py` (`create_care_plan_job`): `create_job_doc` is called before `enqueue_job`; a `FirestoreError` here propagates to Flask's 500 handler (now structured via `app.py`'s errorhandler). Acceptable; no partial-job cleanup needed at this point.
- `batch_jobs.py` (`create_care_plan_batch_jobs`): same — `FirestoreError` from `create_job_doc` returns 500; the batch has not been enqueued yet so no cleanup is required.

---

### 4b. Error handling: `routes/saved_outputs.py`

**File:** `backend/routes/saved_outputs.py`

Four endpoints need wrapping.

**`list_saved` (line 37) — wrap the stream:**

```python
@saved_outputs_bp.route('/care_plan/saved', methods=['GET'])
@verify_firebase_token
def list_saved(user_id: str):
    try:
        db = firestore_client()
        docs = (
            db.collection('care_plan_outputs')
            .where('uid', '==', user_id)
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .stream()
        )
        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append({
                'id': doc.id,
                'name': data.get('name', 'Untitled'),
                'source_filename': data.get('source_filename', ''),
                'created_at': data['created_at'].isoformat() if data.get('created_at') else None,
                'updated_at': data['updated_at'].isoformat() if data.get('updated_at') else None,
                'batch_group_id': data.get('batch_group_id'),
                'status': data.get('status', 'completed'),
            })
        return jsonify({'outputs': results})
    except Exception:
        logger.exception("list_saved: Firestore query failed for user_id=%s", user_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
```

**`get_saved` (line 63) — wrap dict access after ownership check:**

```python
@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['GET'])
@verify_firebase_token
def get_saved(user_id: str, doc_id: str):
    try:
        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
        if err:
            return err
        data = doc.to_dict()
        return jsonify({
            'id': doc.id,
            'name': data.get('name', 'Untitled'),
            'source_filename': data.get('source_filename', ''),
            'created_at': data['created_at'].isoformat() if data.get('created_at') else None,
            'output_data': data.get('output_data', {}),
        })
    except Exception:
        logger.exception("get_saved: failed for doc_id=%s", doc_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
```

**`rename_saved` (line 81) — wrap the Firestore `.update()` call (line 161):**

The validation block (lines 87–159) is replaced by a Pydantic model (§4g). The remaining gap is the unguarded write:

```python
    try:
        db.collection('care_plan_outputs').document(doc_id).update(updates)
    except Exception:
        logger.exception("rename_saved: Firestore update failed for doc_id=%s", doc_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return jsonify({'id': doc_id, **{k: v for k, v in updates.items() if k != 'updated_at'}})
```

**`toggle_share` (line 238) — wrap the Firestore `.update()` call (line 254):**

```python
    try:
        db.collection('care_plan_outputs').document(doc_id).update({
            'shared': shared,
            'updated_at': firestore.SERVER_TIMESTAMP,
        })
    except Exception:
        logger.exception("toggle_share: Firestore update failed for doc_id=%s", doc_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return jsonify({'shared': shared})
```

Note: `delete_saved`'s Firestore delete at line 189 is also unguarded. Wrap it identically:

```python
    try:
        db.collection('care_plan_outputs').document(doc_id).delete()
    except Exception:
        logger.exception("delete_saved: Firestore delete failed for doc_id=%s", doc_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return jsonify({'deleted': doc_id})
```

---

### 4c. Error handling: `routes/admin.py`

**File:** `backend/routes/admin.py`

Wrap the entire body of `get_admin_stats`:

```python
@admin_bp.route('/admin/stats', methods=['GET'])
@require_admin
def get_admin_stats(user_id: str):
    try:
        db = firestore_client()
        # ... existing logic unchanged ...
        return jsonify({...})
    except Exception:
        logger.exception("admin: get_admin_stats failed")
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
```

Add import: `from utils.error_codes import make_error_response, ErrorCode` and `from flask import request` at the top of `admin.py`.

---

### 4d. Error handling: `routes/grading.py`

**File:** `backend/routes/grading.py`

Two specific gaps in `run_care_plan_grading`:

1. **Firestore dict access** (lines 38–43): `output_data = data.get(...)` / `raw = ...` — safe (dict `.get()` never throws), but `doc.reference.update({"output_data.grading": grading.to_dict()})` at line 55 is unguarded.

2. **`doc.reference.update()`** (line 55) — wrap:

```python
        try:
            doc.reference.update({"output_data.grading": grading.to_dict()})
        except Exception:
            logger.exception("grading: Firestore update failed for saved_id=%s", saved_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
```

SP08 boundary: SP08 wraps the Firestore call. SP07 owns any deeper pipeline changes inside `run_care_plan_grading`. The Pydantic request-body model for `grading.py` is in §4g.

---

### 4e. Markers registry expansion

**File:** `backend/utils/markers/markers.py`

Add four new top-level namespaces. SP08 owns the registry; other SPs reference leaves by importing `Markers` from `utils.markers`.

```python
from __future__ import annotations
from .marker import CodeMarker, code_marker


class Markers:
    """Juno operation registry. Each leaf's name() is the emitted metric name."""

    class CarePlan:
        # ... existing leaves unchanged ...

    class Grading:
        @code_marker("grading.run")
        class Run(CodeMarker): pass  # existing — fired inside the pipeline

        @code_marker("grading.route")
        class Route(CodeMarker): pass  # new — fired at the HTTP route level

    class Http:
        @code_marker("http.request")
        class Request(CodeMarker): pass  # existing

    # ── New namespaces ─────────────────────────────────────────────────────

    class Worker:
        @code_marker("worker.job_execute")
        class JobExecute(CodeMarker): pass

        @code_marker("worker.job_stage")
        class JobStage(CodeMarker): pass

    class SavedOutputs:
        @code_marker("saved_outputs.list")
        class List(CodeMarker): pass

        @code_marker("saved_outputs.get")
        class Get(CodeMarker): pass

        @code_marker("saved_outputs.rename")
        class Rename(CodeMarker): pass

        @code_marker("saved_outputs.delete")
        class Delete(CodeMarker): pass

        @code_marker("saved_outputs.get_pdf_url")
        class GetPdfUrl(CodeMarker): pass

        @code_marker("saved_outputs.toggle_share")
        class ToggleShare(CodeMarker): pass

    class Batch:
        @code_marker("batch.create_jobs")
        class CreateJobs(CodeMarker): pass  # registry leaf; SP06 wires the call

    class Firestore:
        @code_marker("firestore.job_write")
        class JobWrite(CodeMarker): pass  # generic wrapper for job-doc mutations

    class Athena:
        @code_marker("athena.api_call")
        class ApiCall(CodeMarker): pass  # SP04 wires this; SP08 registers the leaf
```

**Wiring plan by file:**

| File | Marker(s) to wire | Owner |
|---|---|---|
| `routes/saved_outputs.py` | `Markers.SavedOutputs.*` (all 6) | SP08 |
| `routes/grading.py` | `Markers.Grading.Route` | SP08 |
| `routes/worker.py` | `Markers.Worker.JobExecute` | SP08 |
| `routes/batch_jobs.py` or `batch_utils.py` | `Markers.Batch.CreateJobs` | SP06 (references SP08 leaf) |
| `utils/firebase.py` (wrappers) | `Markers.Firestore.JobWrite` | SP08 (optional; instrument `complete_job` and `fail_job`) |
| `utils/athena_client.py` | `Markers.Athena.ApiCall` | SP04 (references SP08 leaf) |

**Example wiring for `saved_outputs.list_saved`:**

```python
from utils.markers import Markers, JunoContext

@saved_outputs_bp.route('/care_plan/saved', methods=['GET'])
@verify_firebase_token
def list_saved(user_id: str):
    def _run(scope):
        JunoContext.from_g(function="list_saved").apply(scope)
        try:
            # ... existing implementation ...
            scope.add("result_count", len(results))
            return jsonify({'outputs': results})
        except Exception:
            scope.mark_failed()
            logger.exception("list_saved: Firestore query failed for user_id=%s", user_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return Markers.SavedOutputs.List.execute(_run)
```

**Example wiring for `worker.execute_job`:**

SP07 owns the internal restructuring of `execute_job`. SP08 wraps only the outer job-lifecycle span, not the pipeline internals:

```python
@worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
def execute_job(job_id: str):
    # ... existing OIDC / queue-name validation (not under marker) ...
    def _run(scope):
        JunoContext.from_g(function="execute_job").apply(scope)
        scope.add("job_id", job_id)
        # ... existing try/except body unchanged; scope.mark_failed() on error paths ...
    return Markers.Worker.JobExecute.execute(_run)
```

SP08 does NOT move the try/except inside `execute_job` — it only wraps the outer boundary. SP07 owns any internal restructuring.

---

### 4f. Shared helper: `utils/output_helpers.py` (new file)

**Files affected:** `routes/worker.py` (line 354 `_derive_name`), `routes/batch.py` (line 100 `_output_name`) → after SP06 renames to `batch_utils.py`

Both functions derive an output name from a `care_plan` dict but with different fallback strategies. Canonical signature merges both:

```python
# backend/utils/output_helpers.py

def derive_output_name(
    care_plan_data: dict,
    source_filename: str = "",
    group_fallback: str = "",
) -> str:
    """Derive a human-readable output name from care plan data.

    Priority:
      1. reason_for_visit[0].reason (title-cased, max 60 chars)
      2. diagnosis.main_conclusion first sentence (max 60 chars)
      3. source_filename stem (if not 'text_input', max 60 chars)
      4. group_fallback (e.g. '{group} {input_id}' for batch; max 60 chars)
      5. 'Appointment'
    """
    try:
        rfv = care_plan_data.get("reason_for_visit")
        if rfv and isinstance(rfv, list):
            reason = (rfv[0].get("reason") or "").strip()
            if reason:
                return reason.title()[:60]
        diagnosis = care_plan_data.get("diagnosis") or {}
        main = (diagnosis.get("main_conclusion") or "").strip()
        if main:
            first_sentence = main.split(".")[0].strip()
            if first_sentence:
                return first_sentence[:60]
    except Exception:
        pass
    if source_filename and source_filename != "text_input":
        stem = source_filename.split(",")[0].strip()
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        stem = stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem.title()[:60]
    if group_fallback:
        return group_fallback[:60]
    return "Appointment"
```

**Call sites to update:**

| File | Old call | New call |
|---|---|---|
| `routes/worker.py:333` | `name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))` | `name = derive_output_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))` |
| `routes/batch.py:100` (or `batch_utils.py` per SP06) | `return _output_name(output_data, group, input_id)` | `return derive_output_name(output_data.get("care_plan", {}), group_fallback=f"{group} {input_id}")` |

Remove `_derive_name` from `worker.py` and `_output_name` from `batch.py` / `batch_utils.py`. Add `from utils.output_helpers import derive_output_name` at the import block of each.

---

### 4g. Shared helper: `score_text_safe` in `utils/scoring.py`

**Files affected:** `routes/care_plan.py` (line 233 `_score_or_none`), `routes/grading.py` (line 76 `_score_safe`)

Both are identical: call `score_text(text)`, catch any exception, return `None` on failure. Add to the existing `utils/scoring.py`:

```python
def score_text_safe(text: str, label: str) -> dict | None:
    """Call score_text; return None and log on any failure."""
    try:
        return score_text(text)
    except Exception:
        logger.exception("scoring: %s-score failed", label)
        return None
```

**Call sites to update:**

| File | Old | New |
|---|---|---|
| `routes/care_plan.py:233` | `def _score_or_none(text, label): ...` (private function) | Remove; import `score_text_safe` from `utils.scoring` |
| `routes/care_plan.py` (callers of `_score_or_none`) | `_score_or_none(text, "before")` | `score_text_safe(text, "before")` |
| `routes/grading.py:76` | `def _score_safe(text, label): ...` (private function) | Remove; import `score_text_safe` from `utils.scoring` |
| `routes/grading.py` (callers of `_score_safe`) | `_score_safe(text, "before")` | `score_text_safe(text, "before")` |

SP07 owns the broader care_plan.py refactor; SP08 only removes `_score_or_none` and updates its call sites within care_plan.py without touching any other function in that file. If SP07 lands first and already touches those lines, SP08 defers to SP07 for that specific change.

---

### 4h. Shared helper: Bearer-token parse in `utils/firebase.py`

**File:** `backend/utils/firebase.py`

`verify_firebase_token` (lines 55–91) and `require_admin` (lines 94–131) share identical Bearer-parse logic. Extract into a private helper at the top of the module, below `require_admin`:

```python
def _extract_bearer_token(auth_header: str | None) -> tuple[str | None, tuple | None]:
    """Parse 'Bearer <token>' from auth_header.

    Returns (token, None) on success, or (None, (error_response_dict, status_int)) on failure.
    Does not verify the token — only parses the header format.
    """
    if not auth_header:
        return None, (make_error_response(ErrorCode.MISSING_AUTH_HEADER, None).to_dict(), 401)
    parts = auth_header.split(' ', 1)
    if len(parts) != 2 or parts[0] != 'Bearer':
        return None, (make_error_response(ErrorCode.MALFORMED_AUTH_HEADER, None).to_dict(), 401)
    return parts[1], None
```

Update both decorators to call `_extract_bearer_token(request.headers.get('Authorization'))` instead of duplicating the four-line parse block.

---

### 4i. Shared helper: GCS client construction in `utils/gcs_helpers.py` (new file)

**Files affected:** `routes/care_plan.py` (upload_combined_pdf, _fetch_from_gcs), `routes/saved_outputs.py` (delete_saved, get_input_pdf_url)

All four call sites do the same two lines:

```python
client = gcs.Client(project=os.environ.get('GCP_PROJECT_ID') or None)
bucket = client.bucket(_BUCKET_NAME)
```

Extract to:

```python
# backend/utils/gcs_helpers.py
import os
from google.cloud import storage as gcs

_DEFAULT_BUCKET = os.environ.get('GCP_BUCKET_NAME', '')

def get_gcs_bucket(bucket_name: str | None = None):
    """Return a GCS Bucket object for the given bucket name (default: GCP_BUCKET_NAME env)."""
    name = bucket_name or _DEFAULT_BUCKET
    client = gcs.Client(project=os.environ.get('GCP_PROJECT_ID') or None)
    return client.bucket(name)
```

**Call sites to update:**

| File | Old | New |
|---|---|---|
| `routes/care_plan.py` (upload_combined_pdf) | inline client + bucket | `bucket = get_gcs_bucket()` |
| `routes/care_plan.py` (_fetch_from_gcs) | inline client + bucket | `bucket = get_gcs_bucket()` |
| `routes/saved_outputs.py` (delete_saved) | inline client + bucket | `bucket = get_gcs_bucket()` |
| `routes/saved_outputs.py` (get_input_pdf_url) | inline client + bucket | `bucket = get_gcs_bucket()` |

SP07 owns the broader care_plan.py refactor; if SP07 already touches upload_combined_pdf / _fetch_from_gcs, coordinate which SP updates those two call sites.

---

### 4j. Shared helper: `enqueue_job_safe` in `utils/cloud_tasks.py`

**Files affected:** `routes/care_plan_jobs.py` (lines 123–144), `routes/batch_jobs.py` (lines 122–138 and 205–221)

The try/except block around `enqueue_job` is copy-pasted 3× with only the log message differing. Extract a helper that encapsulates the error handling and returns an error response or `None`:

```python
# In backend/utils/cloud_tasks.py — add after enqueue_job()

def enqueue_job_safe(
    job_id: str,
    *,
    queue_name: str,
    worker_url: str,
    service_account: str,
    deadline_seconds: int,
    batch_run_id: str | None = None,
    path: str | None = None,
) -> tuple[dict, int] | None:
    """Enqueue a job and return (error_response_dict, status_int) on failure, None on success.

    Callers: ``if err := enqueue_job_safe(...): return err``
    """
    try:
        enqueue_job(
            job_id,
            queue_name=queue_name,
            worker_url=worker_url,
            service_account=service_account,
            deadline_seconds=deadline_seconds,
            batch_run_id=batch_run_id,
        )
        return None
    except MissingJobConfigError:
        logger.exception("enqueue_job_safe: missing Cloud Tasks config for job_id=%s", job_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, path).to_dict(), 500
    except Exception:
        logger.exception("enqueue_job_safe: failed to enqueue Cloud Task for job_id=%s", job_id)
        return make_error_response(ErrorCode.INTERNAL_ERROR, path).to_dict(), 500
```

**Call sites to update (coordinate with SP06 which also edits these handlers):**

| File | Old pattern | New pattern |
|---|---|---|
| `care_plan_jobs.py:123` | `try: enqueue_job(...) except MissingJobConfigError: ... except Exception: ...` | `if err := enqueue_job_safe(..., path=request.path): return err` |
| `batch_jobs.py:122` (GCS loop) | same | same |
| `batch_jobs.py:205` (Athena loop) | same | same |

SP06 is the primary owner of `batch_jobs.py` edits. SP08 provides `enqueue_job_safe` in `cloud_tasks.py` and updates `care_plan_jobs.py`. SP06 updates `batch_jobs.py` (or `batch_utils.py`) to use the new helper. If SP06 lands first, its enqueue blocks should already call `enqueue_job_safe`.

---

### 4k. Pydantic request bodies

**File:** `backend/routes/saved_outputs.py` — `rename_saved` handler (lines 87–159)

Add a `RenameOutputRequest` model (in `models/` or inline at top of `saved_outputs.py`; prefer `models/saved_outputs.py` for consistency with SP03):

```python
# backend/models/saved_outputs.py (new file, or add to existing models package)
from typing import Optional
from pydantic import BaseModel, validator

class RenameOutputRequest(BaseModel):
    name: Optional[str] = None
    comment: Optional[str] = None
    note: Optional[str] = None
    grading: Optional[dict] = None

    @validator('name', pre=True, always=True)
    def name_stripped(cls, v):
        if v is None:
            return v
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("name cannot be empty or whitespace")
        if len(stripped) > 200:
            raise ValueError("name exceeds 200 character limit")
        return stripped

    @validator('comment', 'note', pre=True, always=True)
    def str_fields_max_len(cls, v, field):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError(f"{field.name} must be a string")
        if len(v) > 2000:
            raise ValueError(f"{field.name} exceeds 2000 character limit")
        return v

    @validator('grading', pre=True, always=True)
    def grading_must_be_dict(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError("grading must be an object")
        return v
```

Replace the 54-line isinstance ladder in `rename_saved` with:

```python
    from pydantic import ValidationError
    try:
        req = RenameOutputRequest(**body)
    except ValidationError as exc:
        first_err = exc.errors()[0]
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            f"/care_plan/saved/{doc_id}",
            {"field": first_err.get("loc", ["unknown"])[0], "reason": first_err["msg"]},
        ).to_dict(), 400

    if all(v is None for v in (req.name, req.comment, req.note, req.grading)):
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            f"/care_plan/saved/{doc_id}",
            {"reason": "at least one of 'name', 'comment', 'note', or 'grading' is required"},
        ).to_dict(), 400

    updates: dict = {'updated_at': datetime.now(timezone.utc)}
    if req.name is not None:
        updates['name'] = req.name
    if req.comment is not None:
        updates['comment'] = req.comment
    if req.note is not None:
        updates['output_data.care_plan.note'] = req.note
    if req.grading is not None:
        updates['output_data.grading'] = req.grading
```

**File:** `backend/routes/grading.py` — `run_care_plan_grading` handler

Add a `GradingRequest` model:

```python
# backend/models/grading_request.py (or add to models/grading.py alongside build_grading)
from typing import Optional
from pydantic import BaseModel

class GradingRequest(BaseModel):
    saved_id: Optional[str] = None
    text: Optional[str] = None
    clarified_text: Optional[str] = None
```

Replace `body = request.get_json(silent=True) or {}` and raw `.get()` calls at the top of `run_care_plan_grading` with:

```python
    from pydantic import ValidationError
    try:
        req = GradingRequest(**(request.get_json(silent=True) or {}))
    except ValidationError as exc:
        first_err = exc.errors()[0]
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            request.path,
            {"field": str(first_err.get("loc", ["unknown"])[0]), "reason": first_err["msg"]},
        ).to_dict(), 400
```

Then replace `saved_id = body.get("saved_id")` with `saved_id = req.saved_id`, etc.

---

### 4l. Legacy data-shape removal

**File:** `backend/routes/saved_outputs.py`

Two identical fallback patterns — remove the `or data.get('input_pdf_gcs', '')` leg from both:

**`delete_saved` (lines 176–179):**

```python
# Before:
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)

# After:
gcs_uri = (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url') or ''
```

**`get_input_pdf_url` (lines 206–209):**

```python
# Before:
gcs_uri = (
    (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
    or data.get('input_pdf_gcs', '')
)

# After:
gcs_uri = (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url') or ''
```

Consequence: documents written before the envelope was introduced (which stored `input_pdf_gcs` at top level) will return 404 for the PDF-URL endpoint. This is the intended behavior; those documents are stale. Coordinate with SP10 to confirm no live frontend feature relies on the old field path. If SP10 determines legacy docs must still work, this item is deferred.

---

### 4m. Section-header comments

**File:** `backend/routes/saved_outputs.py` — add section dividers:

```python
# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rename (PATCH)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Signed URL
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Share toggle
# ---------------------------------------------------------------------------
```

**File:** `backend/utils/firebase.py` — add section dividers:

```python
# ---------------------------------------------------------------------------
# Firebase / Firestore initialization
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Document access helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Persistence: general outputs
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Persistence: job lifecycle wrappers
# ---------------------------------------------------------------------------
```

**File:** `backend/utils/jargon_db.py` — add section dividers (no logic changes):

```python
# ---------------------------------------------------------------------------
# Data paths and loader
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Abbreviation lookups
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Term detection helpers
# ---------------------------------------------------------------------------
```

---

## 5. API Change Summary

All error responses for the affected routes change from Flask's default HTML 500 page (when an unhandled exception propagates) to structured `ApiResponse` JSON. HTTP status codes are unchanged. No success-path response shapes change.

| Route | Change |
|---|---|
| `GET /care_plan/saved` | Firestore exception now returns `ApiResponse` 500 instead of HTML 500 |
| `GET /care_plan/saved/<doc_id>` | Same |
| `PATCH /care_plan/saved/<doc_id>` | Same; validation errors now Pydantic-driven (same HTTP 400, structured body unchanged) |
| `DELETE /care_plan/saved/<doc_id>` | Firestore delete exception now returns `ApiResponse` 500 |
| `GET /care_plan/saved/<doc_id>/input-pdf-url` | Legacy `input_pdf_gcs` fallback removed — old-schema docs now return 404 |
| `PATCH /care_plan/saved/<doc_id>/share` | Firestore update exception now returns `ApiResponse` 500 |
| `GET /admin/stats` | Firestore exception now returns `ApiResponse` 500 instead of HTML 500 |
| `POST /care_plan/grade` | Firestore update exception now returns `ApiResponse` 500; request body now Pydantic-validated |
| `POST /internal/jobs/execute/<job_id>` | `FirestoreError` from wrappers is caught by existing outer handler; no HTTP change |

---

## 6. Frontend

Not applicable. No frontend files are modified by SP08. The only user-visible change is the legacy-fallback removal (§4l), which causes old-schema documents to return 404 for the PDF-URL endpoint; SP10 must audit whether any live frontend code path reaches those old documents.

---

## 7. Testing

### Backend unit tests

**`backend/tests/utils/test_firebase.py`** — add or update:

- `test_create_job_doc_raises_firestore_error_on_exception`: mock `firestore_client().collection().document().set` to raise `Exception("network")`; assert `FirestoreError` is raised with the original message in its args.
- `test_update_job_stage_raises_firestore_error`: same pattern for `update()`.
- `test_complete_job_raises_firestore_error`: same.
- `test_fail_job_raises_firestore_error`: same.
- `test_get_job_doc_raises_firestore_error`: mock `.get()` to raise; assert `FirestoreError`.
- `test_extract_bearer_token_missing_header`: call `_extract_bearer_token(None)`; assert returns `(None, (_, 401))`.
- `test_extract_bearer_token_malformed`: call with `"Token abc"`; assert returns `(None, (_, 401))`.
- `test_extract_bearer_token_valid`: call with `"Bearer mytoken"`; assert returns `("mytoken", None)`.

**`backend/tests/utils/test_output_helpers.py`** (new file):

- `test_derive_output_name_rfv`: pass `care_plan_data={"reason_for_visit": [{"reason": "chest pain"}]}`; assert `"Chest Pain"`.
- `test_derive_output_name_diagnosis_fallback`: pass empty `reason_for_visit`, populated `diagnosis.main_conclusion`; assert first sentence title-cased, max 60 chars.
- `test_derive_output_name_filename_fallback`: pass no rfv/diagnosis, `source_filename="annual_checkup.pdf"`; assert `"Annual Checkup"`.
- `test_derive_output_name_group_fallback`: pass nothing, `group_fallback="sp1 0001"`; assert `"Sp1 0001"` (not "Appointment").
- `test_derive_output_name_appointment_fallback`: pass all empty; assert `"Appointment"`.
- `test_derive_output_name_max_60`: pass a 100-char reason; assert output length is 60.

**`backend/tests/utils/test_scoring.py`** (add to existing if it exists, else new):

- `test_score_text_safe_returns_dict_on_success`: mock `score_text` to return `{"score": 5}`; assert `score_text_safe("x", "before") == {"score": 5}`.
- `test_score_text_safe_returns_none_on_exception`: mock `score_text` to raise `RuntimeError`; assert `score_text_safe("x", "before") is None`.

**`backend/tests/utils/test_cloud_tasks.py`** (add):

- `test_enqueue_job_safe_returns_none_on_success`: mock `enqueue_job` to succeed; assert return is `None`.
- `test_enqueue_job_safe_returns_500_on_missing_config`: mock `enqueue_job` to raise `MissingJobConfigError`; assert return is `(dict, 500)` with `error.code == "INTERNAL_ERROR"`.
- `test_enqueue_job_safe_returns_500_on_exception`: mock `enqueue_job` to raise `Exception`; assert same.

**`backend/tests/routes/test_saved_outputs.py`** (add):

- `test_list_saved_returns_500_on_firestore_error`: mock `firestore_client().collection().where()...stream()` to raise `Exception`; assert response status 500, `ApiResponse.status == "error"`.
- `test_rename_saved_returns_500_on_update_error`: mock `.update()` to raise; assert 500.
- `test_toggle_share_returns_500_on_update_error`: same.
- `test_get_input_pdf_url_returns_404_without_legacy_fallback`: create a doc with only `input_pdf_gcs` field (no `output_data.input.pdf_gcs_url`); assert 404 (legacy fallback removed).

**`backend/tests/routes/test_grading.py`** (add):

- `test_run_grading_returns_500_on_firestore_update_error`: mock `doc.reference.update()` to raise; assert 500.
- `test_run_grading_validates_body_with_pydantic`: POST with body `{"saved_id": 123}` (int instead of str); assert 400 with structured error.

**`backend/tests/models/test_saved_outputs_model.py`** (new):

- `test_rename_output_request_name_stripped`: `RenameOutputRequest(name=" foo ")` → `name == "foo"`.
- `test_rename_output_request_empty_name_raises`: `RenameOutputRequest(name=" ")` raises `ValidationError`.
- `test_rename_output_request_name_too_long`: name of 201 chars raises `ValidationError`.
- `test_rename_output_request_comment_not_string_raises`: `RenameOutputRequest(comment=123)` raises.
- `test_rename_output_request_all_none`: valid — `RenameOutputRequest()` succeeds; caller checks all-None.

### Manual integration tests

1. `GET /care_plan/saved` with a valid token while Firestore is unreachable (simulate by revoking credentials in local env); confirm response is `{"status": "error", "error": {"code": "INTERNAL_ERROR", ...}}` and HTTP 500.
2. `PATCH /care_plan/saved/<id>` with `{"name": " "}` (whitespace-only); confirm 400 with `error.code == "INPUT_VALIDATION_ERROR"` and `error.details` mentioning "name".
3. `PATCH /care_plan/saved/<id>/share` with `{"shared": "yes"}` (string, not bool); confirm 400.
4. `GET /care_plan/saved/<id>/input-pdf-url` for a document that has only `input_pdf_gcs` at the top level (no `output_data.input.pdf_gcs_url`); confirm 404.
5. `POST /care_plan/grade` with `{"saved_id": "nonexistent-id"}`; confirm 404 with structured error.
6. `GET /admin/stats` with Firestore unreachable; confirm `ApiResponse` 500 (not HTML).

---

## 8. Manual Intervention Required

None. SP08 is entirely code changes with no infrastructure side effects:
- No new GCS buckets or IAM bindings.
- No Cloud Run env vars.
- No Firestore index additions (the existing composite index on `care_plan_outputs` is unchanged).
- The legacy fallback removal (§4l) is backend-only and backward-incompatible only for old-schema documents. No data migration is needed; those documents simply return 404 for the PDF-URL endpoint going forward.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Error handling added to all listed surfaces in §4b–§4d and the five firebase wrappers in §4a. | [RESOLVED: wrap each unguarded call in try/except → `make_error_response(ErrorCode.INTERNAL_ERROR)` + logger.exception; re-raise from firebase wrappers as `FirestoreError`.] |
| Q2 | Markers registry expanded here (SP08 owns the registry file). | [RESOLVED: SP08 adds `Worker`, `SavedOutputs`, `Batch`, `Firestore`, `Athena` namespaces to `markers.py`. Other SPs reference leaves without modifying the registry file.] |
| Q3 | Helpers de-duplicated into shared utils. | [RESOLVED: `derive_output_name` → `utils/output_helpers.py`; `score_text_safe` → `utils/scoring.py`; `_extract_bearer_token` → private helper inside `utils/firebase.py`; `get_gcs_bucket` → `utils/gcs_helpers.py`; `enqueue_job_safe` → `utils/cloud_tasks.py`.] |
| Q4 | Legacy `saved_outputs` fallback removed. | [RESOLVED: remove `or data.get('input_pdf_gcs', '')` from both `delete_saved` and `get_input_pdf_url`. Old-schema documents return 404 for PDF-URL endpoint — coordinate SP10.] |
| Q5 | Does removing `input_pdf_gcs` fallback affect any live frontend feature? | [OPEN: SP10 must audit whether any live user document (in production Firestore) still has `input_pdf_gcs` at top level and lacks `output_data.input.pdf_gcs_url`. If yes, defer §4l to SP10 or add a one-time Firestore migration script.] |
| Q6 | Athena metrics leaf ownership: does SP04 add `Markers.Athena` or does SP08 add it? | [RESOLVED: SP08 registers `Markers.Athena.ApiCall` in the registry. SP04 wires the actual `Markers.Athena.ApiCall.execute(...)` call inside `utils/athena_client.py`. If SP04 lands before SP08, SP04 must add the leaf itself and SP08 reconciles on merge.] |
| Q7 | SP07 overlap on `care_plan.py` — `_score_or_none` and GCS helpers. | [RESOLVED: if SP07 lands first and touches `_score_or_none` call sites or `_fetch_from_gcs`/`upload_combined_pdf`, SP08 defers those specific lines to SP07 and does not duplicate the edit. Both SPs must communicate which lines each touches before merging.] |
| Q8 | SP06 overlap on `batch_jobs.py` enqueue blocks. | [RESOLVED: SP08 provides `enqueue_job_safe` in `cloud_tasks.py` and updates `care_plan_jobs.py`. SP06 is responsible for updating `batch_jobs.py` (or `batch_utils.py`) to use the new helper. Neither SP touches the other's assigned file for the enqueue pattern.] |
| Q9 | `Markers.Batch.CreateJobs` — who wires it into the route? | [RESOLVED: SP08 registers the leaf; SP06 wires the `Markers.Batch.CreateJobs.execute(...)` call inside the batch-jobs handler it already owns.] |
| Q10 | `GradingRequest` model placement — inline in `grading.py` or in `models/`? | [RESOLVED: add `GradingRequest` to `models/grading.py` alongside `build_grading` and the existing `Grading` model, consistent with SP03's models-in-models pattern.] |
