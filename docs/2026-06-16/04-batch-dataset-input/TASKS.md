# Tasks: Batch/Dataset Input

Read `PRD.md` in this folder first. This sub-project has the most moving parts — follow the task
order strictly, and stop at the flagged checkpoints.

---

### Task 1 — Extract reusable pipeline executor (v1-2)

**File:** `backend/routes/simplify_v1_2.py`

Refactor `_generate_stream(user_id)` into two pieces:
1. Extract request/input resolution into a small helper that returns resolved text and input
   metadata. This helper handles user-uploaded files/text for single runs; batch runs will build the
   same resolved text shape from group/input selections before calling the executor.
2. `run_v1_2_pipeline(text: str, metrics: Metrics, grading_enabled: bool) -> Generator[str, None, None]`
   — everything from "Step 1: extract medical terms" onward in the current function body, parameterized
   on `text` instead of reading it from `resolved`/`request`. It still does its own SSE `yield`s for
   step progress, builds `SimplifiedCarePlan`/`Grading` as already wired in Sub-projects 1/3, and as
   its last action yields `{"step": "result", "data": <SimplifyOutput.to_dict()>}` — but does **not**
   itself call `save_simplify_output` (that becomes the caller's job, so both the single-run route and
   the batch route can decide independently whether/how to save).
2. The existing `_generate_stream(user_id)` becomes a thin wrapper: parse the request into `text`
   (via the existing input-resolution code), build `Metrics`/`Input` as today, call
   `run_v1_2_pipeline(...)`, forward its yields, and on the final result do the existing
   `save_simplify_output` + `saved_id` attachment + final re-yield with `saved_id` populated.

