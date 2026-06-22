# PRD: Firebase Async Jobs (SP1)

Sub-project 1 of the Juno async-jobs initiative. Phase 2, depends on SP2 (Error Contract). Lands
after SP2. Every locked decision in this doc was set at the initiative level and is not up for
re-debate in TASKS.

## 1. Problem

The current architecture runs the care-plan pipeline **synchronously inside an HTTP response** using
Server-Sent Events (SSE). This means:

- The frontend holds an open HTTP streaming connection for the entire pipeline duration (30–90 s).
- A single Cloud Run instance is consumed for the full duration of each job, making batch runs
  strictly sequential — item N cannot start until item N-1 finishes.
- If the user closes the tab, the pipeline still runs (no signal to abort) but the result is lost.
- Batch jobs share one SSE connection, so a single instance processes all items serially regardless
  of instance availability.
- There is no durable job state: if the Cloud Run instance crashes mid-pipeline, the result is
  permanently lost and the frontend shows a broken stream with no recovery path.
- The frontend cannot deep-link to a care plan by ID; the URL is always `/`.

## 2. Goals

1. Replace SSE streaming with Firestore-backed async jobs: every job has a durable Firestore doc
   that records status, progress stage, and final output.
2. Split Cloud Run into two services from the same Docker image — juno-api (always-on, CRUD) and
   juno-worker (scale-to-zero, pipeline execution) — controlled by `JUNO_MODE` env var.
3. Route each job through Cloud Tasks so the queue absorbs submission bursts and the worker scales
   independently (max 3 instances).
4. Parallelize batch: each batch item becomes one Cloud Task; up to 3 items run simultaneously.
5. Introduce `batch_run_id` (UUID per batch submission) for correlated observability across
   workers.
6. Change frontend to POST job → receive `job_id` → `onSnapshot` Firestore doc for progress.
7. Add `/carePlan/:id` deep-link route; job_id = output_id = URL param.
8. Sidebar shows spinner for in-progress items; hides three-dot menu while processing.
9. Enforce per-job timeouts: 5 min (single), 15 min (batch item) via Cloud Tasks deadline + worker
   internal deadline.

## 3. Non-Goals

- **Not** changing any pipeline logic, scoring math, or LLM prompts.
- **Not** building a Cloud Tasks admin UI, dead-letter queue UI, or retry UI. Retries are Cloud
  Tasks defaults; the dev does not configure custom retry policies beyond what is noted in §4.
- **Not** migrating existing Firestore docs in `care_plan_outputs` — old docs without the new
  `status` / `stage` fields will never have those fields added. The read path tolerates their
  absence (see §4.1).
- **Not** implementing user-facing job cancellation. Abort from the frontend stops watching the doc
  but does not cancel the Cloud Task.
- **Not** changing the grading route (`POST /care_plan/grade`) — it is synchronous, returns JSON,
  and stays that way.
- **Not** changing the datasets list route (`GET /care_plan/datasets`).
- **Not** building any real-time admin dashboard or observability tooling — that is SP4.
- **Not** doing the SP3 UI polish work (sidebar resize, nav reorganization, sign-out).
- **Not** defining error shapes — those are SP2's deliverable. SP1 references SP2's `error_data`
  shape by name and documents the hand-off contract (see §9).

## 4. Architecture Decisions

### 4.0 File layout overview

New files (backend):
```
backend/
  routes/
    care_plan_jobs.py        # POST /care_plan/jobs (API service)
    batch_jobs.py            # POST /care_plan/batch/jobs (API service)
    worker.py                # POST /internal/jobs/execute/<job_id> (worker service)
  utils/
    cloud_tasks.py           # enqueue_job() helper
```

Modified files (backend):
```
backend/app.py               # JUNO_MODE branching
backend/routes/__init__.py   # two blueprint lists
backend/cloudbuild.yaml      # two Cloud Run service deploys
backend/utils/firebase.py    # new job-doc helpers
```

New files (frontend):
```
frontend/src/api/jobs.ts     # POST /care_plan/jobs, POST /care_plan/batch/jobs
frontend/src/hooks/useJobSnapshot.ts  # Firestore onSnapshot hook for a job doc
frontend/src/pages/care-plan/CarePlanJobPage.tsx  # /carePlan/:id deep-link page
```

Modified files (frontend):
```
frontend/src/App.tsx          # add /carePlan/:id route
frontend/src/pages/care-plan/CarePlanPage.tsx  # remove SSE, call POST jobs, use onSnapshot
frontend/src/components/Sidebar/Sidebar.tsx    # spinner for in-progress, hide menu
frontend/src/api/savedOutputs.ts               # SavedOutputMeta gains status field
frontend/src/constants.ts                      # new path constants
```

---

### 4.1 Firestore job doc schema

Collection: `care_plan_outputs` (unchanged — job doc and output doc are the same document).

New fields added to the existing doc shape:

| Field | Type | Notes |
|---|---|---|
| `status` | `"not_started" \| "processing" \| "completed" \| "error"` | Job lifecycle state |
| `stage` | `int \| None` | Current pipeline step (1–5); null until pipeline starts |
| `error_data` | SP2 error shape or `None` | Populated by worker on failure; shape defined by SP2 |
| `started_at` | `datetime \| None` | When worker picked up the job |
| `completed_at` | `datetime \| None` | When job reached terminal state |
| `batch_run_id` | `str \| None` | UUID shared by all items in one batch submission |

