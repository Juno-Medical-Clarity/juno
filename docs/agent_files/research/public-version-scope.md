---

# Juno Public Version — Scope & Design Document

## Overview

Juno currently operates as an internal tool: clinicians upload clinical notes, an AI pipeline simplifies them into patient-friendly care plans, and clinicians review/download results. This document scopes the work to create a **public B2C version** that allows anyone (no login required) to upload their own medical documents and receive a simplified care plan — with an option to create an account and save permanently.

### Core Principles

1. **Public ⊂ Internal**: Every field shown to public users is also visible to internal/authenticated users. Internal models *extend* public models — never the reverse.
2. **Ephemeral by default**: Anonymous sessions expire after 24 hours. Users login to persist.
3. **Minimum Necessary (HIPAA)**: Public API responses never return raw text, input text, or processing artifacts. Stripped models only.
4. **B2C, no clinicians**: Users process their own records. No doctor-patient relationship. Different HIPAA posture than the internal tool.
5. **One codebase, two modes**: Not a separate fork. The same backend and frontend handle both modes with routing, auth, and serialization differences.

---

## Current State (What Exists Today)

### Data Models

```
CarePlanV1_2 (backend/models/care_plan_versions/v1_2.py)
  ├── doc_type, version, urgency
  ├── summary, reason_for_visit, diagnosis
  ├── medications, tests, procedures, other
  ├── follow_up, warning_signs, questions
  ├── low_priority, terms (glossary)
  ├── additional_info[]          ← INTERNAL (Athena API paths, source metadata)
  ├── note: str | None           ← CLINICIAN-ONLY (per HIPAA doc)
  └── raw: RawArtifacts | None   ← INTERNAL (original text, simplified_text, clarified_text)

Grading (backend/models/grading.py)
  └── entries: GradingEntry[]
      ├── SMOG
      ├── Flesch-Kincaid
      ├── Dale-Chall
      ├── PEMAT
      ├── SAM
      ├── CDC CCI
      └── combined  ← Only one visible in public version

CarePlanInternal (backend/models/envelope.py)  ← full envelope stored in Firestore
  ├── metrics: Metrics
  ├── input: Input               ← Contains pdf_gcs_url, raw text, doc IDs (PHI-adjacent)
  ├── grading: Grading
  └── care_plan: CarePlanV1_2
```

### Firestore
- Single collection: `care_plan_outputs`
- Auth: docs owned by Firebase UID
- Sharing: `shared: true` flag allows unauthenticated Firestore client reads (P0-1 HIPAA gap)
- No TTL/expiry mechanism exists

### Auth
- Firebase Authentication (email/password, Google OAuth)
- No anonymous auth implemented
- No guest/session flow
- Backend middleware: `@verify_firebase_token` on all non-health endpoints

### Frontend Routes
- `/` — Upload page (CarePlanPage); always accessible; NavBar/Sidebar hidden for unauthenticated
- `/carePlan/:id` — Result page; accessible if job is owned by user OR `shared: true`
- `/models`, `/docs`, `/admin` — Authenticated-only
- Unauthenticated users at non-share routes → see LoginPage

---

## Proposed Changes

### 1. Model Architecture — Public/Internal Split

The user proposed splitting models so public is the base class and internal extends it. Concrete naming convention: `CarePlanV1_2Public` / `CarePlanV1_2Internal`.

#### Backend Python Models

```
# NEW: backend/models/care_plan_versions/v1_2_public.py
class CarePlanV1_2Public(CarePlan):
    version: Literal["1.2"] = "1.2"
    urgency: Literal["normal", "caution", "concern", "urgent"] = "normal"
    summary: str = ""
    reason_for_visit: list[ReasonForVisit] = []
    diagnosis: Diagnosis = {}
    medications: list[Medication] = []
    tests: list[Test] = []
    procedures: list[Procedure] = []
    other: list[OtherInstruction] = []
    follow_up: list[FollowUp] = []
    warning_signs: list[WarningSign] = []
    questions: list[str] = []
    low_priority: list[str] = []
    terms: dict[str, GlossaryTerm] = {}
    # NOTE: No raw, no additional_info, no note

# RENAME + EXTEND: backend/models/care_plan_versions/v1_2.py
class CarePlanV1_2Internal(CarePlanV1_2Public):  # was CarePlanV1_2
    raw: RawArtifacts | None = None
    additional_info: list[str] = []
    note: str | None = None

# NEW: backend/models/grading.py — split Grading
class GradingPublic(JsonModel):
    combined: GradingEntry | None = None   # Only the combined score
    enabled: bool = True
    graded_at: str | None = None

class GradingInternal(JsonModel):   # current Grading → renamed
    entries: list[GradingEntry] = []
    enabled: bool = True
    graded_at: str | None = None

# NEW: backend/models/envelope.py
class CarePlanEnvelopePublic(JsonModel):
    metrics: Metrics           # timing data, version string — no PHI
    grading: GradingPublic     # combined score only
    care_plan: CarePlanV1_2Public
    # NOTE: No input field — strips all source doc references

class CarePlanEnvelopeInternal(JsonModel):  # rename current CarePlanInternal
    metrics: Metrics
    input: Input               # Full input (pdf_gcs_url, text, doc_id)
    grading: GradingInternal   # All 6 methods + combined
    care_plan: CarePlanV1_2Internal
```

