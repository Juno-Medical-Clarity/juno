from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, model_validator
from utils.constants import Constants

_TRUTHY = {"1", "true", "yes", "on"}


def _coerce_grading_enabled(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in _TRUTHY


class AthenaEncounterSelection(BaseModel):
    input_source_kind: Literal["athena_encounter"]
    athena_practice_id: str = ""
    athena_patient_id: str = ""
    athena_encounter_id: str
    athena_document_id: str | None = None
    athena_api_path: str = ""

    @model_validator(mode="after")
    def _require_encounter_id(self) -> "AthenaEncounterSelection":
        if not self.athena_encounter_id:
            raise ValueError("athena_encounter requires athena_encounter_id")
        return self


class AthenaClinicalDocSelection(BaseModel):
    input_source_kind: Literal["athena_clinical_doc"]
    athena_practice_id: str = ""
    athena_patient_id: str = ""
    athena_encounter_id: str | None = None
    athena_document_id: str
    athena_api_path: str = ""

    @model_validator(mode="after")
    def _require_document_id(self) -> "AthenaClinicalDocSelection":
        if not self.athena_document_id:
            raise ValueError("athena_clinical_doc requires athena_document_id")
        return self


class GcsDatasetSelection(BaseModel):
    input_source_kind: Literal["gcs_dataset"]
    group: str
    files: list[str]
    inputs: str | list[str]

    @model_validator(mode="after")
    def _validate_fields(self) -> "GcsDatasetSelection":
        if not self.group:
            raise ValueError("Selection is missing group")
        if not self.files or not all(isinstance(f, str) and f for f in self.files):
            raise ValueError(f"Selection for {self.group} must include files")
        if self.inputs != "all" and not (
            isinstance(self.inputs, list)
            and all(isinstance(i, str) for i in self.inputs)
        ):
            raise ValueError(f"Selection for {self.group} must include inputs")
        return self


Selection = Annotated[
    Union[AthenaEncounterSelection, AthenaClinicalDocSelection, GcsDatasetSelection],
    Field(discriminator="input_source_kind"),
]


class BatchJobsRequest(BaseModel):
    selections: list[Selection] = Field(min_length=1)
    version: str = Constants.PIPELINE_VERSION_V1_2
    grading_enabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_grading(cls, data):
        if isinstance(data, dict) and "grading_enabled" in data:
            data["grading_enabled"] = _coerce_grading_enabled(data["grading_enabled"])
        return data


class SingleJobRequest(BaseModel):
    version: str = Constants.PIPELINE_VERSION_V1_2
    grading_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _coerce_grading(cls, data):
        if isinstance(data, dict) and "grading_enabled" in data:
            data["grading_enabled"] = _coerce_grading_enabled(data["grading_enabled"])
        return data
