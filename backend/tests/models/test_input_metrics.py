"""Tests for the strict Pydantic input and metrics models."""

from io import BytesIO

import pytest
from pydantic import ValidationError
from werkzeug.datastructures import FileStorage

import models.input as input_models
from models.input import Input, InputFile
from models.metrics import Metrics


def test_input_version_constant_is_defined():
    assert input_models.INPUT_VERSION == "1.0"


def test_input_from_text_serializes_same_shape():
    assert Input.from_text("Patient note").to_dict() == {
        "mode": "text",
        "text": "Patient note",
        "doc_id": None,
        "files": [],
        "dataset_group": None,
        "dataset_input": None,
        "selected_files": None,
        "batch_group_id": None,
    }


def test_input_from_doc_id_serializes_same_shape():
    assert Input.from_doc_id("gs://bucket/input.pdf").to_dict() == {
        "mode": "doc_id",
        "text": None,
        "doc_id": "gs://bucket/input.pdf",
        "files": [],
        "dataset_group": None,
        "dataset_input": None,
        "selected_files": None,
        "batch_group_id": None,
    }


def test_input_from_file_uploads_serializes_same_shape_and_resets_streams():
    upload = FileStorage(
        stream=BytesIO(b"pdf bytes"),
        filename="visit.pdf",
        content_type="application/pdf",
    )

    model = Input.from_file_uploads([upload])

    assert model.to_dict() == {
        "mode": "file",
        "text": None,
        "doc_id": None,
        "files": [
            {
                "filename": "visit.pdf",
                "content_type": "application/pdf",
                "size_bytes": 9,
            }
        ],
        "dataset_group": None,
        "dataset_input": None,
        "selected_files": None,
        "batch_group_id": None,
    }
    assert upload.read() == b"pdf bytes"


def test_input_from_batch_dataset_serializes_same_shape():
    assert Input.from_batch_dataset(
        text="Combined dataset text",
        dataset_group="cardiology",
        dataset_input="sample-1",
        selected_files=["a.pdf", "b.txt"],
        batch_group_id="batch-123",
    ).to_dict() == {
        "mode": "text",
        "text": "Combined dataset text",
        "doc_id": None,
        "files": [],
        "dataset_group": "cardiology",
        "dataset_input": "sample-1",
        "selected_files": ["a.pdf", "b.txt"],
        "batch_group_id": "batch-123",
    }


def test_input_round_trip_reconstructs_nested_input_files():
    model = Input(
        mode="file",
        files=[
            InputFile(
                filename="visit.pdf",
                content_type="application/pdf",
                size_bytes=123,
            )
        ],
    )

    restored = Input.from_dict(model.to_dict())

    assert restored == model
    assert isinstance(restored.files[0], InputFile)


def test_input_and_input_file_reject_extra_kwargs():
    with pytest.raises(ValidationError):
        Input(mode="text", text="Patient note", unexpected=True)

    with pytest.raises(ValidationError):
        InputFile(
            filename="visit.pdf",
            content_type="application/pdf",
            size_bytes=123,
            unexpected=True,
        )


def test_metrics_start_is_mutable_and_serializes_mutations_without_step_durations():
    metrics = Metrics.start("session-1", "v1-2", "text")

    metrics.total_duration_ms = 42.5
    metrics.saved_id = "saved-123"

    data = metrics.to_dict()
    assert data["session_id"] == "session-1"
    assert data["pipeline_version"] == "v1-2"
    assert data["input_type"] == "text"
    assert data["total_duration_ms"] == 42.5
    assert data["saved_id"] == "saved-123"
    assert "created_at" in data
    assert "step_durations_ms" not in data
    assert "step_durations_ms" not in Metrics.model_fields


def test_metrics_rejects_extra_kwargs():
    with pytest.raises(ValidationError):
        Metrics(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
            created_at="2026-06-20T00:00:00+00:00",
            unexpected=True,
        )
