# Code Review — 03-grading-rework

Branch: `feature/structured-output-grading-batch-input`
Reviewer: automated production-readiness review (review-only, no code changed)
Tests run: `pytest tests/test_grading_model.py tests/test_scoring_methods.py` → **32 passed**.

---

## Summary verdict — Quality score: **4 / 5**

This is the most complete sub-project of the set. The implementation faithfully follows the PRD's
detailed code sketch: `GradingEntry`/`Grading` models, the six per-method scorers in
`scoring_methods.py`, the `build_grading()` converter, the `POST /simplify/grade` endpoint (with
auth + ownership checks + 404/403/400 paths), and `grading_enabled` wiring that is **consistent
across all three pipeline versions** (v1, v1-1, v1-2). The before/after-score data was correctly
removed from `SimplifiedCarePlan` and now lives only inside `Grading.entries`. Backend test coverage
for the model, scorers, and the new route is genuinely good (32 tests, including the saved_id
overwrite/404/403 cases the PRD asked for). The frontend wiring is clean and matches the spec
(selectors, ConfigurationCard toggle, MethodGradingCards, OutputGradingCard).

It falls short of 5/5 because of: (1) **zero frontend test coverage** for any grading component or
the `grading.ts` selectors; (2) **no rate/size limits** on the `/simplify/grade` text-mode endpoint
(an unauthenticated-cost vector mitigated only by auth); (3) **no metrics/structured logging** on the
re-grade endpoint (it uses bare `logging`, not `JunoLogger`/`JunoMetrics` like the rest of the
codebase); (4) duplicated `_get_doc_or_403` instead of the shared helper TASKS.md explicitly asked
for; and (5) a handful of small correctness/robustness edges around malformed saved-doc dimensions
and the SAM denominator documentation mismatch.

---

## Correctness vs PRD / TASKS

Mostly complete and faithful. Item-by-item:

- **Task 1 (model):** Done. `to_dict`/`from_dict` round-trip; `Grading()` → `{entries: [], enabled:
  True, graded_at: None}`. Matches acceptance criteria.
- **Task 2 (scoring_methods):** Done. All six scorers + `compute_method_scores` match the PRD sketch
  almost verbatim; `_grade_to_score` imported from `scoring.py` (no duplication). SMOG `<30
  sentences` → `score 0, insufficient_sample True`. FK clamp to [0,100]. Good.
- **Task 3 (build_grading):** Done with the updated 4-arg signature. Produces 14 entries (7×2),
  combined entry carries the full `dimensions` dict. Matches acceptance tests.
- **Task 4/5 (wiring v1-2, v1, v1-1):** Done and **consistent** across all three. `grading_enabled`
  defaults to `True` when the field is absent (verified: `_grading_enabled_from_request` and the
  inline equivalents seed `raw = json_data.get("grading_enabled", True)` before the truthy-string
  test, so an omitted field → `True`, not `False`). Both `score_text` calls are genuinely gated
  (compute saved, per Goals). Disabled path builds `Grading(enabled=False)` → empty entries.
- **Task 6 (`POST /simplify/grade`):** Done as a separate `routes/grading.py` blueprint, registered
  in `routes/__init__.py`. Both modes implemented; saved_id mode overwrites `output_data.grading`.
  Auth via `@verify_firebase_token`; ownership via `_get_doc_or_403`.
- **Tasks 7–10 (frontend):** Done. ConfigurationCard toggle (default checked), `grading.ts`
  selectors match the PRD exactly, `MethodGradingCards` renders 6 cards with before→after bubbles +
  breakdown + reasoning, `OutputGradingCard` posts to `/simplify/grade` and lifts state up via
  `onGraded`. `ReadabilityCard` not rewritten; only rendered when both before & after non-null.
- **Task 11 (tests):** Backend done well. **Frontend tests entirely absent** (see gaps below).

**Deviations from PRD (acceptable / minor):**
- SAM `total_possible` is `28` in code (and in the PRD code sketch), but the PRD §4 *table* row says
  `total_points / 42 * 100`. The code follows the sketch (28 = 8+14+6 automatable domains). This is
  a PRD-internal inconsistency, not a bug, but the divergence should be reconciled in docs so the
  score's meaning is unambiguous.
- "before" scoring was kept (the default per PRD §8). Correct given no instruction to drop it.

---

## Bugs & Edge Cases (severity-tagged)

- **[Medium] Malformed saved-doc dimensions cause a 500 on re-grade.** In `routes/grading.py`,
  `build_grading` calls `compute_method_scores(text, score["dimensions"])`, and `score_pemat`/
  `score_sam`/`score_cdc_cci` index hard keys like `dimensions["jargon_density"]["score"]`. For the
  saved_id path the *text* is re-scored fresh via `score_text`, so dimensions are well-formed — OK.
  But there is no defense if `score_text` ever returns a dict missing a dimension (future schema
  drift) — it would raise `KeyError` and surface as an unhandled 500 (no try/except around
  `build_grading` in the route, unlike `_score_safe` which only wraps `score_text`). Low likelihood
  today, but the re-grade route has no top-level error handler.
