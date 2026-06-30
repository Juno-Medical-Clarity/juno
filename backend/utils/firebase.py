"""Firebase utilities: initialization, Firestore client, auth, and persistence."""

from __future__ import annotations

import copy  # noqa: F401
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from functools import wraps

import firebase_admin
from firebase_admin import auth, credentials, firestore
from flask import g, request
from errors import make_error_response, ErrorCode

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class FirestoreError(RuntimeError):
    """Raised when a Firestore operation fails in a firebase wrapper function."""


# ---------------------------------------------------------------------------
# Firebase / Firestore initialization
# ---------------------------------------------------------------------------

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    if not firebase_admin._apps:
        # Prefer JSON string from env (Cloud Run / CI via Secret Manager)
        sa_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        if sa_json:
            cred = credentials.Certificate(json.loads(sa_json))
            firebase_admin.initialize_app(cred)
        else:
            service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            if service_account_path and os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                # For production, use default credentials
                firebase_admin.initialize_app()

    # Get the Firestore database ID from environment variable
    database_id = os.getenv('FIRESTORE_DATABASE_ID', '(default)')

    # Return Firestore client with specific database
    return firestore.client(database_id=database_id)


def firestore_client():
    """Return a Firestore client using FIRESTORE_DATABASE_ID env (default: '(default)')."""
    db_id = os.environ.get("FIRESTORE_DATABASE_ID", "(default)")
    return firestore.client(database_id=db_id)


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def _extract_bearer_token(auth_header: str | None) -> tuple[str | None, tuple | None]:
    """Parse 'Bearer <token>'. Returns (token, None) or (None, (error_dict, status))."""
    if not auth_header:
        return None, (make_error_response(ErrorCode.MISSING_AUTH_HEADER, None).to_dict(), 401)
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        return None, (make_error_response(ErrorCode.MALFORMED_AUTH_HEADER, None).to_dict(), 401)
    return parts[1], None


def verify_firebase_token(f):
    """Decorator to verify Firebase ID token from Authorization header"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # OPTIONS preflight must pass through so flask-cors can attach CORS headers
        if request.method == 'OPTIONS':
            return '', 204

        token, err = _extract_bearer_token(request.headers.get("Authorization"))
        if err:
            return err

        try:
            # Verify the token
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']

            # Store on flask.g so JunoLogger / SessionIdFilter pick it up
            # automatically on every structured log call in this request.
            g.user_id = user_id

            # Also pass as a kwarg for route handlers that need it explicitly
            kwargs['user_id'] = user_id

        except Exception as e:
            return make_error_response(ErrorCode.UNAUTHORIZED, request.path, {"detail": str(e)}).to_dict(), 401

        return f(*args, **kwargs)

    return decorated_function


def require_admin(f):
    """Decorator to verify Firebase ID token and require the 'admin' custom claim."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # OPTIONS preflight must pass through so flask-cors can attach CORS headers
        if request.method == 'OPTIONS':
            return '', 204

        token, err = _extract_bearer_token(request.headers.get("Authorization"))
        if err:
            return err

        try:
            # Verify the token
            decoded_token = auth.verify_id_token(token)

            # Check admin custom claim
            if decoded_token.get('admin') is not True:
                return make_error_response(ErrorCode.RESOURCE_FORBIDDEN, request.path).to_dict(), 403

            user_id = decoded_token['uid']
            g.user_id = user_id
            kwargs['user_id'] = user_id

        except Exception as e:
            logger.warning("Admin token verification failed: %s", e)
            return make_error_response(ErrorCode.UNAUTHORIZED, request.path).to_dict(), 401

        return f(*args, **kwargs)

    return decorated_function


# ---------------------------------------------------------------------------
# Document access helpers
# ---------------------------------------------------------------------------

def get_owned_doc_or_403(db, collection: str, doc_id: str, user_id: str, path: str | None = None):
    """Fetch a document from `collection`, verify ownership.

    Returns (doc, None) on success, or (None, (response, status_code)) on error.
    """
    ref = db.collection(collection).document(doc_id)
    doc = ref.get()
    if not doc.exists:
        return None, (make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path, {"collection": collection, "doc_id": doc_id}).to_dict(), 404)
    data = doc.to_dict()
    if data.get('uid') != user_id:
        return None, (make_error_response(ErrorCode.RESOURCE_FORBIDDEN, path, {"collection": collection, "doc_id": doc_id}).to_dict(), 403)
    return doc, None


# ---------------------------------------------------------------------------
# Persistence: general outputs
# ---------------------------------------------------------------------------

def save_care_plan_output(
    *,
    user_id: str,
    name: str,
    source_filename: str,
    output_data: dict,
    dataset_group: str | None = None,
    batch_group_id: str | None = None,
) -> str:
    """Save a care_plan output document to Firestore and return its ID."""
    database_id = os.environ.get("FIRESTORE_DATABASE_ID", "(default)")
    output_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db = firestore.client(database_id=database_id)
    payload = {
        "uid": user_id,
        "name": name,
        "source_filename": source_filename,
        "created_at": now,
        "updated_at": now,
        "output_data": output_data,
    }
    if dataset_group is not None:
        payload["dataset_group"] = dataset_group
    if batch_group_id is not None:
        payload["batch_group_id"] = batch_group_id

    db.collection("care_plan_outputs").document(output_id).set(payload)
    return output_id


# ---------------------------------------------------------------------------
# Persistence: job lifecycle wrappers
# ---------------------------------------------------------------------------

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
