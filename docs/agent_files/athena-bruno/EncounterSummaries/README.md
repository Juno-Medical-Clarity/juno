# Encounter Summaries API

## What This Returns
A single `summaryhtml` field containing the complete, rendered HTML encounter summary for one encounter. This is the richest single source of clinical data in Athena — it combines every chart section into one document.

## API Endpoint
```
GET /v1/195900/chart/encounters/{encounterId}/summary
```
- **Note**: Path uses `encounters` (plural), unlike the Assessment and Orders endpoints which use `encounter` (singular)
- **Required params**: none beyond `encounterId` in the path
- **Auth**: Bearer token (OAuth2 client credentials)
- **Scope**: Encounter-scoped — one call per encounter

## Response Structure
```json
{
  "summaryhtml": "<html>...(full HTML)...</html>"
}
```

The `summaryhtml` field is a complete HTML document containing sections (in order):
| Section | HTML `sectionname` | Contents |
|---|---|---|
| Patient header | `Patient` | Name, DOB, age, sex, ID, appointment date/time, provider, department, insurance |
| Chief Complaint | `EncounterReason` | Free-text reason for visit |
| Patient Pharmacies | `PatientPrescriptionProvider` | List of patient's preferred pharmacies |
| Vitals | `Vitals` | Vital signs recorded at visit |
| Allergies | `AllergyList` | Full allergy list with reactions and severity |
| Medications | `MedicationList` | Current medication list with sig and source |
| Vaccines | `VaccineList` | Full immunization history with dates |
| Problems | `ProblemList` | Active problem list |
| Family History | `FamilyHistoryList` | Relatives + conditions with onset/death ages |
| Surgical History | `SurgicalHistoryList` | Procedures with dates |
| OB/GYN History | `OBGYNHistoryList`, `GPALHistory`, `HistoricalPregnancies` | OB-specific history (if applicable) |
| Genetic Screening | `GeneticScreeningInfectionHistory` | Y/N questionnaire responses |
| Prenatal Flowsheet | `PrenatalFlowsheet` | Per-visit prenatal data (if applicable) |
| Past Medical History | `PastMedicalHistory` | Medical history questionnaire answers |
| HPI | `HPI_Templated` | History of Present Illness narrative |
| ROS | `ReviewOfSystems` | Review of Systems narrative |
| Physical Exam | `PhysicalExam` | Physical examination findings |
| Assessment / Plan | `AssessmentPlan` | Provider A/P with diagnosis-order pairings |
| Sign-Off | `SignOff` | Encounter closure / sign-off status |

## Clinical Value for Juno: HIGHEST
This is the single most valuable API for Juno context. One call returns everything a provider wrote or signed for an encounter. The HTML is structured with consistent CSS class names (`sectionname` attributes) and can be parsed to extract individual sections. For Juno's pre-appointment context building, pulling the 2-3 most recent encounter summaries gives a near-complete clinical picture.

## Example curl
```bash
# 1. Get token
TOKEN=$(curl -s -X POST https://api.preview.platform.athenahealth.com/oauth2/v1/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=athena/service/Athenanet.MDP.*" \
  | jq -r '.access_token')

# 2. Get summary for encounter 62283
curl -s "https://api.preview.platform.athenahealth.com/v1/195900/chart/encounters/62283/summary" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.summaryhtml'
```

## Parsing Tips
- Each section is wrapped in `<div id="SUMMARYCONTAINER" sectionname="SectionName">` — use this to extract individual sections
- Section headers use `<span class="clinicalsubsubheading">Section Name</span>`
- Content is inside `<div id="SUMMARYCONTENT">`
- HPI, ROS, and Physical Exam free text is in `<div class="freetext">` blocks
- Assessment/Plan diagnoses are in `<div class="dxheadingsummary">` and orders in `<ul><li class="dxorderssummary">`
- Strip HTML tags for plain-text extraction; preserve `<br />` as newlines

## Caveats
- **Path is `encounters` (plural)** — `chart/encounters/{id}/summary`, not `chart/encounter/{id}/summary`
- Returns the summary in its current state; if the encounter is not yet closed, the Sign-Off section will say "Encounter not closed"
- OB-specific sections (Prenatal Flowsheet, Obstetric History, etc.) appear for all patients but are populated only for OB encounters
- `summaryhtml` can be very large (50-200KB) — avoid storing multiple in-memory simultaneously
- Encounter ID must be known in advance; get encounter IDs from `GET /v1/195900/chart/{patientId}/encounters`
