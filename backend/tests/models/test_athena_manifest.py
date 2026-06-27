"""Unit and integration tests for backend/models/athena_manifest.py."""
from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from models.athena_manifest import (
    AthenaClinicalDocManifest,
    AthenaEncounterManifest,
    AthenaEncounterManifestEntry,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent  # backend/tests/models -> backend/tests -> backend -> repo root
_UNIFIED_MANIFEST_PATH = _REPO_ROOT / "preset-data" / "manifest.json"


def test_encounters_manifest_parses():
    """The encounters manifest in the unified manifest parses through AthenaEncounterManifest."""
    with _UNIFIED_MANIFEST_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("athena_sources", [])
    encounter_source = next((s for s in sources if s.get("source_kind") == "athena_encounter"), None)
    assert encounter_source is not None, "No athena_encounter source found in unified manifest"
    manifest = AthenaEncounterManifest.model_validate(encounter_source)
    assert manifest.source_kind == "athena_encounter"
    assert len(manifest.entries) >= 1
    first = manifest.entries[0]
    assert first.encounter_id
    assert first.practice_id


def test_clinical_docs_manifest_parses():
    """The clinical docs manifest in the unified manifest parses through AthenaClinicalDocManifest."""
    with _UNIFIED_MANIFEST_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("athena_sources", [])
    clinical_source = next((s for s in sources if s.get("source_kind") == "athena_clinical_doc"), None)
    assert clinical_source is not None, "No athena_clinical_doc source found in unified manifest"
    manifest = AthenaClinicalDocManifest.model_validate(clinical_source)
    assert manifest.source_kind == "athena_clinical_doc"
    assert len(manifest.entries) >= 1
    first = manifest.entries[0]
    assert first.document_id
    assert first.patient_id


def test_invalid_source_kind_raises():
    """AthenaEncounterManifest rejects a dict with the wrong source_kind."""
    data = {
        "source_kind": "athena_unknown",
        "label": "Test",
        "tab_id": "x",
        "preview_entry_id": "e1",
        "entries": [],
    }
    with pytest.raises(ValidationError):
        AthenaEncounterManifest.model_validate(data)


def test_encounter_entry_missing_encounter_id_raises():
    """AthenaEncounterManifestEntry requires encounter_id."""
    data = {
        "id": "e1",
        "label": "Entry 1",
        "practice_id": "195900",
        "patient_id": "60183",
        "api_path": "/v1/195900/chart/encounters/62021/summary",
        "is_preview": False,
    }
    with pytest.raises(ValidationError):
        AthenaEncounterManifestEntry.model_validate(data)


def test_extra_fields_are_ignored():
    """Extra keys are silently dropped (ConfigDict extra='ignore')."""
    data = {
        "source_kind": "athena_encounter",
        "label": "Test",
        "tab_id": "enc",
        "preview_entry_id": "e1",
        "entries": [{
            "id": "e1",
            "label": "Entry 1",
            "practice_id": "195900",
            "patient_id": "60183",
            "encounter_id": "62021",
            "api_path": "/v1/195900/chart/encounters/62021/summary",
            "is_preview": True,
            "preview_content": None,
        }],
        "metadata": {"version": 1},
    }
    manifest = AthenaEncounterManifest.model_validate(data)
    dumped = manifest.model_dump()
    assert "metadata" not in dumped
    assert manifest.label == "Test"


