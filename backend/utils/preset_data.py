import json
import os
from pathlib import Path


PRESET_DATA_ROOT = Path(
    os.environ.get("PRESET_DATA_PATH")
    or (Path(__file__).resolve().parent.parent.parent / "preset-data")
)

MANIFEST_PATH = PRESET_DATA_ROOT / "manifest.json"

_manifest_cache: dict | None = None


class GCSFetchRequired(Exception):
    """Raised when the requested file is not in the manifest and requires GCS fetch (SP2)."""

    def __init__(self, group: str, input_id: str, filename: str):
        self.group = group
        self.input_id = input_id
        self.filename = filename
        super().__init__(f"GCS fetch required for {group}/{input_id}/{filename}")


def _load_manifest() -> dict:
    """Load and cache manifest.json. Raises RuntimeError if not found."""
    global _manifest_cache
    if _manifest_cache is None:
        if not MANIFEST_PATH.is_file():
            raise RuntimeError(f"Dataset manifest not found at {MANIFEST_PATH}")
        with MANIFEST_PATH.open("r", encoding="utf-8") as f:
            _manifest_cache = json.load(f)
    return _manifest_cache


def list_datasets() -> list[dict]:
    """Return dataset metadata from manifest. Same shape as before."""
    try:
        manifest = _load_manifest()
    except RuntimeError:
        return []

    return [
        {
            "group": entry["group"],
            "inputs": entry["inputs"],
            "files": entry["file_types"],  # manifest uses "file_types"; API uses "files"
        }
        for entry in manifest.get("datasets", [])
    ]


def list_athena_sources() -> list[dict]:
    """Return Athena source manifests from the unified manifest."""
    try:
        manifest = _load_manifest()
    except RuntimeError:
        return []
    return manifest.get("athena_sources", [])


def read_dataset_file(group: str, input_id: str, filename: str) -> bytes:
    """
    Return file content as bytes.

    For the sample input_id (inputs[0] per manifest): returns content from manifest.
    For all other input_ids: raises GCSFetchRequired — handled by SP2.
    """
    try:
        manifest = _load_manifest()
    except RuntimeError as exc:
        raise FileNotFoundError(str(exc)) from exc
    entry = next((d for d in manifest.get("datasets", []) if d["group"] == group), None)
    if entry is None:
        raise FileNotFoundError(f"Group not found: {group}")
    if input_id not in entry["inputs"]:
        raise FileNotFoundError(f"Input ID not found: {input_id}")
    if filename not in entry["file_types"]:
        raise FileNotFoundError(f"File type not found: {filename}")

    sample = entry["sample"]
    if input_id == sample["input_id"]:
        content = sample["files"].get(filename)
        if content is None:
            raise FileNotFoundError(f"Sample file not in manifest: {filename}")
        return content.encode("utf-8")

    # Non-sample input_id: on-demand GCS download is SP2's responsibility.
    raise GCSFetchRequired(group=group, input_id=input_id, filename=filename)