**Acceptance criteria:** Every existing v1-2 test (Sub-projects 1/3's tests) passes unchanged — this
step must be behavior-neutral. Add one new test that calls `run_v1_2_pipeline()` directly with a
plain string and asserts it yields the same step sequence as before.

**Depends on:** Sub-project 3 Task 3 (the function being extracted already has grading wiring in it).

---

### Task 2 — Same extraction for v1 and v1-1

**Files:** `backend/routes/simplify.py`, `backend/routes/simplify_v1_1.py`

Same pattern as Task 1: `run_v1_pipeline(text, metrics, grading_enabled)` and
`run_v1_1_pipeline(text, metrics, grading_enabled)`.

**Acceptance criteria:** Same as Task 1, for each version.

**Depends on:** Task 1 (copy the proven pattern).

---

### Task 3 — `backend/utils/preset_data.py`

**File (new):** `backend/utils/preset_data.py`

Implement `list_datasets()` and `read_dataset_file(group, input_id, filename)` exactly per PRD.md §4,
**with the path-traversal guard as a hard requirement**:
```python
from pathlib import Path

PRESET_DATA_ROOT = (Path(__file__).resolve().parent.parent.parent / "preset-data")

def list_datasets() -> list[dict]:
    datasets = []
    for group_dir in sorted(p for p in PRESET_DATA_ROOT.iterdir() if p.is_dir()):
        inputs = sorted(p.name for p in group_dir.iterdir() if p.is_dir())
        files = []
        if inputs:
            first_input_dir = group_dir / inputs[0]
            files = sorted(p.name for p in first_input_dir.iterdir() if p.is_file())
        datasets.append({"group": group_dir.name, "inputs": inputs, "files": files})
    return datasets

def read_dataset_file(group: str, input_id: str, filename: str) -> bytes:
    datasets = list_datasets()
    match = next((d for d in datasets if d["group"] == group), None)
    if not match or input_id not in match["inputs"] or filename not in match["files_for"](input_id):
        raise FileNotFoundError()
    path = (PRESET_DATA_ROOT / group / input_id / filename).resolve()
    if not path.is_relative_to(PRESET_DATA_ROOT.resolve()):
        raise FileNotFoundError()
    return path.read_bytes()
```
Note: the sketch above calls a `files_for(input_id)` helper that doesn't exist yet in `list_datasets()`'s
return shape (which only returns the *first* input's files as the group's representative list) — for
`read_dataset_file`, you need to check the filename exists in the **specific `input_id` requested**,
not just the first one (a user could in principle ask to preview a file from input 2, which might not
match input 1 exactly even though the convention assumes they're copies). Add a small internal helper
that lists files for an arbitrary input dir, reuse it both for the "representative files" list in
`list_datasets()` and for this existence check.

**Acceptance criteria:** Unit tests: normal listing/read works against a temp fixture directory
structure; `read_dataset_file("DocConv", "../../../etc", "passwd")`,
`read_dataset_file("DocConv", "input-1", "../../../../etc/passwd")`, and similar traversal attempts
all raise `FileNotFoundError` (mapped to HTTP 404 at the route layer, never 500, never a path
disclosed in any error message).

**Depends on:** nothing.

---

### Task 4 — Dataset routes

**File (new):** `backend/routes/datasets.py`, registered in `backend/routes/__init__.py`

```python
datasets_bp = Blueprint("datasets", __name__)

@datasets_bp.route("/simplify/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id):
    return jsonify({"datasets": list_datasets()})

@datasets_bp.route("/simplify/datasets/<group>/<input_id>/<filename>", methods=["GET"])
@verify_firebase_token
def get_dataset_file_route(user_id, group, input_id, filename):
    try:
        file_bytes = read_dataset_file(group, input_id, filename)
    except FileNotFoundError:
        return jsonify({"error": "Not found"}), 404
    content = _extract_text(file_bytes, filename)  # reuse from routes/simplify.py — move to a shared utils module if it's currently private there
    return jsonify({"filename": filename, "content": content})
```
(If `_extract_text` is private to `simplify.py`, move it to `backend/utils/text_extract.py` or similar
shared location — don't duplicate it.)

**Acceptance criteria:** Per PRD.md §7's listing/read tests, now at the HTTP layer (auth required,
404 on bad input, 200 with correct shape on valid input).

**Depends on:** Task 3.

---

### Task 5 — Extend the `Input` model

**File:** `backend/models/input.py` (from Sub-project 1)

Add four optional fields: `dataset_group: str | None = None`, `dataset_input: str | None = None`,
`selected_files: list[str] | None = None`, `batch_group_id: str | None = None`. Add a constructor
helper `Input.from_batch_dataset(text, dataset_group, dataset_input, selected_files, batch_group_id)`.

**Acceptance criteria:** Round-trips through `to_dict()`/`from_dict()` with and without the new fields
populated (backward compatible with Sub-project 1/3's existing `Input` usages, which simply leave
these as `None`).

**Depends on:** Sub-project 1 Task 3.

---

### Task 6 — `POST /simplify/batch` route

**File (new):** `backend/routes/batch.py`, registered in `backend/routes/__init__.py`

Implement per PRD.md §4 "Per-input execution" and "SSE shape for the batch endpoint":
1. Parse `version`, `grading_enabled`, `selections` from the JSON body.
2. Resolve `"inputs": "all"` against a fresh `list_datasets()` call (don't trust a stale client list).
3. Compute group-scoped batch identifiers using one timestamp per request:
   `batch_group_id = f"{group}-{timestamp}"`. A multi-group request produces multiple identifiers,
   one per group, never `Batch-<timestamp>`.
4. Build a flat, ordered list of `(group, input_id, files)` tuples across all selections, sorted by
   group then input id.
5. For each tuple, sequentially: read+extract+concatenate the selected files via Task 3/4's helpers,
   build `Metrics`/`Input` (using `Input.from_batch_dataset(...)` from Task 5), call the matching
   `run_v{version}_pipeline(...)` from Tasks 1–2, forward its SSE yields wrapped in the
   `batch_progress` envelope described in PRD.md §4, save the resulting `SimplifyOutput` individually
   via the existing `save_simplify_output`, storing `dataset_group` and `batch_group_id` as top-level
   metadata for that saved result, and collect it into a results list.
6. After all inputs are processed, yield the final `batch_result` event with `batch_group_ids`
   (a map of group name to group-scoped identifier) and all collected outputs.

**Acceptance criteria:** Per PRD.md §7's batch route tests (use a stubbed/mocked pipeline executor in
tests — don't make real LLM calls in automated tests; mock `run_v1_2_pipeline` etc. to return a fixed
`SimplifyOutput` and assert call order + count). Multi-group tests must assert distinct
group-scoped IDs, e.g. `GroupA-<timestamp>` and `GroupB-<timestamp>`.

**Depends on:** Tasks 1, 2, 4, 5.

---

### Task 7 — Frontend: dataset types + API client

**Files:** `frontend/src/types/datasets.ts` (new), `frontend/src/api/datasets.ts` (new — match
whatever existing convention `frontend/src/api/` or equivalent uses for other endpoints, e.g.
`saved_outputs` client)

Types: `Dataset { group: string; inputs: string[]; files: string[] }`. API functions:
`listDatasets(): Promise<Dataset[]>`, `getDatasetFileContent(group, input, filename): Promise<{filename, content}>`,
`runBatch(selections, version, gradingEnabled): EventSource-or-fetch-stream` (match whatever SSE
client pattern the existing single-run submit already uses — reuse it, don't reinvent SSE handling).

**Acceptance criteria:** Compiles; manually callable against the Task 4/6 backend routes.

**Depends on:** Tasks 4, 6.

---

### Task 8 — Frontend: `PresetDataCard` component tree

**Files (new):** `frontend/src/components/PresetDataCard.tsx`, `DatasetGroupRow.tsx`, plus whatever
sub-components the implementer finds natural for the inputs/files lists and the file preview.

Implement the UI described in PRD.md §6: collapsed by default, group rows with select-all + expand,
nested Inputs/Files toggles with checkboxes, a "View" button per file opening a small preview of that
file's content (call `getDatasetFileContent` for the first selected input in that group, or the
first input overall if none selected yet — per your "only need to see files from 1 input" instruction).
Maintain selection state as `{ group: string; inputs: string[] | 'all'; files: string[] }[]`, exposed
to the parent page via a callback prop so the upload screen can decide single-run vs batch submission.

**Acceptance criteria:** Manual run (`/run` skill) — expand a group, select inputs (individually and
via select-all), select files, preview one, confirm state updates are reflected (e.g. via a debug log
or temporary on-screen state dump during development, removed before considering this task done).

**Depends on:** Task 7.

---

### Task 9 — Frontend: wire batch submission into the upload screen

**File:** `frontend/src/pages/simplify/SimplifyPage.tsx` (from Sub-project 2)

1. Render `<PresetDataCard onSelectionChange={...} />` below the existing upload-data card and above
   the Configuration card.
2. On submit: if the preset-data selection is non-empty, call `runBatch(...)` instead of the existing
   single-run submit path; otherwise behave exactly as before.
3. Extend the existing SSE-progress UI to show "Input {index} of {total}" when handling
   `batch_progress` events, layered above the existing per-step labels (which still come through
   nested inside each input's processing, per PRD.md §4's SSE shape).
4. On `batch_result`, decide how to present N outputs — simplest correct behavior for this task is to
   show a summary ("10 reports generated") with a link/button per output to view each individually
   (reusing the existing single-result view component for each); a richer multi-output browsing UI is
   not required here, since Sub-project 5's history/grouping view is where users will browse batch
   outputs after the fact.

**Acceptance criteria:** End-to-end manual run against a real populated `preset-data/` group (see
PRD.md §8 — you need to add this) produces N saved outputs sharing one `batch_group_id`, viewable via
the existing Sidebar (even before Sub-project 5's grouping UI exists, they'll just appear as N
separate entries — that's expected and fine at this stage).

**Depends on:** Task 8.

---

### Task 10 — Tests

Cover PRD.md §7 in full, plus Task 1/2's behavior-neutrality tests.

**Depends on:** Tasks 1–6.

---

## Summary of what requires you (not a dev agent)

1. **Add a real populated dataset** under `preset-data/` before Task 9 can be manually verified
   end-to-end (or explicitly approve using synthetic fixtures left in the repo for this purpose).
2. **Post-deploy spot check:** metadata-based grouping has been checked now and can be spot checked
   after deploy.
3. **Recommended (not blocking):** review the Task 1 refactor before Tasks 5–9 build on top of it.
