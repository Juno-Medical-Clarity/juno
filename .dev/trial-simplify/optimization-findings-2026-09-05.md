# Trial Pipeline Optimization Findings — 2026-09-05

**Scope:** read-only investigation of the Juno trial request lifecycle (`POST /trial/jobs`
→ Cloud Tasks → `/internal/jobs/execute/<job_id>` → v1.2 pipeline → grading → Firestore →
`frontend-trial` snapshot/render), branch `main`, HEAD `ad5a1550`. No code was changed.
Goal: find latency/cost/payload optimizations now that the trial UI has been stripped down
(no Readability section, no Other Items / `low_priority`, glossary + `combined` score
kept).

All findings were verified by reading the actual trial frontend source and grepping for
consumption of each backend-computed field — see each finding's "Proof" line.

---

## Executive summary

The trial's per-job wall-clock time is dominated by **three sequential Gemini Pro calls**
(`simplify_language` → `clarify_and_action` → `structure_appointment_note`), each
dependent on the previous step's output — this is inherent to the pipeline design, shared
verbatim with the main app, and not realistically changeable as a "trial-only" tweak.
**Grading and term-detection are not LLM calls at all** — they're local CPU work
(`textstat` + an optional scispaCy model, and dictionary lookups), so they contribute
wall-clock time but no Vertex AI cost, and no network latency.

Given that, the real opportunities are:

1. **The trial computes and stores a full 14-entry grading blob (all 6 non-`combined`
   readability methods × before/after) when the frontend uses exactly 2 of those 14
   entries** (`combined`/before, `combined`/after) for the score widget, and 0 of them
   anywhere else (`CarePlanView` accepts a `grading` prop but never reads it; the trial's
   `downloadReport` call passes `includeReadability: false`, so `buildPdfHtml` never
   touches `grading` either). Measured on a real sample payload, the grading blob is
   **5,083 of 8,565 bytes (59%) of `output_data`**, and the 12 unused entries alone are
   **3,286 bytes (38%)** — see Finding 1.
2. **`low_priority` is a field on the single `structure_appointment_note` JSON schema**,
   not a separate LLM call — dropping it saves a small slice of prompt+output tokens on
   that one step, not a whole pipeline stage. Real savings are modest; effort is
   non-trivial because it requires threading a trial flag through pipeline code shared
   with the main app — see Finding 2.
3. **`before`-score computation (CPU-only, depends only on the raw input text) currently
   runs serially *after* all three LLM calls finish**, even though the input text is known
   before the first LLM call starts. Moving it to run concurrently with the LLM stages
   would hide its CPU cost behind Vertex AI network wait — see Finding 3.
4. Two small, genuinely free wins: **`total_duration_ms` is never actually populated
   anywhere in the backend** (Finding 6, a correctness gap more than an optimization), and
   the shared `@main` import surface (`CarePlanView`, `MedicalTerm`, `buildPdfHtml`,
   `types/`) was independently re-verified to be exactly what the PRD claims — auth-free,
   router-free, ~zero extra bundle weight (Finding 7 — a **non-finding**, confirming
   nothing needs fixing there).
5. **Image OCR (Gemini vision) and all other text extraction happen synchronously inside
   the `POST /trial/jobs` request handler, before the job is even created or enqueued** —
   this delays the moment the user sees *any* progress UI. This is real, but it is
   **shared, pre-existing behavior with the main app's `POST /care_plan/jobs`**, not
   trial-specific, so it's flagged as a structural/shared-code item rather than a
   trial-only recommendation — see Finding 5.

**If every "safe for trial, gated behind a flag" recommendation in the ranked table is
applied, the honest total estimated wall-clock saving is roughly 50–250ms per job** (all
of it CPU-bound scoring/serialization overlap and payload trimming — none of it touches
the three Vertex AI calls that actually dominate total latency, which are unaffected by
every recommendation below except the parallelization in Finding 3, itself only a
partial-overlap win). The **larger, more valuable win is payload size** (Finding 1: ~38%
smaller `output_data`, cutting the final Firestore write and snapshot payload pushed to
the client), not raw latency. Nothing here removes an LLM call, so **no material Vertex AI
cost reduction** is available without either (a) accepting an output-quality/prompt-schema
change (Finding 2, modest) or (b) a structural pipeline redesign that is out of scope for
"trial-only" (Finding 5's deeper form, and any idea of merging `clarify_and_action` +
`structure_appointment_note` into one call — noted but not recommended here since it
changes shared-pipeline behavior for every caller, not just the trial).

