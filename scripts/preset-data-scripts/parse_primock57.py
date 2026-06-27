#!/usr/bin/env python3
"""
PriMock57 dataset parser — two parsers in one file.

This file combines two complementary parsers for the PriMock57 dataset:

  1. Conversation Parser (mode: conversations)
     Downloads TextGrid audio transcripts from GitHub and converts them into
     readable conversation transcripts (preset-data/primock57/).
     Dataset: https://github.com/babylonhealth/primock57

  2. Notes Parser (mode: notes)
     Parses local JSON consultation notes files into plain-text notes
     (preset-data/primock57/).
     Dataset: https://github.com/Sydney-Informatics-Hub/primock57

Usage:
    # Parse TextGrid conversations from GitHub (downloads automatically):
    python parse_primock57.py conversations

    # Parse from a local directory of TextGrid files:
    python parse_primock57.py conversations --local-dir /path/to/textgrid/files

    # Parse local JSON notes files:
    python parse_primock57.py notes --source /path/to/primock57

    # Parse specific consultations (conversations mode):
    python parse_primock57.py conversations --consultations day1_consultation01 day1_consultation02

    # Specify custom output directory:
    python parse_primock57.py conversations --output-dir /path/to/output
    python parse_primock57.py notes --dest /path/to/juno/preset-data

    # Replace already-generated files (notes mode):
    python parse_primock57.py notes --source /path/to/primock57 --overwrite
"""

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ===========================================================================
# Section 1: TextGrid Conversation Parser
# ===========================================================================

# GitHub raw base URL for transcripts
GITHUB_BASE_URL = "https://raw.githubusercontent.com/babylonhealth/primock57/main/transcripts"

# Default output directory for conversations
DEFAULT_CONVERSATIONS_OUTPUT_DIR = (
    Path(__file__).parent.parent / "preset-data" / "primock57"
)

# All 57 consultations in the dataset
ALL_CONSULTATIONS = [
    "day1_consultation01", "day1_consultation02", "day1_consultation03",
    "day1_consultation04", "day1_consultation05", "day1_consultation06",
    "day1_consultation07", "day1_consultation08", "day1_consultation09",
    "day1_consultation10", "day1_consultation11", "day1_consultation12",
    "day1_consultation13", "day1_consultation14", "day1_consultation15",
    "day2_consultation01", "day2_consultation02", "day2_consultation03",
    "day2_consultation04", "day2_consultation05", "day2_consultation06",
    "day2_consultation07", "day2_consultation08", "day2_consultation09",
    "day2_consultation10",
    "day3_consultation01", "day3_consultation02", "day3_consultation03",
    "day3_consultation04", "day3_consultation05", "day3_consultation06",
    "day3_consultation07", "day3_consultation08", "day3_consultation09",
    "day3_consultation10",
    "day4_consultation01", "day4_consultation02", "day4_consultation03",
    "day4_consultation04", "day4_consultation05", "day4_consultation06",
    "day4_consultation07", "day4_consultation08", "day4_consultation09",
    "day4_consultation10",
    "day5_consultation01", "day5_consultation02", "day5_consultation03",
    "day5_consultation04", "day5_consultation05", "day5_consultation06",
    "day5_consultation07", "day5_consultation08", "day5_consultation09",
    "day5_consultation10", "day5_consultation11", "day5_consultation12",
]


@dataclass
class Interval:
    """A timed interval from a TextGrid file."""
    xmin: float
    xmax: float
    text: str
    speaker: str  # "Doctor" or "Patient"


def fetch_textgrid(consultation_id: str, role: str, local_dir: Optional[str] = None) -> str:
    """
    Fetch TextGrid content for a given consultation and role.
    Returns the raw text content of the file.
    """
    filename = f"{consultation_id}_{role}.TextGrid"

    if local_dir:
        path = Path(local_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"TextGrid file not found: {path}")
        return path.read_text(encoding="utf-8")
    else:
        url = f"{GITHUB_BASE_URL}/{filename}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to fetch {url}: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to fetch {url}: {e.reason}") from e


def parse_textgrid(content: str, speaker: str) -> list[Interval]:
    """
    Parse a Praat TextGrid file and extract all non-empty intervals.

    TextGrid format:
        intervals [N]:
            xmin = <float>
            xmax = <float>
            text = "<text>"

    Returns a list of Interval objects with non-empty text.
    """
    intervals = []

    # Split into interval blocks
    # Each block starts with "intervals [N]:"
    blocks = re.split(r'\s*intervals\s*\[\d+\]:\s*', content)

    for block in blocks[1:]:  # Skip preamble before first interval
        # Extract xmin
        xmin_match = re.search(r'xmin\s*=\s*([\d.eE+\-]+)', block)
        # Extract xmax
        xmax_match = re.search(r'xmax\s*=\s*([\d.eE+\-]+)', block)
        # Extract text - handles multi-line text and escaped quotes
        text_match = re.search(r'text\s*=\s*"(.*?)"(?:\s*$|\s*\n)', block, re.DOTALL)

        if not (xmin_match and xmax_match and text_match):
            continue

        xmin = float(xmin_match.group(1))
        xmax = float(xmax_match.group(1))
        text = text_match.group(1).strip()

        # Skip empty intervals (silence)
        if not text:
            continue

        intervals.append(Interval(
            xmin=xmin,
            xmax=xmax,
            text=text,
            speaker=speaker,
        ))

    return intervals


