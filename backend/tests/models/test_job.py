"""Unit tests for models.job.JobDoc."""
import pytest
from datetime import datetime, timezone

from models.job import JobDoc
from models.api_response import StatusEnum, ErrorDetail
from utils.constants import Constants

AthenaSourceKind = Constants.Athena.AthenaSourceKind


def test_import():
    from models.job import JobDoc  # noqa: F401


@pytest.fixture
def now():
    return datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def gcs_kwargs(now):
    return dict(
        user_id="u1",
        now=now,
        version="v1-2",
        grading_enabled=False,
        batch_run_id="run-1",
        batch_group_id="grp-1",
        dataset_group="GroupA",
        dataset_input_id="input-1",
        dataset_files=["a.txt", "b.txt"],
        source_filename="a.txt",
    )


def test_for_gcs_dataset_sets_correct_fields(gcs_kwargs):
    job = JobDoc.for_gcs_dataset(**gcs_kwargs)
    assert job.input_source_kind == "gcs_batch_dataset"
    assert job.athena_practice_id is None
    assert job.athena_patient_id is None
    assert job.athena_encounter_id is None
    assert job.athena_document_id is None
    assert job.athena_api_path is None
    assert job.dataset_group == "GroupA"
    assert job.dataset_input_id == "input-1"
    assert job.dataset_files == ["a.txt", "b.txt"]
    assert job.shared is None
    assert job.comment is None
    assert job.trace_id is None
    assert job.batch_run_id == "run-1"
    assert job.batch_group_id == "grp-1"
    assert job.status == StatusEnum.not_started


def test_for_athena_encounter_sets_correct_fields(now):
    job = JobDoc.for_athena(
        user_id="u1",
        now=now,
        version="v1-2",
        grading_enabled=False,
        batch_run_id="run-2",
        batch_group_id="grp-2",
        source_kind=AthenaSourceKind.ATHENA_ENCOUNTER,
        source_filename="enc.pdf",
        practice_id="195900",
        patient_id="P1",
        encounter_id="E42",
        document_id=None,
        api_path="/api/enc",
    )
    assert job.dataset_group is None
    assert job.dataset_input_id is None
    assert job.dataset_files is None
    assert job.athena_encounter_id == "E42"
    assert job.athena_document_id is None
    assert job.input_source_kind == "athena_encounter"


def test_for_athena_clinical_doc_sets_correct_fields(now):
    job = JobDoc.for_athena(
        user_id="u1",
        now=now,
        version="v1-2",
        grading_enabled=False,
        batch_run_id="run-3",
        batch_group_id="grp-3",
        source_kind=AthenaSourceKind.ATHENA_CLINICAL_DOC,
        source_filename="doc.pdf",
        practice_id="195900",
        patient_id="P2",
        encounter_id=None,
        document_id="D99",
        api_path="/api/doc",
    )
    assert job.athena_document_id == "D99"
    assert job.athena_encounter_id is None
    assert job.input_source_kind == "athena_clinical_doc"


def test_for_single_sets_shared_comment_trace(now):
    input_fields = {
        "input_source_kind": "text",
        "input_text": "hello",
        "input_doc_id": None,
        "input_source_filename": "note.txt",
        "input_pdf_gcs_uri": None,
        "input_version": "v1-2",
        "grading_enabled": False,
    }
    job = JobDoc.for_single(user_id="u2", now=now, trace_id="abc123", input_fields=input_fields)
    assert job.shared is False
    assert job.comment == ""
    assert job.trace_id == "abc123"
    assert job.batch_run_id is None
    assert job.batch_group_id is None


def test_for_single_defaults_is_trial_false_and_expires_at_none(now):
    input_fields = {
        "input_source_kind": "text",
        "input_text": "hello",
        "input_doc_id": None,
        "input_source_filename": "note.txt",
        "input_pdf_gcs_uri": None,
        "input_version": "v1-2",
        "grading_enabled": False,
    }
    job = JobDoc.for_single(user_id="u2", now=now, trace_id=None, input_fields=input_fields)
    assert job.is_trial is False
    assert job.expires_at is None


