# Tasks: SP3 — Athena Health Integration

**Sub-project:** SP3
**Branch:** `athena_health_part1`
**PRD source:** `docs/agent_files/tasks/2026-06-27/03-athena-health-integration/PRD.md`
**Fresh authoring** — no prior TASKS.md existed.

---

### Task 1 — Create `backend/data/athena-encounters-manifest.json`

**Traced to PRD §4-C**

- **Files:** `/root/projects/juno/backend/data/athena-encounters-manifest.json` *(new file — create `backend/data/` directory too)*

- **Changes:** Create the file with the exact JSON below. The `preview_content` for `p60183_e62021` is the plain-text rendering obtained by calling `AthenaClient._strip_html()` on the `summaryhtml` field of `docs/agent_files/athena-bruno/EncounterSummaries/sample_p60183_e62021_02.json` (first 3000 characters of stripped output).

```json
{
  "source_kind": "athena_encounter",
  "label": "Athena — Encounters",
  "tab_id": "athena-encounter",
  "preview_entry_id": "p60183_e62021",
  "entries": [
    {
      "id": "p60183_e62021",
      "label": "Gary 78yo M — Chest Pain / Dyspnea",
      "practice_id": "195900",
      "patient_id": "60183",
      "encounter_id": "62021",
      "api_path": "/v1/195900/chart/encounters/62021/summary",
      "is_preview": true,
      "preview_content": "PatientName SANDBOXTEST, GARY (78yo, M) ID# 60183 Appt. Date/Time 11/10/2025 01:00PM DOB 04/18/1948 Service Dept. Cruickshank HEALTH CARE Provider BRICKER, ADAM Insurance Med Primary: CIGNA HEALTHCARE (HMO) Insurance # : TEST123456 Chief ComplaintNone recorded.VitalsNone recorded.AllergiesAMIODARONE: Other (Severe) - increase Liver Function Tests LEXAPRO: Rash (Mild) PHENERGAN: Other (Moderate severity) - dystonic reaction MedicationsName Date Source Abilify 5 mg tablet Take 1 tablet(s) every day by oral route. 12/29/15   entered INTF-114612150 allopurinol 100 mg tablet Take 1 tablet(s) 3 times a day by oral route. 12/29/15   entered INTF-114612150 atorvastatin 40 mg tablet Take 1 tablet(s) every day by oral route., start 09/18/2016 09/18/16   started INTF-114612150 buPROPion HCl SR 150 mg tablet,12 hr sustained-release Take 1 tablet(s) twice a day by oral route. 12/29/15   entered INTF-114612150 cloNIDine HCl 0.1 mg tablet Take 1 tablet(s) twice a day by oral route. 12/29/15   entered INTF-114612150 Exforge 10 mg-320 mg tablet Take 1 tablet(s) every day by oral route., start 12/17/2016 12/17/16   started INTF-114612150 gabapentin 300 mg capsule Take 1 capsule(s) every day by oral route at bedtime. 01/07/16   entered INTF-114612150 Sotalol AF 80 mg tablet Take 1 tablet(s) twice a day by oral route. 12/29/15   entered INTF-114612150 zolpidem 10 mg tablet Take 1 tablet(s) every day by oral route at bedtime. 12/29/15   entered INTF-114612150 VaccinesVaccine Type Date Amt. Route Site NDC Lot # Mfr. Exp. Date VIS VIS Given Vaccinator COVID-19 COVID-19, mRNA, LNP-S, bivalent booster, PF, 30 mcg/0.3 mL dose (Pfizer-BioNTech) 10/27/25  0.3 mL Intramuscular Deltoid, Left FF2588 Pfizer, Inc Diphtheria, Tetanus Td(adult) 09/19/13  999 Influenza influenza, injectable, quadrivalent, preservative free 10/02/23  0.5 mL Intramuscular Deltoid, Left 946605 Seqirus influenza, seasonal, injectable 09/18/17  999 Problems Hyperlipidemia - Onset: 08/08/2016  Gout - Onset: 09/20/2018  Depressive disorder - Onset: 08/08/2016  Restless legs syndrome - Onset: 08/08/2016  Essential hypertension - Onset: 08/08/2016  Coronary atherosclerosis - Onset: 08/08/2016 - RCA stent, LAD disease  Congenital anomaly of peripheral blood vessel - Onset: 08/08/2016  Patient post percutaneous transluminal coronary angioplasty - Onset: 08/08/2016  Anxiety - Onset: 09/20/2018  Diverticular disease of colon - Onset: 08/08/2016 Social HistoryGender Identity and LGBTQ IdentityGender identity: Identifies as Male Assigned sex at birth: Male Pronouns: he/him Sexual orientation: Bisexual ScreeningNone recorded.ROS None recorded.Physical ExamNone recorded.Assessment / Plan1. Chest pain R07.9: Chest pain, unspecified INTERVENTIONAL CARDIOLOGY REFERRAL Reason for Referral: Chest pain, unspecified INTERVENTIONAL CARDIOLOGY REFERRAL Reason for Referral: Chest pain and shortness of breath requiring interventional cardiology assessment CARDIOLOGIST REFERRAL Reason for Referral: Chest pain, unspecified INTE"
    },
    {
      "id": "p60183_e61456",
      "label": "Gary 78yo M — Encounter 61456",
      "practice_id": "195900",
      "patient_id": "60183",
      "encounter_id": "61456",
      "api_path": "/v1/195900/chart/encounters/61456/summary",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "p60178_e62281",
      "label": "Donna 41F — Encounter 62281",
      "practice_id": "195900",
      "patient_id": "60178",
      "encounter_id": "62281",
      "api_path": "/v1/195900/chart/encounters/62281/summary",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "p60178_e62283",
      "label": "Donna 41F — Encounter 62283",
      "practice_id": "195900",
      "patient_id": "60178",
      "encounter_id": "62283",
      "api_path": "/v1/195900/chart/encounters/62283/summary",
      "is_preview": false,
      "preview_content": null
    }
  ],
  "sandbox_note": "Only 4 real encounter IDs are available in the Athena sandbox. This manifest will grow as additional encounters are generated or the sandbox is expanded."
}
```

- **Acceptance criteria:** Run from `backend/`:
  ```bash
  python -c "import json; m = json.load(open('data/athena-encounters-manifest.json')); assert len(m['entries']) == 4; assert any(e['is_preview'] for e in m['entries']); assert m['preview_entry_id'] == 'p60183_e62021'; assert m['source_kind'] == 'athena_encounter'; print('OK')"
  ```
  Must print `OK` and exit 0.

---

### Task 2 — Create `backend/data/athena-clinicaldocs-manifest.json`

**Traced to PRD §4-D**

- **Files:** `/root/projects/juno/backend/data/athena-clinicaldocs-manifest.json` *(new file)*

- **Changes:** Create the file with the exact JSON below. 100 entries total, one with `is_preview: true` (`60178_204552`). The `preview_content` for that entry is the first 2000 characters of `docs/agent_files/athena-bruno/ClinicalDocumentContentAll/60178_204552/document.txt`. All other 99 entries have `"is_preview": false, "preview_content": null`. Directory names follow `{patient_id}_{document_id}` format; patient 60178 is labelled "Donna 41F", patients 60179–60182 are labelled "Sandbox Patient {patient_id}".

