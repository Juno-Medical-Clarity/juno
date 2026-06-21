"""Firebase utilities: initialization, Firestore client, auth, and persistence."""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from functools import wraps

import firebase_admin
from firebase_admin import auth, credentials, firestore
from flask import g, jsonify, request

from dotenv import load_dotenv

load_dotenv()


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


def verify_firebase_token(f):
    """Decorator to verify Firebase ID token from Authorization header"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401

        try:
            # Extract token from "Bearer <token>"
            parts = auth_header.split(' ', 1)
            if len(parts) != 2 or parts[0] != 'Bearer':
                return jsonify({'error': 'Malformed Authorization header'}), 401
            token = parts[1]

            # Verify the token
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']

            # Store on flask.g so JunoLogger / SessionIdFilter pick it up
            # automatically on every structured log call in this request.
            g.user_id = user_id

            # Also pass as a kwarg for route handlers that need it explicitly
            kwargs['user_id'] = user_id

            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401

    return decorated_function


def get_owned_doc_or_403(db, collection: str, doc_id: str, user_id: str):
    """Fetch a document from `collection`, verify ownership.

    Returns (doc, None) on success, or (None, (response, status_code)) on error.
    """
    ref = db.collection(collection).document(doc_id)
    doc = ref.get()
    if not doc.exists:
        return None, (jsonify({'error': 'Not found'}), 404)
    data = doc.to_dict()
    if data.get('uid') != user_id:
        return None, (jsonify({'error': 'Forbidden'}), 403)
    return doc, None


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
