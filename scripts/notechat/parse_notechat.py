#!/usr/bin/env python3
"""
Parse NoteChat dataset and save samples to preset-data.

Dataset source: https://huggingface.co/datasets/akemiH/NoteChat

NoteChat contains 207,001 synthetic patient-physician dialogues conditioned on
clinical notes (EHR summaries).  Each entry pairs a structured clinical note
with a realistic multi-turn conversation between a simulated patient and a
simulated physician.

Key fields:
  - data         (str): clinical note / EHR summary
  - conversation (str): multi-turn dialogue between patient and physician

Output structure per sample:
  preset-data/notechat/[sample-id]/clinical_note.txt
  preset-data/notechat/[sample-id]/conversation.txt

Sample IDs are zero-padded six-digit integers: 000000, 000001, ...

Usage:
  python parse_notechat.py               # process first 50 samples (default)
  python parse_notechat.py --limit 10    # process first 10 samples
  python parse_notechat.py --limit 0     # process ALL samples (901 MB download!)
"""

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# HuggingFace dataset identifier
DATASET_ID = "akemiH/NoteChat"

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "preset-data",
    "notechat",
)

DEFAULT_LIMIT = 50  # Safe default — avoids downloading the full 901 MB dataset

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and parse NoteChat samples into preset-data/notechat/."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            f"Maximum number of samples to process (default: {DEFAULT_LIMIT}). "
            "Set to 0 to process all samples (downloads ~901 MB)."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sample_id(index: int) -> str:
    """Return a zero-padded six-digit sample identifier string."""
    return f"{index:06d}"


def write_file(path: str, content: str) -> None:
    """Write *content* to *path*, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    limit: int = args.limit

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: 'datasets' package is not installed.", file=sys.stderr)
        print("Install it with:  pip install datasets", file=sys.stderr)
        sys.exit(1)

    print(f"Loading NoteChat from HuggingFace ({DATASET_ID}) in streaming mode …")
    # streaming=True avoids downloading the full 901 MB corpus up-front.
    dataset = load_dataset(DATASET_ID, split="train", streaming=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    count = 0
    skipped = 0

    for i, row in enumerate(dataset):
        if limit > 0 and count >= limit:
            break

        clinical_note: str = (row.get("data") or "").strip()
        conversation: str = (row.get("conversation") or "").strip()

        # Skip rows that are missing both fields — nothing useful to save.
        if not clinical_note and not conversation:
            skipped += 1
            continue

        sid = sample_id(count)
        sample_dir = os.path.join(OUTPUT_DIR, sid)

        write_file(os.path.join(sample_dir, "clinical_note.txt"), clinical_note)
        write_file(os.path.join(sample_dir, "conversation.txt"), conversation)

        count += 1

        if count % 10 == 0 or count == 1:
            print(f"  Saved {count} sample(s) …")

    print(f"\nDone. {count} sample(s) saved to {OUTPUT_DIR}/")
    if skipped:
        print(f"  ({skipped} row(s) skipped — both fields were empty)")


if __name__ == "__main__":
    main()
