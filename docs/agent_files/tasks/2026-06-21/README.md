# Juno Feature Initiative — Sub-Project Index

**Date:** 2026-06-21
**Source proposal:** Firebase async jobs, error contract, UI polish, docs page, grading display
**Status:** PRDs authored. All open questions resolved. Ready for `dev-tasks`.

## Sub-projects & phasing

| # | Sub-project | Phase | Depends on |
|---|-------------|-------|------------|
| 01 | [Firebase Async Jobs](01-firebase-async-jobs/) | 2 | SP2 |
| 02 | [Error Contract](02-error-contract/) | 1 | — |
| 03 | [Ad Hoc UI Polish](03-ad-hoc-ui-polish/) | 3 | SP1 |
| 04 | [Docs Page](04-docs-page/) | 4 | SP3 |
| 05 | [Grading Display](05-grading-display/) | 1 | — |
| 06 | [Remove Preset Manifest](06-remove-preset-manifest/) | 1 | — |
| 07 | [Preset Data Parser — Primock57](07-preset-data-parser-primock57/) | 1 | — |
| 08 | [PresetDataCard UI Redesign](08-preset-data-card-redesign/) | 1 | — |
| 09 | [Force Vertex AI — Remove GEMINI_API_KEY](09-force-vertex-ai/) | 1 | — |
| 10 | [Firebase Auth → Identity Platform + Session Timeout](10-firebase-identity-platform/) | 1 | SP09 (BAA must be executed first) |

```
Phase 1 (parallel):  SP2 ──► SP1 ──► SP3 ──► SP4
                     SP5 (independent)
                     SP6 (independent)
                     SP7 (independent)
                     SP8 (independent)
                     SP9 (independent — do BEFORE SP10)
                     SP10 (after SP9 BAA step)
```

## Cross-cutting locked decisions

- **Cloud Run split**: same Docker image, two services via `JUNO_MODE` env var. `juno-api`: `--min-instances=1`, public, CRUD + job creation. `juno-worker`: `--min-instances=0`, `--max-instances=3`, internal-only, pipeline execution only.
- **Cloud Tasks**: juno-api enqueues tasks pointing at juno-worker `/internal/jobs/execute/<job_id>`. Payload: `job_id` + `batch_run_id` only (files resolved + uploaded to GCS by juno-api at submission time).
- **Firestore job lifecycle**: single doc in `care_plan_outputs`. `status`: `not_started → processing → completed | error`. `output_data` filled only on completion. `error_data` uses SP2's `ErrorDetail` shape.
- **SSE removed**: all progress via Firestore `onSnapshot`. Old `/care_plan` + `/care_plan/batch` SSE endpoints kept deprecated until SP3 window; removed then.
- **Batch parallelized**: each batch item = one Cloud Task. `batch_group_id` groups sidebar items. `batch_run_id` (new UUID per batch submission) propagates through Cloud Tasks → worker → every log entry and Firestore doc for correlated observability across machines.
- **URL**: `/carePlan/:id` (job_id = output_id). `CarePlanPage` (`/`) becomes submission-only; `CarePlanJobPage` (`/carePlan/:id`) owns processing + result view.
- **Error contract everywhere**: `ApiResponse` / `ErrorDetail` / `ErrorCode` registry replaces all `{"error": "..."}` patterns. SSE transition: `{"step":"error","error_data":{...}}` until SP1 removes SSE entirely.
- **Docs page URL slugs**: `smog`, `flesch-kincaid`, `dale-chall`, `pemat`, `sam`, `cdc-cci` at `/docs/grading/<slug>`. Shared contract between SP3 (links) and SP4 (pages).
- **SP1 → SP3 interface**: SP1 delivers `useJobStatuses(): { statuses: Map<string, JobStatus> }` hook at `frontend/src/api/useJobStatuses.ts`. SP3 consumes it via optional `processingIds` prop on Sidebar.
- **SP2 → SP3/SP5 interface**: SP2 delivers `ApiError` TypeScript type at `frontend/src/types/errors.ts`. SP3 and SP5 import from there.
- **Grading card**: `OutputGradingCard` props change to `{ grading: Grading; error: string | null }`. `runGrading` logic moves up to `CarePlanPage` as `handleRunGrading`.

## Owner decisions — all RESOLVED