---

## Ranked recommendations (impact × effort)

| # | Recommendation | Impact | Effort | Blast radius |
|---|---|---|---|---|
| 1 | Drop the 12 non-`combined` grading entries from the trial's stored `output_data` (keep only `combined`/before, `combined`/after) | **High** (payload: −38% of `output_data`, ~3.3KB/job) | Low–Medium | Shared `models/grading.py` + `services/care_plan_pipeline.py`, gated by an `is_trial`/`include_method_breakdown` param — main app untouched by default |
| 2 | Compute `before`-score concurrently with the 3 sequential LLM calls instead of after all of them | Medium (hides ~tens–hundreds of ms of CPU/scispaCy time behind network wait) | Low–Medium | Shared `services/care_plan_pipeline.py`; behavior-preserving (same result, just computed earlier) — safe for **both** trial and main app, no flag needed |
| 3 | Populate `total_duration_ms` on `Metrics` (currently always `None`/0) | N/A (correctness, not perf) — but the trial's `simplify_complete` GA4 event is currently always reporting `total_duration_ms: 0` | Low | Shared `models/metrics.py` / `routes/worker.py`; additive field, no behavior change |
| 4 | Skip the trial-unused non-`combined` method computation itself (not just drop it from storage) — i.e. gate `compute_method_scores` calls, not just the entries list | Low–Medium (modest CPU savings; textstat calls are cheap, milliseconds each) | Medium (same plumbing as #1, plus touches `models/grading.py`'s `build_grading_with_before_after_score`) | Shared, must default to "all methods" for main app |
| 5 | Drop `low_priority` from the trial's structuring-step JSON schema/prompt | Low (≈1 of 15 top-level schema fields; sample data shows it's typically 1–3 short strings) | Medium–High (requires a second precomputed schema variant + threading a trial flag through `CarePlanV1_2Pipeline.structure_appointment_note` → `iter_steps` → `run_care_plan_pipeline` → `worker.py`) | Shared `care_plan/v1_2/pipeline.py`; must not change main-app schema/behavior |
| 6 | Move image/file text extraction (including Gemini-vision OCR) off the synchronous `POST /trial/jobs` request path and into the async worker | Medium–High for image-upload jobs specifically (removes N sequential vision calls from the pre-job-visible-progress window); zero for text-paste jobs | High (redesigns the input-resolution contract) | **Shared with main app** — `care_plan_jobs.py` has the exact same synchronous-extraction pattern; this is a structural, cross-cutting change, not a trial-only fix. Flagged, not recommended as trial-scoped work. |
| 7 | Confirm `@main` alias bundle weight / shared-surface risk | — | — | **No finding** — independently re-verified: `CarePlanView.tsx` + `MedicalTerm.tsx` + `types/` import only React, `createPortal`, and type-only modules. No firebase, no router, no app state. Nothing to cut. |
| 8 | Firestore write count per job (7 writes: create, processing+stage1, stage2, stage3, stage4, stage5, complete) | Low | — | Already near-minimal; the apparent "redundant" stage-5 write before `complete_job`'s own stage=5 is not actually redundant — it's what makes the "Organizing your care plan" step show *while* the (usually longest) structuring LLM call is in flight. **No change recommended.** |

---

## Detailed findings

### Finding 1 — Grading: 12 of 14 entries generated and stored, 2 used (HIGH impact, LOW–MEDIUM effort)

**What:** `services/care_plan_pipeline.py:94-105` calls
`build_grading_with_before_after_score(before_score, text, after_score, event.clarified)`
(`models/grading.py:26-63`), which for **each** of `before`/`after` calls
`compute_method_scores` (`utils/scoring_methods.py:94-104`) and emits one `GradingEntry`
per method in `Constants.Grading.GRADING_METHODS` (SMOG, Flesch-Kincaid, Dale-Chall,
PEMAT, SAM, CDC_CCI — `utils/constants.py:202-208`) **plus** one `combined` entry — 7
entries × 2 targets = **14 entries total**. All 14 are written into
`output_data["grading"]` by `worker.py:207` (`envelope.to_dict()`) and land in the
Firestore doc via `complete_job` (`utils/firebase.py:321-335`).

