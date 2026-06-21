# Tasks: Firebase Async Jobs (SP1)

Implements durable Firestore-backed async jobs, Cloud Tasks dispatch, and a split
juno-api / juno-worker Cloud Run deployment. Lands **after SP2** (error contract).

**Assumed interfaces (state up front, adapt if wrong):**
- SP2 delivers `models/errors.py` (`ApiResponse`, `ErrorDetail`), `utils/error_codes.py`
  (`ErrorCode`), and `frontend/src/types/errors.ts` (`ApiError`). Until SP2 merges, SP1 uses
  `{"code": "PIPELINE_ERROR", "message": "<str>"}` as the `error_data` placeholder. When SP2
  lands, replace placeholder calls with SP2's error constructor.
- SP3 (ad-hoc-ui-polish) consumes the `useJobSnapshot` hook SP1 delivers at
  `frontend/src/hooks/useJobSnapshot.ts`. No changes needed here beyond exporting it correctly.
- SSE endpoint removal is deferred to SP3; do **not** remove `POST /care_plan` or
  `POST /care_plan/batch` in this SP.

---

### Task 1 — Add Firestore job-doc helpers to `firebase.py`

- Files: `backend/utils/firebase.py`
- Changes:
  - Add five new functions below the existing `save_care_plan_output()`. Import `datetime,
    timezone` are already present. No new imports needed.
  ```python
  def create_job_doc(*, user_id: str, job_id: str, payload: dict) -> None:
      """Write the initial job doc. job_id is caller-generated (uuid4)."""
      db = firestore_client()
      db.collection("care_plan_outputs").document(job_id).set(payload)


  def update_job_stage(job_id: str, stage: int) -> None:
      """Write stage update during pipeline execution."""
      db = firestore_client()
      db.collection("care_plan_outputs").document(job_id).update({
          "stage": stage,
          "updated_at": datetime.now(timezone.utc),
      })


  def complete_job(job_id: str, output_data: dict, name: str) -> None:
      """Write output_data and mark job completed."""
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


  def fail_job(job_id: str, error_data: dict) -> None:
      """Write error_data and mark job failed."""
      now = datetime.now(timezone.utc)
      db = firestore_client()
      db.collection("care_plan_outputs").document(job_id).update({
          "status": "error",
          "error_data": error_data,
          "completed_at": now,
          "updated_at": now,
      })


  def get_job_doc(job_id: str) -> dict | None:
      """Fetch a job doc. Returns None if not found."""
      db = firestore_client()
      doc = db.collection("care_plan_outputs").document(job_id).get()
      return doc.to_dict() if doc.exists else None
  ```
  - The existing `save_care_plan_output()` is left untouched (still used by the deprecated SSE
    endpoints during the migration window).
- Acceptance criteria:
  - `from utils.firebase import create_job_doc, update_job_stage, complete_job, fail_job, get_job_doc` imports without error.
  - With a mocked Firestore client, `create_job_doc(user_id="u", job_id="j", payload={"uid":"u"})` calls `set()` on `care_plan_outputs/j`.
  - `get_job_doc("nonexistent")` returns `None`.

---

### Task 2 — Add `google-cloud-tasks` dependency

- Files: `backend/requirements.txt`
- Changes:
  - Append `google-cloud-tasks` as a new line after the existing `google-cloud-*` entries. The exact version pin is not required; an unpinned entry matches the project's existing pattern.
  ```
  google-cloud-tasks
  ```
- Acceptance criteria:
  - `pip install -r backend/requirements.txt` completes without error (run in the backend
    Dockerfile context or locally).
  - `from google.cloud import tasks_v2` imports successfully after the install.

---

### Task 3 — Implement `backend/utils/cloud_tasks.py`

- Files: `backend/utils/cloud_tasks.py` (new file)
- Changes:
  - Create the file with one public function `enqueue_job`:
  ```python
  """Cloud Tasks enqueue helper for juno-worker dispatch."""
  import json

  from google.cloud import tasks_v2
  from google.protobuf import duration_pb2


  def enqueue_job(
      job_id: str,
      *,
      queue_name: str,
      worker_url: str,
      service_account: str,
      deadline_seconds: int,
      batch_run_id: str | None = None,
  ) -> None:
      """
      Enqueue a Cloud Task targeting POST /internal/jobs/execute/<job_id>
      on the juno-worker service.

      Args:
          job_id: UUID of the Firestore job doc.
          queue_name: Full queue resource name,
              e.g. 'projects/{proj}/locations/{region}/queues/care-plan-jobs'.
          worker_url: Base URL of the juno-worker Cloud Run service,
              e.g. 'https://juno-worker-abc.run.app'.
          service_account: Invoker SA email with roles/run.invoker on juno-worker,
              e.g. 'juno-worker-invoker@proj.iam.gserviceaccount.com'.
          deadline_seconds: dispatch_deadline for the task (300 for single, 900 for batch).
          batch_run_id: UUID shared by all batch items, or None for single jobs.
      """
      client = tasks_v2.CloudTasksClient()
      url = f"{worker_url.rstrip('/')}/internal/jobs/execute/{job_id}"
      payload = json.dumps({"job_id": job_id, "batch_run_id": batch_run_id}).encode()

      task = {
          "http_request": {
              "http_method": tasks_v2.HttpMethod.POST,
              "url": url,
              "headers": {"Content-Type": "application/json"},
              "body": payload,
              "oidc_token": {
                  "service_account_email": service_account,
                  "audience": url,
              },
          },
          "dispatch_deadline": duration_pb2.Duration(seconds=deadline_seconds),
      }
      client.create_task(request={"parent": queue_name, "task": task})
  ```
- Acceptance criteria:
  - `from utils.cloud_tasks import enqueue_job` imports without error.
  - Unit test with a mocked `tasks_v2.CloudTasksClient`: calling `enqueue_job("abc", queue_name="q", worker_url="https://w.run.app", service_account="sa@p.iam", deadline_seconds=300)` calls `client.create_task` with `url` containing `/internal/jobs/execute/abc`, `oidcToken.serviceAccountEmail == "sa@p.iam"`, and `dispatchDeadline.seconds == 300`.
  - Payload body decodes to `{"job_id": "abc", "batch_run_id": null}`.

---

### Task 4 — Implement `backend/routes/care_plan_jobs.py`

