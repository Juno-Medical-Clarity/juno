# Patient Share Link — Design & Implementation Analysis

**Date:** 2026-06-15  
**Project:** Juno (GCP: `juno-499419`, Firebase: `juno-medical-clarity`)  
**Stack:** React 19 + Firebase Hosting / Flask + Google Cloud Run / Firestore / GCS  
**Author:** Pre-implementation design analysis for founder decision

---

## Executive Summary

The patient share link feature is straightforward to implement correctly and easy to get wrong if the token design or data model shortcuts are taken. The right approach is: **UUID v4 tokens stored in a dedicated `share_links` Firestore collection, served by a single new unauthenticated Flask endpoint, displayed at a new `/share/:token` React route.** The whole feature is a medium-sized backend + frontend task — no third-party services, no infrastructure changes, no database migration of existing records.

Total implementation estimate: **2–3 days** for a fully functional, secure MVP.

---

## 1. Token Design Options

### Option A: UUID v4 (random, stored in Firestore)

A random 128-bit token (`uuid.uuid4()` → 32 hex chars, formatted as `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`) stored as a field in Firestore. The token itself encodes nothing — it is just a lookup key.

**Pros:**
- Trivially unguessable: 2^122 effective entropy (122 random bits in UUID v4). At 1 billion guesses per second, heat death of the universe arrives first.
- Revocable: delete or disable the Firestore document, token stops working instantly.
- No server secret to manage or rotate.
- Easy to audit: each token is its own database record.
- Standard Python: `import uuid; str(uuid.uuid4())`.
- Opaque to patients — they cannot infer anything about the report or the clinic.

**Cons:**
- Requires a Firestore read on every patient access (one indexed lookup — negligible cost, ~1ms).
- Slightly more storage than HMAC (a few hundred bytes per document).

**Verdict: This is the correct choice.**

---

### Option B: Signed JWT with `report_id` + `clinic_id` embedded

A JWT signed with a server-side secret (`HS256`), containing `{doc_id, uid, exp}`. The backend verifies the signature without a database read.

**Pros:**
- No database read required for validation (stateless).
- Can encode expiry natively in JWT `exp` claim.

**Cons:**
- **Not revocable.** A JWT signed with a 30-day expiry stays valid for 30 days even after a clinic deletes the report or asks you to revoke it. The only "revocation" strategy requires a blocklist (which requires a database read anyway, defeating the stated advantage).
- Requires managing a `JWT_SECRET` env var. Secret rotation = all issued tokens immediately invalid.
- `doc_id` is embedded in the token — anyone who decodes the base64 can see the Firestore document ID. This leaks internal structure.
- Adds `PyJWT` or `python-jose` to requirements. Not worth the dependency for this use case.
- JWT is designed for authentication (who you are), not authorization (what you can access). Using it as a share token is semantically wrong.

**Verdict: Do not use.**

---

### Option C: HMAC-SHA256 hash of `doc_id + secret`

`token = HMAC-SHA256(secret_key, doc_id)` — deterministic, no storage needed. Given a `doc_id`, you can always recompute the same token.

**Pros:**
- No database read or storage needed.
- Deterministic: token for a given report never changes.

