import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from routes import all_blueprints


def create_app():
    app = Flask(__name__)
    for blueprint in all_blueprints:
        app.register_blueprint(blueprint)
    return app


class DatasetRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        input_1 = self.root / "DocConv" / "input-1"
        input_2 = self.root / "DocConv" / "input-2"
        input_1.mkdir(parents=True)
        input_2.mkdir(parents=True)

        (input_1 / "notes.txt").write_bytes(b"input 1 notes")
        (input_1 / "transcript.txt").write_bytes(b"input 1 transcript")
        (input_2 / "notes.txt").write_bytes(b"input 2 notes")
        (input_2 / "transcript.txt").write_bytes(b"input 2 transcript")

        from utils import preset_data

        self.preset_data = preset_data
        self.original_root = preset_data.PRESET_DATA_ROOT
        preset_data.PRESET_DATA_ROOT = self.root
        self.client = create_app().test_client()

    def tearDown(self):
        self.preset_data.PRESET_DATA_ROOT = self.original_root
        self.temp_dir.cleanup()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_list_datasets_returns_dataset_metadata(self, _verify_token):
        response = self.client.get(
            "/care_plan/datasets",
            headers={"Authorization": "Bearer token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "datasets": [
                    {
                        "group": "DocConv",
                        "inputs": ["input-1", "input-2"],
                        "files": ["notes.txt", "transcript.txt"],
                    }
                ]
            },
        )

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_preview_dataset_file_returns_decoded_content(self, _verify_token):
        response = self.client.get(
            "/care_plan/datasets/DocConv/input-2/transcript.txt",
            headers={"Authorization": "Bearer token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"filename": "transcript.txt", "content": "input 2 transcript"},
        )

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_preview_dataset_file_maps_missing_and_traversal_to_404(self, _verify_token):
        # These paths reach our handler (group/input/filename all parse as non-slash strings)
        # and are rejected by our file-existence check with a JSON 404.
        handler_rejected_paths = [
            "/care_plan/datasets/DocConv/input-1/missing.txt",
            "/care_plan/datasets/../input-1/notes.txt",
            "/care_plan/datasets/DocConv/../notes.txt",
        ]
        for path in handler_rejected_paths:
            with self.subTest(path=path):
                response = self.client.get(path, headers={"Authorization": "Bearer token"})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.get_json(), {"error": "Not found"})
                self.assertNotIn(str(self.root), response.get_data(as_text=True))

        # URL-encoded slashes (%2F) in the filename segment: Flask decodes them before routing,
        # producing a path with literal slashes. <string:filename> rejects slashes, so Flask
        # returns a 404 before our handler is even invoked — a stronger rejection than our own.
        url_encoded_traversal = "/care_plan/datasets/DocConv/input-1/..%2F..%2F..%2Fetc%2Fpasswd"
        with self.subTest(path=url_encoded_traversal):
            response = self.client.get(url_encoded_traversal, headers={"Authorization": "Bearer token"})
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(str(self.root), response.get_data(as_text=True))

    def test_dataset_routes_require_authorization_header(self):
        for path in (
            "/care_plan/datasets",
            "/care_plan/datasets/DocConv/input-1/notes.txt",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json(), {"error": "No authorization header"})


if __name__ == "__main__":
    unittest.main()