**Why it's safe for the trial (proof):**
- `ResultScreen.tsx:38-42` extracts exactly `entries.filter(e => e.name === 'combined')`
  for its `score_before`/`score_after` GA4 params — nothing else from `grading`.
- `ResultScreen.tsx:117` passes the **full** `grading` object to `CarePlanView`, but
  `grep -n "grading" frontend/src/components/CarePlanView.tsx` shows it appears **only**
  in the prop-type declaration (`CarePlanView.tsx:97`) — never read in the render body.
  It is dead weight passed through, not rendered.
- `downloadReport.ts:8-10` calls `buildPdfHtml(carePlan, grading, { includeReadability:
  false, ... })`; in `buildPdfHtml.ts` the Readability block is guarded by
  `if (includeReadability && grading?.enabled && grading.entries?.length)` — with
  `includeReadability: false` this branch never runs, so none of `grading.entries` is
  touched in the PDF path either.
- So of the 14 stored entries, only the 2 `combined` ones (read directly out of
  `output_data.grading.entries` in `ResultScreen.tsx`, not through `CarePlanView` or
  `buildPdfHtml` at all) are ever consumed anywhere in `frontend-trial/`.

**Estimated saving:** Measured directly against
`frontend-trial/src/tests/fixtures/realCarePlanOutput.fixture.json` (a real captured
pipeline output, 8,565 bytes total `output_data`):
- `grading` block: 5,083 bytes (59% of the whole payload)
- The 2 `combined` entries alone: 1,718 bytes
- The 12 unused method entries: **3,286 bytes (38% of the whole `output_data` payload)**

This is a **payload** saving, not primarily a latency one: it shrinks the final
`complete_job` Firestore write and the snapshot document pushed to the client over the
realtime channel. CPU-time saving from *not storing* the entries (as opposed to not
*computing* them, which is Finding 4) is ~zero — the computation already happened; this
finding is about what gets serialized into `envelope.to_dict()` / written to Firestore.
Confidence: **high** for the payload-size number (measured directly); low-to-none for any
latency claim from this specific change alone.

**Risk/blast radius:** `models/grading.py` and `services/care_plan_pipeline.py` are
shared with the main app's `/care_plan/jobs` path, where the grading UI **does** show
per-method breakdowns (main app's `CarePlanView` usage — not audited here, but the
existence of `routes/grading.py` and a dedicated grading UI in the main app implies
per-method data is live there). **Any change must be gated behind an explicit
`is_trial`/`include_method_entries` parameter threaded from `worker.py`'s
`getattr(job, "is_trial", False)` check down through `run_care_plan_pipeline` into
`build_grading_with_before_after_score`, defaulting to "include everything"** so main-app
behavior is provably unchanged. The simplest safe version: after grading is built, in
`worker.py` (alongside the existing `is_trial` block at `worker.py:218-222` that already
pops `care_plan.raw` and `input.text`), also filter
`output_data["grading"]["entries"]` down to `name == "combined"` — this requires **zero**
changes to `models/grading.py` or `services/care_plan_pipeline.py`, is a pure
post-processing step in the same place the existing trial-trim logic already lives, and
is trivially safe (same pattern, same file, same guard). This is the recommended
implementation — much lower risk than threading a flag through the grading module itself.

**Effort:** Low if implemented as the post-processing filter in `worker.py` (a few
lines, same shape as the existing `raw`/`input.text` drop). Medium if implemented as a
flag threaded through `models/grading.py` (only worth doing if Finding 4's CPU savings are
also wanted).

---

### Finding 2 — `before`-score computed serially after all 3 LLM calls, though it only needs the raw input text (MEDIUM impact, LOW–MEDIUM effort, safe for everyone)

