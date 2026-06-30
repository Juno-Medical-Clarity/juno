"""Tests for the discriminated Input union and metrics model."""

from io import BytesIO

import pytest
from pydantic import TypeAdapter, ValidationError
from werkzeug.datastructures import FileStorage

import models.input as input_models
from models.input import (
    BatchDatasetInput,
    DocIdInput,
    FileInput,
    Input,
    InputFile,
    TextInput,
)
from models.metrics import Metrics

_input_adapter = TypeAdapter(Input)


def test_input_version_constant():
    assert input_models.INPUT_VERSION == "1.0"


# ---------------------------------------------------------------------------
# FileInput
# ---------------------------------------------------------------------------

def test_file_input_from_file_uploads_exact_shape_and_resets_stream():
    upload = FileStorage(
        stream=BytesIO(b"pdf bytes"),
        filename="visit.pdf",
        content_type="application/pdf",
    )
    model = FileInput.from_file_uploads([upload])
    assert model.to_dict() == {
        "mode": "file",
        "files": [{"filename": "visit.pdf", "content_type": "application/pdf", "size_bytes": 9}],
        "pdf_gcs_url": None,
    }
    assert upload.read() == b"pdf bytes"


def test_file_input_default_pdf_gcs_url_is_none():
    assert FileInput(files=[]).to_dict()["pdf_gcs_url"] is None


def test_file_input_rejects_stray_text_field():
    with pytest.raises(ValidationError):
        FileInput(mode="file", text="oops")


# ---------------------------------------------------------------------------
# TextInput
# ---------------------------------------------------------------------------

def test_text_input_exact_shape():
    assert TextInput(text="Patient note").to_dict() == {
        "mode": "text",
        "text": "Patient note",
    }


def test_text_input_text_defaults_to_none():
    assert TextInput().to_dict() == {"mode": "text", "text": None}


def test_text_input_rejects_stray_doc_id():
    with pytest.raises(ValidationError):
        TextInput(text="x", doc_id="y")


# ---------------------------------------------------------------------------
# DocIdInput
# ---------------------------------------------------------------------------

def test_doc_id_input_exact_shape():
    assert DocIdInput(doc_id="gs://bucket/x.pdf").to_dict() == {
        "mode": "doc_id",
        "doc_id": "gs://bucket/x.pdf",
    }


def test_doc_id_input_rejects_stray_files():
    with pytest.raises(ValidationError):
        DocIdInput(doc_id="x", files=[])


# ---------------------------------------------------------------------------
# BatchDatasetInput
# ---------------------------------------------------------------------------

def test_batch_dataset_input_exact_shape_and_mode_is_batch_dataset():
    result = BatchDatasetInput(
        text="Combined text",
        dataset_group="cardiology",
        dataset_input="sample-1",
        selected_files=["a.pdf", "b.txt"],
        batch_group_id="batch-123",
    ).to_dict()
    assert result == {
        "mode": "batch_dataset",
        "text": "Combined text",
        "dataset_group": "cardiology",
        "dataset_input": "sample-1",
        "selected_files": ["a.pdf", "b.txt"],
        "batch_group_id": "batch-123",
    }


def test_batch_dataset_input_requires_all_fields():
    with pytest.raises(ValidationError):
        BatchDatasetInput(text="x", dataset_group="g")


# ---------------------------------------------------------------------------
# Union dispatch via TypeAdapter
# ---------------------------------------------------------------------------

def test_type_adapter_dispatches_file():
    result = _input_adapter.validate_python({"mode": "file", "files": []})
    assert isinstance(result, FileInput)


def test_type_adapter_dispatches_text():
    result = _input_adapter.validate_python({"mode": "text", "text": "x"})
    assert isinstance(result, TextInput)


def test_type_adapter_dispatches_doc_id():
    result = _input_adapter.validate_python({"mode": "doc_id", "doc_id": "gs://x"})
    assert isinstance(result, DocIdInput)


def test_type_adapter_dispatches_batch_dataset():
    result = _input_adapter.validate_python({
        "mode": "batch_dataset",
        "text": "t",
        "dataset_group": "g",
        "dataset_input": "i",
        "selected_files": ["a.pdf"],
        "batch_group_id": "g-ts",
    })
    assert isinstance(result, BatchDatasetInput)


def test_type_adapter_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        _input_adapter.validate_python({"mode": "unknown"})


# ---------------------------------------------------------------------------
# CarePlanInternal round-trips
# ---------------------------------------------------------------------------

def _make_internal(input_obj):
    from models.care_plan.versions.v1_2 import CarePlanV1_2
    from models.care_plan.envelope import CarePlanInternal
    from models.grading import Grading
    from models.metrics import Metrics

    metrics = Metrics.start("s1", "v1-2", input_obj.mode)
    grading = Grading(entries=[], enabled=False, graded_at=None)
    care_plan = CarePlanV1_2()
    return CarePlanInternal(
        metrics=metrics,
        input=input_obj,
        grading=grading,
        care_plan=care_plan,
    )


def test_care_plan_internal_round_trips_text_input():
    from models.care_plan.envelope import CarePlanInternal

    c = _make_internal(TextInput(text="hi"))
    restored = CarePlanInternal.model_validate(c.to_dict())
    assert isinstance(restored.input, TextInput)
    assert restored.input.text == "hi"


def test_care_plan_internal_round_trips_file_input():
    from models.care_plan.envelope import CarePlanInternal

    c = _make_internal(FileInput(files=[InputFile(filename="f.pdf", content_type="application/pdf", size_bytes=10)]))
    restored = CarePlanInternal.model_validate(c.to_dict())
    assert isinstance(restored.input, FileInput)
    assert restored.input.files[0].filename == "f.pdf"


def test_care_plan_internal_round_trips_doc_id_input():
    from models.care_plan.envelope import CarePlanInternal

    c = _make_internal(DocIdInput(doc_id="gs://bucket/doc.pdf"))
    restored = CarePlanInternal.model_validate(c.to_dict())
    assert isinstance(restored.input, DocIdInput)
    assert restored.input.doc_id == "gs://bucket/doc.pdf"


def test_care_plan_internal_round_trips_batch_dataset_input():
    from models.care_plan.envelope import CarePlanInternal

    c = _make_internal(BatchDatasetInput(
        text="t", dataset_group="g", dataset_input="i",
        selected_files=["a.pdf"], batch_group_id="g-ts",
    ))
    restored = CarePlanInternal.model_validate(c.to_dict())
    assert isinstance(restored.input, BatchDatasetInput)
    assert restored.input.dataset_group == "g"


# ---------------------------------------------------------------------------
# Metrics (keep existing tests)
# ---------------------------------------------------------------------------

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
