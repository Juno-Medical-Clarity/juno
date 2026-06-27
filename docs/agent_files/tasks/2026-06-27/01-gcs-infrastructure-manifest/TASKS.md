# Tasks: SP1 — GCS Dataset Infrastructure, Manifest & Backend

**Sub-project:** SP1  
**Branch:** `athena_health_part1`  
**PRD source:** `docs/agent_files/tasks/2026-06-27/01-gcs-infrastructure-manifest/PRD.md`  
**Fresh authoring** — no prior TASKS.md existed.

---

### Task 1 — Add `DATASETS_BUCKET_NAME` constants to `constants.py`

**Traced to PRD §4-E**

- **Files:** `/root/projects/juno/backend/utils/constants.py`
- **Changes:** Inside the `Constants` class, after the existing `# ── GCS / Cloud config` block (after `GCS_BUCKET_ENV_VAR`), add a new sub-section:

```python
# ── Dataset GCS config ─────────────────────────────────────────────────────
DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
```

No other lines in the file change.

- **Acceptance criteria:**
  - `python -c "from utils.constants import Constants; assert Constants.DATASETS_BUCKET_NAME_ENV_VAR == 'DATASETS_BUCKET_NAME'; assert Constants.DATASETS_BUCKET_NAME_DEFAULT == 'juno-preset-data'; print('OK')"` (run from `backend/`) exits 0 and prints `OK`.

---

### Task 2 — Add `DATASETS_BUCKET_NAME` to env files

**Traced to PRD §4-E**

- **Files:**
  - `/root/projects/juno/backend/.env.example`
  - `/root/projects/juno/backend/.env` (local, gitignored — edit in place if it exists; create it otherwise with just this line)

- **Changes to `.env.example`:** Append at the end of the file:

```
# Dataset GCS bucket (preset research datasets)
DATASETS_BUCKET_NAME=juno-preset-data
```

- **Changes to `.env`:** Append the same two lines (comment + assignment). If `.env` does not exist, create it with just these two lines. Do not touch any other content.

- **Acceptance criteria:**
  - `grep "DATASETS_BUCKET_NAME=juno-preset-data" /root/projects/juno/backend/.env.example` exits 0.
  - `.env.example` still parses cleanly (no syntax errors, no duplicate keys).

---

### Task 3 — Write `scripts/preset-data-scripts/generate_manifest.py`

**Traced to PRD §4-B and §4-C**

- **Files:** `/root/projects/juno/scripts/preset-data-scripts/generate_manifest.py` (new file)

- **Changes:** Create the file with the following behavior (implement fully):

  1. Accept a single optional CLI argument `--output` (default: `preset-data/manifest.json` relative to the repo root, resolved as `Path(__file__).resolve().parents[2] / "preset-data" / "manifest.json"`).
  2. Determine the `preset-data/` directory as `output_path.parent` (or the resolved repo-root-based path if `--output` is not given).
  3. Walk group directories in `preset-data/`: include any subdirectory whose name is NOT `example` and which contains sub-subdirectories (i.e., it has input_id directories inside). Sort groups alphabetically.
  4. For each group:
     - Collect all input IDs (subdirectory names) sorted lexicographically. These are the immediate children of `preset-data/{group}/`.
     - Set `file_types` to the sorted list of filenames in the **first** input ID's directory.
     - Set `sample.input_id` to `inputs[0]`.
     - For each file in the sample directory, read its bytes and decode as UTF-8 with `errors="replace"`.
     - Build the dataset entry matching the schema in PRD §4-C.
  5. Build the top-level manifest dict:
     ```python
     {
         "generated_at": datetime.utcnow().isoformat() + "Z",
         "bucket": "juno-preset-data",
         "gcs_prefix": "preset-data",
         "datasets": [...]
     }
     ```
  6. Write the manifest as pretty-printed JSON (`json.dump(..., indent=2)`).
  7. Print a summary to stdout: number of groups processed, total inputs indexed, and the byte size of each sample file embedded.

- **Exact schema fields** (all required, per PRD §4-C):
  - `generated_at`, `bucket`, `gcs_prefix`, `datasets`
  - Per dataset entry: `group`, `total_inputs` (== `len(inputs)`), `file_types` (sorted), `inputs` (sorted), `sample.input_id`, `sample.files` (dict of filename → UTF-8 string content)

