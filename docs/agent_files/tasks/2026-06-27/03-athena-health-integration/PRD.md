# PRD: SP3 — Athena Health Integration

**Sub-project:** SP3
**Branch context:** `athena_health_part1`
**Date:** 2026-06-27
**Status:** Planning — no implementation started

---

## 1. Problem

Juno generates care plans from uploaded files and GCS-staged research datasets. There is no path to pull live clinical data from an EHR. The Athena Health sandbox exposes 4 encounter summaries and 100 SOAP notes via REST API. These are richer, more realistic inputs than the current research datasets, and they let the team demo Juno against actual EHR records.

Two obstacles exist:
1. Athena uses OAuth2 client credentials — tokens must be obtained, cached, and refreshed.
2. Athena's sandbox enforces rate limits that require batch-size-2 with 30-second inter-batch pauses.

---

## 2. Goals

1. Fetch Athena encounter summaries at worker execution time and run them through the care plan pipeline.
2. Fetch Athena SOAP-note clinical documents at worker execution time and run them through the care plan pipeline.
3. Expose both Athena sources in `GET /care_plan/datasets` alongside existing groups.
4. Add a frontend `AthenaPresetPanel` component with Preview mode (embedded sample text) and List mode (all 99+ non-preview entries).
5. Render a "Data Sources" card in the care plan result showing the Athena API paths consumed.
6. Store Athena job metadata (practice_id, patient_id, encounter_id or document_id, api_path) in Firestore.

---

## 3. Non-Goals

- Writing Juno outputs back to Athena (push-to-Athena deferred — see §9, Q5).
- Production Athena account or non-sandbox credentials.
- Authentication / authorization changes (Athena credentials are backend-only env vars).
- Streaming the Athena fetch progress to the frontend (worker does not report sub-steps).
- FHIR or HL7 API paths (only REST v1 Athena API is used).
- Athena encounter/document creation or modification.

---

## 4. Architecture Decisions

### New files (data model contract)

| File | Purpose |
|------|---------|
| `backend/models/athena.py` | Pydantic v2 models for all Athena API requests and responses |
| `frontend/src/types/athena.ts` | TypeScript interfaces mirroring the backend Athena models |

The `AthenaClient` in `backend/utils/athena_client.py` imports from `backend/models/athena.py` for type-annotated request/response handling.

---

### A. New file: `backend/utils/athena_client.py`

**Full interface:**

```python
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from utils.constants import Constants

BATCH_SIZE = 2
BATCH_SLEEP_S = 30


class AthenaAPIError(Exception):
    """Raised when an Athena API call returns a non-200 status."""
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Athena API error {status_code}: {body[:200]}")


class AthenaClient:
    TOKEN_TTL_S: int = 300
    TOKEN_REFRESH_BUFFER_S: int = 20

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if within 20s of expiry."""
        import os
        now = time.time()
        if self._token and now < self._token_expires_at - self.TOKEN_REFRESH_BUFFER_S:
            return self._token
        client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
        client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]
        resp = requests.post(
            f"{Constants.ATHENA_BASE_URL}/oauth2/v1/token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials",
                  "scope": "athena/service/Athenanet.MDP.*"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]
        self._token_expires_at = now + self.TOKEN_TTL_S
        return self._token

    def _get(self, path: str, retries: int = 3) -> dict:
        """GET with retry on 429; raises AthenaAPIError on other non-200."""
        for attempt in range(retries + 1):
            token = self.get_token()
            resp = requests.get(
                f"{Constants.ATHENA_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                if attempt == retries:
                    from utils.error_codes import ErrorCode
                    raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise AthenaAPIError(resp.status_code, resp.text)
            return resp.json()
        raise AthenaAPIError(429, "Rate limit: max retries exhausted")

    def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
        """Fetch encounter summary HTML and return as stripped plain text."""
        data = self._get(f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary")
        raw_html = data.get("summaryhtml", "")
        return self._strip_html(raw_html)

    def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
        """Fetch SOAP note clinical document and return documentdata string."""
        data = self._get(
            f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
        )
        return data.get("documentdata", "")

    @staticmethod
    def _strip_html(raw_html: str) -> str:
        unescaped = html.unescape(raw_html)
        text = re.sub(r'<[^>]+>', '', unescaped)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def fetch_items_with_rate_limit(
        self, items: list[dict]
    ) -> list[tuple[dict, str]]:
        """Fetch a list of Athena items (encounter or doc) in batches of 2.

        Each item dict must have: source_kind, practice_id, and either
        (encounter_id) or (patient_id + document_id).

        Returns list of (item, text) pairs in arbitrary order.
        Sleeps BATCH_SLEEP_S seconds between batches (skips after last).
        """
        results: list[tuple[dict, str]] = []
        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i : i + BATCH_SIZE]

            def _fetch_one(item: dict) -> str:
                if item["source_kind"] == "athena_encounter":
                    return self.fetch_encounter_summary(
                        item["practice_id"], item["encounter_id"]
                    )
                return self.fetch_clinical_doc(
                    item["practice_id"], item["patient_id"], item["document_id"]
                )

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
                futures = {pool.submit(_fetch_one, item): item for item in batch}
                for future in as_completed(futures):
                    results.append((futures[future], future.result()))

            is_last_batch = (i + BATCH_SIZE) >= len(items)
            if not is_last_batch:
                time.sleep(BATCH_SLEEP_S)

        return results


# Module-level singleton — shared across all requests in the same worker process.
athena_client = AthenaClient()
```

