"""Batch dataset care plan utilities."""

from datetime import datetime, timezone
from typing import Callable, Generator

from flask import Blueprint

from utils.constants import Constants

from routes.care_plan import _extract_text_from_bytes, run_care_plan_pipeline
from utils.firebase import save_care_plan_output
from utils.preset_data import list_datasets, read_dataset_file


batch_bp = Blueprint("batch", __name__)


@batch_bp.route("/care_plan/batch", methods=["POST"])
def care_plan_batch_sse_deprecated():
    """Deprecated SSE batch endpoint — use POST /care_plan/batch/jobs instead."""
    from flask import jsonify
    return jsonify({
        "error": "This SSE endpoint has been removed. Use POST /care_plan/batch/jobs instead."
    }), 410


def _batch_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _grading_enabled(raw_value) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _pipeline_for_version(version: str) -> Callable[..., Generator[str | tuple, None, None]]:
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

        dataset = datasets_by_group.get(group)
        available_files = dataset["files"] if dataset else []
        for f in files:
            if f not in available_files:
                raise ValueError(f"File type not found in dataset {group}: {f!r}. Available: {available_files}")

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


def _pipeline_kwargs_for_batch() -> dict:
    """Return the canonical keyword arguments for a batch pipeline invocation.

    All batch executions pass ``is_batch=True`` and ``source_kind="batch_dataset"``
    so that pipeline markers record the correct provenance dimensions.
    """
    return {
        "is_batch": True,
        "source_kind": "batch_dataset",
    }