#### TypeScript Frontend Types (frontend/src/types/)

Mirror the model split:
- `CarePlanPublic` interface — no `raw`, no `additional_info`, no `note`
- `CarePlanInternal` interface — extends public + adds internal fields
- `GradingPublic` — only combined entry
- `GradingInternal` — all entries
- `CarePlanEnvelopePublic` — public envelope (no `input` field)
- `CarePlanEnvelopeInternal` — current full envelope

**Important**: The data stored in Firestore does NOT change — it still uses the internal model. The split happens at the API response/serialization layer. The backend serializes to the correct model class based on who's requesting.

---

### 2. User Flows

#### Flow A: Anonymous User (New)

```
1. User visits / (landing page, no login required)
2. Frontend generates UUID session token on first visit → stored in localStorage
3. User uploads clinical document or pastes text
4. POST /public/jobs sends X-Session-Token header (no Firebase auth)
5. Job stored in separate collection: `public_care_plan_outputs`
   with session_token field and expires_at = created_at + 24h
6. User redirected to /report/{job_id}
7. Result page shows PUBLIC-filtered view:
   - No sidebar
   - Minimal nav (logo + Login/Sign Up button)
   - PDF download button only
   - Combined grading score only
   - "Show Original" available (signed URL in public response, single-panel)
   - "Login to save this report permanently" banner
8. Anonymous PDF download works (client-side, uses public data only)
9. At 24h: Firestore doc + GCS file auto-deleted
   - Visiting /report/{expired_id} → "This report has expired"
10. IF user clicks "Login to save":
    - Auth modal → user logs in or creates account (real Firebase auth)
    - Frontend calls POST /public/claim/{job_id} with Bearer token + X-Session-Token
    - Backend migrates job from public_care_plan_outputs → care_plan_outputs
    - Report is now permanent under their account
```

#### Flow B: Authenticated User (Existing, Minimal Changes)

```
1. User logs in → full internal experience
2. Upload → process → saved to care_plan_outputs
3. Full sidebar, grading details, note, share, grade button
4. All existing functionality unchanged
```

#### Flow C: Anonymous → Login Mid-Session

```
1. Anonymous user has viewed report at /report/{job_id}
2. Clicks "Login to save"
3. Auth modal appears
4. On successful auth (new or existing account):
   - Frontend calls POST /public/claim/{job_id}
     with Firebase Bearer token + X-Session-Token header
   - Backend validates both, migrates doc to care_plan_outputs under real UID
   - Returns { new_job_id }
5. Redirect to /carePlan/{new_job_id} (authenticated view)
```

---

### 3. Backend Changes

#### New: Public Firestore Collection

```
Collection: public_care_plan_outputs
Document fields:
  uid: string           # Anonymous Firebase UID (or session token hash)
  name: string          # Auto-generated (e.g., "Report - Jun 28")
  created_at: Timestamp
  expires_at: Timestamp # created_at + 24h  ← NEW
  status: "not_started" | "processing" | "completed" | "error"
  stage: int
  output_data: {        # Full internal envelope (for migration path)
    metrics, input, grading, care_plan  ← stored as full internal model
  }
  error_data: {...}
  is_anonymous: true    # Marker field
```

**Important**: Store the full internal model in Firestore (same as today) to support the "login to save" migration path. The public/internal split only applies at the API response layer, not storage.

#### New API Endpoints

```python
# Public (unauthenticated, or anonymous Firebase UID)
POST /public/jobs
  - Body: { text, version, grading_enabled }
  - Auth: Anonymous Firebase UID (Bearer token from signInAnonymously)
  - Creates doc in public_care_plan_outputs with expires_at
  - Returns: { job_id }

GET /public/jobs/{job_id}
  - Auth: None (validate by job_id + optional session token)  
  - Returns: { status, stage, error? }

GET /public/output/{job_id}
  - Auth: None (or anonymous UID check)
  - Returns: CarePlanEnvelopePublic (FILTERED — no raw, no input, combined grading only)

POST /public/claim/{job_id}
  - Auth: Authenticated Firebase UID (after login)
  - Migrates doc from public_care_plan_outputs → care_plan_outputs
  - Updates uid field
  - Returns: { new_job_id }
```

#### Modified API Endpoints

```python
# Existing authenticated endpoint — add public serialization for shared links
GET /care_plan/saved/{doc_id}
  - If request authenticated AND owner → return CarePlanEnvelopeInternal (unchanged)
  - If request unauthenticated AND doc.shared == true → return CarePlanEnvelopePublic
    (fixes P0-1 HIPAA gap: no longer returns raw text to unauthenticated shared-link viewers)
```

#### New: TTL Cleanup Mechanism

Option A (Recommended): **Firestore native TTL policy** — set `expires_at` as the TTL field on `public_care_plan_outputs`. Firestore auto-deletes docs after the expiry time. No cleanup job needed.

Option B: **Cloud Scheduler** — daily Cloud Run job that queries `expires_at < now()` and deletes.

**GCS cleanup**: Add lifecycle rule on GCS bucket targeting `public_care_plan/` path prefix:
```json
{ "action": "delete", "condition": { "age": 1 } }
```

