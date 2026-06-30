# Juno Backend Cleanup — PRD Index (2026-06-29)

## Overview

This directory contains a design-only decomposition (PRDs only; tasks generated later via `/dev-tasks`) of a deep backend cleanup plus a light frontend pass for Juno. Eleven top cleanup themes were condensed into 10 sub-projects across 4 sequential phases. The initiative unifies error handling, restructures models and constants, moves the Athena client to a proper services layer, introduces a typed JobDoc, hardens batch/job creation, consolidates pipeline orchestration with SSE retirement, performs a broad error/metrics/dedup sweep, runs a dead-code purge with a linter baseline, and retires frontend legacy shims.

---

## Locked Decisions (apply across all SPs)

- `models/base.py` STAYS at top-level `models/base.py` (shared base for all models).
- Athena typed models (`athena.py`) are WIRED IN (no raw-dict parsing) and moved to `models/external_api/`; `athena_manifest.py` is DELETED as dead code; the `manifest/` subfolder is NOT created (its only occupant was dead).
- The live Athena HTTP client moves to a NEW `services/external_api/` package; its data models and `AthenaAPIError` live under `models/external_api/`.
- Care-plan orchestration (detect→simplify→clarify→structure→glossary) is OWNED by `care_plan/v1_2/pipeline.py` (new `run_streaming` + `run()`); `routes/care_plan.py` becomes a thin SSE/markers/grading adapter.
- `models/errors.py` is kept as the pydantic wire/serialization contract (not a duplicate).

---

## Sub-Projects

| SP # | Name | Phase | Scope | Depends On |
|------|------|-------|-------|------------|
| SP01 | Unified Error System | 1 | Merge 4 error files → 1 mappings (`errors/codes.py`) + 1 definitions (`errors/exceptions.py`) package; fix latent worker.py KeyError; re-parent scattered exceptions under `JunoError`. | none |
| SP02 | Constants + Backend-Root Layout | 1 | Namespaced `Constants` nested classes; fold scattered constants and `AthenaSourceKind`; delete dead `config.py`; move `logging_config.py`/`telemetry.py` → `observability/`. | none |
| SP03 | Models Folder Reorg | 1 | Create `models/care_plan/` and `models/external_api/`; fold `ResolvedInput` into `models/input.py`; delete `athena_manifest.py`. | SP01 |
| SP04 | Athena External API | 2 | Move Athena client → `services/external_api/`; wire typed responses; add `Markers.Athena` leaves; delete `fetch_items_with_rate_limit`. | SP01, SP02, SP03 |
| SP05 | JobDoc Model | 2 | Introduce `models/job.py` `JobDoc` with `for_gcs_dataset`/`for_athena`/`for_single` factories; migrate worker read-path to `from_firestore()`. | SP02, SP03 |
| SP06 | Batch + Job-Creation Hardening | 3 | Pydantic request models with discriminated `Selection` union; shared grading validator; whole-handler try/except; metrics; `JobDoc` factory wiring; rename `batch.py` → `batch_utils.py`; delete 5 dead helpers. | SP01, SP02, SP05 |
| SP07 | Pipeline Consolidation + SSE Retirement | 3 | Pipeline owns orchestration via `run_streaming`; route becomes thin adapter; retire dead SSE 410 stub routes and worker SSE re-parse. | SP01, SP05 (coordinate SP06) |
| SP08 | Error-Handling + Metrics + Dedup Sweep | 3 | try/except on all unguarded routes and firebase wrappers; expand Markers registry; extract 5 dedup helpers; pydantic request bodies; remove legacy `saved_outputs` fallback. | SP01, SP02, SP05 (coordinate SP04, SP06, SP07) |
| SP09 | Dead-Code Purge + Linter | 4 | Add ruff; residual dead-code sweep (must run last after all backend SPs). | SP01–SP08 |
| SP10 | Frontend Legacy-Shim Retirement | 4 | Retire legacy error/output shims; wire dead `processingIds` stub; gate `normalizeOutput.ts` deletion on Q1 resolution. | SP01, SP07 |

---

## Dependency Graph

