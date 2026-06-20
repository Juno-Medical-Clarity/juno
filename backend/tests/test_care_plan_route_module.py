import json
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
from models.care_plan import CarePlan
from models.grading import Grading
from models.input import Input


def create_app():
    app = Flask(__name__)
    app.register_blueprint(care_plan_module.care_plan_bp)
    return app


def parse_sse_chunks(chunks):
    events = []
    for chunk in chunks:
        if not isinstance(chunk, str):
            continue
        for block in chunk.strip().split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block.removeprefix("data: ")))
    return events


def fake_care_plan(summary="route composed"):
    return CarePlan.from_pipeline_result("1.2", {"summary": summary})


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
                    care_plan_module._sse({"step": 2, "status": "done"}),
                    (
                        "__result__",
                        fake_care_plan("from registry"),
                        Grading(enabled=False),
                        "raw note",
                        "clarified note",
                        None,
                        None,
                    ),
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
                events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

        registry_pipeline.assert_called_once()
        self.assertEqual(registry_pipeline.call_args.args[0], "plain note")
        self.assertEqual(registry_pipeline.call_args.args[1].pipeline_version, "v1-test")
        self.assertEqual(registry_pipeline.call_args.kwargs, {"grading_enabled": False})
        hard_coded_pipeline.assert_not_called()
        self.assertEqual(events[-1]["data"]["care_plan"]["summary"], "from registry")

    def test_care_plan_stream_without_session_id_does_not_fall_back_to_user_id(self):
        app = Flask(__name__)
        resolved = care_plan_module.ResolvedInput(
            text="plain note",
            source_description="doc:abc",
            source_filename="note.txt",
            source_kind="doc_id",
        )
        pipeline = MagicMock(
            return_value=iter(
                [
                    (
                        "__result__",
                        fake_care_plan("no user fallback"),
                        Grading(enabled=False),
                        "raw note",
                        "clarified note",
                        None,
                        None,
                    )
                ]
            )
        )

        with app.test_request_context("/care_plan", json={"grading_enabled": False}):
            with patch.object(care_plan_module, "PIPELINES", {"v1-test": pipeline}), patch.object(
                care_plan_module, "_resolve_input", return_value=resolved
            ):
                events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

        self.assertEqual(pipeline.call_args.args[1].session_id, "")
        self.assertEqual(events[-1]["data"]["metrics"]["session_id"], "")

    def test_care_plan_stream_rejects_pipeline_result_sse_without_sentinel(self):
        app = Flask(__name__)
        resolved = care_plan_module.ResolvedInput(
            text="plain note",
            source_description="doc:abc",
            source_filename="note.txt",
            source_kind="doc_id",
        )
        pipeline = MagicMock(
            return_value=iter(
                [
                    care_plan_module._sse({"step": 2, "status": "done"}),
                    care_plan_module._sse(
                        {"step": "result", "data": {"care_plan": {"summary": "bypassed route"}}}
                    ),
                ]
            )
        )

        with app.test_request_context("/care_plan", json={"grading_enabled": False}):
            g.session_id = "session-1"
            with patch.object(care_plan_module, "PIPELINES", {"v1-test": pipeline}), patch.object(
                care_plan_module, "_resolve_input", return_value=resolved
            ), patch.object(
                care_plan_module, "save_care_plan_output"
            ) as save_output:
                events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

        self.assertEqual(events[-1]["step"], "error")
        self.assertNotIn("data", events[-1])
        self.assertNotIn("bypassed route", json.dumps(events))
        save_output.assert_not_called()

    def test_care_plan_stream_composes_single_payload_and_saves_same_dict_for_non_doc_id(self):
        app = Flask(__name__)
        resolved = care_plan_module.ResolvedInput(
            text="resolved note",
            source_description="uploaded.pdf",
            source_filename="uploaded.pdf",
            combined_pdf_bytes=b"%PDF-1.4",
            source_kind="upload",
        )
        input_model = Input.from_doc_id("resolved-input")
        grading = Grading(enabled=False)
        step_chunk = care_plan_module._sse({"step": 2, "status": "done"})
        pipeline = MagicMock(
            return_value=iter(
                [
                    step_chunk,
                    (
                        "__result__",
                        fake_care_plan("saved stream"),
                        grading,
                        "raw note",
                        "clarified note",
                        {"before": 1},
                        {"after": 2},
                    ),
                ]
            )
        )
        emitted_result_payloads = []
        original_sse = care_plan_module._sse

        def capture_result_payload(payload):
            if payload.get("step") == "result":
                emitted_result_payloads.append(payload["data"])
            return original_sse(payload)

        with app.test_request_context("/care_plan", json={"grading_enabled": False}):
            g.session_id = "session-1"
            with patch.object(care_plan_module, "PIPELINES", {"v1-test": pipeline}), patch.object(
                care_plan_module, "_resolve_input", return_value=resolved
            ), patch.object(
                care_plan_module, "_input_model_from_resolved", return_value=input_model
            ), patch.object(
                care_plan_module, "upload_combined_pdf", return_value="gs://bucket/uploaded.pdf"
            ), patch.object(
                care_plan_module, "save_care_plan_output", return_value="saved-123"
            ) as save_output, patch.object(
                care_plan_module, "_sse", side_effect=capture_result_payload
            ):
                events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

        result_payload = events[-1]
        final_payload = result_payload["data"]
        self.assertEqual(result_payload["step"], "result")
        self.assertIn("care_plan", final_payload)
        self.assertNotIn("simplified_care_plan", final_payload)
        self.assertEqual(final_payload["care_plan"]["summary"], "saved stream")
        self.assertEqual(final_payload["input"], input_model.to_dict())
        self.assertEqual(final_payload["metrics"]["pipeline_version"], "v1-test")
        self.assertEqual(final_payload["metrics"]["input_type"], "upload")
        self.assertEqual(final_payload["metrics"]["saved_id"], "saved-123")
        self.assertEqual(final_payload["before_score"], {"before": 1})
        self.assertEqual(final_payload["after_score"], {"after": 2})
        self.assertIs(save_output.call_args.kwargs["output_data"], emitted_result_payloads[-1])

    def test_care_plan_stream_doc_id_composes_result_without_saving(self):
        app = Flask(__name__)
        resolved = care_plan_module.ResolvedInput(
            text="stored note",
            source_description="doc:abc",
            source_filename="stored.txt",
            source_kind="doc_id",
        )
        input_model = Input.from_doc_id("abc")
        pipeline = MagicMock(
            return_value=iter(
                [
                    (
                        "__result__",
                        fake_care_plan("stored stream"),
                        Grading(enabled=False),
                        "raw note",
                        "clarified note",
                        None,
                        None,
                    )
                ]
            )
        )

        with app.test_request_context("/care_plan", json={"grading_enabled": False}):
            g.session_id = "session-1"
            with patch.object(care_plan_module, "PIPELINES", {"v1-test": pipeline}), patch.object(
                care_plan_module, "_resolve_input", return_value=resolved
            ), patch.object(
                care_plan_module, "_input_model_from_resolved", return_value=input_model
            ), patch.object(
                care_plan_module, "save_care_plan_output"
            ) as save_output:
                events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

        final_payload = events[-1]["data"]
        self.assertEqual(events[-1]["step"], "result")
        self.assertEqual(final_payload["care_plan"]["summary"], "stored stream")
        self.assertEqual(final_payload["input"], input_model.to_dict())
        self.assertIsNone(final_payload["metrics"]["saved_id"])
        save_output.assert_not_called()

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
