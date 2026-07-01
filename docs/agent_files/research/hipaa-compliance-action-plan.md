# HIPAA Compliance Action Plan — Juno

_Last updated: 2026-06-28_

---

## 1. Status Summary

### What Juno Does

Clinicians upload clinical notes → AI (Vertex AI/Gemini) generates plain-language care plans → clinicians share a link to the care plan with patients → patients view care plans. Both clinicians and patients interact with the system. PHI stored includes: clinical notes (PDFs in GCS), AI-generated care plans (Firestore + GCS), and any patient-identifiable content referenced in care plan text.

### What Is Done (Compliant Baseline)

| Control | Status | Notes |
|---------|--------|-------|
| Google Cloud BAA executed | DONE | Covers Cloud Run, Firestore, GCS, Cloud Tasks, Cloud Logging, Cloud Trace, Secret Manager, Vertex AI |
| HTTPS enforced everywhere | DONE | Cloud Run + Firebase Hosting |
| JWT token verification on every authenticated backend endpoint | DONE | `firebase_admin.auth.verify_id_token()` in backend |
| 30-minute session inactivity timeout | DONE | Frontend |
| User ownership enforcement | DONE | `get_owned_doc_or_403()` pattern throughout |
| All Firestore writes via backend API only | DONE | Client-side writes disabled in `firestore.rules` |
| Vertex AI path only in production | DONE | `GEMINI_API_KEY` not set in `deploy.yml` — AI Studio path cannot fire |
| Structured logging with Cloud Logging + OpenTelemetry | DONE | Session_id, HTTP method/path, status, duration |

### What Remains

Multiple critical gaps exist — most severely: unauthenticated PHI exposure via shared care plan links (anyone with the URL can read PHI), service account keys committed to the repo, no PHI-level audit logging, Cloud Audit Logs not enabled, and Firebase Authentication operating outside BAA coverage. These must be resolved before any real clinic customers or real PHI onboarding.

---

## 2. PHI Surface Map

### PHI Inventory

| PHI Type | Storage Location | Format | Who Can Access |
|----------|-----------------|--------|---------------|
| Clinical notes (uploaded by clinician) | GCS `care_plan/{user_id}/inputs/{uuid}.pdf` | PDF | Clinician (owner), backend service account |
| AI-generated care plan text | Firestore `care_plan_outputs/{doc_id}` | JSON/text | Clinician (owner), backend service account; unauthenticated public if `shared: true` |
| Care plan status/metadata | Firestore `care_plan_outputs/{doc_id}` | JSON | Same as above |
| AI-generated care plan PDFs | GCS (if export enabled) | PDF | Clinician via frontend download (server-blind export) |
| Patient-identifiable references in care plan text | Firestore `care_plan_outputs/{doc_id}` | Embedded text | Same as care plan above |
| Future: patient account data | Firestore (not yet built) | JSON | Patient + clinician (as applicable) |
| Future: chat messages | Firestore (not yet built) | JSON | Clinician + patient |

### Data Flow

```
1. Clinician uploads PDF (clinical note)
        ↓
   PATCH /care_plan/upload → GCS (PHI enters system)
        ↓
2. Backend submits job → Cloud Tasks → Cloud Run worker
        ↓
   Vertex AI processes clinical note → generates care plan text
        ↓
3. Care plan stored → Firestore care_plan_outputs/{doc_id}
        ↓
4. Clinician views/saves care plan (authenticated, JWT-verified)
        ↓
5. Clinician calls PATCH /care_plan/saved/<doc_id>/share
   → Firestore sets shared: true
        ↓
6. Clinician shares URL /carePlan/<doc_id> out-of-band (email, SMS, etc.)
        ↓
7. Patient visits URL → frontend detects no auth + care plan URL
   → sets isPublicView = true
   → reads Firestore doc directly via client-side SDK (onSnapshot)
   ← Firestore rule: allow get if resource.data.shared == true
   [*** NO AUTHENTICATION REQUIRED — CRITICAL GAP ***]
```

