"""
saved_outputs.py — CRUD endpoints for saved care plan outputs.

All endpoints require Firebase auth (user_id from token).

GET  /care_plan/saved              — list user's saved outputs (metadata only)
GET  /care_plan/saved/<doc_id>     — get full output data for one saved output
PATCH /care_plan/saved/<doc_id>    — rename a saved output
DELETE /care_plan/saved/<doc_id>   — delete a saved output and its GCS files
GET  /care_plan/saved/<doc_id>/input-pdf-url — get a signed URL for the combined PDF
"""

import logging
import os
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request
from firebase_admin import firestore
from google.cloud import storage as gcs

from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403
from utils.error_codes import make_error_response, ErrorCode

logger = logging.getLogger(__name__)
saved_outputs_bp = Blueprint("saved_outputs", __name__)

_BUCKET_NAME = os.environ.get('GCP_BUCKET_NAME', '')

# Firestore composite index required:
# Collection: care_plan_outputs
# Fields: uid ASC, created_at DESC
# Create via Firebase console or firestore.indexes.json


@saved_outputs_bp.route('/care_plan/saved', methods=['GET'])
@verify_firebase_token
def list_saved(user_id: str):
    """Return list of saved outputs for the authenticated user, newest first."""
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


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['GET'])
@verify_firebase_token
def get_saved(user_id: str, doc_id: str):
    """Return full output data for a single saved output."""
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


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['PATCH'])
@verify_firebase_token
def rename_saved(user_id: str, doc_id: str):
    """Update a saved output. Body may include {"name": "new name"} and/or {"comment": "text"}."""
    db = firestore_client()
    doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
    if err:
        return err
    body = request.get_json(silent=True) or {}

    updates: dict = {'updated_at': datetime.now(timezone.utc)}

    # Handle optional name update
    if 'name' in body:
        new_name = (body.get('name') or '').strip()
        if not new_name:
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "name", "reason": "required"},
            ).to_dict(), 400
        if len(new_name) > 200:
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "name", "reason": "max 200 chars"},
            ).to_dict(), 400
        updates['name'] = new_name

    # Handle optional comment update
    if 'comment' in body:
        comment = body.get('comment')
        if not isinstance(comment, str):
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "comment", "reason": "must be a string"},
            ).to_dict(), 400
        if len(comment) > 2000:
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "comment", "reason": "max 2000 chars"},
            ).to_dict(), 400
        updates['comment'] = comment

    # Handle optional note update (stored inside output_data.care_plan.note)
    if 'note' in body:
        note = body.get('note')
        if not isinstance(note, str):
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "note", "reason": "must be a string"},
            ).to_dict(), 400
        if len(note) > 2000:
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": "note", "reason": "max 2000 chars"},
            ).to_dict(), 400
        updates['output_data.care_plan.note'] = note

    if len(updates) == 1:
        # Only updated_at was set — no actual fields were provided
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            f"/care_plan/saved/{doc_id}",
            {"reason": "at least one of 'name', 'comment', or 'note' is required"},
        ).to_dict(), 400

    db.collection('care_plan_outputs').document(doc_id).update(updates)
    return jsonify({'id': doc_id, **{k: v for k, v in updates.items() if k != 'updated_at'}})


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['DELETE'])
@verify_firebase_token
def delete_saved(user_id: str, doc_id: str):
    """Delete a saved output and its GCS files."""
    db = firestore_client()
    doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
    if err:
        return err
    data = doc.to_dict()

    # Delete GCS file if present
    gcs_uri = (
        (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
        or data.get('input_pdf_gcs', '')
    )
    if gcs_uri and _BUCKET_NAME:
        try:
            client = gcs.Client(project=os.environ.get('GCP_PROJECT_ID') or None)
            bucket = client.bucket(_BUCKET_NAME)
            blob_name = gcs_uri.replace(f"gs://{_BUCKET_NAME}/", "")
            bucket.blob(blob_name).delete()
        except Exception:
            logger.exception("delete_saved: failed to delete GCS file %s", gcs_uri)

    db.collection('care_plan_outputs').document(doc_id).delete()
    return jsonify({'deleted': doc_id})


@saved_outputs_bp.route('/care_plan/saved/<doc_id>/input-pdf-url', methods=['GET'])
@verify_firebase_token
def get_input_pdf_url(user_id: str, doc_id: str):
    """
    Return a short-lived signed URL for the combined input PDF.
    Used by the Show Original split view.
    """
    db = firestore_client()
    doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
    if err:
        return err
    data = doc.to_dict()
    # Try new envelope location first (SP-11+); fall back to legacy top-level field for old docs.
    gcs_uri = (
        (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url')
        or data.get('input_pdf_gcs', '')
    )
    if not gcs_uri or not _BUCKET_NAME:
        return make_error_response(
            ErrorCode.PDF_URL_UNAVAILABLE,
            f"/care_plan/saved/{doc_id}/input-pdf-url",
            {"doc_id": doc_id},
        ).to_dict(), 404

    try:
        client = gcs.Client(project=os.environ.get('GCP_PROJECT_ID') or None)
        bucket = client.bucket(_BUCKET_NAME)
        blob_name = gcs_uri.replace(f"gs://{_BUCKET_NAME}/", "")
        blob = bucket.blob(blob_name)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=30),
            method="GET",
        )
        return jsonify({'url': signed_url})
    except Exception as e:
        logger.exception("get_input_pdf_url: failed to generate signed URL")
        return make_error_response(
            ErrorCode.INTERNAL_ERROR,
            f"/care_plan/saved/{doc_id}/input-pdf-url",
        ).to_dict(), 500


@saved_outputs_bp.route('/care_plan/saved/<doc_id>/share', methods=['PATCH'])
@verify_firebase_token
def toggle_share(user_id: str, doc_id: str):
    """Toggle the shared flag on a saved output. Body: {"shared": true|false}"""
    db = firestore_client()
    body = request.get_json(silent=True) or {}
    shared = body.get('shared')
    if not isinstance(shared, bool):
        return make_error_response(
            ErrorCode.INPUT_VALIDATION_ERROR,
            f"/care_plan/saved/{doc_id}/share",
            {"field": "shared", "reason": "must be a boolean"},
        ).to_dict(), 400

    doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
    if err:
        return err

    db.collection('care_plan_outputs').document(doc_id).update({
        'shared': shared,
        'updated_at': firestore.SERVER_TIMESTAMP,
    })
    return jsonify({'shared': shared})