```
Phase 1 (Foundation)
  SP01 ──┐
  SP02 ──┤
  SP03 ◄─┘ (needs SP01)

Phase 2 (Service + Model layer)
  SP04 ◄── SP01, SP02, SP03
  SP05 ◄── SP02, SP03

Phase 3 (Route hardening + cleanup) — coordinate SP06/SP07/SP08 merges
  SP06 ◄── SP01, SP02, SP05
  SP07 ◄── SP01, SP05  [sequence after SP06 to avoid batch.py conflict]
  SP08 ◄── SP01, SP02, SP05  [coordinate SP04, SP06, SP07 merge order]

Phase 4 (Final sweep)
  SP09 ◄── SP01, SP02, SP03, SP04, SP05, SP06, SP07, SP08
  SP10 ◄── SP01, SP07
```

---

## Cross-SP Sequencing & Coordination Notes

- **SP01 → SP04**: SP01 must define `ATHENA_API_ERROR`, `ATHENA_AUTH_FAILED`, and `ATHENA_RATE_LIMIT_ERROR` error codes, and the final import path for `JunoError` (moving from `utils.pipeline_errors.JunoError` to `errors/exceptions.py`), before SP04 wires `AthenaAPIError` inheritance.
- **SP02 → SP09**: SP02 deletes `config.py`, which renders `Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR` and `_FALLBACK` dead. SP09 deletes them only AFTER SP02 lands. Confirm no SP03–SP08 re-introduces a reference.
- **SP02 backward-compat shims**: SP02 introduces transitional flat `Constants` shims with `# TODO(SPxx): remove after migration` comments. SP09 must remove them once all downstream SPs have migrated. Confirm whether these shims are acceptable given any "no-legacy" coding rules in the team charter.
- **Markers registry ownership**: SP08 owns the `markers.py` file and adds `Worker`, `SavedOutputs`, `Batch`, `Firestore`, and `Athena` namespaces. SP04 wires the `Markers.Athena` leaf (or adds it if SP08 has not landed). SP06 wires the `Markers.Batch.CreateJobs` leaf. If SP04 lands before SP08, SP04 must add the Athena leaf itself; SP08 reconciles on merge. Decide WHO defines the `Batch` namespace leaf before SP06 and SP08 are assigned to implementers.
- **SP06 ⇄ SP07 on `batch.py`**: SP06 renames `batch.py` → `batch_utils.py`; SP07 deletes the `care_plan_batch_sse_deprecated` 410 stub that lives in that file. Sequence SP06 (rename) then SP07 (deletion in the renamed file), or coordinate in the same PR.
- **SP07 → SP09 on `RESULT_SENTINEL`**: SP07 retires all usage of `RESULT_SENTINEL`; SP09 deletes the constant itself from `utils/constants.py`. SP09 must confirm zero references post-SP07 before deletion.
- **Firestore wire-shape stability (SP05/SP07/SP08/SP10)**: SP05 sets `JobDoc` field names (via pydantic aliases); SP07 finalises output shape; SP08 removes the legacy `saved_outputs` / `input_pdf_gcs` fallback. SP10 depends on the stable output shape from SP07 and the error shape from SP01. Coordinate SP10's gated deletions so they land after BOTH SP01 and SP07 are deployed.

---

## Consolidated Open Questions (need human resolution before/within dev-tasks)

### SP01 — Unified Error System
- **Q4** [OPEN]: Should `UNKNOWN_ERROR` and `INTERNAL_ERROR` be merged into a single code? They share `http_status=500` but serve different contexts (pipeline crash vs. HTTP route handler). Recommendation: keep both with explanatory comments.
- **Q5** [OPEN]: Should `EMPTY_DOCUMENT` and `INPUT_EMPTY` be merged? Same user symptom but different trigger contexts (post-parse vs. pre-pipeline). Recommendation: keep both with comments.
- **Q6** [OPEN]: Package name — `backend/errors/` vs. `backend/error/` vs. `backend/core/errors/`. Recommendation: `backend/errors/`.
- **Q8** [OPEN]: Should `AthenaAPIError`'s HTTP-status-code-to-ErrorCode mapping live in `AthenaAPIError.__init__` (self-identifying at raise time) or in `_classify_exc` (centralised)? Recommendation: `__init__` approach.

### SP02 — Constants + Backend-Root Layout
- **Q2** [OPEN]: Should a config accessor (e.g. `get_env(Constants.EnvVars.GCS_BUCKET)`) be added to centralise `os.environ.get` calls, or leave inline reads of `Constants.EnvVars.*`? Deferred to SP08 or a dedicated config sub-project.

