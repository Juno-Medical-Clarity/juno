# Spec: SP3 — Athena Health Integration Design

**Date:** 2026-06-27
**Branch:** `athena_health_part1`
**Author:** Tejit Pabari
**Status:** Design complete — ready for task generation

---

## 1. Problem Statement and Motivation

Juno currently processes medical documents from two sources: user-uploaded files and pre-staged GCS datasets. Both paths require the clinician or researcher to provide a file or to pre-stage data into GCS before a care plan can be generated.

The Athena Health integration adds a third path: fetching live clinical records directly from the Athena Health EHR sandbox at job execution time. This opens two rich document types:

- **Encounter summaries** — HTML-rendered clinical notes from completed patient encounters (vitals, medications, assessment/plan, vaccines, problems). Athena returns these as `{"summaryhtml": "<html>..."}`.
- **Clinical documents (SOAP notes)** — Pre-authored clinical documentation stored in Athena's document repository, returned as `{"documentdata": "<text>"}`.

The sandbox makes 100 SOAP notes and 4 encounter summaries available for the Juno demo and testing workflow. Real production deployment would extend these counts as the EHR is populated.

**Why fetch at worker time?** The SP2 pattern (GCS download in the worker) establishes the precedent: keep the HTTP request layer thin and delegate all I/O to the worker. The `BATCH_ITEM_INTERNAL_DEADLINE_S = 870s` gives the worker ample time to call the Athena API (typically sub-second per document) and still run the pipeline. Fetching at HTTP request time would require a longer-lived client connection and complicate error attribution.

---

## 2. Architecture Overview

### Data Flow: Encounter submission

```
[Browser]
   │  User opens PresetDataCard → Athena Encounters tab
   │  Clicks on an entry (or Submit in Preview mode)
   │
   ▼
[Frontend: AthenaPresetPanel]
   │  buildAthenaSelection(entry) → AthenaSelection object
   │  calls createBatchJobs({ selections: [AthenaSelection] })
   │
   ▼
[POST /care_plan/batch/jobs]
   │  Validates request body
   │  Creates Firestore job doc with:
   │    input_source_kind: "athena_encounter"
   │    athena_practice_id, athena_patient_id, athena_encounter_id
   │    athena_api_path: "/v1/195900/chart/encounters/{id}/summary"
   │  Enqueues Cloud Task → returns { batch_run_id, job_ids }
   │
   ▼
[Cloud Tasks → POST /internal/jobs/execute/{job_id}]
   │  worker.py reads job doc
   │  source_kind == "athena_encounter"
   │  calls athena_client.fetch_encounter_summary(practice_id, encounter_id)
   │    → GET /v1/195900/chart/encounters/{id}/summary
   │    ← { "summaryhtml": "<html>...</html>" }
   │  strips HTML → plain text
   │  sets additional_info = [athena_api_path]
   │  passes text to run_care_plan_pipeline(...)
   │
   ▼
[Pipeline → Firestore]
   │  care_plan dict + additional_info stored in output_data
   │
   ▼
[Frontend: CarePlanJobPage → CarePlanView]
   │  renders care plan sections
   │  renders "Data Sources" card at bottom (if additional_info non-empty)
```

### Data Flow: Clinical document submission

```
Identical flow above, except:
  source_kind: "athena_clinical_doc"
  athena_document_id added to job doc
  api_path: "/v1/195900/patients/{patient_id}/documents/clinicaldocument/{document_id}"
  worker calls: athena_client.fetch_clinical_doc(practice_id, patient_id, document_id)
    → GET api_path
    ← { "documentdata": "<plain text>" }
  text used directly (no HTML stripping needed)
```

### Data Flow: GET /care_plan/datasets

```
[Browser]
  → GET /care_plan/datasets
  ← {
      "datasets": [...existing groups...],  // from manifest.json
      "athena_sources": [
        { encounters manifest },
        { clinical docs manifest }
      ]
    }
```

---

## 3. Component Breakdown

### New files

