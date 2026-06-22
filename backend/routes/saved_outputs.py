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
    """Rename a saved output. Body: {"name": "new name"}"""
    db = firestore_client()
    doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    new_name = (body.get('name') or '').strip()
    if not new_name:
        return jsonify({'error': 'name is required'}), 400
    if len(new_name) > 200:
        return jsonify({'error': 'name too long (max 200 chars)'}), 400
    db.collection('care_plan_outputs').document(doc_id).update({
        'name': new_name,
        'updated_at': datetime.now(timezone.utc),
    })
    return jsonify({'id': doc_id, 'name': new_name})


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
        return jsonify({'error': 'No input PDF stored for this output'}), 404

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
        return jsonify({'error': f'Could not generate URL: {e}'}), 500
