# PRD: SP1 — GCS Dataset Infrastructure, Manifest & Backend

**Sub-project:** SP1  
**Branch context:** `athena_health_part1`  
**Date:** 2026-06-27  
**Status:** Planning — no implementation started

---

## 1. Problem

Seven medical research datasets (meqsum, mts-dialog, notechat, primock57, primock57-conversations, smith-collection, soap-summary) currently live as full file trees under `preset-data/` in the Juno git repo. Together they contain over 7,000 directories and 14,000+ files. This makes the repository heavyweight: clones are slow, CI pipelines pull unnecessary data, and dataset versioning is conflated with application versioning.

The fix is to move dataset files to Google Cloud Storage and keep only a lightweight JSON manifest committed to the repo. The manifest is the single source of truth for listing and preview; GCS is the storage layer for full file retrieval (covered in SP2).

---

## 2. Goals

1. Upload all 7 datasets to `gs://juno-preset-data/preset-data/{group}/{input_id}/{filename}` (one-time migration script).
2. Generate and commit `preset-data/manifest.json` with full input listings and one embedded sample per dataset for preview.
3. Rewrite `backend/utils/preset_data.py` to serve `list_datasets()` and sample `read_dataset_file()` calls from the manifest; establish the SP2 boundary for non-sample reads.
4. Add `DATASETS_BUCKET_NAME` env var to `constants.py` and `backend/.env.example`.
5. Delete local `preset-data/{group}/` directories after verified upload. Only `manifest.json`, `example/`, and `README.md` remain in `preset-data/`.
6. No frontend changes required for SP1.

---

## 3. Non-Goals

- On-demand GCS download for non-sample input IDs (deferred to SP2).
- Frontend changes beyond what is needed to keep the existing UX working (SP1 preserves current behavior).
- Dataset versioning or multi-bucket support.
- Access control changes to the GCS bucket.
- HIPAA controls on dataset storage (separate initiative per project memory).
- Automating the migration in CI/CD — this is a one-time manual operation.

---

## 4. Architecture Decisions

### A. Upload Script — `scripts/preset-data-scripts/upload_to_gcs.py`

**Purpose:** One-time migration tool. Reads every file under local `preset-data/{group}/{input_id}/` and uploads to `gs://juno-preset-data/preset-data/{group}/{input_id}/{filename}`.

**Interface:**

```
python scripts/preset-data-scripts/upload_to_gcs.py [--dry-run] [--group GROUP]
```

- `--dry-run`: Print what would be uploaded; make zero GCS calls.
- `--group GROUP`: Restrict upload to a single dataset group (useful for resuming or re-uploading).
- Without flags: uploads all 7 groups.

**Behavior:**

1. Scan `preset-data/` for subdirectories that are dataset group directories (i.e., not `example/` and not files like `README.md`, `manifest.json`). Hardcode or auto-detect by checking for sub-subdirectories.
2. For each `group/input_id/filename`, construct the GCS blob name `preset-data/{group}/{input_id}/{filename}`.
3. Upload using `google.cloud.storage.Client`. Use the service account credential already configured for the backend (Application Default Credentials or `GOOGLE_APPLICATION_CREDENTIALS`).
4. Log each upload: `[group/input_id/filename] → gs://juno-preset-data/...` with byte count.
5. Track and print a summary: total files attempted, succeeded, skipped (already exists via `blob.exists()`), failed.
6. On failure of any individual file: log the error and continue; do not abort the full run.
7. Exit non-zero if any file failed.

**Note:** This script does NOT delete local files. Deletion is a separate step (see section F).

---

### B. Manifest Generation — `scripts/preset-data-scripts/generate_manifest.py` (or `--generate-manifest` flag on upload script)

**Recommendation:** Implement as a standalone script `generate_manifest.py`. This keeps responsibilities separated: upload can be re-run independently of manifest regeneration, and manifest can be regenerated without re-uploading.

**Purpose:** Reads the local `preset-data/` directory tree (must be run before local deletion) and writes `preset-data/manifest.json`.

**Interface:**

```
python scripts/preset-data-scripts/generate_manifest.py [--output PATH]
```

- `--output`: Override output path (default: `preset-data/manifest.json`).

**Behavior:**