---

### B. New directory: `backend/data/`

Created at `backend/data/`. Path resolution in code:
```python
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
```
This is relative to `backend/utils/`, so `parent.parent` lands at `backend/`.

---

### C. New file: `backend/data/athena-encounters-manifest.json`

Full schema (90 entries total — 86 from Encounters/ + 4 from EncounterSummaries, one `is_preview: true`):

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
      "preview_content": "<stripped text from sample_p60183_e62021_02.json>"
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
    // ... 86 more entries generated from docs/agent_files/athena-bruno/Encounters/ ...
  ]
}
```

The `preview_content` for `p60183_e62021` is obtained by running `AthenaClient._strip_html()` on the `summaryhtml` field of `docs/agent_files/athena-bruno/EncounterSummaries/sample_p60183_e62021_02.json`. This produces a multi-section plain-text rendering of Gary's encounter (Patient block, Chief Complaint, Vitals, Allergies, Medications, Assessment/Plan).

---

### D. New file: `backend/data/athena-clinicaldocs-manifest.json`

Schema: identical structure to encounters manifest, but with `document_id` instead of `encounter_id` in entries.

- 100 total entries (one `is_preview: true`, 99 `is_preview: false`).
- Preview entry: `60178_204552` — `preview_content` is the first 2000 characters of `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/60178_204552/document.txt`.
- All other entries: `is_preview: false`, `preview_content: null`.
- Directory name format `{patient_id}_{document_id}` maps directly to entry fields.
- Patient labels: 60178 → "Donna 41F", 60179–60182 → "Sandbox Patient {id}".

Generation: a one-time script reads all 100 directory entries from `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/`, sorts them, and writes the manifest. This is a manual step (see §8).

---

### E. Modified: `backend/utils/constants.py`

Add to the `Constants` class:

```python
# ── Athena Health API ──────────────────────────────────────────────────────
ATHENA_CLIENT_ID_ENV_VAR: str     = "ATHENA_HEALTH_CLIENT_ID"
ATHENA_CLIENT_SECRET_ENV_VAR: str = "ATHENA_HEALTH_CLIENT_SECRET"
ATHENA_BASE_URL: str              = "https://api.preview.platform.athenahealth.com"
ATHENA_PRACTICE_ID: str           = "195900"   # sandbox practice ID
```

These are added after the existing `DATASETS_BUCKET_ENV_VAR` block.

---

### F. Modified: `backend/utils/error_codes.py`

Add to `ErrorCode` StrEnum (after `DATASET_DOWNLOAD_ERROR`):

```python
ATHENA_AUTH_FAILED     = "ATHENA_AUTH_FAILED"
ATHENA_API_ERROR       = "ATHENA_API_ERROR"
ATHENA_RATE_LIMIT_ERROR = "ATHENA_RATE_LIMIT_ERROR"
```

Add to `_REGISTRY` dict (after the `DATASET_DOWNLOAD_ERROR` entry):

```python
ErrorCode.ATHENA_AUTH_FAILED:      ("Athena authentication failed",         "Could not obtain Athena OAuth2 token: {detail}"),
ErrorCode.ATHENA_API_ERROR:        ("Athena API error",                     "Athena returned HTTP {status_code} for {path}: {detail}"),
ErrorCode.ATHENA_RATE_LIMIT_ERROR: ("Athena rate limit exceeded",           "Athena API rate limit hit after {retries} retries; try again in {wait_s}s"),
```

---

### G. Modified: `backend/routes/datasets.py`

**Old:**
```python
from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

