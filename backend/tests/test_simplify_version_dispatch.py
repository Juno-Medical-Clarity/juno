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


class SimplifyVersionDispatchTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_form_version_v1_1_dispatches_v1_1(self, _verify_token):
        with patch("routes.simplify.simplify_v1_1", return_value={"version": "v1-1"}) as selected:
            response = self.client.post(
                "/simplify",
                headers={"Authorization": "Bearer token"},
                data={"version": "v1-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"version": "v1-1"})
        selected.assert_called_once_with()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_json_version_v1_2_dispatches_v1_2(self, _verify_token):
        with patch("routes.simplify.simplify_v1_2", return_value={"version": "v1-2"}) as selected:
            response = self.client.post(
                "/simplify",
                headers={"Authorization": "Bearer token"},
                json={"version": "v1-2"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"version": "v1-2"})
        selected.assert_called_once_with()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_omitted_version_uses_default_version(self, _verify_token):
        with patch("routes.simplify.SIMPLIFY_DEFAULT_VERSION", "v1-1"), patch(
            "routes.simplify.simplify_v1_1", return_value={"version": "default"}
        ) as selected:
            response = self.client.post(
                "/simplify",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"version": "default"})
        selected.assert_called_once_with()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_invalid_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/simplify",
            headers={"Authorization": "Bearer token"},
            json={"version": "v2"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version 'v2'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_old_version_endpoints_return_404(self, _verify_token):
        for path in ("/simplify/v1", "/simplify/v1-1", "/simplify/v1-2"):
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    headers={"Authorization": "Bearer token"},
                )

                self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
