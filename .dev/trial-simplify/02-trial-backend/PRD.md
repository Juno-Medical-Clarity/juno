# PRD: SP2 — Trial Backend Route, Rate Limiting & Retention

**Sub-project:** SP2
**Branch context:** users/tejitpabari/trial-app
**Date:** 2026-09-04
**Status:** Draft
**Dependencies:** None (SP3 depends on this PRD's §5 API contract)

---

## 1. Problem

Juno's only existing job-creation path — `POST /care_plan/jobs`
(`backend/routes/care_plan_jobs.py:97-152`) — already works for anonymous callers with
zero changes (D1, verified: `verify_firebase_token` only calls
`auth.verify_id_token(token)` and extracts `uid`; no email/domain check exists anywhere
in the auth layer). But it has three properties that are fine for logged-in users and
wrong for a public, no-login trial:

1. **No rate limiting.** Any caller with a valid Firebase ID token (anonymous or not) can
   create unlimited jobs. A trial route reachable by anyone on the internet needs a hard
   per-IP cap (D11: 5/hour) that does **not** also throttle real app traffic — the two
   must be enforced independently, which is why brainstorm.md's architecture calls for a
   **separate route** rather than adding a limiter to the shared one.
2. **No retention boundary.** Input PDFs uploaded to GCS (`upload_combined_pdf`,
   `care_plan_input.py:21-33`) and Firestore job docs (`care_plan_outputs/{job_id}`) are
   written and then kept forever — correct for users who own and expect to revisit their
   data, incompatible with the trial's "no data is saved" promise (brainstorm §5).
3. **File-count and pipeline-option surfaces sized for logged-in power users.** The main
   app's `MAX_FILE_COUNT = 10` and client-settable `grading_enabled`/`version` fields
   (`models/batch_requests.py:84-93`) are more surface than the trial's product scope
   wants (5 files, grading always on, no version choice) — and none of it should be
   achieved by mutating the shared constants or request model the main app depends on.

SP2 adds a thin, additive `/trial` route family that delegates to the exact same
input-resolution and job-creation helpers as the main app (so it inherits SP1's image
support and any future pipeline change for free), reusing the existing
`care_plan_outputs` collection with two new fields (`is_trial`, `expires_at`) rather than
forking a parallel data model, and adds a Firestore-backed per-IP counter that survives
Cloud Run's autoscaling (an in-memory counter would not: each instance would have its own
count, silently multiplying the effective limit by the instance count).

---

## 2. Goals

1. `POST /trial/jobs` — creates a job in `care_plan_outputs`, marked `is_trial: true`,
   accepting only `text` or up to 5 `files` (no `doc_id`), with `grading_enabled` and
   `version` pinned server-side (not client-settable).
2. Per-IP rate limit, 5 requests/hour, enforced via a Firestore-backed atomic counter
   that is correct under Cloud Run's multi-instance autoscaling.
3. Three-layer retention, all scoped to `is_trial` docs only, with zero behavior change
   for main-app (non-trial) jobs:
   a. Worker deletes the GCS input PDF immediately after the job reaches a terminal
      state (completed or failed).
   b. `DELETE /trial/jobs/<job_id>` lets the frontend trigger cleanup once the result has
      rendered; verifies ownership (`uid`) and `is_trial` before deleting anything.
   c. `expires_at` written on every trial job doc (and every rate-limit counter doc) as
      the field SP5's Firestore TTL policy will key off — SP2 writes the field, SP5 wires
      the policy.
4. A 5-file cap for trial uploads that does not touch `Constants.Uploads.MAX_FILE_COUNT`
   (10, main app) or `resolve_uploaded_files`'s signature.
5. An exhaustive, stable API contract (§5) SP3 can build against without needing to read
   backend code.
6. Recommendations (not implementations) for queue and instance isolation so a trial
   traffic spike cannot degrade real-job dispatch or run away on cost — flagged for SP4's
   deploy-side work where they don't belong to this backend PRD's file changes.

---

## 3. Non-Goals

- **No auth changes anywhere** (D1 locked — anonymous Firebase Auth already works
  end-to-end with zero backend or rules changes; do not re-litigate).
- **No `frontend-trial/` implementation** — that's SP3, which codes directly against §5.
- **No Hosting split, CI deploy job, or Privacy/Terms pages** — SP4.
- **No Firestore TTL policy enablement and no anonymous-Auth-user cleanup cron** — SP5
  (stretch). SP2's job is only to write the `expires_at` field SP5's policy will consume;
  enabling the actual TTL policy (`gcloud firestore fields ttls update`) is out of scope
  here.
- **No image-extraction implementation** — SP1 owns `extract_text_from_bytes`'s image
  branch and the widened `ALLOWED_EXTENSIONS`. SP2 reuses `resolve_uploaded_files`
  unchanged, so the trial inherits image support automatically and order-independently
  regardless of whether SP1 lands before, after, or alongside this work.
- **No changes to `resolve_uploaded_files`, `Constants.Uploads.MAX_FILE_COUNT`,
  `Constants.Uploads.ALLOWED_EXTENSIONS`, or any code path `POST /care_plan/jobs` uses.**
  The trial's 5-file cap and locked `grading_enabled`/`version` are enforced entirely in
  the new trial route, never by touching shared constants or the shared request model.
- **`GET /trial/jobs/<job_id>` does not exist** — see §5 for the justification; the
  brainstorm's route sketch listed it, this PRD drops it.
- **Not fixing the pre-existing orphan-Firestore-doc bug** in `POST /care_plan/jobs`
  (Firestore doc is created before Cloud Tasks env vars are validated, so a
  misconfiguration leaves an unprocessable doc behind). The **new** trial route validates
  Cloud Tasks config before writing anything (§4.1), so it never has this bug itself, but
  fixing the existing main-app route is a separate, out-of-scope follow-up (§9 Q9).
- **No CORS origin changes.** The trial serves from `juno-medical-clarity.web.app`,
  already in `app.py`'s allow-list. Adding `juno-app-99.web.app` (where the main app
  relocates to per D2) is SP4's job when it does the Hosting split — flagged here as a
  cross-cutting dependency, not implemented in this PRD.
- **No Cloud Run `--max-instances` flag change.** Recommended (§4.9, §9 Q7) as a
  deploy-side action for SP4/ops, not a file this PRD's implementer touches.

---

## 4. Architecture Decisions

### 4.1 New blueprint: `backend/routes/trial.py`