**Cons:**
- **Not revocable without revoking all tokens** (you'd have to rotate the secret, which breaks every existing share link for every clinic).
- Token is deterministically tied to `doc_id` — if an attacker knows any one `(doc_id, token)` pair, they can verify guesses for other doc_ids if doc_ids have low entropy (Firestore auto-IDs have ~160 bits, so this attack is infeasible in practice, but the design is still wrong).
- Cannot support multiple different share links per report (e.g., if you later want per-patient tokens or per-referral tokens).
- Requires a `SHARE_SECRET` env var. If it leaks, every share link in history is derivable.
- Determinism means you cannot distinguish "link was never created" from "link exists" — every report implicitly has a derivable token, which is conceptually messy.

**Verdict: Do not use.**

---

### Recommendation: UUID v4

UUID v4 is the industry-standard approach for this exact use case. Every major healthcare platform that supports read-only sharing (Epic's MyChart share, Doximity, etc.) uses opaque random tokens backed by database records. The one Firestore read per patient page load is not a meaningful cost. The revocability, auditability, and simplicity are worth it.

---

## 2. Data Model

### Option A: Add `share_token` field to `simplify_outputs`

Add a nullable `share_token: string | null` field to each existing `simplify_outputs` document.

**Problems:**
- One token per report, forever. Cannot support: multiple recipients with separate tokens, per-token expiry, per-token revocation, per-token access logging.
- When a clinic wants to revoke a link, you set `share_token = null`. But now you've lost the history of whether the report was ever shared and when.
- You cannot add a second share link later (e.g., for a referral) without a schema migration.
- Complicates the `_get_doc_or_403` ownership check — the public endpoint would need to skip the `uid` check when looking up by token, but the existing private endpoints still need it.

### Option B: Dedicated `share_links` Firestore collection

A new top-level collection `share_links`, with one document per issued token. The document references the source report by `doc_id`.

**Why this wins:**
- Clean separation of concerns: auth-protected CRUD lives in `simplify_outputs`, public access is mediated entirely through `share_links`.
- Revocation: set `revoked: true` or delete the document. Zero impact on the source report.
- Audit trail: `created_at`, `last_accessed_at`, `access_count` all live cleanly on the share record without polluting the medical record.
- Future-proof: multiple links per report, per-link expiry, per-link recipient labels — all trivial to add later.
- The token lookup is a single document read by ID (if token = document ID), which is O(1) and does not require a composite index.

**Recommendation: Use Option B.**

---

### Proposed Firestore Schema

#### Collection: `share_links`

```
share_links/
  {token}/                         # token IS the document ID (UUID v4 without dashes)
    doc_id:          string        # Firestore ID of the simplify_outputs document
    uid:             string        # Firebase UID of the clinic user who created it
    created_at:      timestamp
    last_accessed_at: timestamp | null
    access_count:    number        # incremented on each patient access
    revoked:         boolean       # default false; set true to kill the link
    expires_at:      timestamp | null  # null = no expiry (MVP default)
    label:           string | null     # optional clinic-assigned label, e.g. "Patient copy"
```

**Token as document ID:** Using the token directly as the Firestore document ID means the lookup is a single `db.collection('share_links').document(token).get()` — no query needed, no index required, O(1) latency. This is the correct Firestore pattern for token-keyed lookups.

**What data is copied vs. referenced:** The `share_links` document does NOT copy `output_data`. It only stores the `doc_id`. The public endpoint fetches the source document and returns a controlled subset of its fields. This means if a clinic edits the report name, the patient always sees the current name.

---

## 3. Backend Changes Needed

### New Endpoint: `GET /share/<token>`

This is the only new endpoint needed. It is explicitly unauthenticated.

```python
# backend/routes/share.py

@share_bp.route('/share/<token>', methods=['GET'])
def get_shared_report(token: str):
    """
    Public endpoint — no Firebase auth required.
    Resolves a share token to its report data.
    """
    db = _db()

    # 1. Validate token format (UUID hex, 32 chars)
    if not re.match(r'^[0-9a-f]{32}$', token):
        return jsonify({'error': 'Invalid token'}), 404

    # 2. Look up share link
    link_ref = db.collection('share_links').document(token)
    link = link_ref.get()

    if not link.exists:
        return jsonify({'error': 'Not found'}), 404

    link_data = link.to_dict()

    if link_data.get('revoked', False):
        return jsonify({'error': 'This link has been revoked'}), 410

    if link_data.get('expires_at') and link_data['expires_at'] < datetime.now(timezone.utc):
        return jsonify({'error': 'This link has expired'}), 410

    # 3. Fetch the source report
    doc_ref = db.collection('simplify_outputs').document(link_data['doc_id'])
    doc = doc_ref.get()

    if not doc.exists:
        return jsonify({'error': 'Report no longer exists'}), 410

    data = doc.to_dict()

    # 4. Update access stats (fire-and-forget, non-blocking)
    link_ref.update({
        'last_accessed_at': datetime.now(timezone.utc),
        'access_count': firestore.Increment(1),
    })

    # 5. Return only structured output — not raw input PDF GCS path
    return jsonify({
        'name': data.get('name', 'Your Appointment Summary'),
        'output_data': data.get('output_data', {}),
        # Deliberately omit: uid, input_pdf_gcs, source_filename
    })
```

### New Endpoint: `POST /simplify/saved/<doc_id>/share`

Clinic-side endpoint to generate a share link. Requires auth (clinic user must own the report).

```python
@saved_outputs_bp.route('/simplify/saved/<doc_id>/share', methods=['POST'])
@verify_firebase_token
def create_share_link(user_id: str, doc_id: str):
    """Create a share token for a saved output. Returns the token."""
    db = _db()
    doc, err = _get_doc_or_403(db, doc_id, user_id)
    if err:
        return err

    token = uuid.uuid4().hex  # 32-char lowercase hex string

    db.collection('share_links').document(token).set({
        'doc_id': doc_id,
        'uid': user_id,
        'created_at': datetime.now(timezone.utc),
        'last_accessed_at': None,
        'access_count': 0,
        'revoked': False,
        'expires_at': None,
        'label': None,
    })

    return jsonify({'token': token})
```

### Existing Auth Model — No Changes Required

The `@verify_firebase_token` decorator stays on every existing endpoint. The new `/share/<token>` route simply does not use the decorator. There is no need to modify `auth.py`, the middleware, or any existing route.

**Important:** Register the share blueprint in `backend/routes/__init__.py` alongside the existing blueprints. The Flask `app.py` already loops over `all_blueprints` — just add the new blueprint to that list.

### Rate Limiting

Cloud Run does not provide built-in rate limiting. For MVP, the token's 2^128 entropy makes brute-force enumeration astronomically infeasible. For production hardening, options in order of increasing effort:

1. **Cloud Armor** (GCP WAF) — attach a rate limit rule to the Cloud Run backend. No code changes. Recommended if you ever go to production at scale.
2. **Flask-Limiter** with Redis or Memorystore — adds `pip install Flask-Limiter` and a rate store. Overkill for MVP.
3. **Token validation fast-fail** — the regex check on token format before any Firestore read means malformed requests are rejected at near-zero cost.

### What Data to Expose vs. Hide

The public endpoint intentionally omits:
- `uid` — never expose who the clinic user is.
- `input_pdf_gcs` — GCS paths reveal bucket structure and allow fishing for adjacent files.
- `source_filename` — may contain patient name if clinic named the file `smith_john_visit.pdf`.
- `created_at` / `updated_at` — not needed for patient view.

The public endpoint returns:
- `name` — the human-readable report name the clinic assigned.
- `output_data` — the structured `AppointmentNote` object (what `AppointmentNoteV12View` renders).

### Firestore Security Rules

Current assumption: Firestore security rules are permissive (or non-existent) because all access is gated by the Flask backend with Firebase Admin SDK. **Do not expose Firestore directly to the frontend** — continue routing all reads through the Flask backend. No Firestore security rule changes are needed for this feature.

If you later add client-side Firestore reads (e.g., for real-time updates), you would add:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Only backend (Admin SDK) can read/write share_links
    match /share_links/{token} {
      allow read, write: if false;
    }
    // Existing rule — clinic users own their outputs
    match /simplify_outputs/{docId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.uid;
    }
  }
}
```

---

## 4. Frontend Changes Needed

### New Route: `/share/:token`

Add a new top-level route in `App.tsx` that is rendered **outside** the auth gate. This is the most important architectural change: the current `App.tsx` redirects all unauthenticated users to `LoginPage` before rendering any route. The share page must be rendered before that check.

**Current `App.tsx` structure:**
```tsx
if (!user) {
  return <LoginPage />;  // ← This blocks all unauthenticated access
}
return <Routes>...</Routes>;
```

**Required change:** Wrap the existing auth-gated routes in a conditional, and render the share route unconditionally. The cleanest approach is to restructure `App.tsx`:

```tsx
// App.tsx — proposed structure
export default function App() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      {/* Public route — no auth required */}
      <Route path="/share/:token" element={<SharePage />} />

      {/* All other routes — auth gated */}
      <Route path="/*" element={<AuthenticatedApp user={user} loading={loading} />} />
    </Routes>
  );
}
```

`AuthenticatedApp` contains the existing loading spinner + login redirect logic.

### New Component: `SharePage`

Location: `/root/projects/juno/frontend/src/pages/SharePage.tsx`

Behavior:
- On mount, read `:token` from URL params (`useParams`)
- Fetch `GET /share/<token>` (no auth header needed — plain `fetch()`, not `authenticatedFetch()`)
- While loading: show a minimal loading state
- On success: render `AppointmentNoteV12View` with the returned `output_data`
- On error: show an appropriate error state (see UX section)

```tsx
// Rough structure — not final implementation
export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<'loading' | 'success' | 'error'>('loading');
  const [report, setReport] = useState<AppointmentNote | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!token) { setState('error'); setErrorMsg('Invalid link.'); return; }
    fetch(`${API_URL}/share/${token}`)
      .then(res => {
        if (res.status === 410) throw new Error('revoked');
        if (!res.ok) throw new Error('not_found');
        return res.json();
      })
      .then(data => {
        setReport(data.output_data as AppointmentNote);
        setState('success');
      })
      .catch(err => {
        setErrorMsg(err.message === 'revoked' ? 'This link is no longer active.' : 'Report not found.');
        setState('error');
      });
  }, [token]);

  if (state === 'loading') return <ShareLoading />;
  if (state === 'error') return <ShareError message={errorMsg} />;
  return (
    <div className="share-page">
      <header className="share-header">
        <span className="share-brand">Juno</span>
        <span className="share-tagline">Your appointment summary</span>
      </header>
      <div className="container">
        <AppointmentNoteV12View result={report!} />
      </div>
      <footer className="share-footer">
        <p>Shared by your clinic via Juno. Questions? Contact your care team directly.</p>
      </footer>
    </div>
  );
}
```

**What the SharePage does NOT include:**
- No `Sidebar` component
- No sign-out button
- No download JSON button
- No "Show Original" split view (no GCS PDF access from public endpoint)
- No rename or delete controls
- No navigation to other reports

**What it MAY include (nice to have):**
- A "Download as PDF" button using the existing `buildPdfHtml` utility — this is safe because it only uses the already-fetched `output_data`, requires no additional API call, and is genuinely useful for patients.
- Clinic branding (name, logo) — requires storing clinic profile data, out of MVP scope.

### New API Client Function

Add to `/root/projects/juno/frontend/src/api/savedOutputs.ts`:

```typescript
// Public — no auth token
export async function getSharedReport(token: string): Promise<{ name: string; output_data: Record<string, unknown> }> {
  const res = await fetch(`${API_URL}/share/${token}`);
  if (res.status === 410) throw new Error('revoked');
  if (!res.ok) throw new Error('not_found');
  return res.json();
}
```

And a new clinic-side function to create the share link:

```typescript
// Authenticated
export async function createShareLink(docId: string): Promise<string> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved/${docId}/share`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to create share link: ${res.status}`);
  const json = await res.json();
  return json.token as string;
}
```

### Clinic UI: Generating and Copying the Link

The share button lives in the result view of `V1_2Page.tsx`, in the `result-header` section (where "Show Original" already lives). Proposed addition:

```tsx
{activeSavedId && (
  <ShareButton docId={activeSavedId} />
)}
```

`ShareButton` behavior:
1. First click: calls `createShareLink(docId)`, receives `token`, constructs full URL (`https://your-domain.com/share/${token}`), copies to clipboard, shows "Copied!" confirmation.
2. If a link was already created for this `doc_id` in the current session: just copy the already-generated link without a new API call.
3. Note: the MVP does not show "link already exists" across sessions. Each button click generates a fresh token. This is intentional — it allows clinics to issue multiple links if needed. Seeing existing links is a nice-to-have (would require a `GET /simplify/saved/<doc_id>/shares` list endpoint).

