#!/usr/bin/env python3
"""
Parse Smith Collection (Fareez et al. 2022) simulated patient-physician medical
interview transcripts into per-sample conversation files.

Dataset:
  Title:   A dataset of simulated patient-physician medical interviews with a
           focus on respiratory cases
  Authors: Faiha Fareez, Tishya Parikh, Christopher Wavell, Saba Shahab,
           Meghan Chevalier, Scott Good, Isabella De Blasi, Christopher W. Smith
  Journal: Scientific Data (2022)
  DOI:     https://doi.org/10.1038/s41597-022-01423-1
  Data:    https://doi.org/10.6084/m9.figshare.c.5545842.v1
  HuggingFace mirror (transcripts only):
           https://huggingface.co/datasets/yfyeung/medical

Dataset overview:
  - 272 simulated OSCE (Objective Structured Clinical Examination) conversations
  - Case categories (3-letter prefix + 4-digit ID):
      RES  Respiratory     (213 cases — the primary focus)
      MSK  Musculoskeletal ( 46 cases)
      GAS  Gastrointestinal(  6 cases)
      CAR  Cardiac         (  5 cases)
      DER  Dermatological  (  1 case)
      GEN  General         (  1 case)
  - Each case: audio (.mp3) + manually corrected plaintext transcript (.txt)
  - Average conversation length: ~12 minutes

Transcript format:
  - Plain text, ALL CAPS (ASR output, manually corrected)
  - Lines alternate: Doctor (odd lines), Patient (even lines)
  - No explicit speaker labels in the source files
  - The parser adds "Doctor:" / "Patient:" prefixes

Usage:
    # Download transcripts from HuggingFace and parse all 272 cases:
    python parse_smith_collection.py

    # Parse from a local directory of .txt files:
    python parse_smith_collection.py --local-dir /path/to/cleantext/

    # Parse only respiratory cases:
    python parse_smith_collection.py --category RES

    # Parse specific cases:
    python parse_smith_collection.py --cases RES0001 RES0002 CAR0001

    # Custom output directory:
    python parse_smith_collection.py --output-dir /path/to/output
"""

import os
import sys
import re
import tarfile
import argparse
import urllib.request
import urllib.error
import tempfile
from pathlib import Path

# HuggingFace mirror — transcripts only (audio is ~1 GB, not downloaded here)
HF_CLEANTEXT_URL = (
    "https://huggingface.co/datasets/yfyeung/medical/resolve/main/cleantext.tar.gz"
)

# Original Figshare collection (requires browser/account for bulk download)
FIGSHARE_COLLECTION_URL = (
    "https://springernature.figshare.com/collections/"
    "A_dataset_of_simulated_patient-physician_medical_interviews_"
    "with_a_focus_on_respiratory_cases/5545842/1"
)

# Default output directory (relative to this script's location)
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "preset-data" / "smith-collection"

# Known case categories
CATEGORIES = {
    "RES": "Respiratory",
    "MSK": "Musculoskeletal",
    "GAS": "Gastrointestinal",
    "CAR": "Cardiac",
    "DER": "Dermatological",
    "GEN": "General",
}


def download_transcripts(dest_dir: Path, verbose: bool = True) -> Path:
    """
    Download cleantext.tar.gz from HuggingFace and extract to dest_dir.
    Returns the path to the directory containing .txt files.
    """
    tar_path = dest_dir / "cleantext.tar.gz"

    if verbose:
        print(f"Downloading transcripts from HuggingFace...")
        print(f"  URL: {HF_CLEANTEXT_URL}")

    try:
        with urllib.request.urlopen(HF_CLEANTEXT_URL, timeout=120) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tar_path, "wb") as f:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if verbose and total:
                        pct = downloaded / total * 100
                        print(f"\r  {downloaded // 1024:,} KB / {total // 1024:,} KB ({pct:.1f}%)", end="", flush=True)
        if verbose:
            print(f"\r  Downloaded {downloaded // 1024:,} KB                          ")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Failed to download transcripts: {e.reason}\n"
            f"  Try manually downloading from:\n"
            f"    {HF_CLEANTEXT_URL}\n"
            f"  or the Figshare collection:\n"
            f"    {FIGSHARE_COLLECTION_URL}"
        ) from e

    if verbose:
        print(f"  Extracting archive...")

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(dest_dir)

    # The archive extracts into a "cleantext/" subdirectory
    txt_dir = dest_dir / "cleantext"
    if not txt_dir.is_dir():
        # Fall back: look for any directory containing .txt files
        candidates = [d for d in dest_dir.iterdir() if d.is_dir()]
        txt_dir = candidates[0] if candidates else dest_dir

    if verbose:
        n = len(list(txt_dir.glob("*.txt")))
        print(f"  Extracted {n} transcript files to {txt_dir}")

    return txt_dir