Fields already present (unchanged):

```
uid, name, source_filename, created_at, updated_at,
output_data, batch_group_id, dataset_group
```

`output_data` is left `None` / absent until `status=completed`; the worker writes it atomically
with `status=completed`.

Old docs without `status` will have `status=undefined` in Firestore. The frontend and API must
treat `undefined` status as `"completed"` so legacy saved outputs display correctly (they were
written after a successful pipeline run). The worker never reads old docs, so no backend tolerance
is needed.

Full initial doc written by `POST /care_plan/jobs` (before pipeline runs):

```python
{
    "uid": user_id,
    "name": "<derived name or 'Processing…'>",
    "source_filename": source_filename,
    "created_at": now,
    "updated_at": now,
    "status": "not_started",
    "stage": None,
    "started_at": None,
    "completed_at": None,
    "output_data": None,
    "error_data": None,
    "batch_run_id": None,           # set for batch items
    "batch_group_id": None,         # set for batch items
    "dataset_group": None,          # set for batch items
}
```

---

### 4.2 GCS file-passing strategy (critical architecture decision)

Cloud Tasks payload limit is ~100 KB. File inputs can be up to 10 MB. **Files must be in GCS
before the job doc is created.**

The existing route already handles GCS upload for file inputs via `upload_combined_pdf()` which
uploads the merged PDF and returns a `gs://` URI. The `doc_id` path (`source_kind="doc_id"`)
already reads from GCS.

New flow for file input:

1. `POST /care_plan/jobs` receives `multipart/form-data` with file(s).
2. API service extracts text (same `_resolve_uploaded_files` logic, reused from `care_plan.py`).
3. API service uploads combined PDF to GCS → stores `gs://` URI.
4. API service stores the extracted `text` in Firestore job doc under a new field `input_text`
   (plain string, stored in the job doc itself; pipeline reads it from Firestore, not from the
   Cloud Task payload).
5. Cloud Task payload carries only `job_id`, `batch_run_id`, and `version` — no file bytes.
6. Worker fetches the job doc, reads `input_text` from it.

For `doc_id` input: `doc_id` is small and goes into the job doc as `input_doc_id`; worker fetches
from GCS.

For `text` input: text goes into the job doc as `input_text` directly.

```
# New fields on the job doc (written at job creation time, read by worker)
"input_text": str | None          # plain extracted text
"input_doc_id": str | None        # for doc_id source only
"input_source_kind": str          # "upload" | "text" | "doc_id" | "batch_dataset"
"input_source_filename": str      # for display / name derivation
"input_pdf_gcs_uri": str | None   # gs:// URI of combined input PDF, if uploaded
"input_version": str              # e.g. "v1-2"
"grading_enabled": bool
```

These fields are internal to the job doc; they are NOT part of `output_data`.

---

### 4.3 `POST /care_plan/jobs` — new API endpoint

File: `backend/routes/care_plan_jobs.py`

Blueprint: `care_plan_jobs_bp`, registered only when `JUNO_MODE=api`.

```python
@care_plan_jobs_bp.route("/care_plan/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_job(user_id: str):
    """
    Accept: multipart/form-data OR application/json.
    Input: files | text | doc_id (same priority as existing _resolve_input).
    Returns: {"job_id": "<uuid>"}
    """
```

Steps:
1. Resolve input using existing logic (extract text, upload PDF to GCS if file upload).
2. Derive a preliminary name: use `"Processing…"` (full name derived by worker on completion when
   output_data is available; for file inputs a filename-based fallback can be used immediately).
3. Write initial job doc to Firestore (schema from §4.1 + input fields from §4.2).
4. Enqueue Cloud Task targeting `POST /internal/jobs/execute/<job_id>` on juno-worker.
5. Return `{"job_id": job_id}` with HTTP 202.

Error responses follow SP2's error shape. Input validation errors (unsupported file type, size
exceeded, no input) return HTTP 400 before writing any Firestore doc.

---

### 4.4 `POST /care_plan/batch/jobs` — new batch API endpoint

File: `backend/routes/batch_jobs.py`

Blueprint: `batch_jobs_bp`, registered only when `JUNO_MODE=api`.

```python
@batch_jobs_bp.route("/care_plan/batch/jobs", methods=["POST"])
@verify_firebase_token
def create_care_plan_batch_jobs(user_id: str):
    """
    Body: {"selections": [...], "version": "v1-2", "grading_enabled": false}
    Returns: {"batch_run_id": "<uuid>", "job_ids": ["<uuid>", ...]}
    """
```

Steps:
1. Parse and validate `selections` using existing `_resolve_requested_runs` logic (reuse from
   `batch.py`).
2. Generate `batch_run_id = str(uuid.uuid4())`.
3. Compute `batch_group_ids` dict (same `{group: f"{group}-{timestamp}"}` logic as today).
4. For each `(group, input_id, files)` run:
   a. Read dataset file bytes → extract text (reuse `_combined_text_for_dataset_input`).
   b. Write a Firestore job doc: status=not_started, batch_run_id=batch_run_id,
      batch_group_id=batch_group_ids[group], dataset_group=group, input fields from §4.2.
   c. Enqueue one Cloud Task.