- Files: `backend/routes/care_plan_jobs.py` (new file)
- Changes:
  - Create the file with blueprint `care_plan_jobs_bp` and endpoint `POST /care_plan/jobs`.
  - Reuse `_resolve_uploaded_files`, `_extract_text_from_bytes`, `upload_combined_pdf`,
    `_grading_enabled_from_request` from `routes.care_plan`. Also reuse `_fetch_from_gcs`
    from `routes.care_plan` for doc_id input.
  - Read env vars `CLOUD_TASKS_QUEUE`, `WORKER_URL`, `WORKER_SERVICE_ACCOUNT`,
    `JOB_TIMEOUT_SECONDS_SINGLE` (default `"300"`).
  - Full implementation:
  ```python
  """POST /care_plan/jobs — create a single async care-plan job."""
  import logging
  import os
  import uuid
  from datetime import datetime, timezone

  from flask import Blueprint, g, jsonify, request

  from utils.firebase import create_job_doc, verify_firebase_token
  from utils.cloud_tasks import enqueue_job
  from routes.care_plan import (
      _resolve_uploaded_files,
      upload_combined_pdf,
      _fetch_from_gcs,
      _extract_text_from_bytes,
      _grading_enabled_from_request,
      _allowed,
  )
  from utils.constants import Constants

  logger = logging.getLogger(__name__)
  care_plan_jobs_bp = Blueprint("care_plan_jobs", __name__)


  def _resolve_input_for_job(user_id: str) -> dict:
      """
      Resolve request input into job-doc fields.
      Returns a dict with input_* keys ready to be merged into the job doc.
      Raises ValueError on invalid input.
      """
      json_data = request.get_json(silent=True) or {}
      version = (
          request.form.get("version")
          or json_data.get("version")
          or "v1-2"
      )
      grading_enabled = _grading_enabled_from_request()

      # Priority: text > files > doc_id
      text_input = (request.form.get("text") or json_data.get("text") or "").strip()
      if text_input:
          return {
              "input_source_kind": "text",
              "input_text": text_input,
              "input_doc_id": None,
              "input_source_filename": "text_input",
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
          }

      uploads = request.files.getlist("files")
      if not uploads and "file" in request.files:
          uploads = [request.files["file"]]
      if uploads:
          resolved = _resolve_uploaded_files(uploads)
          pdf_gcs_uri = None
          if resolved.combined_pdf_bytes:
              pdf_gcs_uri = upload_combined_pdf(resolved.combined_pdf_bytes, user_id)
          return {
              "input_source_kind": "upload",
              "input_text": resolved.text,
              "input_doc_id": None,
              "input_source_filename": resolved.source_filename,
              "input_pdf_gcs_uri": pdf_gcs_uri,
              "input_version": version,
              "grading_enabled": grading_enabled,
          }

      doc_id = (request.form.get("doc_id") or json_data.get("doc_id") or "").strip()
      if doc_id:
          file_bytes, filename = _fetch_from_gcs(doc_id)
          if not _allowed(filename):
              raise ValueError("Stored file must be PDF, TXT, or DOCX")
          if len(file_bytes) > Constants.MAX_FILE_BYTES:
              raise ValueError("Stored file exceeds 10 MB limit")
          text = _extract_text_from_bytes(file_bytes, filename)
          return {
              "input_source_kind": "doc_id",
              "input_text": text,
              "input_doc_id": doc_id,
              "input_source_filename": filename,
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
          }

      raise ValueError("Request must include 'files', 'file', 'text', or 'doc_id'")


  @care_plan_jobs_bp.route("/care_plan/jobs", methods=["POST"])
  @verify_firebase_token
  def create_care_plan_job(user_id: str):
      """
      Create a single async care-plan job.
      Returns 202 {"job_id": "<uuid>"}.
      Input validation errors return 400 before writing any Firestore doc.
      """
      try:
          input_fields = _resolve_input_for_job(user_id)
      except (ValueError, FileNotFoundError) as exc:
          return jsonify({"error": str(exc)}), 400

      job_id = str(uuid.uuid4())
      now = datetime.now(timezone.utc)

      job_doc = {
          "uid": user_id,
          "name": "Processing…",
          "source_filename": input_fields["input_source_filename"],
          "created_at": now,
          "updated_at": now,
          "status": "not_started",
          "stage": None,
          "started_at": None,
          "completed_at": None,
          "output_data": None,
          "error_data": None,
          "batch_run_id": None,
          "batch_group_id": None,
          "dataset_group": None,
          **input_fields,
      }
      create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

      try:
          enqueue_job(
              job_id,
              queue_name=os.environ["CLOUD_TASKS_QUEUE"],
              worker_url=os.environ["WORKER_URL"],
              service_account=os.environ["WORKER_SERVICE_ACCOUNT"],
              deadline_seconds=int(os.environ.get("JOB_TIMEOUT_SECONDS_SINGLE", "300")),
          )
      except Exception:
          logger.exception("care_plan_jobs: failed to enqueue Cloud Task for job %s", job_id)
          # Job doc exists in Firestore as not_started; worker can't pick it up.
          # Return 500 so the client knows submission failed.
          return jsonify({"error": "Failed to enqueue job"}), 500

      return jsonify({"job_id": job_id}), 202
  ```
- Acceptance criteria:
  - `POST /care_plan/jobs` with a valid text body → 202, `{"job_id": "<uuid>"}`.
  - Firestore `set()` was called with `status="not_started"`, `stage=None`, all required input fields.
  - `enqueue_job` was called with `deadline_seconds=300` and the correct `job_id`.
  - `POST /care_plan/jobs` with no input → 400, no Firestore write, no Cloud Task.
  - `POST /care_plan/jobs` with an unsupported file type → 400.
  - Unauthenticated request → 401.

---

### Task 5 — Implement `backend/routes/batch_jobs.py`

- Files: `backend/routes/batch_jobs.py` (new file)
- Changes:
  - Create the file with blueprint `batch_jobs_bp` and endpoint `POST /care_plan/batch/jobs`.
  - Reuse `_resolve_requested_runs` and `_combined_text_for_dataset_input` from `routes.batch`.
  - `batch_run_id` is a fresh `uuid.uuid4()` per request; `batch_group_ids` uses the same
    `{group: f"{group}-{timestamp}"}` logic already in `batch.py` (`_batch_timestamp()`).
  - Read env vars `CLOUD_TASKS_QUEUE`, `WORKER_URL`, `WORKER_SERVICE_ACCOUNT`,
    `JOB_TIMEOUT_SECONDS_BATCH` (default `"900"`).
  - Full implementation:
  ```python
  """POST /care_plan/batch/jobs — create async batch care-plan jobs."""
  import logging
  import os
  import uuid
  from datetime import datetime, timezone

  from flask import Blueprint, jsonify, request

  from utils.firebase import create_job_doc, verify_firebase_token
  from utils.cloud_tasks import enqueue_job
  from routes.batch import _resolve_requested_runs, _combined_text_for_dataset_input, _batch_timestamp
  from utils.constants import Constants

  logger = logging.getLogger(__name__)
  batch_jobs_bp = Blueprint("batch_jobs", __name__)


  @batch_jobs_bp.route("/care_plan/batch/jobs", methods=["POST"])
  @verify_firebase_token
  def create_care_plan_batch_jobs(user_id: str):
      """
      Create async care-plan jobs for a batch dataset selection.
      Returns 202 {"batch_run_id": "<uuid>", "job_ids": ["<uuid>", ...]}.
      """
      body = request.get_json(silent=True) or {}
      if not isinstance(body, dict):
          return jsonify({"error": "Request body must be a JSON object"}), 400

      selections = body.get("selections")
      if not isinstance(selections, list) or not selections:
          return jsonify({"error": "Request must include selections"}), 400

      version = body.get("version", "v1-2")
      grading_enabled_raw = body.get("grading_enabled", False)
      grading_enabled = grading_enabled_raw if isinstance(grading_enabled_raw, bool) \
          else str(grading_enabled_raw).strip().lower() in {"1", "true", "yes", "on"}

      try:
          runs = _resolve_requested_runs(selections)
      except (ValueError, FileNotFoundError) as exc:
          return jsonify({"error": str(exc)}), 400

      if len(runs) > Constants.MAX_BATCH_RUNS:
          return jsonify({"error": f"Batch request exceeds maximum of {Constants.MAX_BATCH_RUNS} runs"}), 400

      batch_run_id = str(uuid.uuid4())
      timestamp = _batch_timestamp()
      batch_group_ids = {
          group: f"{group}-{timestamp}"
          for group in sorted({group for group, _, _ in runs})
      }

      now = datetime.now(timezone.utc)
      job_ids: list[str] = []
      deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))

      for group, input_id, files in runs:
          try:
              text = _combined_text_for_dataset_input(group, input_id, files)
          except Exception as exc:
              logger.exception(
                  "batch_jobs: failed to read dataset input %s/%s", group, input_id
              )
              return jsonify({"error": f"Could not read dataset input {group}/{input_id}: {exc}"}), 400

          job_id = str(uuid.uuid4())
          batch_group_id = batch_group_ids[group]
          source_filename = ", ".join(files)

          job_doc = {
              "uid": user_id,
              "name": "Processing…",
              "source_filename": source_filename,
              "created_at": now,
              "updated_at": now,
              "status": "not_started",
              "stage": None,
              "started_at": None,
              "completed_at": None,
              "output_data": None,
              "error_data": None,
              "batch_run_id": batch_run_id,
              "batch_group_id": batch_group_id,
              "dataset_group": group,
              "input_source_kind": "batch_dataset",
              "input_text": text,
              "input_doc_id": None,
              "input_source_filename": source_filename,
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
          }
          create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

          try:
              enqueue_job(
                  job_id,
                  queue_name=os.environ["CLOUD_TASKS_QUEUE"],
                  worker_url=os.environ["WORKER_URL"],
                  service_account=os.environ["WORKER_SERVICE_ACCOUNT"],
                  deadline_seconds=deadline_s,
                  batch_run_id=batch_run_id,
              )
          except Exception:
              logger.exception("batch_jobs: failed to enqueue Cloud Task for job %s", job_id)
              return jsonify({"error": f"Failed to enqueue job {job_id}"}), 500

          job_ids.append(job_id)

      return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202
  ```
