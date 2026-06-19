# Care Plan Backend Refactor — Sub-Project Index

**Date:** 2026-06-19
**Source proposal:** "Care Plan Backend Refactor" + "Logging AND OTHER improvement" (owner brief)
**Status:** PRDs + TASKS authored for all 6 sub-projects. Awaiting owner review.

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

- Pydantic v2 everywhere; strict `extra="forbid"`; `raw` kept **and saved**.
- **Full** per-version model framework (base + version-dispatched subclasses); only v1.2 modeled today.
- Drop `appointment.schema.json`; Pydantic is the source of truth; LLM schema generated from the model.
- Each layer returns its own typed model; the **route** composes `CarePlanInternal` and serializes once.
- Single `care_plan` route; remove v1 & v1_1 pipelines/routes; keep v1_2 (named `v1_2`).
- `SimplifyOutput` → `CarePlanInternal`; `simplify` → `care_plan` everywhere; `appointment_id` → `care_plan`.
- `session_id` naming everywhere (`X-Session-Id`); **never** fall back to `user_id`.
- Full frontend alignment; adopt the code-marker metrics pattern (`/root/projects/code_marker_sample`).

## Owner decisions needed before/within implementation (consolidated from the PRDs)

1. **`raw` persistence / PHI** — SP1 found `save_output._without_raw()` strips `raw` before persisting,
   which contradicts "raw kept & saved" and breaks the saved-id re-grade path. Removing the stripper means
   raw (incl. patient text) is persisted to Firestore. **Needs PHI/retention sign-off.** (SP1 §8/§9)
2. **Inner envelope wire key** — keep `simplified_care_plan` (aliased) in Phase 1 vs flip to `care_plan`.
   SP1/SP2/SP5 default to **keep + alias now, flip later**. Confirm. (SP1, SP2, SP5)
3. **`/simplify*` cutover** — hard cut vs one-release `/simplify*` → `/care_plan*` alias/redirect. (SP2)
4. **`JunoMetrics`/`JunoLogger` disposition** — SP4's code-marker sink supersedes the metrics call sites;
   decide delete vs deprecated shim, and which sub-project owns the removal (SP3 vs SP4). (SP3, SP4)
5. **Already-persisted old-shape docs** — recommended tolerant reads, no migration. Confirm. (SP1)
6. **Extra deletions beyond the brief** — SP3 also flags `utils/storage.py` (`StorageService`) as dead.
   Confirm deletion. (SP3)
7. **VersionsPage / version chooser fate** in the frontend once only v1-2 exists. (SP5)

## Manual (human-only) setup flagged across PRDs

- Pin `pydantic>=2` in `backend/requirements.txt` (SP1); add `requirements-dev.txt` for test deps (SP6).
- Cloud Console: create log-based metrics, build Metrics Explorer dashboard, save a Trace Explorer
  `session.id` filter, set `SERVICE_VERSION` on Cloud Run, verify `roles/cloudtrace.agent` (SP4).
- Ensure CORS `Access-Control-Expose-Headers` exposes `X-Session-Id` / `X-Trace-Id` (SP4/SP5;
  relevant to the active `fixing-cors` branch).
- Enable branch protection / required status checks on `main` so CI gates merges (SP6).
