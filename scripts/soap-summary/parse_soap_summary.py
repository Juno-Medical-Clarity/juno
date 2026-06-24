#!/usr/bin/env python3
"""
Parse SubashNeupane/dataset_SOAP_summary from HuggingFace into per-sample files.

Dataset source: https://huggingface.co/datasets/SubashNeupane/dataset_SOAP_summary

The dataset contains 1,473 patient-doctor conversation transcripts paired with
structured SOAP note summaries. Each record has three fields:
  - input:       Raw patient-doctor conversation transcript
  - output:      Structured SOAP note (Subjective, Objective, Assessment, Plan)
  - instruction: Standard prompt used for generating the SOAP note

Output layout:
  preset-data/soap-summary/[sample-id]/conversation.txt   — the dialogue (input field)
  preset-data/soap-summary/[sample-id]/soap_notes.txt     — the SOAP summary (output field)

Sample IDs are zero-padded integers: 0000, 0001, ..., 1472

Usage:
    python parse_soap_summary.py [--output-dir DIR] [--limit N] [--quiet]

    # Parse all samples to default output directory:
    python parse_soap_summary.py

    # Parse only the first 10 samples:
    python parse_soap_summary.py --limit 10

    # Specify a custom output directory:
    python parse_soap_summary.py --output-dir /path/to/output
"""

import sys
import argparse
from pathlib import Path

# Dataset identifier on HuggingFace Hub
DATASET_ID = "SubashNeupane/dataset_SOAP_summary"
DATASET_URL = "https://huggingface.co/datasets/SubashNeupane/dataset_SOAP_summary"

# Default output directory (relative to this script's location: scripts/soap-summary/ → preset-data/soap-summary/)
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "preset-data" / "soap-summary"


def load_dataset_hf():
    """
    Load the dataset using the HuggingFace datasets library.
    Returns the train split (the only split available).
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' library not found. Install with: pip install datasets", file=sys.stderr)
        sys.exit(1)

    print(f"Loading dataset '{DATASET_ID}' from HuggingFace Hub...")
    ds = load_dataset(DATASET_ID, split="train", trust_remote_code=False)
    print(f"  Loaded {len(ds)} samples.")
    return ds


def format_conversation(text: str, sample_id: str) -> str:
    """
    Wrap the raw conversation text with a header line.
    The input field already contains the full dialogue as-is.
    """
    lines = [
        f"# SOAP Summary Dataset — Sample {sample_id}",
        f"# Dataset: {DATASET_URL}",
        "",
        text.strip(),
        "",
    ]
    return "\n".join(lines)


def format_soap_notes(text: str, sample_id: str) -> str:
    """
    Wrap the SOAP note text with a header line.
    The output field already contains the structured SOAP note.
    """
    lines = [
        f"# SOAP Notes — Sample {sample_id}",
        f"# Dataset: {DATASET_URL}",
        "",
        text.strip(),
        "",
    ]
    return "\n".join(lines)


def process_sample(
    sample: dict,
    idx: int,
    output_dir: Path,
    verbose: bool = True,
) -> bool:
    """
    Write conversation.txt and soap_notes.txt for a single dataset sample.
    Returns True on success, False on failure.
    """
    sample_id = f"{idx:04d}"
    out_dir = output_dir / sample_id

    try:
        conversation_text = sample.get("input", "").strip()
        soap_text = sample.get("output", "").strip()

        if not conversation_text and not soap_text:
            print(f"  WARNING: Sample {sample_id} has empty input and output — skipping.", file=sys.stderr)
            return False

        out_dir.mkdir(parents=True, exist_ok=True)

        # Write conversation
        conv_file = out_dir / "conversation.txt"
        conv_file.write_text(
            format_conversation(conversation_text, sample_id),
            encoding="utf-8",
        )

        # Write SOAP notes
        soap_file = out_dir / "soap_notes.txt"
        soap_file.write_text(
            format_soap_notes(soap_text, sample_id),
            encoding="utf-8",
        )

        if verbose:
            print(f"  [{sample_id}] conversation: {len(conversation_text):,} chars, "
                  f"soap_notes: {len(soap_text):,} chars  → {out_dir}")

        return True

    except Exception as e:
        print(f"  ERROR processing sample {sample_id}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Parse SubashNeupane/dataset_SOAP_summary into per-sample text files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N samples (default: all)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-sample progress output",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    verbose = not args.quiet

    if verbose:
        print(f"SOAP Summary Dataset Parser")
        print(f"Dataset: {DATASET_URL}")
        print(f"Output:  {output_dir}")
        if args.limit:
            print(f"Limit:   {args.limit} samples")
        print()

    # Load dataset
    ds = load_dataset_hf()

    # Apply limit
    samples = ds if args.limit is None else ds.select(range(min(args.limit, len(ds))))
    total = len(samples)

    if verbose:
        print(f"\nProcessing {total} samples...\n")

    successes = 0
    failures = 0

    for idx, sample in enumerate(samples):
        ok = process_sample(
            sample=sample,
            idx=idx,
            output_dir=output_dir,
            verbose=verbose,
        )
        if ok:
            successes += 1
        else:
            failures += 1

    print()
    print(f"Done. {successes} succeeded, {failures} failed.")
    if successes > 0:
        print(f"Files saved to: {output_dir}")

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