- Acceptance criteria:
  - `POST /care_plan/batch/jobs` with valid selections → 202, `{"batch_run_id": "<uuid>", "job_ids": [...]}`.
  - All job docs share the same `batch_run_id`; `batch_group_id` matches the per-group key.
  - `enqueue_job` called once per run with `deadline_seconds=900` and matching `batch_run_id`.
  - Unknown dataset group → 400, no Firestore writes.
  - `MAX_BATCH_RUNS` exceeded → 400.

---

### Task 6 — Implement `backend/routes/worker.py`

- Files: `backend/routes/worker.py` (new file)
- Changes:
  - Create the file with blueprint `worker_bp` and endpoint
    `POST /internal/jobs/execute/<job_id>`.
  - `_resolve_input_from_job_doc` reconstructs text from the job doc fields written by Tasks 4
    and 5. For `doc_id` source, use `_fetch_from_gcs` and `_extract_text_from_bytes` from
    `routes.care_plan`.
  - Pipeline execution reuses `run_care_plan_pipeline` from `routes.care_plan` — the generator
    that yields SSE strings or a result tuple. The worker consumes the generator without yielding
    SSE to a client; it watches for the `RESULT_SENTINEL` tuple.
  - Timeout: read deadline from `X-CloudTasks-TaskETA` header if present; otherwise use
    `SINGLE_JOB_INTERNAL_DEADLINE_S = 270` for single jobs, `BATCH_ITEM_INTERNAL_DEADLINE_S = 870`
    for batch items (`batch_group_id is not None`). Check `time.monotonic() - start > deadline_s`
    before each stage begins.
  - SP2 placeholder for `error_data`: use `{"code": "PIPELINE_ERROR", "message": "<str>"}`.
    When SP2 merges, replace with SP2's error constructor. For timeout errors, use
    `{"code": "JOB_TIMEOUT", "message": "Job timed out"}`.
  - Full implementation skeleton:
  ```python
  """POST /internal/jobs/execute/<job_id> — worker endpoint for Cloud Tasks."""
  import logging
  import time
  from datetime import datetime, timezone

  from flask import Blueprint, request

  from utils.firebase import get_job_doc, update_job_stage, complete_job, fail_job
  from routes.care_plan import (
      run_care_plan_pipeline,
      _fetch_from_gcs,
      _extract_text_from_bytes,
  )
  from models.envelope import CarePlanInternal
  from models.input import TextInput, DocIdInput
  from models.metrics import Metrics
  from utils.constants import Constants

  logger = logging.getLogger(__name__)
  worker_bp = Blueprint("worker", __name__)

  SINGLE_JOB_INTERNAL_DEADLINE_S = 270   # 4.5 min (30 s buffer)
  BATCH_ITEM_INTERNAL_DEADLINE_S = 870   # 14.5 min


  def _is_batch_item(job_doc: dict) -> bool:
      return job_doc.get("batch_group_id") is not None


  def _resolve_input_from_job_doc(job_doc: dict) -> str:
      """Return the text to run through the pipeline."""
      source_kind = job_doc.get("input_source_kind", "text")
      if source_kind == "doc_id":
          doc_id = job_doc["input_doc_id"]
          file_bytes, filename = _fetch_from_gcs(doc_id)
          return _extract_text_from_bytes(file_bytes, filename)
      # "upload", "text", "batch_dataset" — text is stored directly
      return job_doc.get("input_text") or ""


  def _build_error_data(code: str, message: str) -> dict:
      """
      SP1 placeholder for SP2's error shape.
      Replace with SP2's error constructor once SP2 merges.
      """
      return {"code": code, "message": message}


  @worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
  def execute_job(job_id: str):
      """
      Internal endpoint called exclusively by Cloud Tasks.
      Security: verify X-CloudTasks-QueueName header is present.
      Returns 200 for all handled outcomes; 500 for unexpected failures
      (triggers Cloud Tasks retry).
      """
      queue_name_header = request.headers.get("X-CloudTasks-QueueName", "").strip()
      if not queue_name_header:
          logger.warning("worker: rejected request without X-CloudTasks-QueueName")
          return "", 403

      try:
          job_doc = get_job_doc(job_id)
          if job_doc is None:
              logger.warning("worker: job doc not found for job_id=%s — skipping", job_id)
              return "", 200

          if job_doc.get("status") in ("completed", "error"):
              logger.info(
                  "worker: job %s already in terminal state %s — idempotent return",
                  job_id, job_doc["status"],
              )
              return "", 200

          uid = job_doc.get("uid")
          batch_run_id = job_doc.get("batch_run_id")

          # Mark processing
          from utils.firebase import firestore_client
          now = datetime.now(timezone.utc)
          firestore_client().collection("care_plan_outputs").document(job_id).update({
              "status": "processing",
              "started_at": now,
              "stage": 1,
              "updated_at": now,
          })

          # Set internal deadline
          deadline_s = (
              BATCH_ITEM_INTERNAL_DEADLINE_S
              if _is_batch_item(job_doc)
              else SINGLE_JOB_INTERNAL_DEADLINE_S
          )
          start = time.monotonic()

          def _check_timeout(stage: int) -> bool:
              """Returns True if the job has exceeded its internal deadline."""
              elapsed = time.monotonic() - start
              if elapsed > deadline_s:
                  fail_job(job_id, _build_error_data("JOB_TIMEOUT", "Job timed out"))
                  logger.warning(
                      "worker: job %s timed out at stage %d after %.1fs",
                      job_id, stage, elapsed,
                      extra={"job_id": job_id, "batch_run_id": batch_run_id, "uid": uid, "stage": stage},
                  )
                  return True
              return False

          text = _resolve_input_from_job_doc(job_doc)
          if not text.strip():
              fail_job(job_id, _build_error_data("PIPELINE_ERROR", "Input text is empty"))
              return "", 200

          version = job_doc.get("input_version", "v1-2")
          grading_enabled = job_doc.get("grading_enabled", False)
          source_kind = job_doc.get("input_source_kind", "text")
          is_batch = _is_batch_item(job_doc)

          from routes.care_plan import PIPELINES
          pipeline_fn = PIPELINES.get(version, PIPELINES["v1-2"])

          metrics = Metrics.start(
              session_id=job_id,
              pipeline_version=version,
              input_type=source_kind,
          )

          # Run the pipeline generator, watching for stage transitions and the result sentinel
          current_stage = 1
          pipeline_result = None
          pipeline_error: str | None = None

          for chunk in pipeline_fn(text, metrics, grading_enabled, source_kind=source_kind, is_batch=is_batch):
              if isinstance(chunk, tuple) and chunk and chunk[0] == Constants.RESULT_SENTINEL:
                  pipeline_result = chunk
                  continue

              # Parse SSE step events to track stage for Firestore writes
              if isinstance(chunk, str) and chunk.startswith("data: "):
                  import json
                  try:
                      payload = json.loads(chunk.removeprefix("data: ").strip())
                  except Exception:
                      continue

                  if payload.get("step") == "error":
                      pipeline_error = payload.get("error") or "Pipeline failed"
                      break

                  step = payload.get("step")
                  status = payload.get("status")
                  if isinstance(step, int) and status == "active" and step != current_stage:
                      current_stage = step
                      if _check_timeout(current_stage):
                          return "", 200
                      update_job_stage(job_id, current_stage)

          if pipeline_error is not None:
              fail_job(job_id, _build_error_data("PIPELINE_ERROR", pipeline_error))
              return "", 200

          if pipeline_result is None:
              fail_job(job_id, _build_error_data("PIPELINE_ERROR", "Pipeline returned no result"))
              return "", 200

          _, care_plan, grading, _raw_text, _clarified_text = pipeline_result

          # Build output envelope
          if source_kind == "doc_id":
              input_model = DocIdInput(doc_id=job_doc["input_doc_id"])
          else:
              input_model = TextInput(text=text)

          envelope = CarePlanInternal(
              metrics=metrics,
              input=input_model,
              grading=grading,
              care_plan=care_plan,
          )
          output_data = envelope.to_dict()

          # Derive name from output (same logic as _derive_output_name in care_plan.py)
          name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))
          output_data["metrics"]["saved_id"] = job_id

          complete_job(job_id, output_data, name)
          logger.info(
              "worker: job %s completed",
              job_id,
              extra={"job_id": job_id, "batch_run_id": batch_run_id, "uid": uid, "stage": 5},
          )
          return "", 200

      except Exception:
          logger.exception(
              "worker: unexpected error for job %s",
              job_id,
              extra={"job_id": job_id},
          )
          return "", 500  # Cloud Tasks will retry


  def _derive_name(care_plan_data: dict, source_filename: str) -> str:
      """Derive a display name from output_data.care_plan. Mirrors _derive_output_name."""
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
      filename = source_filename or ""
      if filename and filename != "text_input":
          stem = filename.split(",")[0].strip()
          if "." in stem:
              stem = stem.rsplit(".", 1)[0]
          stem = stem.replace("_", " ").replace("-", " ").strip()
          if stem:
              return stem.title()[:60]
      return "Appointment"
  ```
  Note: `_derive_name` duplicates `_derive_output_name` from `care_plan.py`. A future cleanup
  can extract it to a shared util; for SP1, the duplication is acceptable to avoid complicating
  the import graph (worker.py must not import from care_plan.py for naming logic).
