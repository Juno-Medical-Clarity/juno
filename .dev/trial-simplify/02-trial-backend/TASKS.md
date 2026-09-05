# Tasks: SP2 — Trial Backend Route, Rate Limiting & Retention

Source PRD: `.dev/trial-simplify/02-trial-backend/PRD.md`. All decisions below trace to
PRD §4 (Architecture Decisions); §9 is fully `[RESOLVED]`/`[DEFERRED]` — no open
questions block this work (Q13 is `[DEFERRED]` to a future topology change, not
actionable here). Order matches dependency order; each task is committable on its own.

**Cross-SP boundaries respected in this file:** no `--max-instances` change (SP4), no
Firestore TTL policy enablement or GCS lifecycle rule (SP5 — SP2 only writes the
`expires_at` field they key off), no `frontend-trial/` code (SP3), no fix for the
pre-existing orphan-Firestore-doc bug in `care_plan_jobs.py` (§9 Q9 — explicitly out of
scope; the new trial route is simply built so it never has this bug itself).

---

### Task 1 — Add `Trial` constants to `backend/utils/constants.py`

   - Files: `backend/utils/constants.py`
   - Changes: Add a new nested class inside `Constants`, alongside the existing
     `Uploads`/`Batch`/`Deadlines` classes (PRD §4.4):
     ```python
     class Trial:
         MAX_FILE_COUNT: int = 5
         RATE_LIMIT_PER_IP_PER_HOUR: int = 5
         RATE_LIMIT_COLLECTION: str = "trial_rate_limits"
         RATE_LIMIT_COUNTER_TTL_HOURS: int = 2
         JOB_TTL_HOURS: int = 1
     ```
     Do not touch `Constants.Uploads.MAX_FILE_COUNT` (stays `10`) or any other existing
     member — this is a purely additive nested class.
   - Acceptance criteria:
     - `python -c "from utils.constants import Constants; print(Constants.Trial.MAX_FILE_COUNT, Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR, Constants.Trial.RATE_LIMIT_COLLECTION, Constants.Trial.RATE_LIMIT_COUNTER_TTL_HOURS, Constants.Trial.JOB_TTL_HOURS)"` prints `5 5 trial_rate_limits 2 1`.
     - `Constants.Uploads.MAX_FILE_COUNT` is still `10` (unchanged).

---

### Task 2 — Add `RATE_LIMIT_EXCEEDED` error code

   - Files: `backend/errors/codes.py`
   - Changes: Per PRD §4.8, two additions:
     1. In the `ErrorCode` enum, add a new member (anywhere sensible — e.g. near the
        end, after `ATHENA_TIMEOUT`, or in a new "Rate Limiting" section):
        ```python
        RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
        """The caller's IP has exceeded the trial's per-hour simplification limit."""
        ```
     2. In `ERROR_CATALOG`, add the matching entry:
        ```python
        ErrorCode.RATE_LIMIT_EXCEEDED: ErrorInfo(
            code="RATE_LIMIT_EXCEEDED",
            http_status=429,
            message="Trial rate limit exceeded",
            user_hint="You've reached the trial's limit of 5 simplifications per hour. Please try again later.",
            retryable=True,
        ),
        ```
   - Acceptance criteria:
     - `python -c "from errors import ErrorCode, ERROR_CATALOG; print(ERROR_CATALOG[ErrorCode.RATE_LIMIT_EXCEEDED].http_status)"` prints `429`.
     - `cd backend && python -m pytest tests/errors/test_codes.py -q` still passes (this
       file likely asserts every `ErrorCode` member has a catalog entry — the new member
       must not break that invariant).

---

