import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from models.athena_manifest import AthenaEncounterManifest, AthenaClinicalDocManifest
from routes.care_plan import _extract_text_from_bytes
from utils.error_codes import make_error_response, ErrorCode
from utils.firebase import verify_firebase_token
from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

datasets_bp = Blueprint("datasets", __name__)
logger = logging.getLogger(__name__)

# Resolved relative to this file: backend/routes/../data/ = backend/data/
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_ATHENA_MANIFEST_NAMES = [
    "athena-encounters-manifest.json",
    "athena-clinicaldocs-manifest.json",
]

_SOURCE_KIND_MODEL_MAP = {
    "athena_encounter": AthenaEncounterManifest,
    "athena_clinical_doc": AthenaClinicalDocManifest,
}


def _load_athena_sources() -> list[dict]:
    """Load and validate Athena source manifests from backend/data/.

    Missing files are silently skipped. Files with an unknown source_kind or a
    Pydantic validation error are logged as warnings and skipped — no exception
    propagates to the caller.
    """
    sources = []
    for name in _ATHENA_MANIFEST_NAMES:
        path = DATA_DIR / name
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        source_kind = raw.get("source_kind")
        model_cls = _SOURCE_KIND_MODEL_MAP.get(source_kind)
        if model_cls is None:
            logger.warning(
                "Skipping manifest %s: unknown source_kind %r", name, source_kind
            )
            continue
        try:
            manifest = model_cls.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Skipping manifest %s: validation error — %s", name, exc)
            continue
        sources.append(manifest.model_dump())
    return sources


@datasets_bp.route("/care_plan/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id: str):
    _ = user_id
    return jsonify({
        "datasets": list_datasets(),
        "athena_sources": _load_athena_sources(),
    })


@datasets_bp.route(
    "/care_plan/datasets/<group>/<input_id>/<string:filename>",
    methods=["GET"],
)
@verify_firebase_token
def get_dataset_file_route(user_id: str, group: str, input_id: str, filename: str):
    _ = user_id

    try:
        file_bytes = read_dataset_file(group, input_id, filename)
        content = _extract_text_from_bytes(file_bytes, filename)
    except GCSFetchRequired:
        return make_error_response(
            ErrorCode.DATASET_DOWNLOAD_ERROR,
            request.path,
            {"group": group, "input_id": input_id, "detail": "GCS fetch not yet implemented (SP2)"},
        ).to_dict(), 503
    except FileNotFoundError:
        return make_error_response(
            ErrorCode.DATASET_NOT_FOUND,
            request.path,
            {"group": group, "input_id": input_id},
        ).to_dict(), 404

    return jsonify({"filename": filename, "content": content})
