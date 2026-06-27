# Medications API

## What This Returns
The full medication list for a patient, including current and recently discontinued medications. Each medication includes the drug name, therapeutic class, structured sig (dosing), free-text sig, provider notes, patient notes, FDB medication ID, and a full event history (ORDER, ENTER, START, END).

## API Endpoint
```
GET /v1/195900/chart/{patientId}/medications?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "nomedicationsreported": false,
  "patientdownloadconsent": true,
  "lastupdated": "04/17/2026",
  "medications": [
    [
      {
        "medicationentryid": "H13544",
        "medicationid": 231084,
        "medication": "Claritin 10 mg tablet",
        "therapeuticclass": "ANTIHISTAMINES - 2ND GENERATION",
        "organclass": "BODY AS A WHOLE",
        "fdbmedicationid": "180342",
        "isdiscontinued": false,
        "issafetorenew": true,
        "isstructuredsig": true,
        "structuredsig": {
          "dosageaction": "Take",
          "dosagequantityvalue": 1,
          "dosagequantityunit": "tablet(s)",
          "dosagefrequencydescription": "every day",
          "dosagefrequencyvalue": 1,
          "dosagefrequencyunit": "per day",
          "dosageroute": "oral",
          "dosagedurationunit": "day"
        },
        "unstructuredsig": "Take 1 tablet every day by oral route.",
        "patientnote": "PRN allergies",
        "providernote": "Verified by API automation script",
        "source": "INTF-114607972",
        "events": [
          { "type": "ENTER", "eventdate": "12/29/2015", "userdisplayname": "INTF-114607972" }
        ]
      }
    ]
  ]
}
```

### Response Shape Note
`medications` is an **array of arrays** — each inner array is a group of entries for the same `medicationid` (e.g., multiple fills or entries for the same drug). Flatten the outer array when processing.

### Key Fields
| Field | Description |
|---|---|
| `medication` | Drug name including strength and form |
| `medicationid` | Athena medication ID |
| `fdbmedicationid` | First Databank (FDB) medication ID for drug database lookups |
| `therapeuticclass` | Drug class (e.g., "BETA-ADRENERGIC BLOCKING AGENTS") |
| `organclass` | Organ system class (e.g., "CARDIOVASCULAR SYSTEM") |
| `isdiscontinued` | `true` if the medication has been stopped |
| `isstructuredsig` | `true` if `structuredsig` is populated |
| `structuredsig` | Parsed dosing: action, quantity, unit, frequency, route |
| `unstructuredsig` | Human-readable dosing string (always present) |
| `patientnote` | Patient-facing note about the medication |
| `providernote` | Provider's internal note about the medication |
| `events[].type` | "ENTER", "ORDER", "START", "END" — tracks the medication lifecycle |
| `nomedicationsreported` | `true` if patient explicitly has no medications |

## Clinical Value for Juno: HIGH
Complete medication list with dosing. The combination of `therapeuticclass` (for drug class reasoning), `unstructuredsig` (for display), and `structuredsig` (for programmatic use) makes this highly usable. `providernote` and `patientnote` add clinical context beyond the drug itself. Key for Juno pre-appointment context and medication reconciliation.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get medications for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/medications?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- `medications` is an **array of arrays** — iterate both levels; the outer groups entries by `medicationid`.
- `isdiscontinued: false` includes both active and entries without an explicit stop — check `events[]` for END events to confirm active status.
- `isstructuredsig: false` means only `unstructuredsig` is available (no parsed dosing components).
- `stopreason` appears on discontinued entries (e.g., "adverse reaction", "end of course").
- `nomedicationsreported: true` means the patient was explicitly reviewed and has no medications — distinct from an empty array.