Mirrors `care_plan_jobs.py`'s shape exactly (own `_resolve_trial_input` helper, same
try/except/Markers wrapping), but forked to drop `doc_id` support and pin
`grading_enabled`/`version` server-side, and reordered so Cloud Tasks config is validated
**before** the Firestore doc is written (fixing the orphan-doc failure mode for this new
route only — see §9 Q9 for why the existing route isn't touched).

```python
"""backend/routes/trial.py — POST /trial/jobs, DELETE /trial/jobs/<job_id>.

Thin, additive trial surface. Delegates to the same input-resolution and
job-creation helpers as care_plan_jobs.py (resolve_uploaded_files,
upload_combined_pdf, JobDoc, create_job_doc, enqueue_job_safe) — forks nothing
from the pipeline itself. Rate-limited and retention-scoped; auth is unchanged
(verify_firebase_token, same as every other route).
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request

from models.job import JobDoc
from utils.firebase import create_job_doc, verify_firebase_token, firestore_client
from utils.cloud_tasks import enqueue_job_safe, require_env, MissingJobConfigError
from utils.rate_limit import rate_limit_trial
from utils.gcs import delete_gcs_object
from utils.constants import Constants
from services.care_plan_input import resolve_uploaded_files, upload_combined_pdf
from utils.markers.markers import Markers
from utils.markers.marker import Scope
from errors import make_error_response, ErrorCode

logger = logging.getLogger(__name__)
trial_bp = Blueprint("trial", __name__)


def _resolve_trial_input(user_id: str) -> dict:
    """Trial-scoped fork of care_plan_jobs._resolve_input_for_job: text or
    <=5 files only (no doc_id — trial has no login, so no prior upload to
    reference). grading_enabled/version are pinned, never client-settable."""
    json_data = request.get_json(silent=True) or {}
    text_input = (request.form.get("text") or json_data.get("text") or "").strip()
    if text_input:
        return {
            "input_source_kind": "text",
            "input_text": text_input,
            "input_doc_id": None,
            "input_source_filename": "text_input",
            "input_pdf_gcs_uri": None,
            "input_version": Constants.Pipeline.PIPELINE_VERSION_V1_2,
            "grading_enabled": True,
        }

    uploads = request.files.getlist("files")
    if not uploads:
        raise ValueError("Request must include 'files' or 'text'")
    if len(uploads) > Constants.Trial.MAX_FILE_COUNT:
        raise ValueError(f"Trial supports at most {Constants.Trial.MAX_FILE_COUNT} files")

    # Unchanged: still enforces MAX_FILE_BYTES / MAX_AGGREGATE_FILE_BYTES /
    # ALLOWED_EXTENSIONS exactly as the main app does (main-app behavior untouched).
    resolved, raw_pdf_bytes = resolve_uploaded_files(uploads)
    pdf_gcs_uri = upload_combined_pdf(raw_pdf_bytes, user_id) if raw_pdf_bytes else None
    return {
        "input_source_kind": "upload",
        "input_text": resolved.text,
        "input_doc_id": None,
        "input_source_filename": resolved.source_filename,
        "input_pdf_gcs_uri": pdf_gcs_uri,
        "input_version": Constants.Pipeline.PIPELINE_VERSION_V1_2,
        "grading_enabled": True,
    }


@trial_bp.route("/trial/jobs", methods=["POST"])
@rate_limit_trial          # outermost: runs before auth, keyed on IP only (§4.4)
@verify_firebase_token
def create_trial_job(user_id: str):
    def _handler(scope: Scope):
        try:
            try:
                input_fields = _resolve_trial_input(user_id)
            except (ValueError, FileNotFoundError) as exc:
                return make_error_response(
                    ErrorCode.INPUT_VALIDATION_ERROR, request.path,
                    {"field": "input", "reason": str(exc)},
                ).to_dict(), 400

            # Validate Cloud Tasks config BEFORE writing anything to Firestore —
            # unlike POST /care_plan/jobs, this route never orphans a doc (§9 Q9).
            try:
                queue_name = require_env("CLOUD_TASKS_QUEUE_TRIAL")
                worker_url = require_env("WORKER_URL")
                service_account = require_env("WORKER_SERVICE_ACCOUNT")
            except MissingJobConfigError:
                logger.exception("trial: missing Cloud Tasks config; refusing job")
                return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            job_doc = JobDoc.for_single(
                user_id=user_id, now=now, trace_id=None, input_fields=input_fields,
                is_trial=True,
                expires_at=now + timedelta(hours=Constants.Trial.JOB_TTL_HOURS),
            )
            create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc.to_firestore())

            if err := enqueue_job_safe(
                job_id, queue_name=queue_name, worker_url=worker_url,
                service_account=service_account,
                deadline_seconds=Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE,
                path=request.path,
            ):
                return err

            return jsonify({"job_id": job_id}), 202
        except Exception:
            logger.exception("create_trial_job: unexpected error")
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

    return Markers.Trial.CreateJob.execute(_handler)


@trial_bp.route("/trial/jobs/<job_id>", methods=["DELETE"])
@verify_firebase_token      # NOT rate-limited — see §9 Q2
def delete_trial_job(job_id: str, user_id: str):
    def _handler(scope: Scope):
        try:
            db = firestore_client()
            ref = db.collection("care_plan_outputs").document(job_id)
            doc = ref.get()
            if not doc.exists:
                return make_error_response(
                    ErrorCode.RESOURCE_NOT_FOUND, request.path,
                    {"collection": "care_plan_outputs", "doc_id": job_id},
                ).to_dict(), 404

            data = doc.to_dict()
            # Both checks required: ownership AND is_trial. A trial-scoped delete
            # must never be usable to delete a main-app (non-trial) doc, even if
            # uid happens to match.
            if data.get("uid") != user_id or not data.get("is_trial"):
                return make_error_response(
                    ErrorCode.RESOURCE_FORBIDDEN, request.path,
                    {"collection": "care_plan_outputs", "doc_id": job_id},
                ).to_dict(), 403

            gcs_uri = data.get("input_pdf_gcs_uri")
            if gcs_uri:
                delete_gcs_object(gcs_uri)  # best-effort; logs+swallows, never raises

            ref.delete()
            return "", 204
        except Exception:
            logger.exception("delete_trial_job: unexpected error for job_id=%s", job_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

    return Markers.Trial.DeleteJob.execute(_handler)
```

**GCS upload prefix — trial uploads get a distinct prefix (added 2026-09-05, resolves SP5
§9 Q3):** `upload_combined_pdf` (`services/care_plan_input.py`) is shared with the main
app's `POST /care_plan/jobs` route (the same helper this section's docstring already
calls out). It originally wrote every caller's PDF to a single
`care_plan/{user_id}/inputs/{object_id}.pdf` prefix — SP5's design pass
(`05-retention-automation/PRD.md` §4.10) found this makes trial and main-app uploads
indistinguishable by path, which blocks a safe GCS lifecycle-rule backstop (a lifecycle
rule can only match by prefix/suffix/age, nothing collection- or field-aware). Per SP5 §9
Q3 (approved by the user, 2026-09-05: "give a distinct prefix if you can, if cheap"),
`upload_combined_pdf` gains an `is_trial` keyword and routes trial uploads to
`care_plan_trial/{user_id}/inputs/{object_id}.pdf` instead:

```python
def upload_combined_pdf(pdf_bytes: bytes, user_id: str, *, is_trial: bool = False) -> str:
    """Upload combined input PDF bytes and return a gs:// URI. is_trial routes to a
    visually distinct prefix (care_plan_trial/) so a GCS lifecycle rule can safely
    target only trial uploads — see 05-retention-automation/PRD.md §4.10/§9 Q3."""
    bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
    if not bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    object_id = str(uuid.uuid4())
    prefix = "care_plan_trial" if is_trial else "care_plan"
    blob_name = f"{prefix}/{user_id}/inputs/{object_id}.pdf"

    bucket = get_gcs_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return f"gs://{bucket_name}/{blob_name}"
```

`is_trial` defaults to `False`, so every existing call site in `care_plan_jobs.py` /
`batch_jobs.py` (main-app uploads) is byte-for-byte unaffected and keeps writing to
`care_plan/` — this is purely additive to the shared function. **§4.1's
`_resolve_trial_input` call site above changes to pass the new flag:**

```python
pdf_gcs_uri = upload_combined_pdf(raw_pdf_bytes, user_id, is_trial=True) if raw_pdf_bytes else None
```

(replaces the `upload_combined_pdf(raw_pdf_bytes, user_id)` line in `_resolve_trial_input`
above.)

**Worker-side cleanup still lines up:** `worker.py`'s `finally`-block cleanup (§4.5) calls
`delete_gcs_object(job.input_pdf_gcs_uri)` on whatever URI is stored on the job doc — it
never parses or depends on the prefix itself, only on the full `gs://` URI already written
at upload time. Since `job.input_pdf_gcs_uri` for a trial job now simply *contains*
`care_plan_trial/...` instead of `care_plan/...`, no change is needed to §4.5's or §4.6's
delete logic — both retention layers keep working unmodified against the new path.

### 4.2 Rate limiter: new `backend/utils/rate_limit.py`

**Why Firestore, not in-memory:** Cloud Run autoscales `juno-api` across N instances with
no shared memory. An in-memory counter (dict, `functools.lru_cache`, etc.) would give
each instance its own independent budget — effective limit becomes `5 × instance_count`,
silently defeating D11. Firestore is the only shared, already-provisioned store available
without adding infrastructure (no Redis/Memorystore for a free trial feature).

**Client IP extraction (Cloud Run proxy):** Cloud Run's Google Front End is the only proxy
hop in front of the container in the current deploy topology (no external HTTPS Load
Balancer / Cloud Armor / CDN — confirmed by reading `deploy.yml`, which deploys `juno-api`
directly with no LB config). GFE **appends** the true client IP as the last entry of
`X-Forwarded-For` before forwarding to the container; everything before that is
client-supplied and spoofable. So: take the **last** comma-separated value, never the
first (a naive first-value read is directly attacker-controlled).

**Hashing:** raw IPs are arguably personal data, especially on a health-adjacent public
page. HMAC-SHA256 with a server-side salt (`TRIAL_RATE_LIMIT_SALT` env var — §8), truncated
to 20 hex chars for a compact doc ID. This is not cryptographic protection of a
high-value secret — it just raises the bar above trivially reversible plaintext storage
(§9 Q8 explains why Secret Manager is overkill here).

**Window algorithm:** fixed, hour-aligned UTC window (`now.strftime("%Y%m%d%H")` as part
of the doc ID) rather than a sliding log. Accepts a boundary-burst edge case (a caller
near the top of the hour can get up to ~2× the nominal limit across the boundary) in
exchange for a single-document atomic transaction per check — a sliding window needs a
subcollection of timestamps and materially more reads/writes for no proportionate
abuse-prevention benefit at trial-traffic scale (§9 Q5).

**Atomic increment:** a Firestore transaction (`@firestore.transactional`) — read the
counter doc, and only write `count+1` if `count < limit`; if already at limit, no write
occurs and the caller is rejected. This is what actually prevents the race where two
concurrent requests both read `count=4` and both think they're allowed — Firestore
transactions serialize via optimistic concurrency + automatic retry, so exactly one wins
the "5th slot."

```python
"""backend/utils/rate_limit.py — Firestore-backed per-IP rate limiter for the
trial route. In-memory counters are unreliable across Cloud Run's autoscaled,
non-shared-memory instances (see PRD §4.2); this is deliberately the only
place in the codebase that hashes a client IP."""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import request
from google.cloud import firestore

from utils.firebase import firestore_client
from utils.constants import Constants
from errors import make_error_response, ErrorCode

logger = logging.getLogger(__name__)


def get_client_ip() -> str:
    """Real client IP behind Cloud Run's proxy: the LAST X-Forwarded-For
    value (Google-appended, trustworthy), never the first (client-supplied,
    spoofable). Falls back to request.remote_addr if the header is absent."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.remote_addr or "unknown"


def _hash_ip(ip: str) -> str:
    secret = os.environ.get("TRIAL_RATE_LIMIT_SALT", "")
    if not secret:
        logger.warning("rate_limit: TRIAL_RATE_LIMIT_SALT not set — hashing unsalted")
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:20]


@firestore.transactional
def _check_and_increment(transaction, ref, limit: int, now, expires_at) -> bool:
    snapshot = ref.get(transaction=transaction)
    count = snapshot.get("count") if snapshot.exists else 0
    if count >= limit:
        return False
    transaction.set(ref, {"count": count + 1, "updated_at": now, "expires_at": expires_at}, merge=True)
    return True


def check_rate_limit() -> bool:
    """Returns True if this request is within budget (and has been counted),
    False if the caller's IP is over the hourly limit."""
    ip_hash = _hash_ip(get_client_ip())
    now = datetime.now(timezone.utc)
    window_start = now.replace(minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(hours=1)
    # Counter TTL buffer: always in the future relative to window_end, so the
    # doc survives long enough for SP5's TTL policy to reliably clean it up.
    doc_expires_at = window_end + timedelta(hours=Constants.Trial.RATE_LIMIT_COUNTER_TTL_HOURS)
    doc_id = f"{ip_hash}_{window_start.strftime('%Y%m%d%H')}"

    db = firestore_client()
    ref = db.collection(Constants.Trial.RATE_LIMIT_COLLECTION).document(doc_id)
    transaction = db.transaction()
    return _check_and_increment(transaction, ref, Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR, now, doc_expires_at)


def rate_limit_trial(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == "OPTIONS":     # let flask-cors attach preflight headers
            return "", 204
        try:
            allowed = check_rate_limit()
        except Exception:
            # Fail OPEN: a transient Firestore hiccup should not take down the
            # whole trial for everyone. Availability > strict enforcement here —
            # this is abuse prevention on a free feature, not a security boundary.
            logger.exception("rate_limit_trial: check_rate_limit failed; allowing request")
            allowed = True
        if not allowed:
            return make_error_response(ErrorCode.RATE_LIMIT_EXCEEDED, request.path).to_dict(), 429
        return f(*args, **kwargs)
    return wrapper
```