def _read_transcript_bytes(txt_path: Path) -> str:
    """
    Read a transcript file, handling multiple encodings found in the dataset.

    Most files are plain UTF-8 (ALL CAPS, no speaker labels).
    Two files (RES0002, RES0054) are UTF-16-LE with BOM and have explicit
    D/P speaker labels, likely created with a different editor.
    """
    raw = txt_path.read_bytes()

    # UTF-16 BOM: FF FE (little-endian) or FE FF (big-endian)
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        # Strip non-printable/non-ASCII bytes introduced by UTF-16 null bytes
        text = raw.decode('latin-1')
        # Remove null bytes and other control characters except newlines/CR
        text = re.sub(r'[^\x20-\x7E\n\r]', '', text)
        return text

    # Standard UTF-8
    return raw.decode('utf-8', errors='replace')


def parse_transcript(txt_path: Path) -> list[tuple[str, str]]:
    """
    Parse a Smith Collection transcript file into a list of (speaker, text) tuples.

    Two transcript formats exist in the dataset:

    Format A (270 files): Plain UTF-8, ALL CAPS, one utterance per line,
        alternating Doctor (odd lines) / Patient (even lines). No speaker labels.

    Format B (2 files: RES0002, RES0054): UTF-16-LE with BOM, explicit D/P
        speaker labels at the start of each line (e.g. "D   What brings you in").

    Lines are ALL CAPS in both formats; this function title-cases them for
    readability.

    Returns a list of (speaker, text) tuples, e.g.:
        [("Doctor", "What brings you in today?"),
         ("Patient", "I've had chest pain for a week."), ...]
    """
    raw = _read_transcript_bytes(txt_path)
    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]  # drop blank lines

    # Detect format: explicit D/P labels vs. alternating lines
    # Two files (RES0002, RES0054) start lines with "D <text>" or "P <text>"
    has_dp_labels = bool(lines and re.match(r'^[DP]\s', lines[0]))

    turns = []

    if has_dp_labels:
        # Format B: explicit speaker labels "D <text>" / "P <text>"
        for line in lines:
            m = re.match(r'^(D|P)\s+(.*)', line)
            if not m:
                continue
            speaker = "Doctor" if m.group(1) == "D" else "Patient"
            text = m.group(2).strip()
            text = _normalize_text(text)
            if text:
                turns.append((speaker, text))
    else:
        # Format A: alternating lines, Doctor starts first
        for i, line in enumerate(lines):
            speaker = "Doctor" if i % 2 == 0 else "Patient"
            text = _normalize_text(line)
            if text:
                turns.append((speaker, text))

    return turns


def _normalize_text(text: str) -> str:
    """
    Normalize a transcript line: title-case ALL CAPS and fix common abbreviations.
    """
    # Title-case the ALL-CAPS text for readability
    text = text.capitalize()
    # Restore common abbreviations that capitalize incorrectly
    text = re.sub(r'\bOk\b', 'OK', text)
    text = re.sub(r'\bUm\b', 'um', text)
    text = re.sub(r'\bUh\b', 'uh', text)
    return text.strip()


