# 2026-06-27 — Athena Health Part 1: GCS Dataset Feature

Two sub-projects covering the full lifecycle of moving preset datasets to Google Cloud Storage and serving them on demand.

## Sub-Projects

| # | Name | PRD | Status | Depends On |
|---|------|-----|--------|------------|
| SP1 | GCS Dataset Infrastructure, Manifest & Backend | 01-gcs-infrastructure-manifest/PRD.md | Draft | (none) |
| SP2 | On-Demand Pipeline Download & Cleanup | 02-on-demand-pipeline-download/PRD.md | Draft | SP1 |

## Dependency Graph

```
SP1: GCS Infrastructure & Manifest
  └─► SP2: On-Demand Pipeline Download
```

SP1 must be deployed (and dataset files uploaded to GCS) before SP2 goes live.

## Locked Decisions

- GCS bucket: `juno-preset-data` (project: juno-medical-clarity, us-central1) — already created
- Service account: `firebase-adminsdk-fbsvc@juno-medical-clarity.iam.gserviceaccount.com` (objectAdmin granted)
- GCS path: `gs://juno-preset-data/preset-data/{group}/{input_id}/{filename}`
- Manifest: `preset-data/manifest.json` committed to git — full enumeration + 1 embedded sample per dataset
- Preview always served from manifest; no GCS calls for listing or preview
- New env var: `DATASETS_BUCKET_NAME=juno-preset-data`
- New `input_source_kind`: `"gcs_batch_dataset"` (backward compat with `"batch_dataset"`)
- Download injection point: `worker.py` execute_job(), not at HTTP request time

## Consolidated Open Questions

All `[OPEN]` items from both PRDs in one place.

### From SP1 (01-gcs-infrastructure-manifest/PRD.md)

- **Q7**: primock57-conversations input ID format — [RESOLVED: uses same day{N}-consultation{NN} format as primock57, confirmed by inspection of preset-data/primock57-conversations/ directory names]
- **Q8**: file_types uniformity across inputs — [RESOLVED: file types are uniform across all inputs within a group — confirmed]
- **Q12**: CI/test fixtures that read local preset-data dirs — [RESOLVED: no tests directly read from preset-data dirs; any that did were removed in this commit]

### From SP2 (02-on-demand-pipeline-download/PRD.md)

- download_dataset_inputs() signature — [RESOLVED: use (group, input_id, files, job_id) — per-input-id tuple, not a list of IDs]
- sweep_stale_dataset_dirs() call site — [RESOLVED: call once in the Flask app factory / startup hook, not per-request]
- PipelineErrorCode for GCS download failure — [RESOLVED: use INTERNAL_ERROR as top-level; add DATASET_DOWNLOAD_ERROR as a new ErrorCode enum value + _REGISTRY entry with details_template for context — no nested sub-error object, context via formatted details string]

## Manual Steps (cross-cutting, in order)

1. Run `generate_manifest.py` (SP1) — while local files still exist
2. Review and commit `preset-data/manifest.json`
3. Run `upload_to_gcs.py` (SP1)
4. Verify upload via GCS console
5. Delete local dataset dirs (SP1 `--delete-local` flag)
6. Deploy SP1 backend changes (preset_data.py + datasets.py)
7. Deploy SP2 backend changes (gcs_datasets.py + worker.py + batch_jobs.py)
8. Set `DATASETS_BUCKET_NAME=juno-preset-data` on Cloud Run worker service

## Next Step

Review both PRDs, resolve or triage open questions in the PRD files (mark each as `[RESOLVED: decision]` or `[DEFERRED]`), then run `dev-tasks` to generate TASKS.md for each sub-project.