```json
{
  "source_kind": "athena_clinical_doc",
  "label": "Athena — Clinical Docs",
  "tab_id": "athena-clinical-doc",
  "preview_entry_id": "60178_204552",
  "entries": [
    {
      "id": "60178_204457",
      "label": "Donna 41F — Doc 204457",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204457",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204457",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204458",
      "label": "Donna 41F — Doc 204458",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204458",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204458",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204460",
      "label": "Donna 41F — Doc 204460",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204460",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204460",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204461",
      "label": "Donna 41F — Doc 204461",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204461",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204461",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204462",
      "label": "Donna 41F — Doc 204462",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204462",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204462",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204463",
      "label": "Donna 41F — Doc 204463",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204463",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204463",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204464",
      "label": "Donna 41F — Doc 204464",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204464",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204464",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204465",
      "label": "Donna 41F — Doc 204465",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204465",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204465",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204466",
      "label": "Donna 41F — Doc 204466",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204466",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204466",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204467",
      "label": "Donna 41F — Doc 204467",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204467",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204467",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204468",
      "label": "Donna 41F — Doc 204468",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204468",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204468",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204469",
      "label": "Donna 41F — Doc 204469",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204469",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204469",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204470",
      "label": "Donna 41F — Doc 204470",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204470",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204470",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204471",
      "label": "Donna 41F — Doc 204471",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204471",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204471",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204473",
      "label": "Donna 41F — Doc 204473",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204473",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204473",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204485",
      "label": "Donna 41F — Doc 204485",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204485",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204485",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204486",
      "label": "Donna 41F — Doc 204486",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204486",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204486",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204487",
      "label": "Donna 41F — Doc 204487",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204487",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204487",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204488",
      "label": "Donna 41F — Doc 204488",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204488",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204488",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204489",
      "label": "Donna 41F — Doc 204489",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204489",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204489",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204493",
      "label": "Donna 41F — Doc 204493",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204493",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204493",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204494",
      "label": "Donna 41F — Doc 204494",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204494",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204494",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204495",
      "label": "Donna 41F — Doc 204495",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204495",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204495",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204496",
      "label": "Donna 41F — Doc 204496",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204496",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204496",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204497",
      "label": "Donna 41F — Doc 204497",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204497",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204497",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204505",
      "label": "Donna 41F — Doc 204505",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204505",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204505",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204508",
      "label": "Donna 41F — Doc 204508",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204508",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204508",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204520",
      "label": "Donna 41F — Doc 204520",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204520",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204520",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204521",
      "label": "Donna 41F — Doc 204521",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204521",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204521",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204522",
      "label": "Donna 41F — Doc 204522",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204522",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204522",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204523",
      "label": "Donna 41F — Doc 204523",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204523",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204523",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204524",
      "label": "Donna 41F — Doc 204524",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204524",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204524",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204525",
      "label": "Donna 41F — Doc 204525",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204525",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204525",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204529",
      "label": "Donna 41F — Doc 204529",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204529",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204529",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204530",
      "label": "Donna 41F — Doc 204530",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204530",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204530",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204531",
      "label": "Donna 41F — Doc 204531",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204531",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204531",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204533",
      "label": "Donna 41F — Doc 204533",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204533",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204533",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204534",
      "label": "Donna 41F — Doc 204534",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204534",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204534",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204535",
      "label": "Donna 41F — Doc 204535",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204535",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204535",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204550",
      "label": "Donna 41F — Doc 204550",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204550",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204550",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204551",
      "label": "Donna 41F — Doc 204551",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204551",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204551",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204552",
      "label": "Donna 41F — Doc 204552",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204552",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204552",
      "is_preview": true,
      "preview_content": "Reason for Appointment\n1. Urgent evaluation of hemodynamic instability and erratic blood pressure readings (ranging 120/70 to 160/90 mmHg).\n2. Critical medication safety review regarding **Critical Safety Discrepancies** (High probability of pregnancy with teratogenic agent use: Paroxetine + Prenatal Vitamins + Hyperemesis gravidarum history).\n3. Optimization of Mild Intermittent Asthma (Guideline-Directed Medical Therapy gaps regarding SABA monotherapy).\n4. Health maintenance review (Vaccination and cancer screening gaps).\n\nHistory of Present Illness\nDonna Sandboxtest is a 41-year-old female presenting for urgent follow-up and care coordination following a series of indirect encounters between 11/19/2025 and 11/28/2025. Review of clinical documentation reveals significant hemodynamic instability, with home blood pressure readings exhibiting substantial lability, fluctuating between 120/70 mmHg and 160/90 mmHg (most recent high recorded 2025-09-09). This variability necessitates rigorous evaluation to rule out hypertensive urgency versus a reactive stress response. The patient reports vague somatic symptoms but denies acute chest pain or dyspnea.\n\nA comprehensive review of the medication profile and active problem list identifies a **High Priority Clinical Alert** and **Critical Safety Discrepancy**. The patient is currently prescribed Paroxetine (Paxil) 10 mg daily while concurrently taking Prenatal Vitamins, and \"Hyperemesis gravidarum\" appears on her active condition list. This constellation strongly implies active or early pregnancy status. Paroxetine is an FDA Category D agent associated with an increased risk of congenital cardiac malformations (specifically atrial and ventricular septal defects). Immediate verification of pregnancy status via quantitative beta-hCG is required to mitigate teratogenic risk and guide psychopharmacologic transition to Sertraline if indicated.\n\nAdditionally, the patient’s respiratory status requires optimization. She has a history"
    },
    {
      "id": "60178_204553",
      "label": "Donna 41F — Doc 204553",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204553",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204553",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204554",
      "label": "Donna 41F — Doc 204554",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204554",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204554",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204555",
      "label": "Donna 41F — Doc 204555",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204555",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204555",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204556",
      "label": "Donna 41F — Doc 204556",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204556",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204556",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204557",
      "label": "Donna 41F — Doc 204557",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204557",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204557",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204564",
      "label": "Donna 41F — Doc 204564",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204564",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204564",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204565",
      "label": "Donna 41F — Doc 204565",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204565",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204565",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204649",
      "label": "Donna 41F — Doc 204649",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204649",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204649",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204650",
      "label": "Donna 41F — Doc 204650",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204650",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204650",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204651",
      "label": "Donna 41F — Doc 204651",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204651",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204651",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204661",
      "label": "Donna 41F — Doc 204661",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204661",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204661",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204662",
      "label": "Donna 41F — Doc 204662",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204662",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204662",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204663",
      "label": "Donna 41F — Doc 204663",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204663",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204663",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204731",
      "label": "Donna 41F — Doc 204731",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204731",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204731",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204732",
      "label": "Donna 41F — Doc 204732",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204732",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204732",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204733",
      "label": "Donna 41F — Doc 204733",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204733",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204733",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204741",
      "label": "Donna 41F — Doc 204741",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204741",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204741",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204742",
      "label": "Donna 41F — Doc 204742",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204742",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204742",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204744",
      "label": "Donna 41F — Doc 204744",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204744",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204744",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204745",
      "label": "Donna 41F — Doc 204745",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204745",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204745",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204748",
      "label": "Donna 41F — Doc 204748",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204748",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204748",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204749",
      "label": "Donna 41F — Doc 204749",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204749",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204749",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204849",
      "label": "Donna 41F — Doc 204849",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204849",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204849",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204851",
      "label": "Donna 41F — Doc 204851",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204851",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204851",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204853",
      "label": "Donna 41F — Doc 204853",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204853",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204853",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204855",
      "label": "Donna 41F — Doc 204855",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204855",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204855",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204878",
      "label": "Donna 41F — Doc 204878",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204878",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204878",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204879",
      "label": "Donna 41F — Doc 204879",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204879",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204879",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204880",
      "label": "Donna 41F — Doc 204880",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204880",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204880",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204881",
      "label": "Donna 41F — Doc 204881",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204881",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204881",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204882",
      "label": "Donna 41F — Doc 204882",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204882",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204882",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204883",
      "label": "Donna 41F — Doc 204883",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204883",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204883",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204884",
      "label": "Donna 41F — Doc 204884",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204884",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204884",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204908",
      "label": "Donna 41F — Doc 204908",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204908",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204908",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204914",
      "label": "Donna 41F — Doc 204914",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204914",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204914",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204915",
      "label": "Donna 41F — Doc 204915",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204915",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204915",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204916",
      "label": "Donna 41F — Doc 204916",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204916",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204916",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204917",
      "label": "Donna 41F — Doc 204917",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204917",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204917",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204918",
      "label": "Donna 41F — Doc 204918",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204918",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204918",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204919",
      "label": "Donna 41F — Doc 204919",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204919",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204919",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204925",
      "label": "Donna 41F — Doc 204925",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204925",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204925",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204926",
      "label": "Donna 41F — Doc 204926",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204926",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204926",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204927",
      "label": "Donna 41F — Doc 204927",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204927",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204927",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204928",
      "label": "Donna 41F — Doc 204928",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204928",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204928",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204930",
      "label": "Donna 41F — Doc 204930",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204930",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204930",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204936",
      "label": "Donna 41F — Doc 204936",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204936",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204936",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204937",
      "label": "Donna 41F — Doc 204937",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204937",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204937",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204938",
      "label": "Donna 41F — Doc 204938",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204938",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204938",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204939",
      "label": "Donna 41F — Doc 204939",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204939",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204939",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60178_204940",
      "label": "Donna 41F — Doc 204940",
      "practice_id": "195900",
      "patient_id": "60178",
      "document_id": "204940",
      "api_path": "/v1/195900/patients/60178/documents/clinicaldocument/204940",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60179_204934",
      "label": "Sandbox Patient 60179 — Doc 204934",
      "practice_id": "195900",
      "patient_id": "60179",
      "document_id": "204934",
      "api_path": "/v1/195900/patients/60179/documents/clinicaldocument/204934",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60179_204935",
      "label": "Sandbox Patient 60179 — Doc 204935",
      "practice_id": "195900",
      "patient_id": "60179",
      "document_id": "204935",
      "api_path": "/v1/195900/patients/60179/documents/clinicaldocument/204935",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60180_204750",
      "label": "Sandbox Patient 60180 — Doc 204750",
      "practice_id": "195900",
      "patient_id": "60180",
      "document_id": "204750",
      "api_path": "/v1/195900/patients/60180/documents/clinicaldocument/204750",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60180_204751",
      "label": "Sandbox Patient 60180 — Doc 204751",
      "practice_id": "195900",
      "patient_id": "60180",
      "document_id": "204751",
      "api_path": "/v1/195900/patients/60180/documents/clinicaldocument/204751",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60181_205151",
      "label": "Sandbox Patient 60181 — Doc 205151",
      "practice_id": "195900",
      "patient_id": "60181",
      "document_id": "205151",
      "api_path": "/v1/195900/patients/60181/documents/clinicaldocument/205151",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60181_205152",
      "label": "Sandbox Patient 60181 — Doc 205152",
      "practice_id": "195900",
      "patient_id": "60181",
      "document_id": "205152",
      "api_path": "/v1/195900/patients/60181/documents/clinicaldocument/205152",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60182_206206",
      "label": "Sandbox Patient 60182 — Doc 206206",
      "practice_id": "195900",
      "patient_id": "60182",
      "document_id": "206206",
      "api_path": "/v1/195900/patients/60182/documents/clinicaldocument/206206",
      "is_preview": false,
      "preview_content": null
    },
    {
      "id": "60182_206240",
      "label": "Sandbox Patient 60182 — Doc 206240",
      "practice_id": "195900",
      "patient_id": "60182",
      "document_id": "206240",
      "api_path": "/v1/195900/patients/60182/documents/clinicaldocument/206240",
      "is_preview": false,
      "preview_content": null
    }
  ],
  "sandbox_note": "These 100 SOAP-note clinical documents are from the Athena sandbox. Patient 60178 (Donna) is the primary sandbox patient; patients 60179-60182 have 2 documents each."
}
```

