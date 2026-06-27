#!/usr/bin/env python3
"""
NoteAid-README parser — offline ingestion script.

Converts the NoteAid-README dataset into preset-data/ files
consumable by the Juno batch pipeline.

Dataset source: https://huggingface.co/datasets/bio-nlp-umass/NoteAid-README
GitHub:         https://github.com/seasonyao/NoteAid-README

NoteAid-README contains 50,000+ (medical jargon term, lay definition) pairs
grounded in EHR context passages.  The dataset is split across six CSV files,
each a quality variant:
  readme_exp         General definitions from UMLS open-source data
  readme_exp_good    UMLS definitions suitable for training
  readme_exp_bad     UMLS definitions unsuitable for training
  readme_syn         AI-generated general definitions
  readme_syn_good    Quality AI definitions for training (DEFAULT)
  readme_syn_bad     Lower-quality AI definitions

Note: the HuggingFace 'default' config merges all six CSVs but fails due to a
column mismatch (readme_exp* has 'split_print'; readme_syn* has 'gen_def').
This script loads a single CSV variant directly via hf:// URL.

Key fields:
  ann_text             — medical jargon term (plain string)
  gpt_generated        — GPT-3.5 generated lay definition
  gpt_text_to_annotate — GPT-4o-mini generated EHR context passage

Output structure per sample:
  preset-data/noteaid-readme/<NNNNN>/jargon.txt     — medical jargon term
  preset-data/noteaid-readme/<NNNNN>/definition.txt — plain-language lay definition
  preset-data/noteaid-readme/<NNNNN>/context.txt    — EHR passage containing the term

Usage:
    # From repo root:
    python -m backend.utils.preset_data_parser.noteaid_readme.parser

    # With options:
    python -m backend.utils.preset_data_parser.noteaid_readme.parser \\
        --variant readme_syn_good --limit 500

    # Specify output location explicitly:
    python -m backend.utils.preset_data_parser.noteaid_readme.parser \\
        --dest /path/to/juno/preset-data

    # Replace already-generated files:
    python -m backend.utils.preset_data_parser.noteaid_readme.parser --overwrite
"""

import argparse
import math
import sys
from pathlib import Path

_DEFAULT_DEST = Path(__file__).resolve().parents[4] / "preset-data"

HF_BASE_URL = "hf://datasets/bio-nlp-umass/NoteAid-README"
DEFAULT_VARIANT = "readme_syn_good"
VALID_VARIANTS = [
    "readme_exp",
    "readme_exp_good",
    "readme_exp_bad",
    "readme_syn",
    "readme_syn_good",
    "readme_syn_bad",
]
GROUP_NAME = "noteaid-readme"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoteAid-README parser")
    parser.add_argument(
        "--variant",
        default=DEFAULT_VARIANT,
        choices=VALID_VARIANTS,
        help=f"CSV variant to load (default: {DEFAULT_VARIANT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of samples to write (default: 500). Use 0 for all.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_DEFAULT_DEST,
        help=f"Root preset-data directory (default: {_DEFAULT_DEST})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing sample directories (default: skip existing)",
    )
    return parser.parse_args()


def _is_missing(val) -> bool:
    """True if val is None, NaN, or pandas NA."""
    if val is None:
        return True
    try:
        if isinstance(val, float) and math.isnan(val):
            return True
    except (TypeError, ValueError):
        pass
    try:
        import pandas as pd
        if pd.isna(val):
            return True
    except (TypeError, ValueError, ImportError):
        pass
    return False


def _extract_ann_text(raw) -> str:
    """
    ann_text is a plain string in the actual dataset rows.
    Handles list fragments as a safety net.
    """
    if _is_missing(raw):
        return ""
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw if str(p).strip() not in ("", "-", " - ")]
        return " ".join(parts).strip()
    return str(raw).strip()


def _safe_str(val, field: str, idx: int) -> str:
    if _is_missing(val):
        print(f"WARNING: row {idx}: field '{field}' is missing", file=sys.stderr)
        return ""
    return str(val).strip()


def _write_sample(
    sample_id: str,
    jargon: str,
    definition: str,
    context: str,
    dest_root: Path,
    overwrite: bool,
) -> str:
    out_dir = dest_root / sample_id

    if not overwrite and out_dir.exists():
        print(
            f"WARNING: skipping {sample_id} — {out_dir} already exists "
            "(pass --overwrite to replace)",
            file=sys.stderr,
        )
        return "skipped"

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: could not create {out_dir} — {e}", file=sys.stderr)
        return "error"

    for filename, content in [
        ("jargon.txt", jargon),
        ("definition.txt", definition),
        ("context.txt", context),
    ]:
        try:
            (out_dir / filename).write_text(content, encoding="utf-8")
        except OSError as e:
            print(f"ERROR: could not write {out_dir / filename} — {e}", file=sys.stderr)
            return "error"

    return "written"


def main() -> None:
    args = _parse_args()

    try:
        import pandas as pd
    except ImportError:
        print("ERROR: 'pandas' not found. Install: pip install pandas", file=sys.stderr)
        sys.exit(1)

    csv_url = f"{HF_BASE_URL}/{args.variant}.csv"
    print(f"Loading NoteAid-README variant='{args.variant}' from {csv_url} …")
    try:
        df = pd.read_csv(csv_url)
    except Exception as e:
        print(f"ERROR: failed to load CSV — {e}", file=sys.stderr)
        sys.exit(1)

    total_available = len(df)
    limit = args.limit if args.limit and args.limit > 0 else total_available
    limit = min(limit, total_available)
    print(f"Dataset has {total_available} rows; will process up to {limit}.")

    dest_root = args.dest / GROUP_NAME
    written = skipped = errors = 0

    for idx in range(limit):
        row = df.iloc[idx]

        jargon = _extract_ann_text(row.get("ann_text"))
        definition = _safe_str(row.get("gpt_generated"), "gpt_generated", idx)
        context = _safe_str(row.get("gpt_text_to_annotate"), "gpt_text_to_annotate", idx)

        if not jargon:
            print(f"WARNING: row {idx}: 'ann_text' resolved to empty — skipping", file=sys.stderr)
            errors += 1
            continue

        result = _write_sample(
            f"{idx:05d}", jargon, definition, context, dest_root, args.overwrite
        )

        if result == "written":
            written += 1
        elif result == "skipped":
            skipped += 1
        else:
            errors += 1

        if (idx + 1) % 100 == 0:
            print(f"  … processed {idx + 1}/{limit}")

    print()
    if skipped > 0:
        print(
            f"noteaid-readme parser: {written} written, {skipped} skipped "
            f"(pass --overwrite to replace), {errors} errors"
        )
    else:
        print(f"noteaid-readme parser: {written} written, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