#### Firestore Security Rules Update

```javascript
match /public_care_plan_outputs/{docId} {
  // Anonymous user can read their own doc (by UID)
  allow get: if request.auth != null && request.auth.uid == resource.data.uid
              && request.time < resource.data.expires_at;
  // No list access (prevent enumeration)
  allow list: if false;
  // All writes via backend only
  allow write: if false;
}

match /care_plan_outputs/{docId} {
  // UPDATED: Shared links return public data (but backend handles serialization now)
  allow get: if (request.auth != null && request.auth.uid == resource.data.uid)
              || resource.data.shared == true;
  // ... rest unchanged
}
```

---

### 4. Frontend Changes

#### New / Modified Routes

| Route | Auth State | Behavior |
|-------|-----------|----------|
| `/` | Any | If unauthenticated: show public upload form. If authenticated: show current CarePlanPage with sidebar. |
| `/report/:id` | None (anonymous) | NEW route. Shows public result view. No sidebar, minimal nav. |
| `/carePlan/:id` | Authenticated | Unchanged internal result view. |

#### NavBar Changes (frontend/src/components/NavBar.tsx)

Current NavBar shows: Logo | Models | Docs | Admin | [+] | SignOut

**Public/Anonymous NavBar**: Logo only + "Login / Sign Up" button (right side)
**Authenticated NavBar**: Unchanged (current behavior)
**Implementation**: Pass `isPublic` prop OR check `!user` in NavBar component.

#### CarePlanJobPage / Public Result Page (frontend/src/pages/)

Current `CarePlanJobPage.tsx` has `isPublicView = !user` logic. For the new public flow, consider a dedicated `PublicReportPage.tsx` at `/report/:id` that:

- Fetches from `GET /public/output/{job_id}` (not Firestore client-side)
- Shows `CarePlanView` (unchanged — already public-safe)
- Shows `OutputGradingCard` in **combined-only mode** (new prop: `publicMode={true}`)
- Shows PDF download button only (no JSON, no Grade, no Share)
- Shows "Show Original" only if `originalText` exists (single panel, no side-by-side)
- Shows "Login to save this report" banner (fixed bottom bar or card)
- NO sidebar
- 24h expiry banner: "This report expires in Xh Ym"

#### OutputGradingCard Changes (frontend/src/components/OutputGradingCard.tsx)

Add `publicMode?: boolean` prop:
- `publicMode=true`: Show only the `combined` GradingEntry (single score, no method breakdown)
- `publicMode=false` (default): Current behavior (all methods, expandable)

#### SplitView / Show Original

**Both authenticated and anonymous users** can use "Show Original." For anonymous users:
- Uploaded PDFs are stored in GCS at `gs://bucket/public_care_plan/{session_token}/inputs/` with a 24-hour lifecycle rule
- A signed URL (30-min expiry) is returned in the `GET /public/output/{job_id}` response
- Frontend renders the PDF the same as for authenticated users (iframe with signed URL)
- Text inputs: same single-panel text view as today

**Not side-by-side for anonymous users.** "Show Original" shows the original document alone, not split with the care plan. The care plan is shown separately on scroll.

#### New "Login to Save" Component

Fixed banner at bottom of PublicReportPage:
```
[Logo] This report expires in 18h 42m.  [Create Account to Save]  [Log In]
```
On "Log In" / "Create Account": show auth modal → on success → call `/public/claim/{job_id}` → redirect to `/carePlan/{new_id}`.

#### Session State for Anonymous Users

After anonymous job creation, store `{ job_id, expires_at }` in `localStorage` so the user can return to their report without re-processing. Clear on expiry or account linking.

---

### 5. Auth Changes

#### Firebase Anonymous Auth

Non-logged-in users are silently assigned an anonymous Firebase account the moment they land on the site. This is completely invisible — no signup form, no friction.

```typescript
// frontend/src/auth/AuthContext.tsx — on app load if no user
import { signInAnonymously } from 'firebase/auth';

if (!currentUser) {
  await signInAnonymously(auth);
  // Firebase stores anonymous credential in IndexedDB
  // Survives page refreshes; same UID returned on revisit
}
```

**How it works:**
1. User visits site → `signInAnonymously()` fires automatically
2. Firebase creates an anonymous account: `uid = "anon_abc123"` (persists in browser IndexedDB)
3. User submits care plan → job stored in `public_care_plan_outputs` under `uid = "anon_abc123"`
4. User can create **multiple care plans** — all under the same anonymous UID, all listed if they revisit
5. After 24h: Firestore TTL deletes expired docs; GCS lifecycle deletes input files
6. Anonymous UID persists until: user clears browser storage, or account is linked/deleted

#### "Login to Save" — New Account Path

When an anonymous user signs up for a new account:

```typescript
// Firebase upgrades the anonymous account to a permanent one
// The UID stays the same — no Firestore migration needed
import { linkWithCredential, EmailAuthProvider } from 'firebase/auth';

const credential = EmailAuthProvider.credential(email, password);
await linkWithCredential(auth.currentUser, credential);
// auth.currentUser.uid is unchanged
// All their Firestore docs under the anonymous UID are now permanently owned
```