@datasets_bp.route("/care_plan/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id: str):
    _ = user_id
    return jsonify({"datasets": list_datasets()})
```

**New:**
```python
from pathlib import Path
import json

from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_ATHENA_MANIFEST_NAMES = [
    "athena-encounters-manifest.json",
    "athena-clinicaldocs-manifest.json",
]

def _load_athena_sources() -> list[dict]:
    sources = []
    for name in _ATHENA_MANIFEST_NAMES:
        path = DATA_DIR / name
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                sources.append(json.load(f))
    return sources

@datasets_bp.route("/care_plan/datasets", methods=["GET"])
@verify_firebase_token
def list_datasets_route(user_id: str):
    _ = user_id
    return jsonify({
        "datasets": list_datasets(),
        "athena_sources": _load_athena_sources(),
    })
```

The manifest files are read on every request (no cache). If a file is missing, it is silently omitted from `athena_sources`. This allows the endpoint to work before the manifest files are created.

---

### H. Modified: `backend/routes/batch_jobs.py`

The existing `_resolve_requested_runs()` call processes GCS dataset selections. Athena selections bypass this entirely.

**New request body fields accepted per selection item:**

```json
{
  "input_source_kind": "athena_encounter" | "athena_clinical_doc",
  "athena_practice_id": "195900",
  "athena_patient_id": "60183",
  "athena_encounter_id": "62021",   // encounters only; null for clinical docs
  "athena_document_id": null,       // clinical docs only; null for encounters
  "athena_api_path": "/v1/195900/chart/encounters/62021/summary"
}
```

**New Firestore job doc fields** (added alongside existing fields in the `job_doc` dict):

```python
job_doc = {
    # ... existing fields unchanged ...
    "input_source_kind": selection["input_source_kind"],  # "athena_encounter" | "athena_clinical_doc"
    "athena_practice_id":  selection.get("athena_practice_id"),
    "athena_patient_id":   selection.get("athena_patient_id"),
    "athena_encounter_id": selection.get("athena_encounter_id"),
    "athena_document_id":  selection.get("athena_document_id"),
    "athena_api_path":     selection.get("athena_api_path"),
    # dataset fields remain in doc but are None for Athena jobs
    "dataset_group":    None,
    "dataset_input_id": None,
    "dataset_files":    None,
}
```

The route must detect whether a selection is an Athena kind and skip the `_resolve_requested_runs()` path for those items. The batch_run_id and enqueue logic are unchanged.

---

### I. Modified: `backend/routes/worker.py`

**`_INPUT_TYPE_MAP` addition:**

```python
_INPUT_TYPE_MAP = {
    "upload": "file",
    "batch_dataset": "text",
    "gcs_batch_dataset": "text",
    "athena_encounter": "text",     # new
    "athena_clinical_doc": "text",  # new
    "doc_id": "doc_id",
    "text": "text",
}
```

**Dispatch block in `execute_job()`:**

The existing `if source_kind == "gcs_batch_dataset": ...` block is extended to also handle Athena kinds. After the GCS branch and before the `else` (which calls `_resolve_input_from_job_doc`):

```python
elif source_kind in ("athena_encounter", "athena_clinical_doc"):
    from utils.athena_client import athena_client, AthenaAPIError
    practice_id = job_doc.get("athena_practice_id", Constants.ATHENA_PRACTICE_ID)
    api_path = job_doc.get("athena_api_path", "")
    try:
        if source_kind == "athena_encounter":
            text = athena_client.fetch_encounter_summary(
                practice_id, job_doc["athena_encounter_id"]
            )
        else:
            text = athena_client.fetch_clinical_doc(
                practice_id, job_doc["athena_patient_id"], job_doc["athena_document_id"]
            )
    except AthenaAPIError as exc:
        from utils.error_codes import ErrorCode, make_error_response
        fail_job(job_id, build_error_data(
            PipelineErrorCode.ATHENA_API_ERROR,
            f"status={exc.status_code} path={api_path}"
        ))
        return "", 200
    athena_additional_info = [api_path] if api_path else []
```

After pipeline completes and before `complete_job()`, merge `athena_additional_info` into the output:

```python
# For Athena jobs, inject additional_info into the care_plan dict
if source_kind in ("athena_encounter", "athena_clinical_doc") and athena_additional_info:
    care_plan_dict = output_data.get("care_plan", {})
    care_plan_dict["additional_info"] = athena_additional_info
    output_data["care_plan"] = care_plan_dict
```

---

### J. Modified: `backend/models/care_plan_versions/v1_2.py`

**Old** (`CarePlanV1_2` class body, after `raw: RawArtifacts | None = None`):
```python
    raw: RawArtifacts | None = None
```

**New:**
```python
    raw: RawArtifacts | None = None
    additional_info: list[str] = Field(default_factory=list)
```

This field is ignored by the pipeline LLM steps and is purely a pass-through populated by the worker. Existing outputs that lack this field deserialize with the default empty list.

---

### K. Modified: `backend/.env.example`

Add after the existing `DATASETS_BUCKET_NAME` line:

```
# Athena Health API credentials (OAuth2 client credentials flow)
# Obtain from: https://developer.athenahealth.com/
ATHENA_HEALTH_CLIENT_ID=your_client_id_here
ATHENA_HEALTH_CLIENT_SECRET=your_client_secret_here
```

---

### L. Modified: `frontend/src/types/carePlan.ts`

**Old** (last two lines of `CarePlanContent`):
```typescript
  raw?: {
    text: string;
    simplified_text: string;
    clarified_text: string;
  };
  before_score?: PatientScore;
  after_score?: PatientScore;
}
```

**New:**
```typescript
  raw?: {
    text: string;
    simplified_text: string;
    clarified_text: string;
  };
  before_score?: PatientScore;
  after_score?: PatientScore;
  additional_info?: string[];
}
```

---

### M. Modified: `frontend/src/components/CarePlanView.tsx`

Add at the end of the `<div className="result-cards">` block, after the Glossary `ResultCard`:

**Old** (last block before closing `</div>`):
```tsx
      {Object.keys(terms).length > 0 && (
        <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
          ...
        </ResultCard>
      )}
    </div>
  );
