# Lab Results API

## What This Returns
All lab results on file for a patient. Each result has a free-text `internalnote` (narrative description of the labs, often with full panel values) and an `analytes` array of structured individual lab values with reference ranges and abnormal flags. Some results are attachment-only (PDF linked) with empty `analytes`.

## API Endpoint
```
GET /v1/195900/chart/{patientId}/labresults?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "totalcount": 67,
  "results": [
    {
      "labresultid": 213245,
      "description": "lab result",
      "priority": "2",
      "createddatetime": "02/21/2026 12:56:13",
      "createddate": "02/21/2026",
      "attachmentexists": false,
      "internalnote": "Abnormal Results — Most Recent Labs",
      "analytes": [
        {
          "analyteid": 13965,
          "analytename": "glucose, fasting",
          "analytedatetime": "02/21/2026 00:00:00",
          "analytedate": "02/21/2026",
          "value": "142",
          "units": "mg/dL",
          "referencerange": "70-100",
          "abnormalflag": "high",
          "status": "high",
          "loinc": "4548-4",
          "description": "Hemoglobin A1c/Hemoglobin.total in Blood",
          "analytecreateduser": "API-35411"
        }
      ]
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `totalcount` | Total number of lab result records for this patient |
| `results[].labresultid` | Unique lab result ID |
| `results[].internalnote` | Free-text narrative (often a full formatted panel with all values) |
| `results[].attachmentexists` | `true` if there is a PDF attachment; body not returned in this call |
| `results[].analytes[]` | Structured individual test values |
| `analytes[].analytename` | Test name (e.g., "hemoglobin A1C", "LDL cholesterol") |
| `analytes[].value` | Numeric result value as string |
| `analytes[].units` | Units (e.g., "mg/dL", "mIU/L", "%") |
| `analytes[].referencerange` | Normal range string (e.g., "70-100", ">40") |
| `analytes[].abnormalflag` | "high", "low", "abnormal", or absent if normal |
| `analytes[].loinc` | LOINC code (only present on some analytes) |
| `analytes[].status` | Mirrors `abnormalflag` ("high", "low", "abnormal") |

## Clinical Value for Juno: HIGH
Two complementary data sources in one call:
1. **`internalnote`**: Often contains a full formatted panel (CMP, CBC, A1c, lipids, thyroid) as provider-readable text — excellent for Juno context building even without parsing analytes
2. **`analytes[]`**: Structured values with LOINC codes and abnormal flags enable programmatic analysis (e.g., "flag all high values", "trend A1c over time")

Most clinically rich sandbox data is in the `internalnote` for completeness; `analytes[]` contains the same values in structured form when populated.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get all lab results for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/labresults?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3. Get only recent results (add pagination)
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/labresults?departmentid=1&limit=10&offset=0" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- `analytes[]` is empty for many results — check `internalnote` for narrative data even when `analytes` is empty.
- `attachmentexists: true` means a PDF is linked; retrieving the PDF requires a separate document download call.
- `loinc` code is only present on some analytes — not all structured values are LOINC-coded.
- Results are sorted newest-first by default.
- With `totalcount` potentially in the dozens-to-hundreds, use `limit`/`offset` pagination for large charts.
- Some `internalnote` values are brief (e.g., "blood work from 1/24/26") with no actual values — filter by `analytes` presence for structured data.
