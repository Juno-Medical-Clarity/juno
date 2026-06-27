# 2026-06-27 — Athena Health Part 1: GCS Dataset Feature

Five sub-projects covering the full lifecycle of moving preset datasets to Google Cloud Storage, serving them on demand, integrating live Athena Health EHR data, and enforcing typed manifest models end-to-end.

## Sub-Projects

| # | Name | PRD | Status | Depends On |
|---|------|-----|--------|------------|
| SP1 | GCS Dataset Infrastructure, Manifest & Backend | 01-gcs-infrastructure-manifest/PRD.md | Draft | (none) |
| SP2 | On-Demand Pipeline Download & Cleanup | 02-on-demand-pipeline-download/PRD.md | Draft | SP1 |
| SP3 | Athena Health Integration | 03-athena-health-integration/PRD.md | Draft | SP2 |
| SP4 | Unified Error Control Model | 04-error-control-model/PRD.md | Draft | SP2 (uses error codes from SP2 contract) |
| SP5 | Athena Manifest Models | 05-manifest-models/PRD.md | Draft | SP3 (after SP3 Tasks 1, 2, 6 — manifest files on disk, datasets route) |

## Investigation Artifacts
- [Error Handling Investigation](error-handling-investigation.md) — 2026-06-27 audit of error handling inconsistencies that motivated SP4

## Dependency Graph

```
SP1: GCS Infrastructure & Manifest
  └─► SP2: On-Demand Pipeline Download
        └─► SP3: Athena Health Integration
        │     └─► SP5: Athena Manifest Models (after SP3 Tasks 1, 2, 6)
        └─► SP4: Unified Error Control Model (parallel with SP3; adds Athena codes SP3 will reference)
```

SP1 must be deployed (and dataset files uploaded to GCS) before SP2 goes live.
SP3 can be developed in parallel with SP1/SP2 but requires SP2's worker pattern to be deployed before SP3 ships (the `execute_job()` dispatch block in worker.py requires SP2's `gcs_batch_dataset` branch structure already present).
SP5 depends on SP3 Tasks 1 and 2 (manifest JSON files committed to `backend/data/`) and SP3 Task 6 (the `GET /care_plan/datasets` route returning `athena_sources`); it can be developed concurrently with later SP3 tasks.

## Locked Decisions

### SP1 / SP2

- GCS bucket: `juno-preset-data` (project: juno-medical-clarity, us-central1) — already created
- Service account: `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com` (objectAdmin granted)
- GCS path: `gs://juno-preset-data/preset-data/{group}/{input_id}/{filename}`
- Manifest: `preset-data/manifest.json` committed to git — full enumeration + 1 embedded sample per dataset
- Preview always served from manifest; no GCS calls for listing or preview
- New env var: `DATASETS_BUCKET_NAME=juno-preset-data`
- New `input_source_kind`: `"gcs_batch_dataset"` (backward compat with `"batch_dataset"`)
- Download injection point: `worker.py` execute_job(), not at HTTP request time

### SP3 (Athena Health Integration)

- **Worker-time fetching** — Athena API calls happen inside `execute_job()`, matching the SP2 GCS pattern
- **New `input_source_kind` values**: `"athena_encounter"` and `"athena_clinical_doc"`
- **New Firestore fields per job**: `athena_practice_id`, `athena_patient_id`, `athena_encounter_id` (encounters), `athena_document_id` (clinical docs), `athena_api_path`
- **OAuth2 token cache**: module-level `AthenaClient` singleton; cache `(access_token, expires_at)`; refresh 20s before 300s expiry
- **Rate limiting**: `ThreadPoolExecutor(max_workers=2)`, `time.sleep(30)` between batches; skip after last batch
- **Manifest files**: `backend/data/athena-encounters-manifest.json` (4 entries) and `backend/data/athena-clinicaldocs-manifest.json` (100 entries) — committed to git
- **`GET /care_plan/datasets`** extended to return `athena_sources` array alongside existing `datasets`
- **Preview mode**: one entry per tab has `is_preview: true` and embedded `preview_content` in manifest; shown in `AthenaPresetPanel` Preview mode without an API call in the UI (live fetch still happens at worker execution time)
- **`additional_info: list[str]`** added to `CarePlanV1_2` (backend) and `CarePlanContent` (frontend)
- **"Data Sources" card**: rendered at end of `CarePlanView` (after Glossary card); visible only when `additional_info` is non-empty
- **HTML stripping**: stdlib `html.unescape()` + `re.sub(r'<[^>]+>', '', ...)` (no BeautifulSoup dependency)
- **Sandbox**: practiceId=195900; encounter patients 60183 (Gary) and 60178 (Donna); clinical doc patients 60178–60182
- **Push to Athena deferred** — `POST /v1/{practiceId}/patients/{patientId}/documents/clinicaldocument` is out of scope for SP3