```

**New:**
```tsx
      {Object.keys(terms).length > 0 && (
        <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
          ...
        </ResultCard>
      )}

      {result.additional_info && result.additional_info.length > 0 && (
        <ResultCard color="gray" icon="🔗" title="Data Sources">
          <ul className="result-list">
            {result.additional_info.map((path, i) => (
              <li key={i} style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {path}
              </li>
            ))}
          </ul>
        </ResultCard>
      )}
    </div>
  );
```

The `ResultCard` component's `color` prop is `"gray"` and `icon` is `"🔗"`. No `collapsible` prop — the card is always expanded since it contains only a short list.

---

### N. New file: `frontend/src/components/PresetDataCard/AthenaPresetPanel.tsx`

This component handles a single Athena source manifest (one of encounters or clinical docs). Props:

```typescript
interface AthenaEntry {
  id: string;
  label: string;
  practice_id: string;
  patient_id: string;
  encounter_id?: string;    // for athena_encounter
  document_id?: string;     // for athena_clinical_doc
  api_path: string;
  is_preview: boolean;
  preview_content: string | null;
}

interface AthenaSource {
  source_kind: "athena_encounter" | "athena_clinical_doc";
  label: string;
  tab_id: string;
  preview_entry_id: string;
  entries: AthenaEntry[];
}

export interface AthenaSelection {
  source_kind: "athena_encounter" | "athena_clinical_doc";
  entry: AthenaEntry;
}