Zero backend work needed — the UID doesn't change. Docs already belong to them.

After linking, migrate the docs from `public_care_plan_outputs` → `care_plan_outputs` so they become part of the full internal experience:

```python
# POST /public/claim/{job_id}
# Called after successful linkWithCredential (new account)
@verify_firebase_token
def claim_public_job(job_id):
    user_id = g.user_id  # same UID as the anonymous one, now permanent
    public_doc = db.collection('public_care_plan_outputs').document(job_id).get()
    # Validate uid matches
    if public_doc.get('uid') != user_id:
        return 403
    # Move to permanent collection
    new_ref = db.collection('care_plan_outputs').document()
    new_ref.set({**public_doc.to_dict(), 'expires_at': None, 'is_anonymous': False})
    public_doc.reference.delete()
    return {'new_job_id': new_ref.id}
```

#### "Login to Save" — Existing Account Path

When an anonymous user logs into an account they already have:

Firebase throws `auth/credential-already-in-use` on `linkWithCredential`. The anonymous UID cannot merge into the existing UID automatically. Handle on the frontend:

```typescript
try {
  await linkWithCredential(auth.currentUser, credential);
} catch (err) {
  if (err.code === 'auth/credential-already-in-use') {
    // Save the anonymous job_ids before signing out
    const pendingJobIds = getAnonymousJobIds(); // from localStorage
    
    // Sign in to their real account
    await signInWithCredential(auth, err.credential);
    
    // Claim each pending job under their real UID
    for (const jobId of pendingJobIds) {
      await claimPublicJob(jobId); // calls POST /public/claim/{job_id}
    }
  }
}
```

Backend `POST /public/claim/{job_id}` now needs to accept the old anonymous UID as a proof-of-ownership parameter, since the caller's UID is now different:

```python
# Request body: { anonymous_uid: "anon_abc123", job_id: "xyz" }
# Validates: public_doc.uid == anonymous_uid
# Moves doc to care_plan_outputs under the new real user_id (g.user_id)
```

Frontend stores anonymous `job_ids` in localStorage (just the IDs, not the content) so this claim can happen after the existing-account sign-in.

#### Why Not Session Token or "Test Account"

- **Session token**: Doesn't survive browser storage clears; doesn't allow multiple care plans across sessions cleanly; loses data if user uses different device
- **Shared test account**: Still needs a session token inside the account to distinguish users; security risk (all anonymous data under one UID); no clean upgrade path
- **Firebase Anonymous Auth**: Invisible to user, handles multiple care plans, new-account path is zero-migration, existing-account path is one claim call per job

#### Anonymous Auth Cleanup

Firebase retains anonymous accounts indefinitely unless explicitly deleted. Add cleanup:
- Firestore TTL on `public_care_plan_outputs` auto-deletes docs after 24h
- A Cloud Scheduler job (daily) deletes Firebase Auth anonymous accounts older than 48h via Admin SDK:
  ```python
  # backend/utils/cleanup.py
  # firebase_admin.auth.list_users() → filter anonymous + created_at < 48h ago
  # firebase_admin.auth.delete_users([uid, ...])
  ```

#### HIPAA Note on Anonymous Auth

Firebase Auth (including Anonymous Auth) is not yet BAA-covered — this is the existing deferred P0-4 gap that applies across the whole app, not new risk introduced by this feature. Acceptable for the test/B2C phase. Flag for review before onboarding real clinic customers.

---

### 6. HIPAA Considerations

#### Lower Risk Profile for B2C

The two-deployment architecture provides natural isolation: internal PHI (clinician data, research datasets) never touches the public deployment's infrastructure. The public Cloud Run service has no access to `care_plan_outputs`, `/admin` routes, or the internal GCS buckets.

- Users entering their own records are not "patients" in the HIPAA sense — HIPAA applies to covered entities (healthcare providers/insurers), not to individuals accessing their own data
- However: We're storing health information → should still minimize exposure

#### New HIPAA-Relevant Design Decisions