### Task 3 — Add `is_trial`/`expires_at` fields to `JobDoc` (`backend/models/job.py`)

   - Files: `backend/models/job.py`
   - Changes: Per PRD §4.3.
     1. Add two new optional fields, after the existing `trace_id: Optional[str] = None`
        line (end of the "Single-job-only extras" section):
        ```python
        # ── Trial (SP2) ───────────────────────────────────────────────────────
        is_trial: bool = False
        expires_at: Optional[datetime] = None
        ```
     2. Update `for_single()`'s signature and body to accept and pass through the two
        new optional kwargs, defaulting to today's behavior:
        ```python
        @classmethod
        def for_single(
            cls,
            *,
            user_id: str,
            now: datetime,
            trace_id: Optional[str],
            input_fields: dict,
            is_trial: bool = False,
            expires_at: Optional[datetime] = None,
        ) -> "JobDoc":
            """Build a job doc for a single (non-batch) care-plan job.

            input_fields dict must contain:
              input_source_kind, input_text, input_doc_id,
              input_source_filename, input_pdf_gcs_uri,
              input_version, grading_enabled
            """
            return cls(
                uid=user_id,
                name=now.strftime("%b %d, %Y %H:%M"),
                source_filename=input_fields["input_source_filename"],
                created_at=now,
                updated_at=now,
                status=StatusEnum.not_started,
                shared=False,
                comment="",
                trace_id=trace_id,
                is_trial=is_trial,
                expires_at=expires_at,
                **input_fields,
            )
        ```
     Do not change `to_firestore()` — it already does `model_dump(mode="python",
     exclude_none=False)`, which is exactly what makes every main-app doc's
     `expires_at: null` write TTL-inert (verified in PRD §4.3's "Critical
     verification" note). No other model file or call site needs touching:
     `care_plan_jobs.py`'s existing `JobDoc.for_single(...)` call omits the two new
     kwargs and gets `is_trial=False, expires_at=None` for free.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/models/test_job.py -q` passes (existing
       tests untouched by this task must still be green — the new fields are optional
       with safe defaults).
     - `python -c "from models.job import JobDoc; import inspect; print(inspect.signature(JobDoc.for_single))"`
       shows `is_trial` and `expires_at` as keyword params with defaults `False`/`None`.

---

### Task 4 — Extend `backend/tests/models/test_job.py` for the new trial fields

   - Files: `backend/tests/models/test_job.py`
   - Changes: Add two new test functions (per PRD §7), using the existing
     `test_for_single_sets_shared_comment_trace` test's `input_fields` fixture pattern:
     ```python
     def test_for_single_defaults_is_trial_false_and_expires_at_none(now):
         input_fields = {
             "input_source_kind": "text",
             "input_text": "hello",
             "input_doc_id": None,
             "input_source_filename": "note.txt",
             "input_pdf_gcs_uri": None,
             "input_version": "v1-2",
             "grading_enabled": False,
         }
         job = JobDoc.for_single(user_id="u2", now=now, trace_id=None, input_fields=input_fields)
         assert job.is_trial is False
         assert job.expires_at is None


     def test_for_single_accepts_trial_kwargs(now):
         from datetime import timedelta
         expires = now + timedelta(hours=1)
         input_fields = {
             "input_source_kind": "text",
             "input_text": "hello",
             "input_doc_id": None,
             "input_source_filename": "note.txt",
             "input_pdf_gcs_uri": None,
             "input_version": "v1-2",
             "grading_enabled": True,
         }
         job = JobDoc.for_single(
             user_id="u2", now=now, trace_id=None, input_fields=input_fields,
             is_trial=True, expires_at=expires,
         )
         assert job.is_trial is True
         assert job.expires_at == expires


     def test_to_firestore_writes_explicit_null_expires_at_for_non_trial_doc(now):
         input_fields = {
             "input_source_kind": "text",
             "input_text": "hello",
             "input_doc_id": None,
             "input_source_filename": "note.txt",
             "input_pdf_gcs_uri": None,
             "input_version": "v1-2",
             "grading_enabled": False,
         }
         job = JobDoc.for_single(user_id="u2", now=now, trace_id=None, input_fields=input_fields)
         d = job.to_firestore()
         assert "expires_at" in d
         assert d["expires_at"] is None
         assert d["is_trial"] is False
     ```
     (The `now` fixture already exists in this file at module scope.)
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/models/test_job.py -q` passes, including
       the three new tests.

---

### Task 5 — Add `delete_gcs_object` to `backend/utils/gcs.py`

   - Files: `backend/utils/gcs.py`
   - Changes: Per PRD §4.5/§4.6, add a new best-effort delete helper. Add near the
     "Generic bucket access" section (after `get_gcs_bucket`):
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
     No other function in this file changes.
   - Acceptance criteria:
     - `python -c "from utils.gcs import delete_gcs_object; print('ok')"` succeeds.
     - A non-`gs://` string passed to `delete_gcs_object` logs a warning and returns
       without raising (manually verify via Task 6's tests).

---

### Task 6 — Extend `backend/tests/utils/test_gcs.py` for `delete_gcs_object`

   - Files: `backend/tests/utils/test_gcs.py`
   - Changes: Add a new section using this file's existing `mock_gcs_module` fixture
     (chain: `gcs.Client()` → `mock_client` → `.bucket()` → `mock_bucket` → `.blob()` →
     `mock_blob`):
     ```python
     # ---------------------------------------------------------------------------
     # delete_gcs_object
     # ---------------------------------------------------------------------------

     def test_delete_gcs_object_parses_uri_and_deletes(mock_gcs_module):
         from utils.gcs import delete_gcs_object
         delete_gcs_object("gs://my-bucket/care_plan_trial/user-1/inputs/abc.pdf")
         mock_gcs_module.delete.assert_called_once()


     def test_delete_gcs_object_uses_correct_bucket_and_blob_name(monkeypatch):
         from unittest.mock import MagicMock
         import utils.gcs as mod

         mock_client = MagicMock()
         monkeypatch.setattr(mod, "_client", mock_client)

         from utils.gcs import delete_gcs_object
         delete_gcs_object("gs://my-bucket/care_plan_trial/user-1/inputs/abc.pdf")

         mock_client.bucket.assert_called_once_with("my-bucket")
         mock_client.bucket.return_value.blob.assert_called_once_with(
             "care_plan_trial/user-1/inputs/abc.pdf"
         )


     def test_delete_gcs_object_swallows_not_found(mock_gcs_module):
         from google.api_core.exceptions import NotFound
         mock_gcs_module.delete.side_effect = NotFound("gone")

         from utils.gcs import delete_gcs_object
         delete_gcs_object("gs://my-bucket/some/path.pdf")  # must not raise


     def test_delete_gcs_object_logs_but_does_not_raise_on_other_error(mock_gcs_module):
         mock_gcs_module.delete.side_effect = RuntimeError("boom")

         from utils.gcs import delete_gcs_object
         delete_gcs_object("gs://my-bucket/some/path.pdf")  # must not raise


     def test_delete_gcs_object_warns_and_noops_on_non_gs_uri(caplog):
         from utils.gcs import delete_gcs_object
         delete_gcs_object("not-a-gs-uri")  # must not raise
     ```
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_gcs.py -q` passes, including
       the five new tests.

---

### Task 7 — `upload_combined_pdf` gains `is_trial` kwarg (trial GCS prefix, §9 Q15)

   - Files: `backend/services/care_plan_input.py`
   - Changes: Per PRD §4.1 (the "GCS upload prefix" addendum, resolving SP5 §9 Q3 / this
     PRD's own §9 Q15). Replace the current `upload_combined_pdf`:
     ```python
     # old
     def upload_combined_pdf(pdf_bytes: bytes, user_id: str) -> str:
         """Upload combined input PDF bytes and return a gs:// URI."""
         bucket_name = os.environ.get(Constants.Storage.GCS_BUCKET_ENV_VAR, "")
         if not bucket_name:
             raise RuntimeError("GCP_BUCKET_NAME is not configured")

         object_id = str(uuid.uuid4())
         blob_name = f"care_plan/{user_id}/inputs/{object_id}.pdf"

         bucket = get_gcs_bucket(bucket_name)
         blob = bucket.blob(blob_name)
         blob.upload_from_string(pdf_bytes, content_type="application/pdf")
         return f"gs://{bucket_name}/{blob_name}"
     ```
     with:
     ```python
     # new
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
     `is_trial` defaults to `False`, so both existing call sites
     (`routes/care_plan_jobs.py:65` and any `batch_jobs.py` caller) are byte-for-byte
     unaffected and keep writing to `care_plan/`. Do not change either existing call
     site in this task — Task 11 wires the new trial call site.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_save_output.py -q` passes
       unmodified — `test_upload_combined_pdf_uses_care_plan_gcs_path` (which calls
       `upload_combined_pdf(b"%PDF", "user-1")` with no `is_trial` arg and asserts the
       `care_plan/user-1/...` path) must still pass with zero changes to that test,
       proving the default is unaffected.

---

### Task 8 — Extend `backend/tests/utils/test_save_output.py` for the trial prefix

   - Files: `backend/tests/utils/test_save_output.py`
   - Changes: Add one new test directly after `test_upload_combined_pdf_uses_care_plan_gcs_path`,
     following its exact mocking pattern:
     ```python
     @patch.dict("services.care_plan_input.os.environ", {"GCP_BUCKET_NAME": "bucket", "GCP_PROJECT_ID": "project"})
     @patch("services.care_plan_input.uuid.uuid4")
     @patch("services.care_plan_input.get_gcs_bucket")
     def test_upload_combined_pdf_is_trial_uses_trial_gcs_path(get_gcs_bucket, uuid4):
         from services.care_plan_input import upload_combined_pdf

         uuid4.return_value = "input-789"
         blob = MagicMock()
         bucket = get_gcs_bucket.return_value
         bucket.blob.return_value = blob

         uri = upload_combined_pdf(b"%PDF", "user-1", is_trial=True)

         assert uri == "gs://bucket/care_plan_trial/user-1/inputs/input-789.pdf"
         bucket.blob.assert_called_once_with("care_plan_trial/user-1/inputs/input-789.pdf")
     ```
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_save_output.py -q` passes,
       including the new test, and the pre-existing non-trial test in the same file is
       unmodified.

---

### Task 9 — New module `backend/utils/rate_limit.py` (Firestore-backed per-IP limiter)

   - Files: `backend/utils/rate_limit.py` (new)
   - Changes: Per PRD §4.2, create the file verbatim as specified there:
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
   - Acceptance criteria:
     - `python -c "from utils.rate_limit import get_client_ip, check_rate_limit, rate_limit_trial; print('ok')"`
       succeeds.
     - No other file is modified in this task (verified in Task 10 by running only the
       new test file).

---

### Task 10 — New test file `backend/tests/utils/test_rate_limit.py`

   - Files: `backend/tests/utils/test_rate_limit.py` (new)
   - Changes: Per PRD §7. Cover:
     ```python
     """Tests for utils/rate_limit.py — the trial route's per-IP Firestore counter."""
     import pytest
     from unittest.mock import MagicMock, patch
     from datetime import datetime, timezone

     from utils.rate_limit import get_client_ip, _hash_ip, check_rate_limit, rate_limit_trial
     from utils.constants import Constants


     # ---------------------------------------------------------------------------
     # get_client_ip
     # ---------------------------------------------------------------------------

     def test_get_client_ip_uses_last_xff_value(app):
         with app.test_request_context(headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}):
             assert get_client_ip() == "5.6.7.8"


     def test_get_client_ip_ignores_spoofed_first_value():
         from flask import Flask
         app = Flask(__name__)
         with app.test_request_context(headers={"X-Forwarded-For": "attacker-spoofed, 9.9.9.9"}):
             assert get_client_ip() == "9.9.9.9"


     def test_get_client_ip_falls_back_to_remote_addr():
         from flask import Flask
         app = Flask(__name__)
         with app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
             assert get_client_ip() == "10.0.0.1"


     # ---------------------------------------------------------------------------
     # _hash_ip
     # ---------------------------------------------------------------------------

     def test_hash_ip_deterministic_same_ip_and_salt(monkeypatch):
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
         assert _hash_ip("1.2.3.4") == _hash_ip("1.2.3.4")


     def test_hash_ip_differs_across_ips(monkeypatch):
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
         assert _hash_ip("1.2.3.4") != _hash_ip("5.6.7.8")


     def test_hash_ip_differs_across_salts(monkeypatch):
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-a")
         h1 = _hash_ip("1.2.3.4")
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt-b")
         h2 = _hash_ip("1.2.3.4")
         assert h1 != h2


     # ---------------------------------------------------------------------------
     # check_rate_limit — uses fake_firestore-style in-memory counter, not the
     # emulator (no emulator is configured in this test suite's CI setup).
     # ---------------------------------------------------------------------------

     class _FakeSnapshot:
         def __init__(self, count):
             self._count = count
             self.exists = count is not None

         def get(self, field):
             return self._count if field == "count" else None


     class _FakeRef:
         """Minimal Firestore doc-ref stand-in with an in-memory count."""
         def __init__(self, store, key):
             self._store = store
             self._key = key

         def get(self, transaction=None):
             return _FakeSnapshot(self._store.get(self._key))


     class _FakeTransaction:
         def set(self, ref, data, merge=True):
             ref._store[ref._key] = data["count"]


     @pytest.fixture
     def fake_rate_limit_firestore(monkeypatch):
         """Patch firestore_client() so check_rate_limit() operates on an
         in-memory dict keyed by doc_id, simulating Firestore's transactional
         read-then-write without needing a real emulator."""
         store: dict[str, int] = {}

         def _fake_client():
             db = MagicMock()

             def _doc(doc_id):
                 return _FakeRef(store, doc_id)

             db.collection.return_value.document.side_effect = _doc
             db.transaction.return_value = _FakeTransaction()
             return db

         monkeypatch.setattr("utils.rate_limit.firestore_client", _fake_client)
         return store


     def test_check_rate_limit_allows_up_to_limit_and_blocks_the_next(fake_rate_limit_firestore, monkeypatch):
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt")
         from flask import Flask
         app = Flask(__name__)
         with app.test_request_context(environ_base={"REMOTE_ADDR": "1.1.1.1"}):
             results = [check_rate_limit() for _ in range(Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR + 1)]
         assert results == [True] * Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR + [False]


     def test_check_rate_limit_resets_in_next_hour_window(fake_rate_limit_firestore, monkeypatch):
         monkeypatch.setenv("TRIAL_RATE_LIMIT_SALT", "salt")
         from flask import Flask
         app = Flask(__name__)

         with app.test_request_context(environ_base={"REMOTE_ADDR": "2.2.2.2"}):
             for _ in range(Constants.Trial.RATE_LIMIT_PER_IP_PER_HOUR):
                 assert check_rate_limit() is True
             assert check_rate_limit() is False

         # Simulate the next hour-aligned window by freezing datetime.now().
         class _FrozenDatetime(datetime):
             @classmethod
             def now(cls, tz=None):
                 base = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
                 return base if tz is None else base.astimezone(tz)

         with patch("utils.rate_limit.datetime", _FrozenDatetime):
             with app.test_request_context(environ_base={"REMOTE_ADDR": "2.2.2.2"}):
                 assert check_rate_limit() is True


     # ---------------------------------------------------------------------------
     # rate_limit_trial decorator
     # ---------------------------------------------------------------------------

     def test_rate_limit_trial_fails_open_on_exception(monkeypatch):
         monkeypatch.setattr("utils.rate_limit.check_rate_limit", MagicMock(side_effect=RuntimeError("firestore down")))

         @rate_limit_trial
         def _handler():
             return "ok", 200

         from flask import Flask
         app = Flask(__name__)
         with app.test_request_context("/trial/jobs", method="POST"):
             body, status = _handler()
         assert status == 200
         assert body == "ok"


     def test_rate_limit_trial_returns_429_when_blocked(monkeypatch):
         monkeypatch.setattr("utils.rate_limit.check_rate_limit", MagicMock(return_value=False))

         @rate_limit_trial
         def _handler():
             return "ok", 200

         from flask import Flask
         app = Flask(__name__)
         with app.test_request_context("/trial/jobs", method="POST"):
             body, status = _handler()
         assert status == 429
     ```
     Note: the `app` fixture used by `test_get_client_ip_uses_last_xff_value` is the
     shared one from `backend/tests/conftest.py` — verify it resolves via normal pytest
     fixture discovery; if not, replace with the same inline `Flask(__name__)` +
     `test_request_context` pattern the other tests in this file use (kept both styles
     above deliberately since either is acceptable — the fixture is only pulled in for
     the first test as a convenience, not a hard requirement).
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/utils/test_rate_limit.py -q` passes.
     - The 6th call within one simulated hour window is blocked (`False`); a call in a
       later simulated window succeeds again.
     - `rate_limit_trial` returns `200` (fails open) when `check_rate_limit` raises, and
       `429` when it returns `False`.

---

### Task 11 — New route module `backend/routes/trial.py`

   - Files: `backend/routes/trial.py` (new)
   - Changes: Per PRD §4.1, §4.6. Create the file verbatim as specified in the PRD
     (already incorporates the §4.1 GCS-prefix addendum — note the
     `upload_combined_pdf(raw_pdf_bytes, user_id, is_trial=True)` call, which depends on
     Task 7):
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
         pdf_gcs_uri = upload_combined_pdf(raw_pdf_bytes, user_id, is_trial=True) if raw_pdf_bytes else None
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
     This file has two forward dependencies that must land first: `Markers.Trial.*`
     (Task 13) and `CLOUD_TASKS_QUEUE_TRIAL` being a real env var name (Task 17 wires it
     into deploy; tests in Task 14 set it directly via `os.environ`/`monkeypatch`, so the
     route works correctly before Task 17 lands — order between 13/17 and this task only
     matters for `import` succeeding, which requires Task 13 first).
   - Acceptance criteria:
     - `python -c "from routes.trial import trial_bp; print(trial_bp.name)"` prints
       `trial` (requires Task 13's marker leaf to exist first, or this import fails with
       `AttributeError: type object 'Markers' has no attribute 'Trial'` — do Task 13
       before this task if implementing out of order).
     - No changes to `care_plan_jobs.py`, `resolve_uploaded_files`, or
       `Constants.Uploads.*` (grep `git diff --stat` to confirm only `trial.py` is new).

---

### Task 12 — Register `trial_bp` in `backend/routes/__init__.py`

   - Files: `backend/routes/__init__.py`
   - Changes: Per PRD §4.10, add the import and list entry:
     ```python
     from routes.saved_outputs import saved_outputs_bp
     from routes.datasets import datasets_bp
     from routes.clinician_dataset import clinician_dataset_bp
     from routes.grading import grading_bp
     from routes.care_plan_jobs import care_plan_jobs_bp
     from routes.batch_jobs import batch_jobs_bp
     from routes.worker import worker_bp
     from routes.admin import admin_bp
     from routes.trial import trial_bp

     API_BLUEPRINTS = [
         care_plan_jobs_bp,
         batch_jobs_bp,
         saved_outputs_bp,
         datasets_bp,
         clinician_dataset_bp,
         grading_bp,
         admin_bp,
         trial_bp,
     ]

     WORKER_BLUEPRINTS = [
         worker_bp,
     ]
     ```
   - Acceptance criteria:
     - `python -c "from routes import API_BLUEPRINTS; print([bp.name for bp in API_BLUEPRINTS])"`
       includes `"trial"` as the last entry.
     - `cd backend && python -c "from app import app; print(sorted(r.rule for r in app.url_map.iter_rules() if 'trial' in r.rule))"`
       prints `['/trial/jobs', '/trial/jobs/<job_id>']`.
     - **Known pre-existing unrelated failure, do not attempt to fix as part of this
       task:** `backend/tests/routes/test_route_rewire.py` already fails on `main`
       before this SP's changes (it hardcodes an exact blueprint-name list that is
       already stale — missing `clinician_dataset`, added by an earlier, unrelated SP).
       Adding `trial_bp` does not make this test "more broken" in any new way; it is out
       of this PRD's scope to fix (not named in PRD §4, §7, or §9). Confirm this by
       running `git stash && cd backend && python -m pytest tests/routes/test_route_rewire.py -q; git stash pop`
       before starting this task if you want to double check it was already red.

---

### Task 13 — Add `Trial` marker leaf to `backend/utils/markers/markers.py`

   - Files: `backend/utils/markers/markers.py`
   - Changes: Per PRD §4.10, add a new leaf class following the existing
     `Batch`/`Worker` pattern (place it near `Batch`, e.g. right after the `Batch` class):
     ```python
     class Trial:
         @code_marker("trial.create_job")
         class CreateJob(CodeMarker): pass

         @code_marker("trial.delete_job")
         class DeleteJob(CodeMarker): pass
     ```
   - Acceptance criteria:
     - `python -c "from utils.markers.markers import Markers; print(Markers.Trial.CreateJob.name(), Markers.Trial.DeleteJob.name())"`
       prints `trial.create_job trial.delete_job` (or however `CodeMarker.name()`
       formats it — match the existing `Markers.Batch.CreateSingleJob.name()` output
       convention; verify with `python -c "from utils.markers.markers import Markers; print(Markers.Batch.CreateSingleJob.name())"` first if unsure).
     - `cd backend && python -m pytest tests/utils/test_markers.py tests/utils/test_code_markers.py -q`
       still passes (confirms the new leaf doesn't collide with the marker registry's
       uniqueness checks, if any).

---

### Task 14 — New test file `backend/tests/routes/test_trial.py`

   - Files: `backend/tests/routes/test_trial.py` (new)
   - Changes: Per PRD §7, mirroring `test_care_plan_jobs.py`'s fixture/mocking style
     (own blueprint-scoped Flask app, `auth_ok` fixture bypassing
     `utils.firebase.auth.verify_id_token`, `@patch.dict("os.environ", {...})` for the
     three required Cloud Tasks env vars):
     ```python
     """TDD tests for POST /trial/jobs and DELETE /trial/jobs/<job_id>."""
     import pytest
     from datetime import datetime, timezone, timedelta
     from io import BytesIO
     from unittest.mock import patch, MagicMock
     from flask import Flask


     TRIAL_ENV = {
         "CLOUD_TASKS_QUEUE_TRIAL": "trial-queue",
         "WORKER_URL": "https://worker.run.app",
         "WORKER_SERVICE_ACCOUNT": "sa@proj.iam",
     }


     @pytest.fixture
     def app_trial():
         from routes.trial import trial_bp
         app = Flask(__name__)
         app.register_blueprint(trial_bp)
         return app


     @pytest.fixture
     def client_trial(app_trial):
         return app_trial.test_client()


     @pytest.fixture
     def auth_ok(monkeypatch):
         monkeypatch.setattr("utils.firebase.auth.verify_id_token", lambda *a, **k: {"uid": "user-1"})
         return {"Authorization": "Bearer test-token"}


     @pytest.fixture(autouse=True)
     def _allow_rate_limit(monkeypatch):
         """Most tests aren't testing the rate limiter itself — always allow."""
         monkeypatch.setattr("routes.trial.rate_limit_trial", lambda f: f)


     # ---------------------------------------------------------------------------
     # POST /trial/jobs
     # ---------------------------------------------------------------------------

     @patch.dict("os.environ", TRIAL_ENV)
     @patch("routes.trial.enqueue_job_safe", return_value=None)
     @patch("routes.trial.create_job_doc")
     def test_post_text_returns_202_with_trial_fields(mock_create_doc, mock_enqueue, client_trial, auth_ok):
         resp = client_trial.post("/trial/jobs", json={"text": "Patient has hypertension."}, headers=auth_ok)
         assert resp.status_code == 202
         assert "job_id" in resp.get_json()

         payload = mock_create_doc.call_args.kwargs["payload"]
         assert payload["is_trial"] is True
         assert payload["expires_at"] > datetime.now(timezone.utc)
         assert payload["grading_enabled"] is True
         assert payload["input_version"] == "v1-2"
         assert payload["input_doc_id"] is None

         enqueue_kwargs = mock_enqueue.call_args.kwargs
         assert enqueue_kwargs["queue_name"] == "trial-queue"


     @patch.dict("os.environ", TRIAL_ENV)
     @patch("routes.trial.enqueue_job_safe", return_value=None)
     @patch("routes.trial.create_job_doc")
     def test_post_multipart_upload_within_limit_returns_202(mock_create_doc, mock_enqueue, client_trial, auth_ok):
         data = {"files": (BytesIO(b"hello world"), "note.txt")}
         resp = client_trial.post(
             "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
         )
         assert resp.status_code == 202
         mock_create_doc.assert_called_once()


     @patch.dict("os.environ", TRIAL_ENV)
     @patch("routes.trial.enqueue_job_safe", return_value=None)
     @patch("routes.trial.create_job_doc")
     def test_post_more_than_5_files_returns_400(mock_create_doc, mock_enqueue, client_trial, auth_ok):
         data = {"files": [(BytesIO(b"x"), f"f{i}.txt") for i in range(6)]}
         resp = client_trial.post(
             "/trial/jobs", data=data, content_type="multipart/form-data", headers=auth_ok,
         )
         assert resp.status_code == 400
         assert resp.get_json()["error"]["code"] == "INPUT_VALIDATION_ERROR"
         mock_create_doc.assert_not_called()


     @patch.dict("os.environ", TRIAL_ENV)
     @patch("routes.trial.create_job_doc")
     def test_post_no_input_returns_400(mock_create_doc, client_trial, auth_ok):
         resp = client_trial.post("/trial/jobs", json={}, headers=auth_ok)
         assert resp.status_code == 400
         mock_create_doc.assert_not_called()


     def test_post_unauthenticated_returns_401(client_trial):
         resp = client_trial.post("/trial/jobs", json={"text": "hi"})
         assert resp.status_code == 401


     @patch.dict("os.environ", {}, clear=True)
     @patch("routes.trial.create_job_doc")
     def test_post_missing_cloud_tasks_config_returns_500_and_no_doc_created(mock_create_doc, client_trial, auth_ok):
         resp = client_trial.post("/trial/jobs", json={"text": "hi"}, headers=auth_ok)
         assert resp.status_code == 500
         # Regression guard for the orphan-doc bug (§9 Q9) — this route validates
         # Cloud Tasks config BEFORE writing to Firestore, unlike care_plan_jobs.py.
         mock_create_doc.assert_not_called()


     @patch.dict("os.environ", TRIAL_ENV)
     @patch("routes.trial.create_job_doc")
     def test_post_ignores_client_supplied_grading_and_version_and_doc_id(mock_create_doc, client_trial, auth_ok):
         with patch("routes.trial.enqueue_job_safe", return_value=None):
             resp = client_trial.post(
                 "/trial/jobs",
                 json={"text": "hi", "grading_enabled": False, "version": "v9-9", "doc_id": "some-doc"},
                 headers=auth_ok,
             )
         assert resp.status_code == 202
         payload = mock_create_doc.call_args.kwargs["payload"]
         assert payload["grading_enabled"] is True
         assert payload["input_version"] == "v1-2"
         assert payload["input_doc_id"] is None


     def test_rate_limit_429_blocks_before_auth(client_trial, monkeypatch):
         """With the real (non-bypassed) rate_limit_trial decorator, a blocked IP
         gets 429 even with no Authorization header at all."""
         import importlib
         import routes.trial as trial_module
         importlib.reload(trial_module)  # undo the autouse bypass fixture's monkeypatch
         monkeypatch.setattr(trial_module, "check_rate_limit", lambda: False)

         app = Flask(__name__)
         app.register_blueprint(trial_module.trial_bp)
         resp = app.test_client().post("/trial/jobs", json={"text": "hi"})
         assert resp.status_code == 429


     # ---------------------------------------------------------------------------
     # DELETE /trial/jobs/<job_id>
     # ---------------------------------------------------------------------------

     def _mock_doc(exists, data=None):
         doc = MagicMock()
         doc.exists = exists
         doc.to_dict.return_value = data or {}
         return doc


     @patch("routes.trial.delete_gcs_object")
     @patch("routes.trial.firestore_client")
     def test_delete_owned_trial_job_returns_204_and_deletes_gcs(mock_fs, mock_delete_gcs, client_trial, auth_ok):
         doc = _mock_doc(True, {"uid": "user-1", "is_trial": True, "input_pdf_gcs_uri": "gs://b/p.pdf"})
         ref = MagicMock()
         ref.get.return_value = doc
         mock_fs.return_value.collection.return_value.document.return_value = ref

         resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
         assert resp.status_code == 204
         mock_delete_gcs.assert_called_once_with("gs://b/p.pdf")
         ref.delete.assert_called_once()


     @patch("routes.trial.firestore_client")
     def test_delete_nonexistent_job_returns_404(mock_fs, client_trial, auth_ok):
         ref = MagicMock()
         ref.get.return_value = _mock_doc(False)
         mock_fs.return_value.collection.return_value.document.return_value = ref

         resp = client_trial.delete("/trial/jobs/nope", headers=auth_ok)
         assert resp.status_code == 404


     @patch("routes.trial.firestore_client")
     def test_delete_wrong_uid_returns_403(mock_fs, client_trial, auth_ok):
         doc = _mock_doc(True, {"uid": "someone-else", "is_trial": True})
         ref = MagicMock()
         ref.get.return_value = doc
         mock_fs.return_value.collection.return_value.document.return_value = ref

         resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
         assert resp.status_code == 403
         ref.delete.assert_not_called()


     @patch("routes.trial.firestore_client")
     def test_delete_non_trial_doc_returns_403_even_with_matching_uid(mock_fs, client_trial, auth_ok):
         doc = _mock_doc(True, {"uid": "user-1", "is_trial": False})
         ref = MagicMock()
         ref.get.return_value = doc
         mock_fs.return_value.collection.return_value.document.return_value = ref

         resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
         assert resp.status_code == 403
         ref.delete.assert_not_called()


     def test_delete_unauthenticated_returns_401(client_trial):
         resp = client_trial.delete("/trial/jobs/job-1")
         assert resp.status_code == 401


     @patch("routes.trial.firestore_client")
     def test_delete_is_not_rate_limited(mock_fs, client_trial, auth_ok):
         """DELETE has no rate_limit_trial decorator at all (§9 Q2) — calling it
         many times in a row never returns 429."""
         doc = _mock_doc(True, {"uid": "user-1", "is_trial": True, "input_pdf_gcs_uri": None})
         ref = MagicMock()
         ref.get.return_value = doc
         mock_fs.return_value.collection.return_value.document.return_value = ref

         for _ in range(10):
             resp = client_trial.delete("/trial/jobs/job-1", headers=auth_ok)
             assert resp.status_code in (204, 404)  # never 429
     ```
     Adjust mock targets (`routes.trial.<name>`) if any of them are actually imported
     under a different bound name than assumed here — verify against Task 11's exact
     `trial.py` import lines before finalizing.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/routes/test_trial.py -q` passes, all cases
       in PRD §7's `test_trial.py` bullet list are covered: 202 on text, 202 on ≤5-file
       upload, 400 on >5 files, 400 on neither text nor files, 401 unauthenticated, 500 +
       no-doc-created on missing Cloud Tasks config, ignored `grading_enabled`/`version`/
       `doc_id`, 204/404/403×2/401 for DELETE, and DELETE never rate-limited.

---

### Task 15 — Worker-side GCS cleanup hook for trial jobs (`backend/routes/worker.py`)

   - Files: `backend/routes/worker.py`
   - Changes: Per PRD §4.5. Two edits inside `execute_job`'s `_run` closure:
     1. Declare `job` before the `try` block, alongside the existing
        `gcs_temp_dir`/`is_gcs_dataset_job` declarations:
        ```python
        gcs_temp_dir: Path | None = None
        is_gcs_dataset_job = False
        job: JobDoc | None = None
        ```
     2. The line `job = JobDoc.from_firestore(job_doc)` (currently inside the `try`
        block) already assigns to this now-pre-declared variable — no change needed
        there, just confirm it's the same `job` name.
     3. Extend the `finally` block:
        ```python
        finally:
            if is_gcs_dataset_job:
                from utils.gcs import cleanup_dataset_inputs
                cleanup_dataset_inputs(job_id)
            if job is not None and getattr(job, "is_trial", False) and job.input_pdf_gcs_uri:
                from utils.gcs import delete_gcs_object
                delete_gcs_object(job.input_pdf_gcs_uri)
        ```
     This runs on every exit path (success, pipeline failure, timeout, unhandled
     exception) because `finally` always executes, and is idempotent on a Cloud Tasks
     retry of an already-terminal job (the `job.status in ("completed", "error")`
     early-return at the top of the try block still reaches this same `finally`).
     `getattr(job, "is_trial", False)` (rather than `job.is_trial`) is deliberate
     defensive coding matching the PRD's snippet, even though `is_trial` is now always a
     declared field with a default — do not "simplify" this to `job.is_trial`.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/routes/test_worker.py -q` passes (existing
       tests must stay green — verifies non-trial jobs are unaffected).
     - Manual read-check: `job = None` is now declared before the outer `try:` in
       `execute_job`'s `_run` function, and the `finally` block references it without
       raising `UnboundLocalError` even when an exception occurs before `job` is ever
       assigned (e.g. `get_job_doc` raising) — the `if job is not None` guard handles
       this.

---

### Task 16 — Extend `backend/tests/routes/test_worker.py` for trial GCS cleanup

   - Files: `backend/tests/routes/test_worker.py`
   - Changes: Per PRD §7. Add tests using this file's existing `_make_job_doc` helper
     (extend its signature to accept `is_trial`/`input_pdf_gcs_uri`, or build the dict
     inline — whichever keeps the diff smaller given the helper's current call sites):
     ```python
     def _make_trial_job_doc(status="not_started", input_pdf_gcs_uri="gs://b/p.pdf"):
         doc = _make_job_doc(status=status)
         doc["is_trial"] = True
         doc["input_pdf_gcs_uri"] = input_pdf_gcs_uri
         return doc


     @patch("utils.gcs.delete_gcs_object")
     @patch("utils.firebase.firestore.client")
     @patch("routes.worker.complete_job")
     @patch("routes.worker.update_job_stage")
     @patch("routes.worker.fail_job")
     @patch("routes.worker.get_job_doc")
     def test_trial_job_success_triggers_gcs_cleanup(
         mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
         mock_delete_gcs, client_worker,
     ):
         mock_get_doc.return_value = _make_trial_job_doc()
         mock_fs_client.return_value = MagicMock()

         care_plan_mock = MagicMock()
         care_plan_mock.to_dict.return_value = {"reason_for_visit": [{"reason": "Hypertension"}]}
         grading_mock = MagicMock()

         def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
             yield AdapterResult(care_plan=care_plan_mock, grading=grading_mock, raw_text=text, clarified_text="c")

         envelope_mock = MagicMock()
         envelope_mock.to_dict.return_value = {"care_plan": {}, "metrics": {"saved_id": None}}

         with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline(*a, **kw)}):
             with patch("routes.worker.CarePlanInternal", return_value=envelope_mock):
                 resp = client_worker.post(
                     "/internal/jobs/execute/job-1", headers=QUEUE_HEADER, content_type="application/json",
                 )

         assert resp.status_code == 200
         mock_delete_gcs.assert_called_once_with("gs://b/p.pdf")


     @patch("utils.gcs.delete_gcs_object")
     @patch("utils.firebase.firestore.client")
     @patch("routes.worker.complete_job")
     @patch("routes.worker.update_job_stage")
     @patch("routes.worker.fail_job")
     @patch("routes.worker.get_job_doc")
     def test_trial_job_pipeline_failure_still_triggers_gcs_cleanup(
         mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
         mock_delete_gcs, client_worker,
     ):
         mock_get_doc.return_value = _make_trial_job_doc()
         mock_fs_client.return_value = MagicMock()

         def fake_pipeline_error(text, metrics, grading_enabled, source_kind="text", is_batch=False):
             yield AdapterError(error_data={"code": "PIPELINE_ERROR", "message": "boom"})

         with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline_error(*a, **kw)}):
             resp = client_worker.post("/internal/jobs/execute/job-1", headers=QUEUE_HEADER)

         assert resp.status_code == 200
         mock_delete_gcs.assert_called_once_with("gs://b/p.pdf")


     @patch("utils.gcs.delete_gcs_object")
     @patch("utils.firebase.firestore.client")
     @patch("routes.worker.complete_job")
     @patch("routes.worker.update_job_stage")
     @patch("routes.worker.fail_job")
     @patch("routes.worker.get_job_doc")
     def test_non_trial_job_never_triggers_gcs_cleanup(
         mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
         mock_delete_gcs, client_worker,
     ):
         mock_get_doc.return_value = _make_job_doc()  # is_trial defaults False, no input_pdf_gcs_uri key
         mock_fs_client.return_value = MagicMock()

         care_plan_mock = MagicMock()
         care_plan_mock.to_dict.return_value = {}
         grading_mock = MagicMock()

         def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
             yield AdapterResult(care_plan=care_plan_mock, grading=grading_mock, raw_text=text, clarified_text="c")

         envelope_mock = MagicMock()
         envelope_mock.to_dict.return_value = {"care_plan": {}, "metrics": {"saved_id": None}}

         with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline(*a, **kw)}):
             with patch("routes.worker.CarePlanInternal", return_value=envelope_mock):
                 client_worker.post(
                     "/internal/jobs/execute/job-1", headers=QUEUE_HEADER, content_type="application/json",
                 )

         mock_delete_gcs.assert_not_called()
     ```
     Note: patch `utils.gcs.delete_gcs_object` (the function's home module), not
     `routes.worker.delete_gcs_object` — `worker.py`'s `finally` block imports it
     locally (`from utils.gcs import delete_gcs_object`) inside the `finally:` clause,
     so there is no module-level `routes.worker.delete_gcs_object` name to patch.
   - Acceptance criteria:
     - `cd backend && python -m pytest tests/routes/test_worker.py -q` passes, including
       the three new tests, and every pre-existing test in this file is still green
       (unmodified assertions).

---

### Task 17 — `.github/workflows/deploy.yml`: trial env vars and queue-ensure step

   - Files: `.github/workflows/deploy.yml`
   - Changes: Per PRD §4.12.
     1. Add a new step immediately before the existing "Configure juno-api env vars and
        secrets" step (after "Build, push, and deploy juno-api + juno-worker"):
        ```yaml
        - name: Ensure trial Cloud Tasks queue exists
          run: |
            gcloud tasks queues create care-plan-jobs-trial \
              --location "$GCP_REGION" --project "$GCP_PROJECT_ID" \
              --max-concurrent-dispatches=5 --max-dispatches-per-second=2 \
              || echo "queue already exists — continuing"
        ```
     2. In the "Configure juno-api env vars and secrets" step, extend the
        `API_ENV_VARS` string with two more comma-separated entries (append at the end):
        ```
        ,CLOUD_TASKS_QUEUE_TRIAL=projects/$GCP_PROJECT_ID/locations/$GCP_REGION/queues/care-plan-jobs-trial,TRIAL_RATE_LIMIT_SALT=${{ secrets.TRIAL_RATE_LIMIT_SALT }}
        ```
        So the full line becomes (existing content unchanged, just appended):
        ```yaml
        API_ENV_VARS="GCP_PROJECT_ID=$GCP_PROJECT_ID,GCP_BUCKET_NAME=$GCP_BUCKET_NAME,GCP_LOCATION=global,VERTEX_AI_MODEL=gemini-3.5-flash,SIMPLIFY_DEFAULT_VERSION=v1-2,FIRESTORE_DATABASE_ID=(default),CLOUD_TASKS_QUEUE=projects/$GCP_PROJECT_ID/locations/$GCP_REGION/queues/care-plan-jobs,WORKER_URL=$WORKER_URL,WORKER_SERVICE_ACCOUNT=juno-worker-invoker@$GCP_PROJECT_ID.iam.gserviceaccount.com,JOB_TIMEOUT_SECONDS_SINGLE=300,JOB_TIMEOUT_SECONDS_BATCH=900,CLOUD_TASKS_QUEUE_TRIAL=projects/$GCP_PROJECT_ID/locations/$GCP_REGION/queues/care-plan-jobs-trial,TRIAL_RATE_LIMIT_SALT=${{ secrets.TRIAL_RATE_LIMIT_SALT }}"
        ```
     Do not touch `deploy-frontend` or `tag` jobs, `juno-worker`'s env vars (the worker
     dispatches by `job_id` alone, agnostic of which queue enqueued the task — no worker
     change needed per PRD §4.12), or any `--max-instances`/`--min-instances` flag (SP4's
     territory, not touched here).

     **Context note (not a blocker for this task):** per the initiative's
     `.dev/trial-simplify/README.md` ("Infrastructure already provisioned"), the
     `care-plan-jobs-trial` queue has already been created manually and is `RUNNING`,
     and the `TRIAL_RATE_LIMIT_SALT` GitHub secret has already been added — so this
     task's `gcloud tasks queues create ... || echo "already exists"` step is expected
     to hit the "already exists" branch on its first real run. That is correct,
     intended, idempotent behavior, not a sign anything is wrong.
   - Acceptance criteria:
     - `grep -n "CLOUD_TASKS_QUEUE_TRIAL\|TRIAL_RATE_LIMIT_SALT\|care-plan-jobs-trial" .github/workflows/deploy.yml`
       shows the new step and the two new `API_ENV_VARS` entries.
     - The workflow YAML is still valid: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
       (or equivalent YAML lint) succeeds with no parse error.
     - `deploy-frontend` and `tag` jobs are byte-for-byte unchanged (`git diff .github/workflows/deploy.yml`
       shows edits confined to the `deploy-backend` job).

---

### Task 18 — Run the SP2-scoped test files and fix any regressions

   - Files: any file that fails — diagnose before editing; do not touch files outside
     this SP's scope (Tasks 1–17's files) without a clear regression reason.
   - Changes / steps: Run only the test files this SP touched or extended (per project
     convention, do not run the full backend suite for this pass):
     ```bash
     cd backend && python -m pytest \
       tests/utils/test_constants.py \
       tests/errors/test_codes.py \
       tests/models/test_job.py \
       tests/utils/test_gcs.py \
       tests/utils/test_save_output.py \
       tests/utils/test_rate_limit.py \
       tests/routes/test_trial.py \
       tests/routes/test_worker.py \
       tests/utils/test_markers.py \
       tests/utils/test_code_markers.py \
       tests/routes/test_care_plan_jobs.py \
       -q
     ```
     (`test_care_plan_jobs.py` is included as a regression guard — it must stay green
     with zero changes, proving the trial route's changes to shared helpers like
     `upload_combined_pdf` didn't alter main-app behavior.)

     For each failure, read the traceback and fix with a minimal targeted edit; re-run
     until green. Do not run or attempt to fix `tests/routes/test_route_rewire.py` as
     part of this task — see Task 12's note; it was already broken before this SP and
     fixing it is out of scope.
   - Acceptance criteria:
     - The command above exits 0 (all listed test files pass).
     - `git diff --stat` shows changes confined to: `backend/utils/constants.py`,
       `backend/errors/codes.py`, `backend/models/job.py`,
       `backend/tests/models/test_job.py`, `backend/utils/gcs.py`,
       `backend/tests/utils/test_gcs.py`, `backend/services/care_plan_input.py`,
       `backend/tests/utils/test_save_output.py`, `backend/utils/rate_limit.py` (new),
       `backend/tests/utils/test_rate_limit.py` (new), `backend/routes/trial.py` (new),
       `backend/routes/__init__.py`, `backend/utils/markers/markers.py`,
       `backend/tests/routes/test_trial.py` (new), `backend/routes/worker.py`,
       `backend/tests/routes/test_worker.py`, `.github/workflows/deploy.yml` — nothing
       else.

---

## Summary of what requires you (not a dev agent)

1. **`TRIAL_RATE_LIMIT_SALT` GitHub Actions secret (PRD §8 item 1, §9 Q8).** Per
   `.dev/trial-simplify/README.md`'s "Infrastructure already provisioned" list, **this
   is already done** — the secret has been added. No action needed unless it needs
   rotating.
2. **Confirm the `GCP_SA_KEY` deploy service account can create Cloud Tasks queues**
   (PRD §8 item 2, §9 Q7 — `cloudtasks.queues.create`/`.get`, e.g. `roles/cloudtasks.admin`
   or a narrower custom role). Per the initiative README, the `care-plan-jobs-trial`
   queue has **already been created manually** and is `RUNNING`, and the README also
   notes the investigation found `GCP_SA_KEY` holds no Cloud Tasks role — so Task 17's
   new "Ensure trial Cloud Tasks queue exists" deploy step is expected to hit its
   `|| echo "already exists"` fallback on next deploy rather than actually needing the
   IAM grant immediately. If a future deploy ever needs to recreate this queue (e.g. a
   different environment/project), you would need to grant that role once at that time.
3. **Cross-SP dependency for SP4:** SP4 must add `juno-app-99.web.app` to `app.py`'s
   CORS origin allow-list before the relocated full app can call the API from its new
   address (PRD §3 non-goals / initiative README's cross-cutting risks) — not this SP's
   file to change, flagged here only so it isn't missed when SP4 lands.
4. **Cross-SP dependency for SP5:** SP5's Firestore TTL policy
   (`gcloud firestore fields ttls update` on `care_plan_outputs.expires_at` and
   `trial_rate_limits.expires_at`) and the GCS lifecycle rule on `care_plan_trial/` are
   not part of this SP's tasks — SP2's job ends at writing the `expires_at` field and the
   distinct GCS prefix correctly (verified by Tasks 3–4 and 7–8 respectively). Do not
   run any `gcloud firestore fields ttls update` command from this task list.
5. **No other manual/owner-only step exists in this PRD.** PRD §8 lists exactly the two
   items above and both are already resolved per the initiative README's infrastructure
   checklist; nothing else in this PRD requires your direct action to land the code.