| File | Purpose |
|------|---------|
| `backend/utils/athena_client.py` | OAuth2 client singleton, token cache, API fetch methods, rate-limited batch fetcher |
| `backend/data/athena-encounters-manifest.json` | 4 real encounter entries from Athena sandbox |
| `backend/data/athena-clinicaldocs-manifest.json` | 100 SOAP note entries from Athena sandbox |
| `frontend/src/components/PresetDataCard/AthenaPresetPanel.tsx` | Two-mode (Preview / List) UI for Athena sources |

### Modified files

| File | Change summary |
|------|----------------|
| `backend/utils/constants.py` | Add Athena API env var names, base URL, practice ID constant |
| `backend/utils/error_codes.py` | Add `ATHENA_AUTH_FAILED`, `ATHENA_API_ERROR`, `ATHENA_RATE_LIMIT_ERROR` |
| `backend/routes/datasets.py` | Load and return `athena_sources` array from manifest files |
| `backend/routes/batch_jobs.py` | Accept and store `athena_*` fields from request body |
| `backend/routes/worker.py` | Dispatch `athena_encounter` and `athena_clinical_doc` source kinds; populate `additional_info` |
| `backend/models/care_plan_versions/v1_2.py` | Add `additional_info: list[str]` field |
| `backend/.env.example` | Add `ATHENA_HEALTH_CLIENT_ID` and `ATHENA_HEALTH_CLIENT_SECRET` |
| `frontend/src/types/carePlan.ts` | Add `additional_info?: string[]` to `CarePlanContent` |
| `frontend/src/components/CarePlanView.tsx` | Render "Data Sources" `ResultCard` at bottom when `additional_info` is non-empty |
| `frontend/src/components/PresetDataCard/PresetDataCard.tsx` | Detect `athena_sources` in response; render Athena tabs |

---

## 4. Data Models

### 4.1 Athena Encounters Manifest (`backend/data/athena-encounters-manifest.json`)

```json
{
  "source_kind": "athena_encounter",
  "label": "Athena — Encounters",
  "tab_id": "athena-encounter",
  "preview_entry_id": "p60183_e62021",
  "entries": [
    {
      "id": "p60183_e62021",
      "label": "Gary 78yo M — Chest Pain / Dyspnea",
      "practice_id": "195900",
      "patient_id": "60183",
      "encounter_id": "62021",
      "api_path": "/v1/195900/chart/encounters/62021/summary",
      "is_preview": true,
      "preview_content": "Patient: SANDBOXTEST, GARY (78yo, M) ..."
    },
    {
      "id": "p60183_e61456",
      "label": "Gary 78yo M — Encounter 61456",
      "practice_id": "195900",
      "patient_id": "60183",
      "encounter_id": "61456",
      "api_path": "/v1/195900/chart/encounters/61456/summary",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "p60178_e62281",
      "label": "Donna 41F — Encounter 62281",
      "practice_id": "195900",
      "patient_id": "60178",
      "encounter_id": "62281",
      "api_path": "/v1/195900/chart/encounters/62281/summary",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "p60178_e62283",
      "label": "Donna 41F — Encounter 62283",
      "practice_id": "195900",
      "patient_id": "60178",
      "encounter_id": "62283",
      "api_path": "/v1/195900/chart/encounters/62283/summary",
      "is_preview": false,
      "preview_content": null
    }
  ],
  "sandbox_note": "Only 4 real encounter IDs are available in the Athena sandbox. This manifest will grow as additional encounters are generated or the sandbox is expanded."
}
```

**Entry field semantics:**
- `id` — stable unique key, used as React key and for batch job identification
- `is_preview: true` — one per manifest; this entry has embedded `preview_content`; the AthenaPresetPanel shows it without an API call
- `preview_content` — stripped plain text from the stored sample JSON; non-null only when `is_preview: true`
- `api_path` — the Athena REST path used for live fetching; stored in Firestore job doc as `athena_api_path`

### 4.2 Athena Clinical Docs Manifest (`backend/data/athena-clinicaldocs-manifest.json`)

