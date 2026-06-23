"""
admin.py — Admin-only endpoints.

GET /admin/stats — Returns job status counts and recent errors/active jobs.
Requires the 'admin' custom claim on the Firebase token.
"""

import logging

from flask import Blueprint, jsonify
from google.cloud import firestore

from utils.firebase import require_admin, firestore_client

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/admin/stats', methods=['GET'])
@require_admin
def get_admin_stats(user_id: str):
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

    # Recent errors - ordered by created_at desc
    recent_errors = []
    for doc in (collection
                .where('status', '==', 'error')
                .order_by('created_at', direction=firestore.Query.DESCENDING)
                .limit(10)
                .stream()):
        data = doc.to_dict()
        recent_errors.append({
            'id': doc.id,
            'name': data.get('name'),
            'created_at': data.get('created_at').isoformat() if data.get('created_at') else None,
            'error_data': data.get('error_data'),
        })

    # Active jobs - ordered by started_at desc
    recent_processing = []
    for doc in (collection
                .where('status', '==', 'processing')
                .order_by('started_at', direction=firestore.Query.DESCENDING)
                .limit(20)
                .stream()):
        data = doc.to_dict()
        recent_processing.append({
            'id': doc.id,
            'name': data.get('name'),
            'stage': data.get('stage'),
            'started_at': data.get('started_at').isoformat() if data.get('started_at') else None,
            'uid': data.get('uid'),
        })

    return jsonify({
        'status_counts': counts,
        'total': total,
        'recent_errors': recent_errors,
        'active_jobs': recent_processing,
    })
