# PRD: Preset Data Parser Infrastructure + Primock57 (SP07)

Phase 1, no dependencies. Creates the offline parser convention for dataset-specific ingestion
scripts, and ships the first concrete parser for the primock57 dataset. The parser writes files
into `preset-data/` in the structure the existing runtime already reads — no backend or frontend
changes required.

## 1. Problem

The batch pipeline relies on pre-staged files in `preset-data/{group}/{input_id}/{filename}`.
Today there is no reproducible, documented way to generate those files from a downloaded dataset.
A developer who wipes `preset-data/` or clones the repo has no script to restore the data; they
are left to reverse-engineer the required structure from the runtime code by hand.

The primock57 dataset (57 simulated GP consultations) is the first concrete dataset we want to
ship. Its source files are JSON (not txt/pdf/docx), so they cannot be placed in `preset-data/`
directly — they need a one-time transform that extracts the two text fields the pipeline uses.

## 2. Goals

1. Establish `backend/utils/preset_data_parser/` as the canonical home for offline dataset
   ingestion scripts, with a clear per-dataset subfolder convention.
2. Ship `backend/utils/preset_data_parser/primock57/parser.py`: a standalone CLI script that
   reads the downloaded primock57 `notes/` directory and writes one
   `preset-data/primock57/{input_id}/consultation_notes.txt` file per consultation.
3. Make the script idempotent with a documented, explicit `--overwrite` flag (default: skip
   existing files with a logged warning, never silently destroy data).
4. Make the script runnable as both `python parser.py` (from its own directory) and as
   `python -m backend.utils.preset_data_parser.primock57.parser` (from the repo root).
5. Document the exact run command in the script docstring, in the PRD §8, and in a
   `backend/utils/preset_data_parser/README.md`.
6. Add `.gitignore` rules to prevent accidentally committing the large primock57 source download.
7. Ship pytest tests for the parser in
   `backend/tests/utils/test_preset_data_parser_primock57.py`.

## 3. Non-Goals

- No changes to any backend route, Flask app, or `utils/preset_data.py` runtime reader.
- No frontend changes.
- No shared base class or `Protocol` for parsers — each parser is a standalone script (YAGNI).
  The convention is enforced by the directory layout and this PRD, not by Python inheritance.
- No CI/CD automation for running parsers — they are offline, human-run, one-time scripts.
- No second dataset parser (future parsers are separate sub-projects).
- The primock57 `highlights` field in the source JSON is intentionally ignored; only
  `presenting_complaint` and `note` are extracted.

## 4. Architecture Decisions

### 4.1 Directory layout

```
backend/utils/preset_data_parser/
    __init__.py                  # empty — marks package for -m invocation
    README.md                    # how to add a new parser; index of existing ones
    primock57/
        __init__.py              # empty
        parser.py                # the CLI script
```

The layout mirrors one-parser-per-dataset: future datasets land in their own peer subfolder
(`backend/utils/preset_data_parser/{dataset_name}/parser.py`). No shared base class is
introduced — the convention is the directory structure + this naming pattern.

### 4.2 `backend/utils/preset_data_parser/README.md`

Explains the convention:

> Each dataset parser lives in its own subfolder:
> `backend/utils/preset_data_parser/{dataset_name}/parser.py`
>
> Each parser is a self-contained CLI script. It reads from a downloaded source directory
> and writes files into the `preset-data/` tree expected by the runtime. Run it once after
> downloading the dataset; it does not need to be re-run unless `preset-data/` is wiped.
>
> Available parsers:
> - `primock57/` — 57 GP consultation notes from the primock57 dataset

### 4.3 `parser.py` — CLI interface

```
usage: parser.py [-h] --source SOURCE [--dest DEST] [--overwrite]

positional/optional flags:
  --source SOURCE   Path to the primock57 repo root (containing notes/)
                    OR the notes/ directory itself. Required.
  --dest DEST       Path to the preset-data/ output root.
                    Default: <repo-root>/preset-data
                    (resolved relative to this script's location as
                     ../../../../../preset-data from parser.py's __file__)
  --overwrite       If set, overwrite existing consultation_notes.txt files.
                    Default: skip existing files and print a warning.
  -h, --help        Show this help message and exit.
```

**Source resolution:** if `--source` points to a directory that contains a `notes/` subdirectory,
the parser descends into `notes/` automatically. If `--source` points to the `notes/` directory
directly (no `notes/` child), it uses that directory as-is. This handles both
`--source /path/to/primock57` (repo root) and `--source /path/to/primock57/notes` (notes dir).

**Dest default resolution** (exact logic, for the implementer):

```python
# parser.py lives at backend/utils/preset_data_parser/primock57/parser.py
# Four parents up from __file__ is the repo root.
_DEFAULT_DEST = Path(__file__).resolve().parents[4] / "preset-data"
```

