from flask import Blueprint, jsonify, request

from routes.care_plan import _extract_text_from_bytes
from errors import make_error_response, ErrorCode
from utils.firebase import verify_firebase_token
from utils.preset_data import list_datasets, list_athena_sources, read_dataset_file, GCSFetchRequired

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/care_plan/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id: str):
    _ = user_id
    return jsonify({
        "datasets": list_datasets(),
        "athena_sources": list_athena_sources(),
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
