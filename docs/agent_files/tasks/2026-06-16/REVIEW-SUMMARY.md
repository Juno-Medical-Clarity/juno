# Branch Review — `feature/structured-output-grading-batch-input`

**Date:** 2026-06-17
**Reviewer:** Claude Code (5 parallel sub-project review agents + verification)
**Scope:** Full branch diff vs `main` — 74 files, +8,663 / −666 lines, across 5 sub-projects.
**Per-sub-project detail:** see each `docs/2026-06-16/<NN>-*/REVIEW.md`.

---

## TL;DR

The branch is **substantial, well-structured, and mostly high quality** — the backend model layer, grading rework, batch path-traversal defenses, and history grouping are all solid and faithful to their PRDs. Backend tests are green (**116 passed**).

**It is NOT production-ready yet.** Two classes of blocker:

1. **The frontend production build is broken** (`npm run build` fails with 2 TypeScript errors) — confirmed, deploy blocker.
2. **Batch processing lacks resource limits and per-item failure isolation** — an authenticated user can abort a whole batch on one bad row, orphan saved outputs, or trigger unbounded LLM cost/DoS.

Plus a structural gap: **frontend test coverage is effectively zero** (5 tests in 1 file) against ~2,500 lines of new/changed React, including the 632-line `SimplifyPage`.

### Quality scorecard

| Sub-project | Quality | Tests (backend) | Headline risk |
|---|---|---|---|
| 01 core-output-envelope | 4/5 | green | v1/v1-1 build envelope with wrong `Input` (file inputs mislabeled `text`, doc text persisted) |
| 02 version-config-selection | 3/5 | green (8) | **CRITICAL: prod build broken**; dead legacy pages not deleted |
| 03 grading-rework | 4/5 | green (32) | No size limit / observability on re-grade route |
| 04 batch-dataset-input | 4/5 | green (13) | **No batch size cap + no per-item failure isolation** |
| 05 output-history-grouping | 4/5 | green (4) | Timezone (UTC vs local) date bucketing mismatch |

---

## 🚨 Must-fix before production (P0 — blockers)

