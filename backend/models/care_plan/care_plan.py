"""Strict Pydantic care-plan models."""

from __future__ import annotations

from ..base import VersionedModel

class CarePlan(VersionedModel):
    """Version-agnostic base model for all care plan outputs. The concrete version schema is CarePlanV1_2 in models/care_plan/versions/v1_2.py."""

    doc_type: str
    version: str

    @classmethod
    def from_pipeline_result(cls, version: str, data: dict) -> "CarePlan":
        """Validate pipeline output against the concrete care-plan version."""
        return cls.from_dict({**data, "version": version})
