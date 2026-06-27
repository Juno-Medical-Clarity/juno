# Vitals API

## What This Returns
All vital sign readings for a patient across all encounters, grouped by vital type (e.g., BLOODPRESSURE, TEMPERATURE). Each reading is LOINC-coded and tied to a specific encounter (`sourceid`), with the date the reading was taken. Multiple readings of the same vital type from the same encounter are grouped together.

## API Endpoint
```
GET /v1/195900/chart/{patientId}/vitals?departmentid={departmentId}
```
- **Required params**: `departmentid`
- **Auth**: Bearer token (OAuth2 client credentials)

## Response Structure
```json
{
  "totalcount": 2,
  "vitals": [
    {
      "key": "BLOODPRESSURE",
      "abbreviation": "BP",
      "ordering": 0,
      "readings": [
        [
          {
            "vitalid": 23440410,
            "clinicalelementid": "VITALS.BLOODPRESSURE.DIASTOLIC",
            "codedescription": "Diastolic blood pressure",
            "code": "8462-4",
            "codeset": "LOINC",
            "value": "73",
            "readingtaken": "01/01/2016",
            "sourceid": 61964,
            "source": "FLOWSHEET",
            "isgraphable": true,
            "createdby": "API-34297",
            "createddate": "10/10/2025 04:52:22",
            "readingid": 1
          },
          {
            "vitalid": 23440409,
            "clinicalelementid": "VITALS.BLOODPRESSURE.SYSTOLIC",
            "codedescription": "Systolic blood pressure",
            "code": "8480-6",
            "codeset": "LOINC",
            "value": "120",
            "readingtaken": "01/01/2016",
            "sourceid": 61964
          }
        ]
      ]
    },
    {
      "key": "TEMPERATURE",
      "abbreviation": "T",
      "readings": [
        [
          {
            "clinicalelementid": "VITALS.TEMPERATURE",
            "codedescription": "Body temperature",
            "code": "8310-5",
            "codeset": "LOINC",
            "value": "98.6",
            "unit": "F",
            "readingtaken": "01/01/2016",
            "sourceid": 61964
          }
        ]
      ]
    }
  ]
}
```

### Key Fields
| Field | Description |
|---|---|
| `vitals[].key` | Vital type key (e.g., "BLOODPRESSURE", "TEMPERATURE", "WEIGHT", "HEIGHT", "PULSE", "O2SAT", "RESPIRATIONS") |
| `vitals[].abbreviation` | Short display label (e.g., "BP", "T") |
| `vitals[].readings[][]` | Outer array = encounter groupings; inner array = component readings for that vital at that encounter |
| `readings[][].value` | Numeric value as string |
| `readings[][].unit` | Unit (e.g., "F", "mmHg", "kg"); often absent for BP (unit implicit) |
| `readings[][].code` | LOINC code for the specific component |
| `readings[][].codedescription` | Human-readable LOINC description |
| `readings[][].readingtaken` | Date the vital was recorded (format: MM/DD/YYYY) |
| `readings[][].sourceid` | Encounter/flowsheet ID this reading belongs to |
| `readings[][].isgraphable` | `true` if the value can be trended over time |
| `totalcount` | Number of distinct vital type groups returned |

### Common Vital Keys and LOINC Codes
| Key | Component | LOINC |
|---|---|---|
| BLOODPRESSURE | Systolic | 8480-6 |
| BLOODPRESSURE | Diastolic | 8462-4 |
| TEMPERATURE | Body temperature | 8310-5 |
| PULSE | Heart rate | 8867-4 |
| RESPIRATIONS | Respiratory rate | 9279-1 |
| O2SAT | Oxygen saturation | 59408-5 |
| WEIGHT | Body weight | 29463-7 |
| HEIGHT | Body height | 8302-2 |

## Clinical Value for Juno: MEDIUM
Provides numeric trends across encounters. Most useful for:
- Trending BP over time in hypertensive patients
- Checking recent O2 saturation in pulmonary patients
- Weight trends for obesity management
Vitals are less narrative than other chart sections but complement the encounter summaries with objective numbers. The LOINC coding enables standardized interpretation.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get vitals for patient 60178
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/60178/vitals?departmentid=1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- `departmentid` is required.
- `readings` is an **array of arrays**: outer = encounter groupings (by `sourceid`), inner = components of that vital at that encounter (e.g., systolic + diastolic are two elements in the inner array for one BP reading).
- `unit` is absent for blood pressure components (value is implicitly mmHg).
- `readingtaken` date is when the vital was clinically recorded, which may differ from `createddate` (when it was entered in the system).
- Sandbox data may have limited vital sign entries; production data will have readings across all encounters.
- To get vitals for a specific encounter only, use the encounter summary API instead (which embeds vitals in the `Vitals` section of the HTML).
