import json
import pytest


def test_writes_correct_content(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "day1_consultation01.json").write_text(json.dumps({
        "day": 1, "consultation": 1,
        "presenting_complaint": "Headache",
        "note": "Patient reports 3-day headache.",
        "highlights": [],
    }))
    dest = tmp_path / "preset-data"
    from utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(notes_dir / "day1_consultation01.json", dest / "primock57", overwrite=False)
    assert result == "written"
    out = (dest / "primock57" / "day1-consultation01" / "consultation_notes.txt").read_text()
    assert out == "Presenting Complaint: Headache\nNotes: Patient reports 3-day headache."


def test_input_id_uses_hyphens(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "day3_consultation07.json").write_text(json.dumps({
        "presenting_complaint": "Cough", "note": "Dry cough x 2 weeks."
    }))
    dest = tmp_path / "preset-data" / "primock57"
    from utils.preset_data_parser.primock57.parser import _process_file
    _process_file(notes_dir / "day3_consultation07.json", dest, overwrite=False)
    assert (dest / "day3-consultation07" / "consultation_notes.txt").exists()


def test_skip_existing_without_overwrite(tmp_path):
    dest = tmp_path / "primock57"
    out_dir = dest / "day1-consultation01"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "consultation_notes.txt"
    out_file.write_text("original")
    json_path = tmp_path / "day1_consultation01.json"
    json_path.write_text(json.dumps({"presenting_complaint": "X", "note": "Y"}))
    from utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(json_path, dest, overwrite=False)
    assert result == "skipped"
    assert out_file.read_text() == "original"


def test_overwrite_replaces_existing(tmp_path):
    dest = tmp_path / "primock57"
    out_dir = dest / "day1-consultation01"
    out_dir.mkdir(parents=True)
    (out_dir / "consultation_notes.txt").write_text("old")
    json_path = tmp_path / "day1_consultation01.json"
    json_path.write_text(json.dumps({"presenting_complaint": "New", "note": "New note"}))
    from utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(json_path, dest, overwrite=True)
    assert result == "written"
    assert "New" in (out_dir / "consultation_notes.txt").read_text()


def test_malformed_json_returns_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{")
    dest = tmp_path / "primock57"
    from utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(bad, dest, overwrite=False)
    assert result == "error"


def test_missing_field_returns_error(tmp_path):
    src = tmp_path / "day1_consultation01.json"
    src.write_text(json.dumps({"presenting_complaint": "X"}))
    dest = tmp_path / "primock57"
    from utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(src, dest, overwrite=False)
    assert result == "error"


def test_resolve_notes_dir_with_nested_notes_subdir(tmp_path):
    repo_root = tmp_path / "primock57"
    notes = repo_root / "notes"
    notes.mkdir(parents=True)
    from utils.preset_data_parser.primock57.parser import _resolve_notes_dir
    assert _resolve_notes_dir(repo_root) == notes


def test_resolve_notes_dir_when_source_is_notes_dir(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    from utils.preset_data_parser.primock57.parser import _resolve_notes_dir
    assert _resolve_notes_dir(notes) == notes


def test_main_processes_all_json_files(tmp_path, monkeypatch):
    notes = tmp_path / "notes"
    notes.mkdir()
    for i in range(3):
        (notes / f"day1_consultation0{i+1}.json").write_text(json.dumps({
            "presenting_complaint": f"Complaint {i}", "note": f"Note {i}",
        }))
    dest = tmp_path / "preset-data"
    monkeypatch.setattr("sys.argv", ["parser.py", "--source", str(notes), "--dest", str(dest)])
    from utils.preset_data_parser.primock57.parser import main
    main()
    assert len(list((dest / "primock57").iterdir())) == 3
    for i in range(3):
        f = dest / "primock57" / f"day1-consultation0{i+1}" / "consultation_notes.txt"
        assert f.exists()
        assert f"Complaint {i}" in f.read_text()
