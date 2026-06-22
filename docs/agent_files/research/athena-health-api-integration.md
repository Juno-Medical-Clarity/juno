# Athena Health API Integration Research

**Research Date:** 2026-06-21  
**Scope:** Full Athena Health API surface relevant to Juno — both pulling clinical content into Juno and pushing Juno output back into Athena's workflows.  
**Note on documentation access:** The docs.athenahealth.com portal requires authentication for most detail pages. This report synthesizes data from the official FHIR subscription GitHub repository, the go-athenahealth open-source SDK, the FHIR StructureDefinition pages, third-party integration guides, Athena's public blog posts, and indirect references from indexed documentation URLs. Where details could not be confirmed, this is flagged.

---

## Executive Summary

Athenahealth exposes three distinct integration pathways — proprietary athenaOne REST APIs (800+ endpoints, richest functionality, pay-per-call), Certified FHIR R4 APIs (standards-based, free, read-only), and Dataview (nightly SQL replica, read-only). For Juno's core needs, the **athenaOne proprietary API** is the primary path: it provides PULL access to encounter summaries, clinical documents, medications, diagnoses, orders, and discharge information, and PUSH access via patient messaging, secure messages, document upload, and patient case notes. The **FHIR R4 API** is the secondary path for standards-based clinical data access (conditions, medications, DocumentReference for notes). The highest-value APIs for Juno are: (1) the Encounter Summary endpoint for encounter-level clinical text, (2) the Secure Messages / Patient Case API for pushing plain-language content back to patients, and (3) the Clinical Document API for attaching Juno-generated summaries to the chart. The path to production requires completing Athena's Marketplace partner program (6–12 week review) and signing a BAA.

---

## Integration Architecture Overview

```
PULL FLOW (Athena → Juno)
--------------------------
Athena EHR
  ├── Encounter signoff event (FHIR Subscription or Changed Data poll)
  │     triggers →
  ├── GET /chart/encounter/{id}/summary        → summaryHTML text
  ├── GET /v1/{pid}/patients/{patid}/documents/clinicaldocument/{docid}/xml → CCD/CCDA
  ├── FHIR GET /DocumentReference?patient=...  → clinical notes, visit docs
  ├── GET /chart/{patid}/medications           → active med list
  ├── GET /chart/{patid}/problems              → active diagnoses/ICD-10
  ├── GET /chart/{patid}/orders                → patient info orders (education)
  ├── FHIR GET /Condition?patient=...          → problem list (FHIR)
  ├── FHIR GET /MedicationRequest?patient=...  → medications (FHIR)
  └── Discharge Info endpoint                  → discharge instructions

All clinical text → Juno pipeline (translate → personalize → plain-language output)

PUSH FLOW (Juno → Athena)
--------------------------
Juno plain-language output
  ├── POST /v1/{pid}/patients/{patid}/documents/patientcase
  │     → creates Patient Case note with Juno link + content visible to care team
  ├── POST Secure Messages endpoint
  │     → sends secure portal message to patient with Juno link
  ├── POST /v1/{pid}/patients/{patid}/documents/clinicaldocument
  │     → attaches Juno-generated plain-language summary as document to chart
  ├── POST /v1/{pid}/patients/{patid}/documents/letter
  │     → attaches formal letter-format summary (for mailing or portal delivery)
  ├── POST /v1/{pid}/patients/{patid}/documents/admin
  │     → logs engagement metrics or care adherence data as admin document
  └── FHIR Subscription (id-only push from Athena)
        → Athena notifies Juno of Encounter.signoff, then Juno pulls content
```

**Key constraint:** Athena's FHIR API is largely read-only. Write-back (PUSH) requires the proprietary athenaOne API endpoints.

---

## Developer Program & Access

### Registration & Sandbox

- **Developer Portal:** `developer.athenahealth.com` (also `mydata.athenahealth.com`)
- **Sandbox access:** Immediately available upon developer registration — no gating. Sandbox URL: `https://api.preview.platform.athenahealth.com/v1/{practiceid}/`
- **Production URL:** `https://api.platform.athenahealth.com/v1/{practiceid}/`
- **FHIR Base URLs:**
  - Preview: `https://api.preview.platform.athenahealth.com/fhir/r4`
  - Production: `https://api.platform.athenahealth.com/fhir/r4`

### Authentication

