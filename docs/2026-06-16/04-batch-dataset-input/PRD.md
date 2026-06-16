# PRD: Batch/Dataset Input

Sub-project 4 of 5. **Depends on Sub-project 1** (envelope/models) and **Sub-project 3** (the
grading toggle, since batch runs honor it too). Depends on **Sub-project 2** only loosely — it reuses
the `version` concept, but this sub-project also requires one additional backend refactor that
Sub-project 2 didn't scope (see §4 "Required refactor"). This is the largest of the five sub-projects;
expect it to take the longest and to be the one most worth a mid-implementation check-in with you.

## 1. Problem

`preset-data/` already exists as a documented convention (`preset-data/README.md`):
```
preset-data/
  GroupName/
    ProcessName/
      file1.pdf
      file2.pdf
```
But it's wired into the **frontend only**, loaded from the public folder at build time, not through
any API — there's an existing "preset dataset modal" that reads this static, build-time list. It
can't reflect new files added without a rebuild/deploy, and it doesn't support the selection model you
want.

You want: an API-backed, inline (non-modal) card on the upload screen that lists every dataset group,
lets you select whole groups or individual inputs within/across groups, lets you pick which files
within each input to use (uniformly across all selected inputs in that group), preview a file's
content before committing, and then run the pipeline once per selected input, sequentially, with all
the runs from one submission tagged so Sub-project 5 can group them in the output history.

## 2. Goals