1. Walk each group directory in alphabetical order.
2. For each group, collect all input IDs (subdirectory names) sorted lexicographically. This preserves the original sort order that `list_datasets()` currently produces via `sorted()`.
3. Determine `file_types` from the first input's file listing (assumes all inputs in a group have the same file types — verified by inspection).
4. Pick the first input ID as `sample.input_id`.
5. Read each file in the sample input directory and embed its content as a UTF-8 string. If a file is not valid UTF-8, decode with `errors="replace"`.
6. Write `preset-data/manifest.json` with the schema defined in section C.
7. Print a summary: groups processed, total inputs indexed, sample content sizes.

**Run order:** `generate_manifest.py` first (while files are local), then `upload_to_gcs.py`, then delete local dirs.

---

### C. Manifest JSON Schema

Exact shape. All fields are required.

```json
{
  "generated_at": "2026-06-27T12:00:00Z",
  "bucket": "juno-preset-data",
  "gcs_prefix": "preset-data",
  "datasets": [
    {
      "group": "meqsum",
      "total_inputs": 1000,
      "file_types": ["question.txt", "summary.txt"],
      "inputs": ["0001", "0002", "0003"],
      "sample": {
        "input_id": "0001",
        "files": {
          "question.txt": "<full text content of preset-data/meqsum/0001/question.txt>",
          "summary.txt": "<full text content of preset-data/meqsum/0001/summary.txt>"
        }
      }
    }
  ]
}
```

**Field notes:**

| Field | Type | Notes |
|---|---|---|
| `generated_at` | ISO-8601 UTC string | Set at generation time, e.g. `datetime.utcnow().isoformat() + "Z"` |
| `bucket` | string | Always `"juno-preset-data"` for this migration |
| `gcs_prefix` | string | Top-level GCS path segment, always `"preset-data"` |
| `datasets[].group` | string | Directory name, e.g. `"meqsum"`, `"mts-dialog"` |
| `datasets[].total_inputs` | int | `len(inputs)` — redundant with `inputs` but useful for quick display |
| `datasets[].file_types` | string[] | File names (not extensions) from the first input, e.g. `["question.txt", "summary.txt"]`. Sorted lexicographically. Maps to what the current `list_datasets()` returns as `"files"`. |
| `datasets[].inputs` | string[] | ALL input IDs, sorted lexicographically. Input IDs are directory names as-found (e.g. `"0001"`, `"RES0213"`, `"day1-consultation01"`). |
| `datasets[].sample.input_id` | string | Always `inputs[0]` |
| `datasets[].sample.files` | object | Keys are file type names; values are full UTF-8 text content |

**Input ID formats observed in existing data:**

| Group | ID format | Example |
|---|---|---|
| meqsum | zero-padded integer | `0001` |
| mts-dialog | zero-padded integer | (TBD from inspection) |
| notechat | (TBD) | |
| primock57 | `day{N}-consultation{NN}` | `day1-consultation01` |
| primock57-conversations | same as primock57 | |
| smith-collection | `RES{NNNN}` | `RES0213` |
| soap-summary | integer (unpadded) | `1468` |

The manifest uses these IDs verbatim. No normalization.

**Manifest size estimate:** ~100–250 KB total (dominated by the sample text content). Safe to commit to git.

**Note on sensitive content:** Sample content embedded in the manifest will be committed to the repository. All 7 datasets are publicly available de-identified research corpora (MTS-Dialog, NoteChat, etc.). Verify before committing that no real patient data is present.

---

### D. Backend Changes — `backend/utils/preset_data.py`

**Current state:**
- `PRESET_DATA_ROOT` resolves to `preset-data/` on disk (or `PRESET_DATA_PATH` env override).
- `list_datasets()` walks the local filesystem.
- `read_dataset_file()` validates via `list_datasets()` then reads a local file path.

**After SP1:**