**What:** `services/care_plan_pipeline.py:94-105`:
```python
elif isinstance(event, PipelineRunResult):
    if grading_enabled:
        before_score = score_text_safe(text, "before")
        after_score  = score_text_safe(event.clarified, "after")
        ...
```
This code only runs once the `for event in pipeline.iter_steps(...)` loop yields the
final `PipelineRunResult` — i.e., **after** `detect_terms` (fast, deterministic),
`simplify_language` (LLM), `clarify_and_action` (LLM), and `structure_appointment_note`
(LLM) have all completed. But `before_score = score_text_safe(text, ...)` depends **only**
on `text`, the original input — available before the pipeline even starts
(`care_plan/v1_2/pipeline.py`'s `iter_steps(self, text, ...)` receives it as its first
argument). `score_text` (`utils/scoring.py:253-306`) is pure CPU work: `textstat` calls
plus, if `en_core_sci_sm` loaded successfully at import time
(`utils/scoring.py:21-24`), a spaCy pass over up to 50,000 characters
(`utils/scoring.py:143`, `text[:50000]`) for passive-voice detection.

**Why it's safe:** This is a pure reordering — the same `score_text_safe(text, "before")`
call, with the same input, producing the identical result, just started earlier (e.g. on
a background thread via `concurrent.futures.ThreadPoolExecutor` submitted at the top of
`run_care_plan_pipeline`, joined right before `build_grading_with_before_after_score` is
called). No output changes for anyone — trial or main app. This is not a trial-only
change and needs no flag; it's a correctness-preserving performance change to shared code.

**Estimated saving:** Not directly measurable from logs (no per-stage timing exists in
this codebase — see Finding 6). Honest estimate: `textstat`'s SMOG/Flesch-Kincaid/
Dale-Chall/lexicon/sentence counters are each sub-millisecond to a few milliseconds on
typical care-plan-length text; the spaCy `en_core_sci_sm` pass (if available; the `except
Exception` fallback at `utils/scoring.py:22-24` means it may not be installed/loaded in
this environment at all) is the dominant cost and could plausibly be tens to a couple
hundred milliseconds on a long document. Overlapping this with ~3 sequential Vertex AI
calls (each very likely several seconds) means the win is "free" (fully hidden) as long as
the LLM calls take longer than the scoring work, which is almost certainly true. Net wall
-clock saving: **low tens to ~200ms**, entirely hidden/free if the assumption holds; zero
downside if it doesn't (worst case, no overlap achieved, same total time as today).

**Risk:** Low. Needs care that `score_text_safe`'s internal exception handling (already
present, `utils/scoring.py:307-313`) is preserved across the thread boundary, and that the
`Markers.Grading.Run` span (`services/care_plan_pipeline.py:97-104`) still gets correct
attributes when the "before" half of the work already ran on another thread — some
telemetry code near the marker `scope.add("before_composite", ...)` may need minor
adjustment. Effort: Low–Medium (concurrency plumbing + telemetry adjustment, still a
small, self-contained change).

---

### Finding 3 — `low_priority` is one field of one LLM call's schema, not a separate call (LOW impact, MEDIUM–HIGH effort)

**What:** `low_priority: list[str] = Field(default_factory=list)` is one of 15 top-level
properties in `CarePlanV1_2` (`models/care_plan/versions/v1_2.py:117`) that the single
`structure_appointment_note` LLM call (`care_plan/v1_2/pipeline.py:143-155`) is asked to
populate, per the `structure_note.txt` prompt's rule 11 ("Put low-priority details in
low_priority array", `care_plan/v1_2/prompts/structure_note.txt:15`). The
`_STRUCTURING_SCHEMA` module-level constant (`care_plan/v1_2/pipeline.py:64-67`) is
computed once at import time via `_llm_schema(CarePlanV1_2, exclude={"terms", "raw",
"note"})` — the exclusion mechanism already exists and already proves this kind of
schema-trimming is safe and cheap to do; `low_priority` is simply not in that exclude set
today.

**Why it's safe for the trial (proof):** `ResultScreen.tsx:117` passes `hideLowPriority`
to `CarePlanView`, which at `CarePlanView.tsx:304` gates the "Other Items From Your Visit"
card on `!hideLowPriority && result.low_priority?.length > 0` — never rendered in the
trial. `downloadReport.ts:10` passes `includeLowPriority: false` to `buildPdfHtml`, which
gates its own "Other Items" section the same way (`buildPdfHtml.ts`, the
`includeLowPriority && result.low_priority?.length` guard). Confirmed: `low_priority` is
generated but never displayed anywhere in `frontend-trial/`.

