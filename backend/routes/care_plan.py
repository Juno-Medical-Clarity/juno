"""
care_plan.py - V1.2 care plan blueprint registration.

The input-resolution and GCS upload/fetch helpers formerly here have moved to
services/care_plan_input.py. The pipeline-execution adapter
(run_care_plan_pipeline) has moved to services/care_plan_pipeline.py.
The SSE streaming route (POST /care_plan) has been removed; use POST /care_plan/jobs instead.
"""

# ── Imports & blueprint setup ──────────────────────────────────────────────────
import logging

from flask import Blueprint, g, request  # noqa: F401

from models.grading import GRADING_VERSION  # noqa: F401
from models.care_plan import CarePlan, CARE_PLAN_VERSION  # noqa: F401
from models.care_plan.envelope import CarePlanInternal  # noqa: F401
from models.input import INPUT_VERSION  # noqa: F401
from errors import make_error_response, ErrorCode, build_error_data_from_exc, JunoError  # noqa: F401

logger = logging.getLogger(__name__)

care_plan_bp = Blueprint("care_plan", __name__)


