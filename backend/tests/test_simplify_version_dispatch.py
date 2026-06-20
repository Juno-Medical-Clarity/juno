import importlib
import os
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
        legacy_default_version_path = "routes.simplify." + "SIMPLIFY" + "_DEFAULT_VERSION"
        with patch(legacy_default_version_path, "v1-1"), patch(
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
    def test_omitted_version_uses_latest_default_without_route_monkeypatch(self, _verify_token):
        import config
        import routes.simplify as simplify_module

        try:
            with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
                importlib.reload(config)
                importlib.reload(simplify_module)

            app = Flask(__name__)
            app.register_blueprint(simplify_module.simplify_bp)
            client = app.test_client()

            with patch.object(
                simplify_module, "simplify_v1_2", return_value={"version": "latest"}
            ) as selected, patch.object(
                simplify_module, "simplify_v1_1", return_value={"version": "v1-1"}
            ) as v1_1, patch.object(
                simplify_module, "_simplify_document_v1", return_value={"version": "v1"}
            ) as v1:
                response = client.post(
                    "/simplify",
                    headers={"Authorization": "Bearer token"},
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"version": "latest"})
            selected.assert_called_once_with()
            v1_1.assert_not_called()
            v1.assert_not_called()
        finally:
            importlib.reload(config)
            importlib.reload(simplify_module)

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
    def test_json_list_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/simplify",
            headers={"Authorization": "Bearer token"},
            json={"version": ["v1-2"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version '['v1-2']'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_form_empty_version_returns_400(self, _verify_token):
        response = self.client.post(
            "/simplify",
            headers={"Authorization": "Bearer token"},
            data={"version": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version ''"})

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
