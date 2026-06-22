"""grading.py — Re-run grading on a saved or ephemeral care plan output."""

import logging
import os

from flask import Blueprint, jsonify, request

from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403
from utils.scoring import score_text
from models.grading import build_grading

logger = logging.getLogger(__name__)
grading_bp = Blueprint("grading", __name__)


@grading_bp.route("/care_plan/grade", methods=["POST"])
@verify_firebase_token
def run_care_plan_grading(user_id: str):
    """Re-run grading for a saved or ephemeral care plan output.

    Body (JSON):
      { "saved_id": "<uuid>" }
        OR
      { "text": "...", "clarified_text": "..." }

    Returns: { "grading": <Grading.to_dict()> }
    """
    body = request.get_json(silent=True) or {}

    saved_id = body.get("saved_id")
    if saved_id:
        db = firestore_client()
        doc, err = get_owned_doc_or_403(db, "care_plan_outputs", saved_id, user_id, path=request.path)
        if err:
            return err

        data = doc.to_dict()
        output_data = data.get("output_data", {})
        raw = output_data.get("care_plan", {}).get("raw", {})
        raw_text = raw.get("text") or ""
        clarified_text = raw.get("clarified_text") or ""

        if not raw_text:
            return jsonify({"error": "No source text found in saved output"}), 400

        before_score = _score_safe(raw_text, "before")
        after_score = _score_safe(clarified_text, "after") if clarified_text else None
        grading = build_grading(before_score, raw_text, after_score, clarified_text or None)

        doc.reference.update({"output_data.grading": grading.to_dict()})

        return jsonify({"grading": grading.to_dict()})

    text = body.get("text", "").strip()
    clarified_text = body.get("clarified_text", "").strip()

    if not text:
        return jsonify({"error": "Provide either 'saved_id' or 'text'"}), 400

    before_score = _score_safe(text, "before")
    after_score = _score_safe(clarified_text, "after") if clarified_text else None
    grading = build_grading(before_score, text, after_score, clarified_text or None)

    return jsonify({"grading": grading.to_dict()})


def _score_safe(text: str, label: str) -> dict | None:
    try:
        return score_text(text)
    except Exception:
        logger.exception("grading: %s-score failed", label)
        return None
