"""Batch utilities: timestamp helper and GCS selection resolver."""

from datetime import datetime, timezone

from flask import Blueprint

from utils.preset_data import list_datasets


batch_bp = Blueprint("batch", __name__)


def _batch_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


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