- **Acceptance criteria:** Run from `backend/`:
  ```bash
  python -c "import json; m = json.load(open('data/athena-clinicaldocs-manifest.json')); assert len(m['entries']) == 100; assert sum(1 for e in m['entries'] if e['is_preview']) == 1; assert m['preview_entry_id'] == '60178_204552'; assert m['source_kind'] == 'athena_clinical_doc'; assert all(e['preview_content'] is None for e in m['entries'] if not e['is_preview']); print('OK')"
  ```
  Must print `OK` and exit 0.

---

### Task 3 — Add Athena constants to `backend/utils/constants.py` and `.env.example`

**Traced to PRD §4-E and §4-K**

- **Files:**
  - `/root/projects/juno/backend/utils/constants.py`
  - `/root/projects/juno/backend/.env.example`

- **Changes to `constants.py`:** In the `Constants` class, add the following block after the existing `DATASETS_BUCKET_ENV_VAR` line (currently line 28):

  **Old** (lines 25–29):
  ```python
      # ── Dataset GCS config ─────────────────────────────────────────────────────
      DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
      DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
      DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"

      # ── Pipeline registry ─────────────────────────────────────────────────────
  ```

  **New:**
  ```python
      # ── Dataset GCS config ─────────────────────────────────────────────────────
      DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
      DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
      DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"

      # ── Athena Health API ──────────────────────────────────────────────────────
      ATHENA_CLIENT_ID_ENV_VAR: str     = "ATHENA_HEALTH_CLIENT_ID"
      ATHENA_CLIENT_SECRET_ENV_VAR: str = "ATHENA_HEALTH_CLIENT_SECRET"
      ATHENA_BASE_URL: str              = "https://api.preview.platform.athenahealth.com"
      ATHENA_PRACTICE_ID: str           = "195900"   # sandbox practice ID

      # ── Pipeline registry ─────────────────────────────────────────────────────
  ```

- **Changes to `.env.example`:** Append after the existing `DATASETS_BUCKET_NAME=juno-preset-data` line:

  ```
  # Athena Health API credentials (OAuth2 client credentials flow)
  # Obtain from: https://developer.athenahealth.com/
  ATHENA_HEALTH_CLIENT_ID=your_client_id_here
  ATHENA_HEALTH_CLIENT_SECRET=your_client_secret_here
  ```

- **Acceptance criteria:**
  ```bash
  python -c "from utils.constants import Constants; assert Constants.ATHENA_CLIENT_ID_ENV_VAR == 'ATHENA_HEALTH_CLIENT_ID'; assert Constants.ATHENA_CLIENT_SECRET_ENV_VAR == 'ATHENA_HEALTH_CLIENT_SECRET'; assert Constants.ATHENA_BASE_URL == 'https://api.preview.platform.athenahealth.com'; assert Constants.ATHENA_PRACTICE_ID == '195900'; print('OK')"
  ```
  Run from `backend/`. Must print `OK`.
  Also: `grep "ATHENA_HEALTH_CLIENT_ID" /root/projects/juno/backend/.env.example` exits 0.

---

### Task 4 — Add Athena error codes to `backend/utils/error_codes.py`

**Traced to PRD §4-F and §9-Q7**

- **Files:** `/root/projects/juno/backend/utils/error_codes.py`

- **Changes:**

  1. In the `ErrorCode(StrEnum)` body, add after `DATASET_DOWNLOAD_ERROR` (in the `# Batch` section):
     ```python
     # Athena Health
     ATHENA_AUTH_FAILED      = "ATHENA_AUTH_FAILED"
     ATHENA_API_ERROR        = "ATHENA_API_ERROR"
     ATHENA_RATE_LIMIT_ERROR = "ATHENA_RATE_LIMIT_ERROR"
     ```

  2. In `_REGISTRY`, add after the `ErrorCode.DATASET_DOWNLOAD_ERROR` entry:
     ```python
     ErrorCode.ATHENA_AUTH_FAILED:      ("Athena authentication failed",       "Could not obtain Athena OAuth2 token: {detail}"),
     ErrorCode.ATHENA_API_ERROR:        ("Athena API error",                   "Athena returned HTTP {status_code} for {path}: {detail}"),
     ErrorCode.ATHENA_RATE_LIMIT_ERROR: ("Athena rate limit exceeded",         "Athena API rate limit hit after {retries} retries; try again in {wait_s}s"),
     ```

- **Acceptance criteria:**
  ```bash
  python -c "from utils.error_codes import ErrorCode, make_error_response; r = make_error_response(ErrorCode.ATHENA_API_ERROR, '/', {'status_code': 429, 'path': '/v1/195900/...', 'detail': 'err'}); assert r.error.code == 'ATHENA_API_ERROR'; print('OK')"
  ```
  Run from `backend/`. Must print `OK` without `KeyError`.

---

### Task 5 — Create `backend/utils/athena_client.py`

**Traced to PRD §4-A and §9-Q2, Q3, Q6**

- **Files:** `/root/projects/juno/backend/utils/athena_client.py` *(new file)*

- **Changes:** Create the file with the complete implementation below:

```python
"""utils/athena_client.py — Athena Health API client for Juno (SP3).

OAuth2 client-credentials flow with token caching, rate-limit-aware
batch fetching (batch_size=2, sleep 30s between batches), and HTML
stripping for encounter summaries.
"""
import html
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from utils.constants import Constants

logger = logging.getLogger(__name__)

BATCH_SIZE = 2
BATCH_SLEEP_S = 30


class AthenaAPIError(Exception):
    """Raised when an Athena API call returns a non-200 status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Athena API error {status_code}: {body[:200]}")


class AthenaClient:
    """Singleton HTTP client for the Athena Health REST API.

    Caches the OAuth2 access token in memory for the process lifetime,
    refreshing when fewer than TOKEN_REFRESH_BUFFER_S seconds remain.
    """

    TOKEN_TTL_S: int = 300
    TOKEN_REFRESH_BUFFER_S: int = 20

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if within 20s of expiry."""
        now = time.time()
        if self._token and now < self._token_expires_at - self.TOKEN_REFRESH_BUFFER_S:
            return self._token
        client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
        client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]
        resp = requests.post(
            f"{Constants.ATHENA_BASE_URL}/oauth2/v1/token",
            auth=(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "athena/service/Athenanet.MDP.*",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]
        self._token_expires_at = now + self.TOKEN_TTL_S
        logger.info("athena_client: obtained new access token (expires in %ds)", self.TOKEN_TTL_S)
        return self._token

    def _get(self, path: str, retries: int = 3) -> dict:
        """GET with retry on 429; raises AthenaAPIError on other non-200."""
        for attempt in range(retries + 1):
            token = self.get_token()
            resp = requests.get(
                f"{Constants.ATHENA_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                if attempt == retries:
                    raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
                logger.warning(
                    "athena_client: rate limited on %s (attempt %d/%d), sleeping %ds",
                    path, attempt + 1, retries, wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise AthenaAPIError(resp.status_code, resp.text)
            return resp.json()
        raise AthenaAPIError(429, "Rate limit: max retries exhausted")

    def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
        """Fetch encounter summary HTML and return as stripped plain text."""
        path = f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary"
        data = self._get(path)
        raw_html_str = data.get("summaryhtml", "")
        return self._strip_html(raw_html_str)

    def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
        """Fetch SOAP-note clinical document and return documentdata string."""
        path = f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
        data = self._get(path)
        return data.get("documentdata", "")

    @staticmethod
    def _strip_html(raw_html_str: str) -> str:
        """Strip HTML tags, unescape entities, collapse excess blank lines."""
        unescaped = html.unescape(raw_html_str)
        text = re.sub(r"<[^>]+>", "", unescaped)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def fetch_items_with_rate_limit(
        self, items: list[dict]
    ) -> list[tuple[dict, str]]:
        """Fetch Athena items in batches of BATCH_SIZE with BATCH_SLEEP_S between batches.

        Each item dict must contain: source_kind, practice_id, and either
        encounter_id (for athena_encounter) or patient_id + document_id
        (for athena_clinical_doc).

        Returns list of (item, text) pairs in arbitrary order.
        Sleeps BATCH_SLEEP_S seconds between batches but NOT after the last batch.
        """
        results: list[tuple[dict, str]] = []

        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i : i + BATCH_SIZE]

            def _fetch_one(item: dict) -> str:
                if item["source_kind"] == "athena_encounter":
                    return self.fetch_encounter_summary(
                        item["practice_id"], item["encounter_id"]
                    )
                return self.fetch_clinical_doc(
                    item["practice_id"], item["patient_id"], item["document_id"]
                )

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
                futures = {pool.submit(_fetch_one, item): item for item in batch}
                for future in as_completed(futures):
                    results.append((futures[future], future.result()))

            is_last_batch = (i + BATCH_SIZE) >= len(items)
            if not is_last_batch:
                logger.info(
                    "athena_client: batch %d/%d done; sleeping %ds before next batch",
                    i // BATCH_SIZE + 1,
                    (len(items) + BATCH_SIZE - 1) // BATCH_SIZE,
                    BATCH_SLEEP_S,
                )
                time.sleep(BATCH_SLEEP_S)

        return results


# Module-level singleton — shared across all requests in the same worker process.
athena_client = AthenaClient()
```

