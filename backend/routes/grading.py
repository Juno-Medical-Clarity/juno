"""grading.py — Re-run grading on a saved or ephemeral care plan output."""

import logging
import os  # noqa: F401

from flask import Blueprint, jsonify, request
from errors import make_error_response, ErrorCode

from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403
from utils.scoring import score_text_safe
from models.grading import build_grading_with_before_after_score
from utils.markers import Markers, JunoContext

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
    def _run(scope):
        JunoContext.from_g(function="run_care_plan_grading").apply(scope)
        from pydantic import ValidationError
        from models.grading import GradingRequest

        try:
            req = GradingRequest(**(request.get_json(silent=True) or {}))
        except ValidationError as exc:
            first_err = exc.errors()[0]
            loc = first_err.get("loc", ("unknown",))
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                request.path,
                {"field": str(loc[0]) if loc else "unknown", "reason": first_err["msg"]},
            ).to_dict(), 400

        saved_id = req.saved_id
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
                return make_error_response(
                    ErrorCode.NO_SOURCE_TEXT,
                    request.path,
                    {"saved_id": saved_id},
                ).to_dict(), 400

            before_score = score_text_safe(raw_text, "before")
            after_score = score_text_safe(clarified_text, "after") if clarified_text else None
            grading = build_grading_with_before_after_score(before_score, raw_text, after_score, clarified_text or None)

            try:
                doc.reference.update({"output_data.grading": grading.to_dict()})
            except Exception:
                logger.exception("grading: Firestore update failed for saved_id=%s", saved_id)
                return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

            return jsonify({"grading": grading.to_dict()})

        text = (req.text or "").strip()
        clarified_text = (req.clarified_text or "").strip()

        if not text:
            return make_error_response(
                ErrorCode.INPUT_VALIDATION_ERROR,
                request.path,
                {"field": "text", "reason": "provide either 'saved_id' or 'text'"},
            ).to_dict(), 400

        before_score = score_text_safe(text, "before")
        after_score = score_text_safe(clarified_text, "after") if clarified_text else None
        grading = build_grading_with_before_after_score(before_score, text, after_score, clarified_text or None)

        return jsonify({"grading": grading.to_dict()})

    return Markers.Grading.Route.execute(_run)