```python
# New imports
import json
from pathlib import Path

# Keep PRESET_DATA_ROOT for backward compat and for locating manifest.json
PRESET_DATA_ROOT = Path(
    os.environ.get("PRESET_DATA_PATH")
    or (Path(__file__).resolve().parent.parent.parent / "preset-data")
)

MANIFEST_PATH = PRESET_DATA_ROOT / "manifest.json"

_manifest_cache: dict | None = None

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
            "files": entry["file_types"],   # manifest uses "file_types"; API uses "files"
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

**New exception — add to `preset_data.py`:**

```python
class GCSFetchRequired(Exception):
    """Raised when the requested file is not in the manifest and requires GCS fetch (SP2)."""
    def __init__(self, group: str, input_id: str, filename: str):
        self.group = group
        self.input_id = input_id
        self.filename = filename
        super().__init__(f"GCS fetch required for {group}/{input_id}/{filename}")
```

**SP2 boundary:** In `backend/routes/datasets.py`, the `get_dataset_file_route` handler catches `GCSFetchRequired` and returns HTTP 503 with a clear message until SP2 is implemented:

```python
# In datasets.py — to be updated in SP1
from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

@datasets_bp.route("/care_plan/datasets/<group>/<input_id>/<string:filename>", methods=["GET"])
@verify_firebase_token
def get_dataset_file_route(user_id: str, group: str, input_id: str, filename: str):
    _ = user_id
    try:
        file_bytes = read_dataset_file(group, input_id, filename)
        content = _extract_text_from_bytes(file_bytes, filename)
    except GCSFetchRequired:
        return jsonify({"error": "On-demand GCS fetch not yet implemented (SP2)"}), 503
    except FileNotFoundError:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"filename": filename, "content": content})
```

**Manifest caching note:** `_manifest_cache` is a module-level variable that persists for the lifetime of the Flask worker process. This is intentional — the manifest is static after deployment. If the manifest is ever regenerated and re-deployed, the new worker processes will pick it up on first load.

**Old helper removed:** `_input_files()` is no longer needed and should be deleted.

---

### E. Env Var Additions

**`backend/utils/constants.py` — add to `Constants` class:**

```python
# ── Dataset GCS config ─────────────────────────────────────────────────────
DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
```

The default value is provided so local development without the env var set still works (since SP1 doesn't use GCS for reads — only the scripts do). SP2 will use `DATASETS_BUCKET_NAME_ENV_VAR` when fetching non-sample files from GCS.

**`backend/.env.example` — add:**

```
# Dataset GCS bucket (preset research datasets)
DATASETS_BUCKET_NAME=juno-preset-data
```

**`backend/.env` — add the same line** (for local dev; actual value matches the example since there's only one bucket).

**`frontend/.env.local` — no changes required.**

---

### F. Local File Deletion

After the upload is verified and `manifest.json` is committed, the local dataset directories must be deleted.

**Option 1 (recommended): `--delete-local` flag on `upload_to_gcs.py`**

```
python scripts/preset-data-scripts/upload_to_gcs.py --delete-local
```

Behavior: After a successful upload run (zero failures), delete each local `preset-data/{group}/` directory. Refuses to delete if any file failed to upload. Prints a confirmation prompt before deleting.

**Option 2: Manual `rm -rf`**

```bash
cd /root/projects/juno
for group in meqsum mts-dialog notechat primock57 primock57-conversations smith-collection soap-summary; do
  rm -rf preset-data/$group
done
```

Either option is acceptable; `--delete-local` is preferred to avoid accidental partial deletion.

**What remains in `preset-data/` after deletion:**

```
preset-data/
  manifest.json        ← committed to git
  example/             ← kept as reference (already committed)
  README.md            ← kept