---

## 5. Security Analysis

### Token Guessing Entropy

UUID v4 has 122 random bits (`uuid4().hex` is 32 hex characters, but 6 bits are fixed by the UUID spec). For an attacker attempting to guess a valid token:

- Keyspace: 2^122 ≈ 5.3 × 10^36 possible tokens
- Assuming 1 million Firestore reads per second (practically impossible from one attacker, and Cloud Run would be rate-limited long before this)
- Expected time to find one valid token among N issued tokens: 2^122 / N seconds at 10^6 reads/sec
- Even with 1 million issued tokens: expected time ≈ 5.3 × 10^27 seconds

**Conclusion: Guessing is not a viable attack. The token provides adequate security on entropy grounds alone.**

### What If a Patient Shares Their Link?

This is **by design**. The feature spec explicitly states: "If they share the link with someone else, that person can also see that same report — but cannot access any other report."

This is acceptable and correct behavior. Healthcare analogies: a printed after-visit summary, a patient portal PDF, a discharge summary faxed to a specialist — all can be shared by the patient. The clinic chose to send a shareable link; the implied consent is that the patient may share it.

**Do not add friction here** (e.g., requiring the patient to authenticate, or using single-use tokens). These features would make the UX significantly worse and are inconsistent with the product design.

### What If a Clinic Wants to Revoke a Link?

