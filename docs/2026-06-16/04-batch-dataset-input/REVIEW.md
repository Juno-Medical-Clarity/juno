# Code Review — 04-batch-dataset-input

Branch: `feature/structured-output-grading-batch-input`
Reviewer: automated production-readiness review (review-only, no code modified)
Tests: full backend suite **116 passed** (18 subtests); sub-project suite **13 passed**. Frontend: **0 tests** for any batch/dataset code.

---

## Summary verdict — Quality score: 4 / 5

This is a well-executed implementation of the largest sub-project. The PRD/TASKS are followed closely and faithfully: the executor extraction (`run_v1_pipeline` / `run_v1_1_pipeline` / `run_v1_2_pipeline`) is clean and behavior-neutral (verified — all pre-existing tests still pass unchanged), the path-traversal defense is genuinely solid and layered, auth is enforced on all three routes, the SSE envelope matches the spec, group-scoped `batch_group_id`s are correct, and backend test coverage of the happy path + ordering + multi-group + traversal is strong. The standout weaknesses are all on the **batch resilience and resource-limiting** axis — exactly where batch processing tends to fail in production: a single bad input aborts the entire batch (orphaning already-saved outputs), there is **no cap on batch size or per-file size** (DoS / runaway-cost vector), and there is **no per-input/per-batch metrics or progress logging** in the batch route itself. None of these are correctness-against-spec failures (the PRD under-specifies them), but they are real production gaps. The frontend has zero automated tests. Fixing the partial-failure handling and adding batch/size caps would move this to a 5.

---

## Correctness vs PRD / TASKS

Implemented and matches spec:

- **Task 1–2 (executor extraction):** `run_v1_2_pipeline(text, metrics, grading_enabled)` and v1/v1-1 equivalents exist, do their own SSE yields, end with `{"step":"result","data":...}`, and do **not** save (`simplify_v1_2.py:323`, `simplify.py:90`, `simplify_v1_1.py:156`). `_generate_stream` is now a thin wrapper. Behavior-neutrality verified by the full existing suite passing + `test_simplify_pipeline_executors.py`.
- **Task 3 (`preset_data.py`):** `list_datasets()` and `read_dataset_file()` match the PRD sketch, including the internal `_input_files(group, input_id)` helper that checks files in the **specific requested input** (not just the first), exactly as the TASKS note required. Handles missing root (`list_datasets` returns `[]`).
- **Task 4 (dataset routes):** Both GET routes present, auth-gated, 404 on miss, correct response shape, reuse `_extract_text_from_bytes` (no duplication).
- **Task 5 (`Input` model):** Four optional fields added, `from_batch_dataset()` helper present, `from_dict` round-trips them.
- **Task 6 (`POST /simplify/batch`):** All 6 sub-steps present. `"inputs":"all"` re-resolved server-side against a fresh `list_datasets()`. Group-scoped IDs with one timestamp per request. Runs sorted by `(group, input_id)`. Per-input save with `dataset_group`/`batch_group_id` metadata. Final `batch_result` event with the `batch_group_ids` map.
- **Tasks 7–9 (frontend):** types, API client (`listDatasets`/`getDatasetFileContent`/`runBatch`), `PresetDataCard` → `DatasetGroupRow` tree with select-all + indeterminate, Inputs/Files tabs, per-file View preview, and `V1_2Page` batch submission with `batch_progress`/`batch_result` handling and "Input N of M" progress. `PresetDatasetModal.tsx` removed.

Deviations / under-delivered:

- **PRD SSE field name mismatch (Low):** PRD §4 shows nested per-step events; the implementation wraps them as `{"step":"batch_progress", ..., "status":"pipeline", "event": <payload>}`. This is a reasonable, arguably cleaner choice, and the frontend consumes it correctly — but it diverges from the literal PRD example. Worth noting only for spec-fidelity.
- **No GCS combined PDF for batch** — correctly omitted per PRD (`input_pdf_gcs=None`). Good.
- **`preset-data/` still effectively empty** (`example/sample-note/.gitkeep`). Per PRD §8 this is owner-action; end-to-end manual verification cannot have been done. Flagged in PRD, acceptable.

---

## Bugs & Edge Cases

