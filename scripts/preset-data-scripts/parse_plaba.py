#!/usr/bin/env python3
"""
Parse the PLABA dataset and save sentence-level simplification pairs to preset-data.

Dataset source: https://osf.io/rnpmf/
GitHub:         https://github.com/attal-kush/PLABA
Paper:          "A Dataset for Plain Language Adaptation of Biomedical Abstracts"
                Attal, Ondov & Demner-Fushman — Scientific Data (2023)

PLABA contains 749 PubMed abstracts organised under 75 consumer health questions.
Each abstract was simplified sentence-by-sentence by one or more expert annotators,
producing up to three independent adaptations (adaptation1 / adaptation2 / adaptation3).

data.json structure:
  {
    "<question_number>": {
      "<pmid>": {
        "Title":    "<article title>",
        "abstract": {"1": "<sent1>", "2": "<sent2>", ...},
        "adaptations": {
          "adaptation2": {"1": "<plain1>", "2": "<plain2>", ...},
          ...
        }
      },
      ...
    },
    ...
  }

Each sample = one (abstract × adaptation) pair, i.e. one unique original + one
complete plain-language version authored by a single annotator.  Abstracts with
multiple adaptations produce multiple samples so every expert version is kept.

Output structure per sample:
  preset-data/plaba/<NNNNN>/original.txt       — original biomedical sentences (one per line)
  preset-data/plaba/<NNNNN>/simplified.txt     — plain-language adaptation (one per line)
  preset-data/plaba/<NNNNN>/metadata.txt       — PMID, title, question, adaptation version

Samples are numbered sequentially (00000, 00001, …) across all questions,
PMIDs, and adaptation versions, sorted by question number → PMID → adaptation name.

Usage:
    python parse_plaba.py               # parse all samples
    python parse_plaba.py --limit 20    # parse first 20 samples (testing)
    python parse_plaba.py --output-dir /custom/path
"""

import argparse
import json
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_JSON_URL = "https://osf.io/download/4kp7v/"  # data.json on OSF (rnpmf)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "preset-data" / "plaba"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def fetch_data_json(url: str) -> dict:
    """Download data.json from OSF and parse it."""
    print(f"Downloading data.json from {url} …")
    resp = requests.get(url, allow_redirects=True, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print(f"  Downloaded {len(resp.content) / 1024:.1f} KB — "
          f"{len(data)} questions loaded.")
    return data


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def iter_samples(data: dict):
    """
    Yield (question_num, pmid, adaptation_name, title, abstract_sents, adapt_sents)
    tuples sorted deterministically.

    abstract_sents / adapt_sents are lists of strings in sentence order.
    Only sentence indices that exist in BOTH the original and the adaptation
    are included (they should always match, but we guard against edge cases).
    """
    for qnum in sorted(data.keys(), key=lambda x: int(x)):
        abstracts = data[qnum]
        for pmid in sorted(abstracts.keys()):
            abstract_entry = abstracts[pmid]
            if not isinstance(abstract_entry, dict):
                continue

            title = abstract_entry.get("Title", "").strip()
            abstract_dict = abstract_entry.get("abstract", {})
            adaptations = abstract_entry.get("adaptations", {})

            for adapt_name in sorted(adaptations.keys()):
                adapt_dict = adaptations[adapt_name]

                # Build aligned sentence lists using shared sentence indices
                shared_indices = sorted(
                    set(abstract_dict.keys()) & set(adapt_dict.keys()),
                    key=lambda x: int(x),
                )
                if not shared_indices:
                    continue

                original_sents = [abstract_dict[i].strip() for i in shared_indices]
                simplified_sents = [adapt_dict[i].strip() for i in shared_indices]

                yield qnum, pmid, adapt_name, title, original_sents, simplified_sents


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_sample(
    sample_dir: Path,
    qnum: str,
    pmid: str,
    adapt_name: str,
    title: str,
    original_sents: list[str],
    simplified_sents: list[str],
) -> None:
    sample_dir.mkdir(parents=True, exist_ok=True)

    # original.txt — one original sentence per line
    (sample_dir / "original.txt").write_text(
        "\n".join(original_sents) + "\n", encoding="utf-8"
    )

    # simplified.txt — one plain-language sentence per line (same order)
    (sample_dir / "simplified.txt").write_text(
        "\n".join(simplified_sents) + "\n", encoding="utf-8"
    )

    # metadata.txt
    meta_lines = [
        f"pmid:        {pmid}",
        f"question:    {qnum}",
        f"adaptation:  {adapt_name}",
        f"title:       {title}",
        f"sentences:   {len(original_sents)}",
    ]
    (sample_dir / "metadata.txt").write_text(
        "\n".join(meta_lines) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse PLABA dataset into preset-data/plaba/")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N samples (useful for testing).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Root output directory (default: {OUTPUT_DIR})",
    )
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download
    data = fetch_data_json(DATA_JSON_URL)

    # Collect all samples first (so we know the total)
    print("Iterating samples …")
    samples = list(iter_samples(data))
    total = len(samples)
    print(f"  Found {total} (abstract × adaptation) samples across {len(data)} questions.")

    if args.limit is not None:
        samples = samples[: args.limit]
        print(f"  Limiting to first {len(samples)} samples (--limit={args.limit}).")

    # Write
    written = 0
    total_sentence_pairs = 0
    for i, (qnum, pmid, adapt_name, title, orig, simp) in enumerate(samples):
        sample_id = f"{i:05d}"
        sample_dir = output_dir / sample_id
        write_sample(sample_dir, qnum, pmid, adapt_name, title, orig, simp)
        written += 1
        total_sentence_pairs += len(orig)

        if written % 100 == 0:
            print(f"  … wrote {written}/{len(samples)} samples")

    print(f"\nDone.")
    print(f"  Samples written:        {written}")
    print(f"  Total sentence pairs:   {total_sentence_pairs}")
    print(f"  Output directory:       {output_dir}")


if __name__ == "__main__":
    main()
