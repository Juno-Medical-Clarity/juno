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

from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403
from utils.gcs_helpers import get_gcs_bucket
from utils.markers import Markers, JunoContext
from errors import make_error_response, ErrorCode

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
    def _run(scope):
        JunoContext.from_g(function="list_saved").apply(scope)
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
            scope.add("result_count", len(results))
            return jsonify({'outputs': results})
        except Exception:
            scope.mark_failed()
            logger.exception("list_saved: Firestore query failed for user_id=%s", user_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return Markers.SavedOutputs.List.execute(_run)


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['GET'])
@verify_firebase_token
def get_saved(user_id: str, doc_id: str):
    """Return full output data for a single saved output."""
    def _run(scope):
        JunoContext.from_g(function="get_saved").apply(scope)
        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
        if err:
            return err
        try:
            data = doc.to_dict()
            return jsonify({
                'id': doc.id,
                'name': data.get('name', 'Untitled'),
                'source_filename': data.get('source_filename', ''),
                'created_at': data['created_at'].isoformat() if data.get('created_at') else None,
                'output_data': data.get('output_data', {}),
            })
        except Exception:
            scope.mark_failed()
            logger.exception("get_saved: failed to read doc %s", doc_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return Markers.SavedOutputs.Get.execute(_run)


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['PATCH'])
@verify_firebase_token
def rename_saved(user_id: str, doc_id: str):
    """Update a saved output. Body may include {"name": "new name"} and/or {"comment": "text"}."""
    def _run(scope):
        JunoContext.from_g(function="rename_saved").apply(scope)
        from pydantic import ValidationError
        from models.saved_outputs import RenameOutputRequest

        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
        if err:
            return err

        try:
            req = RenameOutputRequest(**(request.get_json(silent=True) or {}))
        except ValidationError as exc:
            first_err = exc.errors()[0]
            loc = first_err.get("loc", ("unknown",))
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                f"/care_plan/saved/{doc_id}",
                {"field": str(loc[0]) if loc else "unknown", "reason": first_err["msg"]},
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

        try:
            db.collection('care_plan_outputs').document(doc_id).update(updates)
        except Exception:
            scope.mark_failed()
            logger.exception("rename_saved: Firestore update failed for doc_id=%s", doc_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
        return jsonify({'id': doc_id, **{k: v for k, v in updates.items() if k != 'updated_at'}})
    return Markers.SavedOutputs.Rename.execute(_run)


@saved_outputs_bp.route('/care_plan/saved/<doc_id>', methods=['DELETE'])
@verify_firebase_token
def delete_saved(user_id: str, doc_id: str):
    """Delete a saved output and its GCS files."""
    def _run(scope):
        JunoContext.from_g(function="delete_saved").apply(scope)
        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
        if err:
            return err
        data = doc.to_dict()

        # Delete GCS file if present
        gcs_uri = (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url') or ''
        if gcs_uri and _BUCKET_NAME:
            try:
                bucket = get_gcs_bucket()
                blob_name = gcs_uri.replace(f"gs://{_BUCKET_NAME}/", "")
                bucket.blob(blob_name).delete()
            except Exception:
                logger.exception("delete_saved: failed to delete GCS file %s", gcs_uri)

        try:
            db.collection('care_plan_outputs').document(doc_id).delete()
            return jsonify({'deleted': doc_id})
        except Exception:
            scope.mark_failed()
            logger.exception("delete_saved: Firestore delete failed for doc_id=%s", doc_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return Markers.SavedOutputs.Delete.execute(_run)


@saved_outputs_bp.route('/care_plan/saved/<doc_id>/input-pdf-url', methods=['GET'])
@verify_firebase_token
def get_input_pdf_url(user_id: str, doc_id: str):
    """
    Return a short-lived signed URL for the combined input PDF.
    Used by the Show Original split view.
    """
    def _run(scope):
        JunoContext.from_g(function="get_input_pdf_url").apply(scope)
        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", doc_id, user_id, path=request.path)
        if err:
            return err
        data = doc.to_dict()
        gcs_uri = (data.get('output_data') or {}).get('input', {}).get('pdf_gcs_url') or ''
        if not gcs_uri or not _BUCKET_NAME:
            return make_error_response(
                ErrorCode.PDF_URL_UNAVAILABLE,
                f"/care_plan/saved/{doc_id}/input-pdf-url",
                {"doc_id": doc_id},
            ).to_dict(), 404

        try:
            bucket = get_gcs_bucket()
            blob_name = gcs_uri.replace(f"gs://{_BUCKET_NAME}/", "")
            blob = bucket.blob(blob_name)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=30),
                method="GET",
            )
            return jsonify({'url': signed_url})
        except Exception:
            scope.mark_failed()
            logger.exception("get_input_pdf_url: failed to generate signed URL")
            return make_error_response(
                ErrorCode.INTERNAL_ERROR,
                f"/care_plan/saved/{doc_id}/input-pdf-url",
            ).to_dict(), 500
    return Markers.SavedOutputs.GetPdfUrl.execute(_run)


@saved_outputs_bp.route('/care_plan/saved/<doc_id>/share', methods=['PATCH'])
@verify_firebase_token
def toggle_share(user_id: str, doc_id: str):
    """Toggle the shared flag on a saved output. Body: {"shared": true|false}"""
    def _run(scope):
        JunoContext.from_g(function="toggle_share").apply(scope)
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

        try:
            db.collection('care_plan_outputs').document(doc_id).update({
                'shared': shared,
                'updated_at': firestore.SERVER_TIMESTAMP,
            })
            return jsonify({'shared': shared})
        except Exception:
            scope.mark_failed()
            logger.exception("toggle_share: Firestore update failed for doc_id=%s", doc_id)
            return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
    return Markers.SavedOutputs.ToggleShare.execute(_run)