```json
{
  "source_kind": "athena_clinical_doc",
  "label": "Athena — Clinical Documents",
  "tab_id": "athena-clinical-doc",
  "preview_entry_id": "60178_204552",
  "entries": [
    {
      "id": "60178_204552",
      "label": "Donna 41F — BP / Paroxetine / Pregnancy Risk",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204552",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204552",
      "is_preview": true,
      "preview_content": "Reason for Appointment\n1. Urgent evaluation..."
    },
    {
      "id": "60178_204457",
      "label": "Donna 41F — Document 204457",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204457",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204457",
      "is_preview": false,
      "preview_content": null
    }
    // ... 98 more entries
  ]
}
```

**Patient ID to name mapping used in manifest labels:**
- 60178 → Donna 41F
- 60179 → Sandbox Patient 60179
- 60180 → Sandbox Patient 60180
- 60181 → Sandbox Patient 60181
- 60182 → Sandbox Patient 60182

The actual sandbox has 92 docs for patient 60178 (Donna), 2 for 60179, 2 for 60180, 2 for 60181, and 2 for 60182 — 100 total.

### 4.3 API Response Shape (`GET /care_plan/datasets`)

Current response:
```json
{ "datasets": [...] }
```

New response:
```json
{
  "datasets": [...],
  "athena_sources": [
    {
      "source_kind": "athena_encounter",
      "label": "Athena — Encounters",
      "tab_id": "athena-encounter",
      "preview_entry_id": "p60183_e62021",
      "entries": [...],
      "sandbox_note": "..."
    },
    {
      "source_kind": "athena_clinical_doc",
      "label": "Athena — Clinical Documents",
      "tab_id": "athena-clinical-doc",
      "preview_entry_id": "60178_204552",
      "entries": [...]
    }
  ]
}
```

The `preview_content` field is included in entries where `is_preview: true`; it is `null` for all other entries.

### 4.4 Batch Jobs Request Body (new Athena source kinds)

For encounters:
```json
{
  "input_source_kind": "athena_encounter",
  "dataset_group": null,
  "dataset_input_id": null,
  "dataset_files": null,
  "athena_practice_id": "195900",
  "athena_patient_id": "60183",
  "athena_encounter_id": "62021",
  "athena_document_id": null,
  "athena_api_path": "/v1/195900/chart/encounters/62021/summary",
  "file_types": ["soap_note"]
}
```

For clinical documents:
```json
{
  "input_source_kind": "athena_clinical_doc",
  "dataset_group": null,
  "dataset_input_id": null,
  "dataset_files": null,
  "athena_practice_id": "195900",
  "athena_patient_id": "60178",
  "athena_encounter_id": null,
  "athena_document_id": "204552",
  "athena_api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204552",
  "file_types": ["soap_note"]
}
```

### 4.5 Firestore Job Document Fields (additions)

All athena_* fields are stored flat in the Firestore job document alongside the existing fields:

```
athena_practice_id: str | None
athena_patient_id:  str | None
athena_encounter_id: str | None   (encounters only)
athena_document_id:  str | None   (clinical docs only)
athena_api_path:     str | None
```

### 4.6 Backend `CarePlanV1_2` (v1_2.py addition)

```python
additional_info: list[str] = Field(default_factory=list)
```

This field is populated by the worker after fetching from Athena. It carries the `athena_api_path` values used. For non-Athena jobs it remains the default empty list and does not appear in the serialized output (or appears as `[]`, which the frontend treats as absent).

### 4.7 Frontend `CarePlanContent` (carePlan.ts addition)

```typescript
additional_info?: string[];
```

---

## 5. Key Algorithms

### 5.1 OAuth2 Token Caching (`AthenaClient`)

Athena tokens are issued with a 300-second TTL via the client credentials flow. A module-level singleton `AthenaClient` caches `(access_token, expires_at)`. Before each API call, `get_token()` checks whether the current time is within 20 seconds of expiry; if so, a new token is fetched.

```
get_token():
  now = time.time()
  if _token is not None and now < _token_expires_at - TOKEN_REFRESH_BUFFER_S:
    return _token
  resp = POST /oauth2/v1/token (client_credentials, scope=athena/service/Athenanet.MDP.*)
  _token = resp["access_token"]
  _token_expires_at = now + TOKEN_TTL_S
  return _token
```

The singleton pattern avoids token churn across batch jobs that run within the same worker container process lifetime.

### 5.2 Rate Limiting for Batch Fetches (`fetch_items_with_rate_limit`)

