import sys
import unittest
from pathlib import Path

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import all_blueprints


def create_app():
    app = Flask(__name__)
    for blueprint in all_blueprints:
        app.register_blueprint(blueprint)
    return app


class SimplifyAuthTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_simplify_routes_require_authorization_header(self):
        for path in ("/simplify", "/simplify/v1", "/simplify/v1-1", "/simplify/v1-2"):
            with self.subTest(path=path):
                response = self.client.post(path)

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.get_json(), {"error": "No authorization header"})


if __name__ == "__main__":
    unittest.main()