With the `share_links` collection design, revocation is a single Firestore write:

```python
db.collection('share_links').document(token).update({'revoked': True})
```

For MVP: expose this as `DELETE /simplify/saved/<doc_id>/share/<token>` (authenticated). The patient will receive a 410 Gone response and see an error message.

For the clinic UI: a "Revoke link" button in a share link management panel. Scoping this as post-MVP is reasonable — very few clinics will need to revoke links in early stages.

### HIPAA Considerations

**The hard truth:** A no-auth, no-expiry URL containing medical information is not inherently HIPAA-compliant or non-compliant. HIPAA's "minimum necessary" standard applies to what data is disclosed, not the mechanism. The key factors are:

**Risk factors:**
- The URL could be shared or forwarded unintentionally.
- If a patient's device is accessed by a third party, the link in browser history reveals medical data.
- Search engines could theoretically index the URL if pasted into a public forum (though they will not crawl it proactively).

**Risk mitigations (in order of importance):**

1. **Add `X-Robots-Tag: noindex` response header** on `/share/<token>` responses. This prevents any search engine that happens upon the URL from indexing it. Zero implementation cost.

2. **Set `Cache-Control: no-store, private`** on the share endpoint response. Prevents intermediate proxies and CDNs from caching medical data.

3. **HTTPS only** — Firebase Hosting enforces HTTPS, Cloud Run enforces HTTPS. Already handled.

