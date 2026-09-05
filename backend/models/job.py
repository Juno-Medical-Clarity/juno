"""Typed Pydantic model for the Firestore care_plan_outputs job document."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import ConfigDict

from .base import JsonModel
from .api_response import ErrorDetail, StatusEnum
from .care_plan.envelope import CarePlanInternal
from utils.constants import Constants

AthenaSourceKind = Constants.Athena.AthenaSourceKind


class JobDoc(JsonModel):
    """Typed representation of a Firestore care_plan_outputs job document.

    Field names are the exact Firestore wire keys — do NOT rename without
    coordinating with the frontend (SP10) and Firestore security rules.

    extra="ignore" is intentional: unknown keys written to Firestore
    out-of-band are silently dropped rather than raising ValidationError.
    """

    model_config = ConfigDict(extra="ignore")

    # ── Identity ──────────────────────────────────────────────────────────
    uid: str
    name: str
    source_filename: str

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime

    # ── Lifecycle ─────────────────────────────────────────────────────────
    status: StatusEnum = StatusEnum.not_started
    stage: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_data: Optional[CarePlanInternal] = None
    error_data: Optional[ErrorDetail] = None

    # ── Batch grouping ────────────────────────────────────────────────────
    batch_run_id: Optional[str] = None
    batch_group_id: Optional[str] = None

    # ── Input provenance ──────────────────────────────────────────────────
    input_source_kind: AthenaSourceKind
    input_text: Optional[str] = None
    input_doc_id: Optional[str] = None
    input_source_filename: str
    input_pdf_gcs_uri: Optional[str] = None
    input_version: str = "v1-2"
    grading_enabled: bool = False

    # ── GCS-dataset-specific ──────────────────────────────────────────────
    dataset_group: Optional[str] = None
    dataset_input_id: Optional[str] = None
    dataset_files: Optional[list[str]] = None

    # ── Athena-specific ───────────────────────────────────────────────────
    athena_practice_id: Optional[str] = None
    athena_patient_id: Optional[str] = None
    athena_encounter_id: Optional[str] = None
    athena_document_id: Optional[str] = None
    athena_api_path: Optional[str] = None

    # ── Single-job-only extras ────────────────────────────────────────────
    shared: Optional[bool] = None
    comment: Optional[str] = None
    trace_id: Optional[str] = None

    # ── Trial (SP2) ───────────────────────────────────────────────────────
    is_trial: bool = False
    expires_at: Optional[datetime] = None

    # ── Factories ─────────────────────────────────────────────────────────

    @classmethod
    def for_gcs_dataset(
        cls,
        *,
        user_id: str,
        now: datetime,
        version: str,
        grading_enabled: bool,
        batch_run_id: str,
        batch_group_id: str,
        dataset_group: str,
        dataset_input_id: str,
        dataset_files: list[str],
        source_filename: str,
    ) -> "JobDoc":
        """Build a job doc for a GCS-batch-dataset item."""
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=source_filename,
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            input_source_kind=AthenaSourceKind.GCS_BATCH_DATASET,
            input_source_filename=source_filename,
            input_version=version,
            grading_enabled=grading_enabled,
            batch_run_id=batch_run_id,
            batch_group_id=batch_group_id,
            dataset_group=dataset_group,
            dataset_input_id=dataset_input_id,
            dataset_files=dataset_files,
        )

    @classmethod
    def for_athena(
        cls,
        *,
        user_id: str,
        now: datetime,
        version: str,
        grading_enabled: bool,
        batch_run_id: str,
        batch_group_id: str,
        source_kind: AthenaSourceKind,
        source_filename: str,
        practice_id: str,
        patient_id: str,
        encounter_id: Optional[str],
        document_id: Optional[str],
        api_path: str,
    ) -> "JobDoc":
        """Build a job doc for an Athena Health batch item."""
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=source_filename,
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            input_source_kind=source_kind,
            input_source_filename=source_filename,
            input_version=version,
            grading_enabled=grading_enabled,
            batch_run_id=batch_run_id,
            batch_group_id=batch_group_id,
            athena_practice_id=practice_id,
            athena_patient_id=patient_id,
            athena_encounter_id=encounter_id,
            athena_document_id=document_id,
            athena_api_path=api_path,
        )

    @classmethod
    def for_single(
        cls,
        *,
        user_id: str,
        now: datetime,
        trace_id: Optional[str],
        input_fields: dict,
        is_trial: bool = False,
        expires_at: Optional[datetime] = None,
    ) -> "JobDoc":
        """Build a job doc for a single (non-batch) care-plan job.

        input_fields dict must contain:
          input_source_kind, input_text, input_doc_id,
          input_source_filename, input_pdf_gcs_uri,
          input_version, grading_enabled
        """
        return cls(
            uid=user_id,
            name=now.strftime("%b %d, %Y %H:%M"),
            source_filename=input_fields["input_source_filename"],
            created_at=now,
            updated_at=now,
            status=StatusEnum.not_started,
            shared=False,
            comment="",
            trace_id=trace_id,
            is_trial=is_trial,
            expires_at=expires_at,
            **input_fields,
        )

    # ── Persistence ───────────────────────────────────────────────────────

    def to_firestore(self) -> dict:
        """Serialise to a Firestore-ready dict (datetime objects preserved)."""
        return self.model_dump(mode="python", exclude_none=False)

    @classmethod
    def from_firestore(cls, data: dict) -> "JobDoc":
        """Parse a raw Firestore document dict into a typed JobDoc."""
        return cls.model_validate(data)
