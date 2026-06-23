# Athena Health Sandbox: Getting Started from Just a PracticeId

**Last updated:** 2026-06-22  
**Sandbox base URL:** `https://api.preview.platform.athenahealth.com/v1/{practiceid}/`  
**Auth endpoint:** `POST https://api.preview.platform.athenahealth.com/oauth2/v1/token`

---

## Your Three Practice IDs

| PracticeId | Purpose |
|------------|---------|
| `195900` | Ambulatory testing — use this for most APIs (encounters, chart, patients, appointments) |
| `1128700` | Hospital / Health System testing — use for inpatient/discharge APIs |
| `80000` | PHR (patient portal) app testing — use for 3-legged OAuth / patient-facing flows |

**Default for Juno:** use `195900` for everything unless an endpoint is hospital-specific.

---

## Part 1 — Authentication First

### What credentials you need

Before making any API call you need:
- `CLIENT_ID` — issued when you register an app in the Athena developer portal at `developer.athenahealth.com`
- `CLIENT_SECRET` — issued alongside the client ID
- Token endpoint: `POST https://api.preview.platform.athenahealth.com/oauth2/v1/token`

### How authentication works (2-legged OAuth)

Athena uses OAuth 2.0 `client_credentials` flow for system-to-system calls. Credentials are sent as HTTP Basic Auth (Base64-encoded `client_id:client_secret`), NOT in the POST body. The token lasts 300 seconds (5 minutes).

### Exact curl command to get a token

```bash
export CLIENT_ID="your-client-id"
export CLIENT_SECRET="your-client-secret"

curl -s -X POST \
  "https://api.preview.platform.athenahealth.com/oauth2/v1/token" \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  -d "scope=athena/service/Athenanet.MDP.*" | jq .
```

### Expected token response

```json
{
  "access_token": "bSQeVaRd47Tnof8GWbDZTud9ghLP",
  "expires_in": "300"
}
```

Save the `access_token` — every subsequent API call needs:
```
Authorization: Bearer <access_token>
```

### Token caching tip

Tokens expire in 300 seconds. Request a fresh token before each test session, or implement a caching layer that re-requests when within 60 seconds of expiry.

---

## Part 2 — Bootstrap Sequence: Discovering IDs

You have a `practiceId` and a token. You have no other IDs. Here is the exact order to call APIs to bootstrap:

### Why you can't just guess IDs

Every clinical endpoint (encounter summary, medications, problems, lab results) requires at least a `patientid`. Some also require a `departmentid`. You must discover these from the API itself — there are no globally-published test patient IDs for the ambulatory sandbox.

### Bootstrap ladder (each step unlocks the next)

```
practiceId (you have this)
    │
    ├─► STEP 1: GET /departments       → departmentId list
    │
    ├─► STEP 2: GET /providers         → providerId list
    │
    ├─► STEP 3: GET /patients?limit=10 → patientId list
    │        OR GET /appointments/booked?startdate=...&enddate=... → patientId + appointmentId + encounterId
    │
    ├─► STEP 4: GET /patients/{patientid}              → patient demographics
    │       GET /appointments/{appointmentid}          → appointment detail + encounterId
    │
    └─► STEP 5: GET /chart/encounter/{encounterid}/summary   → encounter summary HTML (Juno's primary endpoint)
                GET /chart/{patientid}/medications           → medication list
                GET /chart/{patientid}/problems             → problem/diagnosis list
                GET /chart/{patientid}/labresults           → lab results
```

---

## Part 3 — Pre-seeded Test Data

### What Athena's sandbox does (and does not) provide

The sandbox practice `195900` is a **shared multi-tenant sandbox** used by all developers who register. Athena pre-loads it with test patients, encounters, and appointments, but **Athena does not publish a public list of specific patient IDs or encounter IDs** in their documentation.

What is known from SDK examples and developer community references:

| Resource | Known value | Notes |
|----------|-------------|-------|
| Practice ID (ambulatory) | `195900` | Shared by all sandbox developers |
| Practice ID (hospital) | `1128700` | Shared hospital sandbox |
| Practice ID (PHR/portal) | `80000` | 3-legged OAuth only |
| Test patient ID (80000 practice) | `14545` | PHR sandbox; may be stale — verify |
| Test patient username (80000) | `phrtest_[...]@mailinator.com` | 3-legged OAuth testing |
| Test patient password (80000) | `Password1` | 3-legged OAuth testing |
| Go SDK example patient ID | `"1"` | Used in `GetPatient("1")` in go-athenahealth README; try it |

**For practice 195900:** call `GET /patients?limit=10` (Step 3 below) — the API will return actual pre-seeded patient records with their IDs. You do not need to guess.

### Department IDs

Department IDs in practice `195900` are not published but can be retrieved with a single call (Step 1 below). The `showalldepartments=true` parameter returns inactive departments too. Always fetch departments via API — do not hardcode them.

---

## Part 4 — ID Requirements for Each Major Workflow

| Workflow | IDs needed | How to get them |
|----------|-----------|----------------|
| Encounter summary | `practiceId` + `encounterId` | From booked appointments list (encounterId is a field on the appointment) |
| Patient medications | `practiceId` + `patientId` | From patient list/search |
| Patient problems/diagnoses | `practiceId` + `patientId` | From patient list/search |
| Patient lab results | `practiceId` + `patientId` + `departmentId` | From patient list + departments list |
| List booked appointments | `practiceId` + `startdate` + `enddate` | Just the practiceId — dates are optional filters |
| Get one appointment | `practiceId` + `appointmentId` | From booked appointments list |
| Open appointment slots | `practiceId` + `departmentId` | From departments list |
| Post patient case document | `practiceId` + `patientId` + `departmentId` | From patient + departments |
| Post secure message | `practiceId` + `patientId` | From patient list |
| FHIR patient resources | `practiceId` (FHIR uses different IDs) | `GET /fhir/r4/Patient` |

---

## Part 5 — First 5 API Calls in Order

Set these variables once at the top of your Postman environment or shell session:

```bash
export BASE="https://api.preview.platform.athenahealth.com/v1/195900"
export TOKEN="<your access_token from Step 0>"
```

---

### Call 0 — Get a token (prerequisite)

```bash
curl -s -X POST \
  "https://api.preview.platform.athenahealth.com/oauth2/v1/token" \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  -d "scope=athena/service/Athenanet.MDP.*"
```

Save the `access_token` into `$TOKEN`.

---

### Call 1 — List departments (discover departmentIds)

```bash
curl -s -X GET \
  "$BASE/departments?showalldepartments=true&limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**What you get:** A list of departments with `departmentid`, `name`, `address`, `city`. Pick any `departmentid` from this list — you will use it in calls that require it (lab results, open appointment slots, patient case documents).

**No other IDs needed.** This call works with just practiceId + token.

---

### Call 2 — List providers (discover providerIds)

```bash
curl -s -X GET \
  "$BASE/providers?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**What you get:** Providers with `providerid`, `firstname`, `lastname`, `specialty`. Use providerIds to filter appointment searches.

**No other IDs needed.**

---

### Call 3 — Search/list patients (discover patientIds)

```bash
curl -s -X GET \
  "$BASE/patients?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**What you get:** A page of pre-seeded patients with `patientid`, `firstname`, `lastname`, `dob`, `departmentid`. Pick any `patientid` from this list.

If you want to search by name:
```bash
curl -s -X GET \
  "$BASE/patients?firstname=Jane&lastname=Doe&limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**No other IDs needed.** This is the key bootstrap call — after this you have patient IDs.

**Also try patient ID "1"** — the go-athenahealth SDK calls `GetPatient("1")` as its hello-world:

```bash
curl -s -X GET \
  "$BASE/patients/1" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

### Call 4 — List booked appointments (discover appointmentIds + encounterIds)

```bash
# List all booked appointments in a date range
curl -s -X GET \
  "$BASE/appointments/booked?startdate=01/01/2020&enddate=12/31/2025&limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**What you get:** Appointments with `appointmentid`, `patientid`, `departmentid`, `providerid`, `date`, `encounterid`, `encounterstatus`. This single call gives you ALL the IDs you need in one shot.

Key fields to note from the response:
- `appointmentid` — use for appointment detail calls
- `patientid` — use for chart calls (medications, problems, lab results)
- `departmentid` — use for document uploads and lab results
- `encounterid` — use directly for encounter summary (the most important ID for Juno)

If you get no results, try a wider date range: `startdate=01/01/2015&enddate=12/31/2026`.

---

### Call 5 — Get encounter summary (Juno's primary endpoint)

Once you have an `encounterid` from Call 4:

```bash
export ENCOUNTER_ID="<encounterid from Call 4>"

curl -s -X GET \
  "https://api.preview.platform.athenahealth.com/v1/195900/chart/encounter/$ENCOUNTER_ID/summary" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**What you get:** The full encounter summary with `summaryhtml` — the clinician's narrative including HPI, assessment, plan. This is the content Juno needs to translate into plain-language patient guidance.

Note: this endpoint path uses `/chart/encounter/` not `/appointments/` — it is different from the appointment endpoints above.

---

## Bonus Calls — After You Have Patient and Department IDs

Once you have `patientId` and `departmentId` from the calls above, these all work:

### Patient medications
```bash
curl -s -X GET \
  "$BASE/chart/$PATIENT_ID/medications" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Patient problems / diagnoses
```bash
curl -s -X GET \
  "$BASE/chart/$PATIENT_ID/problems" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Patient lab results (needs departmentId)
```bash
curl -s -X GET \
  "$BASE/chart/$PATIENT_ID/labresults?departmentid=$DEPT_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Patient demographics
```bash
curl -s -X GET \
  "$BASE/patients/$PATIENT_ID?showinsurance=true&showportalstatus=true" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### FHIR patient (for FHIR-based workflows)
```bash
curl -s -X GET \
  "https://api.preview.platform.athenahealth.com/fhir/r4/Patient?_count=10" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Token expired or missing | Re-run Call 0 to get a fresh token (expires in 300s) |
| `403 Forbidden` | Scope mismatch or practice not authorized | Verify `scope=athena/service/Athenanet.MDP.*` in token request |
| `404 Not Found` | Wrong practice ID in URL or endpoint path typo | Double-check URL: `v1/195900/...` not `v1/19590/...` |
| `400 Bad Request` | Missing required parameter | Check endpoint docs for required params (e.g., `startdate`/`enddate` for some appointment endpoints) |
| No results from patient list | Sandbox practice has no data yet | Try booked appointments with a wide date range first |
| `encounterid` is null on appointment | Appointment was scheduled but never checked in | Filter for `appointmentstatus=3` (checked out) or use encounters with `encounterstatus=CLOSED` |

---

## Summary Cheat Sheet

```
1. POST /oauth2/v1/token            → get Bearer token (expires 300s)
2. GET  /v1/195900/departments      → get departmentIds (no prereqs)
3. GET  /v1/195900/providers        → get providerIds (no prereqs)
4. GET  /v1/195900/patients         → get patientIds (no prereqs)
5. GET  /v1/195900/appointments/booked?startdate=...&enddate=... 
                                    → get appointmentIds + patientIds + encounterIds
6. GET  /v1/195900/chart/encounter/{encounterid}/summary 
                                    → get summaryHTML (Juno's primary pull)
7. GET  /v1/195900/chart/{patientid}/medications   → med list
8. GET  /v1/195900/chart/{patientid}/problems      → diagnoses
```

The key insight: **calls 2, 3, and 4 require only a practiceId.** Call 5 (booked appointments) returns encounterIds in one shot, avoiding the need to look up encounters separately.
