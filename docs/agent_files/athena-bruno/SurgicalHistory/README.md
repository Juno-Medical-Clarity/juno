# Surgical History API

## What This Returns
The patient's past surgical and procedure history: a list of named procedures with dates, plus a section-level free-text `sectionnote` for additional narrative context (e.g., details about a specific surgery not captured in the structured procedure list).

## API Endpoint
```
GET /v1/195900/chart/{patientId}/surgicalhistory?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "sectionnote": "Uncomplicated laparoscopic appendectomy",
  "notelastmodifieddatetime": "02/22/26 15:06:10",
  "notelastmodifiedby": "API-35411",
  "procedures": [
    {
      "procedureid": 6512,
      "description": "tonsilectomy/adenoids",
      "proceduredate": "03/2013",
      "source": "historical",
      "lastmodifiedby": "INTF-114607978",
      "lastmodifieddatetime": "07/21/25 22:55:47"
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `procedures[].procedureid` | Athena internal procedure ID |
| `procedures[].description` | Procedure name (free-text, not coded) |
| `procedures[].proceduredate` | Date of procedure; may be month/year only ("03/2013") |
| `procedures[].source` | "historical" for patient-reported, or a system/user ID |
| `sectionnote` | Free-text note for the whole section (often contains details not in `procedures[]`) |

## Clinical Value for Juno: MEDIUM
Useful background for anesthesia risk, surgical planning, and understanding the patient's clinical history. The `sectionnote` often contains details not captured in the structured procedure list (e.g., "Uncomplicated laparoscopic appendectomy"). The procedure names are free-text, not CPT or SNOMED coded, which limits automated processing but preserves provider language.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get surgical history for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/surgicalhistory?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- Procedure names (`description`) are free-text — no CPT or SNOMED coding.
- `proceduredate` is a string and may be partial (year only, month/year only, or full date).
- `sectionnote` may contain the most clinically important information — always include it alongside the `procedures[]` array.
- A missing or empty `procedures[]` array does not mean no surgical history — check `sectionnote` for narrative entries.
- `source: "historical"` indicates the data was entered from patient-reported history, not from an operative report.