Athena's sandbox enforces a rate limit. The `download_encounters.py` script discovered empirically that batches of 2 with 30-second inter-batch pauses are safe.

```
fetch_items_with_rate_limit(items: list[dict]) -> list[tuple[dict, str]]:
  results = []
  for i in range(0, len(items), BATCH_SIZE):       # BATCH_SIZE = 2
    batch = items[i : i + BATCH_SIZE]
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
      futures = { pool.submit(_fetch_one, item): item for item in batch }
      for future in as_completed(futures):
        item = futures[future]
        text = future.result()   # raises on API error
        results.append((item, text))
    is_last_batch = (i + BATCH_SIZE) >= len(items)
    if not is_last_batch:
      time.sleep(BATCH_SLEEP_S)   # BATCH_SLEEP_S = 30
  return results
```

For single-item jobs (the common case), the rate limiting logic still applies but produces a single batch with no post-batch sleep.

### 5.3 HTML Stripping (Encounter Summaries)

Athena returns encounter summaries as an HTML document in `summaryhtml`. This must be converted to plain text before passing to the pipeline.

```python
import html
import re

def _strip_html(raw_html: str) -> str:
    unescaped = html.unescape(raw_html)
    text = re.sub(r'<[^>]+>', '', unescaped)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
```

Clinical documents (`documentdata`) are already plain UTF-8 text; no HTML stripping is applied.

---

## 6. Frontend UX Flow

### 6.1 Dataset Loading

`PresetDataCard.tsx` already calls `GET /care_plan/datasets` on mount. SP3 adds consumption of `athena_sources` from the response. For each entry in `athena_sources`, the component adds a tab in the left sidebar using `tab_id` as the key and `label` as the display name. When an Athena tab is active, `<AthenaPresetPanel>` is rendered in the right panel instead of `<PresetDataPanel>`.

### 6.2 `AthenaPresetPanel` — Two Modes

The panel has two UI modes toggled by "Preview" / "List" buttons at the top:

**Preview mode (default):**
- Shows the single entry where `is_preview: true` in a non-interactive card with the entry label and a text excerpt from `preview_content`.
- A "Submit" button triggers a single batch job using the preview entry's identifiers and `input_source_kind` from the manifest.
- No Athena API call at job time — the preview_content is displayed only in the panel; the live API fetch happens in the worker just like any other entry.

**List mode:**
- Renders a scrollable checklist of all entries where `is_preview: false`.
- Each entry is selectable; selected entries are submitted as a batch job group.
- Entries display their `label` field; no inline preview is shown (the documents are fetched at worker time).

The selection state is propagated up to `PresetDataCard` via an `onSelectionChange` callback carrying `AthenaSelection[]` objects, which are then merged with the existing `BatchDatasetSelection[]` in the parent's `createBatchJobs()` call.

### 6.3 "Data Sources" Card in Care Plan View

At the bottom of `CarePlanView`, after all existing result cards and before the action buttons in `CarePlanJobPage`:

```tsx
{result.care_plan.additional_info && result.care_plan.additional_info.length > 0 && (
  <ResultCard color="gray" icon="🔗" title="Data Sources">
    <ul className="result-list">
      {result.care_plan.additional_info.map((path, i) => (
        <li key={i} style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{path}</li>
      ))}
    </ul>
  </ResultCard>
)}
```

This is appended at the end of the `<div className="result-cards">` block, after the Glossary card. It renders the Athena API paths used, giving the clinician a traceable audit trail back to the source records.

---

## 7. Error Handling Strategy

### 7.1 Auth failure (`ATHENA_AUTH_FAILED`)

If the OAuth2 token request fails (bad credentials, network error, non-200 response), `AthenaClient.get_token()` raises. The worker catches this as an unexpected exception, calls `fail_job()` with `build_error_data_from_exc(exc)`, and returns `200` to Cloud Tasks (so the task is not retried). The Firestore job shows `status: "error"` with the error code.

### 7.2 API error (`ATHENA_API_ERROR`)

If the Athena API returns a non-200 status on a fetch call, `fetch_encounter_summary()` or `fetch_clinical_doc()` raises an `AthenaAPIError` exception. This is caught by the worker's outer try/except and results in a `fail_job()` call with `ATHENA_API_ERROR`.

