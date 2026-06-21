# HIPAA Compliance Roadmap for Juno

> **Disclaimer:** This document is a technical planning resource, not legal advice. HIPAA compliance involves legal, operational, and technical dimensions that require interpretation by qualified healthcare counsel and a certified compliance professional. Use this as a starting framework, then validate with legal.

> **Research date:** June 2026. HIPAA regulations and vendor BAA coverage change — always verify vendor BAA status directly with the vendor before onboarding PHI.

---

## Executive Summary

Juno processes Protected Health Information (PHI) — clinical notes, discharge summaries, SOAP notes, patient identifiers, and AI-generated care plan outputs — on behalf of clinic customers. This makes Juno a **Business Associate** under HIPAA, and its clinic customers are Covered Entities. Juno must execute a Business Associate Agreement (BAA) with every clinic customer and with every vendor that handles PHI on Juno's behalf.

**The three biggest compliance risks, in order of severity:**

1. **Gemini API via `GEMINI_API_KEY` (Critical — likely active violation):** Juno's backend currently supports a `GEMINI_API_KEY` path that sends PHI to Google AI Studio's Gemini API. Google AI Studio is a free developer playground explicitly excluded from Google's HIPAA BAA. Sending PHI through it is a HIPAA violation. If `GEMINI_API_KEY` is set in production (the deploy workflow in `.github/workflows/deploy-backend.yml` injects it as `GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}`), this is an active gap that must be closed before any PHI flows through the system.

2. **Firebase Authentication is not covered under Google's HIPAA BAA:** Juno uses Firebase Authentication for user identity. Firebase Authentication does not appear on Google's HIPAA covered services list. It must be replaced with Google Cloud Identity Platform (the enterprise-grade successor, covered under the BAA) before PHI is linked to user identities.

3. **No HIPAA BAA has been executed yet:** No evidence of an executed Google Cloud HIPAA BAA exists in the codebase. Without a signed BAA, none of Juno's GCP infrastructure — even the covered services — is contractually HIPAA compliant.

**The positive news:** Juno's core infrastructure (Cloud Run, Firestore, Cloud Storage, Cloud Tasks) is all on the GCP covered services list. Firebase Hosting, Firestore (the database), and Cloud Storage are addressed in the BAA. The architecture is largely sound — the critical gaps are the AI API path and authentication layer, plus the operational and administrative program that doesn't yet exist.

**Overall posture:** Pre-compliant. Juno has good bones (GCP infrastructure, JWT auth, structured logging, session tracking) but is missing the contractual, administrative, and several technical components required by HIPAA. Estimated time to full technical readiness: 60–90 days with dedicated effort. Administrative program: 90–120 days.

---

## HIPAA Overview

### What HIPAA Actually Requires (the regulatory picture)

HIPAA is not a single standard — it is three interlocking rules administered by the HHS Office for Civil Rights (OCR):

- **Privacy Rule** (45 CFR Part 164, Subparts A and E): Governs who can access PHI, patient rights (access, amendment, accounting of disclosures), minimum necessary standard, and permissible uses/disclosures.
- **Security Rule** (45 CFR Part 164, Subpart C): Governs how ePHI (electronic PHI) must be protected. Contains three categories of safeguards: Administrative, Physical, and Technical. Each safeguard has "required" and "addressable" implementation specifications.
- **Breach Notification Rule** (45 CFR Part 164, Subpart D): Governs what must happen when a breach of unsecured PHI occurs — notification timelines, content, and reporting to HHS.

**Important 2025 Update — Proposed HIPAA Security Rule Overhaul:**
On January 6, 2025, HHS published a Notice of Proposed Rulemaking (NPRM) that would significantly strengthen the Security Rule. Key proposed changes:
- Remove the distinction between "required" and "addressable" specifications — everything becomes required
- Mandate encryption of ePHI at rest and in transit (currently "addressable")
- Mandate MFA for all ePHI access (currently "addressable")
- Require biannual vulnerability scans and annual penetration testing
- Network segmentation requirements

This rule is expected to finalize in mid-2026 and is directionally where HIPAA is heading. Juno should build to the proposed standard, not just the current one.

### PHI Definition — What Juno Data Qualifies

Protected Health Information (PHI) is individually identifiable health information created, received, maintained, or transmitted by a covered entity or business associate. The 18 HIPAA identifiers include: names, dates (birth date, service dates), geographic data below state level, phone/fax numbers, email addresses, medical record numbers, health plan numbers, account numbers, certificate/license numbers, IP addresses, URLs, device identifiers, biometric identifiers, and any other unique identifying number or code.

**What Juno data is PHI:**
- Clinical notes, SOAP notes, discharge summaries uploaded by clinicians — clearly PHI (contain patient name, DOB, condition, provider identifiers)
- AI-generated care plan outputs — PHI (derived from PHI, contain patient-identifiable content)
- Stored care plan outputs in Firestore (`care_plan_outputs` collection) — PHI
- PDFs stored in GCS under `care_plan/{user_id}/inputs/` — PHI
- Patient engagement/adherence tracking data — PHI when linked to individuals
- User accounts for clinicians — may contain PHI-adjacent data (linked to patient records)

**Minimum Necessary Standard:** Juno must ensure it only uses, discloses, or requests the minimum amount of PHI necessary to accomplish the intended purpose. Each AI prompt should be evaluated: does the Gemini call require the full clinical note, or could a subset suffice?

### The Three Rules: Privacy, Security, Breach Notification

