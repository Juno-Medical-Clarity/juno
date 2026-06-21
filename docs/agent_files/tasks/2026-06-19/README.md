# Care Plan Backend Refactor — Sub-Project Index

**Date:** 2026-06-19
**Source proposal:** "Care Plan Backend Refactor" + "Logging AND OTHER improvement" (owner brief)
**Status:** PRDs + TASKS authored and **reconciled against owner resolutions (2026-06-20)**.
All open questions resolved; tasks regenerated from the amended PRDs. Ready to implement.

Each sub-project folder contains a `PRD.md` (problem → architecture → API/frontend impact →
testing → **Manual Intervention Required From You** → **Open Questions**) and a `TASKS.md`
(junior-dev-followable, with acceptance criteria + a "what requires you" summary).

## Sub-projects & phasing

| # | Sub-project | Phase | Depends on |
|---|-------------|-------|-----------|
| 01 | [Pydantic Model Migration](01-pydantic-model-migration/) | 0 (foundation) | — |
| 02 | [Route Consolidation & `care_plan` Rename](02-route-consolidation-care-plan-rename/) | 1 | 01 |
| 03 | [Utils Consolidation & Dead-Code Cleanup](03-utils-consolidation-cleanup/) | 1 | 01 (coord. imports w/ 02) |
| 04 | [Observability: Logging, Tracing, Metrics & Code Markers](04-observability-logging-metrics-codemarkers/) | 2 | 01, 02, 03 |
| 05 | [Frontend Alignment to `care_plan`](05-frontend-care-plan-alignment/) | 2 | 01, 02 |
| 06 | [Testing & CI Pipeline](06-testing-and-ci/) | 3 (locks final shapes) | 01–05 |

```
Phase 0:  01 ─┐
Phase 1:      ├─> 02 ─┬─> 04
              └─> 03 ─┘   └─> (05 in parallel, needs 02)
Phase 2:  04, 05
Phase 3:  06
```

## Cross-cutting decisions already locked (apply to all)

- Pydantic v2 everywhere; strict `extra="forbid"` (no third-party writers); `raw` kept **and saved**.
- No legacy concern: nothing is in production, barely any data — **no migrations**, tolerant reads only; breaking changes are fine; no dead-code/wrapper/alias retention.
- **Full** per-version model framework (base + version-dispatched subclasses); only v1.2 modeled today.
  Version is read from the **request body**; pipelines/serialization selected via a registry so adding v1_3 is a one-line append.
- Drop `appointment.schema.json`; Pydantic is the source of truth; LLM schema generated from the model.
- Each layer returns its own typed model (`pipeline.run()` returns the model); the **route** composes `CarePlanInternal` and serializes once (persistence derived from the same serialized dict).
- Single `care_plan` route; remove v1 & v1_1 pipelines/routes (**hard cut**, no `/simplify*` alias); keep v1_2 (named `v1_2`).
- **Inner wire key is `care_plan`** — hard flip now, **no `simplified_care_plan` alias**.
- `SimplifyOutput` → `CarePlanInternal`; `simplify` → `care_plan` everywhere (incl. Firestore collection + GCS prefix, renamed here, no data migration); `doc_type: 'appointment_note'` → `'care_plan'`; frontend `SimplifyOutput`/`SimplifyPage` **hard-renamed** (no aliases).
- `session_id` naming everywhere (`X-Session-Id`); **never** fall back to `user_id`.
- Full frontend alignment; adopt the code-marker metrics pattern (`/root/projects/code_marker_sample`); **delete `JunoMetrics`** (no shim). Dynamic version chooser deleted; static `VersionsPage` kept (extensible for v1_3+).

## Owner decisions — all RESOLVED (2026-06-20)

1. **`raw` persistence / PHI** — RESOLVED: remove `_without_raw()`; `raw` is kept & saved. No third-party
   writers, so strict models are fine; no legacy/PHI-migration concern (barely any data). (SP1)
2. **Inner envelope wire key** — RESOLVED: **hard flip to `care_plan` now, no alias.** (SP1, SP2, SP5)
3. **`/simplify*` cutover** — RESOLVED: **hard cut**, no alias/redirect. (SP2)
4. **`JunoMetrics`/`JunoLogger` disposition** — RESOLVED: **delete `JunoMetrics`** (no shim); SP4 owns
   call-site removal, SP3 deletes the module; `JunoLogger` kept. (SP3, SP4)
5. **Already-persisted old-shape docs** — RESOLVED: tolerant reads only, no migration. (SP1)
6. **Extra deletions** — RESOLVED: delete `utils/storage.py`, `utils/ocr.py`, `utils/gcs.py`, `utils/llm.py`
   per SP3; no transitional re-exports. (SP3)
7. **VersionsPage / version chooser fate** — RESOLVED: delete the **dynamic chooser**; keep a **static
   `VersionsPage`** structured for easy addition of v1_3+. (SP5)

## Sub-projects added 2026-06-21 (Phase 4–5 continuation)

| # | Sub-project | Phase | Depends on |
|---|-------------|-------|-----------|
| 07 | [Care Plan Model & Folder Restructure](07-care-plan-model-folder-restructure/) | 4 (foundation) | — |
| 08 | [Input Type Discrimination](08-input-type-discrimination/) | 4 | — |
| 09 | [Pipeline Prompts as Text Files](09-pipeline-prompts-text-files/) | 4 | 07 (path rename) |
| 10 | [Metrics Wiring](10-metrics-wiring/) | 4 | 07 (path rename) |
| 11 | [Show Original & Input Display Redesign](11-show-original-input-display/) | 5 | 08 |
| 12 | [Constants Consolidation](12-constants-consolidation/) | 4 | — |
| 13 | [Frontend Code Organization](13-frontend-code-organization/) | 4 | — |

