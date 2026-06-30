"""Strict Pydantic care-plan models."""

from __future__ import annotations

from ..base import VersionedModel

class CarePlan(VersionedModel):
    """Version-agnostic care-plan family base. Concrete versions live in models/care_plan/versions/."""

    doc_type: str
    version: str

    @classmethod
    def from_pipeline_result(cls, version: str, data: dict) -> "CarePlan":
        """Validate pipeline output against the concrete care-plan version."""
        return cls.from_dict({**data, "version": version})