- **[HIGH] Partial batch failure aborts the entire batch and orphans saved outputs.** In `batch.py`, an empty/unreadable input (line 157–159), a pipeline `error` event (182–184), or a missing result (195–197) all `return` immediately from the generator. Any inputs already processed *were already saved to Firestore* (line 201) but are **not** included in any `batch_result` — the client receives only `{"step":"error"}` and `V1_2Page` resets to the upload screen discarding them. Result: silently orphaned outputs in Firestore + a confusing all-or-nothing UX for a 50-input batch that fails on item 49. For batch the expected behavior is per-item error isolation (record the failure, continue, report failures in the final result). This is the single most important issue.
- **[HIGH] No cap on batch size / item count.** `selections` is unbounded and `"inputs":"all"` expands to *every* input in a group with no limit (`_resolve_requested_runs`). A request selecting all inputs across all groups produces N sequential pipeline runs, each making multiple LLM calls. No `MAX_BATCH_RUNS` guard → runaway LLM cost + a single request that can run for many minutes/hours. (See Security/DoS.)
- **[MED] No per-file size limit on dataset reads.** `_combined_text_for_dataset_input` calls `read_dataset_file` → `path.read_bytes()` with no size check, unlike uploads which enforce `MAX_FILE_BYTES`/`MAX_AGGREGATE_FILE_BYTES`. A large file in `preset-data/` (or many files) loads fully into memory and into one LLM call. Lower risk because the source is repo-controlled, but it is an inconsistency and an unbounded-memory path.
- **[MED] Long-running stream has no heartbeat / timeout.** A large sequential batch can exceed proxy/load-balancer idle timeouts between the per-input `active` and the next event during a slow LLM step. Headers set `X-Accel-Buffering: no` (good) but there is no periodic keep-alive. The single-run path is short; batch is not.
- **[LOW] `files` selection not validated against the specific input's files.** `_resolve_requested_runs` validates `group` and `input_id` exist, but accepts any `files` list; existence per-file is only enforced later inside `read_dataset_file` (which raises `FileNotFoundError` → aborts the whole batch, see HIGH above). A typo in one filename kills the batch rather than producing a clear up-front 400-style rejection.
- **[LOW] Shared `session_id` across all runs in a batch.** Every per-input `Metrics.start(session_id=getattr(g,"session_id",user_id), ...)` uses the same session id (`batch.py:162`). Fine if intended (one session = one batch), but per-input metrics are not individually correlatable. Document the intent.
- **[LOW] `_output_name` swallows all exceptions** (`except Exception: pass`) and falls back to `"{group} {input_id}"` — acceptable, but masks malformed-output cases silently.
- **[LOW] `run_v{n}_pipeline` hardcodes `input=Input.from_text(text)` inside the `SimplifyOutput`**, then the batch route overwrites `result_data["input"]` post-hoc (line 199). Works, but the `SimplifyOutput.input` and the serialized `result_data["input"]` momentarily disagree; brittle if anyone later reads `output.input` instead of the dict.

---

## Test Coverage Gaps (concrete)

Backend (good baseline, but missing):

- **Partial-failure behavior** — no test asserts what happens when input #2 of 3 fails (empty text, pipeline `error`, or `result_data is None`). This is the highest-value missing test given the HIGH bug above.
- **Empty group / group with zero inputs** — `_resolve_requested_runs` raises `"has no inputs"`; untested.
- **Malformed selection bodies** — non-dict selection, missing `files`, empty `files`, `inputs` neither `"all"` nor a list, empty `selections`, non-JSON body. The route handles these; only `MissingGroup` is tested.
- **Unknown input id** (`unknown_inputs` → `FileNotFoundError`) — untested.
- **Large/many-input batch** — no test exercising more than 3 runs or asserting ordering across many groups.
- **Per-file size / large file** — N/A today (no limit exists); add once a limit is added.
- **`read_dataset_file` on a `.pdf`/`.docx`** path (extraction) — preset_data tests only use `.txt`.
- **Dataset preview of non-txt** and **unsupported extension** (route returns 500 from `_extract_text_from_bytes` `ValueError`, not 404 — untested edge).

Frontend (**zero tests** — biggest gap by volume):

- `toBatchSelections` collapse-to-`'all'` logic, partial selection, file-filtering against `dataset.files`.
- `DatasetGroupRow` indeterminate/select-all toggle, input/file toggling, preview fetch + error.
- `V1_2Page` SSE parsing: `batch_progress` step reset on input change, `batch_result` population, error → reset, abort handling.

---

## Security

Overall: **strong** on the two areas the PRD flagged as hard requirements (path traversal, auth). Weak on DoS/resource limits.