### Who Accesses PHI

| Actor | Access Method | Authentication | Audit Trail |
|-------|--------------|---------------|-------------|
| Clinician | Authenticated frontend + backend API | JWT (Firebase Auth) | Partial — HTTP access logged, not doc-level |
| Patient (current) | Unauthenticated Firestore client-side read | None | None — server never sees the read |
| Patient (future) | Authenticated patient account | Not yet built | Not yet built |
| Backend service | GCS + Firestore SDK | Service account | Cloud Audit Logs (not yet enabled) |
| Admin (Juno team) | `GET /admin/stats` endpoint | JWT (admin claim) | Partial |

---

## 3. Deferred Items

These items are intentionally deferred for the test-app phase. Do not act on them now; revisit before real PHI onboarding with real clinic customers.

| Item | Reason Deferred | Revisit Trigger |
|------|----------------|----------------|
| **Firebase Analytics removal** (`VITE_FIREBASE_MEASUREMENT_ID=G-4R0CDYKSPW`) | Needed for test-phase usage understanding. Firebase Analytics is not BAA-covered. | Before first real clinic customer onboards |
| **MFA enforcement** | Deferred until Firebase Auth → Identity Platform migration is complete and stable. | After Identity Platform migration (P0-4) is stable in production |
| **Athena Health BAA** | In progress separately. | Separate track |

---

## 4. Critical Gaps by Priority

### P0 — Blocking (fix before any real PHI / real clinic customers)

No PHI should enter the system from a real clinic until all P0 items are resolved.

| # | Gap | Severity | Where | Action |
|---|-----|----------|-------|--------|
| P0-1 | **Unauthenticated PHI exposure via share links** | CRITICAL | `firestore.rules`, `backend/routes/saved_outputs.py`, `frontend/src/pages/care-plan/CarePlanJobPage.tsx` | Require patient authentication before serving shared PHI. See Section 5 for full analysis and recommended approach. |
| P0-2 | **Service account keys committed to repo** | CRITICAL | Repo root: `gcp-sa-key.json`, `juno-medical-clarity-firebase-adminsdk-fbsvc-91f08cee6f.json` | Revoke both keys in GCP IAM immediately. Delete from repo. Add both filenames to `.gitignore`. Move all credentials to Secret Manager only. |
| P0-3 | **Cloud Audit Logs (Data Access) not enabled** | HIGH | GCP Console → IAM & Admin → Audit Logs | Enable DATA_READ, DATA_WRITE, and ADMIN_READ for Firestore and GCS. Without this, zero GCP-level record of PHI access exists outside the app. |
| P0-4 | **Firebase Authentication not BAA-covered** | HIGH | `frontend/src/auth/AuthContext.tsx`, `frontend/src/api/firebase.ts`, `backend/utils/firebase.py` | Migrate to Google Cloud Identity Platform (BAA-covered, largely API-compatible). All auth for PHI-accessing users must flow through a covered provider. |

---

### P1 — High (implement in `hipaa-int` sprint)

Required for a defensible HIPAA posture. No dependency on P0 for most items — can be parallelized.