5. Return `{"batch_run_id": batch_run_id, "job_ids": [<list of all job_ids>]}` with HTTP 202.

`batch_run_id` flows through:
- Written to each Firestore job doc at creation.
- Included in Cloud Task payload (JSON body).
- Worker reads it from job doc (or payload as fallback) and stamps it on all structured log
  fields and metrics for that job.

Note: batch dataset inputs are text-only (read from preset data files), so no GCS upload is
needed. `input_text` is written directly to the job doc.

---

### 4.5 Cloud Task payload and enqueue helper

File: `backend/utils/cloud_tasks.py`

```python
def enqueue_job(
    job_id: str,
    *,
    queue_name: str,         # e.g. "care-plan-jobs"
    worker_url: str,         # e.g. "https://juno-worker-xxx.run.app"
    service_account: str,    # e.g. "juno-worker-invoker@proj.iam.gserviceaccount.com"
    deadline_seconds: int,   # 300 for single, 900 for batch
    batch_run_id: str | None = None,
) -> None:
    """Enqueue a Cloud Task to /internal/jobs/execute/<job_id>."""
```

Task payload (JSON body, always small):
```json
{
  "job_id": "<uuid>",
  "batch_run_id": "<uuid> | null"
}
```

The task URL is `{worker_url}/internal/jobs/execute/{job_id}`.

Cloud Tasks authenticates using the service account with `roles/run.invoker` on juno-worker. The
`oidcToken` method is used so Cloud Run's IAM check passes automatically.

Configuration (from env vars on juno-api):
- `CLOUD_TASKS_QUEUE` — full queue resource name
  `projects/{proj}/locations/{region}/queues/{queue-name}`
- `WORKER_URL` — base URL of juno-worker Cloud Run service
- `WORKER_SERVICE_ACCOUNT` — invoker service account email
- `JOB_TIMEOUT_SECONDS_SINGLE` — default 300
- `JOB_TIMEOUT_SECONDS_BATCH` — default 900

---

### 4.6 `POST /internal/jobs/execute/<job_id>` — worker endpoint

File: `backend/routes/worker.py`

Blueprint: `worker_bp`, registered only when `JUNO_MODE=worker`.

```python
@worker_bp.route("/internal/jobs/execute/<job_id>", methods=["POST"])
def execute_job(job_id: str):
    """
    Internal-only endpoint called by Cloud Tasks.
    Security: verify X-CloudTasks-QueueName header is present and non-empty.
    Returns 200 on success or handled error (Cloud Tasks won't retry on 2xx).
    Returns 500 on unexpected error (Cloud Tasks will retry).
    """
```

Security: Check that `request.headers.get("X-CloudTasks-QueueName")` is present. Cloud Tasks
always sets this header; direct callers cannot spoof it because the endpoint is only reachable
within the VPC (internal-only Cloud Run service). No Firebase token auth — Cloud Tasks OIDC token
is validated by Cloud Run IAM, not application code.

Worker steps:
1. Fetch job doc from Firestore by `job_id`.
2. Verify `uid` ownership is present (doc must exist; if not, log and return 200 — idempotent).
3. If `status` is already `completed` or `error`, return 200 (idempotent retry guard).
4. Write `status=processing`, `started_at=now`, `stage=1` to Firestore.
5. Set internal deadline: `deadline = time.monotonic() + (timeout_seconds - 30)` where
   `timeout_seconds` comes from the Cloud Tasks `X-CloudTasks-TaskETA` header or falls back to
   the shorter single-job timeout (4.5 min). If the internal deadline is exceeded at any stage
   transition, write `status=error, error_data=<timeout error shape>` and return 200.
6. Run `_resolve_input_from_job_doc(job_doc)` — reconstruct text from `input_text` or fetch from
   GCS using `input_doc_id`.
7. Run the pipeline stages (reuse the existing per-step functions from `care_plan.py`), writing
   `stage=N` to Firestore before each step. Each `stage` write is a `update()` call, not a `set()`.
8. On success: write `output_data=payload, status=completed, completed_at=now, stage=5` atomically
   using a Firestore `update()` call.
9. On pipeline error: write `status=error, error_data=<SP2 error shape>, completed_at=now`.
10. Return HTTP 200 in all handled cases (success and handled error). Return HTTP 500 only for
    unexpected exceptions (Firestore unavailable, etc.) so Cloud Tasks retries.

Structured log fields stamped on every worker log line:
`job_id`, `batch_run_id` (from job doc), `uid` (from job doc), `stage`.

---

### 4.7 `JUNO_MODE` branching in `app.py`

Current `app.py` registers all blueprints unconditionally via `all_blueprints`. After SP1:

```python
# backend/routes/__init__.py
from routes.care_plan import care_plan_bp
from routes.saved_outputs import saved_outputs_bp
from routes.datasets import datasets_bp
from routes.batch import batch_bp
from routes.grading import grading_bp
from routes.care_plan_jobs import care_plan_jobs_bp
from routes.batch_jobs import batch_jobs_bp
from routes.worker import worker_bp

API_BLUEPRINTS = [
    care_plan_bp,          # POST /care_plan (SSE, deprecated but kept until frontend migrated)
    batch_bp,              # POST /care_plan/batch (SSE, deprecated but kept until frontend migrated)
    care_plan_jobs_bp,     # POST /care_plan/jobs
    batch_jobs_bp,         # POST /care_plan/batch/jobs
    saved_outputs_bp,      # GET/PATCH/DELETE /care_plan/saved
    datasets_bp,           # GET /care_plan/datasets
    grading_bp,            # POST /care_plan/grade
]

WORKER_BLUEPRINTS = [
    worker_bp,             # POST /internal/jobs/execute/<job_id>
]
```