- Acceptance criteria:
  - `POST /internal/jobs/execute/<id>` without `X-CloudTasks-QueueName` → 403.
  - Happy path (mock Firestore + mock pipeline): job transitions to `processing`, then
    `completed`; `output_data` written to Firestore.
  - Pipeline error (mock pipeline yields `step=error`): job transitions to `error` with
    `error_data={"code": "PIPELINE_ERROR", ...}`.
  - Idempotent: calling endpoint on a job already in `completed` state → 200, no writes.
  - Timeout (mock pipeline that exceeds `deadline_s`): `fail_job` called with
    `{"code": "JOB_TIMEOUT", ...}`; returns 200.
  - Unexpected exception inside handler → 500.

---

### Task 7 — Update `backend/routes/__init__.py` and `backend/app.py` for `JUNO_MODE`

- Files: `backend/routes/__init__.py`, `backend/app.py`
- Changes to `backend/routes/__init__.py`:
  - Replace the current `all_blueprints` export with two named lists:
  ```python
  from routes.care_plan import care_plan_bp
  from routes.saved_outputs import saved_outputs_bp
  from routes.datasets import datasets_bp
  from routes.batch import batch_bp
  from routes.grading import grading_bp
  from routes.care_plan_jobs import care_plan_jobs_bp
  from routes.batch_jobs import batch_jobs_bp
  from routes.worker import worker_bp

  # SSE routes (care_plan_bp, batch_bp) are deprecated but kept during the SP1 migration window.
  # Remove in SP3 once the frontend is fully migrated and no active SSE sessions remain.
  API_BLUEPRINTS = [
      care_plan_bp,       # POST /care_plan (SSE — deprecated, kept for migration window)
      batch_bp,           # POST /care_plan/batch (SSE — deprecated)
      care_plan_jobs_bp,  # POST /care_plan/jobs
      batch_jobs_bp,      # POST /care_plan/batch/jobs
      saved_outputs_bp,   # GET/PATCH/DELETE /care_plan/saved
      datasets_bp,        # GET /care_plan/datasets
      grading_bp,         # POST /care_plan/grade
  ]

  WORKER_BLUEPRINTS = [
      worker_bp,          # POST /internal/jobs/execute/<job_id>
  ]

  # Backwards-compatible alias so any other code importing all_blueprints still works.
  all_blueprints = API_BLUEPRINTS
  ```
- Changes to `backend/app.py`:
  - Add `JUNO_MODE` branching. Current code registers `all_blueprints`; replace lines 44–46
    (the `for bp in all_blueprints` block) with:
  ```python
  import os as _os
  from routes import API_BLUEPRINTS, WORKER_BLUEPRINTS

  JUNO_MODE = _os.environ.get("JUNO_MODE", "api")
  _blueprints = WORKER_BLUEPRINTS if JUNO_MODE == "worker" else API_BLUEPRINTS
  for bp in _blueprints:
      app.register_blueprint(bp)
  ```
  - Remove the `from routes import all_blueprints` import that was on line 10 (it is replaced
    by the above import).
  - Also update the root endpoint docstring at `/` to mention the two new job endpoints.
