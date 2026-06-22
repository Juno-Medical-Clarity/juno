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

import argparse
import json
import sys
from pathlib import Path

_DEFAULT_DEST = Path(__file__).resolve().parents[4] / "preset-data"


def _resolve_notes_dir(source: Path) -> Path:
    candidate = source / "notes"
    if candidate.is_dir():
        return candidate
    return source


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="primock57 parser")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--dest", type=Path, default=_DEFAULT_DEST)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _process_file(json_path: Path, dest_root: Path, overwrite: bool) -> str:
    """Process one JSON file. Returns 'written', 'skipped', or 'error'."""
    input_id = json_path.stem.replace("_", "-")
    out_dir = dest_root / input_id
    out_file = out_dir / "consultation_notes.txt"

    if out_file.exists() and not overwrite:
        print(f"WARNING: skipping {json_path.name} — {out_file} already exists (pass --overwrite to replace)", file=sys.stderr)
        return "skipped"

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {json_path}: invalid JSON — {e}", file=sys.stderr)
        return "error"

    if "presenting_complaint" not in data:
        print(f"ERROR: {json_path}: missing 'presenting_complaint' field", file=sys.stderr)
        return "error"
    if "note" not in data:
        print(f"ERROR: {json_path}: missing 'note' field", file=sys.stderr)
        return "error"

    complaint = data["presenting_complaint"]
    if not isinstance(complaint, str) or complaint is None:
        print(f"WARNING: {json_path}: 'presenting_complaint' is not a string — coercing to empty string", file=sys.stderr)
        complaint = ""

    note = data["note"]
    if not isinstance(note, str) or note is None:
        print(f"WARNING: {json_path}: 'note' is not a string — coercing to empty string", file=sys.stderr)
        note = ""

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: {json_path}: could not create output directory {out_dir} — {e}", file=sys.stderr)
        return "error"

    try:
        out_file.write_text(f"Presenting Complaint: {complaint}\nNotes: {note}", encoding="utf-8")
    except OSError as e:
        print(f"ERROR: {json_path}: could not write {out_file} — {e}", file=sys.stderr)
        return "error"

    return "written"


def main() -> None:
    args = _parse_args()

    if not args.source.exists():
        print(f"ERROR: --source path does not exist: {args.source}", file=sys.stderr)
        sys.exit(1)

    notes_dir = _resolve_notes_dir(args.source)
    json_files = sorted(notes_dir.glob("*.json"))

    if not json_files:
        print(f"WARNING: no .json files found in {notes_dir}", file=sys.stderr)
        sys.exit(0)

    dest_root = args.dest / "primock57"
    written = skipped = errors = 0

    for json_path in json_files:
        result = _process_file(json_path, dest_root, args.overwrite)
        if result == "written":
            written += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    if skipped > 0:
        print(f"primock57 parser: {written} written, {skipped} skipped (pass --overwrite to replace), {errors} errors")
    else:
        print(f"primock57 parser: {written} written, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
