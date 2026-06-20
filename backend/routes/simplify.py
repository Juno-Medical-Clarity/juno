"""
Simplify route — medical document simplification pipeline.

POST /simplify
  Accepts: multipart/form-data with 'file' field (PDF, .txt, .docx)
  Returns: text/event-stream (SSE) with per-step progress + final result

SSE event schema (each line: "data: <json>\\n\\n"):
  { "step": 1, "status": "active", "label": "..." }
  { "step": 1, "status": "done",   "label": "..." }
  { "step": "result", "data": { ...structured output... } }
  { "step": "error",  "error": "..." }

File is held in memory only — never written to GCS or Firestore.
"""

import io
import json
import logging
from typing import Generator

from config import SIMPLIFY_DEFAULT_VERSION
from flask import Blueprint, g, request, Response, stream_with_context

from routes.simplify_v1_1 import simplify_v1_1
from routes.simplify_v1_2 import simplify_v1_2
from simplify.v1.pipeline import V1Pipeline
from utils.auth import verify_firebase_token
from utils.juno_logger import monotonic_ms
from utils.pdf_extract import extract_text_from_pdf
from utils.scoring import score_text
from models.metrics import Metrics
from models.input import Input
from models.grading import Grading, build_grading

logger = logging.getLogger(__name__)

simplify_bp = Blueprint("simplify", __name__)

# ── Step metadata ─────────────────────────────────────────────────────────────
STEPS = {
    1: "Reading your document",
    2: "Identifying document type",
    3: "Simplifying language",
    4: "Adding explanations for medical terms",
    5: "Clarifying numbers and actions",
    6: "Organizing for clarity",
    7: "Generating follow-up questions",
}

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
ALLOWED_VERSIONS = {"v1", "v1-1", "v1-2"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _sse(payload: dict) -> str:
    """Format a Python dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF, TXT, or DOCX bytes."""
    ext = filename.rsplit(".", 1)[1].lower()

    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)

    if ext == "docx":
        try:
            from docx import Document  # python-docx
        except ImportError:
            raise RuntimeError(
                "python-docx is not installed. Add 'python-docx' to requirements.txt."
            )
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    raise ValueError(f"Unsupported file extension: {ext}")


def run_v1_pipeline(text: str, metrics: Metrics, grading_enabled: bool) -> Generator[str, None, None]:
    pipeline_start = monotonic_ms()

    try:
        pipeline = V1Pipeline()

        # ── Score original text (silent — no SSE event) ───────────────────
        if grading_enabled:
            try:
                before_score = score_text(text)
            except Exception:
                logger.exception("simplify: before-score failed — continuing without score")
                before_score = None
        else:
            before_score = None

        # ── Step 2: Classify document type ────────────────────────────────
        yield _sse({"step": 2, "status": "active", "label": STEPS[2]})
        t0 = monotonic_ms()
        try:
            classification = pipeline.classify_document(text)
            doc_type = classification.get("doc_type", "appointment_note")
        except Exception:
            logger.exception("simplify: document classification failed — defaulting to appointment_note")
            doc_type = "appointment_note"
        yield _sse({"step": 2, "status": "done", "label": STEPS[2]})

        # ── Detect jargon (silent) ────────────────────────────────────────
        t0 = monotonic_ms()
        try:
            jargon_result = pipeline.detect_jargon(text)
            medical_jargon = jargon_result["medical_jargon"]
            complex_terms = jargon_result["complex_terms"]
        except Exception:
            logger.exception("simplify: jargon detection failed — continuing without jargon data")
            medical_jargon = []
            complex_terms = []

        # ── Step 3: Simplify language ─────────────────────────────────────
        yield _sse({"step": 3, "status": "active", "label": STEPS[3]})
        t0 = monotonic_ms()
        try:
            simplified = pipeline.simplify_language(text, medical_jargon, complex_terms)
        except Exception as exc:
            logger.exception("simplify: language simplification failed")
            yield _sse({"step": "error", "error": f"Simplification failed: {exc}"})
            return
        yield _sse({"step": 3, "status": "done", "label": STEPS[3]})

        # ── Step 4: Add definitions ───────────────────────────────────────
        yield _sse({"step": 4, "status": "active", "label": STEPS[4]})
        t0 = monotonic_ms()
        try:
            with_defs = pipeline.add_definitions(simplified, medical_jargon)
        except Exception:
            logger.exception("simplify: definition injection failed — using simplified text")
            with_defs = simplified
        yield _sse({"step": 4, "status": "done", "label": STEPS[4]})

        # ── Step 5: Clarify numbers and actions ───────────────────────────
        yield _sse({"step": 5, "status": "active", "label": STEPS[5]})
        t0 = monotonic_ms()
        try:
            clarified = pipeline.clarify_and_action(with_defs)
        except Exception:
            logger.exception("simplify: clarification step failed — using previous output")
            clarified = with_defs
        yield _sse({"step": 5, "status": "done", "label": STEPS[5]})

        # ── Score simplified text (silent — no SSE event) ─────────────────
        if grading_enabled:
            try:
                after_score = score_text(clarified)
            except Exception:
                logger.exception("simplify: after-score failed — continuing without score")
                after_score = None
        else:
            after_score = None

        # ── Steps 6 + 7: Structure + questions ───────────────────────────
        yield _sse({"step": 6, "status": "active", "label": STEPS[6]})
        yield _sse({"step": 7, "status": "active", "label": STEPS[7]})
        t0 = monotonic_ms()
        try:
            structured = pipeline.structure_document(clarified, medical_jargon, doc_type)
        except Exception as exc:
            logger.exception("simplify: document structuring failed")
            yield _sse({"step": "error", "error": f"Structuring failed: {exc}"})
            return
        yield _sse({"step": 6, "status": "done", "label": STEPS[6]})
        yield _sse({"step": 7, "status": "done", "label": STEPS[7]})

        # ── Final result ──────────────────────────────────────────────────
        result_payload = {**structured}

        metrics.total_duration_ms = monotonic_ms() - pipeline_start
        if grading_enabled:
            grading = build_grading(before_score, text, after_score, clarified)
        else:
            grading = Grading(enabled=False)
        output = {
            "metrics": metrics.to_dict(),
            "input": Input.from_text(text).to_dict(),
            "grading": grading.to_dict(),
            "care_plan": {"version": "1.0", **result_payload},
        }
        yield _sse({"step": "result", "data": output})

    except Exception as exc:
        logger.exception("simplify: unexpected pipeline error")
        yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})