interface AthenaPresetPanelProps {
  source: AthenaSource;
  onSelectionChange: (selections: AthenaSelection[]) => void;
}
```

**Mode toggle:**
```tsx
type PanelMode = 'preview' | 'list';
const [mode, setMode] = useState<PanelMode>('preview');
```

Two buttons rendered at panel top:
```tsx
<div className="athena-mode-toggle">
  <button
    type="button"
    className={`athena-mode-btn ${mode === 'preview' ? 'active' : ''}`}
    onClick={() => setMode('preview')}
  >
    Preview
  </button>
  <button
    type="button"
    className={`athena-mode-btn ${mode === 'list' ? 'active' : ''}`}
    onClick={() => setMode('list')}
  >
    List ({source.entries.filter(e => !e.is_preview).length})
  </button>
</div>
```

**Preview mode renders:**
```tsx
const previewEntry = source.entries.find(e => e.is_preview);
// Single non-interactive card + Submit button
<div className="athena-preview-card">
  <div className="athena-preview-label">{previewEntry?.label}</div>
  <div className="athena-preview-content">{previewEntry?.preview_content?.slice(0, 500)}…</div>
  <button type="button" className="athena-preview-submit"
    onClick={() => previewEntry && onSelectionChange([{ source_kind: source.source_kind, entry: previewEntry }])}>
    Submit
  </button>
</div>
```

**List mode renders:**
```tsx
const listEntries = source.entries.filter(e => !e.is_preview);
const [selected, setSelected] = useState<Set<string>>(new Set());
// Scrollable checklist
<div className="athena-list-panel">
  {listEntries.map(entry => (
    <label key={entry.id} className="preset-data-option">
      <input
        type="checkbox"
        className="preset-data-checkbox"
        checked={selected.has(entry.id)}
        onChange={() => {
          const next = new Set(selected);
          next.has(entry.id) ? next.delete(entry.id) : next.add(entry.id);
          setSelected(next);
          onSelectionChange(listEntries.filter(e => next.has(e.id))
            .map(e => ({ source_kind: source.source_kind, entry: e })));
        }}
      />
      <span className="preset-data-option-text">{entry.label}</span>
    </label>
  ))}
