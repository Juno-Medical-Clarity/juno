# Tasks: Preset Data Parser Infrastructure + Primock57 (SP07)

Read `PRD.md` in this folder first. SP07 is **Phase 1** with no dependencies — it can land immediately.

**Assumed conventions (state up front, verify before coding):**
- `backend/tests/conftest.py` inserts `BACKEND_DIR` (`backend/`) at position 0 of `sys.path`, so test imports use `from utils.preset_data_parser.primock57.parser import ...` (no `backend.` prefix).
- `pytest` is run from `backend/` with `addopts = "--import-mode=importlib"` per `pyproject.toml`.
- The existing `.gitignore` at repo root already contains `!preset-data/**/*.txt`, so generated `.txt` files under `preset-data/` will be tracked once committed.
- No `preset-data/primock57/` directory exists yet — the parser creates it on first run.

---

### Task 1 — Create `backend/utils/preset_data_parser/` package skeleton

- **Files:**
  - `backend/utils/preset_data_parser/__init__.py` *(new)*
  - `backend/utils/preset_data_parser/primock57/__init__.py` *(new)*
- **Changes:**
  - Create both files as empty (a single blank line or literally empty — the only requirement is that they exist so Python treats both directories as packages, enabling `-m` invocation from the repo root).
  - Do not add any imports or exports to either file (PRD §4.1 and §9.7 resolved: both `__init__.py` files remain empty).
- **Acceptance criteria:**
  - `python -c "import backend.utils.preset_data_parser.primock57"` exits 0 from the repo root.
  - Both files exist on disk. `cat` of each file produces no output or a single newline.

---

### Task 2 — Create `backend/utils/preset_data_parser/README.md`

- **Files:** `backend/utils/preset_data_parser/README.md` *(new)*
- **Changes:**
  - Create the file with exactly the content from PRD §4.2:

    ```
    # Preset Data Parsers

    Each dataset parser lives in its own subfolder:
    `backend/utils/preset_data_parser/{dataset_name}/parser.py`

    Each parser is a self-contained CLI script. It reads from a downloaded source directory
    and writes files into the `preset-data/` tree expected by the runtime. Run it once after
    downloading the dataset; it does not need to be re-run unless `preset-data/` is wiped.

    ## Available parsers

    - `primock57/` — 57 GP consultation notes from the primock57 dataset
      Download: https://github.com/Sydney-Informatics-Hub/primock57

    ## Running a parser

    From the repo root:

        python -m backend.utils.preset_data_parser.primock57.parser --source /path/to/primock57

    From inside the parser's own directory:

        python parser.py --source /path/to/primock57

    ## Adding a new parser

    1. Create `backend/utils/preset_data_parser/{dataset_name}/`.
    2. Add an empty `__init__.py`.
    3. Add `parser.py` — a self-contained CLI script following the same CLI interface pattern as `primock57/parser.py`.
    4. Add an entry to the "Available parsers" list above.
    ```

- **Acceptance criteria:**
  - File exists at `backend/utils/preset_data_parser/README.md`.
  - The file names the `primock57/` parser and links to the GitHub download URL.

---

### Task 3 — Create `backend/utils/preset_data_parser/primock57/parser.py`

