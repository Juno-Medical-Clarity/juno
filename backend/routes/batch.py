"""Batch dataset care plan route."""

import json
from datetime import datetime, timezone
from typing import Callable, Generator

from flask import Blueprint, Response, g, request, stream_with_context

from config import CARE_PLAN_DEFAULT_VERSION
from models.envelope import CarePlanInternal
from models.input import BatchDatasetInput
from models.metrics import Metrics
from utils.constants import Constants
from routes.care_plan import _extract_text_from_bytes, run_care_plan_pipeline
from utils.firebase import verify_firebase_token, save_care_plan_output
from utils.preset_data import list_datasets, read_dataset_file


batch_bp = Blueprint("batch", __name__)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _payload_from_sse(chunk: str) -> dict | None:
    if not chunk.startswith("data: "):
        return None
    return json.loads(chunk.removeprefix("data: ").strip())


def _batch_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _grading_enabled(raw_value) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _pipeline_for_version(version: str) -> Callable[[str, Metrics, bool], Generator[str | tuple, None, None]]:
    if version == Constants.PIPELINE_VERSION_V1_2:
        return run_care_plan_pipeline
    raise ValueError(f"Unknown version '{version}'")


def _resolve_requested_runs(selections: list[dict]) -> list[tuple[str, str, list[str]]]:
    datasets = list_datasets()
    datasets_by_group = {dataset["group"]: dataset for dataset in datasets}
    runs: list[tuple[str, str, list[str]]] = []

    for selection in selections:
        if not isinstance(selection, dict):
            raise ValueError("Each selection must be an object")

        group = selection.get("group")
        files = selection.get("files")
        selected_inputs = selection.get("inputs")
        if not isinstance(group, str) or not group:
            raise ValueError("Selection is missing group")
        if group not in datasets_by_group:
            raise ValueError(f"Dataset group not found: {group}")
        if not isinstance(files, list) or not files or not all(isinstance(name, str) and name for name in files):
            raise ValueError(f"Selection for {group} must include files")

        available_inputs = datasets_by_group[group].get("inputs", [])
        if selected_inputs == "all":
            input_ids = sorted(available_inputs)
        elif isinstance(selected_inputs, list) and all(isinstance(input_id, str) for input_id in selected_inputs):
            input_ids = sorted(selected_inputs)
        else:
            raise ValueError(f"Selection for {group} must include inputs")

        if not input_ids:
            raise ValueError(f"Selection for {group} has no inputs")
        unknown_inputs = [input_id for input_id in input_ids if input_id not in available_inputs]
        if unknown_inputs:
            raise FileNotFoundError(f"Dataset input not found: {group}/{unknown_inputs[0]}")

        for input_id in input_ids:
            runs.append((group, input_id, list(files)))

    return sorted(runs, key=lambda run: (run[0], run[1]))


def _combined_text_for_dataset_input(group: str, input_id: str, files: list[str]) -> str:
    parts: list[str] = []
    has_text = False
    for filename in files:
        file_bytes = read_dataset_file(group, input_id, filename)
        text = _extract_text_from_bytes(file_bytes, filename).strip()
        has_text = has_text or bool(text)
        parts.append(f"\n\n--- {filename} ---\n\n{text}")
    return "".join(parts) if has_text else ""


def _output_name(output_data: dict, group: str, input_id: str) -> str:
    try:
        reasons = output_data.get("care_plan", {}).get("reason_for_visit", [])
        if reasons and isinstance(reasons, list):
            reason = (reasons[0].get("reason") or "").strip()
            if reason:
                return reason.title()[:60]
    except Exception:
        pass
    return f"{group} {input_id}"[:60]


def _batch_progress_error(group: str, input_id: str, index: int, total: int, error: str) -> dict:
    return {
        "step": "batch_progress",
        "group": group,
        "input": input_id,
        "index": index,
        "total": total,
        "status": "error",
        "error": error,
    }