</div>
```

CSS class names reuse the `preset-data-option`, `preset-data-checkbox`, and `preset-data-option-text` patterns from `PresetDataPanel.tsx`. New classes `athena-mode-toggle`, `athena-mode-btn`, `athena-preview-card`, `athena-preview-label`, `athena-preview-content`, `athena-preview-submit`, `athena-list-panel` are added to `PresetDataCard.css`.

---

### O. Modified: `frontend/src/components/PresetDataCard/PresetDataCard.tsx`

The `listDatasets()` API call already exists. The response type must be extended to include `athena_sources`. The component adds state for Athena selections and renders Athena tabs.

**New state:**
```typescript
const [athenaSources, setAthenaSources] = useState<AthenaSource[]>([]);
const [athenaSelections, setAthenaSelections] = useState<AthenaSelection[]>([]);
```

**In `loadDatasets()`:**
```typescript
const response = await listDatasets();    // listDatasets() now returns { datasets, athena_sources }
if (!cancelled) {
  setDatasets(response.datasets ?? []);
  setAthenaSources(response.athena_sources ?? []);
}
```

**Tab rendering** — Athena tabs are added after dataset group tabs in the sidebar:
```tsx
{athenaSources.map(source => (
  <button
    key={source.tab_id}
    type="button"
    className={`preset-panel-tab ${activeGroup === source.tab_id ? 'active' : ''}`}
    onClick={() => setActiveGroup(source.tab_id)}
    aria-selected={activeGroup === source.tab_id}
  >
    <span className="preset-panel-tab-name">{source.label}</span>
    <span className="preset-panel-tab-meta">
      {athenaSelections.filter(s => s.source_kind === source.source_kind).length} sel.
    </span>
  </button>
))}
```

**Content panel** — When the active tab is an Athena source:
```tsx
const activeAthenaSource = athenaSources.find(s => s.tab_id === activeGroup);
if (activeAthenaSource) {
  return (
    <AthenaPresetPanel
      source={activeAthenaSource}
      onSelectionChange={(sels) => {
        setAthenaSelections(prev => [
          ...prev.filter(s => s.source_kind !== activeAthenaSource.source_kind),
          ...sels,
        ]);
      }}
    />
  );
}
```

**`onSelectionChange` propagation** — The parent's `onSelectionChange` is updated to include both GCS dataset selections and Athena selections. The parent receives a combined list; `createBatchJobs()` must understand both selection types.

---

## 5. API Change Summary

| Endpoint | Change |
|----------|--------|
| `GET /care_plan/datasets` | Response adds `athena_sources: AthenaSource[]` alongside existing `datasets` |
| `POST /care_plan/batch/jobs` | Accepts `input_source_kind: "athena_encounter" \| "athena_clinical_doc"` with `athena_*` fields |
| `POST /internal/jobs/execute/{job_id}` | Worker dispatches new source kinds; no HTTP interface change |

**`GET /care_plan/datasets` new response shape:**

```json
{
  "datasets": [
    {
      "group": "meqsum",
      "inputs": ["0001", "0002"],
      "files": ["question.txt", "summary.txt"]
    }
  ],
  "athena_sources": [
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
          "preview_content": "Patient: SANDBOXTEST, GARY ..."
        }
      ]
    }
  ]
}
```

**`POST /care_plan/batch/jobs` new request shape (Athena encounter):**

```json
{
  "selections": [
    {
      "input_source_kind": "athena_encounter",
      "athena_practice_id": "195900",
      "athena_patient_id": "60183",
      "athena_encounter_id": "62021",
      "athena_document_id": null,
      "athena_api_path": "/v1/195900/chart/encounters/62021/summary"
    }
  ],
  "version": "v1-2",
  "grading_enabled": false
}
```

---

## 6. Frontend Change Summary

| File | Change |
|------|--------|
| `frontend/src/types/carePlan.ts` | Add `additional_info?: string[]` to `CarePlanContent` |
| `frontend/src/components/CarePlanView.tsx` | Render "Data Sources" `ResultCard` when `additional_info` is non-empty |
| `frontend/src/components/PresetDataCard/PresetDataCard.tsx` | Add `athenaSources` state; render Athena tabs; propagate Athena selections |
| `frontend/src/components/PresetDataCard/AthenaPresetPanel.tsx` | New component — Preview/List mode panel for Athena sources |
| `frontend/src/components/PresetDataCard/PresetDataCard.css` | Add styles for `.athena-mode-toggle`, `.athena-mode-btn`, `.athena-preview-card`, `.athena-list-panel` |
| `frontend/src/api/datasets.ts` | Update `listDatasets()` return type to include `athena_sources` |
| `frontend/src/types/datasets.ts` | Add `AthenaEntry`, `AthenaSource`, `AthenaSelection` types |

---

## 7. Testing

### Unit tests — backend

**`backend/tests/utils/test_athena_client.py`**

1. `test_get_token_caches_within_ttl` — mock `requests.post`; call `get_token()` twice within TTL; assert HTTP call made exactly once.
2. `test_get_token_refreshes_before_buffer` — set `_token_expires_at = time.time() + 15`; call `get_token()`; assert HTTP call made (15s < 20s buffer).
3. `test_get_token_does_not_refresh_when_fresh` — set `_token_expires_at = time.time() + 100`; call `get_token()`; assert no HTTP call.
4. `test_strip_html_removes_tags` — assert `_strip_html('<p>Hello <b>world</b></p>')` returns `'Hello world'`.
5. `test_strip_html_unescapes_entities` — assert `_strip_html('&lt;b&gt;')` returns `'<b>'`.
6. `test_fetch_encounter_summary_calls_correct_path` — mock `_get`; call `fetch_encounter_summary("195900", "62021")`; assert path equals `/v1/195900/chart/encounters/62021/summary`.
7. `test_fetch_clinical_doc_calls_correct_path` — mock `_get`; call `fetch_clinical_doc("195900", "60178", "204552")`; assert path equals `/v1/195900/patients/60178/documents/clinicaldocument/204552`.
8. `test_fetch_items_rate_limit_sleeps_between_batches` — mock `_fetch_one`; pass 3 items; assert `time.sleep` called once with `BATCH_SLEEP_S` (after batch 1, not after batch 2).

**`backend/tests/utils/test_athena_manifests.py`**

1. `test_encounters_manifest_loads` — load `backend/data/athena-encounters-manifest.json`; assert `source_kind == "athena_encounter"`; assert exactly one entry with `is_preview: true`; assert `preview_entry_id` matches that entry's `id`; assert 90 entries total.
2. `test_clinical_docs_manifest_loads` — load `backend/data/athena-clinicaldocs-manifest.json`; assert `source_kind == "athena_clinical_doc"`; assert exactly one entry with `is_preview: true`; assert 100 entries total.
3. `test_all_non_preview_entries_have_null_preview_content` — for both manifests, assert all entries where `is_preview == false` have `preview_content == null`.

### Unit tests — frontend

No new test files for SP3 (existing Vitest coverage does not include PresetDataCard components). Manual verification per §8 step 5.

---

## 8. Manual Intervention Required From You

1. **Generate `preview_content` for encounters manifest** — run `AthenaClient._strip_html()` on `docs/agent_files/athena-bruno/EncounterSummaries/sample_p60183_e62021_02.json`'s `summaryhtml` field and paste the result into the manifest as `p60183_e62021.preview_content`.

2. **Generate `preview_content` for clinical docs manifest** — paste the first 2000 characters of `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/60178_204552/document.txt` as `60178_204552.preview_content`.

3. **Generate the full clinical docs manifest** — write a one-time script (or inline Python) that enumerates all 100 directories in `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/`, excludes `manifest.json`, builds an entry per directory, marks `60178_204552` as the preview entry, and writes `backend/data/athena-clinicaldocs-manifest.json`.

4. **Set Athena credentials** — add `ATHENA_HEALTH_CLIENT_ID` and `ATHENA_HEALTH_CLIENT_SECRET` to `backend/.env` (local) and to the Cloud Run worker service environment (production). Credentials are in the Athena developer portal for the sandbox account.

5. **Deploy** — after all backend changes are merged:
   - Deploy worker service with new env vars set.
   - Verify `GET /care_plan/datasets` returns `athena_sources` with 90 encounters and 100 clinical doc entries.
   - Run a single-item encounter job and confirm the care plan result includes a "Data Sources" card.

---

## 9. Open Questions & Decisions

**Q1: Why fetch at worker time rather than at request time?**
[RESOLVED: Worker-time fetching matches the SP2 GCS pattern. The HTTP request layer stays thin; errors are attributed to job execution rather than the creation endpoint. `BATCH_ITEM_INTERNAL_DEADLINE_S = 870s` gives ample time for sub-second Athena fetches plus full pipeline execution.]

**Q2: How do we avoid hitting the Athena rate limit on batch jobs?**
[RESOLVED: `concurrent.futures.ThreadPoolExecutor(max_workers=2)` with `time.sleep(30)` between batches of 2. The batch size and delay were validated empirically by the `download_encounters.py` script (BATCH_SIZE=2, BATCH_DELAY_SECONDS=30). The sleep is skipped after the last batch to avoid unnecessary delay.]

**Q3: What token caching strategy avoids per-request OAuth roundtrips?**
[RESOLVED: Module-level `AthenaClient` singleton caches `(access_token, expires_at)`. Tokens are valid for 300 seconds; the client refreshes when fewer than 20 seconds remain. Within a single worker container process, all jobs share the cached token.]

**Q4: Should the preview entry be served without a live Athena call?**
[RESOLVED: Preview mode in `AthenaPresetPanel` shows embedded `preview_content` text in the UI. However, when the preview entry is submitted as a job, the worker still makes a live Athena API call for the text — the embedded content is only for the UI preview display, not a shortcut for job execution. This keeps job execution uniform across all entries.]

**Q5: Should Juno push the generated care plan back to Athena?**
[DEFERRED: The `POST /v1/{practiceId}/patients/{patientId}/documents/clinicaldocument` push path is architecturally straightforward (same OAuth2 client) but is out of scope for SP3. The `additional_info` field already captures the Athena source paths for traceability. The push feature will be SP4 or a later iteration.]

**Q6: Should encounter HTML stripping use BeautifulSoup or regex?**
[RESOLVED: Use `html.unescape()` + `re.sub(r'<[^>]+>', '', ...)` (stdlib only). The Athena HTML structure is simple enough for regex; no BeautifulSoup dependency is added. If edge cases surface in production, upgrade to BeautifulSoup at that time.]

**Q7: What error code applies when Athena OAuth2 fails vs. when an API call fails?**
[RESOLVED: `ATHENA_AUTH_FAILED` when `get_token()` raises (bad credentials or OAuth endpoint error). `ATHENA_API_ERROR` when a fetch call returns a non-200 non-429 status. `ATHENA_RATE_LIMIT_ERROR` when 429 retries are exhausted. All three are new `ErrorCode` enum values with `_REGISTRY` entries.]

**Q8: How is `additional_info` populated for multi-item batch jobs?**
[RESOLVED: Each job doc in Firestore stores exactly one `athena_api_path`. The worker reads the single job doc per execution and sets `additional_info = [athena_api_path]`. Multi-item selections create multiple job docs (one per entry), each with its own path. The "Data Sources" card on each care plan result shows exactly one entry.]

**Q9: Does the `datasets` key name change in the API response?**
[RESOLVED: The existing `datasets` key is preserved unchanged. `athena_sources` is a new top-level key. No breaking change to existing frontend consumers that read `datasets`.]

---

## § Athena Data Models

These are the typed model definitions for all Athena Health API interactions. Both files must be created before any other SP3 implementation task.

### `backend/models/athena.py` (Pydantic v2)

```python
# Auth
class AthenaTokenRequest(BaseModel):
    client_id: str; client_secret: str; grant_type: str = "client_credentials"; scope: str

