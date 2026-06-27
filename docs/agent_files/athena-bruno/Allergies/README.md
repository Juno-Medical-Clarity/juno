# Allergies API

## What This Returns
The complete allergy list for a patient: allergen names, reaction details (symptom name + SNOMED code + severity), onset date, provider notes, RxNorm codes, and allergy categories (food, medication, environmental). Also includes a section-level free-text note and an `nkda` boolean (No Known Drug Allergies).

## API Endpoint
```
GET /v1/195900/chart/{patientId}/allergies?departmentid={departmentId}
```
- **Required params**: `departmentid` (required by Athena to scope the chart)
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "nkda": false,
  "sectionnote": "Free-text note on the whole allergy section",
  "allergies": [
    {
      "id": "8715",
      "allergenid": 12349,
      "allergenname": "Anticholinergics - Other",
      "categories": ["medication"],
      "onsetdate": "01/15/2026",
      "note": "allergic to anticholinergics",
      "rxnormcode": "1309458",
      "rxnormdescription": "Substance with muscarinic receptor antagonist...",
      "reactions": [
        {
          "reactionname": "rash",
          "snomedcode": 271807003,
          "severity": "moderate severity",
          "severitysnomedcode": 6736007
        }
      ],
      "lastmodifiedby": "API-35804",
      "lastmodifieddatetime": "2026-03-27T02:57:45-04:00"
    }
  ],
  "lastupdated": "04/17/2026",
  "lastmodifiedby": "API-34748",
  "lastmodifieddatetime": "2026-04-17T01:22:46-04:00"
}
```

### Key Fields
| Field | Description |
|---|---|
| `allergies[].allergenname` | Human-readable allergen name |
| `allergies[].allergenid` | Athena internal allergen ID |
| `allergies[].rxnormcode` | RxNorm code (not always present) |
| `allergies[].categories` | `["food"]`, `["medication"]`, or both |
| `allergies[].reactions[].reactionname` | Reaction symptom (e.g., "rash") |
| `allergies[].reactions[].snomedcode` | SNOMED code for the reaction |
| `allergies[].reactions[].severity` | "mild severity", "moderate severity", "severe" |
| `allergies[].note` | Provider free-text note per allergy |
| `allergies[].onsetdate` | Date allergy was first noted |
| `nkda` | `true` if patient has no known drug allergies |
| `sectionnote` | Section-level provider note |

## Clinical Value for Juno: HIGH
Critical for patient safety. Juno should surface this before any medication recommendation or prescription context. The SNOMED-coded reactions and RxNorm codes enable structured lookups; the free-text `note` field adds provider context. `nkda: true` is a safe signal to display explicitly.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get allergies for patient 60178 in dept 1
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/allergies?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required; request returns an error without it.
- `rxnormcode` is not always populated (absent for some allergens).
- `reactions[]` array can be empty — allergy is still recorded, just without a documented reaction.
- Allergen categories can span both `food` and `medication` (e.g., lactose).
- `nkda: false` does not mean allergies exist — it means NKDA status was not explicitly confirmed.