- Acceptance criteria:
  - With `JUNO_MODE=api` (or unset): `/care_plan/jobs` and `/care_plan/batch/jobs` are
    registered; `/internal/jobs/execute/<id>` is **not** registered (returns 404).
  - With `JUNO_MODE=worker`: only `/internal/jobs/execute/<id>` is registered; all other
    routes return 404.
  - `from routes import API_BLUEPRINTS, WORKER_BLUEPRINTS, all_blueprints` imports without error
    (backward-compat alias works).

---

### Task 8 — Update `backend/cloudbuild.yaml` to deploy two Cloud Run services

- Files: `backend/cloudbuild.yaml`
- Changes:
  - Extend the current single-step build file to push the image and deploy both services.
    The existing step builds `$_BACKEND_IMAGE`; add steps for push, api deploy, and worker deploy:
  ```yaml
  steps:
    # Step 1: Build image (existing)
    - name: gcr.io/cloud-builders/docker
      args:
        - build
        - --tag
        - $_BACKEND_IMAGE
        - .

    # Step 2: Push image
    - name: gcr.io/cloud-builders/docker
      args:
        - push
        - $_BACKEND_IMAGE

    # Step 3: Deploy juno-api (always-on, public)
    - name: gcr.io/cloud-builders/gcloud
      args:
        - run
        - deploy
        - juno-api
        - --image=$_BACKEND_IMAGE
        - --region=$_REGION
        - --platform=managed
        - --set-env-vars=JUNO_MODE=api
        - --min-instances=1
        - --allow-unauthenticated

    # Step 4: Deploy juno-worker (scale-to-zero, internal-only)
    - name: gcr.io/cloud-builders/gcloud
      args:
        - run
        - deploy
        - juno-worker
        - --image=$_BACKEND_IMAGE
        - --region=$_REGION
        - --platform=managed
        - --set-env-vars=JUNO_MODE=worker
        - --min-instances=0
        - --max-instances=3
        - --no-allow-unauthenticated
        - --ingress=internal

  images:
    - $_BACKEND_IMAGE
  options:
    logging: CLOUD_LOGGING_ONLY
  ```
  - `$_BACKEND_IMAGE` substitution already exists. Add `$_REGION` to the Cloud Build trigger
    substitutions if it is not already present (see §8 of PRD — this is a manual GCP step, noted
    in the summary below).
- Acceptance criteria:
  - `cloudbuild.yaml` has exactly four steps: build, push, deploy juno-api, deploy juno-worker.
  - juno-api step includes `--set-env-vars=JUNO_MODE=api` and `--min-instances=1` and
    `--allow-unauthenticated`.
  - juno-worker step includes `--set-env-vars=JUNO_MODE=worker`, `--min-instances=0`,
    `--max-instances=3`, `--no-allow-unauthenticated`, and `--ingress=internal`.
  - Running `gcloud builds submit --config cloudbuild.yaml --substitutions _BACKEND_IMAGE=...,_REGION=...` on a dry run (or in CI) does not produce a parse error.

---

### Task 9 — Update `GET /care_plan/saved` to include `status` field

- Files: `backend/routes/saved_outputs.py`
- Changes:
  - In the `list_saved` function, add `"status"` to each result dict. Old docs without the field
    get a default of `"completed"` (they were written after a successful pipeline run):
  ```python
  # Current serialization in list_saved (lines ~48-55):
  results.append({
      'id': doc.id,
      'name': data.get('name', 'Untitled'),
      'source_filename': data.get('source_filename', ''),
      'created_at': data['created_at'].isoformat() if data.get('created_at') else None,
      'updated_at': data['updated_at'].isoformat() if data.get('updated_at') else None,
      'batch_group_id': data.get('batch_group_id'),
  })
  # Change to:
  results.append({
      'id': doc.id,
      'name': data.get('name', 'Untitled'),
      'source_filename': data.get('source_filename', ''),
      'created_at': data['created_at'].isoformat() if data.get('created_at') else None,
      'updated_at': data['updated_at'].isoformat() if data.get('updated_at') else None,
      'batch_group_id': data.get('batch_group_id'),
      'status': data.get('status', 'completed'),
  })
  ```
- Acceptance criteria:
  - `GET /care_plan/saved` response includes `"status"` on every item.
  - A doc without a `status` field in Firestore returns `"status": "completed"`.
  - A doc with `status="processing"` returns `"status": "processing"`.
  - No existing fields are removed or renamed.

---

### Task 10 — Add path constants and new API client functions (frontend)

- Files: `frontend/src/constants.ts`, `frontend/src/api/jobs.ts` (new), `frontend/src/api/index.ts`
- Changes to `frontend/src/constants.ts`:
  - Append four new exports at the bottom:
  ```typescript
  export const CARE_PLAN_JOBS_PATH = '/care_plan/jobs';
  export const CARE_PLAN_BATCH_JOBS_PATH = '/care_plan/batch/jobs';
  export const CARE_PLAN_PAGE_ROUTE = '/carePlan';
  export const carePlanPagePath = (id: string) => `/carePlan/${id}`;
  ```