- **Acceptance criteria:**
  - `python scripts/preset-data-scripts/generate_manifest.py --output /tmp/test_manifest.json` runs without error (requires local `preset-data/` dirs to be present).
  - The output JSON has exactly 7 entries in `datasets` (one per group).
  - Each entry has `inputs`, `file_types`, `total_inputs == len(inputs)`, and `sample.files` with non-empty string values.
  - `sample.input_id == inputs[0]` for every group.
  - `--output` flag correctly overrides the output path.

---

### Task 4 — Write `scripts/preset-data-scripts/upload_to_gcs.py`

**Traced to PRD §4-A and §4-F**

- **Files:** `/root/projects/juno/scripts/preset-data-scripts/upload_to_gcs.py` (new file)

- **Changes:** Create the file with the following behavior (implement fully):

  **CLI interface:**
  ```
  python scripts/preset-data-scripts/upload_to_gcs.py [--dry-run] [--group GROUP] [--delete-local]
  ```

  **Upload logic (§4-A):**
  1. Determine `preset-data/` directory (same repo-root detection as Task 3).
  2. Collect group directories: same filter as Task 3 (not `example`, has sub-subdirectories). If `--group GROUP` is given, restrict to that single group; error if the group directory doesn't exist.
  3. For each `group/input_id/filename`:
     - GCS blob name: `preset-data/{group}/{input_id}/{filename}`
     - Bucket: read from env var `DATASETS_BUCKET_NAME` (fallback: `"juno-preset-data"`).
     - If `--dry-run`: print `[DRY RUN] {group}/{input_id}/{filename} → gs://{bucket}/preset-data/{group}/{input_id}/{filename}` and continue.
     - Otherwise: check `blob.exists()`. If true, log `[SKIP] already exists: {blob_name}` and count as skipped. If false, upload via `blob.upload_from_filename(str(local_path))`, log `[OK] {group}/{input_id}/{filename} → gs://{bucket}/... ({bytes} bytes)`.
     - On any exception during upload: log `[ERROR] {group}/{input_id}/{filename}: {exc}`, count as failed, continue.
  4. Print a summary: `Attempted: N, Succeeded: N, Skipped: N, Failed: N`.
  5. Exit non-zero (`sys.exit(1)`) if any file failed.
  6. Use `google.cloud.storage.Client()` (Application Default Credentials / `GOOGLE_APPLICATION_CREDENTIALS`).

  **Delete-local logic (§4-F):**
  - `--delete-local` flag: after a successful upload run (zero failures), delete each processed `preset-data/{group}/` directory using `shutil.rmtree`.
  - Before deleting, print a confirmation prompt: `"About to delete N group directories locally. Type 'yes' to confirm: "`. If the user does not type `yes` exactly, abort without deleting.
  - Refuse to delete if `failed > 0`: print an error and exit non-zero.
  - `--delete-local` is incompatible with `--dry-run`: print an error and exit non-zero if both are given.

- **Acceptance criteria:**
  - `python scripts/preset-data-scripts/upload_to_gcs.py --dry-run` prints expected GCS paths for all 7 groups and exits 0 (no GCS calls made).
  - `python scripts/preset-data-scripts/upload_to_gcs.py --dry-run --group meqsum` only prints paths for `meqsum`.
  - `python scripts/preset-data-scripts/upload_to_gcs.py --dry-run --delete-local` prints an error and exits non-zero.
  - Running with an invalid `--group` value exits non-zero with a clear error message.

---

### Task 5 — Rewrite `backend/utils/preset_data.py`

**Traced to PRD §4-D**

- **Files:** `/root/projects/juno/backend/utils/preset_data.py`

- **Changes:** Replace the entire file content with the following (do not leave any old code):

```python
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


def read_dataset_file(group: str, input_id: str, filename: str) -> bytes:
    """
    Return file content as bytes.

    For the sample input_id (inputs[0] per manifest): returns content from manifest.
    For all other input_ids: raises GCSFetchRequired — handled by SP2.
    """
    manifest = _load_manifest()
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
```

  Notes:
  - `_input_files()` is intentionally removed.
  - `_manifest_cache` is intentionally module-level (process-lifetime cache per PRD §4-D).

