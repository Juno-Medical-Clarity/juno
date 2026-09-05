# PRD: SP6 — Trial Pipeline Optimizations

**Sub-project:** SP6
**Branch context:** users/tejitpabari/trial-optimizations
**Date:** 2026-09-05
**Status:** Draft
**Dependencies:** None (SP1–SP5 are already implemented on `main`; this PRD only touches
shared backend code SP2's trial route and SP2/SP5's retention work already rely on)

---

## 1. Problem

`optimization-findings-2026-09-05.md` (read-only investigation, branch `main`, HEAD
`ad5a1550`, no code changed) audited the trial request lifecycle (`POST /trial/jobs` →
Cloud Tasks → `/internal/jobs/execute/<job_id>` → v1.2 pipeline → grading → Firestore →
`frontend-trial` snapshot/render) now that the trial UI has been stripped down (no
Readability section, no Other Items/`low_priority`, glossary + `combined` score kept)
and produced an 8-item ranked table of possible optimizations. Three of those items are
high-confidence, low-risk, and independently valuable enough to implement now:

1. **The trial stores 12 grading entries the frontend never reads.**
   `build_grading_with_before_after_score` (`backend/models/grading.py:28-68`) always
   computes and emits all 6 non-`combined` readability methods (SMOG, Flesch-Kincaid,
   Dale-Chall, PEMAT, SAM, CDC_CCI) × before/after, plus 2 `combined` entries — 14
   entries total, written verbatim into `output_data["grading"]["entries"]` by
   `worker.py:207`'s `envelope.to_dict()`. `frontend-trial/`'s `ResultScreen.tsx` reads
   only the 2 `combined` entries (`entries.filter(e => e.name === 'combined')`);
   `CarePlanView` accepts a `grading` prop but never reads it, and `downloadReport.ts`
   passes `includeReadability: false` so `buildPdfHtml` never touches `grading.entries`
   either. Measured against a real captured pipeline output
   (`frontend-trial/src/tests/fixtures/realCarePlanOutput.fixture.json`), the 12 unused
   entries are **3,286 of 8,565 bytes (38%) of the whole `output_data` payload** — the
   single largest optimization opportunity found, and a **payload**, not a latency, win
   (it shrinks the final Firestore write and the realtime snapshot pushed to the
   client).
2. **`Metrics.total_duration_ms` (`backend/models/metrics.py:19`) is never populated
   anywhere in production code.** It defaults to `None` and stays `None` through the
   entire job lifecycle — no pipeline stage, `worker.py`, or `envelope.py` ever assigns
   it. `frontend-trial/src/screens/ResultScreen.tsx:44` reads
   `outputData.metrics?.total_duration_ms ?? 0` and reports it as the `total_duration_ms`
   parameter on the `simplify_complete` GA4 event — so this analytics field is, as
   shipped, **always `0`**. This is a correctness gap, not a performance regression, but
   it directly blocks measuring the actual effect of item 3 below (and every other
   latency claim in the findings doc) since there is currently no per-job timing data at
   all.
3. **The CPU-only `before`-grading score runs serially after all three sequential Gemini
   Pro calls, even though it depends only on the original input text.**
   `services/care_plan_pipeline.py:93-96` computes `before_score =
   score_text_safe(text, "before")` only once `pipeline.iter_steps(...)` yields its
   final `PipelineRunResult` — i.e., after `find_medical_terms`, `simplify_language`,
   `clarify_and_action`, and `structure_appointment_note` have all already run. But
   `text` (the function's own first argument) is available before the pipeline even
   starts. Submitting `score_text_safe(text, "before")` to a background thread at the
   top of `run_care_plan_pipeline` and joining it just before grading is built hides its
   CPU cost (textstat + an optional scispaCy pass, up to ~tens–hundreds of ms on a long
   document) behind the Vertex AI network wait of the three sequential LLM calls — a
   pure reordering, identical result, for every caller (trial and main app both).

SP6 implements exactly these three items, in the order **(1) grading trim → (2) metrics
wiring → (3) concurrent before-score)** so that item 2 lands and is available to measure
item 3's effect before item 3 changes any timing-sensitive code path.

