# backend/models/athena_manifest.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class AthenaEncounterManifestEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    practice_id: str
    patient_id: str
    encounter_id: str
    api_path: str
    is_preview: bool
    preview_content: Optional[str] = None


class AthenaEncounterManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_kind: Literal["athena_encounter"]
    label: str
    tab_id: str
    preview_entry_id: str
    entries: list[AthenaEncounterManifestEntry]


class AthenaClinicalDocManifestEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    practice_id: str
    patient_id: str
    document_id: str
    api_path: str
    is_preview: bool
    preview_content: Optional[str] = None


class AthenaClinicalDocManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_kind: Literal["athena_clinical_doc"]
    label: str
    tab_id: str
    preview_entry_id: str
    entries: list[AthenaClinicalDocManifestEntry]


AthenaManifest = AthenaEncounterManifest | AthenaClinicalDocManifest