- **Protocol:** OAuth 2.0
- **Grant types:**
  - `client_credentials` — system-to-system (Juno's backend calling Athena)
  - `authorization_code` — user-facing SMART on FHIR app launch
- **Token endpoint:** `POST https://api.platform.athenahealth.com/oauth2/v1/token`
- **SMART on FHIR:** Supported; required for apps that launch within Athena's clinical workflow
- **Credentials:** Athena issues `client_id` and `client_secret` after registration
- **Practice authorization:** Each practice must explicitly authorize Juno's app before data access

### Production Access & Partner Program

- **Pathway:** Apply to the athenahealth **Marketplace partner program** (marketplace.athenahealth.com)
- **Review process stages:**
  1. Application — business model, integration plan
  2. Technical review — API usage, data handling, architecture
  3. Security review — encryption, access controls, HIPAA compliance, pentest
  4. Compliance review — HIPAA, BAA execution, data usage policies
- **Timeline:** 6–12 weeks
- **Cost model:** Pay-per-call for athenaOne APIs; Certified FHIR APIs are free

### HIPAA / BAA

- A signed **Business Associate Agreement (BAA)** between Juno and athenahealth is required for production access to PHI
- Each clinic deploying the integration must also sign their own BAA with Juno as a subcontractor
- Production access for many athenaOne APIs requires an **athenahealth Platform Services contract** in addition to the BAA
- Confirm exact requirements by endpoint category during partner onboarding

### Rate Limits

- Per-second threshold: 5–20 calls (exact limits negotiated per agreement, not publicly documented)
- Daily limit: Not publicly disclosed; communicated during partner onboarding
- Rate limit headers: `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Exceeded: HTTP 429; implement exponential backoff with jitter

---

## HIGH Priority APIs

### 1. Encounter Summary

- **Category:** Clinical / Encounter
- **Direction:** PULL
- **Juno Use Case:** Retrieve the complete clinician encounter write-up (HPI, exam, assessment, plan) after a visit is signed off, to feed Juno's translation pipeline for generating the patient-facing summary.
- **Endpoint:** `GET /v1/{practiceid}/chart/encounter/{encounterid}/summary`
- **Methods:** GET
- **Key fields:** `summaryhtml` — the entire encounter summary as HTML text, including HPI, physical exam, assessment and plan, orders
- **Notes:** This is the single richest text endpoint for Juno's PULL pipeline. The `summaryhtml` field was confirmed by the go-athenahealth SDK (`EncounterSummaryResponse.Summary` mapped to `summaryhtml`). Trigger this call on `Encounter.signoff` event (see Event Subscriptions below). Part of the athenaOne proprietary API.

---

### 2. Clinical Document (Document Type)

- **Category:** Documents & Forms
- **Direction:** BOTH
- **Juno Use Case (PULL):** Retrieve existing clinical documents (discharge summaries, external notes, C-CDA documents) attached to a patient's chart for ingestion into Juno's pipeline.
- **Juno Use Case (PUSH):** Upload Juno-generated plain-language summaries as a clinical document attached to the patient chart, visible to the care team.
- **Endpoints:**
  - `GET /v1/{practiceid}/patients/{patientid}/documents/clinicaldocument/{documentid}/xml` — retrieve CCD/CCDA XML
  - `GET /v1/{practiceid}/patients/{patientid}/documents` — list patient documents
  - `POST /v1/{practiceid}/patients/{patientid}/documents/clinicaldocument` — create/attach clinical document
- **Methods:** GET, POST
- **Key fields (POST):** `attachmentcontents` (file data), `attachmenttype` (MIME type), `departmentid`, `documentsubclass`, `internalnote`
- **Notes:** The generic `POST /documents` endpoint was retired in 2016; must use class-specific endpoints. Subscription event `ClinicalDocument.create/update` (Alpha) can notify Juno when new clinical documents are filed. C-CDA XML from Athena can be rich in structured clinical data.

---

### 3. Secure Messages

- **Category:** Patient Communication / Messaging
- **Direction:** PUSH
- **Juno Use Case:** Send a secure portal message to the patient containing the Juno plain-language care link, enabling the patient to access their personalized care guidance directly from the Athena patient portal (athenaPatient).
- **Endpoint:** `POST /v1/{practiceid}/...` (exact path: docs.athenahealth.com/api/api-ref/secure-messages — confirm with portal access)
- **Methods:** GET, POST (unverified — confirm with Athena docs)
- **Key fields:** Message body (plain text or HTML), subject, patient ID, provider sender, thread ID (for replies)
- **Notes:** This is Juno's primary channel to deliver plain-language content to patients within the Athena portal workflow. Patients receive a notification in athenaPatient. Subscription event `PatientCase.add-note` can track provider responses. Confirm whether the secure message can contain hyperlinks to external Juno URLs — critical for Juno's link-based delivery model.

---

### 4. Patient Case Document

- **Category:** Documents & Forms / Patient Communication
- **Direction:** PUSH
- **Juno Use Case:** Create a Patient Case note visible to the care team logging that Juno sent a plain-language summary to the patient, with a link to the Juno content and any engagement metrics (viewed, completed checklist, etc.). Closes the loop for the provider.
- **Endpoint:** `POST /v1/{practiceid}/patients/{patientid}/documents/patientcase`
- **Methods:** GET, POST
- **Key fields:** Note text, department ID, patient ID, provider attribution; PatientCase supports `add-note` event so threads can be extended
- **Notes:** FHIR Subscription event `PatientCase.create`, `PatientCase.update`, `PatientCase.add-note` available. This is a low-friction way to write structured notifications back into the EHR workflow without requiring Athena's approval for a new document class.

---

### 5. FHIR DocumentReference

- **Category:** FHIR R4 / Clinical Documents
- **Direction:** PULL
- **Juno Use Case:** Standards-based retrieval of clinical notes, encounter documents, and other attached documents using FHIR. Useful as the interoperability-compliant alternative to proprietary document endpoints; also enables SMART app launch access.
- **Endpoint:** `GET /fhir/r4/DocumentReference/{id}` and `GET /fhir/r4/DocumentReference?patient={id}`
- **Methods:** GET, Search
- **Key fields:** `content.attachment.url` or `content.attachment.data` (document binary/URL), `type` (LOINC code for note type), `category`, `subject` (patient ref), `author` (provider), `date`, `context.encounter`, `ahPublishedDateTimeToPortal` (extension — portal publish date)
- **Notes:** Athena's DocumentReference profile (`ah-documentreference`) includes a custom extension `ahPublishedDateTimeToPortal` enabling Juno to know when documents were shared with the patient. Subscription event `ClinicalDocument.create` (Alpha) triggers on new clinical docs. This is the FHIR-standard path for Note retrieval; preferred if Juno uses SMART on FHIR app launch.

---

### 6. Encounter & Clinical Encounter Diagnosis (Event Subscriptions)

- **Category:** Real-Time Events / FHIR Subscriptions
- **Direction:** PULL (trigger mechanism)
- **Juno Use Case:** Subscribe to `Encounter.signoff` events so Juno is notified in near real-time when a provider signs off on a visit, triggering an automatic PULL of the encounter summary and clinical content to begin Juno's translation pipeline — without any manual provider action.
- **Subscription Topics:**
  - `Encounter` — events: `check-in`, `reopen`, `signoff`
  - `ClinicalDocument` [Alpha] — events: `create`, `update`, `delete`
  - `ClinicalEncounterDiagnosis` — events: `create`, `update`, `delete`
  - `AdminDocument` [Alpha] — events: `create`, `update`
- **Methods:** FHIR Subscription REST API (`POST`, `GET` on Subscription resource)
- **Required scopes:** `system/SubscriptionTopic.read`, `system/Subscription.write`, `system/Subscription.read`
- **Key fields:** Event notification contains resource ID only (`id-only` payload); follow-up API call required to fetch content
- **Notes:** Base URL: `https://api.platform.athenahealth.com/fhir/r4`. Webhook endpoint must be HTTPS on port 443 with 2-second hard timeout. Events have at-least-once delivery with deduplication IDs. `ClinicalDocument` and `AdminDocument` subscriptions are currently Alpha — confirm GA status with Athena. OAuth 2-Legged apps only.

---

### 7. Medications (Chart)

- **Category:** Clinical / Chart
- **Direction:** PULL
- **Juno Use Case:** Pull the patient's current medication list to include in Juno's plain-language care guidance — critical for neurology patients (MS, Parkinson's, dementia) where medication adherence is central to care.
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/medications`
- **Methods:** GET
- **Key fields:** Medication name, dosage, frequency, instructions, prescriber, start/stop dates, status (active/inactive), RxNorm code
- **Notes:** Also available via FHIR R4 `MedicationRequest` resource (`GET /fhir/r4/MedicationRequest?patient={id}`). Prescription change events available via `Prescription` FHIR Subscription topic (events: `create`, `update`, `refill-create`, etc.). Use `ListChangedPrescriptions` for polling-based change detection.

---

### 8. Problems / Diagnoses (Chart)

- **Category:** Clinical / Chart
- **Direction:** PULL
- **Juno Use Case:** Pull the patient's active problem list (ICD-10 diagnoses) to personalize Juno's plain-language care guidance — e.g., tailor MS relapse content specifically for the patient's documented MS subtype.
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/problems`
- **Methods:** GET
- **Key fields:** Problem name, ICD-10 code, onset date, status (active/inactive), notes, provider
- **Notes:** Also available via FHIR R4 `Condition` resource. `PatientProblem` FHIR Subscription topic supports `create`, `update`, `delete` events. `ListChangedProblems` available for polling.

---

### 9. Discharge Info

- **Category:** Clinical / Hospital / Inpatient
- **Direction:** PULL
- **Juno Use Case:** For clinic practices that handle hospital admissions (neurology inpatient cases), retrieve discharge instructions and discharge summary text for translation into Juno's plain-language guidance.
- **Endpoint:** `GET /v1/{practiceid}/...` (exact path: docs.athenahealth.com/api/api-ref/discharge-info — unverified, confirm with Athena portal)
- **Methods:** GET, possibly PUT (unverified)
- **Key fields:** Discharge instructions text, discharge date, follow-up instructions, discharge diagnosis
- **Notes:** Companion endpoint `Hospital Systems Visit` (`docs.athenahealth.com/api/api-ref/hospital-systems-visit`) covers inpatient visit context. Most Athena practices are ambulatory; relevance depends on whether Juno's target clinics use Athena for inpatient. Verify endpoint availability and field structure during sandbox testing.

---

## MEDIUM Priority APIs

### 10. Orders (Patient Info Order / Patient Education)

- **Category:** Clinical Orders / Patient Education
- **Direction:** PULL
- **Juno Use Case:** Retrieve patient information / education orders placed by providers during the encounter, which may contain specific care instruction text or references to educational materials that Juno should amplify and translate.
- **Endpoint:** `GET /v1/{practiceid}/...` (see docs.athenahealth.com/api/api-ref/order-patient-info-order and docs.athenahealth.com/api/api-ref/order)
- **Methods:** GET
- **Key fields:** Order type (patient info/education), order text, instructions text, provider, encounter reference
- **Notes:** `PatientInfoOrder` FHIR Subscription topic [Alpha] — events: `create`, `update`, `delete`. This is the closest Athena API surface to "patient instructions" explicitly embedded in the clinical order workflow.

---

### 11. Encounter Service Notes / Encounter Chart

- **Category:** Clinical / Encounter
- **Direction:** PULL
- **Juno Use Case:** Access structured encounter service notes (SOAP note sections) as a supplement or alternative to the full `summaryhtml` endpoint — may expose finer-grained sections (HPI, ROS, physical exam, A&P separately).
- **Endpoints:**
  - docs.athenahealth.com/api/api-ref/encounter-service-notes
  - docs.athenahealth.com/api/api-ref/encounter-chart
- **Methods:** GET (unverified — confirm field-level structure with Athena docs)
- **Notes:** The Encounter overview page (`docs.athenahealth.com/api/docs/encounter`) documents that Athena supports vitals, screening questionnaires, diagnosis, history, and physical examination sections. These may be separate fields rather than free-text blobs — useful for structured extraction.

---

### 12. Encounter Document (Document Type)

- **Category:** Documents & Forms
- **Direction:** PULL
- **Juno Use Case:** Retrieve documents attached directly to an encounter (e.g., external referral docs, imaging reports, specialist notes attached to visit) that may add clinical context for Juno's pipeline.
- **Endpoint:** `GET /v1/{practiceid}/...` (see docs.athenahealth.com/api/api-ref/document-type-encounter-document)
- **Methods:** GET, possibly POST
- **Notes:** `ListEncounterDocuments` function confirmed in go-athenahealth SDK (`ListEncounterDocuments(ctx, departmentID, patientID, opts)`).

---

### 13. Patient (Demographics & Portal Access)

- **Category:** Patient Management
- **Direction:** PULL / PUSH
- **Juno Use Case (PULL):** Get patient demographics (name, DOB, preferred language, caregiver info, contact) to personalize Juno's plain-language content delivery — especially important for neurology patients where a caregiver may be the primary recipient.
- **Juno Use Case (PUSH):** Enable patient portal access (`POST /v1/{practiceid}/patients/{patientid}/...` portal access endpoint) or update patient contact info so Juno's link can be delivered.
- **Endpoints:**
  - `GET /v1/{practiceid}/patients/{patientid}` — patient record
  - `GET /v1/{practiceid}/patients/{patientid}/customfields` — practice-specific custom fields
  - docs.athenahealth.com/api/api-ref/patient-portal-access — portal access management
  - docs.athenahealth.com/api/api-ref/patient-portal-settings
- **Methods:** GET, POST, PUT
- **Key fields:** First name, last name, DOB, preferred language, email, phone, caregiver/guarantor info, portal enrollment status
- **Notes:** Patient FHIR Subscription topic supports `create`, `update`, `delete`, `merge` events. `ListChangedPatients` available for polling.

---

### 14. Allergies (Chart)

- **Category:** Clinical / Chart
- **Direction:** PULL
- **Juno Use Case:** Pull allergy list to include safety context in Juno's medication-related plain-language guidance.
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/allergies`
- **Methods:** GET
- **Key fields:** Allergen name, reaction, severity, onset date
- **Notes:** Also available as FHIR R4 `AllergyIntolerance` resource.

---

### 15. Lab Results

- **Category:** Clinical / Chart
- **Direction:** PULL
- **Juno Use Case:** Retrieve recent lab results to include in Juno's care guidance — especially for MS patients (MRI results, JC virus titers) or Parkinson's patients where results drive care instructions.
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/labresults`
- **Methods:** GET
- **Key fields:** Test name, LOINC code, value, units, reference range, abnormal flag, collection date
- **Notes:** FHIR R4 `DiagnosticReport` and `Observation` resources also provide lab data. `LabResult` FHIR Subscription topic events: `create`, `update`, `close`. `ListChangedLabResults` for polling.

---

### 16. User Message (Provider-to-Provider)

- **Category:** Internal Messaging
- **Direction:** PUSH
- **Juno Use Case:** Send an internal notification to the provider or care team (via Athena's internal message system) alerting them that a patient has not engaged with Juno's care summary, enabling proactive follow-up.
- **Endpoint:** docs.athenahealth.com/api/api-ref/user-message
- **Methods:** POST (unverified — confirm with Athena docs)
- **Notes:** Distinct from patient-facing Secure Messages. Intended for staff-to-staff communication within Athena. Juno could use this to send "Patient has not opened care instructions 72h post-visit" alerts to the care coordinator queue.

---

### 17. Appointment (Notes & Context)

- **Category:** Scheduling / Appointments
- **Direction:** PULL
- **Juno Use Case:** Pull appointment context (appointment type, provider, department, date) to pre-populate Juno's pipeline context before the encounter summary is signed; also pull appointment notes for any pre-existing patient instructions.
- **Endpoints:**
  - `GET /v1/{practiceid}/appointments/{appointmentid}` — appointment detail
  - docs.athenahealth.com/api/api-ref/appointment-notes — GET/POST appointment notes
- **Methods:** GET, POST
- **Key fields:** Appointment type, provider ID, department ID, patient ID, date/time, appointment notes
- **Notes:** `Appointment` FHIR Subscription topic events: `schedule`, `check-in`, `check-out`, `cancel`, `reschedule`. `ListChangedAppointments` for polling. The `Appointment.check-out` event can serve as an alternative trigger to `Encounter.signoff`.

---

### 18. Office Note (Document Type)

- **Category:** Documents & Forms
- **Direction:** PULL / PUSH
- **Juno Use Case (PULL):** Retrieve provider-authored office notes (distinct from auto-generated encounter summaries) for ingestion into Juno.
- **Juno Use Case (PUSH):** Post a Juno-generated structured note as an office note subtype if clinical workflows require it.
- **Endpoint:** docs.athenahealth.com/api/api-ref/document-type-office-note
- **Methods:** GET, POST (unverified — confirm with Athena docs)
- **Notes:** Separate from the generic Clinical Document class. May map more directly to provider-dictated notes vs. structured chart entries.

---

### 19. Letter (Document Type)

- **Category:** Documents & Forms
- **Direction:** PUSH
- **Juno Use Case:** Send a Juno-generated plain-language care letter (formatted for patient readability) as a Letter document, which Athena can deliver via portal, print-to-mail, or patient-facing communication.
- **Endpoint:** `POST /v1/{practiceid}/patients/{patientid}/documents/letter`
- **Methods:** POST (GET to list/retrieve)
- **Key fields:** Document content/attachment, addressee, department ID, provider attribution
- **Notes:** Letters in Athena can be routed to the patient portal or printed; this is a supported delivery channel. Confirm whether Athena allows hyperlinks within letter bodies for Juno's URL-based delivery model.

---

### 20. Changed Data Subscriptions (Legacy Polling)

- **Category:** Real-Time Integration / Polling
- **Direction:** PULL (trigger mechanism)
- **Juno Use Case:** Alternative to FHIR Event Subscriptions for practices that do not support the newer FHIR Subscription framework; poll for changed encounters, clinical documents, lab results, and patient records.
- **Endpoint:** `GET /v1/{practiceid}/{feedtype}/changed`
- **Supported feed types (verified):** patients, appointments, lab results, prescriptions, problems, providers, clinical documents
- **Methods:** GET
- **Notes:** Pull-based (Juno polls Athena, not push). Latency 1–5 minutes depending on polling interval. Subscription management: `GET /v1/{practiceid}/{feedtype}/changed/subscription`, `POST` to subscribe. Coexists with FHIR Subscriptions; use whichever is appropriate per practice configuration.

---

## LOW Priority / Awareness APIs

### 21. Vitals (Chart)
- **Direction:** PULL
- **Use Case:** Pull vital signs (BP, weight, BMI) as context for Juno's care guidance (e.g., "your blood pressure was X — here's what that means and what to do").
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/vitals`

### 22. Immunizations (Chart / FHIR)
- **Direction:** PULL
- **Use Case:** Include immunization status in Juno's care guidance for neurology patients on immunosuppressive therapies (e.g., MS biologics and live vaccine contraindications).
- **Endpoint:** `GET /v1/{practiceid}/chart/{patientid}/immunizations` or FHIR `Immunization`

### 23. Social History
- **Direction:** PULL
- **Use Case:** Context enrichment — pull smoking, alcohol, exercise habits for personalizing Juno's lifestyle recommendations in the care summary.
- **Endpoint:** `GET /v1/{practiceid}/patients/{patientid}/socialhistory`

### 24. Patient Custom Fields
- **Direction:** PULL / PUSH
- **Use Case:** Read practice-specific custom fields (e.g., "preferred caregiver contact") or write Juno-specific metadata (e.g., "Juno consent given", "last Juno link sent") into Athena's custom field system for workflow tracking.
- **Endpoint:** `GET/PUT /v1/{practiceid}/patients/{patientid}/customfields`

### 25. Medical Record (Document Type)
- **Direction:** PULL / PUSH
- **Use Case:** Retrieve externally uploaded medical records (e.g., hospital discharge records faxed in) that may contain discharge summaries not native to Athena.
- **Endpoint:** docs.athenahealth.com/api/api-ref/document-type-medical-record

### 26. Admin Document (Document Type)
- **Direction:** PUSH
- **Use Case:** Write administrative-category documents to the patient chart — e.g., log Juno engagement audit trail or attach signed consent to use Juno.
- **Endpoint:** `POST /v1/{practiceid}/patients/{patientid}/documents/admin`

### 27. Phone Message (Document Type)
- **Direction:** PUSH
- **Use Case:** Create a phone message document in the Athena queue — could be used to flag that a patient hasn't engaged with Juno content and needs a phone follow-up call from staff.
- **Endpoint:** docs.athenahealth.com/api/api-ref/document-type-phone-message

### 28. FHIR CarePlan
- **Direction:** PULL
- **Use Case:** Retrieve any structured care plans filed against the patient as context for Juno's output. Primarily read-only in Athena's FHIR API.
- **Endpoint:** `GET /fhir/r4/CarePlan?patient={id}`
- **Notes:** CarePlan support added as part of ONC HTI-1 Final Rule compliance (USCDI). Likely thin data in ambulatory workflows.

### 29. FHIR Procedure
- **Direction:** PULL
- **Use Case:** Retrieve procedures (e.g., nerve block, infusion, biopsy) as context for Juno's post-procedure care guidance.
- **Endpoint:** `GET /fhir/r4/Procedure?patient={id}`

### 30. Providers & Departments
- **Direction:** PULL
- **Use Case:** Look up provider name, specialty, and department to correctly attribute Juno content ("Your care summary from Dr. Smith, Neurology at Memorial Clinic").
- **Endpoints:** `GET /v1/{practiceid}/providers/{providerid}`, `GET /v1/{practiceid}/departments`

### 31. Appointment Reminders
- **Direction:** PULL / PUSH
- **Use Case:** Know when appointment reminders are sent to time Juno's post-visit follow-up appropriately; or integrate Juno into the reminder workflow.
- **Endpoint:** docs.athenahealth.com/api/api-ref/appointment (see Reminders section)

### 32. Telehealth Invite URL
- **Direction:** PULL
- **Use Case:** If a visit is telehealth, pull the telehealth URL as context for Juno's appointment summary content.
- **Endpoint:** `GET /v1/{practiceid}/appointments/{apptid}/telehealthinvite`

### 33. Patient Data Access Info
- **Direction:** PULL / PUSH
- **Use Case:** Track patient data access rights and any flags that would affect Juno's content delivery (e.g., minor patient with restricted portal access, proxy caregiver with full access).
- **Endpoint:** docs.athenahealth.com/api/api-ref/patient-data-access-info

### 34. CCD / CCDA Export (FHIR Bulk Data)
- **Direction:** PULL
- **Use Case:** Bulk export of patient clinical data (for analytics, longitudinal context, or onboarding a new clinic). Not for per-visit use.
- **Endpoint:** FHIR `$export` on Group resource; also `GET /v1/{practiceid}/patients/{patientid}/documents/clinicaldocument/{docid}/xml` for CCD per-patient

---

## Gaps & Limitations

### 1. Clinical Note Free Text May Not Be Directly Accessible
Athena's structured clinical notes (SOAP notes typed by providers) may not be exposed as raw text through a single endpoint. The `summaryhtml` field in the Encounter Summary is the closest available, but its completeness depends on the template the provider used. Providers using free-text addenda or structured templates may produce differently-shaped output. **Mitigation:** Use the FHIR `DocumentReference` endpoint to catch additional note types; test thoroughly in sandbox with realistic neurology note templates.

### 2. No Native "After-Visit Summary" Endpoint
Athena does not appear to expose an explicit "After Visit Summary" (AVS) as a dedicated API endpoint. The AVS printed at check-out is generated within Athena's workflow and is not directly retrievable via API. **Mitigation:** The encounter summary endpoint (`/chart/encounter/{id}/summary`) returns substantially the same content. Alternatively, if the AVS is filed as a clinical document, it may be retrievable via `DocumentReference` or the clinical document endpoint.

### 3. Discharge Summary Endpoint Availability Uncertain
The `Discharge Info` API (docs.athenahealth.com/api/api-ref/discharge-info) exists in the documentation index but full field details could not be confirmed without portal authentication. Many Athena practices are ambulatory-only; the discharge endpoint may be restricted to practices with hospital integration modules. **Action:** Verify during sandbox testing.

### 4. Secure Message Hyperlinks — Unconfirmed
Juno's core delivery model relies on sending patients a link. Whether Athena's Secure Message API supports hyperlinks in message body (and whether the athenaPatient portal renders them clickable) is unconfirmed. **Action:** Test in sandbox. If hyperlinks are not rendered, Juno must fall back to including the URL as plain text or embedding the summary content directly in the message.

### 5. Write-Back Requires athenaOne API (Not Free FHIR)
All PUSH operations (sending content back to Athena) require the proprietary athenaOne API, which is pay-per-call and requires the full partner program approval. The Certified FHIR R4 API is read-only. **Implication:** Juno cannot rely on the free Certified API pathway for any write-back features.

### 6. ClinicalDocument and AdminDocument Subscriptions Are Alpha
The FHIR Subscription topics for `ClinicalDocument`, `AdminDocument`, `MedicalRecord`, `PatientInfoOrder`, and `Letter` are currently marked [Alpha] in Athena's documentation. These may not be stable or available in all practices. **Mitigation:** Use `Encounter.signoff` (non-alpha) as the primary trigger; treat clinical document subscriptions as supplemental.

### 7. Athena Does Not Expose Ambient Note Content via API (as of mid-2025)
Athena's own AI scribe product (athenaAmbient, announced Nov 2025, GA expected mid-2026) generates SOAP notes that are filed as encounter notes. Access to these notes via API is not yet confirmed — they may require the same DocumentReference/encounter summary path as human-authored notes, or may be restricted. **Action:** Confirm with Athena during partner onboarding.

### 8. Patient Engagement Metrics Cannot Be Written Back Easily
Juno's engagement data (link opened, checklist completed, comprehension quiz results) has no native Athena destination. The best current option is a Patient Case note or Admin Document — neither provides structured fields for metrics. **Mitigation:** Store engagement data in Juno's own backend; surface in Athena via human-readable notes. Long-term, explore Athena's Custom Fields API for structured metric storage.

### 9. Rate Limits for Event-Driven Architectures
Athena's FHIR Subscription events are `id-only` — each event notification requires a follow-up API call to fetch content. For a large practice with many daily encounters, this can generate significant API call volume. Rate limits are not publicly disclosed and must be negotiated during partner onboarding. **Mitigation:** Implement event deduplication, queue-based processing, and exponential backoff.

---

## Integration Sequencing Recommendation

### Phase 1 — Sandbox Validation (Weeks 1–4)
**Goal:** Confirm data availability and shape; validate Juno's translation pipeline on real Athena data structures.

1. Register at developer.athenahealth.com — obtain sandbox credentials (immediate)
2. Authenticate via OAuth 2.0 `client_credentials` grant
3. Test **Encounter Summary** (`GET /chart/encounter/{id}/summary`) — validate `summaryhtml` field content and completeness for neurology encounter templates
4. Test **FHIR DocumentReference** (`GET /fhir/r4/DocumentReference?patient=...`) — validate note retrieval and content types returned
5. Test **Medications, Problems, Allergies** chart endpoints — validate data completeness
6. Test **FHIR Subscriptions** for `Encounter.signoff` — validate webhook delivery and follow-up call pattern
7. Test **Patient Case document POST** — validate write-back creates visible record in Athena UI
8. Test **Secure Messages POST** — validate patient portal delivery and hyperlink rendering

### Phase 2 — Marketplace Application (Weeks 4–16)
**Goal:** Obtain production access.

1. Submit Marketplace partner application with Juno's integration plan, architecture, and security documentation
2. Execute BAA with athenahealth
3. Complete security review (pentest, encryption attestation)
4. Negotiate rate limits and per-call pricing for athenaOne API endpoints

### Phase 3 — Pilot Integration (Weeks 12–20)
**Goal:** Live integration with one pilot neurology clinic.

1. Deploy `Encounter.signoff` subscription listener
2. Implement PULL pipeline: signoff → encounter summary + medications + problems → Juno translation
3. Implement PUSH pipeline: Juno link → Secure Message to patient + Patient Case note to provider
4. Measure: time from encounter signoff to patient receiving Juno link (target: <5 minutes)

### Phase 4 — Full Feature Integration (Post-pilot)
1. Add Orders / Patient Info Order pull for explicit provider-ordered education content
2. Add engagement metric write-back via Patient Case notes or Admin Documents
3. Add Lab Results pull for result-contextualized care guidance
4. Explore Discharge Info endpoint for inpatient-adjacent workflows
5. Add provider alert via User Message API when patient has not engaged

---

## Open Questions for Athena

1. **Secure Message hyperlinks:** Does the Athena Patient Portal (athenaPatient) render hyperlinks in secure message bodies as clickable? Is this configurable per practice?
2. **After-Visit Summary:** Is the printed AVS available as a retrievable document via API after check-out? Which document class does it file as?
3. **Encounter note text completeness:** Does `summaryhtml` from `GET /chart/encounter/{id}/summary` include all sections authored by the provider (including free-text addenda, scanned documents attached to the encounter)?
4. **athenaAmbient notes:** When athenaAmbient (GA mid-2026) generates SOAP notes, will they be accessible via the same `DocumentReference` or Encounter Summary endpoints as human-authored notes?
5. **ClinicalDocument subscription GA timeline:** When will the `ClinicalDocument.create/update` FHIR Subscription topic exit Alpha?
6. **Discharge Info API availability:** Is the Discharge Info API available in standard athenaOne ambulatory configurations, or only with hospital systems modules?
7. **Write-back document visibility:** For documents POSTed via the Clinical Document or Admin Document endpoints, which Athena UI views does the care team see them in? Are they visible in the patient's chart without additional configuration?
8. **Rate limit tiers:** What are the production rate limits for Juno's expected call volume (~100–500 encounters per day per clinic)?
9. **Per-call pricing:** What is the per-call cost for the athenaOne proprietary API endpoints Juno needs (encounter summary, secure messages, document POST)?
10. **Patient Case vs. Secure Message for PUSH:** Is a Patient Case note (with patient portal delivery) functionally equivalent to a Secure Message from the patient's perspective, or are they different communication channels?
11. **Caregiver proxy access:** Can Juno's Secure Messages be routed to a registered caregiver proxy (common in neurology patients with cognitive impairment) rather than directly to the patient?
12. **FHIR write-back roadmap:** Is athenahealth planning to add FHIR write-back capabilities (e.g., `Communication` resource POST) in future releases that would reduce reliance on proprietary endpoints?

---

## Key Sources

- Athenahealth FHIR Subscriptions GitHub: https://github.com/athenahealth/aone-fhir-subscriptions
- go-athenahealth SDK: https://pkg.go.dev/github.com/eleanorhealth/go-athenahealth/athenahealth
- Athenahealth DocumentReference StructureDefinition: https://fhir.athena.io/athenacoreext/StructureDefinition-ah-documentreference.html
- Integration pathway comparison: https://alsgaardmiller.com/blog/athenahealth-integration-understanding-the-3-available-pathways
- tactionsoft integration guide: https://www.tactionsoft.com/blog/athenahealth-api-integration-guide/
- FHIR Event Notifications blog: https://www.athenahealth.com/resources/blog/fhir-subscriptions-event-driven-apis
- Athena developer portal: https://mydata.athenahealth.com / https://docs.athenahealth.com/api
- All APIs index: https://docs.athenahealth.com/api/docs/all-apis
- Marketplace partners: https://www.athenahealth.com/solutions/marketplace-partners