---

## 2. Goals

1. Trial jobs' `output_data["grading"]["entries"]` contains only the 2 `combined`
   entries (before/after); non-trial jobs are provably byte-for-byte unaffected.
2. `Metrics.total_duration_ms` is populated with a real millisecond duration on every
   job (trial and main app), wired from timing instrumentation that already exists in
   `worker.py`.
3. The `before`-grading score computation overlaps the three sequential LLM calls
   instead of following them, with identical output and telemetry for every caller —
   behavior-preserving, no flag, no output change.

---

## 3. Non-Goals

- **No change to what gets *computed*, only what gets *stored/timed/ordered*.** Task 1
  is a storage-side filter, not a computation-side skip (that's ranked rec #4, deferred
  — see §4.4). Task 3 reorders when `before_score` is computed; it does not change what
  is computed or skip computing it for anyone.
- **No `low_priority` schema/prompt change** (ranked rec #5) — deferred, see §4.4.
- **No change to where OCR/text-extraction runs** (ranked rec #6) — deferred, see §4.4.
- **No frontend changes anywhere** (`frontend/` or `frontend-trial/`). All three tasks
  are backend-only; `frontend-trial/`'s `ResultScreen.tsx` already reads only the
  `combined` entries and already reads (a today-always-zero) `total_duration_ms` — both
  already do the right thing once the backend catches up.
- **No new Cloud Tasks queues, Cloud Run flags, Firestore collections, or deploy changes.**
  This PRD touches exactly three existing backend files' internals
  (`routes/worker.py`, `models/metrics.py`'s existing field is populated not changed,
  `services/care_plan_pipeline.py`).
- **No threading/concurrency library beyond the standard library's
  `concurrent.futures.ThreadPoolExecutor`** — no new dependency.

---

## 4. Architecture Decisions

### 4.1 Task 1 — Trim trial grading entries in `worker.py` (ranked rec #1)

**Where:** `backend/routes/worker.py`'s existing `is_trial` post-processing block,
immediately after the pipeline result has been serialized to `output_data` and before
`complete_job` is called (currently lines 218–227):

```python
# current
if getattr(job, "is_trial", False):
    output_data.get("care_plan", {}).pop("raw", None)
    output_data.get("input", {}).pop("text", None)
```

**Implementation — post-processing filter, not a threaded flag.** The findings doc
(Finding 1) explicitly evaluated two implementations and recommends the lower-risk one:
a pure post-processing filter in `worker.py`, in the exact same place the existing
`raw`/`input.text` trim already lives, requiring **zero** changes to
`models/grading.py` or `services/care_plan_pipeline.py` (both shared verbatim with the
main app's `/care_plan/jobs` grading UI). The rejected alternative — gating the
`for method in Constants.Grading.GRADING_METHODS` loop inside
`build_grading_with_before_after_score` behind an `is_trial`/`include_method_entries`
flag threaded from `worker.py` down through `run_care_plan_pipeline` — is Finding 4's
**separate**, deferred item (§4.4): it changes *what's computed*, carries real
shared-code risk, and is not worth it for a ~tens-of-ms CPU saving when Finding 1's
~3.3KB payload win is available at near-zero risk via the filter alone.

**New code:**
```python
if getattr(job, "is_trial", False):
    output_data.get("care_plan", {}).pop("raw", None)
    output_data.get("input", {}).pop("text", None)

    # Trial UI (ResultScreen.tsx) reads only the two `combined` grading entries
    # (before/after) — the other 12 non-`combined` method entries are computed
    # (grading is shared with the main app's per-method breakdown UI) but never
    # rendered anywhere in frontend-trial/. Dropping them here, storage-side only,
    # cuts ~38% off output_data (optimization-findings-2026-09-05.md, Finding 1).
    grading = output_data.get("grading")
    if isinstance(grading, dict):
        entries = grading.get("entries")
        if isinstance(entries, list):
            grading["entries"] = [
                e for e in entries
                if isinstance(e, dict) and e.get("name") == "combined"
            ]
```

**Defensiveness required:** `output_data.get("grading")` may be absent, `None`, or (in a
future schema change) something other than a dict; `entries` may be absent, `None`, or
not a list; individual entries could in principle be non-dict. Every one of these must
be a silent no-op, never a `KeyError`/`TypeError`/`AttributeError` — this filter runs
inside `worker.py`'s job-completion path and must never turn a successful job into a
failed one. Note this is a stricter defensiveness bar than the existing `raw`/
`input.text` lines above it (which rely on `.get(..., {})` returning a dict because
`care_plan`/`input` are always dicts by construction) — grading's `entries` list shape
is being filtered element-by-element, so each element's type is checked too.

**Blast radius:** only inside the `if getattr(job, "is_trial", False):` block — a
non-trial job's `output_data` takes the exact same path through `envelope.to_dict()` it
always has, untouched by this change. `models/grading.py`, `services/
care_plan_pipeline.py`, and `routes/grading.py` (the main app's dedicated grading
route/UI) are not modified.

### 4.2 Task 2 — Populate `Metrics.total_duration_ms` in `worker.py` (ranked rec #3)

**Must land before Task 3** so Task 3's effect (and every other latency claim in the
findings doc) is measurable going forward — there is currently zero per-job timing data
anywhere in this codebase to validate any performance change against.

**Where:** `backend/routes/worker.py:88` already starts a monotonic timer for the
existing timeout check:
```python
start = time.monotonic()
```
This is the same timer this task reads back out — no new instrumentation is added, only
a read of an existing value that was previously computed and discarded.

**Change:** immediately before `envelope = CarePlanInternal(...)` is constructed
(currently line 201 — i.e., right after `care_plan`/`grading` are extracted from
`pipeline_result` and before they're serialized), stamp the metrics object:
```python
metrics.total_duration_ms = (time.monotonic() - start) * 1000.0
```
`metrics` is the same `Metrics` instance already passed into `pipeline_fn(...)` and later
into `CarePlanInternal(metrics=metrics, ...)` — mutating it in place before
`envelope.to_dict()` is called (line 207) is sufficient; no change to `models/metrics.py`
or `models/care_plan/envelope.py` is needed since `total_duration_ms` is already a
declared field, just never assigned.

**Scope of the measured duration:** from the timeout-check timer's start (right after
the job is marked `processing`, before pipeline dispatch) through pipeline completion
(right after grading is built) — i.e., effectively "pipeline wall-clock time," not
including the initial Firestore `processing` status write before the timer starts or the
final `complete_job` write after. This is the same window `_check_timeout` already
measures against `Constants.Deadlines.*_INTERNAL_DEADLINE_S`, so it's a natural,
already-meaningful number, not an arbitrary new definition.

**Purely additive, benefits main app too:** every job (trial or not) gets a real
`total_duration_ms` from this change — this is not gated on `is_trial` and needs no flag.
The main app currently has no UI reading this field, so there is no behavior change for
main-app users beyond a previously-`None` field now holding a real float.

### 4.3 Task 3 — Compute `before`-grading score concurrently (ranked rec #2)

**Where:** `backend/services/care_plan_pipeline.py`, `run_care_plan_pipeline` (currently
lines 35–132). The relevant excerpt today:
```python
def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[...]:
    try:
        try:
            pipeline = CarePlanV1_2Pipeline()
        except Exception as e:
            yield AdapterError(error_data=build_error_data_from_exc(e))
            return
        ...
        for event in pipeline.iter_steps(text, wrap_step=wrap_step):
            ...
            elif isinstance(event, PipelineRunResult):
                if grading_enabled:
                    before_score = score_text_safe(text, "before")
                    after_score  = score_text_safe(event.clarified, "after")
                    ...
    except Exception as exc:
        ...
        yield AdapterError(error_data=build_error_data_from_exc(exc))
```

**Change:** submit `score_text_safe(text, "before")` to a
`concurrent.futures.ThreadPoolExecutor` at the very top of the function (`text` and
`grading_enabled` are both already available as the function's own parameters — nothing
about the pipeline needs to have run yet), and join it (`.result()`) right where
`before_score` is currently computed, just before `build_grading_with_before_after_score`
is called:

```python
from concurrent.futures import ThreadPoolExecutor

def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[...]:
    # Kick off the CPU-only "before" grading score immediately: it depends only on
    # `text` (already available, before the pipeline's first LLM call even starts),
    # not on any pipeline step's output — so it can run concurrently with the three
    # sequential Vertex AI calls below instead of serially after all of them
    # (optimization-findings-2026-09-05.md, Finding 3 there / rec #2 in this PRD).
    executor = ThreadPoolExecutor(max_workers=1) if grading_enabled else None
    before_score_future = executor.submit(score_text_safe, text, "before") if executor else None
    try:
        try:
            pipeline = CarePlanV1_2Pipeline()
        except Exception as e:
            yield AdapterError(error_data=build_error_data_from_exc(e))
            return
        ...
        for event in pipeline.iter_steps(text, wrap_step=wrap_step):
            ...
            elif isinstance(event, PipelineRunResult):
                if grading_enabled:
                    before_score = before_score_future.result()
                    after_score  = score_text_safe(event.clarified, "after")
                    ...
    except Exception as exc:
        ...
        yield AdapterError(error_data=build_error_data_from_exc(exc))
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
```

**Why this is behavior-preserving, not just "usually fine":**
- `score_text_safe` (`backend/utils/scoring.py:307-313`) already wraps `score_text` in a
  bare `try/except Exception`, logs, and returns `None` on any failure — it **never
  raises**. Calling it via `executor.submit(...)` and later `.result()` does not
  introduce any new exception path across the thread boundary: `.result()` re-raises
  only if the submitted callable raised, and `score_text_safe` structurally cannot raise.
  This is the one risk the findings doc calls out explicitly (Finding 3's "Risk" section)
  and it is resolved by `score_text_safe`'s existing design, not by new code.
- The value returned is identical to today's synchronous call — same function, same
  arguments (`text`, `"before"`), same return type — only *when* it starts differs.
- `executor.shutdown(wait=True)` in a `finally` block guarantees the background thread
  has finished (or been allowed to finish) before `run_care_plan_pipeline` returns on
  **every** exit path: the happy path, the `PipelineStepError` early return, the
  pipeline-constructor-failure early return, and the outer `except Exception` handler.
  This avoids a leaked/dangling thread on any failure path, even though on most failure
  paths `before_score_future.result()` is never actually read.
- `Markers.Grading.Run`'s span attributes (`scope.add("before_composite", (before_score
  or {}).get("composite", 0.0))`, `scope.add("grading_method_count", ...)`) read the same
  `before_score` value either way — no change needed to `_grade`'s body, since it only
  ever sees the already-resolved value, not the future.
- When `grading_enabled=False`, `executor`/`before_score_future` are both `None` — no
  thread is created, matching today's exact behavior of skipping `score_text_safe`
  entirely in that case.

**Concurrency scope, deliberately minimal:** `max_workers=1` — this is not a general
thread pool, it exists solely to run one CPU-bound function concurrently with the
already-async-from-the-caller's-perspective LLM calls that happen inside
`pipeline.iter_steps(...)`. No other work is scheduled on it.

---

### 4.4 Considered and deferred (ranked recs #4–#8)

Per the findings doc, these are explicitly **not** part of SP6's scope:

- **Rec #4 — Skip computing (not just storing) the non-`combined` grading methods**
  (Finding 4). Distinct from Task 1: this would gate the
  `for method in Constants.Grading.GRADING_METHODS` loop itself inside
  `build_grading_with_before_after_score` (`models/grading.py:35-40`), not just filter
  the output. **Deferred** — the findings doc estimates the CPU saving at "at most tens
  of milliseconds" (cheap `textstat` calls), while the implementation requires a real
  conditional inside `models/grading.py`, which is also used by the main app's own
  `routes/grading.py` UI (which shows the full per-method breakdown) — real shared-code
  risk for a saving Task 1 already captures the higher-value half of (payload) at far
  lower risk. Worth revisiting only as a follow-up to Task 1 if CPU/Cloud-Run-billed-time
  at scale ever becomes a measured concern — not evidenced today.
- **Rec #5 — Drop `low_priority` from the trial's structuring-step JSON schema**
  (Finding 3 in the findings doc's detailed section, ranked rec #5). **Deferred** — the
  findings doc estimates ~1–3% of the `structure_appointment_note` step's tokens (the
  smallest-impact item evaluated), against Medium–High effort: it requires **two**
  schema variants and **two** prompt variants (the prompt's rule 11 gives the model an
  explicit place to put content that doesn't fit elsewhere; removing the schema field
  without also removing that prompt rule risks the model stuffing the same content into
  `diagnosis`/`other`/`summary` instead — an untested output-quality regression risk),
  threaded through `structure_appointment_note` → `iter_steps` → `run_care_plan_pipeline`
  → `worker.py`'s `PIPELINES` dispatch. Poor effort-to-benefit ratio versus the three
  tasks above.
- **Rec #6 — Move image/file text extraction (including Gemini-vision OCR) off the
  synchronous `POST /trial/jobs` request path** (Finding 5). **Deferred** — this pattern
  (`resolve_uploaded_files`/`extract_text_from_bytes` running synchronously before the
  job is created) is **identical** in the main app's
  `routes/care_plan_jobs.py:_resolve_input_for_job`, so fixing it "for the trial" would
  mean either diverging trial and main-app input handling (bad for maintainability) or
  redesigning the shared input-resolution contract for every caller (uploading raw bytes
  to GCS immediately, deferring extraction into the async worker, handling extraction
  failures as job-level errors instead of HTTP 400s) — a legitimate idea, but a
  deliberately shared-scope initiative in its own right, not a "trial optimization."
- **Rec #7 — Confirm `@main` alias bundle weight is minimal.** Not a finding requiring
  any change — independently re-verified by the findings doc to already be minimal (no
  Firebase/router/app-state leakage through the shared `CarePlanView`/`MedicalTerm`/
  `types/` alias). Nothing to do here.
- **Rec #8 — Firestore write count per job (7 writes).** Not a finding requiring any
  change — the findings doc verified the apparent redundancy (the stage-5 write right
  before `complete_job`) is load-bearing UX (it's what keeps "Organizing your care plan"
  showing as active for the full duration of the longest LLM call), not waste. No action
  recommended, none taken here.

---

## 5. API Change Summary

None. All three tasks are internal backend behavior/storage changes with no change to
any request/response contract (`POST /trial/jobs`, `DELETE /trial/jobs/<job_id>`,
`POST /care_plan/jobs`, or any other route's shape). Trial and main-app clients see the
same HTTP surface before and after this PRD.

---

## 6. Frontend Change Summary

None. `frontend-trial/src/screens/ResultScreen.tsx` already filters
`output_data.grading.entries` down to `name === 'combined'` on read (Task 1 makes that
filtering also true on the wire, not just on read) and already reads
`outputData.metrics?.total_duration_ms ?? 0` (Task 2 makes that value real instead of
always-zero). No `frontend/` or `frontend-trial/` file changes are required or made by
this PRD.

---

## 7. Testing

Mirrors the existing `backend/tests/{routes,services,models,care_plan}/` layout. The
suite is `cd backend && python3 -m pytest tests/ -q` (baseline: ~572 tests, 93%
coverage per `README.md`'s last-recorded run) — every new behavior below needs new or
updated tests, not just a passing baseline.

**`backend/tests/routes/test_worker.py`** (extend existing file):
- New tests for the grading-entry trim (Task 1): a trial job's completed
  `output_data["grading"]["entries"]` contains only `name == "combined"` entries (both
  `target` values present); a non-trial job's `output_data["grading"]["entries"]` is
  fully unmodified (all methods present) — regression guard, and the strongest form of
  it is asserting **the entire non-trial `output_data` dict passed to `complete_job` is
  identical to what `envelope.to_dict()` returned**, proving this task's code path is
  never entered for non-trial jobs. Also cover the defensive branches: `output_data`
  with no `"grading"` key, `grading: None`, `grading: {}` (no `"entries"` key),
  `entries: None`, and a non-dict entry inside `entries` — none of these may raise.
- **`test_trial_job_grading_survives_input_and_raw_stripping` (existing test, currently
  at line ~627) must be updated, not left as-is** — it currently asserts
  `saved_output_data["grading"] == _REAL_GRADING_DICT` (the full, untrimmed 14-entry
  dict), which this PRD's Task 1 change makes false by design (only 2 entries will
  remain after trimming). Rename/rewrite it to assert the post-trim shape instead:
  `len(entries) == 2`, both `name == "combined"`, one `target == "before"` and one
  `target == "after"`, and that each `combined` entry's `grade` still matches the value
  `_REAL_GRADING_DICT` originally computed for that name/target pair (proving the
  *values* are unaffected by trimming, only which entries are kept).
- New tests for `total_duration_ms` (Task 2): a completed job's
  `output_data["metrics"]["total_duration_ms"]` is a positive float (not `None`, not
  `0`) — for both a trial and a non-trial job, proving this is unconditional. Cover via
  freezing/monkeypatching `time.monotonic()` to return two known values (matching this
  file's existing style of mocking `routes.worker.*`) so the exact millisecond value is
  assertable, not just "truthy."

**`backend/tests/care_plan/test_pipeline_executors.py`** (extend existing file, uses the
existing `FakePipeline`/`_make_run_result` helpers):
- `grading_enabled=True` still yields an `AdapterResult` whose `grading` is built from
  the same `before_score`/`after_score` values as before (patch
  `services.care_plan_pipeline.score_text_safe` to a `MagicMock` and assert it was
  called exactly twice, with `(text, "before")` and `(event.clarified, "after")` — order
  of the *calls* doesn't matter now that one runs on a background thread, but both
  arguments must still be exactly right).
- `grading_enabled=False` creates no `ThreadPoolExecutor` at all — patch
  `services.care_plan_pipeline.ThreadPoolExecutor` and assert it is never instantiated
  (regression guard that the "only when grading is on" gate in §4.3 actually holds).
- A `PipelineStepError` mid-pipeline (via `FailingPipeline`, already defined in this
  file) with `grading_enabled=True` still yields exactly one `AdapterError` and does not
  raise or hang — proving `executor.shutdown(wait=True)` in the `finally` block cleans
  up correctly even when `before_score_future.result()` is never read.
- A `CarePlanV1_2Pipeline()` constructor failure (patch it to raise) with
  `grading_enabled=True` still yields exactly one `AdapterError` and does not leak a
  thread (same `finally`-block guarantee, one step earlier in the function).

**`backend/tests/utils/test_care_plan_markers.py`** (existing
`test_grading_run_marker_fired_when_grading_enabled` /
`test_grading_run_marker_not_fired_when_grading_disabled`, lines ~228-289): must still
pass unmodified after Task 3 — both already patch `score_text_safe` at module level with
a fixed `return_value`, which continues to work correctly once that same patched name is
called via `executor.submit(...)` instead of directly (Python resolves the module-global
`score_text_safe` name at call time, inside the running generator, which is after the
patch context manager is already active). Run these two explicitly as part of Task 3's
acceptance criteria to confirm no update was needed, rather than assuming it.

**`backend/tests/models/test_input_metrics.py`** (existing `Metrics` tests): no change
required — Task 2 only changes a *caller* (`worker.py`) of the already-existing,
already-optional `total_duration_ms` field; the model itself is untouched.

---

## 8. Manual Intervention Required From You

None. All three tasks are self-contained backend code changes with test coverage;
nothing here requires a GCP console action, a new secret, an IAM grant, or any other
step only you can perform. (SP1–SP5's existing "Still requires you" items — legal-copy
review, the live-GCP retention setup, the production cutover — are unrelated to this
PRD and remain tracked in `README.md`, not duplicated here.)

---

## 9. Open Questions & Decisions

None — all settled. This design was scoped directly from `optimization-findings-2026-09-05.md`'s
top three ranked recommendations, each already fully investigated (read-only, against
real source and a real fixture) before this PRD was written; there is no unresolved
question blocking implementation.