- **Acceptance criteria:**
  ```bash
  python -c "from utils.athena_client import AthenaClient, AthenaAPIError, athena_client, BATCH_SIZE, BATCH_SLEEP_S; assert BATCH_SIZE == 2; assert BATCH_SLEEP_S == 30; assert isinstance(athena_client, AthenaClient); print('OK')"
  ```
  Run from `backend/`. Must print `OK` with no import errors.

---

### Task 6 — Extend `backend/routes/datasets.py` to serve Athena manifests

**Traced to PRD §4-G and §5**

- **Files:** `/root/projects/juno/backend/routes/datasets.py`

- **Changes:** Add `pathlib.Path` and `json` imports, add a `DATA_DIR` constant, add `_load_athena_sources()`, and update the `list_datasets_route` response to include `athena_sources`.

  **Old file:**
  ```python
  from flask import Blueprint, jsonify

  from routes.care_plan import _extract_text_from_bytes
  from utils.firebase import verify_firebase_token
  from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

  datasets_bp = Blueprint("datasets", __name__)


  @datasets_bp.route("/care_plan/datasets", methods=["GET"])
  @verify_firebase_token
  def list_datasets_route(user_id: str):
      _ = user_id
      return jsonify({"datasets": list_datasets()})
  ```

  **New file (full replacement — only the top block and the first route change; the `get_dataset_file_route` stays unchanged):**
  ```python
  import json
  from pathlib import Path

  from flask import Blueprint, jsonify

  from routes.care_plan import _extract_text_from_bytes
  from utils.firebase import verify_firebase_token
  from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

  datasets_bp = Blueprint("datasets", __name__)

  # Resolved relative to this file: backend/routes/../data/ = backend/data/
  DATA_DIR = Path(__file__).resolve().parent.parent / "data"

  _ATHENA_MANIFEST_NAMES = [
      "athena-encounters-manifest.json",
      "athena-clinicaldocs-manifest.json",
  ]


  def _load_athena_sources() -> list[dict]:
      """Load Athena source manifests from backend/data/. Missing files are silently skipped."""
      sources = []
      for name in _ATHENA_MANIFEST_NAMES:
          path = DATA_DIR / name
          if path.is_file():
              with path.open("r", encoding="utf-8") as f:
                  sources.append(json.load(f))
      return sources


  @datasets_bp.route("/care_plan/datasets", methods=["GET"])
  @verify_firebase_token
  def list_datasets_route(user_id: str):
      _ = user_id
      return jsonify({
          "datasets": list_datasets(),
          "athena_sources": _load_athena_sources(),
      })
  ```

  The `get_dataset_file_route` function below is unchanged.

- **Acceptance criteria:**
  ```bash
  python -c "
  import sys; sys.path.insert(0, 'backend')
  import json, pathlib
  DATA_DIR = pathlib.Path('backend/data')
  names = ['athena-encounters-manifest.json', 'athena-clinicaldocs-manifest.json']
  sources = []
  for name in names:
      p = DATA_DIR / name
      if p.is_file():
          sources.append(json.load(open(p)))
  assert len(sources) == 2
  assert any(s['source_kind'] == 'athena_encounter' for s in sources)
  assert any(s['source_kind'] == 'athena_clinical_doc' for s in sources)
  print('OK')
  "
  ```
  Run from repo root. Also confirm that a `GET /care_plan/datasets` response (via the Flask test client) contains both `datasets` and `athena_sources` keys.

---

### Task 7 — Update `backend/routes/batch_jobs.py` for Athena source kinds

**Traced to PRD §4-H and §5**

- **Files:** `/root/projects/juno/backend/routes/batch_jobs.py`

- **Changes:** Athena selections bypass `_resolve_requested_runs()` entirely. The route partitions `selections` into GCS and Athena groups, resolves GCS runs as before, and creates job docs directly for Athena items.

  Replace the entire route body with the following (imports and blueprint declaration unchanged):

  **Old for-loop and surrounding logic (lines 43–128):**
  ```python
      try:
          runs = _resolve_requested_runs(selections)
      except (ValueError, FileNotFoundError) as exc:
          return make_error_response(
              ErrorCode.BATCH_INVALID_SELECTION,
              request.path,
              {"detail": str(exc)},
          ).to_dict(), 400

      if len(runs) > Constants.MAX_BATCH_RUNS:
          return make_error_response(
              ErrorCode.BATCH_TOO_LARGE,
              request.path,
              {"count": len(runs), "max_runs": Constants.MAX_BATCH_RUNS},
          ).to_dict(), 400

      batch_run_id = str(uuid.uuid4())
      timestamp = _batch_timestamp()
      batch_group_ids = {
          group: f"{group}-{timestamp}"
          for group in sorted({group for group, _, _ in runs})
      }

      now = datetime.now(timezone.utc)
      job_ids: list[str] = []
      deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))

      for group, input_id, files in runs:
          job_id = str(uuid.uuid4())
          batch_group_id = batch_group_ids[group]
          source_filename = ", ".join(files)

          job_doc = {
              "uid": user_id,
              "name": now.strftime("%b %d, %Y %H:%M"),
              "source_filename": source_filename,
              "created_at": now,
              "updated_at": now,
              "status": "not_started",
              "stage": None,
              "started_at": None,
              "completed_at": None,
              "output_data": None,
              "error_data": None,
              "batch_run_id": batch_run_id,
              "batch_group_id": batch_group_id,
              "dataset_group": group,
              "dataset_input_id": input_id,
              "dataset_files": files,
              "input_source_kind": "gcs_batch_dataset",
              "input_text": None,
              "input_doc_id": None,
              "input_source_filename": source_filename,
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
          }
          create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)
          # ... enqueue ...

      return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202
  ```

  **New logic (replace from `try: runs = ...` through `return jsonify`):**
  ```python
      # ── Partition selections ─────────────────────────────────────────────────
      ATHENA_KINDS = {"athena_encounter", "athena_clinical_doc"}
      athena_selections = [
          s for s in selections
          if isinstance(s, dict) and s.get("input_source_kind") in ATHENA_KINDS
      ]
      gcs_selections = [
          s for s in selections
          if s not in athena_selections
      ]

      # ── Resolve GCS runs ────────────────────────────────────────────────────
      runs: list[tuple[str, str, list[str]]] = []
      if gcs_selections:
          try:
              runs = _resolve_requested_runs(gcs_selections)
          except (ValueError, FileNotFoundError) as exc:
              return make_error_response(
                  ErrorCode.BATCH_INVALID_SELECTION,
                  request.path,
                  {"detail": str(exc)},
              ).to_dict(), 400

      total_count = len(runs) + len(athena_selections)
      if total_count > Constants.MAX_BATCH_RUNS:
          return make_error_response(
              ErrorCode.BATCH_TOO_LARGE,
              request.path,
              {"count": total_count, "max_runs": Constants.MAX_BATCH_RUNS},
          ).to_dict(), 400

      batch_run_id = str(uuid.uuid4())
      timestamp = _batch_timestamp()
      now = datetime.now(timezone.utc)
      job_ids: list[str] = []
      deadline_s = int(os.environ.get("JOB_TIMEOUT_SECONDS_BATCH", "900"))

      # ── GCS dataset job docs ────────────────────────────────────────────────
      gcs_groups = sorted({group for group, _, _ in runs})
      batch_group_ids = {group: f"{group}-{timestamp}" for group in gcs_groups}

      for group, input_id, files in runs:
          job_id = str(uuid.uuid4())
          batch_group_id = batch_group_ids[group]
          source_filename = ", ".join(files)

          job_doc = {
              "uid": user_id,
              "name": now.strftime("%b %d, %Y %H:%M"),
              "source_filename": source_filename,
              "created_at": now,
              "updated_at": now,
              "status": "not_started",
              "stage": None,
              "started_at": None,
              "completed_at": None,
              "output_data": None,
              "error_data": None,
              "batch_run_id": batch_run_id,
              "batch_group_id": batch_group_id,
              "dataset_group": group,
              "dataset_input_id": input_id,
              "dataset_files": files,
              "input_source_kind": "gcs_batch_dataset",
              "input_text": None,
              "input_doc_id": None,
              "input_source_filename": source_filename,
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
              # Athena fields null for GCS jobs
              "athena_practice_id": None,
              "athena_patient_id": None,
              "athena_encounter_id": None,
              "athena_document_id": None,
              "athena_api_path": None,
          }
          create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

          try:
              enqueue_job(
                  job_id,
                  queue_name=require_env("CLOUD_TASKS_QUEUE"),
                  worker_url=require_env("WORKER_URL"),
                  service_account=require_env("WORKER_SERVICE_ACCOUNT"),
                  deadline_seconds=deadline_s,
                  batch_run_id=batch_run_id,
              )
          except MissingJobConfigError:
              logger.exception(
                  "batch_jobs: missing Cloud Tasks config; cannot enqueue job %s", job_id
              )
              return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
          except Exception:
              logger.exception("batch_jobs: failed to enqueue Cloud Task for job %s", job_id)
              return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

          job_ids.append(job_id)

      # ── Athena job docs ─────────────────────────────────────────────────────
      athena_batch_group_id = f"athena-{timestamp}"

      for sel in athena_selections:
          source_kind = sel["input_source_kind"]
          practice_id = sel.get("athena_practice_id", "")
          patient_id = sel.get("athena_patient_id", "")
          encounter_id = sel.get("athena_encounter_id")
          document_id = sel.get("athena_document_id")
          api_path = sel.get("athena_api_path", "")

          if source_kind == "athena_encounter":
              if not encounter_id:
                  return make_error_response(
                      ErrorCode.BATCH_INVALID_SELECTION,
                      request.path,
                      {"detail": "athena_encounter requires athena_encounter_id"},
                  ).to_dict(), 400
              source_filename = f"athena_encounter_{encounter_id}"
          else:  # athena_clinical_doc
              if not document_id:
                  return make_error_response(
                      ErrorCode.BATCH_INVALID_SELECTION,
                      request.path,
                      {"detail": "athena_clinical_doc requires athena_document_id"},
                  ).to_dict(), 400
              source_filename = f"athena_doc_{document_id}"

          job_id = str(uuid.uuid4())
          job_doc = {
              "uid": user_id,
              "name": now.strftime("%b %d, %Y %H:%M"),
              "source_filename": source_filename,
              "created_at": now,
              "updated_at": now,
              "status": "not_started",
              "stage": None,
              "started_at": None,
              "completed_at": None,
              "output_data": None,
              "error_data": None,
              "batch_run_id": batch_run_id,
              "batch_group_id": athena_batch_group_id,
              # GCS dataset fields null for Athena jobs
              "dataset_group": None,
              "dataset_input_id": None,
              "dataset_files": None,
              "input_source_kind": source_kind,
              "input_text": None,
              "input_doc_id": None,
              "input_source_filename": source_filename,
              "input_pdf_gcs_uri": None,
              "input_version": version,
              "grading_enabled": grading_enabled,
              # Athena-specific fields
              "athena_practice_id": practice_id,
              "athena_patient_id": patient_id,
              "athena_encounter_id": encounter_id,
              "athena_document_id": document_id,
              "athena_api_path": api_path,
          }
          create_job_doc(user_id=user_id, job_id=job_id, payload=job_doc)

          try:
              enqueue_job(
                  job_id,
                  queue_name=require_env("CLOUD_TASKS_QUEUE"),
                  worker_url=require_env("WORKER_URL"),
                  service_account=require_env("WORKER_SERVICE_ACCOUNT"),
                  deadline_seconds=deadline_s,
                  batch_run_id=batch_run_id,
              )
          except MissingJobConfigError:
              logger.exception(
                  "batch_jobs: missing Cloud Tasks config; cannot enqueue Athena job %s", job_id
              )
              return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500
          except Exception:
              logger.exception("batch_jobs: failed to enqueue Athena Cloud Task for job %s", job_id)
              return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 500

          job_ids.append(job_id)

      return jsonify({"batch_run_id": batch_run_id, "job_ids": job_ids}), 202
  ```

