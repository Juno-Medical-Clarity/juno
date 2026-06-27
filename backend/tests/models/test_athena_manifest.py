"""Unit and integration tests for backend/models/athena_manifest.py."""
from __future__ import annotations

import json
import pathlib
import tempfile
from unittest import mock

import pytest
from pydantic import ValidationError

from models.athena_manifest import (
    AthenaClinicalDocManifest,
    AthenaEncounterManifest,
    AthenaEncounterManifestEntry,
)

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"


def test_encounters_manifest_parses():
    """The encounters manifest JSON on disk parses through AthenaEncounterManifest."""
    manifest_path = _DATA_DIR / "athena-encounters-manifest.json"
    assert manifest_path.is_file(), f"Manifest file not found: {manifest_path}"
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    manifest = AthenaEncounterManifest.model_validate(raw)
    assert manifest.source_kind == "athena_encounter"
    assert len(manifest.entries) >= 1
    first = manifest.entries[0]
    assert first.encounter_id
    assert first.practice_id


def test_clinical_docs_manifest_parses():
    """The clinical docs manifest JSON on disk parses through AthenaClinicalDocManifest."""
    manifest_path = _DATA_DIR / "athena-clinicaldocs-manifest.json"
    assert manifest_path.is_file(), f"Manifest file not found: {manifest_path}"
    with manifest_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    manifest = AthenaClinicalDocManifest.model_validate(raw)
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


def test_load_athena_sources_skips_invalid_manifest(caplog):
    """_load_athena_sources() skips a manifest with an unknown source_kind and logs a warning."""
    import routes.datasets as ds

    bad_manifest = {"source_kind": "bad_kind", "entries": []}

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=str(_DATA_DIR), delete=False
    ) as tmp:
        json.dump(bad_manifest, tmp)
        tmp_path = pathlib.Path(tmp.name)

    orig_data_dir = ds.DATA_DIR
    orig_names = ds._ATHENA_MANIFEST_NAMES
    ds.DATA_DIR = tmp_path.parent
    ds._ATHENA_MANIFEST_NAMES = [tmp_path.name]

    try:
        import logging
        with caplog.at_level(logging.WARNING, logger="routes.datasets"):
            result = ds._load_athena_sources()
    finally:
        ds.DATA_DIR = orig_data_dir
        ds._ATHENA_MANIFEST_NAMES = orig_names
        tmp_path.unlink()

    assert result == [], f"Expected empty list, got: {result}"
    assert any("bad_kind" in record.message for record in caplog.records)