### SP03 — Models Folder Reorg
- **Q1** [OPEN]: Athena models in `models/external_api/athena_models.py` use `extra="allow"`. Should SP03 tighten to `extra="forbid"` during relocation, or defer to SP04? Recommendation: defer to SP04 (when models are actually exercised in tests).
- **Q2** [OPEN]: `backend/care_plan/` pipeline package and `backend/models/care_plan/` models subfolder share the `care_plan` name segment. Acceptable, or rename to `models/care_plan_models/` or `models/plans/`? Recommendation: keep `models/care_plan/` with clear docstring guidance.
- **Q3** [OPEN]: `ResolvedInput.combined_pdf_bytes` is `bytes` (not JSON-native). Should it be excluded from the pydantic model? Recommendation: keep as-is; add docstring warning; re-evaluate only if `ResolvedInput` is ever serialised to Firestore.

### SP04 — Athena External API
- **Q4** [OPEN]: Tighten `extra="allow"` → `extra="forbid"` on Athena response models (`AthenaTokenResponse`, `AthenaEncounterSummaryResponse`, `AthenaClinicalDocumentContentResponse`) now, or defer to a follow-up? Tightening catches undocumented Athena API fields earlier but may break integration tests that replay saved responses. Recommendation: defer; keep `extra="allow"` for now.

### SP05 — JobDoc Model
- **Q1** [OPEN]: Should `input_source_kind` in `JobDoc` use `str` now with a `# TODO(SP02)` comment, or block SP05 on SP02 to get `AthenaSourceKind`? Recommendation: merge SP02 first; if forced earlier, use `str`.
- **Q2** [OPEN]: Should `output_data` and `error_data` fields in `JobDoc` be strongly typed sub-models (`CarePlanInternal` / `ErrorDetail`) or remain `Optional[dict[str, Any]]`? Recommendation: keep as `dict` to avoid re-validation overhead; revisit in a later SP.
- **Q3** [OPEN]: Should `JobDoc.from_firestore()` use `extra="forbid"` (surfaces undeclared fields as bugs) or `extra="ignore"` (more lenient for fields manually written to Firestore)? Recommendation: `extra="forbid"` with a try/except in the worker that logs and falls back on failure.
- **Q4** [OPEN]: Firestore serialisation — should `Optional` fields be absent (`exclude_none=True`) or written as `null` (`exclude_none=False`)? Affects whether SP10 frontend uses `T | undefined` vs. `T | null`. Current default writes nulls. Recommendation: switch to `exclude_none=True` for cleaner Firestore docs; requires SP10 coordination.

### SP06 — Batch + Job-Creation Hardening
- **Q2** [OPEN]: Should `_grading_enabled_from_request` in `care_plan.py` be deleted by SP06, or left for SP07/SP08? Preferred: SP06 removes the import from `care_plan_jobs.py`, leaves the function with a `# TODO(SP07): remove` comment.
- **Q3** [OPEN]: GCS `dataset` selections currently sent by the frontend lack an `input_source_kind` field, which the discriminated union requires. Options: (a) add `input_source_kind: "gcs_dataset"` to frontend GCS selections (breaking change); (b) treat GCS as the discriminated-union fallback. **Confirm with frontend before implementation.**
- **Q5** [OPEN]: Should `Markers.Batch` dimensions include a derived `source_kind` string (e.g., `"mixed"`, `"all_athena"`, `"all_gcs"`) in addition to raw `athena_count`/`gcs_count`? Recommendation: raw counts are sufficient for SP06; add derived dimension in SP08 if needed.

### SP07 — Pipeline Consolidation + SSE Retirement
- **Q3** [OPEN]: Where should `StepEvent`, `PipelineRunResult`, `PipelineStepError`, `AdapterStepEvent`, `AdapterResult`, `AdapterError` be defined — in `pipeline.py`, a new `care_plan/events.py`, or `routes/care_plan.py`? Preferred: pipeline events in `pipeline.py`, adapter events in `routes/care_plan.py`; evaluate a separate `care_plan/events.py` at implementation time if circular-import issues arise.
- **Q5** [OPEN]: Will deleting the 410-stub routes for `POST /care_plan` and `POST /care_plan/batch` cause any monitoring alerts or break any third-party integration? Confirm with SP10 that no frontend code calls these routes.
- **Q6** [OPEN]: Does any Firestore job doc in production still carry `input_source_kind == "batch_dataset"` (the legacy `_INPUT_TYPE_MAP` key in `worker.py:36`)? If no live jobs use it, remove in SP08/SP09 sweep.