4. **Token entropy** — already discussed; brute-force is infeasible.

5. **Optional expiry** — see recommendation below. Even a 90-day default expiry meaningfully reduces the risk window.

6. **Do not expose the raw input PDF** from the share endpoint. The `output_data` is the structured simplified summary; the original clinical note (which may contain far more sensitive detail) should never be accessible via the share link.

7. **Audit trail** — `access_count` and `last_accessed_at` in `share_links` give you basic access logging. If needed, structured logging in the Flask endpoint gives you IP and timestamp per access.

**Practical HIPAA posture:** Many covered entities use similar patterns (emailed PDF links, patient portal share URLs, etc.). The key is that the clinic, as the covered entity, is making a judgment that sharing this document with the patient via this mechanism is appropriate. Your BAAs with Google Cloud already cover the data at rest and in transit. The share link mechanism itself is comparable to "email the patient a PDF" in terms of control model.

**Recommendation:** For MVP, the no-expiry no-auth model is acceptable. Add the `X-Robots-Tag` and `Cache-Control` headers on day one. Consider adding an optional 90-day default expiry in v1.1 of the feature.

### Recommendation on Optional Expiry

**Add expiry support in the data model from the start** (the `expires_at` field in `share_links`), but **default to no expiry for MVP.** This way:
- The backend already handles expired links with a 410 response.
- You can add an expiry UI later without any backend changes.
- Clinics can opt into expiry if they want it.
- Default no-expiry respects the patient's need to re-open the link over time (post-visit, before follow-up, etc.).

