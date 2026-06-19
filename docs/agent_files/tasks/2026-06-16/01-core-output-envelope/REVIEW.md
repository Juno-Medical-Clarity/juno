# Production-Readiness Review — 01-core-output-envelope

Reviewer: automated deep review (Opus). Branch: `feature/structured-output-grading-batch-input`. Base: `main`.
Tests verified: 116/116 backend pass; frontend `tsc --noEmit` clean.

---

## Summary Verdict — Quality Score: 4 / 5

This is a well-executed foundational refactor. The model layer (`JsonModel` / `VersionedJsonModel` /
`SimplifyOutput` and friends) is clean, dependency-free, well-documented, and genuinely
unit-testable. The registry/versioning design is sound and the recursive `from_dict` works correctly
end-to-end (verified: `SimplifyOutput.from_dict(out.to_dict())` round-trips with correct nested types
including the versioned care plan). Test coverage on the models is strong (58 focused tests). The
envelope is wired into all three routes, the session ID is surfaced, Firestore save ordering is
correct, and metrics/logging follow the documented conventions. It loses a point for a handful of
real correctness inconsistencies between the three route implementations (notably v1/v1-1 always
emit `input.mode="text"` even for file uploads, contradicting `metrics.input_type`), a couple of
robustness gaps in `from_dict` error typing, and some scope-bleed from later sub-projects landing in
"01" files (Grading is no longer a stub; Input carries batch fields) that makes the "01" boundary
fuzzy. None of these are launch-blockers for the happy path, but several should be fixed before
production.

---

## Correctness vs PRD / TASKS

Implemented and matching spec:
- **Task 1** — `JsonModel` / `VersionedJsonModel` with per-class registry via `__init_subclass__`. No
  Flask/Firestore imports. Round-trips correctly. Matches spec.
- **Task 2** — `Metrics` dataclass + `Metrics.start(...)`. Exact field set from PRD §4. Matches.
- **Task 3** — `Input` / `InputFile` metadata-only (the confirmed PRD §8 decision). `from_file_uploads`
  reads length then `seek(0)` to avoid consuming the stream. Matches.
- **Task 4** — `Grading` stub: **diverged.** The file now contains the *real* schema (`GradingEntry`,
  `build_grading`, method-reasoning table) from sub-project 03, not the stub. `Grading().to_dict()` is
  `{"entries": [], "enabled": True, "graded_at": None}`, not the PRD's `{"entries": []}`. This is
  expected because 03 landed on the same branch, but it means the "01" acceptance criterion
  (`Grading().to_dict() == {"entries": []}`) is no longer true. Not a defect per se — just note the
  envelope's grading shape is wider than the 01 PRD describes.
- **Task 5** — `SimplifiedCarePlan` versioned, registered 1.0/1.1/1.2 to one class. Custom `to_dict`
  flattens `{"version", **data}`; custom `from_dict` splits version out. Matches. The decision to
  write the registry directly (instead of `register()`) is correct and well-commented — using the
  decorator would set `_is_registered=True` and bypass the custom `from_dict`.
- **Task 6** — `SimplifyOutput` + `is_legacy_shape`. Exact PRD §5 shape. Matches.
- **Task 7/8** — Envelope wired into v1-2, v1-1, v1. Session ID surfaced. Save ordering fixed (commit
  069758a) so `total_duration_ms` is set before the Firestore write and `saved_id` after. Matches.
- **Task 9** — `test_models.py`, `test_models_base.py`, persistence test updated to nested shape with
  `session_id` assertions. Matches.
- **Task 10/11/12** — `envelope.ts`, `normalizeOutput.ts`, `outputVersion.ts`, version pages unwrap
  `simplified_care_plan`, "Request ID: {session_id}" line added. Matches.

Notable spec deviations (mostly cross-sub-project bleed, flagged for the aggregate report):
- PRD §3 says route URLs are unchanged in this sub-project, but on this branch `/simplify/v1`,
  `/v1-1`, `/v1-2` now 404 and a single `/simplify` dispatcher exists — that is sub-project 02's
  collapse, landed early. Not an 01 defect.
- `Input` gained `dataset_group`/`dataset_input`/`selected_files`/`batch_group_id` (sub-project 04).
  Out of 01 scope but lands in an 01 file.

