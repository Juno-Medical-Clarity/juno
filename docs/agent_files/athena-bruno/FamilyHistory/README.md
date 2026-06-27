# Family History API

## What This Returns
Structured family history by relative (Mother, Father, Sibling, etc.), with each relative's conditions listed as SNOMED-coded problems including onset age and, if applicable, the age at death.

## API Endpoint
```
GET /v1/195900/chart/{patientId}/familyhistory?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "historyunknown": false,
  "relatives": [
    {
      "relation": "Mother",
      "relationkeyid": 1,
      "problems": [
        {
          "problemid": 6028,
          "description": "History of depression",
          "snomedcode": 161469008,
          "onsetage": 60,
          "diedofage": null,
          "lastmodifiedby": "INTF-114607978",
          "lastmodifieddatetime": "07/21/2025 22:55:45"
        },
        {
          "problemid": 6029,
          "description": "Carcinoma of breast",
          "snomedcode": 254838004,
          "onsetage": 68,
          "diedofage": 72,
          "lastmodifiedby": "INTF-114607978",
          "lastmodifieddatetime": "07/21/2025 22:55:45"
        }
      ]
    },
    {
      "relation": "Father",
      "relationkeyid": 1,
      "problems": [
        {
          "problemid": 6031,
          "description": "Carcinoma of prostate",
          "snomedcode": 254900004,
          "onsetage": 75,
          "diedofage": 82
        }
      ]
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `historyunknown` | `true` if patient reports no family history information available |
| `relatives[].relation` | Relation type ("Mother", "Father", "Sister", "Brother", etc.) |
| `relatives[].problems[].description` | Condition name |
| `relatives[].problems[].snomedcode` | SNOMED CT code for the condition |
| `relatives[].problems[].onsetage` | Age at which the relative developed the condition |
| `relatives[].problems[].diedofage` | Age at death (if applicable; absent if not deceased or not documented) |
| `relatives[].problems[].problemid` | Athena internal problem ID |

## Clinical Value for Juno: MEDIUM
Useful background context for hereditary risk assessment (e.g., cancer screening discussions, cardiovascular risk). SNOMED codes make this structured and queryable. Not typically needed in real-time clinical decision support but valuable for comprehensive pre-visit context. Especially relevant when a patient has hereditary cancer syndromes or strong family cardiac history.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get family history for patient 60178 in dept 1
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/familyhistory?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- `historyunknown: true` means the whole section is unknown — `relatives` will be empty.
- `diedofage` is only present when the relative is deceased and the age was documented; its absence does not mean the relative is still alive.
- `onsetage` is an integer (age in years), not a date.
- Some sandbox patients have no family history entered — the `relatives` array will be empty even if `historyunknown` is false.