## Consolidated Open Questions

All `[OPEN]` items from all PRDs in one place.

### From SP1 (01-gcs-infrastructure-manifest/PRD.md)

- **Q7**: primock57-conversations input ID format — [RESOLVED: uses same day{N}-consultation{NN} format as primock57, confirmed by inspection of preset-data/primock57-conversations/ directory names]
- **Q8**: file_types uniformity across inputs — [RESOLVED: file types are uniform across all inputs within a group — confirmed]
- **Q12**: CI/test fixtures that read local preset-data dirs — [RESOLVED: no tests directly read from preset-data dirs; any that did were removed in this commit]

### From SP2 (02-on-demand-pipeline-download/PRD.md)

- download_dataset_inputs() signature — [RESOLVED: use (group, input_id, files, job_id) — per-input-id tuple, not a list of IDs]
- sweep_stale_dataset_dirs() call site — [RESOLVED: call once in the Flask app factory / startup hook, not per-request]
- PipelineErrorCode for GCS download failure — [RESOLVED: use INTERNAL_ERROR as top-level; add DATASET_DOWNLOAD_ERROR as a new ErrorCode enum value + _REGISTRY entry with details_template for context — no nested sub-error object, context via formatted details string]

### From SP3 (03-athena-health-integration/PRD.md)

All questions resolved — see PRD §9 for full resolutions:
- Fetch at worker time vs. request time — [RESOLVED: worker time, matching SP2 pattern]
- Rate limiting strategy — [RESOLVED: batch_size=2, sleep=30s, skip after last batch]
- Token caching — [RESOLVED: module-level singleton, refresh 20s before expiry]
- Preview entry job execution — [RESOLVED: live API call at worker time; preview_content is UI-only]
- Push to Athena — [DEFERRED: SP4 or later]
- HTML stripping library — [RESOLVED: stdlib html + re, no BeautifulSoup]
- Error code separation — [RESOLVED: ATHENA_AUTH_FAILED / ATHENA_API_ERROR / ATHENA_RATE_LIMIT_ERROR]
- additional_info for multi-item batch — [RESOLVED: one api_path per job doc, one path per care plan result]
- datasets API key naming — [RESOLVED: existing "datasets" key preserved; new "athena_sources" key added]

## Manual Steps (cross-cutting, in order)

### SP1 / SP2 steps
1. Run `generate_manifest.py` (SP1) — while local files still exist
2. Review and commit `preset-data/manifest.json`
3. Run `upload_to_gcs.py` (SP1)
4. Verify upload via GCS console
5. Delete local dataset dirs (SP1 `--delete-local` flag)
6. Deploy SP1 backend changes (preset_data.py + datasets.py)
7. Deploy SP2 backend changes (gcs_datasets.py + worker.py + batch_jobs.py)
8. Set `DATASETS_BUCKET_NAME=juno-preset-data` on Cloud Run worker service

### SP3 steps
9. Generate `preview_content` for encounters manifest — run `AthenaClient._strip_html()` on `docs/agent_files/athena-bruno/EncounterSummaries/sample_p60183_e62021_02.json`'s `summaryhtml` field; paste into `backend/data/athena-encounters-manifest.json`
10. Generate `preview_content` for clinical docs manifest — paste first 2000 chars of `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/60178_204552/document.txt` into `backend/data/athena-clinicaldocs-manifest.json`
11. Generate full `athena-clinicaldocs-manifest.json` by enumerating all 100 entries in `ClinicalDocumentContentAll/`
12. Add `ATHENA_HEALTH_CLIENT_ID` and `ATHENA_HEALTH_CLIENT_SECRET` to `backend/.env` (local) and Cloud Run worker env (production)
13. Deploy SP3 backend changes (athena_client.py + updated worker.py + batch_jobs.py + datasets.py + constants.py + error_codes.py + v1_2.py)
14. Deploy SP3 frontend changes (AthenaPresetPanel.tsx + updated PresetDataCard.tsx + CarePlanView.tsx + carePlan.ts)
15. Verify `GET /care_plan/datasets` returns `athena_sources` with correct entry counts
16. Run a single-item encounter job; confirm "Data Sources" card appears in care plan result

## Next Step

Review SP3 PRD, then run `dev-tasks` to generate TASKS.md for SP3. SP1 and SP2 TASKS.md can be generated concurrently.
