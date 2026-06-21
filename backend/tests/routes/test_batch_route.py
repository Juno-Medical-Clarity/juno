import json
from unittest.mock import MagicMock, call, patch

import pytest


def parse_sse(response_or_text):
    text = response_or_text
    if hasattr(response_or_text, "get_data"):
        text = response_or_text.get_data(as_text=True)
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: ")
        events.append(json.loads(block.removeprefix("data: ")))
    return events


def fixed_output(input_label, group="GroupA", batch_group_id=None):
    return {
        "metrics": {
            "session_id": "session-1",
            "pipeline_version": "v1-2",
            "input_type": "batch_dataset",
            "created_at": "2026-06-16T00:00:00+00:00",
        },
        "input": {
            "mode": "text",
            "text": "executor placeholder",
            "files": [],
            "doc_id": None,
            "dataset_group": group,
            "dataset_input": input_label,
            "selected_files": None,
            "batch_group_id": batch_group_id,
        },
        "grading": {},
        "care_plan": {
            "version": "1.2",
            "reason_for_visit": [{"reason": f"Visit {input_label}"}],
        },
    }


def test_batch_route_requires_authorization_header(client):
    response = client.post("/care_plan/batch", json={})

    assert response.status_code == 401
    assert response.get_json() == {"error": "No authorization header"}


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_runs_in_sorted_order_expands_all_and_saves_metadata(_verify_token, client):
    datasets = [
        {"group": "GroupB", "inputs": ["input-2"], "files": ["notes.txt"]},
        {"group": "GroupA", "inputs": ["input-2", "input-1"], "files": ["notes.txt", "transcript.txt"]},
    ]
    read_bytes = {
        ("GroupA", "input-1", "notes.txt"): b"GroupA input-1 notes",
        ("GroupA", "input-1", "transcript.txt"): b"GroupA input-1 transcript",
        ("GroupA", "input-2", "notes.txt"): b"GroupA input-2 notes",
        ("GroupA", "input-2", "transcript.txt"): b"GroupA input-2 transcript",
        ("GroupB", "input-2", "notes.txt"): b"GroupB input-2 notes",
    }
    executor_calls = []

    def read_dataset_file(group, input_id, filename):
        return read_bytes[(group, input_id, filename)]

    def run_pipeline(text, metrics, grading_enabled):
        executor_calls.append((text, metrics, grading_enabled))
        # text format: "\n\n--- notes.txt ---\n\nGroupA input-1 notes..."
        parts = text.splitlines()[4].split(" ")
        group = parts[0]
        input_label = parts[1]
        batch_group_id = f"{group}-20260616153012"
        yield f"data: {json.dumps({'step': 2, 'status': 'active'})}\n\n"
        yield f"data: {json.dumps({'step': 'result', 'data': fixed_output(input_label, group=group, batch_group_id=batch_group_id)})}\n\n"

    with (
        patch("routes.batch._batch_timestamp", return_value="20260616153012", create=True),
        patch("routes.batch.list_datasets", return_value=datasets, create=True) as list_datasets,
        patch("routes.batch.read_dataset_file", side_effect=read_dataset_file, create=True) as read_file,
        patch("routes.batch.run_care_plan_pipeline", side_effect=run_pipeline, create=True) as executor,
        patch(
            "routes.batch.save_care_plan_output",
            side_effect=["saved-a1", "saved-a2", "saved-b2"],
            create=True,
        ) as save_output,
    ):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": "v1-2",
                "grading_enabled": True,
                "selections": [
                    {"group": "GroupB", "inputs": ["input-2"], "files": ["notes.txt"]},
                    {"group": "GroupA", "inputs": "all", "files": ["notes.txt", "transcript.txt"]},
                ],
            },
            headers={"Authorization": "Bearer token"},
        )
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    list_datasets.assert_called_once_with()
    assert read_file.call_args_list == [
        call("GroupA", "input-1", "notes.txt"),
        call("GroupA", "input-1", "transcript.txt"),
        call("GroupA", "input-2", "notes.txt"),
        call("GroupA", "input-2", "transcript.txt"),
        call("GroupB", "input-2", "notes.txt"),
    ]
    assert executor.call_count == 3
    assert [call_args.args[0] for call_args in executor.call_args_list] == [
        "\n\n--- notes.txt ---\n\nGroupA input-1 notes\n\n--- transcript.txt ---\n\nGroupA input-1 transcript",
        "\n\n--- notes.txt ---\n\nGroupA input-2 notes\n\n--- transcript.txt ---\n\nGroupA input-2 transcript",
        "\n\n--- notes.txt ---\n\nGroupB input-2 notes",
    ]
    assert all(call_args.args[2] is True for call_args in executor.call_args_list)
    assert [entry[1].input_type for entry in executor_calls] == ["batch_dataset"] * 3
    assert [entry[1].pipeline_version for entry in executor_calls] == ["v1-2"] * 3

    save_calls = save_output.call_args_list
    assert len(save_calls) == 3
    assert [(c.kwargs["dataset_group"], c.kwargs["batch_group_id"]) for c in save_calls] == [
        ("GroupA", "GroupA-20260616153012"),
        ("GroupA", "GroupA-20260616153012"),
        ("GroupB", "GroupB-20260616153012"),
    ]
    assert [c.kwargs["source_filename"] for c in save_calls] == [
        "notes.txt, transcript.txt", "notes.txt, transcript.txt", "notes.txt"
    ]

    events = parse_sse(response_text)
    assert events[0]["step"] == "batch_progress"
    assert events[0]["status"] == "active"
    assert events[0]["group"] == "GroupA"
    assert events[0]["input"] == "input-1"
    assert events[0]["index"] == 1
    assert events[0]["total"] == 3
    nested = [event for event in events if event.get("event", {}).get("step") == 2]
    assert [event["input"] for event in nested] == ["input-1", "input-2", "input-2"]

    final = events[-1]
    assert final["step"] == "batch_result"
    assert final["data"]["batch_group_ids"] == {
        "GroupA": "GroupA-20260616153012",
        "GroupB": "GroupB-20260616153012",
    }
    assert [output["metrics"]["saved_id"] for output in final["data"]["outputs"]] == [
        "saved-a1", "saved-a2", "saved-b2"
    ]
    assert [output["input"]["dataset_group"] for output in final["data"]["outputs"]] == [
        "GroupA", "GroupA", "GroupB"
    ]
    assert [output["input"]["batch_group_id"] for output in final["data"]["outputs"]] == [
        "GroupA-20260616153012", "GroupA-20260616153012", "GroupB-20260616153012"
    ]


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_selection_errors_stream_sse_error_not_500(_verify_token, client):
    with (
        patch("routes.batch._batch_timestamp", return_value="20260616153012", create=True),
        patch("routes.batch.list_datasets", return_value=[], create=True),
    ):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": "v1-2",
                "grading_enabled": False,
                "selections": [
                    {"group": "MissingGroup", "inputs": ["input-1"], "files": ["notes.txt"]},
                ],
            },
            headers={"Authorization": "Bearer token"},
        )
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert parse_sse(response_text) == [{"step": "error", "error": "Dataset group not found: MissingGroup"}]


