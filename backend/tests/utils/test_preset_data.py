import json
import pytest


FIXTURE_MANIFEST = {
    "generated_at": "2026-06-27T00:00:00Z",
    "bucket": "juno-preset-data",
    "gcs_prefix": "preset-data",
    "datasets": [
        {
            "group": "meqsum",
            "total_inputs": 3,
            "file_types": ["question.txt", "summary.txt"],
            "inputs": ["0001", "0002", "0003"],
            "sample": {
                "input_id": "0001",
                "files": {
                    "question.txt": "What is aspirin?",
                    "summary.txt": "Aspirin is a pain reliever.",
                },
            },
        },
        {
            "group": "notechat",
            "total_inputs": 2,
            "file_types": ["note.txt"],
            "inputs": ["nc001", "nc002"],
            "sample": {
                "input_id": "nc001",
                "files": {"note.txt": "Patient presents with fever."},
            },
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_manifest_cache():
    """Reset the module-level manifest cache before each test."""
    import utils.preset_data as pd
    pd._manifest_cache = None
    yield
    pd._manifest_cache = None


@pytest.fixture
def manifest_file(tmp_path):
    """Write the fixture manifest to a temp file."""
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(FIXTURE_MANIFEST), encoding="utf-8")
    return p


def test_list_datasets_from_manifest(manifest_file, monkeypatch):
    """list_datasets() returns correct shape from manifest."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    result = pd.list_datasets()
    assert len(result) == 2
    assert result[0] == {
        "group": "meqsum",
        "inputs": ["0001", "0002", "0003"],
        "files": ["question.txt", "summary.txt"],
    }
    assert result[1]["group"] == "notechat"
    assert result[1]["files"] == ["note.txt"]


def test_read_sample_file(manifest_file, monkeypatch):
    """read_dataset_file returns bytes of manifest sample content for inputs[0]."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    result = pd.read_dataset_file("meqsum", "0001", "question.txt")
    assert result == b"What is aspirin?"


def test_read_non_sample_raises_gcs_fetch_required(manifest_file, monkeypatch):
    """read_dataset_file raises GCSFetchRequired for a non-sample input_id."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    with pytest.raises(pd.GCSFetchRequired) as exc_info:
        pd.read_dataset_file("meqsum", "0002", "question.txt")
    assert exc_info.value.group == "meqsum"
    assert exc_info.value.input_id == "0002"
    assert exc_info.value.filename == "question.txt"


def test_read_unknown_group_raises_file_not_found(manifest_file, monkeypatch):
    """read_dataset_file raises FileNotFoundError for an unknown group."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    with pytest.raises(FileNotFoundError):
        pd.read_dataset_file("nonexistent", "0001", "question.txt")


def test_list_datasets_missing_manifest(tmp_path, monkeypatch):
    """list_datasets() returns [] when manifest.json does not exist."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", tmp_path / "no_manifest.json")
    result = pd.list_datasets()
    assert result == []


def test_list_athena_sources_returns_from_manifest(tmp_path, monkeypatch):
    """list_athena_sources() returns the athena_sources array from manifest."""
    import utils.preset_data as pd
    fixture = dict(FIXTURE_MANIFEST)
    fixture["athena_sources"] = [{"source_kind": "athena_encounter", "label": "Test"}]
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(fixture), encoding="utf-8")
    pd._manifest_cache = None
    monkeypatch.setattr(pd, "MANIFEST_PATH", p)
    result = pd.list_athena_sources()
    assert result == [{"source_kind": "athena_encounter", "label": "Test"}]
    pd._manifest_cache = None


def test_list_athena_sources_missing_key_returns_empty(manifest_file, monkeypatch):
    """list_athena_sources() returns [] when athena_sources is absent from manifest."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    result = pd.list_athena_sources()
    assert result == []


def test_manifest_cache(manifest_file, monkeypatch):
    """list_datasets() only opens the manifest file once across multiple calls."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)

    load_count = [0]
    original_json_load = json.load

    def counting_json_load(fp, **kwargs):
        load_count[0] += 1
        return original_json_load(fp, **kwargs)

    monkeypatch.setattr(json, "load", counting_json_load)
    pd.list_datasets()
    pd.list_datasets()
    assert load_count[0] == 1, "Manifest JSON should be parsed only once (cached)"