**Collection:** new `trial_rate_limits` (not `care_plan_outputs` — the "trial jobs live in
`care_plan_outputs`" decision is about job docs specifically; a rate-limit counter is not
a job and introducing it as a new, tiny, single-purpose collection carries none of the
regression risk the rejected `trial_jobs` collection idea had, because nothing else reads
or writes `trial_rate_limits`). **Doc ID:** `{ip_hash}_{YYYYMMDDHH}`. **Cost:** one
transactional read + (at most) one write per `POST /trial/jobs` call — negligible even at
high trial traffic (Firestore's free tier alone covers tens of thousands of these a day).
**Cleanup:** `expires_at` field written on every counter doc; SP5's TTL policy (applied to
this collection too, not just `care_plan_outputs`) deletes them automatically once
enabled — until then they simply accumulate at a rate of at most a few small docs per
distinct IP per hour, which is cheap and bounded.

**Not rate-limited:** `DELETE /trial/jobs/<job_id>` deliberately has no rate limit (§9
Q2) — gating cleanup calls behind the same 5/hour budget a user just spent on
simplifications would block their own retention-guarantee call.

### 4.3 `models/job.py` — `is_trial` / `expires_at` fields (additive)

```python
# new fields on JobDoc (model_config already has extra="ignore")
# ── Trial (SP2) ───────────────────────────────────────────────────────
is_trial: bool = False
expires_at: Optional[datetime] = None
```

`for_single()` gains two new optional kwargs, defaulting to today's behavior so every
existing caller (`care_plan_jobs.py`) is unaffected:

```python
@classmethod
def for_single(
    cls, *, user_id: str, now: datetime, trace_id: Optional[str], input_fields: dict,
    is_trial: bool = False, expires_at: Optional[datetime] = None,
) -> "JobDoc":
    return cls(
        uid=user_id, name=now.strftime("%b %d, %Y %H:%M"),
        source_filename=input_fields["input_source_filename"],
        created_at=now, updated_at=now, status=StatusEnum.not_started,
        shared=False, comment="", trace_id=trace_id,
        is_trial=is_trial, expires_at=expires_at,
        **input_fields,
    )
```

**Critical verification — shared-collection blast radius.** `to_firestore()` is
`self.model_dump(mode="python", exclude_none=False)`, so every main-app job doc
(`is_trial=False, expires_at=None` by default) writes an explicit `expires_at: null`
field to Firestore, not an absent field. This matters because SP5's TTL policy applies
at the **collection-group level**, shared with real user data — a misconfiguration here
would be catastrophic (silently deleting real care plans). Verified against documented
Firestore TTL semantics: **a TTL policy only ever deletes a document where the target
field is present and holds a Timestamp value; a `null` value (or an absent field) is
never eligible and is permanently skipped by the TTL sweep.** So writing `expires_at:
null` on every main-app doc is safe — those docs are simply invisible to TTL forever,
which is exactly the desired "keep indefinitely" behavior for real users. This is called
out again in §9 Q10 as the one true risk in this design, resolved by construction.

### 4.4 Trial file cap without touching main-app constants

New nested class in `backend/utils/constants.py`:

```python
class Trial:
    MAX_FILE_COUNT: int = 5
    RATE_LIMIT_PER_IP_PER_HOUR: int = 5
    RATE_LIMIT_COLLECTION: str = "trial_rate_limits"
    RATE_LIMIT_COUNTER_TTL_HOURS: int = 2
    JOB_TTL_HOURS: int = 1
```

The cap is enforced in `routes/trial.py::_resolve_trial_input` (§4.1) as a check on
`len(uploads)` **before** calling `resolve_uploaded_files(uploads)` — that function's own
`Constants.Uploads.MAX_FILE_COUNT` (10) check is untouched and still runs as a second,
redundant, harmless ceiling. `Constants.Uploads.MAX_FILE_BYTES` (10MB/file) and
`MAX_AGGREGATE_FILE_BYTES` (25MB total) are inherited unchanged — the trial does not
loosen or tighten per-file/aggregate size limits, only file *count*.

### 4.5 Retention layer (a) — worker deletes the GCS input, `is_trial`-gated

**The Show-Original conflict, resolved:** the main app's "Show Original" feature needs
the uploaded PDF to persist in GCS. But tracing `worker.py::execute_job`, for
`source_kind == "upload"` the worker **never reads `input_pdf_gcs_uri` at all** —
`resolve_input_from_job_doc(job)` (`care_plan_input.py:161-165`) just returns
`job.input_text`, which was already extracted and stored in Firestore at job-*creation*
time by the API route. The GCS PDF exists purely as a stored artifact for a
frontend feature (fetching/rendering the original document later) — the pipeline itself
has zero runtime dependency on it. Since the trial's product scope explicitly excludes
"Show Original" (brainstorm §2), deleting the trial's GCS input the moment the job
reaches a terminal state cannot break anything the trial UI does, and doesn't touch the
main app's GCS objects at all (gated on `is_trial`).

**Hook point** — `worker.py::execute_job`'s `finally` block, alongside the existing
`is_gcs_dataset_job` cleanup:

