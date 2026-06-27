# Assessment / Plan API

## What This Returns
The provider's Assessment/Plan text for a single encounter. The response contains a single `assessmenttext` field with the full A/P as a free-text string, often including ICD-10 codes and provider reasoning embedded inline. This is the same text that appears in the "Assessment / Plan" section of the encounter summary HTML.

## API Endpoint
```
GET /v1/195900/chart/encounter/{encounterId}/assessment
```
- **Required params**: none beyond the `encounterId` in the path
- **Auth**: Bearer token (OAuth2 client credentials)
- **Scope**: Encounter-scoped — one call per encounter

## Response Structure
```json
{
  "assessmenttext": "N31.0 - Calculus Patient is here for a routine office visit ...<br />R31.29 - Dr. Kevin Abdo Test 2<br />",
  "lastmodifiedby": "API-37090",
  "lastmodifieddatetime": "2026-06-24T22:32:50-04:00"
}
```

### Key Fields
| Field | Description |
|---|---|
| `assessmenttext` | Full A/P free text; may contain ICD codes, diagnoses, and provider narrative. HTML `<br />` tags used for line breaks. |
| `lastmodifiedby` | User/API that last modified the assessment |
| `lastmodifieddatetime` | ISO8601 timestamp of last modification |

## Clinical Value for Juno: MEDIUM
Provides the provider's direct clinical reasoning per encounter. Useful for understanding what diagnoses were active and what the plan was. However:
- Content is brief and not always well-structured in the API response
- The same content appears in `EncounterSummaries` `summaryhtml` (Assessment/Plan section), which is richer and includes associated diagnosis-order pairings
- For Juno's pre-appointment context, the Encounter Summary is preferred; this endpoint is useful for lightweight A/P-only retrieval

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get assessment for encounter 62283
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/encounter/62283/assessment" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Caveats
- Returns a 404 if the encounter has no assessment recorded yet.
- The `assessmenttext` field uses `<br />` for line breaks — strip HTML before displaying.
- ICD-10 codes appear inline in the text (e.g., "N31.0 - Calculus") but are not returned as structured fields from this endpoint; use `EncounterOrders` for structured diagnosis + order pairing.
- Encounter ID must be known in advance; get encounter IDs from `GET /v1/195900/chart/{patientId}/encounters`.