---

## Bugs & Edge Cases

### HIGH
- **v1 and v1-1 always report `input.mode="text"` even for file/doc_id inputs.** In `simplify.py`
  (line 199) and `simplify_v1_1.py` (line 284) the envelope is built with `input=Input.from_text(text)`
  unconditionally, while `Metrics.start(... input_type="file")` (simplify.py line 267) records the
  *real* kind. Result: for a v1 file upload, `metrics.input_type == "file"` but `input.mode == "text"`,
  the full extracted text is stored under `input.text`, and file metadata
  (filename/content_type/size) is silently dropped. v1-2 does this correctly via
  `_input_model_from_resolved`. This is an internal inconsistency that will mislead any consumer of
  `input`, and for v1-1 (which *does* persist to Firestore via the shared save path) it also bloats
  the stored `input.text` with the entire document. Severity HIGH for v1-1 (persisted, inconsistent),
  MEDIUM for v1 (in-memory only).

### MEDIUM
- **`SimplifiedCarePlan.from_dict` raises bare `KeyError` for an unknown but well-formed version.**
  `registered_cls = cls._registry[version]` (care_plan.py line 72) throws `KeyError` with no message
  listing available versions — inconsistent with the base `VersionedJsonModel.from_dict`, which raises
  a descriptive `ValueError`. A test (`test_unknown_version_raises`) actually asserts `KeyError`, so
  the rough behavior is locked in. If any code path ever deserializes a future/legacy stored care plan
  with an unregistered version, it gets an opaque `KeyError` instead of a clear error. Severity MEDIUM.
- **Base `from_dict` raises `TypeError` on unknown keys.** `cls(**reconstructed_data)` (base.py line
  72) means deserializing any dict with an extra key (e.g. an older/newer Firestore document with a
  field the dataclass doesn't know) throws `TypeError: __init__() got an unexpected keyword argument`.
  In production the saved-output read path returns the raw stored dict (no `from_dict`), so this is not
  currently hit — but it is a latent forward-compat landmine the moment anyone calls
  `SimplifyOutput.from_dict()` / `Metrics.from_dict()` on stored data. Models should ignore/whitelist
  unknown keys for true additive forward-compat. Severity MEDIUM (latent).

### LOW
- **v1-1 loses step durations on a late-step failure.** Unlike v1-2 (which writes
  `metrics.step_durations_ms[name]` immediately after each step), v1-1 accumulates durations into
  local vars and only copies them onto `metrics` in a single block at the end of the success path
  (lines 270–276). If `structure_note` fails (early `return` at line 238) no step durations are ever
  written to `metrics`. Since the error path doesn't emit an envelope, user impact is nil, but it's an
  inconsistency that will surprise the next maintainer. Severity LOW.
- **Frontend `normalizeSimplifyOutput` legacy branch returns `grading: { entries: [] }`** missing the
  `enabled` and `graded_at` fields required by the `Grading` TS interface (normalizeOutput.ts line 30).
  `tsc` doesn't catch it because the surrounding object is widened by the `any` spread of `rest`.
  No current consumer reads `grading.enabled` on a normalized legacy output, so benign today, but a
  latent `undefined` for any future consumer. Severity LOW.
- **Legacy `metrics.pipeline_version` is hard-coded to `'v1'`** in the legacy normalize branch. All
  pre-envelope documents will display/route as v1 even if they were produced by v1-1/v1-2. Acceptable
  per PRD ("legacy documents don't carry pipeline version info") but worth a one-line UI note so a
  support engineer isn't misled by the Request-ID/version line. Severity LOW.
- **`getattr(g, "session_id", user_id)` fallback in v1-2** (line 491) substitutes the *user_id* as the
  session_id if `g.session_id` is somehow unset, whereas v1 falls back to `""` (line 265). Minor
  inconsistency; using a user_id as a session_id could subtly leak/confuse identifiers in logs. Severity LOW.

---

## Test Coverage Gaps (concrete)

Backend model tests are strong. Missing cases worth adding:

1. **`SimplifyOutput.from_dict` round-trip test.** There is *no* test that calls the (base, recursive)
   `SimplifyOutput.from_dict` on `to_dict()` output. It works (verified manually) but is entirely
   untested, including the nested `SimplifiedCarePlan` version-dispatch through the recursive path.
2. **`SimplifiedCarePlan.from_dict` unknown-version error *type/message*.** Existing test asserts
   `KeyError` but does not assert any message or compare to the base-class behavior — add a test that
   pins the intended contract (and ideally fix it to a descriptive `ValueError`).
3. **Base `from_dict` with unknown/extra keys.** No test documents the current `TypeError` behavior.
   Add one to pin the contract (then decide whether to make it lenient).
4. **v1 / v1-1 input-model correctness.** No test asserts what `input` looks like for a *file* upload
   through v1 or v1-1 — which is exactly where the HIGH bug lives. Add a route test asserting
   `input.mode`/`input.files` for a v1-1 file upload (it would currently fail to be "file").
5. **`Input.from_file_uploads` with `filename=None` / `content_type=None`.** Code coalesces to `""`;
   no test covers the None case.
6. **Frontend: no test for `normalizeSimplifyOutput` at all.** TASKS Task 11 acceptance criteria
   explicitly call for "given a legacy flat fixture and a new-envelope fixture, both produce a
   SimplifyOutput-shaped object." This test does not exist (the only frontend test file is
   `groupSavedOutputs.test.ts`). Add: (a) legacy flat → normalized shape, (b) new envelope →
   pass-through, (c) `null`/`undefined` → throws (the guard added in commit 437a4dd is untested).
