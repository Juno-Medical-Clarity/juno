#!/usr/bin/env python3
"""Generate preset-data/manifest.json from local preset-data/ directory tree.

Must be run before uploading files to GCS and before deleting local directories.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESET_DATA_DIR = REPO_ROOT / "preset-data"
DEFAULT_OUTPUT = PRESET_DATA_DIR / "manifest.json"

EXCLUDED_DIRS = {"example"}


def _is_group_dir(path: Path) -> bool:
    """Return True if path looks like a dataset group directory (has sub-subdirectories)."""
    if not path.is_dir():
        return False
    if path.name in EXCLUDED_DIRS:
        return False
    return any(child.is_dir() for child in path.iterdir())


def generate_manifest(preset_data_dir: Path, output_path: Path) -> None:
    existing_athena_sources = []
    if output_path.is_file():
        with output_path.open("r", encoding="utf-8") as f:
            try:
                existing_manifest = json.load(f)
                existing_athena_sources = existing_manifest.get("athena_sources", [])
            except Exception:
                pass

    groups = sorted(
        p for p in preset_data_dir.iterdir() if _is_group_dir(p)
    )

    if not groups:
        print(f"ERROR: No dataset group directories found under {preset_data_dir}", file=sys.stderr)
        sys.exit(1)

    datasets = []
    total_inputs_all = 0

    for group_dir in groups:
        group = group_dir.name
        input_dirs = sorted(p for p in group_dir.iterdir() if p.is_dir())
        input_ids = [d.name for d in input_dirs]

        if not input_ids:
            print(f"WARNING: Group {group} has no input directories, skipping")
            continue

        sample_dir = input_dirs[0]
        file_types = sorted(f.name for f in sample_dir.iterdir() if f.is_file())

        sample_files = {}
        for filename in file_types:
            file_path = sample_dir / filename
            raw = file_path.read_bytes()
            sample_files[filename] = raw.decode("utf-8", errors="replace")
            print(f"  [{group}/sample/{filename}] {len(raw)} bytes")

        datasets.append({
            "group": group,
            "total_inputs": len(input_ids),
            "file_types": file_types,
            "inputs": input_ids,
            "sample": {
                "input_id": input_ids[0],
                "files": sample_files,
            },
        })
        total_inputs_all += len(input_ids)
        print(f"[{group}] {len(input_ids)} inputs, sample={input_ids[0]}")

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "bucket": "juno-preset-data",
        "gcs_prefix": "preset-data",
        "datasets": datasets,
        "athena_sources": existing_athena_sources,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest written to {output_path}")
    print(f"Groups: {len(datasets)}, Total inputs: {total_inputs_all}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate preset-data/manifest.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    generate_manifest(PRESET_DATA_DIR, args.output)


if __name__ == "__main__":
    main()