- **Acceptance criteria:**
  - `from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired` imports cleanly from the `backend/` directory.
  - `list_datasets()` returns `[]` when `manifest.json` is absent (no exception raised).
  - `read_dataset_file(group, non_sample_id, filename)` raises `GCSFetchRequired` (verified by unit tests in Task 7).
  - No reference to `_input_files`, local filesystem reads, or old `PRESET_DATA_ROOT`-based path traversal remains.

---

### Task 6 — Update `backend/routes/datasets.py` to handle `GCSFetchRequired`

**Traced to PRD §4-D (SP2 boundary)**

- **Files:** `/root/projects/juno/backend/routes/datasets.py`

- **Changes:**

  1. Update the import line for `preset_data` to include `GCSFetchRequired`:

     **Old:**
     ```python
     from utils.preset_data import list_datasets, read_dataset_file
     ```
     **New:**
     ```python
     from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired
     ```

  2. In `get_dataset_file_route`, add a `GCSFetchRequired` catch block before the existing `FileNotFoundError` catch. The `try/except` block becomes:

     ```python
     try:
         file_bytes = read_dataset_file(group, input_id, filename)
         content = _extract_text_from_bytes(file_bytes, filename)
     except GCSFetchRequired:
         return jsonify({"error": "On-demand GCS fetch not yet implemented (SP2)"}), 503
     except FileNotFoundError:
         return jsonify({"error": "Not found"}), 404
     ```

  No other lines in the file change.

- **Acceptance criteria:**
  - `GET /care_plan/datasets/{group}/{non_sample_id}/{filename}` returns HTTP 503 with JSON body `{"error": "On-demand GCS fetch not yet implemented (SP2)"}` (verifiable via the route tests after a manifest fixture is in place).
  - `GET /care_plan/datasets/{group}/{sample_id}/{filename}` still returns HTTP 200 with content (unchanged behavior for the sample input).
  - `GET /care_plan/datasets/{group}/{bad_input}/{filename}` still returns HTTP 404.

---

### Task 7 — Write `backend/tests/utils/test_preset_data.py`

**Traced to PRD §7 (Backend unit tests)**

- **Files:** `/root/projects/juno/backend/tests/utils/test_preset_data.py` (new file — the old version was removed in a prior commit per Q12 resolution)

- **Changes:** Create the file with the following six tests. Use a minimal fixture manifest (2 datasets, 3 inputs each, only `inputs[0]` has sample content):

