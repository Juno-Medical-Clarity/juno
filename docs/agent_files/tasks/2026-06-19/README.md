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