```
Phase 4:  07 ──┬──> 09 (path rename)
               └──> 10 (path rename)
          08 ──────────────────────> 11 (Phase 5)
          12, 13  (fully independent)

Phase 5:  11
```

## Locked decisions added 2026-06-21

- `models/care_plan.py` keeps ONLY `class CarePlan(VersionedModel):`. All v1.2-specific types move to `care_plan/v1_2/models.py`.
- `CarePlanV1_2StructuredLLM` removed; LLM schema generated from `CarePlanV1_2` by excluding `terms`/`raw` via a helper.
- `before_score`/`after_score` removed from `CarePlanInternal`; grading encapsulates all score data.
- `is_legacy_shape` deleted (confirmed dead code — no external callers).
- `simplify/` folder renamed → `care_plan/`; `V1_2Pipeline` → `CarePlanV1_2Pipeline`.
- `_METHOD_REASONING` dict → `GradingMethodReason(str, Enum)`.
- `Grading` → `VersionedModel` subclass (with caution — see SP-07 §9.1 on old Firestore docs).
- `Input` → type-discriminated Pydantic union: `FileInput` / `TextInput` / `DocIdInput` / `BatchDatasetInput` each with `mode` as `Literal`. `BatchDatasetInput.mode = "batch_dataset"` (was `"text"` in old `from_batch_dataset`).
- `FileInput` gets `pdf_gcs_url: str | None = None` stub (populated by SP-11).
- All 3 LLM prompts extracted to `care_plan/v1_2/prompts/*.txt` with `{var}` placeholders; loaded at module init via `pathlib`.
- Metrics: keep Cloud Logging / Code Markers — no BigQuery. Wire `Markers.Grading.Run`. Add 12 dimensions: `source_kind`, `grading_enabled`, `is_batch` on pipeline; `file_count`, `file_types` on read_input; `term_count`, `substitution_count` on find_medical_terms; `before_composite`, `after_composite`, `grading_method_count` on grading.run. Pass `source_kind` and `is_batch` as new params to `run_care_plan_pipeline`.
- `pdf_gcs_url` moves inside `FileInput` (set in `_save` closure); top-level `input_pdf_gcs` Firestore field removed. `get_input_pdf_url` falls back to old field for tolerant reads.
- FE `SplitView` reworked: file input → signed URL + iframe; text/batch input → inline `<pre>` from `input.text`.
- Backend constants (`ALLOWED_EXTENSIONS`, `MAX_FILE_BYTES`, `MAX_FILE_COUNT`, `MAX_AGGREGATE_FILE_BYTES`, `STEPS`, `PIPELINE_VERSION_V1_2`, `MAX_BATCH_RUNS`) → `utils/constants.py`. Model version constants (`CARE_PLAN_VERSION` etc.) stay in `models/`.
- Frontend: new `src/constants.ts` with API path constants + helper functions. `batch.py` imports constants from `utils.constants` instead of `routes.care_plan`.
- Frontend tests → `src/tests/{api,components,utils}/`; `vi.mock()` paths updated too.
- CSS-paired components (Sidebar, SplitView, PresetDataCard) → own subfolders with `index.ts`; `src/components/index.ts` barrel added.

## Cross-cutting open questions (2026-06-21 batch)

- **SP-07 §9.1** `[OPEN]` — Promoting `Grading` to `VersionedModel` requires old Firestore docs (without `"version"`) to round-trip safely. Verify read path handles missing `version` before implementing.
- **SP-07 §9.2** `[OPEN]` — Full audit of `from models.care_plan import CarePlanV1_2` call sites needed before the move.
- **SP-08** `[OPEN]` — `mode: "batch_dataset"` wire change is a breaking change for any existing batch Firestore outputs. Human sign-off needed (but no legacy concern was locked already).
- **SP-10** `[OPEN]` — Should `batch.py` also pass `source_kind="batch_dataset"` (not just `is_batch=True`)? Recommended yes.
- **SP-11** `[OPEN]` — Re-serialization timing: mutate `FileInput.pdf_gcs_url` in-place before `envelope.to_dict()` vs. patch the `payload` dict afterward. Implementer to decide.
- **SP-11** `[DEFERRED]` — `doc_id` input mode Show Original (fetch original stored file) — out of scope.
- **SP-13** `[OPEN]` — `src/api/index.ts` barrel `export *` — verify no name collisions across api modules before landing.

## Manual (human-only) setup flagged across PRDs

- Pin `pydantic>=2` in `backend/requirements.txt` (SP1); add test deps (SP6).
- Cloud Console: create log-based metrics, build Metrics Explorer dashboard, save a Trace Explorer
  `session.id` filter, set `SERVICE_VERSION` on Cloud Run (code-default added in `telemetry.py`; the
  residual deploy step + a code-default both get recorded in `code.md` at implementation), verify
  `roles/cloudtrace.agent` (SP4).
- Ensure CORS `Access-Control-Expose-Headers` exposes `X-Session-Id` / `X-Trace-Id` (SP4/SP5;
  relevant to the active `fixing-cors` branch).
- Frontend: owner removes `VITE_DEFAULT_VERSION` (becomes a plain `'v1-2'` constant); the `.env*`
  cleanup is recorded in `code.md` at implementation (SP5).
- CI uses **Node 24** (clears the Node 20 deprecation warning) + Python 3.12; coverage is reporting-only;
  no live API calls / no integration tests / no emulator / no secrets for now (SP6).
- Branch protection / required status checks on `main`: **done** by owner (SP6).
