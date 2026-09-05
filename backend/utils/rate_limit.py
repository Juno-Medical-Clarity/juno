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
