"""Pydantic v2 models for Athena Health API requests and responses.

These models are the contract between Juno and Athena Health.
Any change to Athena's API response shape must be reflected here first.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AthenaTokenRequest(BaseModel):
    """POST /oauth2/v1/token"""

    model_config = ConfigDict(extra="allow")

    client_id: str
    client_secret: str
    grant_type: str = "client_credentials"
    scope: str


class AthenaTokenResponse(BaseModel):
    """OAuth2 token response."""

    model_config = ConfigDict(extra="allow")

    access_token: str
    token_type: str
    expires_in: int


class AthenaEncounterSummaryRequest(BaseModel):
    """GET /v1/{practice_id}/chart/encounters/{encounter_id}/summary"""

    model_config = ConfigDict(extra="allow")

    practice_id: str
    encounter_id: str


class AthenaEncounterSummaryResponse(BaseModel):
    """Encounter summary response."""

    model_config = ConfigDict(extra="allow")

    summaryhtml: str


class AthenaClinicalDocumentMeta(BaseModel):
    """Single document metadata item from the clinical documents list."""

    model_config = ConfigDict(extra="allow")

    clinicaldocumentid: int
    patientid: int
    documentdescription: str
    documentclass: str
    status: str
    internalnote: str | None = None
    createddatetime: str | None = None
    documentsource: str | None = None
    documentroute: str | None = None
    priority: str | None = None
    assignedto: str | None = None
    lastmodifieddatetime: str | None = None
    departmentid: str | None = None
    createddate: str | None = None
    lastmodifieduser: str | None = None
    lastmodifieddate: str | None = None
    observationdate: str | None = None
    createduser: str | None = None


class AthenaClinicalDocumentListRequest(BaseModel):
    """GET /v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument"""

    model_config = ConfigDict(extra="allow")

    practice_id: str
    patient_id: str
    department_id: str | None = None
    limit: int = 200
    offset: int = 0


class AthenaClinicalDocumentListResponse(BaseModel):
    """Clinical documents list response."""

    model_config = ConfigDict(extra="allow")

    clinicaldocuments: list[AthenaClinicalDocumentMeta]
    totalcount: int | None = None


class AthenaClinicalDocumentContentRequest(BaseModel):
    """GET /v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"""

    model_config = ConfigDict(extra="allow")

    practice_id: str
    patient_id: str
    document_id: str


class AthenaClinicalDocumentContentResponse(BaseModel):
    """Clinical document content response."""

    model_config = ConfigDict(extra="allow")

    documentdata: str | None = None
    pages: list[dict] | None = None


class AthenaPushDocumentRequest(BaseModel):
    """POST /v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument (future/deferred)"""

    model_config = ConfigDict(extra="allow")

    practice_id: str
    patient_id: str
    department_id: str
    attachment_contents: str
    attachment_type: str
    document_subclass: str = "JUNO_SUMMARY"
    internal_note: str


class AthenaPushDocumentResponse(BaseModel):
    """Push document response (future/deferred)."""

    model_config = ConfigDict(extra="allow")

    clinicaldocumentid: int
    success: bool | None = None