```

**`.gitignore` consideration:** Confirm `preset-data/` is not currently gitignored. The group dirs were tracked before; after deletion only the above three items need to be tracked. No `.gitignore` changes expected.

---

### G. Frontend Changes

No frontend code changes are required for SP1.

**Why this works without changes:**

The `Dataset` TypeScript type is `{ group: string; inputs: string[]; files: string[] }`. The manifest-backed `list_datasets()` returns exactly this shape:

- `group` → `entry["group"]`  
- `inputs` → `entry["inputs"]` (all input IDs, same as today)  
- `files` → `entry["file_types"]` (renamed in the Python layer before serialization)  

The `PresetDataPanel` preview flow calls `getDatasetFileContent(group, previewInput, filename)` where `previewInput = Array.from(selection.inputs)[0] ?? dataset.inputs[0]`. When no input is selected, this defaults to `dataset.inputs[0]`, which equals the manifest `sample.input_id`. The backend will return manifest content for this case without any GCS call.

**Edge case — user selects a non-sample input and clicks Preview:**

`handleView` will call `GET /care_plan/datasets/{group}/{non_sample_id}/{filename}`. The backend raises `GCSFetchRequired` and returns HTTP 503 until SP2 is implemented. The FE `catch` block in `handleView` will display: `"Could not load preview."` (existing error handling). This is acceptable for SP1.

If this edge case is considered a poor UX during the SP1/SP2 gap, the FE can be patched to always pass `dataset.inputs[0]` to `handleView` regardless of selection — a one-line change in `PresetDataPanel.tsx` line 78. This is optional for SP1.

---

## 5. API Change Summary

| Endpoint | Before SP1 | After SP1 |
|---|---|---|
| `GET /care_plan/datasets` | Reads local filesystem; returns `{datasets: [{group, inputs, files}]}` | Reads `manifest.json`; returns identical shape |
| `GET /care_plan/datasets/{group}/{input_id}/{filename}` | Reads local file | Returns manifest sample content if `input_id == sample.input_id`; returns HTTP 503 for other input IDs |

**Response shape is unchanged for `GET /care_plan/datasets`.** No clients need updating.

**New HTTP 503 case for the file endpoint** is a new behavior, but only for input IDs other than the sample (inputs[0]). The FE preview flow defaults to inputs[0] so this is not hit in normal usage.

---

## 6. Frontend Change Summary

No changes required for SP1. The existing `listDatasets()`, `getDatasetFileContent()`, `PresetDataCard`, and `PresetDataPanel` all work without modification.

Optional (not required for SP1): Patch `PresetDataPanel.tsx` line 78 to always preview from `dataset.inputs[0]` to avoid 503 errors when a non-sample input is selected before SP2 lands.

---

## 7. Testing

### Script testing

- Run `generate_manifest.py` against the current local `preset-data/` and inspect the output manually:
  - All 7 groups present.
  - `inputs` count matches directory count for each group (spot-check meqsum = 1000, soap-summary = 1473).
  - `sample.input_id` equals the first sorted input.
  - `sample.files` contains readable text (not binary garbage).
- Run `upload_to_gcs.py --dry-run` and verify the logged paths match expected GCS locations.
- Run `upload_to_gcs.py` for one group (e.g. `--group notechat`, 50 inputs) and verify files appear in GCS via `gsutil ls gs://juno-preset-data/preset-data/notechat/` or GCS console.
- Run full upload for all 7 groups.
- After full upload, spot-check 3–5 files with `gsutil cat gs://juno-preset-data/preset-data/meqsum/0001/question.txt`.

### Backend unit tests

Add/update tests in the backend test suite (likely `tests/test_preset_data.py`):

- `test_list_datasets_from_manifest`: mock `MANIFEST_PATH` with a small fixture manifest; assert `list_datasets()` returns correct shape.
- `test_read_sample_file`: assert `read_dataset_file("meqsum", "0001", "question.txt")` returns bytes matching manifest sample content.
- `test_read_non_sample_raises_gcs_fetch_required`: assert `read_dataset_file("meqsum", "0002", "question.txt")` raises `GCSFetchRequired`.
- `test_read_unknown_group_raises_file_not_found`: assert `read_dataset_file("nonexistent", "0001", "question.txt")` raises `FileNotFoundError`.
- `test_list_datasets_missing_manifest`: remove manifest path; assert `list_datasets()` returns `[]`.
- `test_manifest_cache`: call `list_datasets()` twice; assert the manifest file is only opened once (mock `open`).

### Integration test (manual)

1. Start the backend locally with the manifest committed but local dataset dirs deleted.
2. Open the Juno frontend and navigate to the Batch page.
3. Verify all 7 groups appear in the PresetDataCard sidebar.
4. Click "Preview" on a file type; verify sample content appears (served from manifest).
5. Select a non-sample input, click Preview; verify the error message appears gracefully (SP2 boundary).

---

## 8. Manual Intervention Required From You

In order from first to last:

1. **Before running scripts:** Ensure `GOOGLE_APPLICATION_CREDENTIALS` or Application Default Credentials are configured on the machine where the script will run (the firebase-adminsdk service account has objectAdmin on `juno-preset-data`).