**Estimated saving:** Low confidence, but bounded: `low_priority` is 1 of 15 schema
properties, and the sample fixture shows a typical value of 1 short sentence (34 bytes for
the whole array in that sample). Removing it from the schema shrinks the prompt (a few
dozen tokens of schema JSON) and very slightly shrinks the model's own output (it no
longer needs to emit that key or its contents) — plausibly **1–3% of the
`structure_appointment_note` step's total tokens**, translating to a similarly small
fraction of that one step's generation latency (autoregressive decoding time scales
roughly with output tokens). This is the smallest-impact item in this document.

**Risk:** Medium, for a subtler reason than plumbing difficulty: the prompt's rule 11
currently gives the model an explicit "escape valve" for information that doesn't belong
in the main clinical fields. Removing `low_priority` from the schema without also removing
rule 11 from the prompt risks the model stuffing that same content into `diagnosis`,
`other`, or `summary` instead — a real (if untested) output-quality regression risk, not
just a schema-diffing exercise. Any implementation must also edit the prompt text
conditionally, which means **two schema variants and two prompt variants**, threaded
through `structure_appointment_note` → `iter_steps` → `run_care_plan_pipeline` →
`worker.py`'s `PIPELINES` dispatch, gated on the same `is_trial` flag already available in
`worker.py:218`. This is real plumbing through pipeline code the main app depends on
verbatim.

**Effort:** Medium–High, disproportionate to the small saving. **Not recommended as a
priority** — flagged for completeness per the task brief, but the effort/risk-to-benefit
ratio here is poor compared to Finding 1.

---

### Finding 4 — Skipping the non-`combined` method *computation* itself, not just its storage (LOW–MEDIUM impact, MEDIUM effort)

**What:** Distinct from Finding 1 (which only stops *storing* the 12 unused entries):
this would stop *computing* them at all, by gating the loop in
`build_grading_with_before_after_score` (`models/grading.py:35-40`, `for method in
Constants.Grading.GRADING_METHODS: ...`) behind a flag, so `compute_method_scores`
(`utils/scoring_methods.py`) — which redundantly recomputes `textstat.smog_index`,
`textstat.flesch_reading_ease`, `textstat.flesch_kincaid_grade`, and
`textstat.dale_chall_readability_score` (already computed once inside `score_text`'s
`_score_grade_level`, `utils/scoring.py:91-104`, for the `combined` grade-level dimension)
— is skipped entirely for trial jobs.

**Why it's safe:** Same proof as Finding 1 — none of the 12 non-`combined` entries are
consumed anywhere in `frontend-trial/`.

**Estimated saving:** Low confidence. These are cheap textstat calls (each likely
low-single-digit milliseconds); skipping 12 of them (6 methods × 2 targets) saves at most
tens of milliseconds of CPU time per job. Given Finding 1 already gets the payload win at
much lower risk, this is only worth doing if CPU/Cloud-Run-billed-time at scale is a
concern, which isn't evidenced by anything found here.