In `app.py`:

```python
import os

JUNO_MODE = os.environ.get("JUNO_MODE", "api")

if JUNO_MODE == "worker":
    blueprints = WORKER_BLUEPRINTS
else:  # "api" or unset
    blueprints = API_BLUEPRINTS

for bp in blueprints:
    app.register_blueprint(bp)
```

**Old SSE endpoints** (`POST /care_plan` and `POST /care_plan/batch`) are kept in `API_BLUEPRINTS`
and marked deprecated in their docstrings. They are removed in a follow-up once the frontend is
fully migrated and no active sessions remain. This avoids a deployment race where the frontend is
still SSE-based while the API has already dropped the endpoint.

---

### 4.8 `cloudbuild.yaml` — split into two Cloud Run services

Current `cloudbuild.yaml` builds one image and implicitly deploys one service. After SP1 it builds
one image and deploys two services.

```yaml
steps:
  # Step 1: Build image
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
      # (other flags: service-account, memory, etc.)

  # Step 4: Deploy juno-worker (scale-to-zero, internal)
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
      # (other flags: service-account, memory, etc.)

images:
  - $_BACKEND_IMAGE
options:
  logging: CLOUD_LOGGING_ONLY
```

Substitution variables needed: `$_BACKEND_IMAGE`, `$_REGION`. These should already exist or be
added to the Cloud Build trigger config (see §8).

---

### 4.9 Firestore helper additions in `firebase.py`

Add to `backend/utils/firebase.py`:

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

The existing `save_care_plan_output()` is **not used by the new job flow** — job docs are created
by `create_job_doc()` at submission time and updated by `complete_job()` at completion. The old
function remains for any code that still calls it (old SSE endpoints during the deprecation window).

---

### 4.10 Frontend: `POST /care_plan/jobs` API client

File: `frontend/src/api/jobs.ts` (new file)

```typescript
export interface CreateJobRequest {
  // For text input
  text?: string;
  // For file input: caller appends to FormData
  // For doc_id input:
  doc_id?: string;
  version?: string;
  grading_enabled?: boolean;
}

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

export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse>;
export async function createBatchJobs(body: CreateBatchJobsRequest): Promise<CreateBatchJobsResponse>;
```

New path constants in `frontend/src/constants.ts`:

```typescript
export const CARE_PLAN_JOBS_PATH = '/care_plan/jobs';
export const CARE_PLAN_BATCH_JOBS_PATH = '/care_plan/batch/jobs';
export const CARE_PLAN_PAGE_ROUTE = '/carePlan';  // base, append /:id
export const carePlanPagePath = (id: string) => `/carePlan/${id}`;
```

---

### 4.11 Frontend: Firestore `onSnapshot` hook

File: `frontend/src/hooks/useJobSnapshot.ts` (new file)

```typescript
import { getFirestore, doc, onSnapshot } from 'firebase/firestore';
import { firebaseApp } from '../api/firebase';

export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

export interface JobDoc {
  status: JobStatus;
  stage: number | null;
  output_data: Record<string, unknown> | null;
  error_data: unknown | null;  // SP2 error shape
  name: string;
  batch_run_id: string | null;
}

export function useJobSnapshot(jobId: string | null): {
  jobDoc: JobDoc | null;
  loading: boolean;
  error: Error | null;
};
```

Implementation: subscribes to `care_plan_outputs/{jobId}` with `onSnapshot`. Fires the callback
on every field change (status, stage, output_data). Unsubscribes on unmount or when `jobId`
changes.

`firebase/firestore` is already available since `firebase` is a project dependency (used for auth).
The Firestore SDK module is not currently imported in the frontend — it must be added (same
`firebase` package, add `getFirestore` import). The Firestore database ID must match
`FIRESTORE_DATABASE_ID` used by the backend; if it is the default `(default)`, no configuration
needed. If it is a named database, add `VITE_FIRESTORE_DATABASE_ID` env var and pass it to
`getFirestore(firebaseApp, import.meta.env.VITE_FIRESTORE_DATABASE_ID)`.

Firestore security rules must allow authenticated users to read their own docs. Expected rule:
```
match /care_plan_outputs/{docId} {
  allow read: if request.auth.uid == resource.data.uid;
}
```
This rule may already exist; see §8.

---

### 4.12 Frontend: `CarePlanPage.tsx` — SSE removal and job flow

The page currently has two SSE paths (single run and batch). Both are replaced with:
`POST job → onSnapshot → render`.

**State changes (what is removed vs what stays):**

Removed state variables:
- `abortRef` (AbortController for SSE) — replaced with a simpler cancel flag
- `steps` / `setSteps` / `resetSteps` — step array driven by SSE step events; now driven by
  `jobDoc.stage` from Firestore
- `batchProgress` / `setBatchProgress` — SSE-driven batch progress object