### 4.4 `parser.py` — input format

Source files: `{notes_dir}/day{N}_consultation{NN}.json` — filenames follow this pattern but the
parser does not need to enforce it; it processes every `*.json` file found directly in the
`notes/` directory (non-recursive).

Each JSON file has this structure (at minimum):

```json
{
  "day": 1,
  "consultation": 1,
  "presenting_complaint": "I've been having really bad diarrhea for the last 3 days",
  "note": "3/7 hx of diarrhea, ...",
  "highlights": [...]
}
```

Only `presenting_complaint` and `note` are used. Other fields (including `highlights`) are
ignored.

### 4.5 `parser.py` — output format

Output file path: `{dest}/primock57/{input_id}/consultation_notes.txt`

`input_id` derivation: take the JSON filename stem and replace every `_` with `-`.

| JSON filename | input_id |
|---|---|
| `day1_consultation01.json` | `day1-consultation01` |
| `day2_consultation03.json` | `day2-consultation03` |

Output file content (exact format, no trailing newline after the last line):

```
Presenting Complaint: {presenting_complaint}
Notes: {note}
```

Concrete example for `day1_consultation01.json`:

```
Presenting Complaint: I've been having really bad diarrhea for the last 3 days
Notes: 3/7 hx of diarrhea, no blood, no vomiting, ...
```

The file is written as UTF-8. Newlines within the `note` field (multi-line notes) are preserved
as-is — the format is `"Presenting Complaint: {x}\nNotes: {y}"` where `{y}` may itself contain
`\n` characters from the source.

### 4.6 `parser.py` — overwrite behavior

| Scenario | Default (`--overwrite` absent) | With `--overwrite` |
|---|---|---|
| Output file does not exist | Write it | Write it |
| Output file already exists | **Skip** — print warning to stderr, continue | **Overwrite** |
| Output dir does not exist | Create it (with parents) | Create it (with parents) |

This is a deliberate "safe by default" design: running the parser twice without `--overwrite`
never silently destroys data that may have been manually edited.

Summary lines printed at end of run:

```
primock57 parser: 57 written, 0 skipped, 0 errors
```

or (if some were skipped):

```
primock57 parser: 55 written, 2 skipped (pass --overwrite to replace), 0 errors
```

Exit code: `0` if no errors; `1` if any JSON file failed to parse or write (errors are logged to
stderr and the parser continues to the next file — partial success is still reported).

### 4.7 `parser.py` — error handling

| Error condition | Behavior |
|---|---|
| `--source` path does not exist | Print error to stderr, exit 1 immediately |
| `--source` path exists but has no `.json` files | Print warning, exit 0 (not an error — empty run) |
| JSON file is not valid JSON | Print error to stderr (file path + exception), increment error count, continue |
| JSON file missing `presenting_complaint` key | Print error to stderr, increment error count, continue |
| JSON file missing `note` key | Print error to stderr, increment error count, continue |
| `note` or `presenting_complaint` is `None` or not a string | Coerce to `""` with a warning (non-fatal) |
| Output directory creation fails | Print error to stderr, increment error count, skip this file |
| Output file write fails | Print error to stderr, increment error count, continue |

A missing required field is treated as a hard error (counted, logged, skipped) — not silently
substituted — because the pipeline output would be meaningless with both fields empty.

### 4.8 `parser.py` — module-level structure

```python
#!/usr/bin/env python3
"""
primock57 parser — offline ingestion script.

Converts the primock57 GP consultation dataset into preset-data/ files
consumable by the Juno batch pipeline.

Usage:
    # From repo root:
    python -m backend.utils.preset_data_parser.primock57.parser \\
        --source /path/to/primock57

    # From this file's directory:
    python parser.py --source /path/to/primock57

    # Specify output location explicitly:
    python parser.py --source /path/to/primock57/notes --dest /path/to/juno/preset-data

    # Replace already-generated files:
    python parser.py --source /path/to/primock57 --overwrite

Download primock57 from: https://github.com/Sydney-Informatics-Hub/primock57
"""

import argparse
import json
import sys
from pathlib import Path

_DEFAULT_DEST = Path(__file__).resolve().parents[4] / "preset-data"


def _resolve_notes_dir(source: Path) -> Path:
    ...

def _parse_args() -> argparse.Namespace:
    ...

def _process_file(json_path: Path, dest_root: Path, overwrite: bool) -> str:
    """Process one JSON file. Returns 'written', 'skipped', or 'error'."""
    ...

def main() -> None:
    ...

if __name__ == "__main__":
    main()
```

`_process_file` returns a status string rather than raising, so `main()` can collect totals and
print the summary without try/except at the loop level.

### 4.9 `.gitignore` additions