### SP08 — Error-Handling + Metrics + Dedup Sweep
- **Q5** [OPEN]: Does removing the `input_pdf_gcs` legacy fallback (from `delete_saved` and `get_input_pdf_url`) affect any live production user documents that have `input_pdf_gcs` at the top level and lack `output_data.input.pdf_gcs_url`? SP10 must audit production Firestore before §4l lands; if old-shape docs exist, either defer §4l or run a Firestore migration script first.

### SP09 — Dead-Code Purge + Linter
- **Q1** [OPEN]: Do `InputFile`, `FileInput`, or `BatchDatasetInput` survive after SP05 introduces `JobDoc`? Grep `backend/models/job.py` post-SP05 merge before deleting these classes.
- **Q2** [OPEN]: Should `Constants.DATASETS_BUCKET_NAME_ENV_VAR` be deleted (currently unused; raw string used directly in `gcs_datasets.py`)? Recommendation: delete once zero-reference is confirmed.
- **Q6** [OPEN]: Is the `all_blueprints = API_BLUEPRINTS` alias at the bottom of `routes/__init__.py` referenced anywhere? Run `grep -rn "all_blueprints" backend/ --include="*.py"` post-SP08 merge; if zero hits, delete.

### SP10 — Frontend Legacy-Shim Retirement
- **Q1** [OPEN]: Are there any `care_plan_outputs` documents in production Firestore that lack the `care_plan` top-level key (i.e., the legacy flat shape that `isLegacyShape()` detects)? **Backend team (SP05/SP07) must answer before `normalizeOutput.ts` can be deleted.** If yes, a Firestore data migration is required first.
- **Q2** [OPEN]: Should the `CarePlanJobPage.tsx` component split (§4f) be included in SP10 or deferred to a follow-on frontend SP?

---

## Consolidated Manual Steps

- **SP01**: No manual steps. Watch: in-flight Athena-path jobs queued during deploy will now write a proper `error_data` dict to Firestore on failure; previously they did not. Old terminal-state jobs are unaffected.
- **SP02**: Communicate to the team: any open branch importing `from logging_config import ...` or `from telemetry import ...` will get a merge conflict. The fix is a one-line import update per occurrence.
- **SP03**: No manual steps. Recommended commit sequence (6 atomic commits) documented in §8 of the PRD.
- **SP04**: No manual steps. The `athena_client` singleton is recreated at import time from the new path; no warm-instance migration needed.
- **SP05**: No manual steps.
- **SP06**: No manual steps. The `batch.py` → `batch_utils.py` rename is a file-system rename with import updates only.
- **SP07**: No manual steps. After 410-stub deletion, any monitoring alert on 404s for `POST /care_plan` or `POST /care_plan/batch` should be suppressed or removed — those endpoints have been retired.
- **SP08**: No manual steps. The legacy `input_pdf_gcs` fallback removal is backward-incompatible for old-schema Firestore documents (they return 404 for the PDF-URL endpoint going forward). Gate this on Q5 resolution.
- **SP09** (run order is critical — must land after all SP01–SP08 branches are merged):
  1. Merge SP01–SP08 (or confirm their feature branches are present on the working branch).
  2. Re-run every grep in SP09 §4B — do not rely on pre-merge checks; upstream SPs may introduce new references to symbols that looked dead before.
  3. Install ruff and record the baseline output before touching any code.
  4. Apply deletion groups in order B1 → B2 → B3 → B4 → B5 → B6 → B7; run `pytest` after each step.
  5. Run ruff after each deletion step — it may surface secondary unused imports that became dead after the primary deletion.
  6. Update `tests/models/test_input_metrics.py` in the same commit as group B4.
  7. Install the pre-commit hook and verify it runs clean; also document `ruff check` in CI/cloudbuild.
  8. Commit each deletion group as a separate logical commit (or one omnibus commit with a clear message).
- **SP10**: If Q1 resolves as "old-shape docs exist," a Firestore data migration must be run (by the backend team, coordinated with SP05/SP07) before `normalizeOutput.ts` can be deleted. Implement SP10 in two commits: (a) no-dependency cleanups (`processingIds`, `logger.ts`) first; (b) SP01/SP07-gated deletions after both SPs are deployed.

---

## Next Step

Reviewer resolves or triages each Open Question IN the relevant PRD's §9 (mark `[RESOLVED: decision]` or `[DEFERRED]`), then runs `/dev-tasks` to generate `TASKS.md` per approved PRD. Tasks are NOT generated yet.