1. **Fix the broken frontend build.** `npm run build` (`tsc -b` + `vite build`) fails:
   - `frontend/src/router.tsx:9` — `versionPath()` reads `version.path`, removed from `config.ts` in SP02 (Task 7 said delete `versionPath()`; it wasn't).
   - `frontend/src/utils/normalizeOutput.ts:29` — returns `grading: { entries: [] }`, missing the now-required `enabled` and `graded_at` fields of the `Grading` type (SP01/SP03 boundary).
   - **Note:** a bare `npx tsc --noEmit` reports clean and masks both — CI must run the real `npm run build`.
2. **Delete the dead legacy pages** `V1Page.tsx` / `V1_1Page.tsx` / `V1_2Page.tsx` (SP02 Tasks 5/6). They're unrouted and also reference the removed `version.path`, so they're a latent re-break.
3. **Batch resource limits (DoS / cost).** `backend/routes/batch.py`: cap `selections` count, cap per-file/dataset bytes (`MAX_FILE_BYTES` is enforced on uploads but **not** on dataset reads), and bound the `"inputs":"all"` expansion. One authed request currently maps to unbounded sequential LLM runs.
4. **Batch per-item failure isolation.** Any empty/erroring input does a bare `return` (`batch.py:158,182,196`), killing the whole batch and **excluding already-saved Firestore outputs** from the result — orphaned data + UI reset. Wrap each item; collect per-item errors; continue.

## 🔴 High priority (P1 — fix before or immediately after launch)

5. **SP01 envelope `Input` bug.** v1 (`simplify.py:199`) and v1-1 (`simplify_v1_1.py:284`) call `Input.from_text(text)` unconditionally, so file/doc_id inputs get `input.mode="text"` (contradicting `metrics.input_type="file"`), drop file metadata, and **v1-1 persists the full document text into `input.text`**. v1-2 does it correctly via `_input_model_from_resolved` — port that.
6. **Add batch logging/metrics.** `batch.py` emits no start/done/error logs and no batch-level metric — when a batch aborts you can't tell which item failed. Use `JunoLogger`/`JunoMetrics` per `backend/utils/LOGGING.md`.
7. **SP05 timezone bug.** Date bucketing uses UTC (`created_at.slice(0,10)`) but the header reparses as local (`new Date(date+'T12:00:00')`) and "today" default-expand is UTC. Users west of UTC see evening outputs filed under tomorrow. Decide on one timezone and make bucketing + labeling + "today" consistent; add a test.

## 🟡 Medium priority (P2 — quality / robustness)

8. **SP03 re-grade route hardening:** no input size limit on `/simplify/grade` text-mode (authed CPU-DoS via textstat/regex on unbounded body); uses bare `logging` instead of `JunoLogger`/`JunoMetrics` (no latency/error metrics); no top-level error handling around `build_grading` (malformed dims → unhandled 500); `_score_safe` silently drops a target yet returns 200.
9. **SP03 dedup:** `_get_doc_or_403` was copy-pasted into `grading.py` instead of shared via `firestore_helpers` (TASKS said share it) — two ownership checks that can drift.
10. **SP02 dispatcher observability:** no log/metric for selected version or default-fallback usage — routing layer is unobservable.
11. **SP04 robustness:** no SSE heartbeat for long batches (proxy idle-timeout risk); selected `files` not validated up front (a typo dies mid-run via `FileNotFoundError`).
12. **SP05 collapse state not persistent** (`<details open>` resets on every refetch from rename/delete); same batch crossing UTC midnight splits into two identical-labeled groups.
13. **SP01 misc:** `SimplifiedCarePlan.from_dict` raises bare `KeyError` (inconsistent with base's descriptive `ValueError`); base `from_dict` does `cls(**data)` → `TypeError` on any unknown key (forward-compat landmine if stored docs are ever deserialized through models); v1-1 writes step durations only on success path; v1-2 falls back to `user_id` as `session_id` (leaks Firebase UID into response/UI).

---

## Test coverage assessment

**Backend: good.** 116 pass; models, scoring methods, grading routes, batch route, dataset routes, version dispatch, persistence all covered. Concrete gaps to add:

- **SP04 (most important):** partial-failure path, empty/malformed `selections`, unknown input id, non-txt dataset preview, large/many-input batch (limit enforcement).
- **SP03:** `grading_enabled=false` end-to-end on a pipeline route (PRD §7), double-call overwrite + `graded_at` change assertion, `score_text`-raises path.
- **SP01:** `SimplifyOutput.from_dict(to_dict())` round-trip; assert `input` shape for v1/v1-1 file uploads (catches bug #5).
- **SP02:** real end-to-end asserting `metrics.pipeline_version` / `care_plan.version` per dispatched version (current tests only mock the target).
- **SP05:** route-level test that cross-user docs are never returned (boundary is correct but unguarded); `batch_group_id` present/absent.

**Frontend: effectively zero (the biggest structural gap).** 5 tests in 1 file (`groupSavedOutputs.test.ts`) cover ~2,500 lines of new React. Priority additions:

- **`SimplifyPage`** (632 lines, central): version in POST payload, `?version=` pre-select + URL strip, invalid `?version=` ignored, reset behavior, SSE result handling.
- **Sidebar** (SP05 Task 4 acceptance is entirely unverified): rename/delete/click-to-load on a batch-*nested* row, today-open-vs-prior-collapsed, date-header rendering, XSS-inert `batch_group_id`.
- **Grading components:** `grading.ts` selectors (null cases), `OutputGradingCard` (saved_id vs text fallback, error surface), `MethodGradingCards` (empty→null).
- **Batch:** `toBatchSelections`, `DatasetGroupRow`, `V1_2Page` SSE handlers.
- **`groupSavedOutputs`:** same-id-across-two-dates, empty-string id, adversarially-unsorted input (current fixture is pre-sorted, so the "preserve order, don't re-sort" contract isn't actually exercised).
- **`normalizeSimplifyOutput`:** SP01 Task 11 acceptance criterion (legacy/new/null) — never written.
- **CI:** add `npm run build` as a gate (would have caught the P0).

---

## Security assessment

**Overall: reasonably solid, one real gap (DoS) and several hardening items.**

- ✅ **Auth:** every touched route stays behind `@verify_firebase_token`; old per-version routes 404; version field is allowlist-validated server-side (rejects unknown/empty/list/non-string with 400).
- ✅ **Path traversal (SP04):** genuinely strong & layered — string converter (fix `eaee099`), enumerated-listing validation, `is_relative_to`, no path disclosure, tested incl. `%2F`.
- ✅ **Tenant isolation (SP05):** server-side `where('uid','==',user_id)` from the auth decorator (not client input) — `batch_group_id` can't leak across users.
- ✅ **XSS:** React JSX escaping; `batch_group_id` is server-generated.
- ✅ **Grading:** deterministic scoring (no LLM on user content) → **no prompt-injection / token-cost surface**.
- ❌ **DoS (SP04):** no batch size cap, no dataset-read byte cap, unbounded `"inputs":"all"` → authenticated cost/resource exhaustion. **Primary security fix.**
- ⚠️ **Re-grade DoS (SP03):** no size limit on `/simplify/grade` text-mode; no per-user rate/cost throttle.
- ⚠️ **Info leak (SP01):** v1-2 `session_id`→`user_id` fallback surfaces a Firebase UID in the response body / UI Request-ID line.
- ⚠️ **Test gap:** no route-level test asserting cross-user reads are blocked (boundary is correct but unguarded against regression).

---

## Logging & metrics assessment

**Inconsistent — the newest routes regressed on observability.** The codebase has `JunoLogger` + `JunoMetrics` conventions (`backend/utils/LOGGING.md`), but:

- ❌ **`batch.py`** — no logging/metrics at all (P1 #6).
- ❌ **`grading.py`** re-grade route — bare `logging`, no metrics (P2 #8).
- ❌ **Version dispatcher** — no selected-version / fallback metric (P2 #10).
- ⚠️ **Pre-existing (from `main`):** routes never call `log_request_end`, so `total_duration_ms` never reaches Cloud Logging — documented "slow request" dashboards/queries return nothing. Worth fixing while in here.
- ✅ Inner pipeline metrics (per-step timing, `step_durations_ms`) are wired and correct in the envelope for v1/v1-1/v1-2.

---

## Extensibility assessment

**Good bones, a few hardcoding hotspots.**

- ✅ **SP01 versioned model registry** is a sound pattern — adding a new model version is localized.
- ✅ **SP04 executor extraction** is clean and behavior-neutral (verified: full suite still 116 pass) — good reuse seam for batch.
- ⚠️ **SP03 grading methods** are hardcoded in **4 parallel lists** (compute dict, `build_grading` tuple, reasoning map, frontend labels) — adding a method touches all four. A single registry/strategy would fix it. Also `scoring_methods.py` vs existing `scoring.py` overlap — reconcile.
- ⚠️ **SP02 `SimplifyPage`** is a 632-line monolith — extract per-concern hooks/components before it grows further.
- ⚠️ **Config DRY:** adding a pipeline version still touches frontend `config.ts` + backend dispatch separately; acceptable but document the steps.

---

## Documentation discrepancies to reconcile

- **SP03:** SAM denominator is 28 in code vs 42 in PRD §4 table (code follows the PRD's own sketch; the table is internally inconsistent).
- **SP05:** batches default-expanded only for *today* vs PRD §8's literal "default expanded" — confirm intent.
- **Scope bleed across the branch:** the "01" file boundary is fuzzy — Grading (03), Input batch fields (04), and collapsed route URLs (02) all landed in files nominally owned by 01. Not a bug, but note it when reading the per-sub-project diffs.

---

## Recommended sequencing

1. **Unblock deploy:** P0 #1–#2 (frontend build + dead pages) — small, mechanical.
2. **Make batch safe:** P0 #3–#4 + P1 #6 (limits, failure isolation, observability) — highest-risk runtime path.
3. **Correctness:** P1 #5 (envelope Input) + P1 #7 (timezone).
4. **Harden + observe:** P2 #8–#13.
5. **Backfill tests** (backend gaps + a frontend test harness for `SimplifyPage`/Sidebar/grading) and **add `npm run build` to CI**.