7. **`outputVersion.ts` (`outputRouteVersionId`) untested** — the version-to-route mapping table,
   including the fallback to `simplified_care_plan.version` and the final `'v1'` default.
8. **Save path: assert persisted `output_data` shape.** Persistence test asserts SSE shape but does not
   assert the *saved* `output_data` kwarg is the nested envelope (with `metrics` minus `saved_id`).
   Add `save_simplify_output.call_args.kwargs["output_data"]` structural assertions.

---

## Security

- **No new auth gaps.** All three routes remain behind `@verify_firebase_token`; the dispatcher
  validates `version` against `ALLOWED_VERSIONS` and now correctly rejects non-string/list/empty
  versions (commit 5b8ff6d, with tests). Good.
- **`from_dict` deserializes attacker-influenceable data?** Not in this sub-project's production paths.
  The only untrusted input deserialized is the request body for version selection (validated) and
  Firestore docs (returned raw, not `from_dict`-ed). If a future change pipes stored docs through
  `SimplifyOutput.from_dict`, the `TypeError`-on-unknown-key behavior becomes a mild DoS/robustness
  concern (a single malformed doc 500s the read). Worth hardening proactively.
- **PII in logs.** `juno_logger.log_step("read_input", ...)` logs `input_chars` (a count, fine) but the
  envelope itself now carries `input.text` (full document text) and `simplified_care_plan.raw.text`.
  These are persisted to Firestore (expected) and sent in the SSE body, but are **not** logged — good.
  Confirm no future logging of the envelope dict at INFO, which would dump PHI into Cloud Logging.
- **`session_id` exposure.** Surfacing `metrics.session_id` to the frontend is intentional (PRD goal)
  and the value is a server-generated request ID, not a secret. Fine. Minor: the v1-2 fallback of
  using `user_id` as `session_id` (see LOW bug) would expose a Firebase UID in the response body and
  the "Request ID" UI line — undesirable; the v1 `""` fallback is safer.
- **No injection vectors** introduced — all model construction is keyword-arg dataclass assembly; no
  eval/format-string/SQL.

---

## Logging & Metrics

- Metrics wiring follows `LOGGING.md` conventions well: `JunoMetrics.record_latency` /
  `record_counter` / `record_error` are called with `{"version", "input_type"}` labels, and
  `juno_logger.log_step(name, "start"|"done"|"error", duration_ms=...)` brackets each step. v1-2 also
  mirrors each `duration_ms` into `metrics.step_durations_ms` immediately (the cleanest pattern).
- **Gap (LOW, pre-existing):** `juno_logger.log_request_start` / `log_request_end` exist and emit the
  `step_name="request_end"` + `total_duration_ms` entry that several `LOGGING.md` Cloud Logging queries
  ("Slow requests over 10 s") and the dashboard depend on — but **no simplify route calls them**
  (confirmed absent in `main` too, so not an 01 regression). `total_duration_ms` lives only on the
  body `Metrics`, not in logs. This sub-project was the natural place to wire `log_request_end` given
  it already computes `total_duration_ms`; recommend doing so.