@batch_bp.route("/care_plan/batch", methods=["POST"])
@verify_firebase_token
def create_care_plan_batch(user_id: str):
    """Stream batch care plan progress via SSE."""
    def generate():
        try:
            body = request.get_json(silent=True) or {}
            if not isinstance(body, dict):
                yield _sse({"step": "error", "error": "Request body must be a JSON object"})
                return

            version = body.get("version", CARE_PLAN_DEFAULT_VERSION)
            if not isinstance(version, str) or version not in Constants.ALLOWED_VERSIONS:
                yield _sse({"step": "error", "error": f"Unknown version '{version}'"})
                return

            selections = body.get("selections")
            if not isinstance(selections, list) or not selections:
                yield _sse({"step": "error", "error": "Request must include selections"})
                return

            grading_enabled = _grading_enabled(body.get("grading_enabled", False))
            pipeline = _pipeline_for_version(version)
            runs = _resolve_requested_runs(selections)
            total = len(runs)
            if total > Constants.MAX_BATCH_RUNS:
                yield _sse({"step": "error", "error": f"Batch request exceeds maximum of {Constants.MAX_BATCH_RUNS} runs"})
                return

            timestamp = _batch_timestamp()
            batch_group_ids = {
                group: f"{group}-{timestamp}"
                for group in sorted({group for group, _, _ in runs})
            }
            outputs: list[dict] = []

            for index, (group, input_id, files) in enumerate(runs, start=1):
                batch_group_id = batch_group_ids[group]
                yield _sse({
                    "step": "batch_progress",
                    "group": group,
                    "input": input_id,
                    "index": index,
                    "total": total,
                    "status": "active",
                })

                try:
                    text = _combined_text_for_dataset_input(group, input_id, files)
                except Exception as exc:
                    yield _sse(_batch_progress_error(group, input_id, index, total, str(exc)))
                    continue
                if not text.strip():
                    yield _sse(_batch_progress_error(
                        group,
                        input_id,
                        index,
                        total,
                        f"Input appears to be empty or unreadable: {group}/{input_id}",
                    ))
                    continue

                metrics = Metrics.start(
                    session_id=g.session_id,
                    pipeline_version=version,
                    input_type="batch_dataset",
                )
                input_model = BatchDatasetInput(
                    text=text,
                    dataset_group=group,
                    dataset_input=input_id,
                    selected_files=files,
                    batch_group_id=batch_group_id,
                )

                result_data = None
                input_failed = False
                for chunk in pipeline(text, metrics, grading_enabled, is_batch=True, source_kind="batch_dataset"):
                    if isinstance(chunk, tuple) and chunk and chunk[0] == Constants.RESULT_SENTINEL:
                        _, care_plan, grading, _raw_text, _clarified_text = chunk
                        envelope = CarePlanInternal(
                            metrics=metrics,
                            input=input_model,
                            grading=grading,
                            care_plan=care_plan,
                        )
                        result_data = envelope.to_dict()
                        continue
                    payload = _payload_from_sse(chunk)
                    if not payload:
                        continue
                    if payload.get("step") == "result":
                        result_data = payload.get("data")
                        continue
                    if payload.get("step") == "error":
                        yield _sse(_batch_progress_error(
                            group,
                            input_id,
                            index,
                            total,
                            payload.get("error") or f"Pipeline failed: {group}/{input_id}",
                        ))
                        result_data = None
                        input_failed = True
                        break
                    yield _sse({
                        "step": "batch_progress",
                        "group": group,
                        "input": input_id,
                        "index": index,
                        "total": total,
                        "status": "pipeline",
                        "event": payload,
                    })

                if result_data is None:
                    if not input_failed:
                        yield _sse(_batch_progress_error(
                            group,
                            input_id,
                            index,
                            total,
                            f"Pipeline did not return a result: {group}/{input_id}",
                        ))
                    continue

                source_filename = ", ".join(files)
                saved_id = save_care_plan_output(
                    user_id=user_id,
                    name=_output_name(result_data, group, input_id),
                    source_filename=source_filename,
                    output_data=result_data,
                    dataset_group=group,
                    batch_group_id=batch_group_id,
                )
                metrics.saved_id = saved_id
                result_data["metrics"]["saved_id"] = metrics.saved_id
                outputs.append(result_data)

                yield _sse({
                    "step": "batch_progress",
                    "group": group,
                    "input": input_id,
                    "index": index,
                    "total": total,
                    "status": "done",
                })

            yield _sse({
                "step": "batch_result",
                "data": {
                    "batch_group_ids": batch_group_ids,
                    "outputs": outputs,
                },
            })
        except (FileNotFoundError, ValueError) as exc:
            yield _sse({"step": "error", "error": str(exc) or "Invalid batch selection"})
        except Exception as exc:
            yield _sse({"step": "error", "error": f"Batch pipeline error: {exc}"})

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