---

## 6. UX Flow

### Flow 1: Clinic Generates the Link

1. Clinic processes a note in Juno → reaches the result view.
2. In the result header (next to "Show Original"), clinic sees a **"Share with Patient"** button.
3. Clinic clicks the button.
4. Frontend calls `POST /simplify/saved/<doc_id>/share`.
5. Backend creates the `share_links` record, returns `token`.
6. Frontend constructs `https://app.juno.health/share/<token>`.
7. Link is automatically copied to clipboard.
8. Button label changes to **"Link copied!"** with a checkmark, reverts after 2 seconds.
9. Clinic pastes the link into their patient messaging system, SMS, EHR portal, or email.

**Notes:**
- The clinic does NOT need to fill out any form. One click, done.
- If the clinic clicks again (later session), a new token is generated. The old token remains valid. This is by design — the clinic may want to send a fresh link to a different number.
- The button should be present even when viewing a previously saved report from the sidebar (not just freshly processed results).

### Flow 2: Patient Receives and Opens the Link

1. Patient receives the link (via text, email, EHR portal, etc.).
2. Patient clicks the link on any device — phone, tablet, laptop.
3. Browser navigates to `https://app.juno.health/share/<token>`.
4. Page loads with a brief "Loading your summary..." spinner.
5. The patient sees their appointment summary rendered with `AppointmentNoteV12View`.
6. No login prompt, no app download, no account creation.

### Flow 3: What the Patient Sees

The share page is a clean, minimal view:
- **Header:** "Juno" brand mark + "Your Appointment Summary from [Clinic Name — post-MVP]"
- **Content:** Full `AppointmentNoteV12View` render — Summary, Diagnosis, Medications, Tests, Warning Signs, Glossary, etc.
- **Footer:** "Shared by your clinic via Juno. Questions? Contact your care team directly."
- **Optional:** "Save as PDF" button (uses existing `buildPdfHtml` utility, no extra API call).
- **No:** sidebar, sign-in prompts, nav to other reports, download JSON, admin controls.

The view is identical to what the clinic sees, minus the clinical/admin chrome.

### Flow 4: Error States

| Condition | HTTP Status | Patient Sees |
|-----------|-------------|--------------|
| Token does not exist (typo, fabricated) | 404 | "This link doesn't exist. Please check your link or contact your clinic." |
| Token has been revoked | 410 | "This link is no longer active. Please contact your clinic for a new one." |
| Token has expired (if expiry enabled) | 410 | "This link has expired. Please contact your clinic for a new one." |
| Report was deleted by clinic | 410 | "This report is no longer available. Please contact your clinic." |
| Backend is down | Network error | "Unable to load your summary. Please try again in a few minutes." |
| Malformed token in URL | 404 | "This link doesn't exist. Please check your link or contact your clinic." |

Error pages should be clean, minimal, non-technical. Include the clinic's contact information if it's stored (post-MVP). Never expose error details like "Firestore document not found" or stack traces.

---

## 7. Implementation Scope Estimate

### MVP (2–3 days)

**Backend (1 day):**
- New file `backend/routes/share.py` with `GET /share/<token>` endpoint (~60 lines)
- New `POST /simplify/saved/<doc_id>/share` endpoint in `saved_outputs.py` (~25 lines)
- Register blueprint in `backend/routes/__init__.py` (2 lines)
- Total: ~90 lines of new Python

**Frontend (1–1.5 days):**
- Restructure `App.tsx` to hoist public `/share/:token` route outside auth gate (~20 lines changed)
- New `pages/SharePage.tsx` component (~100 lines)
- Add `getSharedReport()` and `createShareLink()` to `api/savedOutputs.ts` (~20 lines)
- Add share button to `V1_2Page.tsx` result header (~30 lines)
- Basic CSS for share page (header, footer, minimal chrome) (~50 lines)