Add to `/root/projects/juno/.gitignore` (root-level gitignore):

```gitignore
# primock57 source download (large; run parser.py once to generate preset-data/ files)
primock57/
/primock57/
```

This prevents `git add .` from accidentally staging a downloaded clone of the primock57 repo
whether it's placed at the repo root or in a subdirectory. The generated `preset-data/primock57/`
files are tracked (the existing `.gitignore` rule `!preset-data/**/*.txt` already allows `.txt`
files under preset-data/).

### 4.10 Runnable as `-m` module

Because both `backend/utils/preset_data_parser/__init__.py` and
`backend/utils/preset_data_parser/primock57/__init__.py` exist (even if empty), this works from
the repo root:

```bash
python -m backend.utils.preset_data_parser.primock57.parser --source /path/to/primock57
```

The `if __name__ == "__main__": main()` guard at the bottom of `parser.py` also supports
direct invocation (`python parser.py --source ...`) from inside the `primock57/` directory,
so both usage patterns work without any path manipulation.

## 5. API Change Summary

None. This sub-project contains no backend route changes, no new endpoints, no response shape
changes.

## 6. Frontend Change Summary

None.

## 7. Testing

New test file: `backend/tests/utils/test_preset_data_parser_primock57.py`

The tests use `tmp_path` (pytest built-in fixture) to construct a minimal fake `notes/` source
directory and a temp `dest` root. They import and call `_process_file` and `main` directly —
no subprocess invocation needed.

### 7.1 Output format correctness

```python
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
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(notes_dir / "day1_consultation01.json", dest / "primock57", overwrite=False)
    assert result == "written"
    out = (dest / "primock57" / "day1-consultation01" / "consultation_notes.txt").read_text()
    assert out == "Presenting Complaint: Headache\nNotes: Patient reports 3-day headache."
```

### 7.2 input_id slug conversion

```python
def test_input_id_uses_hyphens(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "day3_consultation07.json").write_text(json.dumps({
        "presenting_complaint": "Cough", "note": "Dry cough x 2 weeks."
    }))
    dest = tmp_path / "preset-data" / "primock57"
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    _process_file(notes_dir / "day3_consultation07.json", dest, overwrite=False)
    assert (dest / "day3-consultation07" / "consultation_notes.txt").exists()
```

### 7.3 Overwrite behavior

```python
def test_skip_existing_without_overwrite(tmp_path):
    dest = tmp_path / "primock57"
    out_dir = dest / "day1-consultation01"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "consultation_notes.txt"
    out_file.write_text("original")
    json_path = tmp_path / "day1_consultation01.json"
    json_path.write_text(json.dumps({"presenting_complaint": "X", "note": "Y"}))
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(json_path, dest, overwrite=False)
    assert result == "skipped"
    assert out_file.read_text() == "original"   # not overwritten

def test_overwrite_replaces_existing(tmp_path):
    dest = tmp_path / "primock57"
    out_dir = dest / "day1-consultation01"
    out_dir.mkdir(parents=True)
    (out_dir / "consultation_notes.txt").write_text("old")
    json_path = tmp_path / "day1_consultation01.json"
    json_path.write_text(json.dumps({"presenting_complaint": "New", "note": "New note"}))
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(json_path, dest, overwrite=True)
    assert result == "written"
    assert "New" in (out_dir / "consultation_notes.txt").read_text()
```

### 7.4 Error handling

```python
def test_malformed_json_returns_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {{")
    dest = tmp_path / "primock57"
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(bad, dest, overwrite=False)
    assert result == "error"

def test_missing_field_returns_error(tmp_path):
    src = tmp_path / "day1_consultation01.json"
    src.write_text(json.dumps({"presenting_complaint": "X"}))   # note field missing
    dest = tmp_path / "primock57"
    from backend.utils.preset_data_parser.primock57.parser import _process_file
    result = _process_file(src, dest, overwrite=False)
    assert result == "error"
```

### 7.5 Source resolution

```python
def test_resolve_notes_dir_with_nested_notes_subdir(tmp_path):
    repo_root = tmp_path / "primock57"
    notes = repo_root / "notes"
    notes.mkdir(parents=True)
    from backend.utils.preset_data_parser.primock57.parser import _resolve_notes_dir
    assert _resolve_notes_dir(repo_root) == notes

def test_resolve_notes_dir_when_source_is_notes_dir(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    from backend.utils.preset_data_parser.primock57.parser import _resolve_notes_dir
    # notes/ has no child named "notes/" — treated as the notes dir itself
    assert _resolve_notes_dir(notes) == notes
```

### 7.6 End-to-end via `main()`