- Changes: create `frontend/src/api/jobs.ts` (new file):
  ```typescript
  import { authenticatedFetch } from './apiClient';
  import { API_URL } from './firebase';
  import { CARE_PLAN_JOBS_PATH, CARE_PLAN_BATCH_JOBS_PATH } from '../constants';
  import type { BatchDatasetSelection } from '../types/datasets';

  export interface CreateJobResponse {
    job_id: string;
  }

  export interface CreateBatchJobsRequest {
    selections: BatchDatasetSelection[];
    version?: string;
    grading_enabled?: boolean;
  }

  export interface CreateBatchJobsResponse {
    batch_run_id: string;
    job_ids: string[];
  }

  export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse> {
    const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_JOBS_PATH}`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Server error: ${res.status}`);
    }
    return res.json();
  }

  export async function createBatchJobs(
    body: CreateBatchJobsRequest,
  ): Promise<CreateBatchJobsResponse> {
    const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_BATCH_JOBS_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Server error: ${res.status}`);
    }
    return res.json();
  }
  ```
- Changes to `frontend/src/api/index.ts`:
  - Add `export * from './jobs';` alongside the existing re-exports.
- Acceptance criteria:
  - `import { createCarePlanJob, createBatchJobs } from '../api/jobs'` resolves without TS error.
  - `import { carePlanPagePath, CARE_PLAN_JOBS_PATH } from '../constants'` resolves.
  - `carePlanPagePath("abc")` returns `"/carePlan/abc"`.
  - `createCarePlanJob` passes the `FormData` as the request body (no `Content-Type` header set
    manually — browser sets multipart boundary automatically).

---

### Task 11 — Implement `useJobSnapshot` Firestore hook (frontend)

- Files: `frontend/src/api/firebase.ts`, `frontend/src/hooks/useJobSnapshot.ts` (new)
- Changes to `frontend/src/api/firebase.ts`:
  - Add Firestore initialization. After the existing `export const firebaseAuth = getAuth(firebaseApp);` line, add:
  ```typescript
  import { getFirestore } from 'firebase/firestore';

  const firestoreDatabaseId = import.meta.env.VITE_FIRESTORE_DATABASE_ID as string | undefined;
  export const firebaseDb = firestoreDatabaseId
    ? getFirestore(firebaseApp, firestoreDatabaseId)
    : getFirestore(firebaseApp);
  ```
  - Also add the import at the top of the file alongside `getAuth`:
  ```typescript
  import { getFirestore } from 'firebase/firestore';
  ```
- Changes: create `frontend/src/hooks/useJobSnapshot.ts` (new file):
  ```typescript
  import { useEffect, useState } from 'react';
  import { doc, onSnapshot } from 'firebase/firestore';
  import { firebaseDb } from '../api/firebase';

  export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

  export interface JobDoc {
    status: JobStatus;
    stage: number | null;
    output_data: Record<string, unknown> | null;
    error_data: { code: string; message: string } | null;  // SP2 placeholder shape
    name: string;
    batch_run_id: string | null;
  }

  export function useJobSnapshot(jobId: string | null): {
    jobDoc: JobDoc | null;
    loading: boolean;
    error: Error | null;
  } {
    const [jobDoc, setJobDoc] = useState<JobDoc | null>(null);
    const [loading, setLoading] = useState(jobId !== null);
    const [error, setError] = useState<Error | null>(null);

    useEffect(() => {
      if (!jobId) {
        setJobDoc(null);
        setLoading(false);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);

      const unsubscribe = onSnapshot(
        doc(firebaseDb, 'care_plan_outputs', jobId),
        (snapshot) => {
          if (!snapshot.exists()) {
            setLoading(false);
            return;
          }
          const data = snapshot.data();
          setJobDoc({
            // Old docs without status are treated as completed (PRD §4.1)
            status: (data.status as JobStatus) ?? 'completed',
            stage: data.stage ?? null,
            output_data: data.output_data ?? null,
            error_data: data.error_data ?? null,
            name: data.name ?? '',
            batch_run_id: data.batch_run_id ?? null,
          });
          setLoading(false);
        },
        (err) => {
          setError(err);
          setLoading(false);
        },
      );

      return () => unsubscribe();
    }, [jobId]);

    return { jobDoc, loading, error };
  }
  ```
- Acceptance criteria:
  - `import { useJobSnapshot } from '../hooks/useJobSnapshot'` resolves without TS error.
  - `import { firebaseDb } from '../api/firebase'` resolves.
  - Unit test with mocked `onSnapshot`: hook returns `loading=true` initially, then `jobDoc`
    populated on first snapshot callback, then `loading=false`.
  - On unmount the unsubscribe function is called (no memory leak).
  - `jobId=null` → `loading=false`, `jobDoc=null`, no Firestore subscription.
  - A doc with no `status` field → `jobDoc.status === 'completed'`.

---

### Task 12 — Add `status` field to `SavedOutputMeta` (frontend type)

- Files: `frontend/src/api/savedOutputs.ts`
- Changes:
  - Add optional `status` field to `SavedOutputMeta`:
  ```typescript
  export interface SavedOutputMeta {
    id: string;
    name: string;
    source_filename: string;
    created_at: string;
    updated_at: string;
    batch_group_id: string | null;
    status?: 'not_started' | 'processing' | 'completed' | 'error';
    // undefined = old doc without status field, treated as completed by the frontend
  }
  ```
- Acceptance criteria:
  - TS compiles without error.
  - Existing code that reads `output.batch_group_id` still compiles (no other fields changed).
  - `output.status === undefined` is a valid type-safe expression.

---

### Task 13 — Update Sidebar to show spinner for in-progress items

- Files: `frontend/src/components/Sidebar/Sidebar.tsx`
- Changes:
  - Add `isInProgress` helper and update `renderRow`:
  ```typescript
  function isInProgress(output: SavedOutputMeta): boolean {
    return output.status === 'not_started' || output.status === 'processing';
  }
  ```
  - In `renderRow`, wrap the three-dot menu button in a conditional. When `isInProgress(output)`
    is true:
    - Replace the `⋯` button with a CSS spinner span (or a small SVG).
    - Block `onSelect(output.id)` click by wrapping the row's `onClick` handler:
      `onClick={() => { if (!isInProgress(output)) onSelect(output.id); }}`
    - Skip rendering the `menuOpenId === output.id` dropdown.
  - Concrete diff to `renderRow`:
  ```tsx
  // Replace:
  //   <button className="sidebar-menu-btn" onClick={...}>⋯</button>
  //   {menuOpenId === output.id && <div className="sidebar-dropdown" ...>...</div>}
  // With:
  {isInProgress(output) ? (
    <span
      className="sidebar-spinner"
      aria-label="Processing"
      style={{
        display: 'inline-block',
        width: '14px',
        height: '14px',
        border: '2px solid var(--accent-violet)',
        borderTopColor: 'transparent',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }}
    />
  ) : (
    <>
      <button
        className="sidebar-menu-btn"
        onClick={e => {
          e.stopPropagation();
          setMenuOpenId(menuOpenId === output.id ? null : output.id);
        }}
      >
        ⋯
      </button>
      {menuOpenId === output.id && (
        <div className="sidebar-dropdown" ref={menuRef} onClick={e => e.stopPropagation()}>
          <button className="sidebar-dropdown-item" onClick={() => {
            setRenamingId(output.id);
            setRenameValue(output.name);
            setMenuOpenId(null);
          }}>Rename</button>
          <button className="sidebar-dropdown-item danger" onClick={() => handleDelete(output.id)}>
            Delete
          </button>
        </div>
      )}
    </>
  )}
  ```
  - Also update the row's `onClick` to block clicks on in-progress items:
  ```tsx
  onClick={() => { if (!isInProgress(output)) onSelect(output.id); }}
  ```
  - Add `@keyframes spin` to `Sidebar.css`:
  ```css
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  ```
- Acceptance criteria:
  - A sidebar item with `status="processing"` shows a spinning circle instead of `⋯`.
  - Clicking a processing item does not call `onSelect`.
  - A sidebar item with `status="completed"` or `status=undefined` shows the `⋯` button and
    behaves as before.
  - The spinner animation does not appear on items that are not in progress.

---

### Task 14 — Implement `CarePlanJobPage.tsx` and `/carePlan/:id` route

- Files:
  - `frontend/src/pages/care-plan/CarePlanJobPage.tsx` (new)
  - `frontend/src/App.tsx`
- Changes: create `frontend/src/pages/care-plan/CarePlanJobPage.tsx`:
  ```tsx
  import { useParams } from 'react-router-dom';
  import { useJobSnapshot } from '../../hooks/useJobSnapshot';
  import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
  import CarePlanView from '../../components/CarePlanView';
  import NavBar from '../../components/NavBar';
  import { INITIAL_STEPS } from './CarePlanPage';  // re-export or duplicate constant
  import type { PipelineStep } from '../../types/carePlan';

  function stepsFromStage(stage: number | null): PipelineStep[] {
    return INITIAL_STEPS.map(step => ({
      ...step,
      status: stage == null
        ? 'waiting'
        : step.id < stage
          ? 'done'
          : step.id === stage
            ? 'active'
            : 'waiting',
    }));
  }

  function stepIcon(status: string): string {
    if (status === 'done') return '✓';
    if (status === 'active') return '◉';
    return '○';
  }

  export default function CarePlanJobPage() {
    const { id } = useParams<{ id: string }>();
    const { jobDoc, loading, error } = useJobSnapshot(id ?? null);

    if (loading) {
      return (
        <>
          <NavBar onNew={() => window.location.assign('/')} />
          <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Loading…
          </div>
        </>
      );
    }

    if (error) {
      const isPermission = error.message?.toLowerCase().includes('permission') ||
        error.message?.toLowerCase().includes('missing or insufficient');
      return (
        <>
          <NavBar onNew={() => window.location.assign('/')} />
          <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
            {isPermission
              ? 'You do not have permission to view this care plan.'
              : `Error loading care plan: ${error.message}`}
          </div>
        </>
      );
    }

    if (!jobDoc) {
      return (
        <>
          <NavBar onNew={() => window.location.assign('/')} />
          <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Care plan not found.
          </div>
        </>
      );
    }

    if (jobDoc.status === 'completed' && jobDoc.output_data) {
      const result = normalizeCarePlanOutput(jobDoc.output_data);
      return (
        <>
          <NavBar onNew={() => window.location.assign('/')} />
          <div style={{ maxWidth: '860px', margin: '0 auto', padding: '80px 32px 32px' }}>
            <CarePlanView result={result.care_plan} grading={result.grading} />
          </div>
        </>
      );
    }

    if (jobDoc.status === 'error') {
      const message = jobDoc.error_data?.message ?? 'An error occurred processing your care plan.';
      return (
        <>
          <NavBar onNew={() => window.location.assign('/')} />
          <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
            {message}
          </div>
        </>
      );
    }

    // status === 'not_started' | 'processing'
    const steps = stepsFromStage(jobDoc.stage);
    return (
      <>
        <NavBar onNew={() => window.location.assign('/')} />
        <div style={{ maxWidth: '600px', margin: '0 auto', padding: '80px 32px' }}>
          <div className="glass-card" style={{ padding: '32px' }}>
            <p className="section-title">Creating your care plan…</p>
            <div className="step-list">
              {steps.map(step => (
                <div className="step-item" key={step.id}>
                  <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
                  <div className="step-content">
                    <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>
                      {step.label}
                    </p>
                    <p className="step-desc">{step.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </>
    );
  }
  ```
  - Note: `INITIAL_STEPS` is currently defined inside `CarePlanPage.tsx` and not exported.
    Either export it from `CarePlanPage.tsx` (`export const INITIAL_STEPS = [...]`) or duplicate
    the array in `CarePlanJobPage.tsx`. Exporting is preferred to avoid drift.
- Changes to `frontend/src/App.tsx`:
  - Import `CarePlanJobPage`:
    ```tsx
    import CarePlanJobPage from './pages/care-plan/CarePlanJobPage';
    ```
  - Add the new route inside `<Routes>`, outside `<Route element={<AuthLayout />}>` (same
    pattern as the existing `CarePlanPage` route — it manages its own NavBar):
    ```tsx
    <Route path="/carePlan/:id" element={<CarePlanJobPage />} />
    ```
- Acceptance criteria:
  - Navigating to `/carePlan/<uuid>` renders `CarePlanJobPage`.
  - With `status=processing, stage=3`: steps 1 and 2 show `done`, step 3 shows `active`,
    steps 4 and 5 show `waiting`.
  - With `status=completed` and `output_data` present: `CarePlanView` is rendered.
  - With `status=error`: error message from `error_data.message` is shown.
  - While `loading=true`: skeleton/loading state is shown.
  - A Firestore permission error displays a 403-style message.
  - TS compiles without error.

---

### Task 15 — Refactor `CarePlanPage.tsx` to POST job and navigate

- Files: `frontend/src/pages/care-plan/CarePlanPage.tsx`
- Changes:
  - Remove all SSE connection logic from `handleSubmit`:
    - Remove the entire `authenticatedFetch(... CARE_PLAN_API_PATH ...)` block (single-run SSE
      path, ~65 lines including the `ReadableStream` reader loop).
    - Remove the `runBatch(...)` block (batch SSE path, ~90 lines).
    - Remove `abortRef` (`useRef<AbortController | null>(null)`) — no longer needed.
    - Remove `steps` / `setSteps` / `resetSteps()` calls from `handleSubmit` — steps display
      is now entirely in `CarePlanJobPage`.
    - Remove `setBatchProgress(null)` and the `batchProgress` state variable — batch progress
      display moves to `CarePlanJobPage`.
    - Remove `updateStep` callback.
  - Add new state: `const [activeJobId, setActiveJobId] = useState<string | null>(null);`
  - Add import: `import { createCarePlanJob, createBatchJobs } from '../../api/jobs';`
  - Add import: `import { carePlanPagePath } from '../../constants';`
  - New `handleSubmit` (single-run path):
    ```typescript
    const formData = new FormData();
    if (inputMode === 'file') {
      files.forEach(f => formData.append('files', f));
    } else {
      formData.append('text', textInput);
    }
    formData.append('version', selectedVersion);
    formData.append('grading_enabled', gradingEnabled.toString());

    try {
      const { job_id } = await createCarePlanJob(formData);
      setActiveJobId(job_id);
      navigate(carePlanPagePath(job_id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setAppState('upload');
    }
    ```
  - New `handleSubmit` (batch path):
    ```typescript
    try {
      const { job_ids } = await createBatchJobs({
        selections: presetDataSelection,
        version: selectedVersion,
        grading_enabled: gradingEnabled,
      });
      // Navigate to the first job's page; batch completion is tracked there.
      if (job_ids.length > 0) {
        navigate(carePlanPagePath(job_ids[0]));
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setAppState('upload');
    }
    ```
  - Since `CarePlanPage` navigates away after POST, the `appState='processing'` section is no
    longer reachable from a fresh submission. Keep it in JSX for now (it is still used by the
    `location.state` path that restores from `VersionsPage`), but `handleSubmit` no longer sets
    `appState='processing'` in the normal flow.
  - Update `handleSelectSaved` to navigate to `/carePlan/:id` instead of loading inline:
    ```typescript
    async function handleSelectSaved(id: string) {
      navigate(carePlanPagePath(id));
    }
    ```
    This removes the `getSavedOutput` REST call from `handleSelectSaved`; `CarePlanJobPage`
    handles loading the doc via `onSnapshot`.
  - Keep all other state and handlers (`handleReset`, `handleFiles`, `handleDownloadJson`,
    `handleDownloadPdf`, `showSplitView`, etc.) unchanged for now; they remain used in the
    `result` section that `location.state` can still populate.
  - Remove now-unused imports: `runBatch` from `datasets`, `authenticatedFetch`,
    `CARE_PLAN_API_PATH` (if no longer used). Keep `getSavedOutput` import only if still
    called elsewhere; with the `handleSelectSaved` change above it can be removed.
- Acceptance criteria:
  - Submitting a file → `createCarePlanJob` called → browser navigates to `/carePlan/<uuid>`.
  - Submitting a batch selection → `createBatchJobs` called → browser navigates to
    `/carePlan/<first-job-id>`.
  - No SSE `ReadableStream` reader code remains in `handleSubmit`.
  - No `abortRef` or `AbortController` references remain.
  - TS compiles without error; no unused import warnings for removed SSE dependencies.
  - Clicking a saved output in the sidebar navigates to `/carePlan/<id>` without a REST GET.

---

### Task 16 — Backend unit tests

- Files:
  - `backend/tests/routes/test_care_plan_jobs.py` (new)
  - `backend/tests/routes/test_batch_jobs.py` (new)
  - `backend/tests/routes/test_worker.py` (new)
  - `backend/tests/utils/test_cloud_tasks.py` (new)
- Changes:
  - `test_care_plan_jobs.py`:
    - Mock `utils.firebase.create_job_doc`, `utils.cloud_tasks.enqueue_job`.
    - `POST /care_plan/jobs` with text body → 202, `{"job_id": ...}`, `create_job_doc` called
      with `status="not_started"`, `enqueue_job` called with `deadline_seconds=300`.
    - `POST /care_plan/jobs` with unsupported file type → 400, no `create_job_doc`, no
      `enqueue_job`.
    - Unauthenticated request → 401.
  - `test_batch_jobs.py`:
    - Mock `utils.firebase.create_job_doc`, `utils.cloud_tasks.enqueue_job`, and
      `utils.preset_data.read_dataset_file`.
    - `POST /care_plan/batch/jobs` with valid selections → 202, all `job_ids` share
      the same `batch_run_id` in both the response and each `create_job_doc` call.
    - `POST /care_plan/batch/jobs` with unknown dataset group → 400.
  - `test_worker.py`:
    - Mock `utils.firebase.get_job_doc`, `utils.firebase.update_job_stage`,
      `utils.firebase.complete_job`, `utils.firebase.fail_job`, and
      `routes.care_plan.PIPELINES`.
    - Without `X-CloudTasks-QueueName` header → 403.
    - Happy path: pipeline yields `RESULT_SENTINEL` → `complete_job` called → 200.
    - Pipeline error: pipeline yields `step=error` SSE → `fail_job` called with
      `code="PIPELINE_ERROR"` → 200.
    - Idempotent: `get_job_doc` returns `{"status": "completed"}` → 200, no writes.
    - Timeout: internal deadline exceeded before pipeline completes → `fail_job` called with
      `code="JOB_TIMEOUT"` → 200.
    - Unexpected exception in handler → 500.
  - `test_cloud_tasks.py`:
    - Mock `google.cloud.tasks_v2.CloudTasksClient`.
    - `enqueue_job("abc", ...)` calls `create_task` with URL ending in
      `/internal/jobs/execute/abc`, `oidcToken.serviceAccountEmail` set, payload body
      decodes to `{"job_id": "abc", "batch_run_id": null}`, `dispatchDeadline.seconds == 300`.
- Acceptance criteria:
  - All new test files pass: `pytest backend/tests/routes/test_care_plan_jobs.py backend/tests/routes/test_batch_jobs.py backend/tests/routes/test_worker.py backend/tests/utils/test_cloud_tasks.py -v`.
  - No real Firestore or Cloud Tasks calls are made (all mocked).

---

### Task 17 — Frontend tests

- Files:
  - `frontend/src/tests/hooks/useJobSnapshot.test.ts` (new)
  - `frontend/src/tests/pages/CarePlanJobPage.test.tsx` (new)
- Changes:
  - `useJobSnapshot.test.ts`:
    - Mock `firebase/firestore` (`onSnapshot`, `doc`).
    - `useJobSnapshot("job-1")` → initially `loading=true`, `jobDoc=null`.
    - On snapshot callback with `{status: "processing", stage: 3}` → `loading=false`,
      `jobDoc.status === "processing"`, `jobDoc.stage === 3`.
    - On unmount → unsubscribe function called.
    - `useJobSnapshot(null)` → `loading=false`, `jobDoc=null`, no `onSnapshot` call.
    - Snapshot with no `status` field → `jobDoc.status === "completed"`.
  - `CarePlanJobPage.test.tsx`:
    - Mock `useJobSnapshot` hook.
    - With `status="processing", stage=3` → steps 1,2 show `done`; step 3 shows `active`;
      steps 4,5 show `waiting`.
    - With `status="completed"` and `output_data` → `CarePlanView` rendered.
    - With `status="error"`, `error_data.message="Pipeline failed"` → "Pipeline failed" shown.
    - While `loading=true` → loading skeleton shown.
- Acceptance criteria:
  - `npm test -- --testPathPattern="useJobSnapshot|CarePlanJobPage"` passes.
  - No real Firestore SDK calls are made (all mocked).

---

## Summary of what requires you (not a dev agent)

The following steps cannot be coded and require manual GCP console or CLI action before the deployment will function end-to-end:

1. **Create the Cloud Tasks queue** before deploying:
   ```
   gcloud tasks queues create care-plan-jobs --location=$REGION \
     --max-concurrent-dispatches=3
   ```
   Setting `max-concurrent-dispatches=3` matches `--max-instances=3` on juno-worker so the
   queue doesn't dispatch faster than the worker accepts.

2. **Create the invoker service account** and grant it `roles/run.invoker` on juno-worker:
   ```
   gcloud iam service-accounts create juno-worker-invoker \
     --display-name="Juno Worker Cloud Tasks Invoker"
   gcloud run services add-iam-policy-binding juno-worker \
     --region=$REGION \
     --member="serviceAccount:juno-worker-invoker@$PROJECT.iam.gserviceaccount.com" \
     --role="roles/run.invoker"
   ```

3. **Add env vars to Cloud Run services** (set these in the Cloud Console or in the Cloud Build
   `gcloud run deploy` args; they are not hardcoded in code):
   - juno-api: `CLOUD_TASKS_QUEUE` (full resource name), `WORKER_URL` (juno-worker base URL),
     `WORKER_SERVICE_ACCOUNT`, `JOB_TIMEOUT_SECONDS_SINGLE=300`, `JOB_TIMEOUT_SECONDS_BATCH=900`.
   - juno-worker: `JUNO_MODE=worker` (already set by cloudbuild.yaml after Task 8).

4. **Add `$_REGION` substitution variable** to the Cloud Build trigger (GCP Console →
   Cloud Build → Triggers → edit trigger → add substitution `_REGION=<your-region>`).
   `$_BACKEND_IMAGE` should already exist.

5. **Verify Firestore security rules** allow authenticated frontend reads of
   `care_plan_outputs` docs by the owning user:
   ```
   match /care_plan_outputs/{docId} {
     allow read: if request.auth != null && request.auth.uid == resource.data.uid;
     allow write: if false;  // backend only, via Admin SDK
   }
   ```
   Deploy updated rules if they are missing or more permissive.

6. **Confirm the Firestore database ID** used by the backend (`FIRESTORE_DATABASE_ID` env var
   on Cloud Run). If it is **not** `(default)`, set `VITE_FIRESTORE_DATABASE_ID=<id>` in the
   frontend environment (`.env.production` or Vercel/hosting env vars) so the frontend connects
   to the same named database (Task 11 wires this automatically when the env var is set).

7. **SP2 error shape replacement** (implementation-time dependency, not a GCP step): once SP2
   merges and delivers `models/errors.py` / `utils/error_codes.py`, replace the two placeholder
   calls in `worker.py`'s `_build_error_data` with SP2's canonical error constructor. Grep for
   `PIPELINE_ERROR` and `JOB_TIMEOUT` in `backend/routes/worker.py` to find them. This is
   a ~5-line change after SP2 lands.
