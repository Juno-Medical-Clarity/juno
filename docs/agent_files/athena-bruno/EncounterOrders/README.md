# Encounter Orders API

## What This Returns
All orders placed during a specific encounter, grouped by diagnosis. Each group contains the diagnosis (SNOMED + ICD-10 coded), and an array of orders linked to that diagnosis. Orders include type (lab, imaging, consult, referral), ordering provider, status, description, and a `providernote` explaining why the order was placed.

## API Endpoint
```
GET /v1/195900/chart/encounter/{encounterId}/orders
```
- **Required params**: none beyond `encounterId` in the path
- **Auth**: Bearer token (OAuth2 client credentials)
- **Scope**: Encounter-scoped — one call per encounter

## Response Structure
```json
{
  "items": [
    {
      "diagnosis": "chest pain",
      "diagnosissnomed": 29857009,
      "diagnosisicd": [
        { "code": "R07.9", "description": "Chest pain, unspecified", "codeset": "ICD10" }
      ],
      "orders": [
        {
          "orderid": 207200,
          "ordertype": "Consult",
          "ordertypename": "interventional cardiology referral",
          "ordergenusname": "CONSULTATION WITH A SPECIALIST",
          "status": "REVIEW",
          "priority": 2,
          "description": "interventional cardiology referral",
          "providernote": "Referral for chest pain",
          "orderingprovider": "abricker1",
          "dateordered": "01/16/2026 08:48 PM",
          "futuresubmitdate": "2026-12-29",
          "documentationonly": false,
          "diagnosislist": [
            {
              "diagnosiscode": { "code": "29857009", "codeset": "SNOMED", "description": "chest pain" },
              "snomedicdcodes": [{ "code": "R079", "codeset": "ICD10", "description": "Chest pain, unspecified" }]
            }
          ],
          "assigneduser": "abricker1",
          "ordertypeid": 269090,
          "ordergenusid": 277,
          "lastmodifiedby": "API-34344",
          "lastmodifieddatetime": "2026-01-16T20:48:23-05:00"
        }
      ]
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `items[].diagnosis` | Diagnosis name (free-text) |
| `items[].diagnosissnomed` | SNOMED code for the diagnosis |
| `items[].diagnosisicd[]` | ICD-10 codes for the diagnosis |
| `items[].orders[].orderid` | Unique order ID |
| `items[].orders[].ordertype` | Order type: "Consult", "Lab", "Imaging", etc. |
| `items[].orders[].ordertypename` | Specific order name (e.g., "interventional cardiology referral") |
| `items[].orders[].status` | "REVIEW", "PEND", "CLOSED", etc. |
| `items[].orders[].providernote` | Provider's reason/note for the order |
| `items[].orders[].orderingprovider` | Username of the ordering provider |
| `items[].orders[].dateordered` | When the order was created |
| `items[].orders[].documentationonly` | `true` if order is for documentation only (not submitted) |

## Clinical Value for Juno: HIGH
Shows what was ordered and the clinical reasoning behind it (`providernote`). Useful for understanding the clinical trajectory of an encounter — what the provider was investigating, treating, or referring out. The SNOMED + ICD-10 coded diagnoses make this queryable. Pairs well with the Assessment/Plan text.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get orders for encounter 62283
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/encounter/62283/orders" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- Returns an empty `items` array (not a 404) if no orders were placed for the encounter.
- `providernote` is optional and may be absent on some orders.
- `diagnosisicd` array can be empty if no ICD-10 code was mapped (only SNOMED in `diagnosiscode`).
- Encounter ID must be known in advance; get encounter IDs from `GET /v1/195900/chart/{patientId}/encounters`.
- `documentationonly: true` orders were not actually submitted to a lab/facility — treat as notes only.
