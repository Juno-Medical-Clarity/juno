# Medical History API

## What This Returns
Past medical history as a structured Y/N questionnaire. Each entry is a condition/question with a yes/no answer, an optional provider note, and timestamps. Also includes a section-level `sectionnote` for free-text additions.

## API Endpoint
```
GET /v1/195900/chart/{patientId}/medicalhistory?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "sectionnote": "test",
  "notelastmodifieddatetime": "03/26/26 03:18:54",
  "notelastmodifiedby": "API-35804",
  "questions": [
    {
      "questionid": 124,
      "question": "Coronary Artery Disease",
      "answer": "Y",
      "note": "Mild Intermittent",
      "createdby": "API-35804",
      "createddatetime": "03/26/26 06:37:51",
      "lastmodifiedby": "API-35804",
      "lastmodifieddatetime": "03/26/26 06:37:51"
    },
    {
      "questionid": 123,
      "question": "Asthma",
      "answer": "Y",
      "note": "Mild Intermittent",
      "createdby": "INTF-114607978",
      "createddatetime": "07/21/25 22:55:47",
      "lastmodifiedby": "API-35804",
      "lastmodifieddatetime": "03/26/26 04:34:52"
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `questions[].questionid` | Athena's internal question ID (maps to a standard condition list) |
| `questions[].question` | Condition name (e.g., "Coronary Artery Disease", "Asthma", "Sea Sickness") |
| `questions[].answer` | "Y" or "N" |
| `questions[].note` | Provider free-text note for this condition (e.g., "Mild Intermittent") |
| `sectionnote` | Free-text note for the entire section |

## Clinical Value for Juno: MEDIUM
Provides a quick checklist of past medical history flagged by the provider. Useful background context for Juno, especially for chronic conditions not yet on the active problem list. The structured Y/N format is easy to parse. However:
- Only "Y" answers are typically returned (unanswered questions are omitted)
- The condition names come from Athena's internal questionnaire — not SNOMED coded
- Active ongoing conditions are better represented in ProblemList (which is SNOMED-coded)

Best use: supplement the Problem List with historical conditions the provider explicitly flagged.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get medical history for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/medicalhistory?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- Only answered questions are returned; a missing `questionid` does not mean "N" — it means not yet answered.
- Condition names are Athena-internal questionnaire labels, not SNOMED codes.
- `note` per question is optional and often absent.
- This is distinct from the active Problem List — a condition here may be historical/resolved.