| # | Gap | Where | Action |
|---|-----|-------|--------|
| P1-1 | **Cloud Logging retention at 30-day default** | GCP Console → Cloud Logging → Log Buckets | Set retention to 2190 days (6 years). HIPAA requires 6-year audit log retention. |
| P1-2 | **No PHI access audit events at Firestore document level** | `backend/utils/firebase.py`, `backend/routes/saved_outputs.py` | Add structured log events for every Firestore read/write/delete on `care_plan_outputs`. Log: `user_id`, `doc_id`, `action`, `timestamp`, `trace_id`. HTTP-level logging is insufficient — application-level PHI context is required. |
| P1-3 | **No PHI audit events for GCS operations** | `backend/routes/care_plan.py`, `backend/routes/saved_outputs.py` | Add audit events for all GCS uploads, downloads, and signed URL generation. Log: `user_id`, `gcs_path`, `action`, `timestamp`. |
| P1-4 | **No server-side record of care plan downloads/exports** | Frontend download handler, `backend/routes/` | Add a lightweight `/audit/download` backend endpoint. Frontend must call it on any care plan PDF download. Without this, PHI exports leave zero server-side trace. |
| P1-5 | **Deletion leaves no audit trail** | `backend/routes/saved_outputs.py` → `delete_saved()` | Before deleting a `care_plan_outputs` document, log a PHI destruction event (`user_id`, `doc_id`, `timestamp`, `action=phi_delete`). HIPAA requires a record of PHI destruction. |
| P1-6 | **Admin stats endpoint exposes individual PHI** | `backend/routes/admin.py` → `GET /admin/stats` | Streams entire `care_plan_outputs` collection. Exposes all `user_id`s and `error_data` for recent 20 errors. Refactor to aggregate counts only; never return individual user records or error details containing PHI. |
| P1-7 | **CORS too broad** | `backend/app.py` | Production CORS allows `localhost:5173`, `localhost:3000`, and Firebase Hosting domains. Restrict to production domain only in the production deploy config. |
| P1-8 | **GCS object versioning not enabled** | GCP Console → Cloud Storage → PHI bucket | Enable versioning on the `care_plan/` bucket. Accidental deletion of PHI is currently permanent and unrecoverable. |

---

### P2 — Medium (vendor BAAs and architecture for planned features)

These items become relevant as new features are added. Begin design and BAA negotiations now so implementation isn't blocked.

| # | Item | Action |
|---|------|--------|
| P2-1 | **Twilio BAA** | Execute Twilio HIPAA BAA (requires HIPAA-eligible plan) before any SMS integration goes live. Design SMS bodies to contain zero PHI — generic notification + link only. No patient name, diagnosis, or care plan content in SMS body. |
| P2-2 | **SendGrid BAA** | Execute SendGrid HIPAA BAA before any patient email is sent. Email bodies must be PHI-free — generic notification + link only. All email events (sent, delivered, opened) must feed into audit logging. |
| P2-3 | **Patient account system design** | Design patient account system with explicit role differentiation: `clinician` vs `patient`. Patient accounts need: access to their own records, ability to request deletion, patient rights under HIPAA Privacy Rule (access, amendment, accounting of disclosures). Shared care plan auto-add must have audit trail. |
| P2-4 | **Chat feature architecture** | Design chat on Firestore (already BAA-covered). Avoid any third-party chat SDK (Twilio Conversations, Stream, Sendbird) unless their HIPAA BAA is vetted and executed. All chat messages are PHI; 6-year retention applies; deletion must be audited. Push/SMS/email notifications for chat must be PHI-free. |
| P2-5 | **Washington MHMDA compliance** | When Juno becomes patient-facing (patient accounts), explicit opt-in consent is required under Washington's My Health MY Data Act. Add consent flow before patient data collection begins. |
| P2-6 | **Patient consent for AI processing** | Add a disclosure to the care plan delivery flow that AI was used to generate the care plan. This is a best practice and may become regulatory requirement under emerging state AI laws. |
| P2-7 | **Clinician-patient role enforcement in Firestore rules** | Currently there is no role differentiation in auth tokens or Firestore rules. Patient accounts need scoped access: read their own care plans, no access to other patients' data, no access to raw clinical notes. |

---

### P3 — Administrative (can run in parallel with P1/P2 technical work)

These are administrative and policy requirements for a complete HIPAA program. No code changes required.