@pytest.mark.parametrize("version", ["v1", "v1-1"])
@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_rejects_unknown_version_with_sse_error(_verify_token, version, client):
    """Legacy versions v1 and v1-1 are no longer supported — must SSE-error."""
    with patch("routes.batch.list_datasets", return_value=[]):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": version,
                "grading_enabled": False,
                "selections": [
                    {"group": "GroupA", "inputs": ["input-1"], "files": ["notes.txt"]},
                ],
            },
            headers={"Authorization": "Bearer token"},
        )
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    events = parse_sse(response_text)
    assert events[0]["step"] == "error"
    assert version in events[0]["error"]


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_rejects_too_many_runs_before_pipeline_work(_verify_token, client):
    datasets = [{"group": "GroupA", "inputs": ["input-1", "input-2", "input-3"], "files": ["notes.txt"]}]

    with (
        patch("routes.batch.MAX_BATCH_RUNS", 2),
        patch("routes.batch.list_datasets", return_value=datasets) as list_datasets,
        patch("routes.batch._batch_timestamp") as batch_timestamp,
        patch("routes.batch.read_dataset_file") as read_file,
        patch("routes.batch.run_care_plan_pipeline") as executor,
        patch("routes.batch.save_care_plan_output") as save_output,
    ):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": "v1-2",
                "grading_enabled": False,
                "selections": [
                    {"group": "GroupA", "inputs": "all", "files": ["notes.txt"]},
                ],
            },
            headers={"Authorization": "Bearer token"},
        )
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert parse_sse(response_text) == [{"step": "error", "error": "Batch request exceeds maximum of 2 runs"}]
    list_datasets.assert_called_once_with()
    batch_timestamp.assert_not_called()
    read_file.assert_not_called()
    executor.assert_not_called()
    save_output.assert_not_called()


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_save_care_plan_output_called_without_input_pdf_gcs(_verify_token, client):
    """
    Regression: batch route must never pass input_pdf_gcs kwarg to save_care_plan_output.
    This kwarg was removed in SP-11 Task 1; passing it would raise TypeError.
    """
    datasets = [{"group": "GroupA", "inputs": ["input-1"], "files": ["notes.txt"]}]
    read_bytes = {("GroupA", "input-1", "notes.txt"): b"GroupA input-1 notes"}

    def read_dataset_file(group, input_id, filename):
        return read_bytes[(group, input_id, filename)]

    def run_pipeline(text, metrics, grading_enabled, **kwargs):
        yield f"data: {json.dumps({'step': 'result', 'data': fixed_output('input-1', group='GroupA', batch_group_id='GroupA-20260616153012')})}\n\n"

    save_kwargs_list = []

    def capture_save(**kwargs):
        save_kwargs_list.append(kwargs)
        return "saved-regress"

    fake_g = MagicMock()
    fake_g.session_id = "session-1"
    fake_g.user_id = "user-1"

    with (
        patch("routes.batch._batch_timestamp", return_value="20260616153012", create=True),
        patch("routes.batch.list_datasets", return_value=datasets, create=True),
        patch("routes.batch.read_dataset_file", side_effect=read_dataset_file, create=True),
        patch("routes.batch.run_care_plan_pipeline", side_effect=run_pipeline, create=True),
        patch("routes.batch.save_care_plan_output", side_effect=capture_save, create=True),
        patch("routes.batch.g", fake_g),
    ):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": "v1-2",
                "grading_enabled": False,
                "selections": [{"group": "GroupA", "inputs": ["input-1"], "files": ["notes.txt"]}],
            },
            headers={"Authorization": "Bearer token"},
        )
        # Read the response body inside the patch context so streaming finishes
        # while all mocks are still active.
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    events = parse_sse(response_text)
    assert not any(e.get("step") == "error" for e in events), f"Unexpected error events: {events}"
    assert len(save_kwargs_list) == 1
    assert "input_pdf_gcs" not in save_kwargs_list[0]


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
def test_batch_continues_after_per_input_failures(_verify_token, client):
    datasets = [
        {
            "group": "GroupA",
            "inputs": ["empty", "pipeline-error", "missing-result", "success"],
            "files": ["notes.txt"],
        },
    ]
    read_bytes = {
        ("GroupA", "empty", "notes.txt"): b"   ",
        ("GroupA", "pipeline-error", "notes.txt"): b"pipeline-error notes",
        ("GroupA", "missing-result", "notes.txt"): b"missing-result notes",
        ("GroupA", "success", "notes.txt"): b"success notes",
    }

    def read_dataset_file(group, input_id, filename):
        return read_bytes[(group, input_id, filename)]

    def run_pipeline(text, metrics, grading_enabled):
        if "pipeline-error" in text:
            yield f"data: {json.dumps({'step': 'error', 'error': 'Pipeline failed for input'})}\n\n"
            return
        if "missing-result" in text:
            yield f"data: {json.dumps({'step': 2, 'status': 'done'})}\n\n"
            return
        yield f"data: {json.dumps({'step': 'result', 'data': fixed_output('success')})}\n\n"

    with (
        patch("routes.batch._batch_timestamp", return_value="20260616153012"),
        patch("routes.batch.list_datasets", return_value=datasets),
        patch("routes.batch.read_dataset_file", side_effect=read_dataset_file),
        patch("routes.batch.run_care_plan_pipeline", side_effect=run_pipeline) as executor,
        patch("routes.batch.save_care_plan_output", return_value="saved-success") as save_output,
    ):
        response = client.post(
            "/care_plan/batch",
            json={
                "version": "v1-2",
                "grading_enabled": False,
                "selections": [
                    {
                        "group": "GroupA",
                        "inputs": ["empty", "pipeline-error", "missing-result", "success"],
                        "files": ["notes.txt"],
                    },
                ],
            },
            headers={"Authorization": "Bearer token"},
        )
        response_text = response.get_data(as_text=True)

    assert response.status_code == 200
    events = parse_sse(response_text)
    assert not [event for event in events if event["step"] == "error"]

    failures = [event for event in events if event["step"] == "batch_progress" and event.get("status") == "error"]
    assert [(event["input"], event["error"]) for event in failures] == [
        ("empty", "Input appears to be empty or unreadable: GroupA/empty"),
        ("missing-result", "Pipeline did not return a result: GroupA/missing-result"),
        ("pipeline-error", "Pipeline failed for input"),
    ]
    assert [event["index"] for event in failures] == [1, 2, 3]
    assert [event["total"] for event in failures] == [4, 4, 4]

    final = events[-1]
    assert final["step"] == "batch_result"
    assert [output["metrics"]["saved_id"] for output in final["data"]["outputs"]] == ["saved-success"]
    assert final["data"]["outputs"][0]["input"]["dataset_input"] == "success"
    assert executor.call_count == 3
    save_output.assert_called_once()