Kept state variables (unchanged semantics):
- `appState` (`'upload' | 'processing' | 'result'`) — still controls which section renders
- `result` — still the final `CarePlanInternal` displayed
- `error` — still an error string
- `batchOutputs`, `batchGroupIds`, `selectedBatchIndex` — still used in batch result view
- `activeSavedId`, `sidebarRefresh`, `showSplitView` — unchanged
- `inputMode`, `files`, `textInput`, `gradingEnabled`, `dragOver` — unchanged

New state variables:
- `activeJobId: string | null` — the job_id returned by the API; passed to `useJobSnapshot`
- `batchJobIds: string[] | null` — for batch: list of all job_ids

New flow for single run (`handleSubmit`, non-batch path):
1. POST `formData` to `/care_plan/jobs` → receive `{job_id}`.
2. Set `activeJobId = job_id` and `appState = 'processing'`.
3. `useJobSnapshot(activeJobId)` begins listening.
4. When `jobDoc.status === 'processing'` and `jobDoc.stage` changes, update `steps` display:
   map `stage` (int 1–5) to step status — steps < stage are `done`, stage == N is `active`,
   steps > stage are `waiting`.
5. When `jobDoc.status === 'completed'`:
   - `normalizeCarePlanOutput(jobDoc.output_data)` → `setResult(normalized)`.
   - `setActiveSavedId(job_id)` (job_id = output_id = saved_id).
   - `setSidebarRefresh(r => r + 1)`.
   - `setAppState('result')`.
6. When `jobDoc.status === 'error'`:
   - Read `error_data` (SP2 error shape); display `error_data.message` or a fallback string.
   - `setAppState('upload')`.

New flow for batch run:
1. POST JSON body to `/care_plan/batch/jobs` → receive `{batch_run_id, job_ids}`.
2. Set `batchJobIds = job_ids`, `appState = 'processing'`.
3. Subscribe to all job docs simultaneously using `useJobSnapshot` instances (or a multi-doc
   variant). Track per-job status in a local map.
4. Update progress display: show total completed/failed/pending counts, no per-step SSE.
5. When all `job_ids` have reached `completed` or `error`:
   - Load each completed doc's `output_data` from Firestore (already in snapshot).
   - Build `batchOutputs`, `batchGroupIds` from the docs.
   - `setResult(batchOutputs[0])`, `setAppState('result')`.

**Simplified `steps` display during processing (stage-driven):**

The stage integer from Firestore replaces SSE-per-step events:

```typescript
function stepsFromStage(stage: number | null): PipelineStep[] {
  return INITIAL_STEPS.map(step => ({
    ...step,
    status: stage == null ? 'waiting'
           : step.id < stage ? 'done'
           : step.id === stage ? 'active'
           : 'waiting',
  }));
}
```

No `updateStep` callback needed; steps are derived from `jobDoc.stage` on every snapshot.

---

### 4.13 Frontend: Sidebar — in-progress items

`SavedOutputMeta` in `frontend/src/api/savedOutputs.ts` gains a `status` field:

```typescript
export interface SavedOutputMeta {
  id: string;
  name: string;
  source_filename: string;
  created_at: string;
  updated_at: string;
  batch_group_id: string | null;
  status?: 'not_started' | 'processing' | 'completed' | 'error' | undefined;
  // undefined = old doc without status field, treated as completed
}
```

The REST `GET /care_plan/saved` endpoint (existing `saved_outputs.py`) must include `status` in
its list response. This is a one-line addition: `"status": doc.get("status", "completed")` in the
serialization of each item.

Sidebar rendering changes in `Sidebar.tsx`:

```typescript
function isInProgress(output: SavedOutputMeta): boolean {
  return output.status === 'not_started' || output.status === 'processing';
}
```

For in-progress items:
- Replace the `⋯` three-dot menu button with a spinner indicator (CSS animation or a small SVG).
- Do not call `onSelect(output.id)` on click (clicking a processing item does nothing or shows a
  toast "Processing…").
- The three-dot menu (`menuOpenId`, rename/delete dropdown) is hidden (`!isInProgress(output)`
  guard around the button).

The Sidebar does **not** need a real-time Firestore listener for status updates. The sidebar list
is refetched when `refreshTrigger` increments (which happens when a job completes and
`CarePlanPage` sets the result). This is sufficient: in-progress items appear with spinners after
submission, and change to normal items after the job completes and the user's result is shown.
Users don't need live sidebar updates for background items — they are watching the main processing
area. If a user navigates away and back, the sidebar will re-fetch on mount and any completed items
will display correctly.

---

### 4.14 Frontend: `/carePlan/:id` route and deep-link page

`frontend/src/App.tsx` gains one new route:

```tsx
<Route path="/carePlan/:id" element={<CarePlanJobPage />} />
```

This route is placed outside `AuthLayout` (same as `CarePlanPage` today) so it manages its own
`NavBar`. Authentication is still required; `AuthContext` guards the render.

`frontend/src/pages/care-plan/CarePlanJobPage.tsx` (new file):

- Reads `id` from `useParams()`.
- Calls `useJobSnapshot(id)`.
- If `status === 'completed'`: renders `CarePlanView` with `output_data`.
- If `status === 'processing'` or `'not_started'`: renders the processing/steps view (same
  `stepsFromStage` logic).
