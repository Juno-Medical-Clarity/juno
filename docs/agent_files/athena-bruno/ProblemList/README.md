# Problem List API

## What This Returns
The active problem list for a patient: SNOMED-coded diagnoses with onset dates, status (ACUTE/CHRONIC), laterality, and per-event provider notes. Each problem can have multiple events (e.g., status changes, updates).

## API Endpoint
```
GET /v1/195900/chart/{patientId}/problems?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "totalcount": 11,
  "lastupdated": "06/23/2026",
  "lastmodifiedby": "API-35968",
  "lastmodifieddatetime": "2026-06-23T17:45:17-04:00",
  "problems": [
    {
      "problemid": 24266,
      "name": "Hypothyroidism",
      "displaynames": ["Hypothyroidism"],
      "code": "40930008",
      "codeset": "SNOMED",
      "lastmodifiedby": "API-35411",
      "lastmodifieddatetime": "2026-02-20T20:48:29-05:00",
      "events": [
        {
          "eventtype": "START",
          "startdate": "02/20/2026",
          "createddate": "02/20/2026",
          "onsetdate": "02/20/2026",
          "note": "Hypothyroidism",
          "status": "CHRONIC",
          "laterality": "BILATERAL",
          "createdby": "API-35411"
        }
      ]
    },
    {
      "problemid": 24158,
      "name": "Allergic asthma",
      "code": "389145006",
      "codeset": "SNOMED",
      "events": [
        {
          "eventtype": "START",
          "startdate": "11/22/2024",
          "onsetdate": "11/22/2024",
          "status": "CHRONIC",
          "laterality": "LEFT",
          "note": "note"
        }
      ]
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `problems[].problemid` | Athena internal problem ID |
| `problems[].name` | Problem display name |
| `problems[].code` | SNOMED CT code |
| `problems[].codeset` | Always "SNOMED" for this endpoint |
| `problems[].displaynames[]` | Array of display name variants |
| `events[].eventtype` | "START" (active), "RESOLVED", "DELETE" |
| `events[].status` | "ACUTE" or "CHRONIC" |
| `events[].onsetdate` | Date problem first started |
| `events[].laterality` | "LEFT", "RIGHT", "BILATERAL" (if applicable) |
| `events[].note` | Provider note for this event |
| `totalcount` | Total number of active problems |

## Clinical Value for Juno: HIGH
The active problem list is the most concise, structured summary of a patient's ongoing conditions. SNOMED codes enable automated reasoning and cross-referencing. The `status` field (ACUTE vs CHRONIC) and `onsetdate` add clinical staging. Per-event provider notes add context. This is a core data source for any Juno pre-appointment briefing.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get problem list for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/problems?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- Each `problems[]` entry can have multiple `events[]` — use the most recent event for current status.
- `status` (ACUTE/CHRONIC) and `laterality` are optional per event — check for presence before using.
- Problems with `eventtype: "RESOLVED"` or `"DELETE"` are no longer active; filter to `"START"` events for the active list.
- SNOMED codes are in `code` (not a nested object) — unlike some other Athena APIs.
- `displaynames` can differ from `name` (e.g., if the problem was mapped to a different display synonym).