| # | Question | Decision |
|---|---|---|
| SP1-1 | Frontend Firestore direct reads | RESOLVED: approved — frontend reads `care_plan_outputs` via `onSnapshot` |
| SP1-2 | Batch Firestore listener strategy | RESOLVED: N separate `onSnapshot` listeners, one per job_id. No composite index. |
| SP1-3 | Firestore security rules | RESOLVED: owner will deploy rules manually (see Manual Steps below) |
| SP2-1 | SSE transition shape | RESOLVED: `{"step":"error","error_data":{...}}` acceptable during SP1 window |
| SP4-1 | Markdown table handling | RESOLVED: rewrite starter content as bullet lists; no table renderer |
| SP5-1 | `combined` row position | RESOLVED: `combined` appears first (headline number) |
| SP5-2 | Grading error placement | RESOLVED: error shown inline below the Download/Run Grading button bar |

## SP09 + SP10 locked decisions

- **SP09**: `google-generativeai` dependency removed entirely. All three deploy workflows (`deploy-backend.yml`, `rollback-production.yml`, `ci.yml`) have `GEMINI_API_KEY` removed. `test_llm.py` fully rewritten for Vertex AI only path. No `config.py` changes needed.
- **SP10**: Identity Platform upgrade is GCP Console only — zero code changes to `firebase.ts`, `.env.production`, or `backend/utils/firebase.py`. Session timeout lives entirely in `AuthContext.tsx`. New `SessionTimeoutWarning.tsx` component. `VITE_SESSION_TIMEOUT_MS` env var optional (defaults 1800000ms). MFA and Firebase Analytics changes are DEFERRED (test app, no functionality removal).
- **SP09 manual step must precede SP10**: GCP BAA must be executed (SP09 §8) before enabling Identity Platform (SP10 §8), since both require the BAA to be active.

## SP06 + SP07 locked decisions

- **SP06**: `frontend/public/preset-data/manifest.json` is not git-tracked (gitignored) — disk-only delete. `frontend/scripts/` entire directory deleted via `git rm -r`. Build script becomes `tsc -b && vite build`.
- **SP07**: Parser is offline/one-time only — no runtime changes. No shared base class (YAGNI). Default overwrite behavior: skip existing files; `--overwrite` flag to replace. `input_id` = filename stem with `_` → `-` (e.g. `day1_consultation01` → `day1-consultation01`). Output format: `"Presenting Complaint: {x}\nNotes: {y}"`. Import path in tests: `from utils.preset_data_parser.primock57.parser import ...` (not `backend.utils...`).

## Manual steps required (human-only)

- **GCP: Cloud Tasks queue** — create `care-plan-jobs` queue in `juno-medical-clarity` project (GCP Console or `gcloud tasks queues create`).
- **GCP: Service account** — grant `roles/run.invoker` on `juno-worker` to the Cloud Tasks invoker service account.
- **GCP: Cloud Run** — add `juno-worker` service deployment with `JUNO_MODE=worker`, `--max-instances=3`, `--no-allow-unauthenticated`.
- **Firebase: Firestore security rules** — add rule allowing authenticated user to read/write their own `care_plan_outputs` docs.
- **Firebase: Firestore composite index** — only if SP1-2 resolves to query-based batch listener.
- **Scoring methods verification (SP3)** — manually verify actual `grade_breakdown` key names from `backend/utils/scoring_methods.py` match what the grading version detail page config lists.
- **SP07 — Download primock57**: `git clone https://github.com/Sydney-Informatics-Hub/primock57 /tmp/primock57`, then run `python -m backend.utils.preset_data_parser.primock57.parser --source /tmp/primock57`. Then `git add preset-data/primock57/ && git commit`.
- **SP07 — Do NOT commit the source download**: `.gitignore` rules added by SP07 exclude `primock57/` at any path level.
- **SP08 locked decisions**: `DatasetGroupRow.tsx` deleted; replaced by `PresetDataPanel.tsx` (internal to PresetDataCard folder, not barrel-exported). `expanded` default stays `false` (card collapsed by default). `activeGroup` initializes to `null`, set to `datasets[0].group` via `useEffect` on first load. Panel height `480px` — verify in browser. Preview placement inside `.preset-panel-files` is preferred; fallback is to move it outside + `max-height: 200px` on files section.
