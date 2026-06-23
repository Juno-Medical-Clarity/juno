"""
admin.py — Admin-only endpoints.

GET /admin/stats — Returns job status counts and recent errors/active jobs.
Requires the 'admin' custom claim on the Firebase token.
"""

import logging

from flask import Blueprint, jsonify

from utils.firebase import require_admin, firestore_client

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.route('/admin/stats', methods=['GET'])
@require_admin
def get_admin_stats(user_id: str):
    db = firestore_client()
    collection = db.collection('care_plan_outputs')

    # Count by status
    all_docs = collection.stream()
    counts = {'not_started': 0, 'processing': 0, 'completed': 0, 'error': 0}
    total = 0
    recent_errors = []
    recent_processing = []

    for doc in all_docs:
        data = doc.to_dict()
        status = data.get('status', 'unknown')
        if status in counts:
            counts[status] += 1
        total += 1
        if status == 'error' and len(recent_errors) < 10:
            recent_errors.append({
                'id': doc.id,
                'name': data.get('name'),
                'created_at': data.get('created_at').isoformat() if data.get('created_at') else None,
                'error_data': data.get('error_data'),
            })
        if status == 'processing' and len(recent_processing) < 20:
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
