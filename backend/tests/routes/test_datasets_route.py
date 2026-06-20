import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def dataset_client(client, monkeypatch):
    """Fixture providing a client with a temp preset-data directory wired up."""
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)

    input_1 = root / "DocConv" / "input-1"
    input_2 = root / "DocConv" / "input-2"
    input_1.mkdir(parents=True)
    input_2.mkdir(parents=True)

    (input_1 / "notes.txt").write_bytes(b"input 1 notes")
    (input_1 / "transcript.txt").write_bytes(b"input 1 transcript")
    (input_2 / "notes.txt").write_bytes(b"input 2 notes")
    (input_2 / "transcript.txt").write_bytes(b"input 2 transcript")

    from utils import preset_data
    monkeypatch.setattr(preset_data, "PRESET_DATA_ROOT", root)

    yield client, root

    temp_dir.cleanup()


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_list_datasets_returns_dataset_metadata(_verify_token, dataset_client):
    client, root = dataset_client
    response = client.get(
        "/care_plan/datasets",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "datasets": [
            {
                "group": "DocConv",
                "inputs": ["input-1", "input-2"],
                "files": ["notes.txt", "transcript.txt"],
            }
        ]
    }


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_preview_dataset_file_returns_decoded_content(_verify_token, dataset_client):
    client, root = dataset_client
    response = client.get(
        "/care_plan/datasets/DocConv/input-2/transcript.txt",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"filename": "transcript.txt", "content": "input 2 transcript"}


@pytest.mark.parametrize("path", [
    "/care_plan/datasets/DocConv/input-1/missing.txt",
    "/care_plan/datasets/../input-1/notes.txt",
    "/care_plan/datasets/DocConv/../notes.txt",
])
@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_preview_dataset_file_maps_missing_and_traversal_to_404(_verify_token, path, dataset_client):
    # These paths reach our handler (group/input/filename all parse as non-slash strings)
    # and are rejected by our file-existence check with a JSON 404.
    client, root = dataset_client
    response = client.get(path, headers={"Authorization": "Bearer token"})
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found"}
    assert str(root) not in response.get_data(as_text=True)


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_preview_dataset_file_url_encoded_traversal_returns_404(_verify_token, dataset_client):
    # URL-encoded slashes (%2F) in the filename segment: Flask decodes them before routing,
    # producing a path with literal slashes. <string:filename> rejects slashes, so Flask
    # returns a 404 before our handler is even invoked — a stronger rejection than our own.
    client, root = dataset_client
    url_encoded_traversal = "/care_plan/datasets/DocConv/input-1/..%2F..%2F..%2Fetc%2Fpasswd"
    response = client.get(url_encoded_traversal, headers={"Authorization": "Bearer token"})
    assert response.status_code == 404
    assert str(root) not in response.get_data(as_text=True)


@pytest.mark.parametrize("path", [
    "/care_plan/datasets",
    "/care_plan/datasets/DocConv/input-1/notes.txt",
])
def test_dataset_routes_require_authorization_header(path, dataset_client):
    client, root = dataset_client
    response = client.get(path)

    assert response.status_code == 401
    assert response.get_json() == {"error": "No authorization header"}