**Firestore (15 minutes):**
- No schema migration of existing data needed.
- New `share_links` collection is created automatically on first write.
- Optionally add a Firestore composite index on `(uid, created_at)` in `share_links` for the future "list all my share links" admin view. Not required for MVP.

### Nice-to-Have (post-MVP)

- **Link management panel:** Clinic can see all share links for a report, see access count, revoke individual links. Requires `GET /simplify/saved/<doc_id>/shares` endpoint.
- **Optional expiry UI:** Checkbox when generating link: "Expire after 30/90/180 days." Backend already handles `expires_at`.
- **Clinic branding on share page:** Clinic name, logo, contact info. Requires a separate clinic profile data model.
- **Copy vs. send:** Instead of just copying the link, offer "Send via SMS" (Twilio) or "Send via email" (SendGrid). Meaningful jump in complexity.
- **Patient accounts:** If/when patients get accounts, existing share links can transfer to patient account access. The `share_links.doc_id` foreign key makes this migration clean.
- **EHR integration:** When EHR auto-uploads data, auto-generate a share link for the patient record. The `POST /simplify/saved/<doc_id>/share` endpoint already supports this.

---

## 8. Recommendation

### Token: UUID v4

Use `uuid.uuid4().hex` (32-char lowercase hex). Store it as the Firestore document ID in `share_links`. Do not use JWT or HMAC.

### Storage Model: Dedicated `share_links` Collection

Do not add a `share_token` field to `simplify_outputs`. Use a separate collection. This is the right call even at small scale — the cost is minimal and the future optionality is significant.

### Security Posture

- No auth required on the patient-facing `GET /share/<token>` endpoint.
- Add `X-Robots-Tag: noindex` and `Cache-Control: no-store, private` headers to the share endpoint.
- Never expose `input_pdf_gcs`, `uid`, or `source_filename` from the share endpoint.
- Default to no-expiry for MVP, but build the `expires_at` field into the data model from day one.
- Rate limiting via Cloud Armor is a production-hardening step, not MVP-blocking.

### What to Build First

1. Backend: `share.py` route + the `create_share_link` endpoint in `saved_outputs.py`.
2. Frontend: Restructure `App.tsx` auth gate → `SharePage` component → share button in `V1_2Page`.
3. Test end-to-end: generate a link as a clinic user, open it in incognito (simulating a patient), verify no auth prompt, verify correct report renders.
4. Ship it. The feature is simple, the security model is sound, and clinics will get immediate value.

### What NOT to Do for MVP

- Do not build link management UI (list/revoke) — add when a clinic actually asks for it.
- Do not add expiry to the UI — the backend supports it, but defaulting to no-expiry is the right UX for patients.
- Do not add rate limiting beyond the token entropy — it is not a meaningful risk at early scale.
- Do not add any patient authentication requirement — this is the whole point of the feature.
- Do not copy `output_data` into the `share_links` document — always fetch from source so the patient sees current data.

---

## Appendix: File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/routes/share.py` | NEW | `GET /share/<token>` public endpoint |
| `backend/routes/saved_outputs.py` | MODIFY | Add `POST /simplify/saved/<doc_id>/share` |
| `backend/routes/__init__.py` | MODIFY | Register `share_bp` |
| `frontend/src/App.tsx` | MODIFY | Hoist `/share/:token` route outside auth gate |
| `frontend/src/pages/SharePage.tsx` | NEW | Patient-facing share page component |
| `frontend/src/api/savedOutputs.ts` | MODIFY | Add `getSharedReport()` and `createShareLink()` |
| `frontend/src/pages/v1_2/V1_2Page.tsx` | MODIFY | Add "Share with Patient" button in result header |

No changes required to: `auth.py`, `app.py`, `firebase.ts`, `AppointmentNoteV12View.tsx`, `AuthContext.tsx`, `Sidebar.tsx`, or any existing route handler.
