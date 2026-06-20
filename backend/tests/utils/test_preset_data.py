import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def preset_root(monkeypatch):
    """Create a temp preset-data tree and wire it into preset_data module."""
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)

    docconv_input_1 = root / "DocConv" / "input-1"
    docconv_input_2 = root / "DocConv" / "input-2"
    other_input = root / "OtherGroup" / "case-a"

    docconv_input_1.mkdir(parents=True)
    docconv_input_2.mkdir(parents=True)
    other_input.mkdir(parents=True)

    (docconv_input_1 / "notes.txt").write_bytes(b"input 1 notes")
    (docconv_input_1 / "transcript.txt").write_bytes(b"input 1 transcript")
    (docconv_input_2 / "input-2-only.txt").write_bytes(b"input 2 only")
    (other_input / "summary.txt").write_bytes(b"summary")
    (root / "DocConv" / "not-an-input.txt").write_text("ignored")

    from utils import preset_data
    monkeypatch.setattr(preset_data, "PRESET_DATA_ROOT", root)

    yield preset_data

    temp_dir.cleanup()


def test_list_datasets_returns_sorted_groups_inputs_and_representative_files(preset_root):
    datasets = preset_root.list_datasets()

    assert datasets == [
        {
            "group": "DocConv",
            "inputs": ["input-1", "input-2"],
            "files": ["notes.txt", "transcript.txt"],
        },
        {
            "group": "OtherGroup",
            "inputs": ["case-a"],
            "files": ["summary.txt"],
        },
    ]


def test_read_dataset_file_reads_from_the_requested_input_folder(preset_root):
    content = preset_root.read_dataset_file("DocConv", "input-2", "input-2-only.txt")

    assert content == b"input 2 only"


@pytest.mark.parametrize("group,input_id,filename", [
    ("../DocConv", "input-1", "notes.txt"),
    ("DocConv", "../../../etc", "passwd"),
    ("DocConv", "input-1", "../../../../etc/passwd"),
    ("DocConv", "input-2", "notes.txt"),
    ("Missing", "input-1", "notes.txt"),
])
def test_read_dataset_file_rejects_mismatches_and_traversal(group, input_id, filename, preset_root):
    with pytest.raises(FileNotFoundError):
        preset_root.read_dataset_file(group, input_id, filename)