- **[Low] `_score_safe` swallows real errors silently to the user.** If `score_text` throws, the
  target is dropped and the endpoint returns a `Grading` with fewer entries and **HTTP 200** — the
  frontend can't distinguish "graded with 7 entries" from "before-scoring crashed." A partial
  failure is invisible. Acceptable for readability scoring (deterministic, rarely throws) but worth a
  flag in the response.
- **[Low] Empty `clarified_text` in saved_id mode yields a before-only Grading silently.** If a saved
  doc has `raw.text` but no `clarified_text`, the result is a 7-entry (before-only) Grading. The
  frontend `ReadabilityCard` only renders when **both** before & after are non-null, so the combined
  card silently disappears after a re-grade — confusing UX with no error.
- **[Low] `request.get_json(silent=True)` called inside SSE generators.** In the pipeline routes
  `_grading_enabled_from_request` / inline equivalents call `request.get_json` while already inside
  the streaming generator. It works because Flask caches the parsed body, but reading `request` deep
  inside a generator is fragile; pre-reading the flag before entering the stream (as v1-2 does at
  line 506, good) is the safer pattern — v1 reads it inside the per-branch generator body instead.
  Inconsistent but currently functional.
- **[Low] `combined.grade` is an int, typed `float`.** `score["composite"]` is `round(...)` → int;
  `GradingEntry.grade` is annotated `float`. Harmless (JSON-wise), purely cosmetic.
- **[Info] No `low_confidence` propagation.** `score_text` sets `low_confidence` for tiny samples,
  but `build_grading` never carries it into any entry, so the frontend can't warn that a score is
  unreliable. The old path didn't either; not a regression, but a lost signal.

---

## Test Coverage Gaps (concrete list)

Backend is solid; the gaps are concentrated on the frontend and a few backend error paths.

**Backend — missing:**
- `score_smog` on text with **0 sentences** / empty string (division and `<30` branch boundary).
- `score_dale_chall` / `score_flesch_kincaid` on empty or whitespace text (textstat behavior on `""`).
- `_score_safe` / route behavior when `score_text` **raises** (the silent-drop-to-200 path is
  untested — assert the 7-entry partial result).
- saved_id path where saved doc has `raw.text` but **no `clarified_text`** (before-only Grading).
- A test asserting `graded_at` **changes** between two consecutive `/simplify/grade` calls and that
  entries are **overwritten, not appended** (PRD §7 explicitly asked for the "two different
  timestamps, no array growth" assertion — current `test_saved_id_updates_firestore` checks the
  update call fired but not the double-call overwrite semantics).
- A route test for `grading_enabled=false` **on the actual pipeline route** (not just the model
  unit). PRD §7 asked for `grading.entries == []` via the v1-2 route; current coverage tests
  `build_grading`/`Grading` in isolation, not the route gate end-to-end.

**Frontend — ZERO coverage (all missing):**
- `patientScoreFromGrading`: (a) returns `null` when entries empty; (b) returns `null` when combined
  entry lacks `dimensions`; (c) correctly reconstructs `PatientScore` from a combined entry; (d)
  handles missing `grade_estimate`/`label`/`word_count` defaults.
- `methodEntriesFromGrading`: filters by target and excludes `combined`.
- `MethodGradingCards`: renders 6 cards; returns `null` when `afterEntries` empty (grading disabled);
  renders before→after bubble only when a matching before entry exists.
- `OutputGradingCard`: uses `saved_id` when present vs `text`/`clarified_text` fallback; surfaces the
  error message on non-OK response; calls `onGraded` with the parsed grading on success.
- `AppointmentNoteV12View`: combined+method cards disappear when grading disabled (empty entries).

---

## Security

- **[Good] Auth + ownership enforced.** `/simplify/grade` requires `@verify_firebase_token`;
  saved_id mode checks `data.get("uid") != user_id` → 403, missing → 404. Solid.
- **[Medium] No input size limit on text-mode re-grade.** `{ "text": ..., "clarified_text": ... }`
  is scored directly with no length cap at the route. `score_text` runs regex + textstat + optional
  spaCy on it; spaCy is capped at 50k chars *inside* `_score_passive_voice`, but the regex passes
  (`PASSIVE_RE`, `IMPERATIVE_RE`) and textstat run on the full string. A multi-MB body is a cheap
  CPU-DoS vector for any authenticated user. Add a max-length guard (e.g. reject > N chars) on both
  text fields.
- **[Low] No rate limiting / per-user cost cap on re-grade.** The "Run Grading" button can be clicked
  repeatedly; each saved_id call does a Firestore read + write. No throttle. Grading is CPU-only (no
  LLM), so cost is bounded, but unbounded Firestore writes per click are worth a debounce server-side
  too, not just client `disabled={loading}`.