| Decision | HIPAA Impact | Recommendation |
|----------|-------------|----------------|
| Public API returns `CarePlanEnvelopePublic` (no raw text) | Reduces PHI exposure | Required |
| Anonymous jobs expire in 24h | Data minimization | Required |
| GCS lifecycle deletes anonymous uploads after 24h | Data minimization | Required |
| No audit trail for anonymous users | Gap | Acceptable for test phase |
| Session token for anonymous users (no Firebase Auth) | No Firebase BAA dependency for anonymous sessions | Session token approach (decision made) |
| `note` field: user-written in B2C context | Likely not PHI (user's own notes) | Expose in public model |

#### Fixes P0-1 HIPAA Gap (Shared Links)
The current P0-1 gap (unauthenticated Firestore reads for `shared=true` docs return full PHI including `raw` text) gets fixed as a side effect of this work: authenticated endpoint now returns `CarePlanEnvelopePublic` for shared/unauthenticated requests, stripping `raw`.

---

## Potential Roadblocks & Integration Difficulties

### 1. VersionedModel Registry Conflict
**Problem**: `VersionedModel.__init_subclass__` auto-registers subclasses by `version` string. Both `CarePlanV1_2Public` and `CarePlanV1_2Internal` would register as `version: "1.2"` — conflict.

**Solution**: The split should happen at the API layer, not the model registry. Keep `CarePlanV1_2` as the stored/registered model. Create `CarePlanV1_2Public` as a separate Pydantic model (not a `VersionedModel` subclass) used only for serialization. Use a `to_public()` method: `def to_public(self) -> CarePlanV1_2Public: ...`

### 2. Existing-Account Linking Conflict
**Problem**: When an anonymous user tries to log into an *existing* Firebase account, `linkWithCredential()` throws `auth/credential-already-in-use`. The anonymous UID cannot auto-merge into the existing UID. The user has already created care plans under the anonymous UID.

**Solution**: Frontend catches this error, saves the anonymous `job_ids` to localStorage, signs into the existing account, then calls `POST /public/claim/{job_id}` for each pending job. Backend validates using the anonymous UID passed in the request body alongside the real Firebase token.

**Edge case**: User has 5 anonymous care plans, logs into existing account — all 5 must be claimed. Frontend should batch these or show a "Saving your reports…" progress indicator.

### 3. Firestore Native TTL vs Collection Design
**Problem**: Firestore native TTL requires a specific field name configured at the collection group level in the Firebase console/CLI. It deletes asynchronously (within ~24h of the `expires_at` time — not guaranteed instant).

**Solution**: Use Firestore TTL for eventual cleanup + add server-side expiry check in the `GET /public/output/{job_id}` endpoint (return 410 Gone if `expires_at < now`).

### 4. GCS Input Files for Anonymous Users
**Problem**: Current `GET /care_plan/saved/{doc_id}/input-pdf-url` returns a 30-min signed URL for the input PDF, but it requires auth. Anonymous users who uploaded a PDF won't have access to it for "Show Original."

**Solution A**: Store anonymous uploads at `gs://bucket/public_care_plan/{session_id}/inputs/` — return a one-time 30-min signed URL in the public output response. Risk: signed URL could be shared.

**Solution B**: Don't support PDF "Show Original" for anonymous users. Show text-input originals only. Simplest.

**Recommendation**: Solution B for launch. Show Original for anonymous = text only.

### 5. `note` Field Reclassification
**Problem**: `note` in `CarePlanV1_2` is documented as "clinician-only" in the HIPAA doc. In the B2C context, the "note" would be written by the user about their own record — not a clinician note. Same field, different semantic.

**Solution**: Include `note` in `CarePlanV1_2Public`. Rename to `user_note` in the public model (clearer semantics). Or keep as `note` and just include it — the HIPAA restriction was about clinician notes on patient records, which doesn't apply in B2C self-service.

### 6. Pipeline Version Dispatch
**Problem**: The anonymous/public flow should use the same pipeline as the internal flow. No separate model needed in the pipeline itself — just at serialization time.

**Solution**: The pipeline stores `CarePlanV1_2Internal` (full model). The `GET /public/output/{job_id}` endpoint reads the full doc and calls `care_plan.to_public()` before returning.

### 7. Batch/Dataset Jobs
Anonymous users should NOT have access to batch processing or preset datasets — these are internal research tools. The public upload endpoint should only accept single-document text or file input.

---

## Decisions Made

| # | Question | Decision |
|---|---------|---------|
| 1 | NavBar for anonymous users? | Logo + "Sign Up" button only |
| 2 | Show Original for anonymous PDF uploads? | Yes — store in GCS 24h, return signed URL in public response |
| 3 | Anonymous auth mechanism? | Firebase Anonymous Auth — silent, invisible, handles multiple care plans, survives page refresh |
| 4 | Separate Firestore collection? | Yes — `public_care_plan_outputs` |
| 5 | Combined grading for anonymous? | Yes — show combined score only |
| 6 | Same or separate deployment? | **Separate** — two Cloud Run services (see Deployment Architecture) |
| 7 | Share links? | Deferred — design separately later |

## Open Questions (Remaining)

1. **`note` field in B2C**: In the public/B2C context there are no clinician notes — the user writes their own notes about their own records. Should the note field exist in the public UI at all? Or is it irrelevant for the initial public launch?

2. **Rate limiting on public endpoints**: Without auth, `/public/jobs` is open to abuse. Plan: API key header, IP-based rate limiting (Cloud Armor), or both?

3. **Frontend repo strategy**: Is the public frontend a separate Vite app in the same repo (e.g., `frontend-public/`) or the same `frontend/` app with env-var feature flags controlling what's visible?

---

## Suggested Sub-Projects

### SP-PUB-1: Model Layer Split (Backend)
- Create `CarePlanV1_2Public` (serialization model, not VersionedModel subclass)
- Add `to_public()` method to `CarePlanV1_2`
- Create `GradingPublic` (combined entry only)
- Create `CarePlanEnvelopePublic`
- Update `GET /care_plan/saved/{doc_id}` to return public envelope for unauthenticated shared-link requests (fixes P0-1 HIPAA gap)
- **Files**: `backend/models/care_plan_versions/v1_2.py`, `backend/models/grading.py`, `backend/models/envelope.py`, `backend/routes/saved_outputs.py`

### SP-PUB-2: Session Token & Claim Flow (Frontend + Backend)
- Generate UUID session token in frontend on first visit → localStorage
- Send `X-Session-Token` header on all `/public/*` requests
- Backend stores `session_token` on Firestore doc (no Firebase UID for anonymous)
- `POST /public/claim/{job_id}` endpoint (requires Bearer token + X-Session-Token)
- LocalStorage stores `{ job_id, expires_at }` for return visits
- **Files**: `frontend/src/auth/AuthContext.tsx`, `backend/routes/public.py` (new)

### SP-PUB-3: Public API Endpoints
- New route file: `backend/routes/public.py`
- `POST /public/jobs`, `GET /public/jobs/{id}`, `GET /public/output/{id}`
- Writes to `public_care_plan_outputs` collection with `expires_at`
- Response: `CarePlanEnvelopePublic`
- **Files**: `backend/routes/public.py`, `backend/app.py` (register blueprint)

### SP-PUB-4: 24-Hour TTL & Cleanup
- Configure Firestore native TTL on `public_care_plan_outputs.expires_at`
- Add GCS lifecycle rule for `public_care_plan/` prefix (1-day delete)
- Add server-side expiry check in `GET /public/output/{id}` (return 410 if expired)
- **Files**: Firestore console config, GCS lifecycle JSON, `backend/routes/public.py`

### SP-PUB-5: Frontend Public UI
- `PublicReportPage.tsx` at `/report/:id`
- Minimal NavBar for anonymous users
- `OutputGradingCard` combined-only mode (`publicMode` prop)
- "Login to save" banner/modal
- Expiry countdown display
- Show Original: single-panel text only
- **Files**: `frontend/src/pages/PublicReportPage.tsx`, `frontend/src/components/NavBar.tsx`, `frontend/src/components/OutputGradingCard.tsx`, `frontend/src/App.tsx`

### SP-PUB-6: Firestore Rules & Security
- Add `public_care_plan_outputs` rules with `expires_at` time-check
- Update `care_plan_outputs` shared-link rules (time-limited or token-based)
- **Files**: `firestore.rules`

---

## Deployment Architecture

Juno will have **two separate deployments**, sharing the same codebase (monorepo):

```
juno/ (monorepo)
├── backend/          ← Shared Python backend (same code, different config)
├── frontend/         ← Internal frontend (current)
├── frontend-public/  ← Public frontend (new, TBD: separate app or same with flags)
└── docs/
```

### Internal Deployment (Existing)
- **Who**: Tejit + invited researchers
- **Frontend**: Current React app — full features (Models, Docs, Admin, sidebar, all grading methods, share links)
- **Backend**: Current Cloud Run service — all endpoints including `/admin`, `/care_plan/batch`
- **Data**: `care_plan_outputs` Firestore collection
- **Auth**: Firebase Auth required for all routes
- **Changes from this work**: Minimal — add `to_public()` serialization method to models; update shared-link response to return public envelope (fixes P0-1 HIPAA gap)

### Public Deployment (New)
- **Who**: Everyone (B2C, self-service)
- **Frontend**: Stripped-down React app — no Models/Docs/Admin pages; NavBar = Logo + Sign Up; sidebar only for logged-in users; combined grading only; PDF download only; Show Original = single-panel
- **Backend**: New Cloud Run service — only exposes `/public/*` and `/health` endpoints; no `/admin`, no `/care_plan/batch`, no `/care_plan/saved/*` (auth users use different routes)
- **Data**: `public_care_plan_outputs` Firestore collection (TTL enabled); `gs://bucket/public_care_plan/` GCS path (24h lifecycle rule)
- **Auth**: Firebase Auth optional (login to save). No auth for browsing/uploading.

### Shared Code
- All pipeline logic (`backend/utils/pipeline/`, `backend/utils/llm/`, etc.)
- All model definitions (`backend/models/`) — public models are the base, internal extends them
- Firestore client utilities
- GCS utilities

### Model Sharing Strategy
Internal models extend public models. Both deployments import from the same `backend/models/`:

```
CarePlanV1_2Public   ← used by public deployment
    ↑ extends
CarePlanV1_2Internal ← used by internal deployment

GradingPublic        ← used by public deployment
GradingInternal      ← used by internal deployment (all 6 methods)

CarePlanEnvelopePublic   ← public API responses
CarePlanEnvelopeInternal ← internal API responses
```

This ensures: any field visible publicly is also in the internal model. Internal-only fields (raw, additional_info) never appear in public responses.

---

## File Impact Summary

| File | Change Type | Sub-Project |
|------|------------|-------------|
| `backend/models/care_plan_versions/v1_2.py` | Add `to_public()`, add internal fields | SP-PUB-1 |
| `backend/models/grading.py` | Add `GradingPublic`, rename `Grading → GradingInternal` | SP-PUB-1 |
| `backend/models/envelope.py` | Add `CarePlanEnvelopePublic`, rename internal | SP-PUB-1 |
| `backend/routes/saved_outputs.py` | Return public envelope for shared links | SP-PUB-1 |
| `backend/routes/public.py` | NEW — public endpoints | SP-PUB-3 |
| `backend/app.py` | Register public blueprint | SP-PUB-3 |
| `backend/utils/firebase.py` | Support anonymous UID (may need no change) | SP-PUB-2 |
| `firestore.rules` | Add public_care_plan_outputs rules | SP-PUB-6 |
| `frontend/src/App.tsx` | Add `/report/:id` route | SP-PUB-5 |
| `frontend/src/pages/PublicReportPage.tsx` | NEW — public result page | SP-PUB-5 |
| `frontend/src/components/NavBar.tsx` | Anonymous nav variant | SP-PUB-5 |
| `frontend/src/components/OutputGradingCard.tsx` | `publicMode` prop | SP-PUB-5 |
| `frontend/src/auth/AuthContext.tsx` | Anonymous auth + linking | SP-PUB-2 |
| `frontend/src/types/carePlan.ts` | Add public types | SP-PUB-1 |
| `frontend/src/types/envelope.ts` | Add public envelope type | SP-PUB-1 |
| `frontend/src/api/*.ts` | Public API calls | SP-PUB-3 |

---

## Non-Changes (Explicitly Out of Scope)

- Pipeline logic — no changes to how care plans are generated
- Existing authenticated user experience — all current features preserved
- Admin panel — unchanged
- Models/Docs pages — internal only, unchanged
- Batch/preset dataset processing — internal only
- MFA — still deferred (per HIPAA deferred items)
- Firebase Analytics — still deferred (per HIPAA deferred items)
- Firebase Auth → Identity Platform migration — still deferred (P0-4)

---

*Document generated from codebase audit — 2026-06-28. Key files explored: `backend/models/`, `backend/routes/`, `frontend/src/`, `firestore.rules`, `docs/hipaa-compliance-action-plan.md`.*

---

## Deployment Guide — Public Version

This section covers how to set up and deploy the public-facing Juno service. The internal deployment (existing) is unchanged.

### Infrastructure Overview

```
juno-medical-clarity (GCP Project)
├── Cloud Run: juno-api (existing — internal)          → internal.juno.app (or current URL)
├── Cloud Run: juno-public-api (NEW)                   → api.juno.app (public)
├── Firebase Hosting: juno-internal (existing)         → app.juno.app (internal frontend)
├── Firebase Hosting: juno-public (NEW)                → juno.app (public frontend)
├── Firestore: care_plan_outputs (existing)            → internal jobs
├── Firestore: public_care_plan_outputs (NEW)          → anonymous + public user jobs, TTL enabled
├── GCS: juno-backend bucket (existing)                → internal uploads: care_plan/{uid}/inputs/
└── GCS: juno-backend bucket (same)                    → public uploads: public_care_plan/{uid}/inputs/
```

### Step 1: Firestore — Create Public Collection & Enable TTL

1. The `public_care_plan_outputs` collection is created automatically when the first doc is written.
2. Enable Firestore TTL on the `expires_at` field:
   ```bash
   gcloud firestore fields ttls update expires_at \
     --collection-group=public_care_plan_outputs \
     --project=juno-medical-clarity \
     --enable-ttl
   ```
   Docs with `expires_at` in the past will be auto-deleted by Firestore (within ~24h of expiry, not guaranteed instant — add server-side expiry check in the API too).

3. Update `firestore.rules` to add rules for the new collection (SP-PUB-6).

### Step 2: GCS — Add Lifecycle Rule for Public Uploads

Add a lifecycle rule to delete files in the `public_care_plan/` path prefix after 1 day:

```bash
# Create lifecycle config file
cat > /tmp/public-lifecycle.json << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 1,
        "matchesPrefix": ["public_care_plan/"]
      }
    }
  ]
}
EOF

# Apply to existing bucket
gsutil lifecycle set /tmp/public-lifecycle.json gs://juno-backend
```

Verify: `gsutil lifecycle get gs://juno-backend`

### Step 3: Firebase — Enable Anonymous Auth

In the Firebase console for project `juno-medical-clarity`:
1. Go to **Authentication → Sign-in method**
2. Enable **Anonymous** provider
3. No additional configuration needed

Or via Firebase CLI:
```bash
# In firebase.json or via Identity Platform API
# Anonymous auth is enabled per-project, not per-app
```

### Step 4: Firebase Anonymous Account Cleanup (Cloud Scheduler)

Anonymous accounts accumulate in Firebase Auth. Set up a daily cleanup:

1. Create a Cloud Scheduler job that hits a new internal endpoint:
   ```
   POST /internal/cleanup/anonymous-accounts
   ```
   Schedule: `0 3 * * *` (3am daily)

2. Backend implementation (`backend/routes/internal.py`):
   ```python
   # Delete anonymous Firebase Auth accounts older than 48h
   # AND delete any remaining public_care_plan_outputs docs where expires_at < now
   # (belt-and-suspenders cleanup alongside Firestore TTL)
   ```

3. Protect the endpoint with a Cloud Scheduler OIDC token or a secret header — not the Firebase user token.

### Step 5: Deploy Public Backend (Cloud Run)

The public backend is the same Python codebase as internal, but deployed as a separate Cloud Run service with different environment variables and only the public routes registered.

**Option A (Recommended for launch)**: Same `app.py`, use an env var `DEPLOYMENT_MODE=public` to conditionally register only public blueprints:

```python
# backend/app.py
import os
mode = os.environ.get('DEPLOYMENT_MODE', 'internal')

app.register_blueprint(public_bp)   # always registered
app.register_blueprint(health_bp)   # always registered

if mode == 'internal':
    app.register_blueprint(care_plan_bp)
    app.register_blueprint(saved_outputs_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(batch_bp)
```

**Deploy:**
```bash
gcloud run deploy juno-public-api \
  --source ./backend \
  --region us-central1 \
  --project juno-medical-clarity \
  --set-env-vars DEPLOYMENT_MODE=public,GCP_PROJECT_ID=juno-medical-clarity,FIRESTORE_DATABASE_ID=(default) \
  --set-secrets FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 10 \
  --memory 512Mi
```

Note `--allow-unauthenticated`: Cloud Run allows unauthenticated requests (Firebase Anonymous Auth tokens are validated inside the app, not at the Cloud Run IAM layer).

### Step 6: Deploy Public Frontend (Firebase Hosting)

**Option A**: Separate Vite app in `frontend-public/` — cleanest separation, separate `package.json`, separate build config.

**Option B**: Same `frontend/` with env var `VITE_DEPLOYMENT_MODE=public` controlling which routes/components render.

Recommended: **Option B for launch** (less duplication), migrate to Option A when the public frontend diverges significantly.

```bash
# Build public frontend
cd frontend
VITE_DEPLOYMENT_MODE=public \
VITE_API_PROCESSING_URL=https://juno-public-api-[hash]-uc.a.run.app \
VITE_FIREBASE_PROJECT_ID=juno-medical-clarity \
npm run build -- --outDir dist-public

# Deploy to Firebase Hosting target "public"
firebase target:apply hosting public juno-public
firebase deploy --only hosting:public
```

In `firebase.json`, add a second hosting target:
```json
{
  "hosting": [
    {
      "target": "internal",
      "public": "frontend/dist",
      "rewrites": [{ "source": "**", "destination": "/index.html" }]
    },
    {
      "target": "public",
      "public": "frontend/dist-public",
      "rewrites": [{ "source": "**", "destination": "/index.html" }]
    }
  ]
}
```

### Step 7: CORS Configuration

The public backend must allow requests from the public frontend domain:

```python
# backend/utils/cors.py or app.py
PUBLIC_ORIGINS = [
    "https://juno.app",           # production public frontend
    "http://localhost:5174",       # local dev for public frontend
]

INTERNAL_ORIGINS = [
    "https://app.juno.app",       # production internal frontend  
    "http://localhost:5173",       # local dev for internal frontend
]

# In public Cloud Run: allow PUBLIC_ORIGINS only
# In internal Cloud Run: allow INTERNAL_ORIGINS only
```

### Step 8: CI/CD (GitHub Actions)

Add a second deploy workflow for the public service. Suggested file: `.github/workflows/deploy-public.yml`

```yaml
name: Deploy Public

on:
  push:
    branches: [main]   # or a separate 'public' branch

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: juno-public-api
          region: us-central1
          source: ./backend
          env_vars: |
            DEPLOYMENT_MODE=public
            GCP_PROJECT_ID=juno-medical-clarity
          secrets: |
            FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account:latest

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
        working-directory: frontend
        env:
          VITE_DEPLOYMENT_MODE: public
          VITE_API_PROCESSING_URL: ${{ secrets.PUBLIC_API_URL }}
          VITE_FIREBASE_API_KEY: ${{ secrets.FIREBASE_API_KEY }}
          # ... other VITE_ vars
      - uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          target: public
```

### Local Development — Public Mode

Run public frontend and backend simultaneously alongside the internal versions:

```bash
# Terminal 1: Internal backend (port 8080)
cd backend && DEPLOYMENT_MODE=internal flask run --port 8080

# Terminal 2: Public backend (port 8081)
cd backend && DEPLOYMENT_MODE=public flask run --port 8081

# Terminal 3: Internal frontend (port 5173)
cd frontend && VITE_DEPLOYMENT_MODE=internal npm run dev -- --port 5173

# Terminal 4: Public frontend (port 5174)
cd frontend && VITE_DEPLOYMENT_MODE=public VITE_API_PROCESSING_URL=http://localhost:8081 npm run dev -- --port 5174
```

### Deployment Checklist

Before going live with the public deployment:

- [ ] Firestore TTL enabled on `public_care_plan_outputs.expires_at`
- [ ] GCS lifecycle rule applied to `public_care_plan/` prefix (1-day delete)
- [ ] Firebase Anonymous Auth enabled in Firebase console
- [ ] Cloud Scheduler job created for daily anonymous account cleanup
- [ ] `juno-public-api` Cloud Run service deployed with `DEPLOYMENT_MODE=public`
- [ ] Public frontend deployed to Firebase Hosting target `public`
- [ ] CORS configured: public Cloud Run allows only public frontend origin
- [ ] `firestore.rules` updated with `public_care_plan_outputs` rules (SP-PUB-6)
- [ ] Smoke test: upload doc as anonymous → get report → PDF download → "Login to save" → report appears in authenticated sidebar
- [ ] Verify 24h expiry: check that Firestore TTL is configured correctly (test with a short expiry in staging)
- [ ] Verify GCS files are deleted after lifecycle rule triggers (check GCS bucket after 25h)