- `GET /simplify/datasets` — list every group, its input folders, and the representative file names
  (read from the first input folder in each group, per your example: "only need to see files from 1
  input since other inputs are supposed to be a copy of the first input").
- `GET /simplify/datasets/<group>/<input>/<filename>` — fetch one file's content for the preview
  ("view") button. **Path-traversal safety is a hard requirement here** — see §4.
- `POST /simplify/batch` — run the pipeline once per selected input (across one or more groups),
  sequentially, honoring the same `version`/`grading_enabled` config as a single run, tagged with one
  shared batch identifier.
- Frontend: a "Preset Data" card, collapsed by default, below the existing upload-data card. Expands
  to show each dataset group with select-all-in-group / select-individual-input checkboxes, an
  "Inputs"/"Files" sub-toggle per group, and a small "View" action per file.

## 3. Non-Goals

- Not supporting user-uploaded batch datasets (confirmed — `preset-data/` only, for now).
- Not parallelizing batch runs (confirmed sequential, matches your "one after another" instruction —
  also avoids LLM rate-limit issues).
- Not building the output-history grouping UI itself (Sub-project 5 consumes the `batch_group_id`
  this sub-project produces).

## 4. Architecture Decisions

**Required refactor (beyond Sub-project 2's scope).** Today, each version's pipeline execution
(per-step SSE yielding, scoring, structuring) lives inline inside a single Flask view function that
also parses the incoming HTTP request (file uploads, form fields). To run the same pipeline N times in
one batch request — once per selected input — request input resolution needs to be extracted first,
then each individual process from the batch can be run through the same executor. The resolved input
can come from a few files uploaded by a user, or from one or more group/individual process selections
based on uploaded/preset data. This sub-project extracts each version's core executor into a plain
function, e.g. in `simplify_v1_2.py`:
```python
def run_v1_2_pipeline(text: str, metrics: Metrics, grading_enabled: bool) -> Generator[str, None, SimplifyOutput]:
    ...  # the existing step-by-step body of _generate_stream, minus the request-parsing prologue
```
that yields SSE-formatted progress strings (so the live single-upload route and the new batch route
both consume the same generator and get the same step-by-step UX) and returns/yields a final
`SimplifyOutput`. The existing route handlers become thin wrappers: parse the request into `text`,
build a `Metrics`, call this function, stream its output. Do the same for v1 and v1-1. **This is a
mechanical extraction, not a behavior change** — the goal is zero difference in single-upload
behavior, verified by Sub-project 1/2/3's existing tests still passing unchanged.

**Dataset scanning (`backend/utils/preset_data.py`, new):**
```python
PRESET_DATA_ROOT = Path(__file__).parent.parent.parent / "preset-data"

def list_datasets() -> list[dict]:
    # for each child dir of PRESET_DATA_ROOT (each a "group"):
    #   inputs = sorted child dir names
    #   files = sorted file names inside the first input dir (if any)
    ...

def read_dataset_file(group: str, input_id: str, filename: str) -> bytes:
    # resolve group/input_id/filename against the *actual directory listing* from list_datasets(),
    # not raw path concatenation — reject anything not found in that listing before touching the
    # filesystem. This closes the path-traversal hole that naively joining user-supplied path
    # segments (e.g. "../../etc/passwd") would otherwise open.
    ...
```
**Security requirement, not optional:** `read_dataset_file` (and the route that calls it) must
validate `group`, `input_id`, and `filename` against the real, enumerated contents of
`PRESET_DATA_ROOT` — e.g. resolve the final path with `Path.resolve()` and assert it's still a
descendant of `PRESET_DATA_ROOT`, AND that the three segments exactly match entries returned by
`list_datasets()`. Reject with 404 (not 400 — don't reveal whether a path exists outside the allowed
root) on any mismatch.

**`GET /simplify/datasets` response shape:**
```json
{
  "datasets": [
    { "group": "DocConv", "inputs": ["input-1", "input-2", "...input-10"], "files": ["transcript.txt", "notes.txt"] }
  ]
}
```

**`GET /simplify/datasets/<group>/<input_id>/<filename>` response:** `{"filename": "...", "content":
"..."}` (decoded text — same extension allowlist as uploads: pdf/txt/docx, extracted via the existing
`_extract_text` helper so PDF/DOCX preview also works, not just plain text).

**Selection model → batch request shape.** Per your "select all for a group, individual in group, or
across groups" requirement, the request body is a list of per-group selections, not a single flat
list — file selection is scoped per group (uniform across that group's selected inputs, per your
"select transcript = use transcript from all inputs" rule), but multiple groups can appear in one
submission:
```json
POST /simplify/batch
{
  "version": "v1-2",
  "grading_enabled": true,
  "selections": [
    { "group": "DocConv", "inputs": "all", "files": ["transcript.txt", "notes.txt"] },
    { "group": "OtherDataset", "inputs": ["input-3", "input-7"], "files": ["notes.txt"] }
  ]
}
```
`"inputs": "all"` expands server-side to every input currently in that group (re-resolved at request
time, not from a stale client-side list).

**Batch identifier.** A "batch" is group-scoped. Each selected group gets its own
`batch_group_id = f"{group}-{timestamp}"` (e.g. `DocConv-20260616153012`). If one submission spans
multiple groups, each group's outputs keep their own group-specific identifier (for example
`DocConv-20260616153012` and `OtherDataset-20260616153012`), rather than being collapsed under a
generic `Batch-<timestamp>` value. The output file/result also includes the dataset group identifier
so downstream output history can keep results attached to the correct group.

**Per-input execution.** For each selected input (in selection order, each group's inputs in sorted
order, fully sequential — no concurrency): read the selected files via `read_dataset_file`, extract
text from each (reusing `_extract_text`), concatenate with a clear separator (e.g.
`"\n\n--- {filename} ---\n\n"` between files) into one combined text blob, then call the refactored
`run_v1_2_pipeline(text, metrics, grading_enabled)` (or v1/v1-1 equivalent) exactly as a text-mode
single run would. `Input` for each individual output gets:
```python
Input(mode="batch_dataset", text=combined_text, dataset_group=group, dataset_input=input_id,
      selected_files=files, batch_group_id=batch_group_id)
```
(extends the Sub-project 1 `Input` model with four new optional fields — additive, no version bump
needed per the established "Input is not versioned" rule).

Each saved output also stores `dataset_group` and `batch_group_id` as top-level metadata alongside the
output payload. The group value is metadata about the source/result; the backend does not interpret
raw input bytes for this purpose.

**No GCS-stored combined PDF for batch runs.** Manual uploads store a combined PDF of the original
input in GCS so it can be re-downloaded later. Batch runs skip this — the source files already live
permanently in `preset-data/` in the repo, so there's nothing additional worth duplicating into GCS.
Flagged as a deliberate scope reduction, not an oversight.

**SSE shape for the batch endpoint.** Streams progress per input, then a final batch result:
```
{ "step": "batch_progress", "input": "input-1", "index": 1, "total": 10, "status": "active" }
...(the same per-step events the single-run pipeline already emits, nested under this input)...
{ "step": "batch_progress", "input": "input-1", "index": 1, "total": 10, "status": "done" }
... (repeat per input) ...
{ "step": "batch_result", "data": { "batch_group_ids": { "DocConv": "DocConv-20260616153012" }, "outputs": [ <SimplifyOutput>, ... ] } }
```
Each individual `SimplifyOutput` in `outputs` is also saved to Firestore individually (so Sub-project
5's history view, and the existing single-output Sidebar/CRUD endpoints, work unchanged on each one) —
batching is purely an input/orchestration concern, not a new storage concept.

## 5. API Change Summary

```
GET  /simplify/datasets                              (new)
GET  /simplify/datasets/<group>/<input_id>/<filename> (new)
POST /simplify/batch                                  (new, SSE)
```
Plus the internal-only refactor described above (no URL changes to existing single-run endpoints).

## 6. Frontend Change Summary

- **Replaces the existing preset-data modal entirely** with an inline, collapsed-by-default "Preset
  Data" card below the upload-data card, per your "not a dialog box" instruction.
- New component tree: `PresetDataCard` → `DatasetGroupRow` (checkbox + name + expand toggle) →
  (when expanded) `InputsList` (checkboxes, "select all" synced with the group-level checkbox,
  indeterminate state when partially selected) + `FilesList` (checkboxes + a "View" button per file
  that opens a small preview showing that file's content from the first selected input, falling back
  to the first input overall if none are selected yet).
- Submitting from the upload screen: if any preset-data selections exist, the submit action posts to
  `/simplify/batch` with the `selections` array instead of a single file/text payload; otherwise
  behaves exactly as today. Both paths use the same Configuration card (version + grading toggle from
  Sub-projects 2/3).
- Progress UI: extend the existing SSE-progress display to also show "Input 3 of 10" batch-level
  progress when running a batch, layered on top of the existing per-step progress labels.

## 7. Testing

- `list_datasets()` / `read_dataset_file()` unit tests, including an explicit path-traversal attempt
  (`filename="../../../etc/passwd"`, `group="../"`, etc.) asserting 404/rejection.
- Route test: `POST /simplify/batch` with a 2-input, single-group selection asserts 2 saved outputs
  created, both sharing the same `batch_group_id`, runs in input-sorted order (assert via a stub/mock
  pipeline that records call order, rather than real LLM calls in tests).
- Route test: multi-group selection produces one group-scoped `batch_group_id` per selected group.
- Frontend manual run: build a small local test dataset under `preset-data/` (e.g. 3 folders each with
  a `transcript.txt`+`notes.txt`), confirm the card lists it, selection/view/run all work end-to-end.

## 8. Manual Intervention Required From You

- **Post-deploy spot check:** the metadata interpretation has been checked and works now. A
  post-deploy spot check is sufficient.
- **Add real test data** under `preset-data/` before this can be manually verified end-to-end — the
  repo currently only has an empty placeholder (`preset-data/example/sample-note/.gitkeep`, no actual
  files). A dev agent can build synthetic fixtures for automated tests, but verifying the real UX
  needs at least one populated dataset, which only you can add (or explicitly say synthetic test data
  in the repo is fine to leave in place for this purpose).
- **Mid-build check-in recommended** (not strictly blocking, but this is the largest, most novel
  sub-project) — review the extracted `run_v1_2_pipeline()` function (§4 "Required refactor") once
  it's done and before batch logic is layered on top, to confirm the single-upload behavior is
  unchanged before more code builds on top of it.
