import sys
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


class CarePlanVersionDispatchTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_v1_version_returns_400(self, _verify_token):
        """v1 is no longer a valid version — must return 400."""
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": "v1", "text": "note"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version 'v1'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_v1_1_version_returns_400(self, _verify_token):
        """v1-1 is no longer a valid version — must return 400."""
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": "v1-1", "text": "note"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version 'v1-1'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_invalid_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": "v2"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version 'v2'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_json_list_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": ["v1-2"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version '['v1-2']'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_form_empty_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={"version": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version ''"})

    def test_old_simplify_endpoints_return_404(self):
        """All /simplify* paths are hard-cut — no alias, unconditional 404."""
        for path in ("/simplify", "/simplify/v1", "/simplify/v1-1", "/simplify/v1-2"):
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    headers={"Authorization": "Bearer token"},
                )
                self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