def format_conversation(turns: list[tuple[str, str]], case_id: str) -> str:
    """
    Format a list of (speaker, text) turns as a readable conversation transcript.
    """
    category = case_id[:3]
    category_name = CATEGORIES.get(category, "Unknown")

    lines = [
        f"# Smith Collection Transcript: {case_id}",
        f"# Category: {category} ({category_name})",
        f"# Dataset DOI: https://doi.org/10.1038/s41597-022-01423-1",
        f"# Data DOI:    https://doi.org/10.6084/m9.figshare.c.5545842.v1",
        f"# HuggingFace: https://huggingface.co/datasets/yfyeung/medical",
        f"# License:     CC BY 4.0",
        f"# Format: Simulated OSCE patient-physician medical interview",
        f"#         Lines alternate Doctor/Patient starting with Doctor.",
        "",
    ]

    for speaker, text in turns:
        lines.append(f"{speaker}: {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def process_case(
    case_id: str,
    txt_dir: Path,
    output_dir: Path,
    verbose: bool = True,
) -> bool:
    """
    Parse a single case transcript and write conversation.txt to output_dir/case_id/.
    Returns True on success, False on failure.
    """
    txt_path = txt_dir / f"{case_id}.txt"
    if not txt_path.exists():
        print(f"  WARNING: {txt_path} not found — skipping {case_id}", file=sys.stderr)
        return False

    out_dir = output_dir / case_id
    out_file = out_dir / "conversation.txt"

    try:
        turns = parse_transcript(txt_path)
        conversation = format_conversation(turns, case_id)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(conversation, encoding="utf-8")

        if verbose:
            print(f"  {case_id}: {len(turns)} turns -> {out_file}")

        return True

    except Exception as e:
        print(f"  ERROR processing {case_id}: {e}", file=sys.stderr)
        return False


def discover_cases(txt_dir: Path, category: str | None = None) -> list[str]:
    """
    Discover all case IDs in txt_dir, optionally filtered by category prefix.
    Returns sorted list of case IDs (e.g. ["CAR0001", "RES0001", ...]).
    """
    pattern = f"{category}*.txt" if category else "*.txt"
    cases = sorted(p.stem for p in txt_dir.glob(pattern))
    return cases


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Parse Smith Collection simulated medical interview transcripts "
            "into per-sample conversation files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--local-dir",
        metavar="DIR",
        help=(
            "Local directory containing .txt transcript files "
            "(skips HuggingFace download). "
            "Pass the cleantext/ subdirectory extracted from cleantext.tar.gz."
        ),
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--category",
        metavar="CAT",
        choices=list(CATEGORIES.keys()),
        help=(
            "Process only cases from this category "
            f"(choices: {', '.join(CATEGORIES)})"
        ),
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        metavar="ID",
        help="Specific case IDs to process (e.g. RES0001 CAR0001). Overrides --category.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case progress output",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    verbose = not args.quiet

    if verbose:
        print("Smith Collection Parser")
        print(f"Dataset: https://doi.org/10.1038/s41597-022-01423-1")
        print(f"Output:  {output_dir}")
        print()

    # Determine source of transcript files
    if args.local_dir:
        txt_dir = Path(args.local_dir)
        if not txt_dir.is_dir():
            print(f"ERROR: --local-dir {txt_dir} is not a directory", file=sys.stderr)
            sys.exit(1)
        if verbose:
            print(f"Using local transcript directory: {txt_dir}")
    else:
        # Download from HuggingFace
        with tempfile.TemporaryDirectory(prefix="smith-collection-") as tmpdir:
            txt_dir = download_transcripts(Path(tmpdir), verbose=verbose)
            # Move extracted files to a persistent temp location so we can process them
            import shutil
            persistent = Path(tmpdir + "_extracted")
            shutil.copytree(txt_dir, persistent)
            txt_dir = persistent

    # Determine which cases to process
    if args.cases:
        case_ids = args.cases
        if verbose:
            print(f"Cases: {len(case_ids)} specified on command line")
    else:
        case_ids = discover_cases(txt_dir, category=args.category)
        if args.category:
            if verbose:
                print(f"Cases: {len(case_ids)} in category {args.category} ({CATEGORIES[args.category]})")
        else:
            if verbose:
                # Show category breakdown
                by_cat: dict[str, int] = {}
                for cid in case_ids:
                    cat = cid[:3]
                    by_cat[cat] = by_cat.get(cat, 0) + 1
                print(f"Cases: {len(case_ids)} total")
                for cat, n in sorted(by_cat.items()):
                    print(f"  {cat} ({CATEGORIES.get(cat, '?')}): {n}")

    print()

    successes = 0
    failures = 0

    for case_id in case_ids:
        ok = process_case(
            case_id=case_id,
            txt_dir=txt_dir,
            output_dir=output_dir,
            verbose=verbose,
        )
        if ok:
            successes += 1
        else:
            failures += 1

    # Clean up the persistent temp directory if we created it
    if not args.local_dir and "persistent" in str(txt_dir):
        import shutil
        try:
            shutil.rmtree(str(txt_dir))
        except Exception:
            pass

    if verbose:
        print()
        print(f"Done. {successes} succeeded, {failures} failed.")
        if successes > 0:
            print(f"Conversations saved to: {output_dir}")

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