- **Path traversal — well defended (PASS).** Three layers: (1) route uses `<string:filename>` (commit `eaee099` changed it from `<path:filename>` — important fix; `path:` would have allowed slashes/traversal in the filename segment); `<group>`/`<input_id>` are default string converters that also reject slashes. (2) `read_dataset_file` validates all three segments against the **enumerated** `list_datasets()` / `_input_files()` listing before touching disk. (3) Final `path.resolve()` + `is_relative_to(PRESET_DATA_ROOT.resolve())` check. Traversal attempts are tested at both the unit (`test_preset_data.py`) and HTTP (`test_dataset_routes.py`, including `%2F`-encoded) layers, and error messages do not disclose filesystem paths (asserted). This meets PRD §4's security requirement.
- **Auth — PASS.** All three routes carry `@verify_firebase_token`; 401 tested on batch + both dataset routes.
- **Tenant isolation — N/A / acceptable.** `preset-data/` is shared, repo-controlled, read-only data, not per-tenant; there is no cross-user data to leak via these routes. Saved outputs are written with the caller's `user_id`. OK.
- **[HIGH] DoS / resource exhaustion — FAIL.** No `MAX_BATCH_RUNS`, no `selections` length cap, no per-file/aggregate size cap on dataset reads (uploads have these; batch does not). One authenticated request can trigger an unbounded number of sequential LLM pipeline runs → cost-amplification and a single connection held open for a very long time. Add a hard cap on total runs per request and a per-file/aggregate byte cap, returning an SSE error before execution.
- **SSRF — N/A.** Datasets are local filesystem only; no URL fetching. Good (matches Non-Goals).
- **Injection — low.** Dataset text flows into LLM prompts (prompt-injection surface exists as with all input), but no SQL/shell/path injection given the listing-based validation.
- **PII — note.** Batch outputs are stored in Firestore individually like single runs; the `output_data` `raw` block is stripped by `_without_raw` in `save_simplify_output`. Consistent with existing behavior.

---

## Logging & Metrics

This is the weakest non-bug area. The batch route (`batch.py`) does **no** logging or metrics of its own:

- **No `JunoLogger` / `JunoMetrics` in `batch.py`.** No batch-start log, no per-input start/done log, no failed-item error log, no batch completion log. The only metrics emitted are those inside each `run_v{n}_pipeline` (latency/counter per pipeline run, labeled `input_type="batch_dataset"` thanks to the Metrics passed in — that part is good). But there is **no batch-level metric**: total runs, batch duration, items-failed count, or batch cost. When a batch silently aborts mid-way (the HIGH bug), there is no log to diagnose which item failed or why beyond the SSE error sent to the client.
- **Recommended:** add `JunoLogger(api_version=version)` calls — `log_step("batch", "start", extra={runs, groups})`, per-item start/done/error, and `log_step("batch", "done"/"error", duration_ms=...)`; add a `JunoMetrics` counter for `batch_request` and a gauge/counter for items processed/failed per batch. Per `backend/utils/LOGGING.md` conventions this is expected for a new orchestration route.

---

## Extensibility

- **Executor extraction — clean and reusable (good).** `_pipeline_for_version` cleanly maps version→executor; adding a new version is a one-line addition plus the new `run_v1_x_pipeline`. The signature `(text, metrics, grading_enabled) -> Generator[str,...]` is uniform across versions. This is the architectural win of the sub-project.
- **Adding a new dataset source — moderate coupling.** `batch.py` is hardwired to `preset_data.list_datasets`/`read_dataset_file`. Supporting user-uploaded datasets later (a stated Non-Goal for now) would require threading a different resolver through `_resolve_requested_runs` and `_combined_text_for_dataset_input`. Not a problem today, but the dataset-access functions could be parameterized behind a small interface if that becomes a goal.
- **Code smells in `batch.py`:** the single `generate()` closure is long (~115 lines) and mixes validation, orchestration, SSE framing, saving, and error handling. The per-input loop body (resolve text → metrics/input → consume pipeline → save → emit) is a natural extract into a `_run_single(...)` helper, which would *also* make per-item error isolation (the HIGH fix) straightforward. `_sse`/`_payload_from_sse` are duplicated between `batch.py` and `simplify_v1_2.py` — candidates for a shared `utils/sse.py`.
- **Frontend** component tree is clean and idiomatic; selection state lifting via callback is fine.

---

## Must-fix before production checklist

1. **[HIGH] Isolate per-item failures.** Do not abort the whole batch when one input is empty / errors / returns no result. Record the failure, continue, and include a `failed` list in the final `batch_result`. Extract a `_run_single()` helper to make this clean.
2. **[HIGH] Add resource caps.** Hard limit on total runs per batch request (e.g. `MAX_BATCH_RUNS`) and a per-file + aggregate byte cap in `_combined_text_for_dataset_input`, rejected up front with an SSE error. Closes the DoS / runaway-cost vector.
3. **[HIGH/MED] Add logging & metrics to `batch.py`.** Batch start/done/error logs, per-item logs (esp. failures), and a batch-level metric (count, duration, items failed). Currently zero observability at the batch level.
4. **[MED] Validate selected `files` up front** against the requested input's actual files, returning a clear error before any runs execute (rather than mid-batch `FileNotFoundError`).
5. **[MED] Stream keep-alive / timeout** for long batches (periodic heartbeat event) to survive proxy idle timeouts.
6. **[MED] Add the missing tests** — partial failure, empty/malformed selections, unknown input, non-txt preview, and at least a smoke set of frontend tests for `toBatchSelections` and the `V1_2Page` SSE handlers.
7. **[LOW] Populate `preset-data/`** with at least one real dataset and do the end-to-end manual run per PRD §8 before relying on the UX.
