from flask import Blueprint, jsonify

from routes.care_plan import _extract_text_from_bytes
from utils.auth import verify_firebase_token
from utils.preset_data import list_datasets, read_dataset_file

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/care_plan/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id: str):
    _ = user_id
    return jsonify({"datasets": list_datasets()})


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
    except FileNotFoundError:
        return jsonify({"error": "Not found"}), 404

    return jsonify({"filename": filename, "content": content})
