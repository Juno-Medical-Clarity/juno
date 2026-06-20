import importlib
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask, g

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from routes import care_plan as care_plan_module


def create_app():
    app = Flask(__name__)
    app.register_blueprint(care_plan_module.care_plan_bp)
    return app


class CarePlanRouteModuleTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_care_plan_route_module_exports_task_1_symbols(self):
        module_path = BACKEND_DIR / "routes" / "care_plan.py"
        spec = importlib.util.spec_from_file_location("care_plan_route_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        self.assertEqual(module.care_plan_bp.name, "care_plan")
        self.assertTrue(callable(module.run_care_plan_pipeline))
        self.assertTrue(callable(module._care_plan_stream))
        self.assertTrue(callable(module.create_care_plan))
        self.assertNotIn("simplify_v1_2", vars(module))

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_omitted_version_defaults_to_sse_stream(self, _verify_token):
        with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/event-stream")
        stream.assert_called_once_with("user-1", "v1-2")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_accepts_json_version_v1_2(self, _verify_token):
        with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
                json={"version": "v1-2"},
            )

        self.assertEqual(response.status_code, 200)
        stream.assert_called_once_with("user-1", "v1-2")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_accepts_form_version_v1_2(self, _verify_token):
        with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
                data={"version": "v1-2"},
            )

        self.assertEqual(response.status_code, 200)
        stream.assert_called_once_with("user-1", "v1-2")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_rejects_unknown_versions(self, _verify_token):
        for version in ("v1", "v1-1"):
            with self.subTest(version=version):
                response = self.client.post(
                    "/care_plan",
                    headers={"Authorization": "Bearer token"},
                    json={"version": version},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": f"Unknown version '{version}'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_rejects_non_string_version(self, _verify_token):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": ["v1-2"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Unknown version '['v1-2']'"})

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_care_plan_ignores_query_string_version(self, _verify_token):
        with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
            response = self.client.post(
                "/care_plan?version=v1",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        stream.assert_called_once_with("user-1", "v1-2")

    def test_care_plan_stream_uses_registry_pipeline_for_version(self):
        app = Flask(__name__)
        resolved = care_plan_module.ResolvedInput(
            text="plain note",
            source_description="doc:abc",
            source_filename="note.txt",
            source_kind="doc_id",
        )
        registry_pipeline = MagicMock(
            return_value=iter(
                [
                    care_plan_module._sse(
                        {"step": "result", "data": {"care_plan": {"summary": "from registry"}}}
                    )
                ]
            )
        )

        with app.test_request_context("/care_plan", json={"grading_enabled": False}):
            g.session_id = "session-1"
            with patch.object(care_plan_module, "PIPELINES", {"v1-test": registry_pipeline}), patch.object(
                care_plan_module, "run_care_plan_pipeline"
            ) as hard_coded_pipeline, patch.object(
                care_plan_module, "_resolve_input", return_value=resolved
            ):
                events = list(care_plan_module._care_plan_stream("user-1", "v1-test"))

        registry_pipeline.assert_called_once()
        self.assertEqual(registry_pipeline.call_args.args[0], "plain note")
        self.assertEqual(registry_pipeline.call_args.args[1].pipeline_version, "v1-test")
        self.assertEqual(registry_pipeline.call_args.kwargs, {"grading_enabled": False})
        hard_coded_pipeline.assert_not_called()
        self.assertIn('"summary": "from registry"', events[-1])

    def test_care_plan_default_version_ignores_legacy_simplify_default_env(self):
        import config

        try:
            with patch.dict("os.environ", {"SIMPLIFY_DEFAULT_VERSION": "v1"}, clear=True), patch(
                "dotenv.load_dotenv"
            ):
                importlib.reload(config)

            self.assertEqual(config.SIMPLIFY_DEFAULT_VERSION, "v1")
            self.assertEqual(config.CARE_PLAN_DEFAULT_VERSION, "v1-2")
        finally:
            importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