```python
# top of execute_job, alongside gcs_temp_dir/is_gcs_dataset_job:
job: JobDoc | None = None
...
# inside try, where job is first constructed (unchanged):
job = JobDoc.from_firestore(job_doc)
...
finally:
    if is_gcs_dataset_job:
        from utils.gcs import cleanup_dataset_inputs
        cleanup_dataset_inputs(job_id)
    if job is not None and getattr(job, "is_trial", False) and job.input_pdf_gcs_uri:
        from utils.gcs import delete_gcs_object
        delete_gcs_object(job.input_pdf_gcs_uri)
```

Runs on **every** exit path (success, pipeline failure, timeout, exception) because
`finally` always executes — matching the "delete regardless of outcome" zero-retention
requirement. It also re-runs harmlessly on an idempotent Cloud Tasks retry of an
already-terminal job (`job.status in ("completed", "error")` early-return at line 66-68
still reaches this same `finally`), which is fine because deletion is idempotent (§4.6).

New helper in `backend/utils/gcs.py`:

```python
def delete_gcs_object(gcs_uri: str) -> None:
    """Best-effort delete of a gs:// object. Swallows NotFound and logs any
    other failure — GCS cleanup failing must never fail the caller (job
    completion or the DELETE route); the expires_at TTL is the safety net."""
    if not gcs_uri.startswith("gs://"):
        logger.warning("gcs: delete_gcs_object called with non-gs:// uri=%s", gcs_uri)
        return
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_name = rest.partition("/")
    try:
        _gcs_client().bucket(bucket_name).blob(blob_name).delete()
    except Exception as exc:
        from google.api_core.exceptions import NotFound
        if isinstance(exc, NotFound):
            return
        logger.exception("gcs: delete_gcs_object failed for uri=%s", gcs_uri)
```

### 4.6 Retention layer (b) — `DELETE /trial/jobs/<job_id>`

See §4.1 for the full route. Two checks before anything is deleted: `uid` ownership
(same pattern as `get_owned_doc_or_403`, but inlined rather than reusing that helper so
the extra `is_trial` condition doesn't have to be retrofitted onto a function
`care_plan_jobs.py`/`saved_outputs.py` also depend on) and `is_trial == True` — a
trial-scoped delete endpoint must be structurally incapable of deleting a main-app doc
even in a uid-collision scenario. On success: best-effort GCS delete, then
`ref.delete()`, then `204`.

**Mid-flight delete race, verified safe:** if the frontend calls `DELETE` while the
worker is still `processing` (shouldn't happen per the intended "delete after render"
flow, but nothing server-side prevents it), the worker's next Firestore write
(`update_job_stage`/`complete_job`/`fail_job`) raises `FirestoreError` (doc gone), which
propagates to `execute_job`'s outer `except Exception` (worker.py:221-229), which returns
`"", 500`. Cloud Tasks retries the dispatch; the retry's `get_job_doc(job_id)` returns
`None`; the existing idempotent path (worker.py:60-62, `"worker: job doc not found —
skipping"`) returns `200`. Self-healing in one retry, no permanent inconsistency, and
irrelevant to the deleted GCS input either way since the job is being discarded. No
status guard was added given this is already safe.

### 4.7 Retention layer (c) — `expires_at` (SP5 dependency)

Written at job-creation time (`now + timedelta(hours=Constants.Trial.JOB_TTL_HOURS)`,
1 hour — generous relative to the 300s processing deadline, tight enough to be a real
safety net if the browser closes before the `DELETE` call fires) and at rate-limit
counter-creation time (§4.2). SP2's responsibility ends at writing the field correctly
(§4.3 verifies main-app docs are TTL-inert); enabling the actual TTL policy on
`care_plan_outputs.expires_at` and `trial_rate_limits.expires_at` is SP5's stretch-goal
deliverable, tracked there, not here.

### 4.8 New error code: `RATE_LIMIT_EXCEEDED`

`backend/errors/codes.py` has no generic rate-limit code today — only
`ATHENA_RATE_LIMIT_ERROR` and `VERTEX_QUOTA_EXCEEDED`, both provider-specific. Add:

```python
# ErrorCode enum
RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
"""The caller's IP has exceeded the trial's per-hour simplification limit."""
```

```python
# ERROR_CATALOG
ErrorCode.RATE_LIMIT_EXCEEDED: ErrorInfo(
    code="RATE_LIMIT_EXCEEDED",
    http_status=429,
    message="Trial rate limit exceeded",
    user_hint="You've reached the trial's limit of 5 simplifications per hour. Please try again later.",
    retryable=True,
),
```

### 4.9 Cloud Tasks queue isolation

**Recommend: yes, a separate queue**, `care-plan-jobs-trial`, distinct from the main
app's `care-plan-jobs` (name confirmed in `deploy.yml`'s `CLOUD_TASKS_QUEUE` substitution).
Both queues still dispatch to the same `juno-worker` Cloud Run service (no new worker
service — that would add real deploy complexity for isolation the API-layer rate limit
and queue-level throughput caps already achieve reasonably well). The queue split buys
independently *tunable dispatch throughput*: give `care-plan-jobs-trial` a deliberately
low `--max-concurrent-dispatches` / `--max-dispatches-per-second` (e.g. 5 and 2) so even
a full trial flood can only push a handful of concurrent worker executions, while
`care-plan-jobs` keeps its current (effectively unbounded) settings for real traffic.
This is throughput isolation, not instance isolation — see §9 Q7 for the
`--max-instances` layer that bounds total cost across both queues.

New env var the trial route requires: `CLOUD_TASKS_QUEUE_TRIAL` (full queue resource
name, same format as the existing `CLOUD_TASKS_QUEUE`). The queue itself must be created
once (`gcloud tasks queues create care-plan-jobs-trial --location=... --max-concurrent-
dispatches=5 --max-dispatches-per-second=2`) — a deploy-time action, not owner-only (the
existing `GCP_SA_KEY` service account already runs equivalent `gcloud` commands in
`deploy.yml`; §9 Q7 flags the one IAM caveat).

### 4.10 Blueprint registration & markers

`backend/routes/__init__.py`:
```python
from routes.trial import trial_bp
API_BLUEPRINTS = [
    care_plan_jobs_bp, batch_jobs_bp, saved_outputs_bp, datasets_bp,
    clinician_dataset_bp, grading_bp, admin_bp,
    trial_bp,   # NEW
]
```

`backend/utils/markers/markers.py` — new leaf, following the existing `Batch`/`Worker`
pattern:
```python
class Trial:
    @code_marker("trial.create_job")
    class CreateJob(CodeMarker): pass

    @code_marker("trial.delete_job")
    class DeleteJob(CodeMarker): pass
```

### 4.11 Firestore security rules — no change