class AthenaTokenResponse(BaseModel):
    access_token: str; token_type: str; expires_in: int

# Encounters
class AthenaEncounterSummaryRequest(BaseModel):
    practice_id: str; encounter_id: str

class AthenaEncounterSummaryResponse(BaseModel):
    summaryhtml: str

# Clinical Documents (list)
class AthenaClinicalDocumentMeta(BaseModel):
    clinicaldocumentid: int; patientid: int; documentdescription: str
    documentclass: str; status: str; internalnote: str | None = None
    createddatetime: str | None = None; documentsource: str | None = None
    documentroute: str | None = None

class AthenaClinicalDocumentListRequest(BaseModel):
    practice_id: str; patient_id: str; department_id: str | None = None
    limit: int = 200; offset: int = 0

class AthenaClinicalDocumentListResponse(BaseModel):
    clinicaldocuments: list[AthenaClinicalDocumentMeta]; totalcount: int | None = None

# Clinical Document content
class AthenaClinicalDocumentContentRequest(BaseModel):
    practice_id: str; patient_id: str; document_id: str

class AthenaClinicalDocumentContentResponse(BaseModel):
    documentdata: str | None = None; pages: list[dict] | None = None

# Push back (future/deferred SP4)
class AthenaPushDocumentRequest(BaseModel):
    practice_id: str; patient_id: str; department_id: str
    attachment_contents: str; attachment_type: str
    document_subclass: str = "JUNO_SUMMARY"; internal_note: str

class AthenaPushDocumentResponse(BaseModel):
    clinicaldocumentid: int; success: bool | None = None
```

All models use `model_config = ConfigDict(extra="allow")`.

### `frontend/src/types/athena.ts` (TypeScript)

```typescript
interface AthenaTokenResponse { access_token: string; token_type: string; expires_in: number; }
interface AthenaEncounterSummaryResponse { summaryhtml: string; [key: string]: unknown; }
interface AthenaClinicalDocumentMeta {
  clinicaldocumentid: number; patientid: number; documentdescription: string;
  documentclass: string; status: string; internalnote?: string;
  createddatetime?: string; documentsource?: string; documentroute?: string;
  [key: string]: unknown;
}
interface AthenaClinicalDocumentListResponse { clinicaldocuments: AthenaClinicalDocumentMeta[]; totalcount?: number; }
interface AthenaClinicalDocumentContentResponse { documentdata?: string; pages?: Array<{ pageid?: number; [key: string]: unknown }>; }
interface AthenaPushDocumentResponse { clinicaldocumentid: number; success?: boolean; }
```
