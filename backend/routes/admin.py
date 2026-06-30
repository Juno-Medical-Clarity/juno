"""
admin.py — Admin-only endpoints.

GET /admin/stats — Returns job status counts and recent errors/active jobs.
Requires the 'admin' custom claim on the Firebase token.
"""

import logging

from flask import Blueprint, jsonify, request
from google.cloud import firestore
from errors import make_error_response, ErrorCode

from utils.firebase import require_admin, firestore_client

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/admin/stats', methods=['GET'])
@require_admin
def get_admin_stats(user_id: str):
    try:
        db = firestore_client()
        collection = db.collection('care_plan_outputs')

        # Count by status (stream all for counts)
        counts = {'not_started': 0, 'processing': 0, 'completed': 0, 'error': 0}
        total = 0
        for doc in collection.stream():
            status = doc.to_dict().get('status', 'unknown')
            if status in counts:
                counts[status] += 1
            total += 1

        # Recent errors - no order_by (avoids composite index requirement), sort in Python
        recent_errors = []
        for doc in collection.where('status', '==', 'error').limit(10).stream():
            data = doc.to_dict()
            recent_errors.append({
                'id': doc.id,
                'name': data.get('name'),
                'created_at': data.get('created_at').isoformat() if data.get('created_at') else None,
                'error_data': data.get('error_data'),
            })
        recent_errors.sort(key=lambda x: x['created_at'] or '', reverse=True)

        # Active jobs - no order_by (avoids composite index requirement), sort in Python
        recent_processing = []
        for doc in collection.where('status', '==', 'processing').limit(20).stream():
            data = doc.to_dict()
            started_at = data.get('started_at')
            recent_processing.append({
                'id': doc.id,
                'name': data.get('name'),
                'stage': data.get('stage'),
                'started_at': started_at.isoformat() if started_at else None,
                'uid': data.get('uid'),
            })
        recent_processing.sort(key=lambda x: x['started_at'] or '', reverse=True)

        return jsonify({
            'status_counts': counts,
            'total': total,
            'recent_errors': recent_errors,
            'active_jobs': recent_processing,
        })
    except Exception:
        logger.exception("admin: get_admin_stats failed")
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