- **Acceptance criteria:**
  - A POST to `/care_plan/batch/jobs` with an `athena_encounter` selection (all Cloud Tasks mocked) creates a job doc with `input_source_kind == "athena_encounter"`, `athena_encounter_id == "62021"`, `dataset_group is None`, and the Athena API path stored in `athena_api_path`.
  - A POST with a GCS selection still produces `input_source_kind == "gcs_batch_dataset"` and `athena_encounter_id is None`.
  - A POST with both GCS and Athena selections in the same request creates one job doc per selection of the correct kind.

---

### Task 8 — Update `backend/routes/worker.py` for Athena dispatch and `additional_info`

**Traced to PRD §4-I and §9-Q8**

- **Files:** `/root/projects/juno/backend/routes/worker.py`

- **Changes:** Two changes to `execute_job()` and one to `_INPUT_TYPE_MAP`.

  **Change 1 — Update `_INPUT_TYPE_MAP`** (lines 34–40 in current file):

  **Old:**
  ```python
  _INPUT_TYPE_MAP = {
      "upload": "file",
      "batch_dataset": "text",       # legacy, pre-extracted text
      "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
      "doc_id": "doc_id",
      "text": "text",
  }
  ```

  **New:**
  ```python
  _INPUT_TYPE_MAP = {
      "upload": "file",
      "batch_dataset": "text",       # legacy, pre-extracted text
      "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
      "athena_encounter": "text",    # new SP3 — live Athena encounter fetch
      "athena_clinical_doc": "text", # new SP3 — live Athena clinical doc fetch
      "doc_id": "doc_id",
      "text": "text",
  }
  ```

  **Change 2 — Add Athena dispatch branch in `execute_job()`** (insert after the `gcs_batch_dataset` if-block, before `else: text = _resolve_input_from_job_doc(job_doc)`):

  **Old (lines 200–216):**
  ```python
          if source_kind == "gcs_batch_dataset":
              is_gcs_dataset_job = True
              from utils.gcs_datasets import download_dataset_inputs
              gcs_temp_dir = download_dataset_inputs(
                  group=job_doc["dataset_group"],
                  input_id=job_doc["dataset_input_id"],
                  files=job_doc["dataset_files"],
                  job_id=job_id,
              )
              text = _extract_text_from_downloaded(
                  gcs_temp_dir,
                  job_doc["dataset_group"],
                  job_doc["dataset_input_id"],
                  job_doc["dataset_files"],
              )
          else:
              text = _resolve_input_from_job_doc(job_doc)
  ```

  **New:**
  ```python
          athena_additional_info: list[str] = []

          if source_kind == "gcs_batch_dataset":
              is_gcs_dataset_job = True
              from utils.gcs_datasets import download_dataset_inputs
              gcs_temp_dir = download_dataset_inputs(
                  group=job_doc["dataset_group"],
                  input_id=job_doc["dataset_input_id"],
                  files=job_doc["dataset_files"],
                  job_id=job_id,
              )
              text = _extract_text_from_downloaded(
                  gcs_temp_dir,
                  job_doc["dataset_group"],
                  job_doc["dataset_input_id"],
                  job_doc["dataset_files"],
              )
          elif source_kind in ("athena_encounter", "athena_clinical_doc"):
              from utils.athena_client import athena_client, AthenaAPIError
              practice_id = job_doc.get("athena_practice_id") or Constants.ATHENA_PRACTICE_ID
              api_path = job_doc.get("athena_api_path", "")
              try:
                  if source_kind == "athena_encounter":
                      text = athena_client.fetch_encounter_summary(
                          practice_id, job_doc["athena_encounter_id"]
                      )
                  else:
                      text = athena_client.fetch_clinical_doc(
                          practice_id,
                          job_doc["athena_patient_id"],
                          job_doc["athena_document_id"],
                      )
              except AthenaAPIError as exc:
                  fail_job(job_id, _build_error_data(
                      PipelineErrorCode.ATHENA_API_ERROR,
                      f"status={exc.status_code} path={api_path}",
                  ))
                  logger.error(
                      "worker: Athena API error for job %s: %s", job_id, exc
                  )
                  return "", 200
              if api_path:
                  athena_additional_info = [api_path]
          else:
              text = _resolve_input_from_job_doc(job_doc)
  ```

  **Change 3 — Inject `additional_info` into care plan before `complete_job`** (insert between `output_data = envelope.to_dict()` and `name = _derive_name(...)`):

  **Old (lines 293–296):**
  ```python
          output_data = envelope.to_dict()

          name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))
  ```

  **New:**
  ```python
          output_data = envelope.to_dict()

          # Inject Athena source paths into care_plan.additional_info
          if athena_additional_info:
              care_plan_dict = output_data.get("care_plan", {})
              care_plan_dict["additional_info"] = athena_additional_info
              output_data["care_plan"] = care_plan_dict

          name = _derive_name(output_data.get("care_plan", {}), job_doc.get("input_source_filename", ""))
  ```

  Note: `athena_additional_info` is initialized to `[]` at the top of the Athena branch, so it is always in scope when reached (for non-Athena jobs it remains `[]` and the `if athena_additional_info:` guard is `False`).

  Also add `ATHENA_API_ERROR` and `ATHENA_AUTH_FAILED` to the `PipelineErrorCode` alias usage. The import already uses `from error_codes import ErrorCode as PipelineErrorCode`. The new error codes are immediately accessible once Task 4 is complete.

- **Acceptance criteria:**
  - `_INPUT_TYPE_MAP["athena_encounter"] == "text"` and `_INPUT_TYPE_MAP["athena_clinical_doc"] == "text"`.
  - When `execute_job()` runs with an `athena_encounter` job_doc (with `athena_client` mocked to return `"encounter text"`), `complete_job` is called with `output_data["care_plan"]["additional_info"] == ["/v1/195900/chart/encounters/62021/summary"]`.
  - When `execute_job()` runs with a `gcs_batch_dataset` job_doc, `athena_client` is never called.
  - When `AthenaAPIError` is raised, `fail_job` is called and the function returns `("", 200)`.

---

### Task 9 — Add `additional_info` field to `backend/models/care_plan_versions/v1_2.py`

**Traced to PRD §4-J**

- **Files:** `/root/projects/juno/backend/models/care_plan_versions/v1_2.py`

