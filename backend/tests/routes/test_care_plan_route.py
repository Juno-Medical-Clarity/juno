import json
import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from routes import care_plan as care_plan_module
from models.care_plan import CarePlan
from models.grading import Grading
from models.input import Input

BACKEND_DIR = Path(__file__).resolve().parents[2]


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


def test_care_plan_route_module_exports_task_1_symbols():
    module_path = BACKEND_DIR / "routes" / "care_plan.py"
    spec = importlib.util.spec_from_file_location("care_plan_route_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.care_plan_bp.name == "care_plan"
    assert callable(module.run_care_plan_pipeline)
    assert callable(module._care_plan_stream)
    assert callable(module.create_care_plan)
    assert "simplify_v1_2" not in vars(module)


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_omitted_version_defaults_to_sse_stream(_verify_token, client):
    with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.content_type == "text/event-stream"
    stream.assert_called_once_with("user-1", "v1-2")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_accepts_json_version_v1_2(_verify_token, client):
    with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            json={"version": "v1-2"},
        )

    assert response.status_code == 200
    stream.assert_called_once_with("user-1", "v1-2")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_accepts_form_version_v1_2(_verify_token, client):
    with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
        response = client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={"version": "v1-2"},
        )

    assert response.status_code == 200
    stream.assert_called_once_with("user-1", "v1-2")


@pytest.mark.parametrize("version", ["v1", "v1-1"])
@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_rejects_unknown_versions(_verify_token, version, client):
    response = client.post(
        "/care_plan",
        headers={"Authorization": "Bearer token"},
        json={"version": version},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": f"Unknown version '{version}'"}


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_rejects_non_string_version(_verify_token, client):
    response = client.post(
        "/care_plan",
        headers={"Authorization": "Bearer token"},
        json={"version": ["v1-2"]},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Unknown version '['v1-2']'"}


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_care_plan_ignores_query_string_version(_verify_token, client):
    with patch.object(care_plan_module, "_care_plan_stream", return_value=iter(["data: {}\n\n"])) as stream:
        response = client.post(
            "/care_plan?version=v1",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    stream.assert_called_once_with("user-1", "v1-2")


def test_care_plan_stream_uses_registry_pipeline_for_version():
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
    assert registry_pipeline.call_args.args[0] == "plain note"
    assert registry_pipeline.call_args.args[1].pipeline_version == "v1-test"
    assert registry_pipeline.call_args.kwargs == {"grading_enabled": False}
    hard_coded_pipeline.assert_not_called()
    assert events[-1]["data"]["care_plan"]["summary"] == "from registry"


def test_care_plan_stream_without_session_id_does_not_fall_back_to_user_id():
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
                )
            ]
        )
    )

    with app.test_request_context("/care_plan", json={"grading_enabled": False}):
        with patch.object(care_plan_module, "PIPELINES", {"v1-test": pipeline}), patch.object(
            care_plan_module, "_resolve_input", return_value=resolved
        ):
            events = parse_sse_chunks(care_plan_module._care_plan_stream("user-1", "v1-test"))

    assert pipeline.call_args.args[1].session_id == ""
    assert events[-1]["data"]["metrics"]["session_id"] == ""


def test_care_plan_stream_rejects_pipeline_result_sse_without_sentinel():
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

    assert events[-1]["step"] == "error"
    assert "data" not in events[-1]
    assert "bypassed route" not in json.dumps(events)
    save_output.assert_not_called()


def test_care_plan_stream_composes_single_payload_and_saves_same_dict_for_non_doc_id():
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
    assert result_payload["step"] == "result"
    assert "care_plan" in final_payload
    assert "simplified_care_plan" not in final_payload
    assert final_payload["care_plan"]["summary"] == "saved stream"
    assert final_payload["input"] == input_model.to_dict()
    assert final_payload["metrics"]["pipeline_version"] == "v1-test"
    assert final_payload["metrics"]["input_type"] == "upload"
    assert final_payload["metrics"]["saved_id"] == "saved-123"
    assert "before_score" not in final_payload
    assert "after_score" not in final_payload
    assert save_output.call_args.kwargs["output_data"] is emitted_result_payloads[-1]


def test_care_plan_stream_doc_id_composes_result_without_saving():
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
    assert events[-1]["step"] == "result"
    assert final_payload["care_plan"]["summary"] == "stored stream"
    assert final_payload["input"] == input_model.to_dict()
    assert final_payload["metrics"]["saved_id"] is None
    save_output.assert_not_called()


def test_config_exposes_only_care_plan_default_version():
    import config

    legacy_default_version_name = "SIMPLIFY" + "_DEFAULT_VERSION"
    try:
        with patch.dict("os.environ", {legacy_default_version_name: "v1"}, clear=True), patch(
            "dotenv.load_dotenv"
        ):
            importlib.reload(config)

        assert not hasattr(config, legacy_default_version_name)
        assert config.CARE_PLAN_DEFAULT_VERSION == "v1-2"
    finally:
        importlib.reload(config)
