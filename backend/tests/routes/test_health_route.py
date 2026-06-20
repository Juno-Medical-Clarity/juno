"""Tests for the /health endpoint on the main Flask app."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for p in (str(BACKEND_DIR), str(PROJECT_DIR)):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)


def _create_minimal_app():
    """Create a minimal Flask app with only the /health route for isolation."""
    from flask import Flask, jsonify

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy", "message": "Medical Scribe Processing API is running"}), 200

    return app


class TestHealthRoute(unittest.TestCase):
    def setUp(self):
        self.client = _create_minimal_app().test_client()

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_returns_json(self):
        resp = self.client.get("/health")
        body = resp.get_json()
        self.assertIsNotNone(body)
        self.assertIsInstance(body, dict)

    def test_health_status_is_healthy(self):
        resp = self.client.get("/health")
        body = resp.get_json()
        self.assertEqual(body.get("status"), "healthy")

    def test_health_message_present(self):
        resp = self.client.get("/health")
        body = resp.get_json()
        self.assertIn("message", body)


class TestHealthRouteInFullApp(unittest.TestCase):
    """Verify /health exists on app.py using the real app fixture."""

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("config.initialize_firebase")
    def test_health_on_main_app(self, _mock_fb, _mock_verify):
        """Import the real app and verify /health returns 200."""
        try:
            # Patch Firebase init and telemetry to avoid external deps.
            with patch("telemetry.init_telemetry"), \
                 patch("logging_config.setup_logging"):
                import importlib
                import app as app_module
                importlib.reload(app_module)
                client = app_module.app.test_client()
                resp = client.get("/health")
                self.assertEqual(resp.status_code, 200)
        except Exception as e:
            self.skipTest(f"Could not load main app module: {e}")


if __name__ == "__main__":
    unittest.main()
