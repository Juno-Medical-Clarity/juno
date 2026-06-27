#!/usr/bin/env python3
"""
Parse MedDialog (English) dataset and save conversations to preset-data.

Dataset source: https://github.com/UCSD-AI4H/Medical-Dialogue-System
HuggingFace mirror: https://huggingface.co/datasets/lighteval/med_dialog

MedDialog is a large-scale medical dialogue dataset.  The English portion
contains ~228,000 dialogues sourced from healthcaremagic.com (~181,000) and
icliniq.com (~25,000).

We use the 'lighteval/med_dialog' dataset (parquet format, no loading script)
which has two configs:
  - 'healthcaremagic': 181,122 train + 22,641 val + 22,642 test
  - 'icliniq':          24,851 train +  3,105 val +  3,108 test

Each entry has:
  - src (str): full conversation with "Patient: ..." and "Doctor: ..." turns
  - tgt (str): brief title/summary of the consultation
  - id  (int): numeric identifier

Output structure per sample:
  preset-data/meddialog/[source]-[split]-[id]/conversation.txt

conversation.txt format:
  Patient: <utterance text>
  Doctor: <response text>

Usage:
  python parse_meddialog.py            # process all samples (both sources)
  python parse_meddialog.py --limit 20 # process first 20 samples (testing)
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Dataset configs to pull from (English only)
DATASET_ID = "lighteval/med_dialog"
DATASET_CONFIGS = ["healthcaremagic", "icliniq"]
DATASET_SPLITS = ["train", "validation", "test"]

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "preset-data",
    "meddialog",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex to split the src string on speaker prefixes.
# Handles: "Patient: ...", "Doctor: ..." with optional whitespace.
_TURN_SPLIT_RE = re.compile(r"\b(Patient|Doctor)\s*:", re.IGNORECASE)


def parse_conversation(src: str) -> list[tuple[str, str]]:
    """
    Parse the flat conversation string into a list of (speaker, text) tuples.

    The `src` field contains text like:
        "Patient: I have a headache. Doctor: Take aspirin."

    Returns e.g.:
        [("Patient", "I have a headache."), ("Doctor", "Take aspirin.")]
    """
    parts = _TURN_SPLIT_RE.split(src.strip())
    # parts[0] is any text before first speaker (usually empty)
    # then [speaker, text, speaker, text, ...]
    turns: list[tuple[str, str]] = []
    i = 1
    while i < len(parts) - 1:
        speaker = parts[i].strip().capitalize()
        text = parts[i + 1].strip()
        if text:
            turns.append((speaker, text))
        i += 2
    return turns


def build_conversation(turns: list[tuple[str, str]]) -> str:
    """Render (speaker, text) pairs as a readable conversation string."""
    return "\n".join(f"{speaker}: {text}" for speaker, text in turns)


def sample_id(source: str, split: str, idx: int) -> str:
    """
    Return a filesystem-safe sample identifier.
    e.g. 'healthcaremagic-train-00042'
    """
    return f"{source}-{split}-{idx:06d}"


def write_sample(sid: str, conversation: str) -> None:
    """Write conversation.txt into preset-data/meddialog/<sid>/."""
    sample_dir = os.path.join(OUTPUT_DIR, sid)
    os.makedirs(sample_dir, exist_ok=True)
    conv_path = os.path.join(sample_dir, "conversation.txt")
    with open(conv_path, "w", encoding="utf-8") as fh:
        fh.write(conversation)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(limit: int | None = None) -> None:
    """
    Download and parse the MedDialog English dataset, then emit preset-data files.

    Args:
        limit: If set, stop after writing this many samples total (for testing).
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print(
            "ERROR: 'datasets' package not found. "
            "Install it with: pip install datasets",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_written = 0

    for config in DATASET_CONFIGS:
        print(f"\nLoading '{DATASET_ID}' config='{config}' …")
        ds_dict = load_dataset(DATASET_ID, config)

        for split in DATASET_SPLITS:
            if split not in ds_dict:
                print(f"  Split '{split}' not found — skipping.")
                continue

            split_data = ds_dict[split]
            print(f"  Split '{split}': {len(split_data)} examples")

            for idx in range(len(split_data)):
                if limit is not None and total_written >= limit:
                    break

                example = split_data[idx]
                src: str = example.get("src", "") or ""
                src = src.strip()

                if not src:
                    continue

                turns = parse_conversation(src)
                if not turns:
                    # Fall back: write raw src if parsing yields nothing
                    conversation = src
                else:
                    conversation = build_conversation(turns)

                sid = sample_id(config, split, idx)
                write_sample(sid, conversation)
                total_written += 1

            if limit is not None and total_written >= limit:
                break

        if limit is not None and total_written >= limit:
            break

    print(f"\nDone. Wrote {total_written} samples to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse MedDialog English dataset into preset-data files."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after writing N samples (useful for testing).",
    )
    args = parser.parse_args()
    main(limit=args.limit)