def test_for_single_accepts_trial_kwargs(now):
    from datetime import timedelta
    expires = now + timedelta(hours=1)
    input_fields = {
        "input_source_kind": "text",
        "input_text": "hello",
        "input_doc_id": None,
        "input_source_filename": "note.txt",
        "input_pdf_gcs_uri": None,
        "input_version": "v1-2",
        "grading_enabled": True,
    }
    job = JobDoc.for_single(
        user_id="u2", now=now, trace_id=None, input_fields=input_fields,
        is_trial=True, expires_at=expires,
    )
    assert job.is_trial is True
    assert job.expires_at == expires


def test_to_firestore_writes_explicit_null_expires_at_for_non_trial_doc(now):
    input_fields = {
        "input_source_kind": "text",
        "input_text": "hello",
        "input_doc_id": None,
        "input_source_filename": "note.txt",
        "input_pdf_gcs_uri": None,
        "input_version": "v1-2",
        "grading_enabled": False,
    }
    job = JobDoc.for_single(user_id="u2", now=now, trace_id=None, input_fields=input_fields)
    d = job.to_firestore()
    assert "expires_at" in d
    assert d["expires_at"] is None
    assert d["is_trial"] is False


def test_to_firestore_returns_datetime_objects(gcs_kwargs):
    job = JobDoc.for_gcs_dataset(**gcs_kwargs)
    d = job.to_firestore()
    assert isinstance(d["created_at"], datetime)
    assert isinstance(d["updated_at"], datetime)
    assert "status" in d


def test_from_firestore_roundtrip(gcs_kwargs):
    job = JobDoc.for_gcs_dataset(**gcs_kwargs)
    d = job.to_firestore()
    job2 = JobDoc.from_firestore(d)
    assert job2.uid == job.uid
    assert job2.dataset_files == job.dataset_files
    assert job2.created_at == job.created_at


def test_from_firestore_ignores_extra_field(gcs_kwargs):
    d = JobDoc.for_gcs_dataset(**gcs_kwargs).to_firestore()
    d["unexpected_field"] = "surprise"
    job2 = JobDoc.from_firestore(d)
    assert not hasattr(job2, "unexpected_field")


def test_error_data_typed_submodel(gcs_kwargs):
    from errors import ErrorCode, build_error_data
    err = build_error_data(ErrorCode.UNKNOWN_ERROR, "boom")
    d = JobDoc.for_gcs_dataset(**gcs_kwargs).to_firestore()
    d["error_data"] = err
    job = JobDoc.from_firestore(d)
    assert isinstance(job.error_data, ErrorDetail)
    assert job.error_data.code == err["code"]
    assert job.error_data.message == err["message"]
    out_d = job.to_firestore()
    assert isinstance(out_d["error_data"], dict)
    assert "code" in out_d["error_data"]
    assert "message" in out_d["error_data"]
    assert "timestamp" in out_d["error_data"]


def _make_care_plan_internal():
    """Build a minimal CarePlanInternal for test use."""
    from models.care_plan.envelope import CarePlanInternal
    from models.care_plan.versions.v1_2 import CarePlanV1_2
    from models.grading import Grading
    from models.input import TextInput
    from models.metrics import Metrics

    metrics = Metrics(
        session_id="session-1",
        pipeline_version="v1-2",
        input_type="text",
        created_at="2026-01-15T10:00:00+00:00",
    )
    care_plan = CarePlanV1_2(
        summary="Take blood pressure medicine daily.",
        terms={
            "hypertension": {
                "definition": "High blood pressure.",
                "source": "provider note",
            }
        },
    )
    return CarePlanInternal(
        metrics=metrics,
        input=TextInput(text="Patient note"),
        grading=Grading(),
        care_plan=care_plan,
    )


def test_output_data_typed_submodel(gcs_kwargs):
    from models.care_plan.envelope import CarePlanInternal

    cpi = _make_care_plan_internal()
    out = cpi.to_dict()

    d = JobDoc.for_gcs_dataset(**gcs_kwargs).to_firestore()
    d["output_data"] = out
    job = JobDoc.from_firestore(d)
    assert isinstance(job.output_data, CarePlanInternal)
    out_d = job.to_firestore()
    assert isinstance(out_d["output_data"], dict)


def test_status_enum_default(gcs_kwargs):
    job = JobDoc.for_gcs_dataset(**gcs_kwargs)
    assert job.status == StatusEnum.not_started