```python
import json
import pytest
from pathlib import Path
from unittest.mock import mock_open, patch, call


FIXTURE_MANIFEST = {
    "generated_at": "2026-06-27T00:00:00Z",
    "bucket": "juno-preset-data",
    "gcs_prefix": "preset-data",
    "datasets": [
        {
            "group": "meqsum",
            "total_inputs": 3,
            "file_types": ["question.txt", "summary.txt"],
            "inputs": ["0001", "0002", "0003"],
            "sample": {
                "input_id": "0001",
                "files": {
                    "question.txt": "What is aspirin?",
                    "summary.txt": "Aspirin is a pain reliever.",
                },
            },
        },
        {
            "group": "notechat",
            "total_inputs": 2,
            "file_types": ["note.txt"],
            "inputs": ["nc001", "nc002"],
            "sample": {
                "input_id": "nc001",
                "files": {"note.txt": "Patient presents with fever."},
            },
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_manifest_cache():
    """Reset the module-level manifest cache before each test."""
    import utils.preset_data as pd
    pd._manifest_cache = None
    yield
    pd._manifest_cache = None


@pytest.fixture
def manifest_file(tmp_path):
    """Write the fixture manifest to a temp file and patch MANIFEST_PATH."""
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(FIXTURE_MANIFEST), encoding="utf-8")
    return p


def test_list_datasets_from_manifest(manifest_file, monkeypatch):
    """list_datasets() returns correct shape from manifest."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    result = pd.list_datasets()
    assert len(result) == 2
    assert result[0] == {
        "group": "meqsum",
        "inputs": ["0001", "0002", "0003"],
        "files": ["question.txt", "summary.txt"],
    }
    assert result[1]["group"] == "notechat"
    assert result[1]["files"] == ["note.txt"]


def test_read_sample_file(manifest_file, monkeypatch):
    """read_dataset_file returns bytes of manifest sample content for inputs[0]."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    result = pd.read_dataset_file("meqsum", "0001", "question.txt")
    assert result == b"What is aspirin?"


def test_read_non_sample_raises_gcs_fetch_required(manifest_file, monkeypatch):
    """read_dataset_file raises GCSFetchRequired for a non-sample input_id."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    with pytest.raises(pd.GCSFetchRequired) as exc_info:
        pd.read_dataset_file("meqsum", "0002", "question.txt")
    assert exc_info.value.group == "meqsum"
    assert exc_info.value.input_id == "0002"
    assert exc_info.value.filename == "question.txt"


def test_read_unknown_group_raises_file_not_found(manifest_file, monkeypatch):
    """read_dataset_file raises FileNotFoundError for an unknown group."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    with pytest.raises(FileNotFoundError):
        pd.read_dataset_file("nonexistent", "0001", "question.txt")


def test_list_datasets_missing_manifest(tmp_path, monkeypatch):
    """list_datasets() returns [] when manifest.json does not exist."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", tmp_path / "no_manifest.json")
    result = pd.list_datasets()
    assert result == []


def test_manifest_cache(manifest_file, monkeypatch):
    """list_datasets() only opens the manifest file once across multiple calls."""
    import utils.preset_data as pd
    monkeypatch.setattr(pd, "MANIFEST_PATH", manifest_file)
    open_calls = []
    real_open = manifest_file.open

    def counting_open(*args, **kwargs):
        open_calls.append(1)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(manifest_file, "open", counting_open)
    pd.list_datasets()
    pd.list_datasets()
    assert len(open_calls) == 1, "Manifest should be opened only once (cached)"
```

- **Acceptance criteria:**
  - `pytest backend/tests/utils/test_preset_data.py -v` (run from repo root) passes all 6 tests with no failures.
  - No test touches the real `preset-data/` directory on disk.
  - The `reset_manifest_cache` autouse fixture ensures tests do not bleed cache state into each other.

---

## Summary of what requires you (not a dev agent)

These steps from PRD §8 cannot be automated and must be performed by you manually, in order:

1. **GCS credentials:** Confirm `GOOGLE_APPLICATION_CREDENTIALS` or Application Default Credentials are active on the machine where you will run the scripts.

2. **Generate manifest** (must happen while local `preset-data/{group}/` dirs still exist):
   ```bash
   cd /root/projects/juno
   python scripts/preset-data-scripts/generate_manifest.py
   ```

3. **Review `preset-data/manifest.json`:** Spot-check all 7 groups are present, input counts look correct (e.g., meqsum ≈ 1000, soap-summary ≈ 1473), sample content is readable text, and no real patient data is present.

4. **Commit the manifest** (before any GCS upload or local deletion):
   ```bash
   git add preset-data/manifest.json
   git commit -m "chore: add preset-data manifest for GCS migration (SP1)"
   ```

5. **Upload to GCS:**
   ```bash
   python scripts/preset-data-scripts/upload_to_gcs.py --dry-run    # verify paths first
   python scripts/preset-data-scripts/upload_to_gcs.py              # actual upload
   ```

6. **Verify GCS upload:** Spot-check 3–5 files via `gsutil cat gs://juno-preset-data/preset-data/meqsum/0001/question.txt` or GCS console.

7. **Delete local dataset dirs** (after verified upload):
   ```bash
   python scripts/preset-data-scripts/upload_to_gcs.py --delete-local
   ```

8. **Update Cloud Run env vars:** Add `DATASETS_BUCKET_NAME=juno-preset-data` to the Cloud Run service configuration (or GCP Secret Manager, matching how other env vars like `GCP_BUCKET_NAME` are managed).

9. **Run backend tests** after all changes land:
   ```bash
   pytest backend/tests/utils/test_preset_data.py -v
   ```
