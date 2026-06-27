#!/usr/bin/env python3
"""
Parse MeQSum dataset and save consumer health question / summary pairs to preset-data.

Dataset source: https://github.com/abachaa/MeQSum

MeQSum (Medical Question Summarization) is a corpus of 1,000 summarized consumer
health questions, introduced in the ACL 2019 paper:
  "On the Summarization of Consumer Health Questions"
  Asma Ben Abacha and Dina Demner-Fushman, ACL 2019.

The dataset Excel file contains the following columns:
  - File:    Source filename (original CHQ source file)
  - CHQ:     Full consumer health question (may include SUBJECT/MESSAGE fields)
  - Summary: Condensed/summarized version of the question
  (Two additional empty columns are present but unused.)

Output structure per sample:
  preset-data/meqsum/[NNNN]/question.txt  (full consumer health question)
  preset-data/meqsum/[NNNN]/summary.txt   (summarized question)

where [NNNN] is a zero-padded integer index (0001–1000).
"""

import io
import os
import sys

import openpyxl
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GITHUB_URL = "https://github.com/abachaa/MeQSum"
RAW_XLSX_URL = (
    "https://raw.githubusercontent.com/abachaa/MeQSum/master/"
    "MeQSum_ACL2019_BenAbacha_Demner-Fushman.xlsx"
)

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "preset-data",
    "meqsum",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def download_xlsx(url: str) -> bytes:
    """Download an Excel file from *url* and return its raw bytes."""
    print(f"Downloading dataset from {url} ...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def clean_text(text: str) -> str:
    """Strip surrounding whitespace and normalise line endings."""
    if not text:
        return ""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


def parse_rows(xlsx_bytes: bytes) -> list[dict]:
    """
    Parse the MeQSum Excel workbook and return a list of dicts with keys:
      file, question, summary
    Row 0 is the header row (File, CHQ, Summary) and is skipped.
    """
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active  # Only one sheet: 'QS'

    records = []
    header_skipped = False
    for row in ws.iter_rows(values_only=True):
        if not header_skipped:
            # Verify we have the expected header
            if row[0] == "File":
                header_skipped = True
                continue
            # If first row is already data (no header), just proceed
            header_skipped = True

        file_name, chq, summary = row[0], row[1], row[2]

        # Skip rows that are entirely empty
        if not file_name and not chq and not summary:
            continue

        records.append(
            {
                "file": clean_text(str(file_name)) if file_name else "",
                "question": clean_text(str(chq)) if chq else "",
                "summary": clean_text(str(summary)) if summary else "",
            }
        )

    return records


def write_sample(idx: int, record: dict) -> str:
    """
    Write question.txt and summary.txt for a single sample.
    Returns the sample directory path.
    """
    sample_id = f"{idx:04d}"
    sample_dir = os.path.join(OUTPUT_DIR, sample_id)
    os.makedirs(sample_dir, exist_ok=True)

    with open(os.path.join(sample_dir, "question.txt"), "w", encoding="utf-8") as f:
        f.write(record["question"])

    with open(os.path.join(sample_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(record["summary"])

    return sample_dir


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Download dataset
    xlsx_bytes = download_xlsx(RAW_XLSX_URL)

    # Parse rows
    records = parse_rows(xlsx_bytes)
    print(f"Parsed {len(records)} records from Excel file.")

    if not records:
        print("ERROR: No records found — aborting.", file=sys.stderr)
        sys.exit(1)

    # Write samples
    written = 0
    skipped = 0
    for idx, record in enumerate(records, start=1):
        if not record["question"] or not record["summary"]:
            print(
                f"  [SKIP] Row {idx}: missing question or summary "
                f"(file={record['file']!r})"
            )
            skipped += 1
            continue

        sample_dir = write_sample(idx, record)
        written += 1

        if idx <= 3 or idx % 100 == 0:
            print(
                f"  [{idx:04d}] {record['file']!r}\n"
                f"         Q: {record['question'][:80]!r}\n"
                f"         S: {record['summary']!r}"
            )

    print(
        f"\nDone. Written: {written} samples, Skipped: {skipped}.\n"
        f"Output directory: {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