**Risk:** Medium — this one *does* require touching `models/grading.py` (used by the main
app's own grading route/UI, `routes/grading.py`) with a real conditional, not a
post-hoc filter. Must default to computing all methods.

**Effort:** Medium. **Recommended only as a follow-up to Finding 1, not standalone.**

---

### Finding 5 — Text/image extraction runs synchronously in the request handler, before the job exists (MEDIUM–HIGH impact for image jobs, HIGH effort, shared code — not a trial-only fix)

**What:** `routes/trial.py:_resolve_trial_input` (`routes/trial.py:32-72`) calls
`resolve_uploaded_files(uploads)` (`services/care_plan_input.py:107-159`) **synchronously,
inside `create_trial_job`'s handler, before `job_id` is generated, before
`create_job_doc` is called, and before `enqueue_job_safe`**. For image uploads, this
means `extract_text_from_bytes` → `extract_text_from_image`
(`utils/image_ocr.py:37-64`) → `LLMClient.generate_text_from_image` — **a full Gemini
vision call per image, run sequentially in a loop** (`services/care_plan_input.py:130`'s
`for upload in files:`) — all execute before the client ever receives a `job_id` and can
start watching the Firestore snapshot / seeing the processing screen. For a multi-image
upload (trial allows up to `Constants.Trial.MAX_FILE_COUNT = 5` files,
`utils/constants.py:83`), this could be several sequential vision-model round trips
entirely invisible to the user — no "Reading your note" progress, just a stalled request.

**Why it's flagged but not recommended as trial-scoped:** This exact pattern —
synchronous `resolve_uploaded_files`/`extract_text_from_bytes` before job creation — is
**identical** in `routes/care_plan_jobs.py:_resolve_input_for_job` (`routes/
care_plan_jobs.py:29-95`), which the main app uses for every logged-in user's upload,
including images (image support was explicitly added to both surfaces per D5, "not
trial-scoped"). Moving extraction into the async worker would require redesigning the
input-resolution contract (uploading raw file bytes to GCS immediately, deferring
extraction to `execute_job`, handling extraction failures as a job-level error instead of
an HTTP 400) — a change to shared behavior, not a "gate behind an `is_trial` flag" change,
since the whole point would be to fix the same latency problem for the main app too.

**Estimated saving:** For text-paste trial jobs (no upload) — **zero**, this code path
isn't hit. For image-upload trial jobs — potentially significant (moves N sequential
vision calls behind the point where the user first sees progress), but no measurement
exists in this repo to quantify N or per-call latency; purely qualitative.

**Risk:** High if done as a quick trial-only hack (would diverge trial and main-app input
handling in a way that makes the codebases harder to keep in sync). **Recommendation:
treat as a separate, deliberately shared-scope initiative if pursued, not part of a
"trial optimization" pass.**

**Effort:** High.

---

### Finding 6 — `total_duration_ms` is never populated (correctness gap, adjacent to this task)

**What:** `Metrics.total_duration_ms` (`models/metrics.py:19`) defaults to `None` and is
never assigned anywhere in non-test production code —
`grep -rln "total_duration_ms" backend --include=*.py` (excluding `tests/`/`__pycache__`)
returns only `models/metrics.py` (the field definition) and `utils/constants.py` (a list
of allowed field names for something unrelated, `utils/constants.py:249`). No pipeline
stage, `worker.py`, or `envelope.py` ever sets it.

**Why this matters here:** `ResultScreen.tsx:44` reads
`outputData.metrics?.total_duration_ms ?? 0` and sends it as the `total_duration_ms`
param on the `simplify_complete` GA4 event described in the task background. As shipped,
**this analytics field is always `0`** — not a performance regression, but a
data-quality gap directly adjacent to the "what's sent to analytics" question this task
was asked to consider, and worth a one-line fix (stamp `total_duration_ms` in `worker.py`
right before `complete_job`, e.g. `time.monotonic() - start` already computed at
`routes/worker.py:87` for the timeout check, multiplied to milliseconds) since the
instrumentation to compute it (the `start = time.monotonic()` timer) already exists at
`routes/worker.py:87` and is simply never read back out at the end.

**Risk:** None — purely additive, and useful for *validating* every latency claim in this
document going forward (right now there is no per-job timing data to check any of these
estimates against).

**Effort:** Trivial (a few lines in `worker.py`, wired to the existing `Metrics` object
before `envelope.to_dict()` is called at `worker.py:207`).

---

### Finding 7 — `@main` alias bundle weight (non-finding: already minimal)

**What was checked:** whether `frontend-trial`'s reuse of `CarePlanView`, `MedicalTerm`,
`buildPdfHtml`, and `types/` via the `@main` Vite alias
(`frontend-trial/vite.config.ts:31-35`) pulls in unwanted main-app weight (auth, routing,
Firebase, app-global state).

**Result:** Independently re-verified by reading every import line of the aliased files:
- `CarePlanView.tsx:1-4` imports only `react` (`useState`, `ReactNode` type), two
  type-only modules (`../types/carePlan`, `../types/envelope`), and `./MedicalTerm`.
- `MedicalTerm.tsx:1-9` imports only `react` and `react-dom`'s `createPortal`.
- `types/envelope.ts` imports only `./carePlan` (another type-only module).

No Firebase, no router, no app-global state, no CSS-in-JS libraries anywhere in this
subtree. This matches (and independently confirms) the claim already recorded in
`03-trial-frontend/PRD.md`. **Nothing to optimize here.** The trial's actual bundle
weight (`frontend-trial/dist/assets/index-*.js`, 776KB unminified-report/776,505 bytes on
disk) is dominated by `firebase/app` + `firebase/auth` + `firebase/firestore` (needed for
anonymous auth and the live snapshot listener — both load-bearing, D1/D9-adjacent) and
`react-router-dom` (used for the 3 real routes: `/`, `/privacy`, `/terms`). A legitimate,
independent small win **not part of the backend/pipeline scope of this task**: lazy-load
`PrivacyPage`/`TermsPage` via `React.lazy` (`App.tsx`'s `<Route>` elements) since they're
rarely the first page a visitor hits, shaving some KB off the initial parse/eval for the
upload screen. Noted for completeness; low confidence on magnitude without a bundle
analyzer run, and outside this task's backend-pipeline focus.

---

### Finding 8 — Firestore write count (7 per job) — no change recommended

**What:** Per job: `create_job_doc` (1, `routes/trial.py`'s `create_job_doc` call) →
worker's `status=processing/stage=1` update (1, `routes/worker.py:73-78`) →
`update_job_stage` for stages 2, 3, 4, 5 as each pipeline step goes "active"
(`routes/worker.py:163-168`, up to 4 more) → `complete_job` (1, `routes/worker.py:207-...`,
`utils/firebase.py:321-335`). Total: up to 7 writes, each pushed to the client's
`onSnapshot` listener (`useTrialJobSnapshot.ts:47-70`).

**Why no change is recommended:** The apparent redundancy — `update_job_stage(5)` firing
right before `complete_job` also sets `stage: 5` — is not actually wasted: it's what
makes the "Organizing your care plan" step show as *active* in `ProcessingScreen.tsx`
(`TRIAL_STEPS` id 5, `ProcessingScreen.tsx:13-19`) for the full duration of the
(typically longest, long-form-budget) `structure_appointment_note` LLM call. Removing it
would leave the UI showing "Clarifying actions and numbers" as active for the entire
final LLM call — a real UX regression for a ~0-cost write. 7 writes for a ~5-stage
pipeline with live progress is not chatty by any reasonable bar. **No action recommended.**

---

## Do not touch

These are explicitly out of scope for optimization, called out so nobody "cleans them up"
in a follow-on pass:

- **Rate limiting (`utils/rate_limit.py`)** — the Firestore-transactional per-IP counter
  adds a small amount of latency to every `POST /trial/jobs` call, but it is the D11/D4
  abuse-protection mechanism (5/hour per IP) and a locked decision. Do not remove or
  weaken to save latency.
- **`min-instances=0` / cold starts (D7)** — the accepted ~15–30s first-load wait after
  idle is an explicit, locked product decision, not an oversight. Do not add
  cold-start-masking UI or bump `min-instances` "to help latency" without re-opening D7.
- **`services/retention.py` (anonymous Auth cleanup) and the Firestore TTL /
  `expires_at`/GCS-lifecycle retention path (SP5)** — safety-critical (`_is_anonymous`'s
  predicate is explicitly documented as having one accepted residual risk, SP5 §9 Q4) and
  entirely orthogonal to job-processing latency. Nothing found in this investigation
  touches or should touch this path.
- **The explicit `DELETE /trial/jobs/<job_id>` call fired from `ResultScreen.tsx:24-27`**
  the moment the result screen mounts — this is the primary, user-visible half of the "no
  data is saved" promise (SP2/SP3 §4.13). Do not defer or batch this to "save a request";
  it is deliberately immediate and best-effort-idempotent.
- **`raw`/`input.text` dropping already shipped (`b3ab5f95`, `eb375b40`,
  `routes/worker.py:218-222`)** — already optimal for the trial; no further trimming of
  those two fields is possible since they're already fully removed for `is_trial` jobs.
- **The 3 sequential Vertex AI calls themselves** (`simplify_language`,
  `clarify_and_action`, `structure_appointment_note`) — each depends on the previous
  step's actual output (not just its schema), so they cannot be parallelized without
  changing what the model is asked to do at each step. Merging steps (e.g.
  `clarify_and_action` + `structure_appointment_note` into one call) is a real idea but is
  a **shared-pipeline redesign affecting every caller** (main app included), well beyond
  a "trial optimization" — noted in the executive summary, not detailed as a
  recommendation here.
- **Legal copy, GCP provisioning, and every other "owner-only" item already tracked in
  `README.md`** — irrelevant to this investigation and not re-litigated here.