### 7.3 Rate limit hit (`ATHENA_RATE_LIMIT_ERROR`)

If Athena returns HTTP 429, the client should inspect `Retry-After` (as the download script does) and sleep before retrying. A maximum of 3 retries is applied. If all retries are exhausted, `ATHENA_RATE_LIMIT_ERROR` is raised. The download script demonstrated this pattern works in practice.

### 7.4 Missing env vars

If `ATHENA_HEALTH_CLIENT_ID` or `ATHENA_HEALTH_CLIENT_SECRET` are not set, `get_token()` raises `RuntimeError` immediately. This is caught by the worker and surfaced as `INTERNAL_ERROR`.

### 7.5 Preview mode (no API call)

For the preview entry, the `preview_content` is shown in the panel but a live API call is still made at worker time. The preview is purely a UX affordance to show document quality before submitting. This is consistent with SP1's sample embed in `manifest.json`.

---

## 8. Future Extension: Push to Athena

A locked decision (not in SP3) defers the write-back path: after generating a care plan from an Athena source, push the simplified output back to Athena as a new clinical document via:

```
POST /v1/{practiceId}/patients/{patientId}/documents/clinicaldocument
```

When this is implemented:
- The care plan result page would show a "Push to Athena" button, visible only for jobs with `athena_patient_id` set.
- The backend would expose a new endpoint (e.g., `POST /care_plan/outputs/{job_id}/push_to_athena`) that reconstructs the formatted output and calls the Athena document API.
- The `additional_info` field would be extended to carry the pushed document ID.

This path requires the same OAuth2 client and token cache already built for SP3.

---

## 9. Testing Approach

### Unit tests

- `test_athena_client.py` — token caching (mock requests): verify token reuse within TTL, refresh before buffer, refresh on expiry; verify `_strip_html()` produces clean text for a representative `summaryhtml` value; verify `fetch_clinical_doc()` returns `documentdata` directly.
- `test_athena_manifests.py` — load both manifest JSON files, assert required keys, assert exactly one `is_preview: true` entry per manifest, assert `preview_entry_id` matches the `is_preview: true` entry's `id`.

### Integration tests

- Worker dispatch test for `athena_encounter` source kind: mock `athena_client.fetch_encounter_summary()`, assert worker calls it with correct args, assert `additional_info` is populated.
- Worker dispatch test for `athena_clinical_doc` source kind: same pattern.

### Manual testing with sandbox

1. Set `ATHENA_HEALTH_CLIENT_ID` and `ATHENA_HEALTH_CLIENT_SECRET` in `backend/.env`.
2. Start the backend, open the frontend, expand the Preset Data card.
3. Click the "Athena — Encounters" tab; verify preview entry is shown in Preview mode.
4. Click "Athena — Clinical Documents" tab; verify List mode shows 99 non-preview entries.
5. Select the preview entry and Submit; verify the job runs and the care plan result includes a "Data Sources" card with the Athena API path.
6. Select 2 non-preview entries and Submit; verify both jobs run and complete within `BATCH_ITEM_INTERNAL_DEADLINE_S`.

---

## 10. Sandbox Data Summary

From reading the `EncounterSummaries/` directory:

| File | Patient | Encounter ID | Notes |
|------|---------|--------------|-------|
| `sample_p60183_e62021_02.json` | Gary 78yo M (60183) | 62021 | Chest pain / dyspnea — **preview entry** |
| `sample_p60183_e61456_03.json` | Gary 78yo M (60183) | 61456 | Second Gary encounter |
| `sample_p60178_e62281_01.json` | Donna 41F (60178) | 62281 | Donna encounter 1 |
| `sample_p60178_e62283_00.json` | Donna 41F (60178) | 62283 | Donna encounter 2 |

From reading the `ClinicalDocumentContentAll/` directory:
- 100 directories total (`60178_204457` through `60182_206240`)
- Patient 60178 (Donna): 92 documents
- Patients 60179–60182: 2 documents each
- Preview entry: `60178_204552` (Donna — BP/Paroxetine/Pregnancy Risk SOAP note)
