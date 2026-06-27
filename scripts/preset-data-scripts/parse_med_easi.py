#!/usr/bin/env python3
"""
Parse Med-EASi dataset and save expert/simplified text pairs to preset-data.

Dataset source: https://huggingface.co/datasets/cbasu/Med-EASi

Med-EASi (Medical dataset for Elaborative and Abstractive Simplification) is a
finely annotated dataset of 1,979 expert-simple medical text pairs. Each record
contains:
  - Expert:    The original complex medical text written for healthcare professionals
  - Simple:    The patient-friendly simplified version of the medical text
  - Annotation: Markup showing transformations (replacement, elaboration,
                insertion, deletion)
  - Additional readability, similarity, and UMLS concept fields

Output structure per sample:
  preset-data/med-easi/[split]-[NNNN]/original.txt    (expert/complex medical text)
  preset-data/med-easi/[split]-[NNNN]/simplified.txt  (patient-friendly version)
"""

import csv
import io
import os
import sys

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HF_BASE = "https://huggingface.co/datasets/cbasu/Med-EASi/resolve/main"
DATASET_FILES = {
    "train": "train.csv",
    "validation": "validation.csv",
    "test": "test.csv",
}

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "preset-data",
    "med-easi",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_csv(url: str) -> list[dict]:
    """Download a CSV from *url* and return a list of row dicts."""
    print(f"Fetching {url} ...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


def clean_text(text: str) -> str:
    """Strip surrounding whitespace and normalise line endings."""
    if not text:
        return ""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


def sample_id(split: str, idx: str, row_num: int) -> str:
    """Return a zero-padded sample identifier, e.g. 'train-0001'."""
    try:
        num = int(idx)
    except (ValueError, TypeError):
        num = row_num
    return f"{split}-{num:04d}"


def write_sample(sid: str, expert: str, simple: str) -> None:
    """Write original.txt and simplified.txt for a single sample."""
    sample_dir = os.path.join(OUTPUT_DIR, sid)
    os.makedirs(sample_dir, exist_ok=True)

    with open(os.path.join(sample_dir, "original.txt"), "w", encoding="utf-8") as f:
        f.write(expert)

    with open(os.path.join(sample_dir, "simplified.txt"), "w", encoding="utf-8") as f:
        f.write(simple)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(max_samples: int | None = None) -> None:
    """
    Download Med-EASi CSV files and emit preset-data files.

    Args:
        max_samples: If set, stop after writing this many samples total
                     (useful for quick testing).
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_written = 0

    for split, filename in DATASET_FILES.items():
        if max_samples is not None and total_written >= max_samples:
            break

        url = f"{HF_BASE}/{filename}"
        rows = fetch_csv(url)
        print(f"  → {len(rows)} rows in '{split}' split")

        for row_num, row in enumerate(rows):
            if max_samples is not None and total_written >= max_samples:
                break

            expert = clean_text(row.get("Expert", ""))
            simple = clean_text(row.get("Simple", ""))

            if not expert and not simple:
                continue  # skip empty rows

            sid = sample_id(split, row.get("idx", ""), row_num)
            write_sample(sid, expert, simple)
            total_written += 1

        print(f"     Written so far: {total_written}")

    print(f"\nDone. Wrote {total_written} samples to {OUTPUT_DIR}")


if __name__ == "__main__":
    # Optional CLI arg: number of samples to generate (default = all)
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"Usage: {sys.argv[0]} [max_samples]", file=sys.stderr)
            sys.exit(1)

    main(max_samples=limit)