- **Changes:** Add `additional_info` to `CarePlanV1_2` after the `raw` field:

  **Old (lines 127):**
  ```python
      raw: RawArtifacts | None = None
  ```

  **New:**
  ```python
      raw: RawArtifacts | None = None
      additional_info: list[str] = Field(default_factory=list)
  ```

  No other lines change. The `Field` import is already present at line 8 (`from pydantic import Field`).

- **Acceptance criteria:**
  ```bash
  python -c "
  from models.care_plan_versions.v1_2 import CarePlanV1_2
  c = CarePlanV1_2()
  assert c.additional_info == []
  c2 = CarePlanV1_2(additional_info=['/v1/195900/chart/encounters/62021/summary'])
  assert c2.additional_info == ['/v1/195900/chart/encounters/62021/summary']
  d = c2.model_dump()
  assert 'additional_info' in d
  print('OK')
  "
  ```
  Run from `backend/`. Must print `OK`.
  Also confirm existing outputs that lack `additional_info` still deserialize to `[]` (Pydantic `default_factory` handles this).

---

### Task 10 — Add `additional_info` to frontend TypeScript types

**Traced to PRD §4-L and §6**

- **Files:**
  - `/root/projects/juno/frontend/src/types/carePlan.ts`
  - `/root/projects/juno/frontend/src/types/datasets.ts`

- **Changes to `carePlan.ts`:** Add `additional_info?: string[]` to `CarePlanContent` after `after_score`:

  **Old (lines 104–106):**
  ```typescript
    before_score?: PatientScore;
    after_score?: PatientScore;
  }
  ```

  **New:**
  ```typescript
    before_score?: PatientScore;
    after_score?: PatientScore;
    additional_info?: string[];
  }
  ```

  Note: Because `SimplifiedCarePlan` in `envelope.ts` is defined as `Omit<CarePlanContent, 'version'> & { version: string }`, adding `additional_info` to `CarePlanContent` automatically propagates it to `SimplifiedCarePlan`. No change to `envelope.ts` is required.

- **Changes to `datasets.ts`:** Add `AthenaEntry`, `AthenaSource`, and `AthenaSelection` types, and update `ListDatasetsResponse`:

  **Old file:**
  ```typescript
  export interface Dataset {
    group: string;
    inputs: string[];
    files: string[];
  }

  export interface BatchDatasetSelection {
    group: string;
    inputs: 'all' | string[];
    files: string[];
  }
  ```

  **New file:**
  ```typescript
  export interface Dataset {
    group: string;
    inputs: string[];
    files: string[];
  }

  export interface BatchDatasetSelection {
    group: string;
    inputs: 'all' | string[];
    files: string[];
  }

  export interface AthenaEntry {
    id: string;
    label: string;
    practice_id: string;
    patient_id: string;
    encounter_id?: string;    // present for athena_encounter
    document_id?: string;     // present for athena_clinical_doc
    api_path: string;
    is_preview: boolean;
    preview_content: string | null;
  }

  export interface AthenaSource {
    source_kind: "athena_encounter" | "athena_clinical_doc";
    label: string;
    tab_id: string;
    preview_entry_id: string;
    entries: AthenaEntry[];
    sandbox_note?: string;
  }

  export interface AthenaSelection {
    source_kind: "athena_encounter" | "athena_clinical_doc";
    entry: AthenaEntry;
  }

  export interface ListDatasetsResponse {
    datasets: Dataset[];
    athena_sources: AthenaSource[];
  }
  ```

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/frontend && npx tsc --noEmit
  ```
  Must exit 0 with no TypeScript errors.

---

### Task 11 — Update `CarePlanView.tsx` to render "Data Sources" card

**Traced to PRD §4-M and §2, Goal 5**

- **Files:** `/root/projects/juno/frontend/src/components/CarePlanView.tsx`

- **Changes:** Add a "Data Sources" `ResultCard` at the end of the `<div className="result-cards">` block, after the Medical Terms Glossary card.

  **Old (lines 310–322):**
  ```tsx
        {Object.keys(terms).length > 0 && (
          <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
            <div className="glossary-list">
              {Object.entries(terms).map(([term, glossary]) => (
                <div className="glossary-item" key={term}>
                  <span className="glossary-term">{term}</span>
                  <span className="glossary-def">{glossary.definition}</span>
                </div>
              ))}
            </div>
          </ResultCard>
        )}
      </div>
    );
  ```

  **New:**
  ```tsx
        {Object.keys(terms).length > 0 && (
          <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
            <div className="glossary-list">
              {Object.entries(terms).map(([term, glossary]) => (
                <div className="glossary-item" key={term}>
                  <span className="glossary-term">{term}</span>
                  <span className="glossary-def">{glossary.definition}</span>
                </div>
              ))}
            </div>
          </ResultCard>
        )}

        {result.additional_info && result.additional_info.length > 0 && (
          <ResultCard color="gray" icon="🔗" title="Data Sources">
            <ul className="result-list">
              {result.additional_info.map((path, i) => (
                <li key={i} style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {path}
                </li>
              ))}
            </ul>
          </ResultCard>
        )}
      </div>
    );
  ```

- **Acceptance criteria:**
  - `cd /root/projects/juno/frontend && npx tsc --noEmit` exits 0.
  - When `result.additional_info` is `["/v1/195900/chart/encounters/62021/summary"]`, the "Data Sources" card renders a single monospace list item with that path.
  - When `result.additional_info` is absent or empty, the card is not rendered.

---

### Task 12 — Create `frontend/src/components/PresetDataCard/AthenaPresetPanel.tsx`

**Traced to PRD §4-N and §2, Goal 4**

- **Files:** `/root/projects/juno/frontend/src/components/PresetDataCard/AthenaPresetPanel.tsx` *(new file)*

- **Changes:** Create the file with the complete implementation:

```tsx
import { useState } from 'react';
import type { AthenaEntry, AthenaSelection, AthenaSource } from '../../types/datasets';

interface AthenaPresetPanelProps {
  source: AthenaSource;
  onSelectionChange: (selections: AthenaSelection[]) => void;
}

type PanelMode = 'preview' | 'list';