| # | Action | Notes |
|---|--------|-------|
| P3-1 | **Formally designate a Security Officer** | Required by HIPAA §164.308(a)(2). Must be a named individual with documented responsibilities. |
| P3-2 | **Conduct formal HIPAA Risk Analysis (NIST SP 800-30)** | Required by HIPAA §164.308(a)(1). Document threats, vulnerabilities, likelihood, impact, and mitigating controls. Use this document as input. |
| P3-3 | **Draft core HIPAA policies** | Required policies: Information Security, Access Control, Sanction, Acceptable Use, Device/Media Controls, Data Retention. |
| P3-4 | **Create Incident Response Plan + Breach Assessment procedure** | Include 60-day breach notification requirement to HHS and affected individuals. Required under HIPAA Breach Notification Rule (§164.400–414). |
| P3-5 | **Draft clinic-facing BAA template** | Juno acts as a Business Associate to clinic customers. BAA required before any clinic shares PHI with Juno. Requires healthcare attorney review — do not use a generic template. |
| P3-6 | **HIPAA security awareness training** | All staff and contractors with PHI access. Document completion. Required by HIPAA §164.308(a)(5). |
| P3-7 | **Emergency Access (break-glass) procedure** | Define how authorized personnel can access PHI during system outages while maintaining audit trail. Required by HIPAA §164.312(a)(2)(ii). |
| P3-8 | **GCS lifecycle policies for PHI retention and deletion** | Configure to meet BAA terms and applicable state law. Ensure PHI is not retained indefinitely beyond contractual obligations. |
| P3-9 | **Evaluate CMEK for GCS PHI buckets** | Not strictly required by HIPAA but often contractually demanded by enterprise healthcare customers. Assess before first enterprise clinic deal. |

---

### P4 — Future / Production Hardening

| # | Action | Notes |
|---|--------|-------|
| P4-1 | **MFA enforcement** | DEFERRED — implement after Identity Platform migration is stable. See Section 3. |
| P4-2 | **Firebase Analytics review** | DEFERRED — review when real PHI is onboarded. See Section 3. |
| P4-3 | **Firebase Hosting migration or formal documentation** | Firebase Hosting is not BAA-covered. Currently serves only static assets (no PHI), which is medium-risk. Either formally document the PHI-free boundary or migrate to Cloud Run static serving before enterprise customers require it. |
| P4-4 | **Annual penetration test** | Engage external firm for black-box API and auth surface pen test. Required by many enterprise customer security reviews. |
| P4-5 | **SOC 2 Type II readiness** | Begin gap analysis 12–18 months before target certification. Most clinic customers will require SOC 2. |
| P4-6 | **HITRUST i1 certification** | After SOC 2 Type II. Required by some health systems and payers. |
| P4-7 | **VPC / private networking for Cloud Run** | Move backend off the public internet; access only via load balancer or VPC connector. Defense-in-depth; may be required by enterprise customers. |
| P4-8 | **Annual audit log review process** | Document who reviews audit logs, how often, and what constitutes an anomaly requiring escalation. Required by HIPAA §164.308(a)(1)(ii)(D). |

---

## 5. Share Link Security Analysis

### Current Architecture

**Relevant code paths:**
- Share toggle: `PATCH /care_plan/saved/<doc_id>/share` in `backend/routes/saved_outputs.py`
- Firestore rule: `firestore.rules` — `allow get: if ... || resource.data.shared == true;`
- Frontend public view: `frontend/src/pages/care-plan/CarePlanJobPage.tsx` — detects no auth + care plan URL → sets `isPublicView = true` → reads Firestore via `onSnapshot` client-side

**The vulnerability:**

When `shared: true` is set on a Firestore document, the Firestore security rule permits ANY unauthenticated client to read the full document by document ID. The document contains all care plan PHI.

The URL `/carePlan/<doc_id>` uses a UUID as the document ID. While UUIDs are not easily guessable, this is not a security control — security-by-obscurity is not HIPAA-compliant.

### Full Gap Inventory