```python
def test_main_processes_all_json_files(tmp_path, monkeypatch):
    notes = tmp_path / "notes"
    notes.mkdir()
    for i in range(3):
        (notes / f"day1_consultation0{i+1}.json").write_text(json.dumps({
            "presenting_complaint": f"Complaint {i}", "note": f"Note {i}",
        }))
    dest = tmp_path / "preset-data"
    monkeypatch.setattr("sys.argv", ["parser.py", "--source", str(notes), "--dest", str(dest)])
    from backend.utils.preset_data_parser.primock57.parser import main
    main()
    assert len(list((dest / "primock57").iterdir())) == 3
    for i in range(3):
        f = dest / "primock57" / f"day1-consultation0{i+1}" / "consultation_notes.txt"
        assert f.exists()
        assert f"Complaint {i}" in f.read_text()
```

### 7.7 Import path note

Because the tests live in `backend/tests/utils/` and the `conftest.py` at `backend/tests/`
inserts `BACKEND_DIR` (`backend/`) at the front of `sys.path`, the import must be:

```python
from utils.preset_data_parser.primock57.parser import _process_file, main, _resolve_notes_dir
```

(not `backend.utils...`) — matching the pattern used by `test_preset_data.py`'s
`from utils import preset_data`.

## 8. Manual Intervention Required From You

1. **Download primock57.** The parser script does not download anything. You must clone the repo
   manually before running the parser:

   ```bash
   git clone https://github.com/Sydney-Informatics-Hub/primock57 /tmp/primock57
   ```

2. **Run the parser** (from the repo root):

   ```bash
   python -m backend.utils.preset_data_parser.primock57.parser \
       --source /tmp/primock57
   ```

   Expected output:
   ```
   primock57 parser: 57 written, 0 skipped, 0 errors
   ```

   To replace previously generated files:
   ```bash
   python -m backend.utils.preset_data_parser.primock57.parser \
       --source /tmp/primock57 --overwrite
   ```

3. **Verify the output.** After the parser runs, confirm the structure looks correct:

   ```bash
   ls preset-data/primock57/ | head -5
   cat preset-data/primock57/day1-consultation01/consultation_notes.txt
   ```

   Expected:
   ```
   Presenting Complaint: <first consultation complaint text>
   Notes: <first consultation note text>
   ```

4. **Commit the generated files.** The existing `.gitignore` rule (`!preset-data/**/*.txt`)
   already tracks `.txt` files under `preset-data/`. After running the parser, stage and commit:

   ```bash
   git add preset-data/primock57/
   git commit -m "Add primock57 preset data (57 consultations)"
   ```

5. **Do NOT commit the primock57 source download.** The `.gitignore` rules added by this SP
   exclude `primock57/` directories at any level. The `/tmp/primock57` clone can be deleted after
   the generated files are committed.

## 9. Open Questions & Decisions

1. **Whether `note` fields with embedded newlines need special handling.**
   `[RESOLVED: Preserve as-is. The runtime reads the `.txt` file via `_extract_text_from_bytes`
   which does `file_bytes.decode("utf-8", errors="replace")` — raw passthrough. Multi-line
   notes are valid input to the pipeline and should be kept intact.]`

2. **Whether the parser should also extract the `highlights` field.**
   `[RESOLVED: No. Highlights are structured grading data for the original study, not clinical
   note content. The pipeline input is only `presenting_complaint` + `note`. Highlights are
   ignored.]`

3. **Whether to add a `day` / `consultation` header line above the complaint.**
   `[RESOLVED: No. The output format is exactly two lines as specified. Adding metadata headers
   would change what the pipeline receives and is not needed for the batch use case.]`

4. **Whether the parser needs a `--dry-run` flag.**
   `[RESOLVED: No — YAGNI. The `--overwrite` default-skip behavior already makes a real run safe
   to re-execute. A dry-run mode adds complexity without clear benefit for a one-time script.]`

5. **Whether to place `parser.py` tests in a new subdirectory `tests/utils/preset_data_parser/`.**
   `[RESOLVED: No — place the test file directly in `backend/tests/utils/` as
   `test_preset_data_parser_primock57.py`. This matches the flat naming convention already used
   by `test_preset_data.py` and avoids needing an extra `__init__.py` or conftest for a single
   test file.]`

6. **Whether `_DEFAULT_DEST` should use `parents[4]` or an env var.**
   `[RESOLVED: `parents[4]`. The script lives at a fixed depth in the repo
   (`backend/utils/preset_data_parser/primock57/parser.py` = 4 parents up to repo root). An env
   var would complicate the usage story for a one-time script. The `--dest` flag is available for
   any non-standard layout.]`

7. **Whether the `preset_data_parser/` package `__init__.py` files should export anything.**
   `[RESOLVED: Both `__init__.py` files remain empty. There is nothing to export from an
   infrastructure package that contains only CLI scripts. Empty `__init__.py` files exist solely
   to enable `-m` module invocation from the repo root.]`
