#!/usr/bin/env python3
"""Upload local preset-data/ directories to gs://juno-preset-data/preset-data/.

Usage:
    python upload_to_gcs.py [--dry-run] [--group GROUP] [--delete-local]

Flags:
    --dry-run        Print paths that would be uploaded; make no GCS calls.
    --group GROUP    Upload only one dataset group (e.g. meqsum).
    --delete-local   After a successful upload, delete local group directories.
                     Incompatible with --dry-run.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRESET_DATA_DIR = REPO_ROOT / "preset-data"
DEFAULT_BUCKET = "juno-preset-data"
EXCLUDED_DIRS = {"example"}


def _is_group_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name in EXCLUDED_DIRS:
        return False
    return any(child.is_dir() for child in path.iterdir())


def _collect_files(group_dirs: list[Path]) -> list[tuple[Path, str]]:
    """Return list of (local_path, blob_name) for all files under group_dirs."""
    result = []
    for group_dir in group_dirs:
        group = group_dir.name
        for input_dir in sorted(group_dir.iterdir()):
            if not input_dir.is_dir():
                continue
            for file_path in sorted(input_dir.iterdir()):
                if not file_path.is_file():
                    continue
                blob_name = f"preset-data/{group}/{input_dir.name}/{file_path.name}"
                result.append((file_path, blob_name))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload preset-data to GCS")
    parser.add_argument("--dry-run", action="store_true", help="Print paths only; no GCS calls")
    parser.add_argument("--group", help="Upload only this dataset group")
    parser.add_argument("--delete-local", action="store_true", help="Delete local dirs after upload")
    args = parser.parse_args()

    if args.dry_run and args.delete_local:
        print("ERROR: --dry-run and --delete-local are incompatible", file=sys.stderr)
        sys.exit(1)

    # Collect group directories
    if args.group:
        group_dir = PRESET_DATA_DIR / args.group
        if not group_dir.is_dir():
            print(f"ERROR: Group directory not found: {group_dir}", file=sys.stderr)
            sys.exit(1)
        group_dirs = [group_dir]
    else:
        group_dirs = sorted(p for p in PRESET_DATA_DIR.iterdir() if _is_group_dir(p))

    if not group_dirs:
        print("ERROR: No dataset group directories found", file=sys.stderr)
        sys.exit(1)

    bucket_name = os.environ.get("DATASETS_BUCKET_NAME", DEFAULT_BUCKET)
    files = _collect_files(group_dirs)

    if args.dry_run:
        for local_path, blob_name in files:
            print(f"[DRY RUN] {blob_name} → gs://{bucket_name}/{blob_name}")
        print(f"\nDry run complete: {len(files)} files would be uploaded")
        sys.exit(0)

    # Real upload
    from google.cloud import storage as gcs
    client = gcs.Client()
    bucket = client.bucket(bucket_name)

    attempted = succeeded = skipped = failed = 0
    for local_path, blob_name in files:
        attempted += 1
        try:
            blob = bucket.blob(blob_name)
            if blob.exists():
                print(f"[SKIP] already exists: {blob_name}")
                skipped += 1
            else:
                blob.upload_from_filename(str(local_path))
                size = local_path.stat().st_size
                print(f"[OK] {blob_name} ({size} bytes)")
                succeeded += 1
        except Exception as exc:
            print(f"[ERROR] {blob_name}: {exc}", file=sys.stderr)
            failed += 1

    print(f"\nAttempted: {attempted}, Succeeded: {succeeded}, Skipped: {skipped}, Failed: {failed}")

    if failed > 0:
        print("ERROR: Some files failed to upload. Local directories NOT deleted.", file=sys.stderr)
        sys.exit(1)

    if args.delete_local:
        names = [d.name for d in group_dirs]
        answer = input(f"About to delete {len(group_dirs)} group directories locally ({', '.join(names)}). Type 'yes' to confirm: ")
        if answer.strip() != "yes":
            print("Aborted — local directories not deleted.")
            sys.exit(0)
        for group_dir in group_dirs:
            shutil.rmtree(group_dir)
            print(f"Deleted: {group_dir}")
        print("Local dataset directories deleted.")


if __name__ == "__main__":
    main()