def _payload_from_sse(chunk: str) -> dict | None:
    if not chunk.startswith("data: "):
        return None
    return json.loads(chunk.removeprefix("data: ").strip())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@simplify_bp.route("/simplify", methods=["POST"])
@verify_firebase_token
def simplify_document(user_id: str):
    """Stream simplification pipeline progress + result via SSE."""
    _ = user_id

    json_body = request.get_json(silent=True) or {}
    if "version" in request.form:
        version = request.form.get("version")
    elif isinstance(json_body, dict) and "version" in json_body:
        version = json_body.get("version")
    else:
        version = SIMPLIFY_DEFAULT_VERSION

    if not isinstance(version, str) or version not in ALLOWED_VERSIONS:
        return {"error": f"Unknown version '{version}'"}, 400

    if version == "v1-2":
        return simplify_v1_2()

    if version == "v1-1":
        return simplify_v1_1()

    return _simplify_document_v1()


def _simplify_document_v1():
    """Stream V1 simplification pipeline progress + result via SSE."""

    # ── Validate file upload ──────────────────────────────────────────────────
    if "file" not in request.files:
        return {"error": "No file field in request"}, 400

    upload = request.files["file"]
    if not upload.filename or not _allowed(upload.filename):
        return {"error": "File must be PDF, TXT, or DOCX"}, 400

    file_bytes = upload.read()
    if len(file_bytes) > MAX_FILE_BYTES:
        return {"error": "File exceeds 10 MB limit"}, 413

    filename = upload.filename
    logger.info("simplify: received '%s' (%d bytes)", filename, len(file_bytes))

    # ── Stream generator ──────────────────────────────────────────────────────
    def generate():
        metrics = Metrics.start(
            session_id=getattr(g, "session_id", ""),
            pipeline_version="v1",
            input_type="file",
        )

        try:
            # ── Step 1: Extract text ──────────────────────────────────────────
            yield _sse({"step": 1, "status": "active", "label": STEPS[1]})
            t0 = monotonic_ms()
            try:
                text = _extract_text(file_bytes, filename)
            except Exception as exc:
                logger.exception("simplify: text extraction failed")
                yield _sse({"step": "error", "error": f"Could not read file: {exc}"})
                return
            if not text.strip():
                yield _sse({"step": "error", "error": "File appears to be empty or unreadable."})
                return
            yield _sse({"step": 1, "status": "done", "label": STEPS[1]})

            try:
                upload.seek(0)
            except Exception:
                pass
            input_model = Input.from_file_uploads([upload])

            json_data = request.get_json(silent=True) or {}
            raw = request.form.get("grading_enabled")
            if raw is None:
                raw = json_data.get("grading_enabled", True)
            grading_enabled_flag = raw if isinstance(raw, bool) else str(raw).strip().lower() in {"1", "true", "yes", "on"}

            for chunk in run_v1_pipeline(text, metrics, grading_enabled=grading_enabled_flag):
                payload = _payload_from_sse(chunk)
                if not payload or payload.get("step") != "result":
                    yield chunk
                    continue

                result_data = payload["data"]
                result_data["input"] = input_model.to_dict()
                yield _sse({"step": "result", "data": result_data})

        except Exception as exc:
            logger.exception("simplify: unexpected pipeline error")
            yield _sse({"step": "error", "error": f"Pipeline error: {exc}"})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection":       "keep-alive",
        },
    )