- If `status === 'error'`: renders error state with `error_data.message`.
- On load (before snapshot arrives): renders a loading skeleton.
- Ownership check: if the Firestore security rule correctly requires `request.auth.uid ==
  resource.data.uid`, an unauthorized access will result in a Firestore permission error — catch it
  and show a 403-style message.

`CarePlanPage` (the `/` route) now navigates to `/carePlan/:id` after a job is created:

```typescript
// After POST /care_plan/jobs returns job_id:
navigate(carePlanPagePath(job_id));
```

This means the main processing experience now lives at `/carePlan/<uuid>`, which supports
refreshing the page, sharing the URL (once completed), and bookmarking.

---

### 4.15 Timeout enforcement

**Cloud Tasks deadline**: set `dispatchDeadline` on the task:
- Single job: 300 seconds (5 min)
- Batch item: 900 seconds (15 min)

**Worker internal deadline**: before starting the pipeline, record the start time. After each
stage write (§4.6 step 7), check if the elapsed time + estimated remaining time exceeds the
budget. A simpler implementation: check `time.monotonic() > deadline` before each stage. If
exceeded, call `fail_job(job_id, timeout_error_data)` and return 200.

```python
SINGLE_JOB_INTERNAL_DEADLINE_S = 270  # 4.5 min (30 s buffer before Cloud Tasks kills)
BATCH_ITEM_INTERNAL_DEADLINE_S = 870  # 14.5 min

def _is_batch_item(job_doc: dict) -> bool:
    return job_doc.get("batch_group_id") is not None

# In execute_job:
deadline_s = BATCH_ITEM_INTERNAL_DEADLINE_S if _is_batch_item(job_doc) else SINGLE_JOB_INTERNAL_DEADLINE_S
start = time.monotonic()

# Before each pipeline stage:
if time.monotonic() - start > deadline_s:
    fail_job(job_id, build_timeout_error())
    return '', 200
```

`build_timeout_error()` returns an `error_data` dict in SP2's error shape. The exact shape is
defined by SP2; SP1 produces `{"code": "JOB_TIMEOUT", "message": "Job timed out"}` as a
placeholder — SP2 replaces this with the canonical error shape.

---

## 5. API Change Summary

### New endpoints (juno-api service)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/care_plan/jobs` | Firebase token | Create a single async job |
| POST | `/care_plan/batch/jobs` | Firebase token | Create batch of async jobs |

Response shapes:
```
POST /care_plan/jobs → 202 {"job_id": "<uuid>"}
POST /care_plan/batch/jobs → 202 {"batch_run_id": "<uuid>", "job_ids": ["<uuid>", ...]}
```

### New endpoint (juno-worker service, internal-only)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/internal/jobs/execute/<job_id>` | Cloud Tasks OIDC | Execute a single job |

This endpoint is not reachable from the public internet (`--ingress=internal`). The only caller
is Cloud Tasks.

### Deprecated endpoints (kept during migration window)

| Method | Path | Status |
|---|---|---|
| POST | `/care_plan` | Deprecated — SSE, remove after frontend fully migrated |
| POST | `/care_plan/batch` | Deprecated — SSE, remove after frontend fully migrated |

### Unchanged endpoints

| Method | Path |
|---|---|
| GET | `/care_plan/saved` |
| GET | `/care_plan/saved/<id>` |
| PATCH | `/care_plan/saved/<id>` |
| DELETE | `/care_plan/saved/<id>` |
| POST | `/care_plan/grade` |
| GET | `/care_plan/datasets` |
| GET | `/health` |

`GET /care_plan/saved` response gains `status` field per item (§4.13). No breaking change —
new field, existing clients ignore it.

### Firestore client access from frontend

Frontend reads `care_plan_outputs/{job_id}` directly via Firestore SDK (onSnapshot). Backend
writes the same collection. This is a new direct frontend-Firestore path; previously the frontend
only accessed Firestore for auth, not data reads.

---

## 6. Frontend Change Summary

### Files modified

**`frontend/src/App.tsx`**
- Add `<Route path="/carePlan/:id" element={<CarePlanJobPage />} />`.

**`frontend/src/pages/care-plan/CarePlanPage.tsx`**
- Remove all SSE connection logic (the `authenticatedFetch` + `ReadableStream` reader loops for
  both single and batch paths, ~150 lines).
- Remove `abortRef` (AbortController).
- Add `activeJobId` state.
- Add `navigate(carePlanPagePath(job_id))` after job creation.
- `handleSubmit` now does: POST to `/care_plan/jobs` (or `/care_plan/batch/jobs`), set state,
  navigate. Processing display moves to `CarePlanJobPage`.

In practice, the single-run experience moves almost entirely to `CarePlanJobPage`. `CarePlanPage`
becomes the upload/submission page only; after POST it navigates away. This is a significant
simplification of `CarePlanPage`.

**`frontend/src/components/Sidebar/Sidebar.tsx`**
- Add `isInProgress` check in `renderRow`.
- Replace three-dot menu button with spinner for in-progress items.
- Block `onSelect` click for in-progress items.

**`frontend/src/api/savedOutputs.ts`**
- Add `status?` field to `SavedOutputMeta`.

**`frontend/src/constants.ts`**
- Add `CARE_PLAN_JOBS_PATH`, `CARE_PLAN_BATCH_JOBS_PATH`, `CARE_PLAN_PAGE_ROUTE`,
  `carePlanPagePath`.