Verified against the current `firestore.rules`:
```
match /care_plan_outputs/{docId} {
  allow get: if (request.auth != null && request.auth.uid == resource.data.uid) || resource.data.shared == true;
  allow list: if request.auth != null && request.auth.uid == resource.data.uid;
  allow write: if false;
}
```
- **Reads (SP3's `onSnapshot`):** the anon Firebase Auth token's `request.auth.uid` equals
  the `uid` the trial job doc was created with (both are the same anonymous uid the
  frontend signed in as) — the existing `allow get` rule already permits this with zero
  changes. `shared` defaults to `false` on every job doc `for_single` creates (trial or
  not), so trial docs are never exposed via the `shared == true` branch either.
- **Writes (job creation, stage updates, delete):** `allow write: if false` already forces
  every write through the backend's Admin SDK, which bypasses security rules entirely
  regardless of what the rule says. Nothing about adding `is_trial`/`expires_at` fields or
  a new `DELETE /trial/jobs/<id>` route changes this — the route deletes via
  `firestore_client()` (Admin SDK), never via a client-side call the rules would gate.

**Conclusion: `firestore.rules` is unmodified by this PRD.**

### 4.12 `.github/workflows/deploy.yml` — new env vars

`juno-api`'s `API_ENV_VARS` string gains two entries:
- `CLOUD_TASKS_QUEUE_TRIAL=projects/$GCP_PROJECT_ID/locations/$GCP_REGION/queues/care-plan-jobs-trial`
- `TRIAL_RATE_LIMIT_SALT=${{ secrets.TRIAL_RATE_LIMIT_SALT }}` (new GitHub secret — §8)

A new step before "Configure juno-api env vars and secrets" ensures the trial queue
exists (idempotent — tolerates already-exists):
```yaml
- name: Ensure trial Cloud Tasks queue exists
  run: |
    gcloud tasks queues create care-plan-jobs-trial \
      --location "$GCP_REGION" --project "$GCP_PROJECT_ID" \
      --max-concurrent-dispatches=5 --max-dispatches-per-second=2 \
      || echo "queue already exists — continuing"
```
`juno-worker` needs no changes — it already dispatches by `job_id` alone, agnostic of
which queue enqueued the task.

---

## 5. API Change Summary

Two new endpoints. **No `GET /trial/jobs/<job_id>`** — see rationale below. Both require
the same `Authorization: Bearer <firebase-id-token>` header every other route requires;
the trial frontend gets this for free from `signInAnonymously()` (D1), invisibly to the
user.

### `POST /trial/jobs`

Request — multipart/form-data OR JSON, same dual-mode convention as
`POST /care_plan/jobs`:

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string | one of `text`/`files` | Pasted care-plan text. |
| `files` | file[] (multipart only) | one of `text`/`files` | Max **5** files (trial-specific — main app allows 10). Each still capped at 10MB, 25MB aggregate, and the shared `ALLOWED_EXTENSIONS` (pdf/txt/docx/html/htm, plus images once SP1 lands). |

Not accepted (unlike `POST /care_plan/jobs`): `doc_id`, `version`, `grading_enabled` — if
sent, they are silently ignored; the trial always runs `version="v1-2"`,
`grading_enabled=True`.

Success:
```
202 Accepted
{"job_id": "3fae21b0-....-uuid"}
```

Errors (all bodies are the standard `ApiResponse` envelope,
`{"status": "error", "error": {...}, "requestId": "..."}`, matching every other route's
`make_error_response(...).to_dict()` shape):

| Status | `error.code` | Cause |
|---|---|---|
| 400 | `INPUT_VALIDATION_ERROR` | Neither `text` nor `files` present; `files` empty of filenames; >5 files; file too large (per-file or aggregate); disallowed extension; unreadable stored doc — any `ValueError`/`FileNotFoundError` from input resolution. |
| 401 | `MISSING_AUTH_HEADER` | No `Authorization` header. |
| 401 | `MALFORMED_AUTH_HEADER` | Header present but not `Bearer <token>`. |
| 401 | `UNAUTHORIZED` | Token present but invalid/expired. |
| 429 | `RATE_LIMIT_EXCEEDED` | Caller's IP has hit 5 requests in the current UTC hour window. |
| 500 | `INTERNAL_ERROR` | Missing `CLOUD_TASKS_QUEUE_TRIAL`/`WORKER_URL`/`WORKER_SERVICE_ACCOUNT` config, Cloud Tasks enqueue failure, or any unhandled exception. |

### `DELETE /trial/jobs/<job_id>`

No request body. Called by the frontend once the result has rendered (success or
error), to trigger retention layer (b).

Success: `204 No Content`, empty body.

| Status | `error.code` | Cause |
|---|---|---|
| 401 | `MISSING_AUTH_HEADER` / `MALFORMED_AUTH_HEADER` / `UNAUTHORIZED` | Same as above. |
| 403 | `RESOURCE_FORBIDDEN` | `job_id` exists but its `uid` doesn't match the caller, or it exists but `is_trial` is not `true` (never deletable via this route). |
| 404 | `RESOURCE_NOT_FOUND` | `job_id` doesn't exist (already deleted, or never existed). |
| 500 | `INTERNAL_ERROR` | Unhandled exception. |

Idempotency: calling `DELETE` twice returns `204` then `404` — the frontend only needs to
call it once and can safely ignore the response.

### Why no `GET /trial/jobs/<job_id>`

The brainstorm's route sketch (§6) listed a `GET`, but it isn't needed and is dropped:
the trial frontend gets live status **the same way the main app already does** —
subscribing directly to Firestore via `onSnapshot(doc(firebaseDb, 'care_plan_outputs',
jobId), ...)`, exactly like `frontend/src/hooks/useJobSnapshot.ts`. The existing security
rule (`allow get: if request.auth.uid == resource.data.uid`) already permits this for an
anonymous-auth uid with zero rule changes (§4.11). Adding a backend `GET` route would be
pure duplication of a read path Firestore's client SDK already serves for free, with live
updates SSE/polling would have to reinvent. **SP3 must use the Firestore `onSnapshot`
pattern, not poll a `GET` endpoint that doesn't exist.**

---

## 6. Frontend Change Summary

N/A — `frontend-trial/` itself is SP3. Cross-cutting notes SP3 needs from this PRD:

- **Job status/results:** subscribe to `care_plan_outputs/{jobId}` via `onSnapshot`,
  structurally identical to `frontend/src/hooks/useJobSnapshot.ts` (same collection, same
  field names: `status`, `stage`, `output_data`, `error_data`, `name`). No new Firestore
  schema for SP3 to learn.
- **Title:** there is no dedicated title field — use the job doc's `name`
  (server-derived by `derive_output_name()`; already what the main app displays).
- **Score:** `output_data.grading.entries[]`, filter `entry.name == "combined"`, read
  `.grade` for `target == "before"` and `target == "after"` — the composite 0–100 D6
  wants. Both entries are always present (grading is always on for trial jobs).
- **Cleanup call:** fire `DELETE /trial/jobs/<job_id>` once the result (or error) has
  rendered. Fire-and-forget is fine — the frontend doesn't need to block on or surface
  its response; `expires_at` is the safety net if this call never happens (browser
  closed, network drop, etc.).
- **Rate-limit UX:** a `429 RATE_LIMIT_EXCEEDED` on `POST /trial/jobs` should be shown as
  a plain "try again later" message using `error.user_hint` directly — no special client
  logic needed beyond displaying it like any other error code.
- **File cap:** SP3's upload UI should cap at 5 files client-side (product scope already
  says this) so the 400 from exceeding it is a rare/defensive case, not the primary UX.

