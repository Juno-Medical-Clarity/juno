# ClinicalDocumentContent

Actual text content of Athena Health clinical documents (SOAP notes, referral letters, etc.), downloaded via the Athena Health Preview API.

---

## API Endpoint

```
GET /v1/{practiceId}/patients/{patientId}/documents/clinicaldocument/{clinicaldocumentId}
```

**Method:** `GET`  
**Auth:** Bearer token (OAuth2 client_credentials)  
**Base URL:** `https://api.preview.platform.athenahealth.com`

### Request example

```
GET /v1/195900/patients/60178/documents/clinicaldocument/204457
Authorization: Bearer <access_token>
```

No additional query parameters are required.

---

## Response structure

The endpoint returns a **JSON array** with one object:

```json
[
  {
    "clinicaldocumentid": 204457,
    "documentdescription": "clinical document",
    "documentclass": "CLINICALDOCUMENT",
    "documentsource": "INTERFACE",
    "status": "REVIEW",
    "departmentid": "1",
    "createddatetime": "2025-11-28T22:45:30-05:00",
    "observationdate": "11/28/2025",
    "internalnote": "SOAP note from SIVIA - Generated 2025-11-28 21:20",
    "assignedto": "CRUICKSHANK HEALTH CARE STAFF",
    "documentroute": "FAX",
    "lastmodifieddatetime": "2026-04-16T02:32:41-04:00",
    "lastmodifieduser": "API-34748",
    "createduser": "API-34755",
    "priority": "1",
    "pages": [],
    "documentdata": "Reason for Appointment\n1. Urgent evaluation of erratic hemodynamic..."
  }
]
```

### Key fields

| Field | Type | Description |
|-------|------|-------------|
| `documentdata` | string | **The actual clinical text** — full SOAP note, referral letter, or clinical summary. Plain text. Present when document was created electronically (e.g. INTERFACE source). |
| `pages` | array | List of page objects for **image-based** (scanned) documents. If non-empty and `documentdata` is absent, the document is a scan with no text representation available via this endpoint. |
| `documentsource` | string | `"INTERFACE"` = created electronically (typically has `documentdata`). `"SCAN"` = scanned physical doc (typically has `pages` only). |
| `documentclass` | string | Always `"CLINICALDOCUMENT"` for clinical documents. |
| `internalnote` | string | Short description of the document written at creation time (e.g. `"SOAP note from SIVIA - Generated 2025-11-28 21:20"`). |

---

## Document types observed

- **Electronically created (INTERFACE):** Returns `documentdata` as structured plain text with sections like `Reason for Appointment`, `History of Present Illness`, `Subjective`, `Objective`, `Assessment`, `Plan`, `Billing & Documentation`, `Health Maintenance`.
- **Image-based (scanned):** Returns `pages` array with page metadata but no `documentdata` text.

---

## Getting more documents

### Step 1 — Get a Bearer token

```bash
curl -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "${CLIENT_ID}:${CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*"
```

The `access_token` field in the response is used as the Bearer token.

### Step 2 — List clinical document IDs for a patient

```bash
curl -H "Authorization: Bearer <token>" \
  "https://api.preview.platform.athenahealth.com/v1/195900/patients/60178/documents/clinicaldocument?departmentid=1"
```

Returns a `clinicaldocuments` array with `clinicaldocumentid` values (no `documentdata`).

### Step 3 — Fetch actual content for a specific document

```bash
curl -H "Authorization: Bearer <token>" \
  "https://api.preview.platform.athenahealth.com/v1/195900/patients/60178/documents/clinicaldocument/204457"
```

The `documentdata` field in the response contains the full clinical text.

---

## Example curl command (full flow)

```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "0oa130qx2jmWVBcQr298:${CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 2. Fetch document content
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.preview.platform.athenahealth.com/v1/195900/patients/60178/documents/clinicaldocument/204457" \
  | python3 -m json.tool
```

---

## Files in this directory

| File | Format | Description |
|------|--------|-------------|
| `{id}_clinical_document.txt` | Plain text | Full SOAP note / clinical letter |
| `{id}_clinical_document_meta.json` | JSON | Metadata only (image-based/scanned document with `pages`) |
| `{id}_clinical_document.html` | HTML | HTML-formatted document (if applicable) |
| `{id}_clinical_document.pdf` | PDF | Decoded PDF (if content was base64 encoded) |
| `manifest.json` | JSON | Index of all downloaded documents with file paths |

---

## Content quality

The `documentdata` field from INTERFACE-sourced documents contains high-quality structured clinical narratives including:
- Chief complaint and reason for appointment
- History of Present Illness (HPI) with detailed clinical context
- Allergies and medications list
- Review of Systems (ROS)
- Objective findings (vitals, physical exam, labs)
- Assessment with ICD-10 codes and clinical reasoning
- Plan (diagnostic, therapeutic, follow-up)
- Billing/E&M code justification
- Health maintenance gaps and preventive care recommendations

These documents are directly usable for AI medical assistant context without further preprocessing.

---

## Sandbox credentials (preview environment)

- BASE_URL: `https://api.preview.platform.athenahealth.com`
- PRACTICE_ID: `195900`
- CLIENT_ID: `0oa130qx2jmWVBcQr298`
- CLIENT_SECRET: stored in `../.env` as `ATHENA_HEALTH_CLIENT_SECRET`
- Test patient IDs: 60178, 60179, 60180, 60181, 60182, 60183, 60184