| Gap | Description | Risk |
|-----|-------------|------|
| No authentication to access shared PHI | Anyone with the URL reads the full care plan | CRITICAL |
| No link expiration | `shared: true` is permanent until clinician manually toggles off | HIGH |
| No audit log of shared link views | Unauthenticated Firestore reads are invisible to the backend | HIGH |
| No patient identity verification | Cannot distinguish intended patient from any other person | HIGH |
| No rate limiting on Firestore reads | Brute-force or enumeration of UUIDs is unchecked | MEDIUM |
| Future patient account auto-add | PHI will be tied to patient accounts via these same unauthenticated links | HIGH |

### Recommended Fix Options

**Option A: Require patient authentication via magic link / email OTP (RECOMMENDED)**

Flow:
1. Clinician shares link with patient (URL contains `doc_id`)
2. Patient visits URL → redirected to "Enter your email to view" screen
3. Juno sends magic link / OTP to patient email
4. Patient authenticates → receives scoped, time-limited JWT
5. Backend serves care plan content (or Firestore rule requires valid auth token)
6. Access is logged server-side with patient email + doc_id + timestamp

Why recommended:
- Verifies patient identity (at minimum, email ownership)
- Creates full audit trail of every share link view
- Directly supports the planned patient account feature — magic link auth can upgrade to a full account
- Eliminates the unauthenticated Firestore read entirely
- Google Cloud Identity Platform (the P0-4 migration target) supports email link sign-in natively

**Option B: Backend-served share token (time-limited, single-use)**

Flow:
1. Clinician calls share endpoint → backend generates a signed, time-limited token (e.g., JWT with 72-hour expiry)
2. Token is embedded in the share URL: `/carePlan/share?token=<signed_token>`
3. Frontend exchanges token via backend API → backend validates token, returns care plan content
4. Firestore rule for `shared: true` is removed entirely — no more unauthenticated Firestore reads
5. Token is single-use or has a view-count limit

Trade-off: Does not verify patient identity. Anyone who receives the URL can access it within the expiry window. Better than current state; weaker than Option A.

**Option C: Signed URL with email confirmation**

A hybrid: send a signed URL (with expiry) that also requires the patient to confirm their email address matches one the clinician specified when sharing. Moderate complexity, moderate security.

**Recommendation: Implement Option A.** It is the only option that:
- Creates a verifiable identity link between viewer and care plan
- Generates a complete audit trail
- Directly scaffolds the future patient account system
- Eliminates the unauthenticated Firestore read rule entirely

**Immediate mitigation while Option A is being built:** Remove the `shared == true` unauthenticated Firestore rule. Serve shared care plan content exclusively through a backend endpoint that validates a time-limited signed token. This closes the worst gap (unauthenticated reads) without requiring full magic link auth infrastructure on day one.

---

## 6. Planned Features — HIPAA Implications

### Twilio (SMS Notifications)

**Intended use:** Notify patients when a clinician shares a care plan with them.

| Requirement | Detail |
|-------------|--------|
| BAA required | Twilio offers HIPAA BAA on HIPAA-eligible plan. Must be executed before any patient SMS. |
| PHI in SMS body | PROHIBITED. SMS is not end-to-end encrypted. SMS body must contain zero PHI — generic message + link only. No patient name, diagnosis, care plan summary, or clinician name if it implies a condition. |
| Safe SMS template | "You have a new care plan to review. Click here: [link]" |
| Audit logging | All SMS send events must be logged (patient identifier, message_id, timestamp, doc_id). |
| Delivery failures | SMS delivery failures must not expose PHI in error logs. |

### SendGrid (Email Notifications)

**Intended use:** Send care plan share link notifications to patients via email.