- **[Good] No LLM on user content.** Per Non-Goals, grading is deterministic readability scoring —
  so there is **no prompt-injection surface** here, and no LLM cost/token risk. This materially
  lowers the security stakes versus an LLM-judge design.
- **[Low] PII in logs.** `_score_safe`/`_score_or_none` use `logger.exception(...)` without text
  content — good. But the pipeline routes log `input_chars`/source descriptions; no raw medical text
  is logged in the grading paths reviewed. No issue found.

---

## Logging & Metrics

- **[Medium gap] `routes/grading.py` uses bare `logging`, not `JunoLogger`/`JunoMetrics`.** Every
  other route in scope (`simplify_v1_2.py` etc.) uses the structured `JunoLogger` + `JunoMetrics`
  (see `utils/LOGGING.md`). The re-grade endpoint emits **no** latency metric, no counter, no
  structured step logs. There is no way to observe how often re-grading is invoked, how long it
  takes, or its error rate. This is the single biggest observability gap.
- **[Low gap] No per-method timing or counters anywhere.** Neither the pipeline grading path nor the
  re-grade path records per-method (`smog`, `pemat`, …) timings or a `grading_runs` counter. PRD
  didn't strictly require it, but for an "extensible array of methods" it would be the natural place
  to track which methods are slow.
- **[Low] Inconsistent error reporting.** Pipeline routes record `juno_metrics.record_error(...)` on
  score failure paths in some places; the grading route just logs and returns. Standardize.

---

## Extensibility

- **[Good] Adding a directly-computable method (text-based) is easy-ish** but **not a clean
  registry.** `compute_method_scores` hardcodes a dict literal of six calls, and `build_grading`
  hardcodes the tuple `("smog","flesch_kincaid","dale_chall","pemat","sam","cdc_cci")` **a second
  time**, plus `_METHOD_REASONING` is a third parallel list, and the frontend `METHOD_LABELS` is a
  fourth. Adding a method means editing **four** separate hardcoded lists (two backend, one reasoning
  map, one frontend). A single registry (`METHODS = {name: (scorer_fn, reasoning, takes="text"|"dimensions")}`)
  would collapse these and remove the drift risk. This is the main extensibility debt.
- **[Good] The array schema genuinely is additive** for a *new kind* of grader (e.g. clinical
  accuracy) — a new `name` value needs no schema change, exactly as the PRD intended. The frontend
  `MethodGradingCards` renders any breakdown generically (`Object.entries → key: value`), so a new
  method with arbitrary breakdown keys displays without code change. That's a real win.
- **[Low] Minor duplication vs `scoring.py`.** `scoring_methods.py` recomputes `textstat.smog_index`,
  `flesch_reading_ease`, etc. that `scoring.py`'s `_score_grade_level` also computes internally —
  textstat is re-run per method. Acceptable (cheap, keeps modules decoupled), but worth noting the
  same text is tokenized many times per grade.
- **[Low] `_get_doc_or_403` duplicated.** TASKS.md Task 6 explicitly said "reuse `_get_doc_or_403`
  from `saved_outputs.py` — move to `backend/utils/firestore_helpers.py` if private, don't
  duplicate." It was **copy-pasted** into `routes/grading.py` instead. Two copies now drift
  independently (the `saved_outputs.py` one is the canonical ownership check). Extract to a shared
  helper.

---

## Must-fix before production (checklist)

1. **[Medium] Add an input size limit** on `/simplify/grade` text-mode (`text` / `clarified_text`)
   to close the CPU-DoS vector.
2. **[Medium] Wrap `build_grading` / the re-grade route body in error handling** and return a proper
   500/partial-failure signal instead of risking an unhandled `KeyError`; surface partial-failure
   (dropped target) to the client rather than silent HTTP 200.
3. **[Medium] Add `JunoLogger` + `JunoMetrics`** to `routes/grading.py` (latency, counter, error
   metric) so re-grade is observable like the rest of the system.
4. **[Medium] De-duplicate `_get_doc_or_403`** into a shared `firestore_helpers` (as TASKS.md
   required) to prevent ownership-check drift.
5. **[Medium] Add frontend tests** for `grading.ts` selectors, `OutputGradingCard` (saved_id vs text
   fallback, error surface), and `MethodGradingCards` (empty → null) — currently zero.
6. **[Low] Add the PRD-§7 route-level tests** still missing: `grading_enabled=false` end-to-end on a
   pipeline route, and the double-call overwrite/`graded_at`-changes assertion.
7. **[Low] Reconcile the SAM denominator** (28 vs the PRD table's 42) in the PRD/docs so the score's
   normalization basis is unambiguous.
8. **[Low] Consider a method registry** to collapse the four parallel hardcoded method lists before
   the next method is added.