- **Files:** `backend/utils/preset_data_parser/primock57/parser.py` *(new)*
- **Changes:**
  - Create the file with the module-level docstring, shebang, imports, module-level constant, and four functions from PRD §4.3 and §4.8. Implement each function exactly per the PRD specifications:

  **Shebang + docstring** (from PRD §4.8):
  ```python
  #!/usr/bin/env python3
  """
  primock57 parser — offline ingestion script.

  Converts the primock57 GP consultation dataset into preset-data/ files
  consumable by the Juno batch pipeline.

  Usage:
      # From repo root:
      python -m backend.utils.preset_data_parser.primock57.parser \
          --source /path/to/primock57

      # From this file's directory:
      python parser.py --source /path/to/primock57

      # Specify output location explicitly:
      python parser.py --source /path/to/primock57/notes --dest /path/to/juno/preset-data

      # Replace already-generated files:
      python parser.py --source /path/to/primock57 --overwrite

  Download primock57 from: https://github.com/Sydney-Informatics-Hub/primock57
  """
  ```

  **Imports + constant:**
  ```python
  import argparse
  import json
  import sys
  from pathlib import Path

  _DEFAULT_DEST = Path(__file__).resolve().parents[4] / "preset-data"
  ```
  Note: `parser.py` is at depth `backend/utils/preset_data_parser/primock57/parser.py`. Four `.parents` steps from `__file__` reach the repo root. So `parents[4]` is correct (per PRD §4.3 and §9.6).

  **`_resolve_notes_dir(source: Path) -> Path`** (PRD §4.3):
  - If `source / "notes"` exists and is a directory, return `source / "notes"`.
  - Otherwise return `source` as-is.
  - No validation here — the caller (`main`) validates that `source` exists.

  **`_parse_args() -> argparse.Namespace`** (PRD §4.3):
  - `argparse.ArgumentParser(description="primock57 parser")`.
  - `--source` (required, type=Path).
  - `--dest` (optional, type=Path, default=`_DEFAULT_DEST`).
  - `--overwrite` (store_true).
  - Return `parser.parse_args()`.

  **`_process_file(json_path: Path, dest_root: Path, overwrite: bool) -> str`** (PRD §4.5, §4.6, §4.7):
  - `input_id = json_path.stem.replace("_", "-")`.
  - `out_dir = dest_root / input_id`.
  - `out_file = out_dir / "consultation_notes.txt"`.
  - If `out_file.exists()` and not `overwrite`: print warning to stderr, return `"skipped"`.
  - Try to read and parse JSON from `json_path`:
    - If `json.JSONDecodeError`: print error to stderr, return `"error"`.
    - If `"presenting_complaint"` not in data: print error to stderr, return `"error"`.
    - If `"note"` not in data: print error to stderr, return `"error"`.
  - `complaint = data["presenting_complaint"]`; if not a string or is None: coerce to `""` with a warning to stderr.
  - `note = data["note"]`; same coercion.
  - Try `out_dir.mkdir(parents=True, exist_ok=True)`:
    - On `OSError`: print error to stderr, return `"error"`.
  - Try `out_file.write_text(f"Presenting Complaint: {complaint}\nNotes: {note}", encoding="utf-8")`:
    - On `OSError`: print error to stderr, return `"error"`.
  - Return `"written"`.

  **`main() -> None`** (PRD §4.6, §4.7):
  - Call `_parse_args()`.
  - Validate `args.source.exists()`; if not: print to stderr, `sys.exit(1)`.
  - `notes_dir = _resolve_notes_dir(args.source)`.
  - `json_files = sorted(notes_dir.glob("*.json"))` (non-recursive).
  - If `len(json_files) == 0`: print warning, `sys.exit(0)`.
  - `dest_root = args.dest / "primock57"`.
  - Loop over `json_files`, call `_process_file(f, dest_root, args.overwrite)`, accumulate `written`, `skipped`, `errors` counts.
  - Print summary line to stdout:
    - If `skipped > 0`: `f"primock57 parser: {written} written, {skipped} skipped (pass --overwrite to replace), {errors} errors"`
    - Else: `f"primock57 parser: {written} written, {skipped} skipped, {errors} errors"`
  - If `errors > 0`: `sys.exit(1)`.

  **Guard:**
  ```python
  if __name__ == "__main__":
      main()
  ```

- **Acceptance criteria:**
  - `python -m backend.utils.preset_data_parser.primock57.parser --help` from the repo root prints usage and exits 0.
  - `python parser.py --help` from inside `backend/utils/preset_data_parser/primock57/` prints usage and exits 0.
  - Given a `notes/` dir with one valid JSON file, the script writes `preset-data/primock57/{input_id}/consultation_notes.txt` with content `"Presenting Complaint: X\nNotes: Y"`.
  - A second run without `--overwrite` prints a skipped warning and exits 0; the file content is unchanged.
  - A second run with `--overwrite` overwrites the file and exits 0.
  - Given a JSON file missing the `note` key, the script prints an error to stderr, exits 1, and does not write an output file for that entry.
  - Given an invalid JSON file, the script prints an error to stderr, exits 1.
  - Given a `--source` path that does not exist, the script prints to stderr and exits 1 immediately (no files processed).
  - Given a `notes/` dir with zero `.json` files, the script prints a warning and exits 0.

---

### Task 4 — Add `.gitignore` rules for the primock57 source download

- **Files:** `/root/projects/juno/.gitignore`
- **Changes:**
  - Append the following block at the end of the file (after the existing `!preset-data/**/*.docx` line):

    ```gitignore

    # primock57 source download (large; run parser.py once to generate preset-data/ files)
    primock57/
    /primock57/
    ```

  The two rules together prevent git from staging a `primock57/` clone whether placed at the repo root (`/primock57/`) or in any subdirectory (`primock57/`). The generated `preset-data/primock57/*.txt` files remain tracked because of the existing `!preset-data/**/*.txt` rule.