No main-app frontend files change.

---

## 7. Testing

Mirrors the existing `backend/tests/{routes,services,utils,models}/` layout.

**`backend/tests/routes/test_trial.py`** (new):
- `POST /trial/jobs` — 202 on valid `text`; 202 on valid multipart upload (≤5 files,
  asserting the created job doc payload has `is_trial=True` and a future `expires_at`);
  400 on >5 files; 400 on neither `text` nor `files`; 400 on oversized/disallowed file
  (delegating to `resolve_uploaded_files`'s existing checks — regression guard that the
  trial route didn't accidentally loosen them); 401 variants (missing/malformed/invalid
  token — same as `test_care_plan_jobs.py`'s existing auth tests, forked); 429 after the
  6th call within a mocked/monkeypatched rate-limit window; 500 when
  `CLOUD_TASKS_QUEUE_TRIAL`/`WORKER_URL`/`WORKER_SERVICE_ACCOUNT` are unset — and assert
  **no Firestore doc was created** in that case (regression guard for the orphan-doc fix
  in §4.1, the one place this route's behavior intentionally differs from
  `care_plan_jobs.py`'s).
- `DELETE /trial/jobs/<job_id>` — 204 on owned trial doc (asserts `delete_gcs_object` was
  called with the doc's `input_pdf_gcs_uri` and the doc no longer exists after); 204 →
  404 on double-delete; 403 when `uid` mismatches; 403 when `is_trial` is `False` even if
  `uid` matches (the two-condition check, §4.6); 404 on a nonexistent `job_id`; 401
  variants.
- `grading_enabled`/`version`/`doc_id` sent in the request body are ignored (assert the
  created job doc always has `grading_enabled=True`, `input_version="v1-2"`,
  `input_doc_id=None` regardless of what's posted).

**`backend/tests/utils/test_rate_limit.py`** (new):
- `get_client_ip` returns the last `X-Forwarded-For` value when present; falls back to
  `remote_addr` when absent; ignores a spoofed first value when a real proxy-appended
  last value is present.
- `_hash_ip` is deterministic for the same IP+salt, differs across IPs, differs across
  salts.
- `check_rate_limit` allows exactly 5 calls for a given IP within one window and blocks
  the 6th; a call in the *next* hour-aligned window is allowed again (mock/freeze time
  across the boundary).
- Concurrent-increment correctness: two simulated simultaneous transactions for the same
  IP+window only ever result in a final count that respects the limit (exercise the
  `@firestore.transactional` retry path, e.g. against the Firestore emulator if the test
  suite has one available, else a mocked transaction with a controlled race).
- `rate_limit_trial` fails OPEN (allows the request) when `check_rate_limit` raises.

**`backend/tests/models/test_job.py`** (extend existing, if present, else add coverage
inline in `test_care_plan_jobs.py`'s job-doc assertions):
- `JobDoc.for_single()` with no `is_trial`/`expires_at` args (i.e. every existing
  main-app call site, unchanged) still produces `is_trial=False, expires_at=None` —
  regression guard that adding the fields didn't change default main-app behavior.
- `to_firestore()` on a non-trial doc includes an explicit `expires_at: None` (verifying
  the `exclude_none=False` behavior §4.3 relies on for the TTL-safety argument).

**`backend/tests/routes/test_worker.py`** (extend):
- A completed `is_trial=True` job with a non-null `input_pdf_gcs_uri` triggers
  `delete_gcs_object` exactly once in the `finally` block, on both the success path and
  the pipeline-failure path.
- A non-trial job never triggers `delete_gcs_object`, regardless of outcome (regression
  guard — this must never fire for main-app jobs).
- A job doc deleted mid-flight (simulate `get_job_doc` returning `None` on a later call)
  still returns `200` idempotently — existing behavior, re-asserted because this PRD adds
  a new code path in the same function.

**`backend/tests/utils/test_gcs.py`** (extend):
- `delete_gcs_object` parses a `gs://bucket/path/to/obj.pdf` URI correctly; swallows
  `google.api_core.exceptions.NotFound`; logs (doesn't raise) on any other exception;
  warns and no-ops on a non-`gs://` input.

**Manual/integration smoke test** (not a new automated test — called out for the P4
"Ship" phase per brainstorm.md, cross-referenced here): create a real trial job end to
end (upload → Cloud Tasks → `juno-worker` → Firestore doc `completed` → GCS input object
gone → `DELETE` removes the Firestore doc), confirmed against the actual deployed
services before public launch.

---

## 8. Manual Intervention Required From You

1. **Add a new GitHub Actions repository secret `TRIAL_RATE_LIMIT_SALT`** — any random
   32+ byte value (e.g. `openssl rand -hex 32`). Used only to HMAC-hash client IPs before
   they're stored in the `trial_rate_limits` Firestore collection, so raw IPs are never
   persisted. Referenced in `deploy.yml` as `${{ secrets.TRIAL_RATE_LIMIT_SALT }}` (§4.12).
2. **Confirm the `GCP_SA_KEY` service account used by `deploy.yml` can create Cloud Tasks
   queues** (`cloudtasks.queues.create`/`.get`, e.g. via `roles/cloudtasks.admin` or a
   narrower custom role) — needed once, the first time the new "Ensure trial Cloud Tasks
   queue exists" deploy step runs (§4.12, §9 Q7). If the deploy step fails with a
   permission error, grant this role once; no other action needed afterward since the
   step is idempotent.

Everything else in this PRD (Firestore collections, model fields, routes, error codes) is
created/written by application code on first use — no other console steps, migrations,
or approvals are required for SP2 specifically. (The Firebase Anonymous sign-in provider
and PR #35 merge are already done per brainstorm.md §8, and SP5's TTL policy enablement
is tracked there, not here.)

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Auth model for the trial route. | **[RESOLVED: D1 — anonymous Firebase Auth, `@verify_firebase_token` unchanged, no auth code touched.]** |
| Q2 | Should `DELETE /trial/jobs/<id>` also be rate-limited? | **[RESOLVED: no.]** Gating cleanup behind the same 5/hour budget a user just spent creating jobs would block their own retention-guarantee call — directly undermines the "no data is saved" promise. Only `POST /trial/jobs` carries `rate_limit_trial`. |
| Q3 | Should `POST /trial/jobs`'s rate limiter run before or after Firebase auth verification? | **[RESOLVED: before.]** `rate_limit_trial` is the outermost decorator, keyed purely on IP (no `uid` dependency), so unauthenticated floods are throttled before paying the token-verification cost. Accepted tradeoff: a legitimate request with a bad/expired token still consumes one of the IP's 5 slots — acceptable since it's the same abusive-or-confused IP either way. |
| Q4 | Does `GET /trial/jobs/<job_id>` need to exist? | **[RESOLVED: no, dropped from the contract.]** SP3 subscribes to Firestore directly via `onSnapshot`, identical to the main app's `useJobSnapshot` — see §5. |
| Q5 | Fixed vs. sliding rate-limit window? | **[RESOLVED: fixed, hour-aligned UTC.]** Accepts a boundary-burst edge case (up to ~2× the nominal limit for requests straddling the hour mark) for a single-document atomic transaction per check; a sliding-log approach needs a timestamp subcollection and materially more reads/writes for no proportionate benefit at trial scale. |
| Q6 | Firestore security rules changes for `is_trial` docs? | **[RESOLVED: none.]** `allow write: if false` already forces every write through the Admin SDK (bypasses rules); `allow get` already covers anon-auth same-uid reads with zero changes. See §4.11. |
| Q7 | Should trial jobs use a separate Cloud Tasks queue, and is a Cloud Run `--max-instances` ceiling also needed? | **[RESOLVED: yes to the queue split (§4.9)]** — `care-plan-jobs-trial` with its own low `--max-concurrent-dispatches`/`--max-dispatches-per-second`, throughput-isolating trial traffic from the main `care-plan-jobs` queue even though both dispatch to the same `juno-worker` service. **[RESOLVED for `--max-instances`, per user 2026-09-05]** — decided in SP4's PRD, not here (`04-hosting-split-and-legal/PRD.md` §4.6, since SP4 owns `deploy.yml`): `juno-api` = 10, `juno-worker` = 5. One dependency still to flag: whichever deploy step ends up creating `care-plan-jobs-trial` must confirm the deploying service account already has the Cloud Tasks queue IAM role SP2's own new deploy step needs (§8 item 2) — same account, same ask, worth doing together. |
| Q8 | Should `TRIAL_RATE_LIMIT_SALT` live in Secret Manager or a plain env var/GitHub secret? | **[RESOLVED: plain env var/GitHub secret.]** The salt only raises the bar against trivial reversal of hashed IPs in Firestore — it is not protecting a high-value credential the way `FIREBASE_SERVICE_ACCOUNT_JSON` is. Secret Manager would add provisioning overhead (new secret resource, IAM binding, `--set-secrets` wiring) with no proportionate benefit here. |
| Q9 | Does this PRD fix the pre-existing "orphan Firestore doc when Cloud Tasks config is missing" bug in `POST /care_plan/jobs`? | **[RESOLVED: no, out of scope for the existing route.]** The **new** trial route validates `require_env(...)` before writing the Firestore doc (§4.1), so it never has this bug itself. Fixing `care_plan_jobs.py`'s existing ordering is a separate, low-risk follow-up flagged here for a future SP, not bundled into this one to keep this PRD's diff scoped to purely additive trial code. |
| Q10 | Firestore TTL policy risk on the shared `care_plan_outputs` collection — could enabling it accidentally delete main-app job docs? | **[RESOLVED: no, verified by construction — see §4.3.]** Firestore TTL only ever deletes a document where the target field is present and holds a Timestamp; a `null` value (which every main-app doc has, since `to_firestore()` writes `expires_at: null` explicitly) is permanently skipped. This is the single highest-blast-radius risk in this design and it is resolved structurally, not by operational discipline alone. |
| Q11 | What happens if the frontend calls `DELETE` while the worker is still `processing`? | **[RESOLVED: allowed, no status guard needed — verified self-healing.]** See §4.6: worst case is one wasted Cloud Tasks retry that resolves via the existing idempotent "job doc not found" path. |
| Q12 | Does the trial route accept `doc_id` input like the main app? | **[RESOLVED: no.]** The trial has no login and no prior uploads to reference by `doc_id`; `_resolve_trial_input` supports only `text` and `files`. |
| Q13 | Is `X-Forwarded-For`'s last value always trustworthy? | **[RESOLVED for the current topology.]** Cloud Run is the only proxy hop today (no external HTTPS Load Balancer/Cloud Armor/CDN — confirmed against `deploy.yml`), so the rightmost XFF value is Google-appended and trustworthy. **[DEFERRED]**: if any future project change puts Cloud Run behind an additional external LB/CDN layer, `get_client_ip()`'s "take the last value" logic must change to "take the second-to-last value" — flagged here for whoever adds such a layer. |
| Q14 | Should `grading_enabled`/`version` be client-controlled for the trial, matching the main app's request model? | **[RESOLVED: no.]** Hard-coded server-side (`grading_enabled=True`, `version="v1-2"`), any client-supplied value silently ignored — matches the product scope's "no grading option shown, grading always runs" (brainstorm §2). |
| Q15 | Should trial GCS uploads move off the shared `care_plan/` prefix onto a distinct one? | **[RESOLVED: yes, per user 2026-09-05]** — raised by SP5's design pass (`05-retention-automation/PRD.md` §4.10/§9 Q3), which found `care_plan/{user_id}/inputs/{uuid}.pdf` indistinguishable between trial and main-app uploads, blocking a safe lifecycle-rule backstop. `upload_combined_pdf` now takes `is_trial` and writes trial uploads to `care_plan_trial/{user_id}/inputs/{uuid}.pdf` (§4.1); main-app behavior is unchanged (`is_trial` defaults `False`). Enables SP5's prefix-scoped lifecycle rule. |