### New files

**`frontend/src/api/jobs.ts`** — `createCarePlanJob`, `createBatchJobs`.

**`frontend/src/hooks/useJobSnapshot.ts`** — Firestore `onSnapshot` hook, returns `{jobDoc, loading, error}`.

**`frontend/src/pages/care-plan/CarePlanJobPage.tsx`** — `/carePlan/:id` page: loading →
processing (with stage-driven steps) → result or error view.

### What stays the same in CarePlanPage

- Upload form (file/text/doc_id), drag-drop, error display.
- `PresetDataCard`, `ConfigurationCard` components.
- `gradingEnabled` state and `handleFiles`.
- Batch output selection UI (the output selector pill buttons) — this moves to `CarePlanJobPage`
  for the new flow, but the component itself is shared.
- `handleSelectSaved` — sidebar click still loads a saved output by REST GET.
- `handleReset`, `handleDownloadJson`, `handleDownloadPdf`.
- `SplitView` integration.

---

## 7. Testing

### Backend unit tests

**`tests/routes/test_care_plan_jobs.py`** (new)
- `POST /care_plan/jobs` with text input → 202, returns `{job_id}`, Firestore doc written with
  `status=not_started`, Cloud Task enqueued (mock `cloud_tasks.enqueue_job`).
- `POST /care_plan/jobs` with unsupported file type → 400, no Firestore doc written, no Cloud
  Task enqueued.
- `POST /care_plan/jobs` unauthenticated → 401.

**`tests/routes/test_batch_jobs.py`** (new)
- `POST /care_plan/batch/jobs` with valid selections → 202, returns `{batch_run_id, job_ids}`,
  one Firestore doc per item, same `batch_run_id` on all docs.
- `POST /care_plan/batch/jobs` with unknown dataset group → 400.
- All job docs share `batch_run_id`; `batch_group_id` is per-group (existing logic).

**`tests/routes/test_worker.py`** (new)
- `POST /internal/jobs/execute/<id>` without `X-CloudTasks-QueueName` header → 403.
- Happy path: mock Firestore + mock pipeline → job transitions `not_started → processing →
  completed`, `output_data` written.
- Pipeline error: mock pipeline raises → job transitions to `error`, `error_data` written.
- Idempotent: call with already-`completed` job → returns 200, no writes.
- Timeout: mock pipeline that takes too long → `fail_job` called with timeout error.

**`tests/utils/test_cloud_tasks.py`** (new)
- `enqueue_job` calls Cloud Tasks client with correct URL, payload, deadline, OIDC token config
  (mock `google.cloud.tasks_v2.CloudTasksClient`).

### Backend integration tests

**`tests/care_plan/test_pipeline_happy_path.py`** (existing, extend)
- Add a test that runs `_resolve_input_from_job_doc` with a mock job doc and confirms it returns
  the correct text.

### Frontend tests

**`src/tests/hooks/useJobSnapshot.test.ts`** (new)
- Mock Firestore `onSnapshot`. Verify hook returns `loading=true` initially, then `jobDoc` on
  snapshot callback, then unsubscribes on unmount.

**`src/tests/pages/CarePlanJobPage.test.tsx`** (new)
- Snapshot/render test: with `status=processing, stage=3` → correct steps shown (1,2 done; 3
  active; 4,5 waiting).
- With `status=completed` → `CarePlanView` rendered.
- With `status=error` → error message shown.

**`src/tests/routes/test_batch_route.ts`** (existing, update)
- Update to reflect that `POST /care_plan/batch` is deprecated; new tests target
  `POST /care_plan/batch/jobs`.

### Manual smoke tests (see also §8)

- Submit a single file, confirm job doc appears in Firestore console with `status=processing`,
  then `status=completed` with `output_data`.
- Navigate to `/carePlan/<job_id>` in a new tab while job is processing; confirm it shows the
  processing view, then transitions to result automatically.
- Submit batch of 4 items; confirm 4 Firestore docs created, all with same `batch_run_id`,
  worker processes them in parallel (check Cloud Run instance count in console).
- Kill/restart juno-worker mid-job (Cloud Run instance forced restart); confirm Cloud Tasks
  retries and job eventually completes or errors.
- Wait 5 min 30 sec after submitting a job without completing it; confirm `status=error` and
  timeout `error_data` in Firestore.

---

## 8. Manual Intervention Required From You

1. **Create a Cloud Tasks queue** in the GCP console or via Terraform before deploying:
   `gcloud tasks queues create care-plan-jobs --location=$REGION`. Set max-concurrent-dispatches
   to 3 (matches max-instances on juno-worker) so the queue doesn't dispatch faster than the
   worker can accept.

2. **Create a service account** for Cloud Tasks → worker invocation:
   `juno-worker-invoker@$PROJECT.iam.gserviceaccount.com` with `roles/run.invoker` on the
   `juno-worker` Cloud Run service. This account must be set as the `WORKER_SERVICE_ACCOUNT` env
   var on juno-api.

3. **Add env vars** to Cloud Run services:
   - juno-api: `CLOUD_TASKS_QUEUE`, `WORKER_URL`, `WORKER_SERVICE_ACCOUNT`,
     `JOB_TIMEOUT_SECONDS_SINGLE=300`, `JOB_TIMEOUT_SECONDS_BATCH=900`.
   - juno-worker: `JUNO_MODE=worker` (set in cloudbuild.yaml).