**Privacy Rule:** As a Business Associate, Juno's obligations include:
- Only using PHI for purposes specified in its BAA with clinic customers
- Not using/disclosing PHI in ways not permitted by the BAA
- Implementing safeguards (the Privacy Rule's administrative safeguards overlap with Security Rule requirements)
- Reporting impermissible uses and disclosures to the Covered Entity
- Making books and records available to HHS if requested

**Security Rule:** See Technical Safeguards section for full breakdown.

**Breach Notification Rule:** See dedicated section below.

---

## Business Associate Agreements (BAAs) — Critical for Juno

A BAA is a written contract that establishes the permitted and required uses of PHI and commits the Business Associate to HIPAA compliance. Required contents (45 CFR 164.504(e)): permitted uses/disclosures, safeguard implementation, breach notification obligations, subcontractor compliance chain, PHI access rights, HHS audit access, and PHI return/destruction on contract termination.

Juno needs BAAs in two directions:
1. **Downstream (with clinic customers):** Juno must offer a BAA to every clinic customer before any PHI flows into the system.
2. **Upstream (with vendors):** Juno must have BAAs with every vendor that handles PHI on its behalf.

### Google Cloud / GCP BAA — What's Covered

**How to execute:** Google Cloud customers can execute the BAA through the GCP Console under Account > Legal / Privacy Compliance. It is a clickwrap agreement; once accepted, it is legally binding.

**Covered GCP services (relevant to Juno):**
| Service | Juno Uses It | BAA Covered |
|---|---|---|
| Cloud Run | Yes (API + worker services) | YES |
| Cloud Storage (GCS) | Yes (file storage) | YES |
| Firestore | Yes (database) | YES |
| Cloud Tasks | Yes (job queuing) | YES |
| Cloud Build | Yes (CI/CD) | YES |
| Cloud Logging | Yes (structured logs) | YES |
| Cloud Trace | Yes (OpenTelemetry) | YES |
| Secret Manager | Yes (service account JSON) | YES |
| Vertex AI | Yes (if GEMINI_API_KEY not set) | YES (see Gemini section) |
| Identity Platform | Not yet — needed | YES |

**Key action required:** Execute the Google Cloud BAA. Without it, none of these covered services are contractually compliant, even if they are technically on the list.

### Firebase BAA — What's Covered and NOT Covered

This is where Juno has a significant gap. Firebase is Google's consumer-oriented developer platform, and many Firebase services are **not** on Google's HIPAA covered services list.

**Firebase services breakdown:**
| Firebase Service | Juno Uses It | BAA Covered | Notes |
|---|---|---|---|
| Firebase Authentication | YES — primary auth | NO | Must migrate to Identity Platform |
| Firebase Hosting | YES — frontend | NO | Must migrate to Cloud Run or another covered host |
| Firestore (via Firebase SDK) | YES — database | YES | Firestore itself is covered; Firebase SDK access is covered if BAA executed |
| Cloud Storage (via Firebase SDK) | YES | YES | Same: storage is covered; the Firebase SDK path is acceptable post-BAA |
| Firebase Analytics | Unknown | NO | Cannot touch PHI under any circumstances |
| Firebase Realtime Database | Not used | NO | Irrelevant |
| Crashlytics | Possibly via frontend | NO | Cannot receive PHI or PII |
| Performance Monitoring | Possibly via frontend | NO | Cannot receive PHI |
| Remote Config | Unknown | NO | Cannot receive PHI |

**Critical Firebase gaps:**

**1. Firebase Authentication (NOT covered):**
The frontend at `/root/projects/juno/frontend/src/api/firebase.ts` and `/root/projects/juno/frontend/src/auth/AuthContext.tsx` uses `firebase/auth` and `getAuth(firebaseApp)`. The backend at `/root/projects/juno/backend/utils/firebase.py` uses `firebase_admin.auth.verify_id_token()`. All of this flows through Firebase Authentication, which is not a HIPAA covered service.

The HIPAA-covered alternative is **Google Cloud Identity Platform**, which is the same underlying technology but exposed under the Cloud project (rather than the Firebase project) and explicitly listed on Google's BAA covered services list. The migration is not trivial but is architecturally similar — Identity Platform supports the same JWT-based flows.

**2. Firebase Hosting (NOT covered):**
The production frontend env (`/root/projects/juno/frontend/.env.production`) shows `VITE_FIREBASE_AUTH_DOMAIN=juno-medical-clarity.firebaseapp.com`, confirming Firebase Hosting is in use. Firebase Hosting is not a BAA-covered service. If the frontend itself contains or transmits PHI (e.g., displays care plan content in the browser), this is a gap.

**Practical note on Firebase Hosting:** The frontend primarily renders the SPA shell and calls the backend API — the PHI lives in the API responses, not in static assets. However, if any PHI is cached in browser storage or served through Firebase Hosting routes, it creates a gap. The clean path is migrating to Cloud Run-served static assets or a covered CDN, or treating Firebase Hosting as a PHI-free presentation layer with strict controls on what is cached.

**3. Firebase Measurement ID (`G-4R0CDYKSPW` in `.env.production`):**
The production env file contains `VITE_FIREBASE_MEASUREMENT_ID=G-4R0CDYKSPW`, which indicates Google Analytics for Firebase is configured. Analytics is explicitly not covered under the Google Cloud BAA. If the frontend sends any PHI (e.g., URL parameters, form content, page titles containing patient names) to Analytics, this is a HIPAA violation. OCR collected over $9.9 million in penalties in 2024 specifically targeting hidden data flows from website tracking tools.

### Gemini API — Is It Covered? (THE CRITICAL FINDING)

**The Gemini API accessed via `GEMINI_API_KEY` (from Google AI Studio) is NOT covered under Google's HIPAA BAA.**

This is the single most important compliance finding for Juno. Here is the precise breakdown:

| Access Path | BAA Covered | Safe for PHI |
|---|---|---|
| Gemini via Vertex AI (on a GCP project with executed BAA) | YES | YES |
| Gemini via `GEMINI_API_KEY` from Google AI Studio (aistudio.google.com) | NO | NO |
| Gemini consumer app (gemini.google.com) | NO | NO |
| Gemini in Google Workspace (with Workspace BAA) | YES | YES (different context) |

**Juno's current code (`/root/projects/juno/backend/utils/llm.py`, lines 33–38):**
```python
if os.environ.get("GEMINI_API_KEY"):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    self._gemini_model = genai.GenerativeModel(model_name)
    self._use_gemini_api = True
```

**The deployment workflow (`.github/workflows/deploy-backend.yml`, line 55):**
```
GEMINI_API_KEY=${{ secrets.GEMINI_API_KEY }}
```

If `secrets.GEMINI_API_KEY` is set in GitHub, then **every production request is sending PHI to a non-BAA-covered endpoint.** This is the highest-priority remediation item.

**The fix:** Remove `GEMINI_API_KEY` from production. Use only the Vertex AI path (the `else` branch in `LLMClient.__init__`), which is HIPAA-covered when a Cloud BAA is executed. Vertex AI exposes the same Gemini models (including `gemini-1.5-pro` and `gemini-2.0-flash`) and requires no `GEMINI_API_KEY` — it uses the service account credentials already configured in Cloud Run.

**Additional AI/PHI consideration:** Google's Vertex AI terms for covered workloads prohibit using customer data to train Google's models. This is a key difference from the consumer Gemini API. Verify this clause is present in the executed BAA.

### Other Vendor BAAs Needed

| Vendor | How Used | BAA Available | Action |
|---|---|---|---|
| Google Cloud (GCP) | Core infrastructure | YES | Execute immediately |
| Firebase Auth | Authentication | N/A (not covered) | Migrate to Identity Platform |
| Gemini via AI Studio | AI processing (if GEMINI_API_KEY set) | NO | Remove; use Vertex AI only |
| GitHub | Code hosting, CI/CD | YES (GitHub Enterprise) | Source code only — PHI should never be in the repo; confirm no PHI in test fixtures |
| Any future analytics vendors | Product analytics | Varies | Must vet before connecting to PHI flows |

---

## Technical Safeguards Required

### 45 CFR §164.312 — Technical Safeguards

#### (a) Access Control

**What HIPAA requires:**
- (a)(1) Unique user identification (Required): Each user must have a unique identifier
- (a)(2)(i) Emergency access procedure (Required): Documented procedure for obtaining ePHI during emergencies
- (a)(2)(ii) Automatic logoff (Addressable → Required under proposed 2026 rule)
- (a)(2)(iii) Encryption/decryption (Addressable → Required under proposed 2026 rule)

**Juno's current state:**
- Unique user identification: Partially met. Firebase Auth provides UIDs, and `verify_firebase_token` sets `g.user_id`. Each Firestore document has a `uid` field. The `get_owned_doc_or_403()` function enforces ownership. However, Firebase Auth itself is not BAA-covered.
- Emergency access: Not documented. No formal break-glass procedure exists.
- Automatic logoff: Not implemented in the frontend. The `AuthContext.tsx` uses `onAuthStateChanged` but there is no session timeout or inactivity logoff.
- Encryption/decryption: GCS and Firestore use Google-managed encryption at rest by default. This is generally sufficient but Customer-Managed Encryption Keys (CMEK) should be evaluated for high-sensitivity clinics.

**What's needed:**
- Migrate from Firebase Auth to Identity Platform
- Implement automatic session timeout on the frontend (15–30 minutes of inactivity is typical)
- Document emergency access procedures
- Evaluate CMEK for GCS buckets containing PHI

#### (b) Audit Controls

**What HIPAA requires (Required):**
Implement hardware, software, and/or procedural mechanisms that record and examine activity in information systems that contain or use ePHI. HIPAA does not specify exactly what to log but the standard is: who accessed what PHI, when, from where, and what action was taken.

**Minimum log events required:**
- Every access to PHI (read, create, update, delete)
- Login/logout events (success and failure)
- Authentication failures and lockouts
- Privilege changes or administrative actions
- Exports of PHI (downloads)
- PHI transmitted to third parties (Gemini/Vertex AI calls)

**Retention:** 6 years minimum. Logs must be tamper-resistant.

**Juno's current state:**
The backend has a solid logging infrastructure (`logging_config.py`, `juno_logger.py`, `markers/`). Structured JSON logs are emitted to Cloud Logging (stdout on Cloud Run), which is a GCP covered service. However:

- Logs include `user_id`, `session_id`, `http_method`, `http_path`, and request duration — this is a good foundation
- What is **not** logged: specific document IDs accessed (which Firestore document was read), which GCS file was accessed, whether a care plan was downloaded (the `handleDownloadJson` and `handleDownloadPdf` functions in the frontend fire without any backend audit event)
- GCS access logs: not explicitly configured in the codebase
- Firestore audit logs: Firestore does not emit per-read access logs by default; Cloud Audit Logs (Data Access logs) must be explicitly enabled
- The `save_care_plan_output` function in `firebase.py` writes to Firestore but does not generate an explicit HIPAA audit event
- Log retention period: not configured to 6 years (Cloud Logging default retention is 30 days unless explicitly extended)

**What's needed:**
- Enable Cloud Audit Logs (Data Access) for Firestore and GCS in GCP Console
- Add PHI access event logging to every Firestore read/write operation on `care_plan_outputs`
- Add audit events for GCS file access (uploads, downloads, signed URL generation)
- Add audit logging for every Vertex AI/Gemini call (timestamp, user_id, document_id, model used)
- Configure Cloud Logging bucket retention to 6 years (or export to GCS with lifecycle policies)
- Add backend endpoint to record "care plan downloaded" events (frontend currently downloads without server knowledge)
- Log the signed URL generation in `get_input_pdf_url()` — this is already present in `saved_outputs.py` but should include user_id and document_id in a dedicated PHI access log

#### (c) Integrity Controls

**What HIPAA requires:**
PHI must not be improperly altered or destroyed. Addressable: implement electronic mechanisms to corroborate that ePHI has not been altered or destroyed in an unauthorized manner.

**Juno's current state:**
- GCS object versioning: not confirmed in the codebase. GCS supports versioning but it must be explicitly enabled on the bucket.
- Firestore: documents have `created_at` and `updated_at` timestamps but no change audit trail or version history
- No hash/checksum verification of stored PHI

**What's needed:**
- Enable GCS object versioning on PHI buckets
- Consider Firestore change streams or Cloud Logging Data Access logs for write audit trails
- Document the data integrity controls in the security policy

#### (d) Person or Entity Authentication

**What HIPAA requires (Required):**
Implement procedures to verify that a person or entity seeking access to ePHI is the one claimed.

**Juno's current state:**
Firebase JWT tokens are verified on every authenticated endpoint via `@verify_firebase_token`. The token includes a UID, expiry, and is cryptographically signed by Firebase. This is technically sound but dependent on Firebase Auth, which is not BAA-covered.

MFA is not required or enforced for clinician accounts currently.

**What's needed:**
- Migrate to Identity Platform (BAA-covered)
- Enforce MFA for all clinician accounts (required under the proposed 2026 Security Rule; strongly recommended now)
- Add account lockout policies after repeated authentication failures

#### (e) Transmission Security

**What HIPAA requires:**
Implement technical security measures to guard against unauthorized access to ePHI that is being transmitted over electronic communications networks. Addressable: encryption.

**Juno's current state:**
- Cloud Run enforces HTTPS with Google-managed TLS certificates (confirmed via `deploy-backend.yml` — Cloud Run always serves HTTPS)
- Frontend serves via HTTPS (Firebase Hosting enforces HTTPS)
- GCS signed URLs are HTTPS
- Internal GCP traffic (Cloud Run to Firestore, Cloud Run to GCS) is encrypted in transit via Google's internal network
- Vertex AI calls are HTTPS

**What's needed:**
- Verify TLS 1.2 minimum is enforced (Cloud Run enforces this by default)
- Document transmission security controls in the security policy
- Ensure any future patient-facing links (e.g., the shareable care plan link mentioned in the product description) are served over HTTPS with appropriate link-level access controls

---

## Administrative Safeguards Required

### 45 CFR §164.308 — Administrative Safeguards

#### (a)(1) Security Management Process (Required)
- Risk Analysis (Required): Conduct an accurate and thorough assessment of potential risks and vulnerabilities to ePHI
- Risk Management (Required): Implement security measures to reduce identified risks
- Sanction Policy (Required): Apply appropriate sanctions against workforce members who fail to comply
- Information System Activity Review (Required): Regularly review records of information system activity

**Juno's current state:** No formal risk analysis has been conducted. No documented sanction policy. Log review process is informal.

**What's needed:**
- Conduct a formal HIPAA Risk Analysis using the NIST SP 800-30 methodology (HHS endorses this approach). The risk analysis must be documented and updated whenever there are significant environmental or operational changes.
- Create a Risk Management Plan that prioritizes and schedules remediation of identified risks
- Draft a Sanction Policy (can be 1–2 pages)
- Establish a regular (at minimum annual) log review process

#### (a)(2) Assigned Security Responsibility (Required)
Designate a security official responsible for developing and implementing security policies and procedures.

**Juno's current state:** Not formally designated. For early-stage startups, this is typically the CTO or a co-founder.

**What's needed:** Formally designate a Security Officer in writing. This can be the technical co-founder. Document the designation.

#### (a)(3) Workforce Security (Required)
Authorization and supervision procedures, workforce clearance procedures, and termination procedures.

**What's needed:** Access provisioning and de-provisioning process. Off-boarding checklist that includes revoking GCP access, Firebase access, and GitHub access within 24 hours of termination.

#### (a)(4) Information Access Management (Required)
Policies for authorizing access to ePHI, role-based access controls.

**What's needed:** Document who has access to what PHI and why. GCP IAM audit to ensure least-privilege principle (developers should not have direct production Firestore read access in normal operations).

#### (a)(5) Security Awareness and Training (Required)
Security reminders, protection from malicious software, log-in monitoring, password management.

**What's needed:** Annual HIPAA security training for all workforce members who handle ePHI. Training records must be kept. Multiple HIPAA training platforms exist ($10–50/person/year).

#### (a)(6) Security Incident Procedures (Required)
Policies and procedures for responding to security incidents.

**What's needed:** Incident Response Plan documenting how Juno will detect, contain, investigate, and report security incidents. Must address breach assessment process (see Breach Notification Rule section).

#### (a)(7) Contingency Plan (Required)
Data backup plan, disaster recovery plan, emergency mode operation plan, testing and revision procedures, and applications and data criticality analysis.

**What's needed:**
- GCS cross-region backup configuration for PHI documents
- Firestore backup configuration
- Documented RTO/RPO targets
- Annual disaster recovery test documentation

#### (a)(8) Evaluation (Required)
Periodic technical and nontechnical evaluation of the extent to which policies and procedures meet HIPAA Security Rule requirements.

**What's needed:** Annual internal or third-party HIPAA assessment.

#### (b) Business Associate Contracts and Other Arrangements (Required)
Written BAA with every vendor that creates, receives, maintains, or transmits PHI on Juno's behalf.

---

## Physical Safeguards

### 45 CFR §164.310 — Physical Safeguards

Physical safeguards primarily cover workstation security, device controls, and facility access controls. For a cloud-native SaaS on GCP:

**Data center controls (Handled by Google):** GCP data centers are ISO 27001 certified, SOC 2 Type II audited, and explicitly covered under the Google Cloud BAA. Google handles physical access controls, environmental controls, and media disposal for covered services. Juno does not need to verify or audit Google's data center controls beyond reviewing Google's compliance documentation (available at cloud.google.com/security/compliance).

**Workstation and device controls (Juno's responsibility):**
- Workstation use policy: what can be done on company devices vs. personal devices, screen lock requirements
- Full-disk encryption on developer machines (macOS FileVault, Windows BitLocker)
- Screen lock after inactivity
- No PHI in local development environments unless isolated and controlled
- Secure disposal of devices that may have contained PHI

**Media controls:**
- GCS object versioning and lifecycle policies for secure deletion
- Documented process for what happens to PHI if a clinic customer terminates (BAA must address this)

**Biggest physical safeguard gap:** The presence of service account key JSON files in the repository root (`gcp-sa-key.json` and `juno-medical-clarity-firebase-adminsdk-fbsvc-91f08cee6f.json`). These files appear to be checked into the repository. If the repository is not perfectly access-controlled, these keys could be compromised, allowing unauthorized access to GCP/Firebase. These keys should be immediately revoked and rotated, and never stored in the repository.

---

## Breach Notification Rule

### What Triggers a Breach

A breach is an impermissible use or disclosure of unsecured PHI that compromises its security or privacy, unless a four-factor risk assessment shows a low probability of compromise:
1. Nature and extent of PHI involved
2. Who accessed or used the PHI (or to whom it was disclosed)
3. Whether PHI was actually acquired or viewed
4. Extent to which risk has been mitigated

PHI is "unsecured" unless it is encrypted in a manner that renders it unreadable, unusable, and indecipherable. This is why encryption at rest matters — encrypted PHI that is accessed without authorization may not trigger the breach notification requirement if the keys were not compromised.

### Timeline Requirements

| Action | Deadline |
|---|---|
| Business Associate (Juno) notifies Covered Entity (clinic) | No later than 60 days from discovery |
| Covered Entity notifies affected individuals | No later than 60 days from discovery |
| Covered Entity notifies HHS (500+ affected individuals) | No later than 60 days from discovery |
| Covered Entity notifies prominent local media (500+ in one state) | No later than 60 days from discovery |
| Covered Entity notifies HHS (<500 individuals) | No later than 60 days after end of the calendar year |

**Discovery:** The clock starts when the breach is first known, not when the investigation concludes.

### What Juno's Breach Notification Process Must Include

1. A defined process for detecting potential breaches (monitoring, alerts)
2. A documented breach assessment procedure (the four-factor risk assessment)
3. A template notification to clinic customers (covered entities)
4. Contact information for each clinic's privacy officer (to be collected in BAA)
5. HHS reporting capability (for Juno's own breaches, or to assist covered entities)

### Current Gaps

No breach notification process, incident response plan, or breach assessment procedure exists in Juno's documentation.

---

## AI/LLM Specific HIPAA Considerations

### The Core Question: Is Your AI Provider a Business Associate?

Yes. Any AI/LLM vendor that receives PHI on behalf of a covered entity or their business associate is itself a Business Associate and must sign a BAA. The AI system does not need to make autonomous decisions — simply processing PHI as part of a service makes it a BA.

### Gemini via Vertex AI — Key Requirements

When using Gemini via Vertex AI under a signed Google Cloud BAA:
- Google commits to not using customer data to train its models (verify this clause in the executed BAA)
- PHI is processed in the customer's chosen GCP region (for Juno: `us-central1` per the config)
- IAM controls and audit logging apply
- No data retention beyond the request processing window (by default — verify)

### Data Retention Risks with AI APIs

The consumer Gemini API (via `GEMINI_API_KEY`) may retain conversation data for model improvement. This is explicitly not allowed for PHI. This is one reason the Gemini API / AI Studio path is not HIPAA eligible — the data handling terms do not support PHI.

Vertex AI's terms for covered workloads prohibit training on customer data and have defined data retention windows. Always verify the current terms when executing the BAA.

### Prompt Engineering and PHI Minimization

Even with a BAA-covered AI service, Juno should evaluate whether every clinical note needs to be sent in full. Consider:
- Sending only the sections relevant to the care plan generation step
- De-identifying patient names and other direct identifiers before sending to the LLM where clinically feasible (though de-identification itself has risks)
- Documenting the data minimization approach in the security policy

### HHS Section 1557 / Non-Discrimination

HHS issued guidance in 2024 requiring healthcare organizations using AI for patient care decision support to assess and mitigate discrimination risks by May 1, 2025. Juno's "Juno translates, it does not interpret" principle is an important safeguard, but the company should document its approach to avoiding discriminatory outputs and implement a human review capability.

### Model Training Prohibition

Juno must ensure its BAA with Google explicitly prohibits Google from using Juno's PHI (including clinical notes) to train or improve its AI models. This clause must be present and verified before PHI flows through Vertex AI.

---

## Juno Architecture Gap Analysis

### Backend Gaps (specific files/components)

**`/root/projects/juno/backend/utils/llm.py`:**
- Lines 33–38: `GEMINI_API_KEY` path sends PHI to non-BAA-covered endpoint
- No PHI access audit event is emitted when Gemini is called
- No logging of which document or patient data was sent to AI

**`/root/projects/juno/backend/utils/firebase.py`:**
- Uses `firebase_admin.auth` for token verification — Firebase Auth is not BAA-covered
- `save_care_plan_output()` writes PHI to Firestore but emits no explicit PHI access audit event
- `get_owned_doc_or_403()` reads PHI without emitting a PHI access audit event

**`/root/projects/juno/backend/routes/care_plan.py`:**
- `upload_combined_pdf()` uploads PHI to GCS without a PHI access audit event
- `_fetch_from_gcs()` reads PHI from GCS without a PHI access audit event
- The pipeline processes PHI but there is no "PHI processed" audit event with document identifiers

**`/root/projects/juno/backend/routes/saved_outputs.py`:**
- `get_saved()` reads PHI from Firestore without a PHI access audit event
- `get_input_pdf_url()` generates a signed GCS URL (30-minute expiry) without logging which user accessed which document
- `delete_saved()` deletes PHI without a PHI destruction audit event

**`/root/projects/juno/backend/app.py`:**
- Request logging (`log_request_start`, `log_request_end`) captures HTTP path but not specific document IDs
- No automatic session timeout enforcement at the API layer
- CORS is wide open: `CORS(app, expose_headers=["X-Session-Id", "X-Trace-Id"])` — should be restricted to known origins

**`/root/projects/juno/backend/logging_config.py`:**
- Cloud Logging retention is not configured to 6 years
- No log integrity/tamper protection configuration

**`/root/projects/juno/backend/config.py`:**
- `GEMINI_API_KEY` path is configured and injected at deploy time

### Frontend Gaps

**`/root/projects/juno/frontend/src/api/firebase.ts`:**
- Uses Firebase SDK (`firebase/auth`, `getAuth`) — Firebase Authentication is not BAA-covered

**`/root/projects/juno/frontend/src/auth/AuthContext.tsx`:**
- No session timeout / automatic logoff based on inactivity
- No MFA enforcement

**`/root/projects/juno/frontend/.env.production`:**
- `VITE_FIREBASE_MEASUREMENT_ID=G-4R0CDYKSPW` — Google Analytics for Firebase is not BAA-covered; must ensure no PHI reaches Analytics (URL parameters, page titles, event data)
- Uses `VITE_FIREBASE_AUTH_DOMAIN` pointing to Firebase Hosting domain

**`/root/projects/juno/frontend/src/pages/care-plan/CarePlanPage.tsx`:**
- `handleDownloadJson()` and `handleDownloadPdf()` at lines 329–351 download PHI to the client with no server-side audit event
- No session inactivity timeout
- Care plan content is rendered in the browser — if Firebase Analytics captures page content, PHI could be transmitted

### Infrastructure Gaps (GCS, Firestore, Cloud Run, IAM)

**GCS Bucket (`juno-medical-clarity-backend`):**
- Object versioning: unknown — likely not enabled. Enable for PHI buckets.
- Bucket-level access logging: not confirmed as enabled. Enable access logs.
- CMEK: using Google-managed keys. Evaluate CMEK for higher-assurance scenarios.
- Lifecycle policies for PHI deletion: not configured in code. Needed for the right-to-deletion and contract termination scenarios.

**Firestore:**
- Cloud Audit Logs (Data Access audit logs): Almost certainly not enabled by default. Must be explicitly enabled in GCP Console under IAM & Admin > Audit Logs. Without Data Access logs, there is no record of who read which Firestore document.
- No field-level encryption for particularly sensitive PHI fields

**Cloud Run:**
- `--allow-unauthenticated` flag is set in `deploy-backend.yml` — the service is publicly accessible and relies on application-level authentication (Firebase token verification). This is acceptable but means the API is exposed to the internet without network-level controls.
- No VPC configuration for restricting traffic between services
- No minimum TLS version explicitly enforced (Cloud Run's default is acceptable but should be documented)

**IAM:**
- Service account key files (`gcp-sa-key.json`, `juno-medical-clarity-firebase-adminsdk-fbsvc-91f08cee6f.json`) appear to be in the repository root. This is a critical security issue — service account keys should never be committed to version control. Keys should be stored in Secret Manager and injected at runtime. These keys should be immediately revoked and rotated.
- IAM roles for Cloud Run service accounts: not visible in the codebase — audit to ensure least-privilege
- GitHub Actions uses `secrets.GCP_SA_KEY` for deployment — verify this has minimum necessary permissions and is rotated periodically

**Logging Retention:**
- Cloud Logging default retention is 30 days. For HIPAA, audit logs must be retained 6 years. Logs must be exported to a GCS bucket with a 6-year lifecycle policy, or a Cloud Logging bucket must be configured with 2190-day retention.

### Vendor/BAA Gaps Summary

| Vendor | PHI Exposure | BAA Status | Action Required |
|---|---|---|---|
| Google Cloud (GCP) | HIGH — core infrastructure | NOT EXECUTED | Execute GCP BAA immediately |
| Firebase Authentication | HIGH — every auth request | NOT COVERED | Migrate to Identity Platform |
| Firebase Hosting | MEDIUM — frontend serving | NOT COVERED | Migrate or document as PHI-free |
| Firebase Analytics (`G-4R0CDYKSPW`) | MEDIUM — tracking | NOT COVERED | Remove or strictly isolate from PHI |
| Gemini API (AI Studio) | CRITICAL — PHI processed | NOT COVERED | Remove `GEMINI_API_KEY` from production |
| Vertex AI | HIGH — PHI processed | COVERED (after BAA) | Execute GCP BAA; confirm Vertex AI path |
| GitHub | LOW — source code only | BAA for Enterprise | Ensure no PHI in test fixtures or code |

---

## Prioritized Change List

| Priority | Change | Where | HIPAA Requirement | Effort |
|---|---|---|---|---|
| P0 — BLOCKING | Remove `GEMINI_API_KEY` from production deploy | `.github/workflows/deploy-backend.yml`, GH Secrets | BAA — Vertex AI only | 1 hour |
| P0 — BLOCKING | Execute Google Cloud HIPAA BAA | GCP Console | BAA required | 1 hour |
| P0 — BLOCKING | Revoke and rotate exposed service account keys | Repo root, GCP IAM | Security / physical safeguards | 2 hours |
| P1 — HIGH | Enable Cloud Audit Logs (Data Access) for Firestore and GCS | GCP Console | §164.312(b) Audit Controls | 30 min |
| P1 — HIGH | Configure Cloud Logging retention to 6 years | GCP Console or Terraform | §164.312(b) Audit Controls | 1 hour |
| P1 — HIGH | Add PHI access audit events to backend | `firebase.py`, `saved_outputs.py`, `care_plan.py` | §164.312(b) Audit Controls | 1–2 days |
| P1 — HIGH | Restrict CORS to known origins | `app.py` | Access Control | 1 hour |
| P2 — HIGH | Migrate Firebase Auth to Identity Platform | `firebase.py`, `firebase.ts`, `AuthContext.tsx` | BAA / §164.312(a) | 3–5 days |
| P2 — HIGH | Implement frontend session timeout (15–30 min inactivity) | `AuthContext.tsx`, frontend | §164.312(a)(2)(ii) | 1 day |
| P2 — HIGH | Enforce MFA for all clinician accounts | Identity Platform config | §164.312(d), Proposed 2026 Rule | 1 day |
| P2 — HIGH | Remove or isolate Firebase Analytics (`VITE_FIREBASE_MEASUREMENT_ID`) | `.env.production`, frontend | BAA — Analytics not covered | 2 hours |
| P2 — HIGH | Enable GCS object versioning on PHI buckets | GCP Console / Terraform | §164.312(c) Integrity | 30 min |
| P2 — HIGH | Add backend audit endpoint for PHI downloads | New endpoint + `CarePlanPage.tsx` | §164.312(b) Audit Controls | 1 day |
| P3 — MEDIUM | Designate a formal Security Officer | Administrative | §164.308(a)(2) | 1 hour (paperwork) |
| P3 — MEDIUM | Conduct formal HIPAA Risk Analysis (NIST SP 800-30) | Administrative | §164.308(a)(1) | 1–2 weeks |
| P3 — MEDIUM | Draft core HIPAA policies and procedures | Administrative | §164.308(a)(1) | 1–2 weeks |
| P3 — MEDIUM | Create workforce training program | Administrative | §164.308(a)(5) | 1 week |
| P3 — MEDIUM | Create Incident Response Plan and Breach Assessment procedure | Administrative | §164.308(a)(6), Breach Rule | 1 week |
| P3 — MEDIUM | Create BAA template for clinic customers | Legal | BAA required | 1 week (lawyer) |
| P3 — MEDIUM | Document Emergency Access procedures | Administrative | §164.312(a)(2)(i) | 1 day |
| P4 — LOWER | Evaluate CMEK for GCS PHI buckets | GCP Console | §164.312(a)(2)(iii) | 2 days |
| P4 — LOWER | Implement VPC / private networking for Cloud Run | GCP infrastructure | §164.312(e) | 3–5 days |
| P4 — LOWER | Migrate Firebase Hosting to Cloud Run or covered CDN | Infrastructure | BAA / Firebase not covered | 2–3 days |
| P4 — LOWER | Conduct penetration test | External vendor | Risk Management, Proposed 2026 Rule | 4–8 weeks + cost |
| P4 — LOWER | Third-party HIPAA assessment or audit | External auditor | §164.308(a)(8) Evaluation | 4–8 weeks + cost |
| P4 — LOWER | Implement GCS lifecycle policies for PHI deletion | GCP Console | Contingency Plan | 1 day |

---

## Compliance Timeline

### Phase 1 — 0–30 days: Blocking Items (BAAs, Critical Security Fixes)

These must be done before any PHI enters the system or before any clinic customer is onboarded.

- [ ] **Day 1:** Remove `GEMINI_API_KEY` from production GitHub Secret and `deploy-backend.yml`. Deploy with Vertex AI path only.
- [ ] **Day 1:** Revoke exposed service account key files in GCP. Remove `gcp-sa-key.json` and `juno-medical-clarity-firebase-adminsdk-fbsvc-91f08cee6f.json` from the repository. Rotate all affected credentials. Store credentials only in Secret Manager.
- [ ] **Day 1–2:** Execute Google Cloud HIPAA BAA via GCP Console.
- [ ] **Day 2–3:** Enable Cloud Audit Logs (Data Access) for Firestore and GCS in GCP Console.
- [ ] **Day 3–5:** Configure Cloud Logging retention to 2190 days (6 years), or set up log export to a GCS archive bucket.
- [ ] **Day 5–7:** Restrict CORS to known clinic frontend origins in `app.py`.
- [ ] **Day 7–14:** Remove or disable Firebase Analytics (`VITE_FIREBASE_MEASUREMENT_ID`). If analytics are needed, evaluate a BAA-covered alternative.
- [ ] **Day 7–21:** Engage a healthcare attorney to draft the clinic-facing BAA template.
- [ ] **Day 14–21:** Enable GCS object versioning on PHI-containing buckets.
- [ ] **Day 14–21:** Formally designate a Security Officer in writing.

### Phase 2 — 30–60 days: Authentication, Audit Logging, Administrative Program

- [ ] **Week 5–6:** Add PHI access audit events to all Firestore read/write operations in `firebase.py` and `saved_outputs.py`. Log: user_id, document_id, action, timestamp, source IP.
- [ ] **Week 5–6:** Add audit events for GCS file operations (upload, download, signed URL generation) in `care_plan.py` and `saved_outputs.py`.
- [ ] **Week 5–6:** Add backend endpoint for "PHI exported" events triggered by the frontend download actions.
- [ ] **Week 5–8:** Begin Firebase Auth → Identity Platform migration. This is a multi-step migration: set up Identity Platform, update `firebase.py` backend auth, update frontend auth SDK.
- [ ] **Week 6–7:** Implement frontend session inactivity timeout (15–30 minutes).
- [ ] **Week 6–8:** Conduct formal HIPAA Risk Analysis (NIST SP 800-30). Document all ePHI flows, threat sources, vulnerabilities, likelihood and impact ratings, and risk levels.
- [ ] **Week 6–8:** Draft core HIPAA policies: Information Security Policy, Access Control Policy, Incident Response Policy, Acceptable Use Policy, Sanction Policy.
- [ ] **Week 7–8:** Create HIPAA awareness training for all staff and contractors. Complete initial training session.

### Phase 3 — 60–90 days: MFA, Advanced Technical Controls, Operations

- [ ] **Week 9–10:** Enforce MFA for all clinician accounts (via Identity Platform after migration).
- [ ] **Week 9–10:** Create and test Incident Response Plan, including breach assessment workflow.
- [ ] **Week 9–12:** Evaluate and configure CMEK for GCS PHI buckets (optional but recommended).
- [ ] **Week 9–12:** Evaluate VPC configuration for Cloud Run services (restrict internal traffic).
- [ ] **Week 10–12:** Migrate Firebase Hosting to a BAA-covered alternative or document it as PHI-free with explicit controls.
- [ ] **Week 10–12:** Configure GCS lifecycle policies for PHI retention and deletion.
- [ ] **Week 12:** Internal HIPAA readiness review against the full §164.308/§164.310/§164.312 checklist.
- [ ] **Week 12:** First annual log review documentation.

### Phase 4 — 90–180 days: Third-Party Validation

- [ ] External penetration test (required under the proposed 2026 Security Rule; best practice now)
- [ ] Third-party HIPAA risk assessment or readiness audit
- [ ] HITRUST CSF certification (optional but strongly recommended for $50K+ ACV clinic sales — buyers increasingly require it)
- [ ] SOC 2 Type II audit (overlaps significantly with HIPAA administrative controls — evaluate combined approach)
- [ ] Execute BAA with first clinic customer

---

## What "HIPAA Compliant" Means in Practice

**There is no HIPAA certification.** The HHS OCR does not issue HIPAA compliance certificates. There is no official body that certifies software as "HIPAA compliant." Anyone claiming to offer HIPAA "certification" is selling a third-party assessment, not an official government certification.

**HIPAA compliance is an ongoing program, not a one-time event.** It requires continuous risk assessment, policy updates, workforce training, log review, and vendor management.

**What Juno CAN legitimately claim:**
- "We maintain a HIPAA compliance program" (after completing Phase 1–3 above)
- "We execute Business Associate Agreements with covered entities" (after completing BAA template)
- "Our infrastructure is hosted on Google Cloud's HIPAA-covered services" (after executing GCP BAA)
- "We have undergone a third-party HIPAA risk assessment" (after Phase 4)

**What Juno CANNOT claim:**
- "HIPAA certified" (no such thing)
- "HIPAA compliant" for services that use uncovered vendors (e.g., Firebase Auth before migration)

**The BAA does not make you compliant.** A signed BAA establishes the contractual relationship and shared liability. It does not validate that technical controls are implemented correctly. HIPAA compliance requires both the BAA and the full administrative and technical program.

**Covered Entities are responsible for their Business Associates.** If Juno mishandles PHI, the clinic (covered entity) can face penalties. This is why sophisticated health system buyers will conduct vendor security assessments of Juno before onboarding.

---

## Open Questions / Things to Verify with Legal

1. **Does the Google Cloud BAA cover Vertex AI's Gemini models explicitly?** The general Cloud BAA covers "Vertex AI Workbench instances" but the specific Gemini model inference API endpoint's coverage should be verified in the current BAA text before PHI flows through it.

2. **Firebase Authentication migration: does Identity Platform share the same user records?** Technically yes — Identity Platform and Firebase Auth share the same underlying identity store in most configurations, but the migration path should be confirmed with Google's documentation to avoid user disruption.

3. **Model training prohibition:** Confirm that the Google Cloud BAA (or a Vertex AI-specific data processing amendment) explicitly prohibits Google from using customer-submitted PHI to train or improve its AI models.

4. **GEMINI_API_KEY in production:** Verify whether `secrets.GEMINI_API_KEY` is currently set in the GitHub repository. If it is, assess whether PHI has already been transmitted through this path and whether that constitutes a reportable breach. Consult legal on this question before proceeding.

5. **Firebase Hosting as PHI surface:** Assess whether the frontend React app caches any PHI in localStorage, sessionStorage, or service worker caches. If so, Firebase Hosting as a distribution channel is a PHI surface requiring either migration or explicit controls.

6. **Patient-facing shareable links:** The product description mentions patients receiving shareable links for their care plans. The HIPAA analysis for these links (authentication requirements for patients, retention, what PHI they expose) was not fully analyzable from the current codebase and requires separate architectural analysis.

7. **State law:** Depending on which states Juno's clinic customers operate in, additional state health data laws may apply (e.g., California CMIA, Washington My Health MY Data Act). These often have stricter requirements than federal HIPAA and require separate analysis.

8. **Subcontractor chain:** If Juno uses any freelancers, contractors, or third-party developers who may access PHI, each needs either a BAA or to be covered under Juno's workforce policies.

9. **Retention vs. deletion:** The current code deletes GCS files when a care plan is deleted (`delete_saved()` in `saved_outputs.py`). However, HIPAA requires documentation to be retained for 6 years after creation or last effective date. Verify whether care plan outputs are "documentation" under HIPAA or clinical records that are governed by state medical records retention laws.

10. **HIPAA proposed rule finalization timeline:** The January 2025 NPRM is expected to finalize in mid-2026. Monitor the Federal Register for the final rule — Juno's compliance program should be updated to reflect the final requirements within the compliance period specified in the rule.

---

*Research conducted June 2026. Sources include Google Cloud compliance documentation, HHS OCR materials, and healthcare compliance guidance from Accountable HQ, HIPAA Journal, Strac, Paubox, and industry legal publications. All regulatory references are to 45 CFR Parts 160 and 164 as of the research date.*