export default function AthenaPresetPanel({
  source,
  onSelectionChange,
}: AthenaPresetPanelProps) {
  const [mode, setMode] = useState<PanelMode>('preview');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const previewEntry = source.entries.find(e => e.is_preview) ?? null;
  const listEntries = source.entries.filter(e => !e.is_preview);

  function handlePreviewSubmit() {
    if (!previewEntry) return;
    onSelectionChange([{ source_kind: source.source_kind, entry: previewEntry }]);
  }

  function handleCheckboxChange(entry: AthenaEntry) {
    const next = new Set(selected);
    if (next.has(entry.id)) {
      next.delete(entry.id);
    } else {
      next.add(entry.id);
    }
    setSelected(next);
    onSelectionChange(
      listEntries
        .filter(e => next.has(e.id))
        .map(e => ({ source_kind: source.source_kind, entry: e }))
    );
  }

  return (
    <div className="preset-panel">
      {/* Mode toggle */}
      <div className="athena-mode-toggle">
        <button
          type="button"
          className={`athena-mode-btn ${mode === 'preview' ? 'active' : ''}`}
          onClick={() => setMode('preview')}
        >
          Preview
        </button>
        <button
          type="button"
          className={`athena-mode-btn ${mode === 'list' ? 'active' : ''}`}
          onClick={() => setMode('list')}
        >
          List ({listEntries.length})
        </button>
      </div>

      <hr className="preset-panel-divider" />

      {/* Preview mode */}
      {mode === 'preview' && (
        <div className="preset-panel-appointments" style={{ overflowY: 'auto', flex: 1 }}>
          {previewEntry ? (
            <div className="athena-preview-card">
              <div className="athena-preview-label">{previewEntry.label}</div>
              <div className="athena-preview-api-path" style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                {previewEntry.api_path}
              </div>
              <div className="athena-preview-content">
                {previewEntry.preview_content?.slice(0, 500)}
                {(previewEntry.preview_content?.length ?? 0) > 500 ? '…' : ''}
              </div>
              <button
                type="button"
                className="athena-preview-submit"
                onClick={handlePreviewSubmit}
              >
                Use This Record
              </button>
            </div>
          ) : (
            <div className="preset-data-status">No preview entry found.</div>
          )}
          {source.sandbox_note && (
            <div className="preset-data-status" style={{ marginTop: '12px', fontStyle: 'italic' }}>
              {source.sandbox_note}
            </div>
          )}
        </div>
      )}

      {/* List mode */}
      {mode === 'list' && (
        <div className="preset-panel-appointments" style={{ overflowY: 'auto', flex: 1 }}>
          {listEntries.length === 0 ? (
            <div className="preset-data-status">No list entries available.</div>
          ) : (
            listEntries.map(entry => (
              <label key={entry.id} className="preset-data-option">
                <input
                  type="checkbox"
                  className="preset-data-checkbox"
                  checked={selected.has(entry.id)}
                  onChange={() => handleCheckboxChange(entry)}
                />
                <span className="preset-data-option-text">{entry.label}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
```

- **Acceptance criteria:**
  - `cd /root/projects/juno/frontend && npx tsc --noEmit` exits 0.
  - The component renders a two-button mode toggle ("Preview" / "List (N)"), a divider, and either the preview card or a scrollable checklist depending on the active mode.
  - Clicking "Use This Record" in preview mode calls `onSelectionChange` with a single-entry array containing the preview entry.
  - Checking a list entry updates the `selected` set and calls `onSelectionChange` with all currently-checked entries.

---

### Task 13 — Update `PresetDataCard.tsx` to render Athena tabs and propagate selections

**Traced to PRD §4-O and §6**

- **Files:**
  - `/root/projects/juno/frontend/src/components/PresetDataCard/PresetDataCard.tsx`
  - `/root/projects/juno/frontend/src/api/datasets.ts`

- **Changes to `datasets.ts`:** Update `listDatasets()` to return `ListDatasetsResponse` and expose `athena_sources`:

  **Old:**
  ```typescript
  import type { Dataset } from '../types/datasets';
  import { DATASETS_PATH, datasetFilePath } from '../constants';

  // ...

  export async function listDatasets(): Promise<Dataset[]> {
    const res = await authenticatedFetch(`${API_URL}${DATASETS_PATH}`);
    if (!res.ok) throw new Error(`Failed to list datasets: ${res.status}`);
    const json = await res.json();
    return json.datasets as Dataset[];
  }
  ```

  **New:**
  ```typescript
  import type { Dataset, AthenaSource, ListDatasetsResponse } from '../types/datasets';
  import { DATASETS_PATH, datasetFilePath } from '../constants';

  // ...

  export async function listDatasets(): Promise<ListDatasetsResponse> {
    const res = await authenticatedFetch(`${API_URL}${DATASETS_PATH}`);
    if (!res.ok) throw new Error(`Failed to list datasets: ${res.status}`);
    const json = await res.json();
    return {
      datasets: (json.datasets ?? []) as Dataset[],
      athena_sources: (json.athena_sources ?? []) as AthenaSource[],
    };
  }
  ```

- **Changes to `PresetDataCard.tsx`:** Add Athena state, update `loadDatasets()`, add Athena tabs to the sidebar, and render `AthenaPresetPanel` for Athena tabs. Show the full modified file:

  ```tsx
  import { useEffect, useMemo, useState } from 'react';
  import { listDatasets } from '../../api/datasets';
  import type { AthenaSelection, AthenaSource, BatchDatasetSelection, Dataset } from '../../types/datasets';
  import AthenaPresetPanel from './AthenaPresetPanel';
  import PresetDataPanel, { type DatasetGroupSelection } from './PresetDataPanel';
  import './PresetDataCard.css';

  interface PresetDataCardProps {
    onSelectionChange: (
      gcsSelections: BatchDatasetSelection[],
      athenaSelections: AthenaSelection[],
    ) => void;
  }

  type SelectionByGroup = Record<string, DatasetGroupSelection>;

  function emptySelection(): DatasetGroupSelection {
    return { inputs: new Set(), files: new Set() };
  }

  function toBatchSelections(
    datasets: Dataset[],
    selectionByGroup: SelectionByGroup,
  ): BatchDatasetSelection[] {
    return datasets.flatMap(dataset => {
      const selection = selectionByGroup[dataset.group];
      if (!selection || selection.inputs.size === 0 || selection.files.size === 0) return [];

      const inputs =
        selection.inputs.size === dataset.inputs.length
          ? 'all'
          : dataset.inputs.filter(input => selection.inputs.has(input));

      const files = dataset.files.filter(filename => selection.files.has(filename));
      if (files.length === 0) return [];

      return [{
        group: dataset.group,
        inputs,
        files,
      }];
    });
  }

  export default function PresetDataCard({ onSelectionChange }: PresetDataCardProps) {
    const [expanded, setExpanded] = useState(false);
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [athenaSources, setAthenaSources] = useState<AthenaSource[]>([]);
    const [selectionByGroup, setSelectionByGroup] = useState<SelectionByGroup>({}); 
    const [athenaSelections, setAthenaSelections] = useState<AthenaSelection[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeGroup, setActiveGroup] = useState<string | null>(null);

    useEffect(() => {
      let cancelled = false;

      async function loadDatasets() {
        setLoading(true);
        setError(null);
        try {
          const response = await listDatasets();
          if (!cancelled) {
            setDatasets(response.datasets ?? []);
            setAthenaSources(response.athena_sources ?? []);
          }
        } catch (loadError) {
          if (!cancelled) {
            setError(loadError instanceof Error ? loadError.message : 'Could not load preset data.');
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
      }

      void loadDatasets();

      return () => {
        cancelled = true;
      };
    }, []);

    const batchSelections = useMemo(
      () => toBatchSelections(datasets, selectionByGroup),
      [datasets, selectionByGroup],
    );

    useEffect(() => {
      onSelectionChange(batchSelections, athenaSelections);
    }, [batchSelections, athenaSelections, onSelectionChange]);

    useEffect(() => {
      if (datasets.length > 0 && activeGroup === null) {
        setActiveGroup(datasets[0].group);
      }
    }, [datasets, activeGroup]);

    function handleGroupSelectionChange(group: string, selection: DatasetGroupSelection) {
      setSelectionByGroup(current => ({
        ...current,
        [group]: selection,
      }));
    }

    function handleAthenaSelectionChange(
      sourceKind: AthenaSource['source_kind'],
      selections: AthenaSelection[],
    ) {
      setAthenaSelections(prev => [
        ...prev.filter(s => s.source_kind !== sourceKind),
        ...selections,
      ]);
    }

    const selectedGroupCount = batchSelections.length;
    const selectedInputCount = batchSelections.reduce((total, selection) => {
      if (selection.inputs === 'all') {
        const dataset = datasets.find(item => item.group === selection.group);
        return total + (dataset?.inputs.length ?? 0);
      }
      return total + selection.inputs.length;
    }, 0);
    const selectedFileCount = batchSelections.reduce(
      (total, selection) => total + selection.files.length,
      0,
    );
    const totalAthenaSelected = athenaSelections.length;

    const summaryText = (() => {
      const parts: string[] = [];
      if (selectedGroupCount > 0) {
        parts.push(`${selectedGroupCount} group${selectedGroupCount === 1 ? '' : 's'}, ${selectedInputCount} input${selectedInputCount === 1 ? '' : 's'}, ${selectedFileCount} file${selectedFileCount === 1 ? '' : 's'}`);
      }
      if (totalAthenaSelected > 0) {
        parts.push(`${totalAthenaSelected} Athena record${totalAthenaSelected === 1 ? '' : 's'}`);
      }
      return parts.length > 0 ? parts.join(' + ') + ' selected' : 'Select repository datasets or Athena records for batch runs.';
    })();

    const hasContent = datasets.length > 0 || athenaSources.length > 0;

    const activeAthenaSource = athenaSources.find(s => s.tab_id === activeGroup) ?? null;

    return (
      <div className="preset-data-card glass-card">
        <div className="preset-data-card-header">
          <div>
            <div className="preset-data-card-title">Preset Data</div>
            <div className="preset-data-card-summary">{summaryText}</div>
          </div>
          <button
            className="preset-data-toggle"
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded(current => !current)}
          >
            {expanded ? 'Collapse' : 'Choose'}
          </button>
        </div>

        {expanded && (
          <div className="preset-data-card-body">
            {loading && <div className="preset-data-status">Loading preset data...</div>}
            {error && <div className="preset-data-status error">{error}</div>}
            {!loading && !error && !hasContent && (
              <div className="preset-data-status">No preset datasets found.</div>
            )}
            {!loading && !error && hasContent && (
              <div className="preset-panel-layout">
                {/* LEFT: vertical tab list */}
                <nav className="preset-panel-sidebar" aria-label="Dataset groups">
                  {datasets.map(dataset => (
                    <button
                      key={dataset.group}
                      type="button"
                      title={dataset.group}
                      className={`preset-panel-tab ${activeGroup === dataset.group ? 'active' : ''}`}
                      onClick={() => setActiveGroup(dataset.group)}
                      aria-selected={activeGroup === dataset.group}
                    >
                      <span className="preset-panel-tab-name">{dataset.group}</span>
                      <span className="preset-panel-tab-meta">
                        {selectionByGroup[dataset.group]?.inputs.size ?? 0}/{dataset.inputs.length}
                      </span>
                    </button>
                  ))}
                  {athenaSources.map(source => (
                    <button
                      key={source.tab_id}
                      type="button"
                      className={`preset-panel-tab ${activeGroup === source.tab_id ? 'active' : ''}`}
                      onClick={() => setActiveGroup(source.tab_id)}
                      aria-selected={activeGroup === source.tab_id}
                    >
                      <span className="preset-panel-tab-name">{source.label}</span>
                      <span className="preset-panel-tab-meta">
                        {athenaSelections.filter(s => s.source_kind === source.source_kind).length} sel.
                      </span>
                    </button>
                  ))}
                </nav>

                {/* RIGHT: content panel for the active group */}
                <div className="preset-panel-content">
                  {activeAthenaSource !== null ? (
                    <AthenaPresetPanel
                      source={activeAthenaSource}
                      onSelectionChange={(sels) =>
                        handleAthenaSelectionChange(activeAthenaSource.source_kind, sels)
                      }
                    />
                  ) : activeGroup !== null ? (
                    (() => {
                      const dataset = datasets.find(d => d.group === activeGroup);
                      if (!dataset) return null;
                      return (
                        <PresetDataPanel
                          dataset={dataset}
                          selection={selectionByGroup[activeGroup] ?? emptySelection()}
                          onSelectionChange={handleGroupSelectionChange}
                        />
                      );
                    })()
                  ) : null}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }
  ```

- **Changes to `PresetDataCard.css`:** Append new Athena-specific CSS classes at the end of the file:

  ```css
  /* ── AthenaPresetPanel ── */

  .athena-mode-toggle {
    display: flex;
    gap: 6px;
    padding: 10px 12px 8px;
    flex-shrink: 0;
  }

  .athena-mode-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    font-family: Inter, sans-serif;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 5px 12px;
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }

  .athena-mode-btn:hover {
    background: var(--surface-hover);
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .athena-mode-btn.active {
    background: rgba(124, 58, 237, 0.08);
    border-color: var(--accent-violet);
    color: var(--accent-violet);
  }

  .athena-preview-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 10px 12px;
    padding: 12px;
  }

  .athena-preview-label {
    color: var(--text-primary);
    font-size: 0.875rem;
    font-weight: 700;
    line-height: 1.3;
  }

  .athena-preview-content {
    background: rgba(26, 19, 64, 0.03);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.76rem;
    line-height: 1.55;
    max-height: 200px;
    overflow: auto;
    padding: 8px;
    white-space: pre-wrap;
  }

  .athena-preview-submit {
    align-self: flex-start;
    background: var(--surface);
    border: 1px solid var(--accent-violet);
    border-radius: var(--radius-sm);
    color: var(--accent-violet);
    cursor: pointer;
    font-family: Inter, sans-serif;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 6px 14px;
    transition: background 0.12s, color 0.12s;
  }

  .athena-preview-submit:hover {
    background: rgba(124, 58, 237, 0.08);
  }
  ```

- **Acceptance criteria:**
  - `cd /root/projects/juno/frontend && npx tsc --noEmit` exits 0.
  - `PresetDataCard.tsx` no longer calls the old `listDatasets(): Promise<Dataset[]>` shape — it now uses `ListDatasetsResponse`.
  - The sidebar renders Athena tabs after GCS dataset tabs.
  - The `onSelectionChange` prop signature changes to accept both `gcsSelections` and `athenaSelections`. **Note for callers:** any parent component that passes `onSelectionChange` to `PresetDataCard` must be updated to accept the new two-argument signature. Check `frontend/src/` for usages of `PresetDataCard` and update accordingly.

---

### Task 14 — Write unit tests for `backend/utils/athena_client.py`

**Traced to PRD §7 (Backend unit tests)**

- **Files:** `/root/projects/juno/backend/tests/utils/test_athena_client.py` *(new file)*

- **Changes:** Create the file with the complete test suite:

```python
"""tests/utils/test_athena_client.py — Unit tests for AthenaClient."""
import time
import unittest
from unittest.mock import MagicMock, patch, call

import pytest

from utils.athena_client import AthenaClient, AthenaAPIError, BATCH_SIZE, BATCH_SLEEP_S


@pytest.fixture
def client():
    """Return a fresh AthenaClient with no cached token."""
    return AthenaClient()


def _mock_token_response(access_token: str = "test_token"):
    """Build a mock requests.Response for a successful token POST."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": access_token}
    return resp


def _mock_get_response(body: dict):
    """Build a mock requests.Response for a successful GET."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


# ─────────────────────────── get_token ────────────────────────────────────


def test_get_token_success(client, monkeypatch):
    """get_token() calls POST /oauth2/v1/token and returns access_token."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch("utils.athena_client.requests.post", return_value=_mock_token_response("tok1")) as mock_post:
        token = client.get_token()
    assert token == "tok1"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "/oauth2/v1/token" in args[0]
    assert kwargs.get("data", {}).get("grant_type") == "client_credentials"


def test_get_token_cached_within_ttl(client, monkeypatch):
    """get_token() called twice within TTL makes only one HTTP call."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch("utils.athena_client.requests.post", return_value=_mock_token_response("tok_cached")) as mock_post:
        t1 = client.get_token()
        t2 = client.get_token()
    assert t1 == t2 == "tok_cached"
    assert mock_post.call_count == 1


def test_get_token_refresh_when_expiry_within_buffer(client, monkeypatch):
    """get_token() refreshes when fewer than TOKEN_REFRESH_BUFFER_S seconds remain."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    # Pre-seed an almost-expired token
    client._token = "old_token"
    client._token_expires_at = time.time() + 10  # 10s < 20s buffer
    with patch("utils.athena_client.requests.post", return_value=_mock_token_response("new_token")) as mock_post:
        token = client.get_token()
    assert token == "new_token"
    mock_post.assert_called_once()


def test_get_token_does_not_refresh_when_fresh(client, monkeypatch):
    """get_token() returns cached token when more than TOKEN_REFRESH_BUFFER_S seconds remain."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    client._token = "fresh_token"
    client._token_expires_at = time.time() + 100  # 100s > 20s buffer
    with patch("utils.athena_client.requests.post") as mock_post:
        token = client.get_token()
    assert token == "fresh_token"
    mock_post.assert_not_called()


# ─────────────────────────── _strip_html ──────────────────────────────────


def test_strip_html_removes_tags():
    """_strip_html strips all HTML tags from the input."""
    result = AthenaClient._strip_html("<p>Hello <b>world</b></p>")
    assert result == "Hello world"


def test_strip_html_unescapes_entities():
    """_strip_html unescapes HTML entities."""
    result = AthenaClient._strip_html("&lt;b&gt;bold&lt;/b&gt;")
    assert result == "<b>bold</b>"


# ─────────────────────────── fetch_encounter_summary ─────────────────────


def test_fetch_encounter_summary_calls_correct_path(client, monkeypatch):
    """fetch_encounter_summary calls _get with the correct Athena path."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"summaryhtml": "<p>Gary</p>"}) as mock_get:
        result = client.fetch_encounter_summary("195900", "62021")
    mock_get.assert_called_once_with("/v1/195900/chart/encounters/62021/summary")
    assert result == "Gary"


# ─────────────────────────── fetch_clinical_doc ──────────────────────────


def test_fetch_clinical_doc_calls_correct_path(client, monkeypatch):
    """fetch_clinical_doc calls _get with the correct Athena path."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"documentdata": "SOAP note text"}) as mock_get:
        result = client.fetch_clinical_doc("195900", "60178", "204552")
    mock_get.assert_called_once_with("/v1/195900/patients/60178/documents/clinicaldocument/204552")
    assert result == "SOAP note text"


# ─────────────────────────── fetch_items_with_rate_limit ─────────────────


def test_fetch_items_rate_limit_sleeps_between_batches_not_after_last(client):
    """fetch_items_with_rate_limit sleeps once between batch 1 and 2, not after batch 2."""
    items = [
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62021"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "61456"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62281"},
    ]
    # 3 items → 2 batches (batch 1: items[0:2], batch 2: items[2:4])
    with patch.object(client, "fetch_encounter_summary", return_value="text") as mock_fetch, \
         patch("utils.athena_client.time.sleep") as mock_sleep:
        results = client.fetch_items_with_rate_limit(items)

    # sleep called exactly once (between batch 1 and batch 2, not after batch 2)
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args == call(BATCH_SLEEP_S)
    # All 3 items should be in results
    assert len(results) == 3


def test_fetch_items_no_sleep_for_single_batch(client):
    """fetch_items_with_rate_limit does not sleep when all items fit in one batch."""
    items = [
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62021"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "61456"},
    ]
    # 2 items == BATCH_SIZE → exactly 1 batch → no sleep
    with patch.object(client, "fetch_encounter_summary", return_value="text"), \
         patch("utils.athena_client.time.sleep") as mock_sleep:
        results = client.fetch_items_with_rate_limit(items)
    mock_sleep.assert_not_called()
    assert len(results) == 2
```

- **Acceptance criteria:**
  ```bash
  pytest backend/tests/utils/test_athena_client.py -v
  ```
  Run from repo root. All tests must pass. No network calls are made (all HTTP patched with `unittest.mock`).

---

## Summary of what requires you (not a dev agent)

These steps from PRD §8 cannot be automated and must be performed manually, in order:

1. **Set Athena credentials locally:** Add `ATHENA_HEALTH_CLIENT_ID=<actual_id>` and `ATHENA_HEALTH_CLIENT_SECRET=<actual_secret>` to `backend/.env`. Credentials are in the Athena developer portal for the sandbox account.

2. **Deploy to Cloud Run:** After all backend changes are merged, add `ATHENA_HEALTH_CLIENT_ID` and `ATHENA_HEALTH_CLIENT_SECRET` to the Cloud Run worker service environment (via GCP Secret Manager or directly in the service configuration).

3. **Verify datasets endpoint:** After deployment:
   ```bash
   curl -H "Authorization: Bearer <token>" https://<api-url>/care_plan/datasets | jq '.athena_sources | length'
   ```
   Should return `2`.

4. **Run an Athena encounter job end-to-end:** Submit a single `athena_encounter` job via the UI (preview mode → "Use This Record"), wait for completion, and confirm the care plan result includes a "Data Sources" card showing `/v1/195900/chart/encounters/62021/summary`.

5. **Update parent of `PresetDataCard`:** The `onSelectionChange` prop signature changed from `(selection: BatchDatasetSelection[]) => void` to `(gcsSelections: BatchDatasetSelection[], athenaSelections: AthenaSelection[]) => void`. Find all usages of `<PresetDataCard>` in `frontend/src/` and update the prop handler and the downstream job-creation logic to handle both selection types.
