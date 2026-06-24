#!/usr/bin/env python3
"""
Parse PriMock57 TextGrid transcripts into conversation format.

Dataset source: https://github.com/babylonhealth/primock57
Transcripts: https://github.com/babylonhealth/primock57/blob/main/transcripts/

PriMock57 is a dataset of 57 mock primary care consultations with paired
doctor and patient TextGrid transcripts in Praat format.

Usage:
    # Download and parse all consultations from GitHub:
    python parse_primock57_conversations.py

    # Parse from a local directory of TextGrid files:
    python parse_primock57_conversations.py --local-dir /path/to/textgrid/files

    # Parse specific consultations:
    python parse_primock57_conversations.py --consultations day1_consultation01 day1_consultation02

    # Specify custom output directory:
    python parse_primock57_conversations.py --output-dir /path/to/output
"""

import re
import os
import sys
import argparse
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# GitHub raw base URL for transcripts
GITHUB_BASE_URL = "https://raw.githubusercontent.com/babylonhealth/primock57/main/transcripts"

# Default output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "preset-data" / "primock57-conversations"

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


def clean_text(text: str) -> str:
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
        text = clean_text(interval.text)
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


def main():
    parser = argparse.ArgumentParser(
        description="Parse PriMock57 TextGrid transcripts into conversation format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--local-dir",
        metavar="DIR",
        help="Local directory containing TextGrid files (skips GitHub download)",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
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
    args = parser.parse_args()

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

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
