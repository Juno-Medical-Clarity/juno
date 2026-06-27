#!/usr/bin/env python3
"""
Parse GEM/cochrane-simplification dataset and save text pairs to preset-data.

Dataset source: https://huggingface.co/datasets/GEM/cochrane-simplification

GEM/cochrane-simplification contains 4,459 paragraph-level pairs drawn from
Cochrane systematic reviews. Each sample pairs a technical medical abstract
(source) with a plain-language patient summary (target) authored by medical
professionals for a general audience.

Key fields per sample:
  - gem_id (str): unique identifier in the GEM benchmark (e.g. "cochrane-train-0")
  - doi    (str): DOI of the originating Cochrane review
  - source (str): technical medical abstract
  - target (str): plain-language patient summary

Splits:
  - train      (3,568 samples)
  - validation (  456 samples)
  - test        (  435 samples)

The dataset is loaded directly from its HuggingFace-hosted JSON files because
the repo uses a legacy loading script that is no longer supported by the
current datasets library.

Output structure per sample:
  preset-data/cochrane-simplification/[split]-[NNNN]/technical.txt       (source)
  preset-data/cochrane-simplification/[split]-[NNNN]/patient_summary.txt (target)

where [split] is the HuggingFace split name (train / validation / test)
and [NNNN] is a four-digit zero-padded index within that split.

Usage:
    python parse_cochrane.py               # parse all samples
    python parse_cochrane.py --limit 20    # parse first 20 samples per split (testing)
    python parse_cochrane.py --output-dir /custom/path
"""

import argparse
import json
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATASET_ID = "GEM/cochrane-simplification"
DATASET_URL = "https://huggingface.co/datasets/GEM/cochrane-simplification"

# Raw JSON files hosted on HuggingFace Hub
_HF_RAW_BASE = (
    "https://huggingface.co/datasets/GEM/cochrane-simplification/resolve/main"
)
SPLIT_URLS: dict[str, str] = {
    "train":      f"{_HF_RAW_BASE}/train.json",
    "validation": f"{_HF_RAW_BASE}/validation.json",
    "test":       f"{_HF_RAW_BASE}/test.json",
}

DEFAULT_OUTPUT_DIR = (
    Path(__file__).parent.parent.parent / "preset-data" / "cochrane-simplification"
)

# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def fetch_split(split: str, url: str) -> list[dict]:
    """Download and parse one JSON split file. Returns a list of sample dicts."""
    print(f"  Fetching '{split}' from {url} ...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array for split '{split}', got {type(data).__name__}"
        )
    print(f"    → {len(data):,} samples")
    return data


def load_all_splits() -> dict[str, list[dict]]:
    """Fetch all splits and return {split_name: [sample, ...]}."""
    result: dict[str, list[dict]] = {}
    for split, url in SPLIT_URLS.items():
        result[split] = fetch_split(split, url)
    return result


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------


def format_technical(text: str, sample_id: str, doi: str, gem_id: str) -> str:
    """Format the technical medical abstract with a header comment block."""
    return "\n".join([
        "# GEM/cochrane-simplification — technical abstract",
        f"# Dataset: {DATASET_URL}",
        f"# Sample:  {sample_id}  |  gem_id: {gem_id}  |  doi: {doi}",
        "",
        text.strip(),
        "",
    ])


def format_patient_summary(text: str, sample_id: str, doi: str, gem_id: str) -> str:
    """Format the plain-language patient summary with a header comment block."""
    return "\n".join([
        "# GEM/cochrane-simplification — plain-language patient summary",
        f"# Dataset: {DATASET_URL}",
        f"# Sample:  {sample_id}  |  gem_id: {gem_id}  |  doi: {doi}",
        "",
        text.strip(),
        "",
    ])


# ---------------------------------------------------------------------------
# Per-sample processing
# ---------------------------------------------------------------------------


def process_sample(
    sample: dict,
    split: str,
    idx: int,
    output_dir: Path,
    verbose: bool = True,
) -> bool:
    """
    Write technical.txt and patient_summary.txt for one dataset sample.
    Returns True on success, False on failure.
    """
    sample_id = f"{split}-{idx:04d}"
    out_dir = output_dir / sample_id

    try:
        source_text = (sample.get("source") or "").strip()
        target_text = (sample.get("target") or "").strip()
        gem_id = sample.get("gem_id") or ""
        doi = sample.get("doi") or ""

        if not source_text and not target_text:
            print(
                f"  WARNING: {sample_id} has empty source and target — skipping.",
                file=sys.stderr,
            )
            return False

        out_dir.mkdir(parents=True, exist_ok=True)

        # Write technical abstract
        tech_file = out_dir / "technical.txt"
        tech_file.write_text(
            format_technical(source_text, sample_id, doi, gem_id),
            encoding="utf-8",
        )

        # Write plain-language patient summary
        summary_file = out_dir / "patient_summary.txt"
        summary_file.write_text(
            format_patient_summary(target_text, sample_id, doi, gem_id),
            encoding="utf-8",
        )

        if verbose:
            print(
                f"  [{sample_id}] technical: {len(source_text):,} chars, "
                f"summary: {len(target_text):,} chars  →  {out_dir}"
            )

        return True

    except Exception as exc:
        print(f"  ERROR processing {sample_id}: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse GEM/cochrane-simplification into per-sample text files.",
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
        help="Process only the first N samples per split (default: all)",
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
        print("Cochrane Simplification Dataset Parser")
        print(f"Dataset: {DATASET_URL}")
        print(f"Output:  {output_dir}")
        if args.limit:
            print(f"Limit:   {args.limit} samples per split")
        print()

    print("Downloading JSON splits from HuggingFace Hub...")
    splits = load_all_splits()
    print()

    total_success = 0
    total_failure = 0

    for split, samples in splits.items():
        cap = min(len(samples), args.limit) if args.limit is not None else len(samples)

        if verbose:
            print(
                f"Processing split '{split}' "
                f"({cap:,} of {len(samples):,} samples)..."
            )

        for idx in range(cap):
            ok = process_sample(
                sample=samples[idx],
                split=split,
                idx=idx,
                output_dir=output_dir,
                verbose=verbose,
            )
            if ok:
                total_success += 1
            else:
                total_failure += 1

        if verbose:
            print()

    print(f"Done. {total_success:,} succeeded, {total_failure} failed.")
    if total_success > 0:
        print(f"Files saved to: {output_dir}")

    sys.exit(0 if total_failure == 0 else 1)


if __name__ == "__main__":
    main()
