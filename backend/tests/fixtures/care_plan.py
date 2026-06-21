"""
Shared fixture data for care-plan tests.
"""
from pathlib import Path
import json

FIXTURE_PATH = Path(__file__).parent / "care_plan_v1_2.json"


def load_fixture() -> dict:
    """Load the full v1.2 care plan fixture from disk."""
    return json.loads(FIXTURE_PATH.read_text())


# Minimal care-plan pipeline output dict matching the CarePlanInternal envelope shape.
# Keys: metrics, input, grading, care_plan (plus optional before_score/after_score).
SAMPLE_PIPELINE_OUTPUT = {
    "metrics": {
        "session_id": "session-1",
        "pipeline_version": "v1-2",
        "input_type": "text",
        "created_at": "2026-06-16T00:00:00+00:00",
        "saved_id": None,
    },
    "input": {
        "mode": "text",
        "text": "Sample clinical note for testing.",
        "files": [],
        "doc_id": None,
        "dataset_group": None,
        "dataset_input": None,
        "selected_files": None,
        "batch_group_id": None,
    },
    "grading": {
        "enabled": False,
    },
    "care_plan": {
        "version": "1.2",
        "doc_type": "care_plan",
        "reason_for_visit": [{"reason": "Annual check-up"}],
        "summary": "You came in for your annual check-up.",
    },
}


def fixed_output(input_label: str, group: str = "GroupA", batch_group_id: str = None) -> dict:
    """
    Build a minimal care-plan pipeline output dict suitable for batch-route tests.

    Matches the shape produced by the real pipeline and consumed by the batch route.
    """
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