- **Inconsistency (LOW):** v1 (`simplify.py`) does *not* call `juno_metrics.record_latency/counter`
  for the pipeline the way v1-1/v1-2 do (it only populates the body Metrics). So v1 runs won't appear
  in the `simplify_request` / latency metrics. Likely acceptable (v1 is legacy/in-memory) but
  undocumented.
- Error paths are logged via `juno_logger.exception(...)` + `record_error(...)` at every step in
  v1-1/v1-2. Good. v1's per-step error handling is lighter (fewer `record_error` calls) — minor.

---

## Extensibility

- **Adding a new care-plan version** is genuinely easy: register the version in the
  `SimplifiedCarePlan._registry` loop and pass it to `from_pipeline_result`. The "same class, many
  versions" pattern is appropriate while parsing is identical; the `from_dict` already looks up
  `registered_cls` so a future divergent V1.3 class can be slotted in without touching callers.
- **Adding a new envelope section** (like the future real Grading) is a one-line dataclass field +
  one line in `SimplifyOutput.to_dict()` — proven by how cleanly the real Grading slotted in.
- **Registry isolation** via `__init_subclass__` is correct and tested (sibling registries are
  distinct). Good defensive design.
- **Code smell — three near-duplicate route generators.** `run_v1_pipeline` / `run_v1_1_pipeline` /
  `run_v1_2_pipeline` share ~80% of their metrics/step/envelope boilerplate but drift (the v1/v1-1
  `Input.from_text` bug, the v1-1 deferred-durations pattern, v1's missing pipeline metrics). This
  duplication is the root cause of two of the bugs above. A shared `_emit_result(metrics, input_model,
  grading, care_plan)` helper and a shared per-step timing context manager would remove the drift.
  Sub-project 02 collapses the *routes*; consider also collapsing the *pipeline-runner* boilerplate.
- **Import-root fragility (LOW).** Model code imports `backend.models.*` (absolute from repo root)
  while route/util code imports `utils.*` (relative to `backend/`). Tests only pass when pytest is run
  from the **repo root**, not from `backend/` (running from `backend/` gives
  `ModuleNotFoundError: No module named 'backend'`). There is no `conftest.py` pinning the path. This
  dual convention is a maintenance/CI hazard — pin it with a root `conftest.py` or consistent import
  style.

---

## Must-Fix Before Production

1. **[HIGH]** Fix v1 and v1-1 to build the real `Input` model (file/doc_id/text) instead of
   unconditional `Input.from_text(text)`, so `input.mode` matches `metrics.input_type` and file
   metadata is captured (v1-1 persists this, so it's also storing whole documents in `input.text`).
2. **[MEDIUM]** Make `SimplifiedCarePlan.from_dict` raise a descriptive `ValueError` (with available
   versions) instead of a bare `KeyError` for unregistered versions; align with the base class and
   update the test.
3. **[MEDIUM]** Decide and enforce forward-compat behavior for `from_dict` on dicts with unknown keys
   (currently `TypeError`). Either filter unknown keys or document/guard it before any code path
   deserializes stored Firestore documents through the models.
4. **[LOW→MEDIUM]** Add the missing frontend `normalizeSimplifyOutput` tests (legacy, new, null) — this
   is an explicit TASKS Task 11 acceptance criterion that was not met.
5. **[LOW]** Add a v1-1 file-upload route test asserting the persisted `input` shape (guards bug #1).
6. **[LOW]** Wire `juno_logger.log_request_end(..., duration_ms=total_ms)` in the routes so
   `total_duration_ms` reaches Cloud Logging and the documented dashboards/queries work.
7. **[LOW]** Backfill `enabled`/`graded_at` in the legacy `grading` object in `normalizeOutput.ts` for
   type completeness; replace the v1-2 `session_id` fallback-to-`user_id` with `""`.
8. **[LOW]** Add a root `conftest.py` (or normalize import style) so the suite runs from any directory
   and CI can't accidentally collect against the wrong root.
