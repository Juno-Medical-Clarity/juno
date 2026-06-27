#!/usr/bin/env python3
"""
Parse MTS-Dialog dataset and save dialogue/summary pairs to preset-data.

Dataset source: https://github.com/abachaa/MTS-Dialog
HuggingFace mirror: https://huggingface.co/datasets/har1/MTS_Dialogue-Clinical_Note

MTS-Dialog is a collection of 1,700 short doctor-patient conversations paired
with clinical notes/summaries. Each row contains:
  - ID: integer identifier
  - section_header: clinical note section type (GENHX, CC, MEDICATIONS, etc.)
  - section_text: clinical summary / note content
  - dialogue: doctor-patient conversation text

Output structure per sample:
  preset-data/mts-dialog/sample-XXXX/conversation.txt
  preset-data/mts-dialog/sample-XXXX/summary.txt
"""

import os
import sys
import csv
import io
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_BASE = (
    "https://raw.githubusercontent.com/abachaa/MTS-Dialog/main/Main-Dataset"
)
DATASET_FILES = {
    "train": "MTS-Dialog-TrainingSet.csv",
    "validation": "MTS-Dialog-ValidationSet.csv",
}

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "preset-data",
    "mts-dialog",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_csv(url: str) -> list[dict]:
    """Download a CSV from *url* and return list of row dicts."""
    print(f"Fetching {url} ...")
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


def clean_dialogue(text: str) -> str:
    """Normalise the dialogue field to consistent line-per-turn format."""
    if not text:
        return ""
    # The raw data sometimes uses " / " as a turn separator; expand to newlines
    text = text.replace(" / ", "\n").replace("/\n", "\n")
    # Strip surrounding whitespace from each line
    lines = [line.strip() for line in text.splitlines()]
    # Remove empty lines at start/end but preserve internal blank lines for
    # readability between long turns
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def clean_summary(header: str, text: str) -> str:
    """Combine section header + section text into a readable summary block."""
    header = (header or "").strip()
    text = (text or "").strip()
    if header:
        return f"[{header}]\n{text}"
    return text


def sample_id(split: str, row_id: str) -> str:
    """Return a zero-padded sample identifier, e.g. 'train-0001'."""
    try:
        num = int(row_id)
    except (ValueError, TypeError):
        num = 0
    return f"{split}-{num:04d}"


def write_sample(sid: str, dialogue: str, summary: str) -> None:
    """Write conversation.txt and summary.txt for a single sample."""
    sample_dir = os.path.join(OUTPUT_DIR, sid)
    os.makedirs(sample_dir, exist_ok=True)

    conv_path = os.path.join(sample_dir, "conversation.txt")
    with open(conv_path, "w", encoding="utf-8") as f:
        f.write(dialogue)

    sum_path = os.path.join(sample_dir, "summary.txt")
    with open(sum_path, "w", encoding="utf-8") as f:
        f.write(summary)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(max_samples: int | None = None) -> None:
    """
    Download MTS-Dialog CSV files and emit preset-data files.

    Args:
        max_samples: If set, stop after writing this many samples total
                     (useful for quick testing).
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_written = 0

    for split, filename in DATASET_FILES.items():
        url = f"{GITHUB_BASE}/{filename}"
        rows = fetch_csv(url)
        print(f"  → {len(rows)} rows in '{split}' split")

        for row in rows:
            if max_samples is not None and total_written >= max_samples:
                break

            sid = sample_id(split, row.get("ID", str(total_written)))
            dialogue = clean_dialogue(row.get("dialogue", ""))
            summary = clean_summary(
                row.get("section_header", ""), row.get("section_text", "")
            )

            if not dialogue and not summary:
                continue  # skip empty rows

            write_sample(sid, dialogue, summary)
            total_written += 1

        if max_samples is not None and total_written >= max_samples:
            break

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