| Requirement | Detail |
|-------------|--------|
| BAA required | SendGrid (Twilio) offers HIPAA BAA. Execute before sending any patient-identifiable emails. |
| PHI in email body | PROHIBITED. Email is not end-to-end encrypted. Email body must contain zero PHI. Generic text + link only. |
| Safe email template | Subject: "You have a new care plan" — Body: "[Clinician name] has shared a care plan with you. Click here to view it: [link]" — Note: including the clinician's name is acceptable; do NOT include the patient's diagnosis or any clinical content. |
| Audit logging | All email send events logged (patient identifier, message_id, timestamp, doc_id). Track deliveries/opens only if logging is auditable. |
| From address | Use a consistent, app-controlled sender (not the clinician's personal email). |

### Patient Accounts

**Intended use:** Patients create accounts to store and access their received care plans.

| Requirement | Detail |
|-------------|--------|
| Role differentiation | Add explicit `clinician` vs `patient` role to auth tokens and Firestore rules. Patient role must be scoped: read only their own care plans, no access to raw clinical notes, no access to other patients' data. |
| Shared care plan auto-add | When a patient with an account views a shared care plan link, PHI is added to their account. This event must be audited: `patient_id`, `doc_id`, `clinician_id`, `timestamp`, `action=care_plan_received`. |
| HIPAA Privacy Rule — patient rights | Patients have the right to: access their records, request amendment, receive an accounting of disclosures. Build patient-facing UI for record access and deletion request. |
| Washington MHMDA | Explicit opt-in consent required before collecting patient health data. Add a consent screen before account creation that discloses what data is collected, how it's used, and who it's shared with. |
| Consent for AI processing | Disclose to patients that their care plans were generated using AI. Include in the care plan view and/or account creation consent flow. |
| Account deletion | Patient must be able to request full account + data deletion. Backend must implement and audit the deletion. Retention obligations (BAA terms, state law) may require a delay or partial retention — document the policy. |

### Chat Feature (Planned)

**Intended use:** Real-time messaging between clinician and patient on care plan material.

| Requirement | Detail |
|-------------|--------|
| Storage | Use Firestore (already BAA-covered). Avoid third-party chat SDKs unless their HIPAA BAA is vetted and executed. |
| PHI audit logging | All chat messages are PHI. Log: `sender_id`, `recipient_id`, `doc_id`, `message_id`, `timestamp`, `action`. |
| Message retention | Chat messages are PHI — 6-year retention applies under HIPAA. Do not implement auto-delete without a documented retention policy. |
| Message deletion | Deletion of chat messages must be audited (`action=phi_delete`). |
| Notifications | Chat notification via push/SMS/email must contain zero PHI in notification body (same rules as SMS/email above). |
| Real-time delivery | Firestore `onSnapshot` for real-time delivery is fine (already BAA-covered). If a third-party delivery layer is added, it needs its own BAA vetting. |
| FDA clinical decision support | If the chat feature allows the AI to respond to patient questions about their care plan, evaluate whether this crosses into regulated clinical decision support. Consult legal before building AI responses into chat. |

### GitHub (CI/CD)

| Requirement | Detail |
|-------------|--------|
| PHI in repo | Never. No test fixtures with real PHI. No care plan samples derived from real patients. |
| Service account keys | P0-2 gap. Keys are currently committed to repo root — must be revoked and removed immediately. |
| GitHub Actions logs | Ensure no PHI is echoed into CI logs (e.g., environment variables, API responses in test output). |
| GitHub BAA | GitHub Enterprise offers a BAA. Evaluate if any PHI could ever transit GitHub (it should not). PHI in repo = compliance violation regardless of BAA. |
| Secret Manager | All production secrets via GCP Secret Manager. GitHub Actions should pull secrets from Secret Manager at deploy time, not store them as GitHub secrets where possible. |

---

## 7. Vendor BAA Tracker

| Vendor | How Used | BAA Available | BAA Status | Action Required |
|--------|----------|--------------|------------|----------------|
| Google Cloud (GCP) | Core infra: Cloud Run, Firestore, GCS, Cloud Tasks, Cloud Logging, Cloud Trace, Secret Manager, Vertex AI | YES | **EXECUTED** | Confirm Vertex AI clause explicitly prohibits model training on Juno PHI |
| Firebase Authentication | User auth (clinicians + future patients) | **NO** — not BAA-covered | Active — MUST MIGRATE | P0-4: Migrate to Identity Platform before PHI onboarding |
| Firebase Hosting | Frontend SPA delivery | **NO** — not BAA-covered | Active | Treat as PHI-free layer; document the PHI-free boundary; or migrate to Cloud Run static serving |
| Firebase Analytics | Usage analytics | **NO** — not BAA-covered | Configured — DEFERRED | Deferred: review before first real clinic customer |
| Google Cloud Identity Platform | Replacement for Firebase Auth | **YES** (covered under GCP BAA) | Not yet deployed | Execute migration (P0-4) |
| Twilio (SMS) | Patient share notifications | **YES** (HIPAA-eligible plan required) | Not yet integrated | Execute BAA before any patient SMS; ensure PHI-free message bodies |
| SendGrid (email) | Patient share link notifications | **YES** (via Twilio) | Not yet integrated | Execute BAA before sending any patient emails; ensure PHI-free email bodies |
| GitHub | Source code, CI/CD | YES (Enterprise only) | Source code only — no PHI | Ensure no PHI in repo; rotate exposed service account keys now (P0-2) |
| Gemini API via AI Studio (direct API key) | AI model inference (non-Vertex path) | **NO** | **NOT in production** (confirmed `deploy.yml` — no `GEMINI_API_KEY`) | Keep removed; Vertex AI only in production |
| Vertex AI (via GCP) | AI model inference | **YES** (covered under GCP BAA) | Active | Confirm no-training clause in executed BAA |
| Future chat SDK (if not Firestore) | Real-time chat (planned) | Varies by vendor | Not yet decided | Prefer Firestore (already covered); vet any third-party SDK before use |

---

## 8. Open Questions

These require legal or external input before implementation decisions can be finalized.

1. **Vertex AI training clause.** Does the executed Google Cloud BAA explicitly prohibit Vertex AI from using Juno PHI for model training or improvement? If this clause is absent or ambiguous, it must be negotiated or clarified before any real clinical notes are processed.

2. **Is the current unauthenticated share link a reportable breach for test data?** If any test data entered the system and was accessible via the unauthenticated Firestore share link (`shared: true`), this may meet the definition of a breach under 45 CFR §164.402 depending on whether the test data is considered PHI. A formal breach risk assessment should be completed before PHI onboarding.

3. **Washington MHMDA applicability.** When patients directly interact with Juno's patient portal (future), is Juno a regulated entity under Washington's My Health MY Data Act? The MHMDA applies broadly to consumer health data — it likely applies when patients create accounts. Requires legal review.

4. **California CMIA applicability.** California's Confidentiality of Medical Information Act may impose additional obligations as Juno becomes patient-facing. Particularly relevant if any early clinic customers or patients are California-based.

5. **FDA intended use — clinical decision support.** Does the planned chat feature (especially if the AI can respond to patient questions about their care plan) cross into regulated clinical decision support software under 21 CFR Part 11 or FDA's CDS guidance? This must be evaluated before building AI responses into patient-facing chat.

6. **Patient consent for care plan auto-add.** When a patient with an account views a shared care plan link and the PHI is automatically added to their account, does this require prior explicit consent? The answer likely depends on whether the patient agreed to this in the account creation consent flow. Design the consent flow accordingly.

7. **SMS/email "From: Dr. X" notification and PHI disclosure.** Does including the clinician's name in a share notification (e.g., "Dr. Smith shared a care plan with you") constitute a PHI disclosure if it implies a treatment relationship? Generally this is low risk, but it depends on the sensitivity of the clinical context (mental health, substance abuse, reproductive health). Washington MHMDA and 42 CFR Part 2 have heightened protections for these categories — confirm with legal.

---

_This document covers technical and administrative action items. For detailed threat modeling, EHR integration compliance, and extended state law analysis, see `docs/agent_files/research/hipaa-compliance-juno.md` and `docs/agent_files/research/ehr-clinic-compliance-requirements.md`._