2. **Generate manifest** (must happen before any local deletion):
   ```bash
   cd /root/projects/juno
   python scripts/preset-data-scripts/generate_manifest.py
   ```

3. **Review `preset-data/manifest.json`** — spot-check content, confirm no real patient data, confirm all 7 groups and correct input counts.

4. **Commit manifest** before upload (so manifest is in git independently of GCS state):
   ```bash
   git add preset-data/manifest.json
   git commit -m "chore: add preset-data manifest for GCS migration (SP1)"
   ```

5. **Upload datasets to GCS:**
   ```bash
   python scripts/preset-data-scripts/upload_to_gcs.py --dry-run   # verify paths
   python scripts/preset-data-scripts/upload_to_gcs.py             # actual upload
   ```

6. **Verify GCS upload** — spot-check files via GCS console or `gsutil`.

7. **Delete local dataset dirs** (after verified upload):
   ```bash
   python scripts/preset-data-scripts/upload_to_gcs.py --delete-local
   # OR manually:
   for g in meqsum mts-dialog notechat primock57 primock57-conversations smith-collection soap-summary; do rm -rf preset-data/$g; done
   ```

8. **Update deployment env vars** — add `DATASETS_BUCKET_NAME=juno-preset-data` to the Cloud Run service configuration (or GCP Secret Manager, depending on how other env vars are managed).

9. **Run backend tests** after the changes land to confirm no regressions.

---

## 9. Open Questions & Decisions

| # | Item | Status |
|---|---|---|
| Q1 | Should `generate_manifest.py` be a standalone script or a flag on `upload_to_gcs.py`? | [RESOLVED: standalone script `generate_manifest.py` — cleaner separation of concerns] |
| Q2 | Should `--delete-local` be part of the upload script or a separate script? | [RESOLVED: `--delete-local` flag on `upload_to_gcs.py` — keeps deletion gated on upload success] |
| Q3 | GCS bucket, path convention, and bucket name env var. | [RESOLVED: bucket=`juno-preset-data`, path=`preset-data/{group}/{input_id}/{filename}`, env var=`DATASETS_BUCKET_NAME`] |
| Q4 | What HTTP status should the backend return for non-sample input_id preview before SP2? | [RESOLVED: HTTP 503 with `{"error": "On-demand GCS fetch not yet implemented (SP2)"}` — clearly signals "coming soon" vs. 404 "not found"] |
| Q5 | Should the manifest cache be invalidated across requests (e.g. on SIGHUP)? | [RESOLVED: No — manifest is static per deployment. Process restart (Cloud Run redeploy) is the natural invalidation mechanism.] |
| Q6 | Should `total_inputs` be included in the manifest given it's redundant with `len(inputs)`? | [RESOLVED: Yes — retained for convenience when reading the manifest file directly without parsing the full inputs list] |
| Q7 | Does `primock57` and `primock57-conversations` share the same input ID format? | [RESOLVED: primock57-conversations uses the same day{N}-consultation{NN} format as primock57, confirmed by inspection of preset-data/primock57-conversations/ directory names] |
| Q8 | Are all files in a given group's inputs guaranteed to have the same set of file types (i.e., is `file_types` uniform across inputs)? | [RESOLVED: file types are uniform across all inputs within a group — confirmed] |
| Q9 | Should the upload script skip already-uploaded blobs (idempotent re-run)? | [RESOLVED: Yes — check `blob.exists()` before uploading; log as "skipped". Makes re-runs safe.] |
| Q10 | Optional FE patch to always preview from `inputs[0]` during SP1/SP2 gap — in scope for SP1? | [DEFERRED — SP2 landing shortly after SP1 makes the gap brief; only patch if SP2 is delayed] |
| Q11 | Does `backend/.env` (the actual local env file, not just `.env.example`) need `DATASETS_BUCKET_NAME` for any SP1 functionality? | [RESOLVED: Not required for SP1 since manifest reads don't hit GCS. Add anyway for consistency and SP2 readiness.] |
| Q12 | Are there any CI jobs or tests that read from `preset-data/{group}/` directories directly that will break after deletion? | [RESOLVED: remove any tests that directly read from preset-data dirs; no tests should depend on local preset datasets — addressed in this commit] |