- **Acceptance criteria:**
  - `git check-ignore -v primock57/` from the repo root outputs a match line (the rule fires).
  - `git check-ignore -v preset-data/primock57/day1-consultation01/consultation_notes.txt` produces no output (the file is not ignored — the `!preset-data/**/*.txt` negation keeps it tracked).
  - The `.gitignore` file still contains all previously existing rules (none removed).

---

### Task 5 — Write pytest tests in `backend/tests/utils/test_preset_data_parser_primock57.py`

- **Files:** `backend/tests/utils/test_preset_data_parser_primock57.py` *(new)*
- **Changes:**
  - Create the file with all tests from PRD §7.1 through §7.6.
  - **Import path** (PRD §7.7): because `conftest.py` puts `BACKEND_DIR` (`backend/`) on `sys.path[0]`, all imports must be:
    ```python
    from utils.preset_data_parser.primock57.parser import _process_file, _resolve_notes_dir, main
    ```
    (not `backend.utils...` — matching the pattern from `test_preset_data.py` which uses `from utils import preset_data`).
  - Include the following tests exactly as specified in the PRD:

  **PRD §7.1 — Output format correctness:**
  ```python
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
  ```

  **PRD §7.2 — input_id slug conversion:**
  ```python
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
  ```

  **PRD §7.3 — Overwrite behavior (two tests):**
  ```python
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
  ```

  **PRD §7.4 — Error handling (two tests):**
  ```python
  def test_malformed_json_returns_error(tmp_path):
      bad = tmp_path / "bad.json"
      bad.write_text("not json {{")
      dest = tmp_path / "primock57"
      from utils.preset_data_parser.primock57.parser import _process_file
      result = _process_file(bad, dest, overwrite=False)
      assert result == "error"

  def test_missing_field_returns_error(tmp_path):
      src = tmp_path / "day1_consultation01.json"
      src.write_text(json.dumps({"presenting_complaint": "X"}))   # note field missing
      dest = tmp_path / "primock57"
      from utils.preset_data_parser.primock57.parser import _process_file
      result = _process_file(src, dest, overwrite=False)
      assert result == "error"
  ```

  **PRD §7.5 — Source resolution (two tests):**
  ```python
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
      # notes/ has no child named "notes/" — treated as the notes dir itself
      assert _resolve_notes_dir(notes) == notes
  ```

  **PRD §7.6 — End-to-end via `main()`:**
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
      from utils.preset_data_parser.primock57.parser import main
      main()
      assert len(list((dest / "primock57").iterdir())) == 3
      for i in range(3):
          f = dest / "primock57" / f"day1-consultation0{i+1}" / "consultation_notes.txt"
          assert f.exists()
          assert f"Complaint {i}" in f.read_text()
  ```

- **Acceptance criteria:**
  - `pytest tests/utils/test_preset_data_parser_primock57.py -v` from `backend/` — all 10 tests collected and pass.
  - No test is skipped.
  - The existing `pytest tests/utils/test_preset_data.py` still passes (no side effects).

---

## Summary of what requires you (not a dev agent)

These steps from PRD §8 cannot be automated and must be done manually after the dev agent lands all tasks above:

1. **Download primock57 source** — the parser does not download anything. Clone it manually:
   ```bash
   git clone https://github.com/Sydney-Informatics-Hub/primock57 /tmp/primock57
   ```

2. **Run the parser** from the repo root:
   ```bash
   python -m backend.utils.preset_data_parser.primock57.parser \
       --source /tmp/primock57
   ```
   Expected output: `primock57 parser: 57 written, 0 skipped, 0 errors`

3. **Verify the output** structure:
   ```bash
   ls preset-data/primock57/ | head -5
   cat preset-data/primock57/day1-consultation01/consultation_notes.txt
   ```
   Expected file content: two lines — `Presenting Complaint: ...` then `Notes: ...`

4. **Commit the generated files** (the `.gitignore` `!preset-data/**/*.txt` rule already tracks them):
   ```bash
   git add preset-data/primock57/
   git commit -m "Add primock57 preset data (57 consultations)"
   ```

5. **Do NOT commit the primock57 clone.** The `.gitignore` rules added in Task 4 exclude it. Delete `/tmp/primock57` once the generated files are committed.