4. **Add substitution variables** to the Cloud Build trigger: `_REGION` if not already present.

5. **Verify Firestore security rules** allow authenticated users to read their own
   `care_plan_outputs` docs. Expected rule:
   ```
   match /care_plan_outputs/{docId} {
     allow read: if request.auth != null && request.auth.uid == resource.data.uid;
     allow write: if false;  // backend only, via Admin SDK
   }
   ```
   If rules are not deployed or are more permissive, update them.

6. **Add `firebase/firestore` SDK usage** to the frontend. The current `firebase` package is used
   only for auth (`firebase/auth`). The Firestore module (`firebase/firestore`) needs to be
   imported. The same `firebase` npm package already installed covers this — no new `npm install`
   needed. Verify no bundle-size budget breaks this addition.

7. **Confirm the Firestore database ID** used by the backend (`FIRESTORE_DATABASE_ID` env var on
   Cloud Run). If it is not `(default)`, set `VITE_FIRESTORE_DATABASE_ID` in the frontend env and
   wire it to `getFirestore(firebaseApp, id)`.

8. **`google-cloud-tasks` Python package**: add `google-cloud-tasks` to
   `backend/requirements.txt`. It is not currently a dependency.

---

## 9. Open Questions & Decisions

1. **SP2 error shape for `error_data` field.**
   `[OPEN]` SP2 defines the canonical error shape (`ApiResponse`, `ErrorCode` enum). SP1 writes
   `error_data` into Firestore job docs when jobs fail. The `error_data` value must conform to
   SP2's shape. Until SP2 ships, SP1 uses `{"code": "PIPELINE_ERROR", "message": "<str>"}` as a
   placeholder dict. When SP2 lands (before SP1 if it is Phase 1), replace the placeholder with
   the real SP2 error constructor. This is the one hard dependency on SP2.

2. **Firestore read cost for onSnapshot.**
   `[RESOLVED: Owner approves direct Firestore reads from frontend via onSnapshot.]` The current
   design uses direct reads for the job progress path and REST for list/load. Approximately 6
   Firestore reads per job (1 initial + 1 per stage write + 1 on completion) — negligible cost.

3. **Name derivation timing.**
   `[RESOLVED: defer]` The output `name` (e.g. "Annual Checkup") is derived from `reason_for_visit`
   inside `output_data`, which is only available at job completion. At job creation, the job doc
   uses `"Processing…"` as the name. On completion, the worker calls `complete_job()` which
   includes the derived name. The sidebar shows "Processing…" while the job runs and the real name
   after completion.

4. **Batch multi-doc snapshot strategy.**
   `[RESOLVED: N separate onSnapshot listeners, one per job_id. No composite Firestore index
   needed.]` Each batch item gets its own `useJobSnapshot` hook instance. Simpler implementation;
   no Firestore index deployment required.

5. **Deprecation window for SSE endpoints.**
   `[OPEN]` The old `POST /care_plan` and `POST /care_plan/batch` SSE endpoints are kept during
   the migration window. When is it safe to remove them? Proposed: remove in SP3 (one sub-project
   after SP1) once the new frontend is confirmed working in production. `[DEFERRED to SP3]`

6. **Cloud Tasks retry policy.**
   `[OPEN]` The worker returns HTTP 200 for all handled outcomes (success and error) and HTTP 500
   only for unexpected failures. Cloud Tasks will retry 500s. If the job doc is already in
   `completed` or `error` state at the start of a retry, the worker's idempotency guard returns
   200 immediately. The default retry policy (up to 5 retries with exponential backoff) should be
   sufficient. `[RESOLVED: use Cloud Tasks defaults]` unless owner wants to configure a DLQ.

7. **batch_run_id in structured logs.**
   `[RESOLVED]` `batch_run_id` is written to every Firestore job doc (including single jobs where
   it is `None`) and stamped on all worker structured log entries for that job. This is the
   correlated-observability requirement from the locked decisions. SP4 (observability) can use
   `batch_run_id` as a log filter dimension.

8. **`CarePlanPage` vs `CarePlanJobPage` split.**
   `[RESOLVED]` After job creation, `CarePlanPage` navigates to `/carePlan/:id`. The processing
   and result experiences live in `CarePlanJobPage`. `CarePlanPage` (at `/`) becomes submission
   only. The sidebar's `handleSelectSaved` still goes through `CarePlanPage`'s `handleSelectSaved`
   which loads via REST — this may want to navigate to `/carePlan/:id` instead. For simplicity,
   in SP1 `handleSelectSaved` can navigate to `/carePlan/:id` directly (since the same
   `CarePlanJobPage` handles completed docs). `[DECISION: route sidebar clicks to /carePlan/:id
   in SP1, simplifying CarePlanPage further — pending owner confirmation]`

9. **Frontend Firestore database initialization.**
   `[OPEN]` The `getFirestore(firebaseApp)` call must happen before any `onSnapshot` calls. Best
   location: initialize once in `frontend/src/api/firebase.ts` and export the `db` instance
   alongside `firebaseAuth`. `[RESOLVED: add export const firebaseDb = getFirestore(firebaseApp)
   to firebase.ts, or with named database id if VITE_FIRESTORE_DATABASE_ID is set]`