def clean_transcript_text(text: str) -> str:
    """
    Clean transcription markers from text.

    Markers in PriMock57:
        <UNSURE>word</UNSURE>   — transcriber was unsure about this word
        <UNIN/>                 — unintelligible speech segment
        <INAUDIBLE_SPEECH/>     — inaudible speech segment
        <UNSURE_WORD/>          — single unintelligible word
    """
    # Keep text inside <UNSURE> tags but remove the tags themselves
    text = re.sub(r'<UNSURE>(.*?)</UNSURE>', r'\1', text)
    # Replace self-closing unintelligible/inaudible markers with [unintelligible]
    text = re.sub(r'<(?:UNIN|INAUDIBLE_SPEECH|UNSURE_WORD)/>', '[unintelligible]', text)
    # Handle any other self-closing XML-style tags that appear as markers
    text = re.sub(r'<[A-Z_]+/>', '[unintelligible]', text)
    # Handle any remaining open/close tags by keeping inner content
    text = re.sub(r'<[A-Z_]+>(.*?)</[A-Z_]+>', r'\1', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def merge_transcripts(doctor_intervals: list[Interval], patient_intervals: list[Interval]) -> list[Interval]:
    """
    Merge doctor and patient intervals into a single chronological list.
    Sort by xmin (start time). When intervals overlap in time, use xmin to order.
    Consecutive utterances from the same speaker are merged into one.
    """
    all_intervals = sorted(
        doctor_intervals + patient_intervals,
        key=lambda iv: iv.xmin,
    )

    # Merge consecutive same-speaker utterances
    merged = []
    for interval in all_intervals:
        if merged and merged[-1].speaker == interval.speaker:
            # Extend the previous interval
            prev = merged[-1]
            merged[-1] = Interval(
                xmin=prev.xmin,
                xmax=interval.xmax,
                text=prev.text + " " + interval.text,
                speaker=prev.speaker,
            )
        else:
            merged.append(Interval(
                xmin=interval.xmin,
                xmax=interval.xmax,
                text=interval.text,
                speaker=interval.speaker,
            ))

    return merged


def format_conversation(intervals: list[Interval], consultation_id: str) -> str:
    """
    Format the merged intervals as a readable conversation transcript.
    """
    lines = [
        f"# PriMock57 Consultation Transcript: {consultation_id}",
        f"# Source: {GITHUB_BASE_URL}/",
        f"# Dataset: https://github.com/babylonhealth/primock57",
        "",
    ]

    for interval in intervals:
        text = clean_transcript_text(interval.text)
        if text:
            lines.append(f"{interval.speaker}: {text}")
            lines.append("")  # blank line between turns

    return "\n".join(lines).rstrip() + "\n"


def process_consultation(
    consultation_id: str,
    output_dir: Path,
    local_dir: Optional[str] = None,
    verbose: bool = True,
) -> bool:
    """
    Download (or read locally), parse, merge, and save a single consultation.
    Returns True on success, False on failure.
    """
    # Convert underscore format (day1_consultation01) to hyphen format for output dir
    folder_name = consultation_id.replace("_", "-")
    out_dir = output_dir / folder_name
    out_file = out_dir / "conversation.txt"

    if verbose:
        print(f"  Processing {consultation_id}...")

    try:
        # Fetch doctor and patient TextGrids
        doctor_content = fetch_textgrid(consultation_id, "doctor", local_dir)
        patient_content = fetch_textgrid(consultation_id, "patient", local_dir)

        # Parse intervals
        doctor_intervals = parse_textgrid(doctor_content, "Doctor")
        patient_intervals = parse_textgrid(patient_content, "Patient")

        if verbose:
            print(f"    Doctor: {len(doctor_intervals)} utterances, "
                  f"Patient: {len(patient_intervals)} utterances")

        # Merge and format
        merged = merge_transcripts(doctor_intervals, patient_intervals)
        conversation = format_conversation(merged, consultation_id)

        # Write output
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(conversation, encoding="utf-8")

        if verbose:
            print(f"    Saved to {out_file}")

        return True

    except Exception as e:
        print(f"    ERROR processing {consultation_id}: {e}", file=sys.stderr)
        return False


def main_conversations(argv=None) -> int:
    """Run the TextGrid conversation parser. Returns exit code."""
    parser = argparse.ArgumentParser(
        description="Parse PriMock57 TextGrid transcripts into conversation format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--local-dir",
        metavar="DIR",
        help="Local directory containing TextGrid files (skips GitHub download)",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(DEFAULT_CONVERSATIONS_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_CONVERSATIONS_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--consultations",
        nargs="+",
        metavar="ID",
        help="Specific consultation IDs to process (e.g. day1_consultation01). "
             "Defaults to all 57 consultations.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    consultations = args.consultations or ALL_CONSULTATIONS
    verbose = not args.quiet

    if verbose:
        source = f"local directory: {args.local_dir}" if args.local_dir else f"GitHub ({GITHUB_BASE_URL}/)"
        print(f"PriMock57 Conversation Parser")
        print(f"Source: {source}")
        print(f"Output: {output_dir}")
        print(f"Consultations: {len(consultations)}")
        print()

    successes = 0
    failures = 0

    for consultation_id in consultations:
        ok = process_consultation(
            consultation_id=consultation_id,
            output_dir=output_dir,
            local_dir=args.local_dir,
            verbose=verbose,
        )
        if ok:
            successes += 1
        else:
            failures += 1

    if verbose:
        print()
        print(f"Done. {successes} succeeded, {failures} failed.")
        if failures == 0:
            print(f"Conversations saved to: {output_dir}")

    return 0 if failures == 0 else 1


# ===========================================================================
# Section 2: Notes Parser (offline ingestion of local JSON notes)
# ===========================================================================

_DEFAULT_NOTES_DEST = Path(__file__).resolve().parents[2] / "preset-data"


def _resolve_notes_dir(source: Path) -> Path:
    candidate = source / "notes"
    if candidate.is_dir():
        return candidate
    return source


def _process_notes_file(json_path: Path, dest_root: Path, overwrite: bool) -> str:
    """Process one JSON notes file. Returns 'written', 'skipped', or 'error'."""
    input_id = json_path.stem.replace("_", "-")
    out_dir = dest_root / input_id
    out_file = out_dir / "consultation_notes.txt"

    if out_file.exists() and not overwrite:
        print(
            f"WARNING: skipping {json_path.name} — {out_file} already exists "
            "(pass --overwrite to replace)",
            file=sys.stderr,
        )
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
    if not isinstance(complaint, str):
        print(
            f"WARNING: {json_path}: 'presenting_complaint' is not a string — coercing to empty string",
            file=sys.stderr,
        )
        complaint = ""

    note = data["note"]
    if not isinstance(note, str):
        print(
            f"WARNING: {json_path}: 'note' is not a string — coercing to empty string",
            file=sys.stderr,
        )
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


def main_notes(argv=None) -> int:
    """Run the JSON notes parser. Returns exit code."""
    parser = argparse.ArgumentParser(description="primock57 notes parser")
    parser.add_argument("--source", required=True, type=Path,
                        help="Path to the primock57 dataset directory (containing notes/ or JSON files)")
    parser.add_argument("--dest", type=Path, default=_DEFAULT_NOTES_DEST,
                        help=f"Root preset-data directory (default: {_DEFAULT_NOTES_DEST})")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"ERROR: --source path does not exist: {args.source}", file=sys.stderr)
        return 1

    notes_dir = _resolve_notes_dir(args.source)
    json_files = sorted(notes_dir.glob("*.json"))

    if not json_files:
        print(f"WARNING: no .json files found in {notes_dir}", file=sys.stderr)
        return 0

    dest_root = args.dest / "primock57"
    written = skipped = errors = 0

    for json_path in json_files:
        result = _process_notes_file(json_path, dest_root, args.overwrite)
        if result == "written":
            written += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

    if skipped > 0:
        print(
            f"primock57 parser: {written} written, {skipped} skipped "
            "(pass --overwrite to replace), {errors} errors"
        )
    else:
        print(f"primock57 parser: {written} written, {skipped} skipped, {errors} errors")

    return 1 if errors > 0 else 0


# ===========================================================================
# Dispatch main
# ===========================================================================

def main():
    """
    Dispatch to the appropriate sub-parser based on the first positional argument.

    Usage:
        python parse_primock57.py conversations [options]
        python parse_primock57.py notes --source /path/to/primock57 [options]
    """
    if len(sys.argv) < 2 or sys.argv[1] not in ("conversations", "notes"):
        print(
            "Usage: parse_primock57.py <mode> [options]\n"
            "\n"
            "Modes:\n"
            "  conversations  Parse TextGrid audio transcripts from GitHub into conversations\n"
            "  notes          Parse local JSON consultation notes files\n"
            "\n"
            "Run 'parse_primock57.py conversations --help' or 'parse_primock57.py notes --help'\n"
            "for mode-specific options.",
            file=sys.stderr,
        )
        sys.exit(1)

    mode = sys.argv[1]
    remaining = sys.argv[2:]

    if mode == "conversations":
        sys.exit(main_conversations(remaining))
    else:
        sys.exit(main_notes(remaining))


if __name__ == "__main__":
    main()
