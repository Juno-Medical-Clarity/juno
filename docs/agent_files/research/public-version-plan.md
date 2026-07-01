---

# Juno Public Version — Implementation Plan (v3)

_Date: 2026-07-01 (v3 revision)_
_Supersedes: `docs/agent_files/research/public-version-scope.md` (2026-06-28) on all points below. That document is left in place for historical context but should not be used for implementation — see "What Changed" for why._

---

## v3 — Review Findings Incorporated

This revision folds in findings from a five-lens expert review (architecture, HIPAA/compliance, PM, dev-feasibility, UX) conducted against the v2 plan and the actual codebase. Nothing in v2's core architecture was wrong at the shape level, but the review found several correctness bugs, one reintroduced P0 security hole, several understated/mis-scoped items, and a set of missing compliance and UX requirements. Summary of what changed, in brief (full detail is inline in the relevant sections below):

- **Correctness/architecture**: fixed a naming collision between the *new* `isPublicBuild` flag and the *existing* `isPublicView` (shared-link viewer) flag that this plan had conflated; closed an auth hole in `GET /public/output/{job_id}` that would have reintroduced the P0-1 unauthenticated-PHI-read gap; corrected the false claim that the job-lifecycle pipeline (`backend/utils/firebase.py`, `backend/routes/worker.py`) is "unchanged" — it hardcodes the internal collection name and needs threading; fixed a bug in `Grading.to_public()` that would have returned the pre-simplification score instead of the post-simplification one; added a GCS-object requirement for pasted-text originals; fixed a claim-flow gap that would silently delete a claimed job's original at the 24h GCS lifecycle mark; specified claim idempotency and stronger claim proof-of-ownership; corrected the CORS and Vite tree-shaking scope items to be concrete code changes with realistic effort; added Cloud Tasks queue/worker-SA isolation to the blast-radius principle.
- **Escalated compliance gap**: the *existing* internal share-link path (`firestore.rules` `shared == true` unauthenticated read) is a live, exploitable P0-1 hole today, independent of this project — reframed Section 9 so P0-1 is not marked closed until this path is also fixed.
- **New compliance items**: WA MHMDA / CA CMIA consumer-health-data consent review and FDA/SaMD re-review are both added as **legal go/no-go blockers**, not engineering tasks; added breach-notification-for-anonymous-guests, AI-disclosure notice, patient self-service deletion, and log-retention coupling for the public path.
- **Product/observability**: added a funnel/product-analytics workstream (via backend Markers, not Firebase Analytics) and an internal dogfood/beta checkpoint before general public launch.
- **UX**: added a full spec for what happens with `NavBar` hidden (no persistent header, no sign-out, no way home today), landing-page orientation copy, guest 24h-expiry UX, a PHI/debug-detail leak in `CarePlanJobErrorView.tsx` that v2 didn't cover at all, mobile responsiveness for `SplitView`, accessibility (tap targets/font size), and several smaller copy/disclaimer requirements.

See "Decisions taken during review (overridable)" near the end of this document for the specific defaults chosen where the review required a judgment call, and Section 9 for the two items requiring legal sign-off before launch.

---

## 2. Supersession Note — What Changed Since `public-version-scope.md`

The earlier scope doc (2026-06-28) got the core architecture right (public ⊂ internal, one codebase, ephemeral guests, model-splitting via `to_public()`) but several specifics are now outdated or under-specified. This doc supersedes it on:

| Topic | Old scope doc said | This plan says | Why it changed |
|---|---|---|---|
| Auth provider for guests/anon | Undecided between session-token and Firebase Anonymous Auth; flagged Firebase Auth as "not yet BAA-covered" (P0-4) as a caveat on using it at all | **Google Cloud Identity Platform migration is DONE.** Firebase/Identity Platform auth is now BAA-covered. Use Firebase Anonymous Auth (`signInAnonymously`) with no caveat. | User confirmed the Identity Platform migration already shipped. The old doc's P0-4 caveat is stale. |
| Login method | Implied full email/password + Google | **Google Sign-In only** (`GoogleAuthProvider` + `signInWithPopup`) for the public build. Email/password remains internal-only. | Explicit product decision — reduces public auth surface (no password reset flows, no credential-stuffing exposure) and simplifies the anonymous-to-real-account linking flow. |
| "Show Original" | Solution B recommended for launch: **text-only**, no PDF, "simplest," deferred PDF signed-URL approach as Solution A | **Required for launch, for BOTH file and text uploads**, via signed GCS URL, in both cases. | Explicit product decision — this was treated as a stretch goal before; it is now a hard launch requirement. |
| Mode switching mechanism | Described as `DEPLOYMENT_MODE` env var conceptually, but frontend guidance leaned on "env var feature flags controlling what's visible" (Option B, "less duplication") | **Build-time static constant that must physically tree-shake the code out**, not a runtime/render-time flag. `{mode && <Internal/>}` is explicitly called out as insufficient because the component code still ships in the bundle. | Security requirement: frontend flags are not a security control; only a hard build determines what code is present. |
| HIPAA gaps | Mentioned in passing, mostly deferred to the HIPAA doc | **Enumerated explicitly as go/no-go gates for public launch** (Section 9), with clear must-block vs. fast-follow split. | The public deployment is internet-facing and unauthenticated by default — several existing HIPAA gaps (unauth PHI reads, committed SA keys, no audit logging) are materially worse in that context and must close before this ships. |
| Grading | "Combined grading for anonymous? Yes — show combined score only" (decision recorded, not deeply modeled) | Confirmed: public shows **both** the pre- and post-simplification `combined` scores (see v3 fix in Section 5.2/5.3 — v2's single-`combined` design had a bug). All 6 per-method entries (smog, flesch_kincaid, dale_chall, pemat, sam, cdc_cci) are internal-only, in both public and internal builds' public-facing surfaces. | Same substance for per-method exclusion; the before/after distinction was corrected during v3 review — see Section 5. |
| Downloads | PDF only, implied JSON might follow | **PDF only, client-side print. No JSON export. No share.** Explicitly excluded. | Explicit product decision, now hard scope boundary. |
| Trace/session console links | Not analyzed | **Bug found during this planning pass**: `CarePlanJobResultView.tsx` (~lines 64–133) renders Cloud Console links to session logs and trace IDs unconditionally — there is no mode gate on this block today. Must be fixed as part of this work (belt-and-suspenders even after tree-shaking, since this component is currently shared). **v3 note**: this gate must be `isPublicBuild`, not `isPublicView`/`user` — see Section 7.0. | Direct code inspection during this planning session; sharpened in v3 review. |
| Existing mode pattern | Not mentioned | Backend already has a `JUNO_MODE` env var (`api` / `worker` / `combined`) in `backend/app.py` that selects between `API_BLUEPRINTS` and `WORKER_BLUEPRINTS` (see `backend/routes/__init__.py`). `DEPLOYMENT_MODE` for public/internal should be a **second, orthogonal** env var, not a replacement for `JUNO_MODE` — a public worker and a public API service both need `DEPLOYMENT_MODE=public`. | Verified by reading `backend/app.py` directly. |

Everything else in the old scope doc's high-level shape (anonymous auth, claim-on-login, Firestore TTL, `to_public()` model-splitting, two Cloud Run services) is directionally correct and is refined, not replaced, below.

---

## 3. Core Principles

1. **Public ⊆ Internal, always.** Every field in a public-facing model also exists in the corresponding internal model. Internal models are never missing a field the public model has. This is enforced by convention (internal model author must check the public model on every change) since Python doesn't let us express "superset" as a type constraint here without the `VersionedModel` registry conflict (see Section 5). **v3 addition**: convention alone is not enough — Section 5.4 adds a CI test that fails the build if this drifts silently.
2. **Ephemeral by default, permanent by choice.** Anonymous/guest work exists for exactly 24 hours unless the user authenticates and claims it. No guest data survives longer than that anywhere (Firestore, GCS, or client localStorage).
3. **Minimum necessary PHI, enforced server-side.** The public API never returns raw uploaded text, `input`, `metrics`, per-method grading, or any internal-only field — regardless of auth state, regardless of which endpoint is hit. This is a server-side serialization guarantee, checked at the model layer, not a frontend responsibility.
4. **One codebase, two build-time deployments.** No fork, no duplicate app. Mode (`public` vs `internal`) is selected at build/deploy time for both backend (env var gating blueprint registration) and frontend (Vite static constant gating imports). There is no runtime toggle a request can flip.
5. **Frontend flags are UX, not security.** Hiding a button with `if (mode === 'internal')` is a UX nicety. The actual security boundary is (a) the internal routes not being registered at all in the public backend process, and (b) the public serialization path never having access to internal fields to accidentally leak. Even if someone hits a public endpoint directly with curl, they get the stripped model — never the internal one.
6. **Separate blast radius per deployment.** Separate Firestore collection, separate GCS prefix, separate service account, separate CORS allowlist per deployment, so a bug or compromise in the public surface cannot reach internal/clinician data. **v3 addition**: this must also cover the *async* side of the system — the public deployment gets its **own Cloud Tasks queue** and its **own worker service account**, not just a separate API-facing SA. `backend/utils/cloud_tasks.py`'s `verify_oidc_token` already keys off a single `WORKER_SERVICE_ACCOUNT` env var per process, so this is achievable by parameterizing that env var per deployment rather than sharing one worker SA across internal and public queues — otherwise a compromised public API could enqueue tasks trusted with internal-worker privileges.

---

## 4. Architecture

### 4.1 Two deployments, one repo

```
                         ┌─────────────────────────────┐
                         │        juno/ (monorepo)     │
                         │  backend/   frontend/       │
                         └──────────────┬──────────────┘
                                        │
                 build/deploy-time mode selection (no runtime toggle)
                                        │
              ┌─────────────────────────┴─────────────────────────┐
              │                                                   │
   DEPLOYMENT_MODE=internal                             DEPLOYMENT_MODE=public
   VITE_DEPLOYMENT_MODE=internal                         VITE_DEPLOYMENT_MODE=public
              │                                                   │
   ┌──────────▼──────────┐                            ┌───────────▼───────────┐
   │ Cloud Run: juno-api  │                            │ Cloud Run: juno-      │
   │ (internal)           │                            │ public-api            │
   │ registers ALL        │                            │ registers ONLY        │
   │ blueprints:           │                            │ public blueprint(s):  │
   │  care_plan_jobs       │                            │  public_bp            │
   │  batch_jobs           │                            │  (health)             │
   │  saved_outputs        │                            │                       │
   │  datasets             │                            │ /admin, /care_plan/   │
   │  grading              │                            │ batch, /care_plan/    │
   │  admin                │                            │ datasets, Athena,     │
   │  worker               │                            │ JSON export, share,   │
   │                       │                            │ note, grade-detail    │
   │                       │                            │ → 404 (not registered)│
   └──────────┬────────────┘                            └───────────┬───────────┘
              │                                                     │
   Firestore: care_plan_outputs                    Firestore: public_care_plan_outputs
   GCS: care_plan/{uid}/...                         GCS: public_care_plan/{uid}/...
   Service account: juno-internal-sa                Service account: juno-public-sa
   Cloud Tasks queue: juno-internal-queue            Cloud Tasks queue: juno-public-queue
   Worker SA: juno-internal-worker-sa                Worker SA: juno-public-worker-sa
   CORS: app.juno internal origin only               CORS: public frontend origin only
              │                                                     │
   ┌──────────▼────────────┐                          ┌─────────────▼─────────────┐
   │ Firebase Hosting       │                          │ Firebase Hosting          │
   │ target: internal       │                          │ target: public            │
   │ built with              │                          │ built with                 │
   │ VITE_DEPLOYMENT_MODE=   │                          │ VITE_DEPLOYMENT_MODE=      │
   │ internal → internal-    │                          │ public → internal-only     │
   │ only components         │                          │ components/imports are     │
   │ included normally        │                          │ tree-shaken OUT of bundle  │
   └────────────────────────┘                          └────────────────────────────┘
```

*(v3: added the Cloud Tasks queue / worker SA row per Section 3, Principle 6.)*

### 4.2 Three independent layers of "public-ness" — don't conflate them

This is the crux of the architecture and the most common way this kind of feature goes wrong, so it's spelled out explicitly:

| Layer | Mechanism | What it guarantees | What it does NOT guarantee |
|---|---|---|---|
| **Backend route existence** | `DEPLOYMENT_MODE` env var gates which blueprints `backend/app.py` registers with Flask | Internal routes (`/admin`, `/care_plan/batch`, `/care_plan/datasets`, Athena routes, share, note, grade-detail, JSON export) literally do not exist as URL rules in the public Cloud Run process → **404**, not 403. Smaller attack surface; no code path to accidentally misconfigure into exposing them. | Does not by itself guarantee that a route which IS registered in public strips PHI correctly — that's the next layer. |
| **Response serialization** | Every model exposed by a public-reachable endpoint calls `.to_public()` before it is returned. `to_public()` is defined once on the internal model and is the single place that decides what a public consumer may see. | Even a public endpoint that is deliberately exposed (e.g. `GET /public/output/{job_id}`) physically cannot return `raw`, `input`, `metrics`, or per-method grading, because those fields don't exist on the object being serialized. This is the **actual PHI-minimization security boundary**. | Does not control which routes exist (that's the layer above) or what the UI shows (that's the layer below). |
| **Frontend bundle composition** | `VITE_DEPLOYMENT_MODE` is a `const` resolved at build time (`import.meta.env.VITE_DEPLOYMENT_MODE`), used in top-level conditional imports/route definitions such that Vite's tree-shaking/dead-code-elimination physically removes internal-only component modules (share button, JSON export, note editor, batch UI, preset dataset cards, per-method grading table, admin pages, trace/session links) from the public bundle's JS output. | This is a UX and bundle-size optimization ("don't ship code for buttons that don't exist"), and it also reduces the chance a developer accidentally wires an internal-only component into a public page. It is explicitly **not** a security control — a public bundle with no download-JSON button doesn't matter if the backend endpoint would still return JSON to a hand-crafted request. That's why layer 2 (serialization) is the one that actually matters for PHI. |

Concretely, this means: **build a public endpoint's response by starting from `to_public()`, never by trusting that the frontend won't render the extra fields.**

**v3 correction — tree-shaking effort was understated.** Verified during review: `frontend/src/App.tsx` statically imports every route component at module top level (no `React.lazy`/dynamic `import()` anywhere in the router), and `CarePlanPage.tsx` statically imports and unconditionally renders `PresetDataCard` and `ConfigurationCard` (`frontend/src/pages/care-plan/CarePlanPage.tsx:9-10, 217-218`). Rollup/Vite can only tree-shake a component reference that sits in a provably dead branch at build time — a plain `{isInternal && <PresetDataCard/>}` with `isInternal` computed at runtime does **not** get eliminated, because the import itself is still live. Achieving real tree-shaking requires converting every internal-only component (`PresetDataCard`, `ConfigurationCard`, share button, JSON export, note editor, per-method grading table, admin pages, batch UI, trace/session links) to `React.lazy(() => import(...))` gated on the **build-time** `VITE_DEPLOYMENT_MODE` constant (or splitting into per-mode entry points), across `App.tsx`, `CarePlanPage.tsx`, `CarePlanJobResultView.tsx`, `Sidebar.tsx`, and `NavBar.tsx`. This is a real code-splitting refactor, not "add a top-level conditional import" — **corrected effort estimate: M**, and it's now called out explicitly in Section 13 (Phase 3) rather than implied to be trivial.

### 4.3 Relationship to the existing `JUNO_MODE` env var

`backend/app.py` already has `JUNO_MODE` (`api` | `worker` | `combined`) selecting between `API_BLUEPRINTS` and `WORKER_BLUEPRINTS` (`backend/routes/__init__.py`). `DEPLOYMENT_MODE` (`public` | `internal`) is an **orthogonal second axis**, not a replacement:

```
JUNO_MODE=api,      DEPLOYMENT_MODE=internal   → today's internal API service
JUNO_MODE=worker,   DEPLOYMENT_MODE=internal   → today's internal worker
JUNO_MODE=api,      DEPLOYMENT_MODE=public     → new public API service
JUNO_MODE=worker,   DEPLOYMENT_MODE=public     → new public worker (pipeline execution)
JUNO_MODE=combined                              → PR-preview convenience mode; DEPLOYMENT_MODE still applies within it
```

Both `API_BLUEPRINTS`/`WORKER_BLUEPRINTS` lists need a `DEPLOYMENT_MODE` filter step (see Section 8.1) rather than a parallel list, to avoid the two axes drifting out of sync.

**v3 note — `JUNO_MODE=combined` interacts with job-doc collection routing (see Section 8.6).** Because a `combined` process (used for PR previews) can serve either mode's requests, the collection a job is written to must be decided per-request/per-job, not baked into a single process-wide constant — this matters for the fix in Section 8.6.

---

## 5. Model Splitting

### 5.1 The registry constraint (why we can't just subclass)

`VersionedModel.__init_subclass__` (base for `CarePlanV1_2` in `backend/models/care_plan/versions/v1_2.py`, which extends `CarePlan` in `backend/models/care_plan/care_plan.py`) auto-registers each subclass under its version string. A hypothetical `CarePlanV1_2Public` inheriting from the same versioned base and also claiming version `"1.2"` collides in that registry. **Resolution**: only one class is ever a `VersionedModel` — the existing `CarePlanV1_2`, which remains the single stored/registered/pipeline-facing model. The public variant is a **plain Pydantic model, not a `VersionedModel` subclass**, produced only via a `to_public()` method on the internal model. It is a serialization target, never something the registry or the pipeline instantiates directly. The same pattern is used for `Grading` → `GradingPublic`, and `CarePlanInternal` (in `backend/models/care_plan/envelope.py`) → `CarePlanEnvelopePublic`.

Firestore **always** stores the full internal model (`CarePlanV1_2`, `Grading`, `CarePlanInternal`). The public/internal split happens **only** at the API/serialization boundary — never in storage. This is what makes the login-to-save "claim" flow (Section 6) a metadata move rather than a data-reshaping migration: the doc's shape never changes, only its collection and owner.

### 5.2 Field tables

**`CarePlanV1_2`** (`backend/models/care_plan/versions/v1_2.py`) — confirmed fields as of this pass: `doc_type`, `version`, `urgency`, `summary`, `reason_for_visit`, `diagnosis`, `medications`, `tests`, `procedures`, `other`, `follow_up`, `warning_signs`, `questions`, `low_priority`, `terms`, plus internal-only `note` (line 125), `raw: RawArtifacts | None` (line 127, containing original `text`/`simplified_text`/`clarified_text`), `additional_info: list[str]` (line 128, Athena API paths / source metadata).

| Field | Public | Internal | Notes |
|---|---|---|---|
| `doc_type`, `version`, `urgency` | Yes | Yes | Structural/classification, not PHI-bearing beyond what's already in the care plan body |
| `summary`, `reason_for_visit`, `diagnosis`, `medications`, `tests`, `procedures`, `other`, `follow_up`, `warning_signs`, `questions`, `low_priority`, `terms` | Yes | Yes | The actual care-plan content — this is the product |
| `note` | **No** | Yes | Clinician-note semantics per HIPAA doc; out of scope for public per explicit exclusion list (no note-taking in public) |
| `raw` (`RawArtifacts`: `text`, `simplified_text`, `clarified_text`) | **No** | Yes | Raw/intermediate pipeline text — explicitly excluded from public |
| `additional_info` | **No** | Yes | Athena/source metadata — internal only, Athena excluded from public entirely |

**`Grading`** (`backend/models/grading.py`) — `Grading{entries: list[GradingEntry], enabled, graded_at}`; each `GradingEntry{name, target, grade, description, grade_breakdown, reasoning}` where `target: Literal["before", "after"]` (`backend/models/grading.py:15`). `name` values observed: `smog`, `flesch_kincaid`, `dale_chall`, `pemat`, `sam`, `cdc_cci`, `combined`. **Critically, every method — including `combined` — is emitted TWICE**, once per `target` (`before` = pre-simplification, `after` = post-simplification), per `build_grading_with_before_after_score` (`backend/models/grading.py:28`).

**v3 bug fix — v2's `to_public()` returned the wrong entry.** v2's implementation used `next(e for e in entries if e.name == "combined")`, which returns the **first** match in list order. Because `before` entries are built before `after` entries, this silently returned the **pre-simplification** score — i.e., the *worse*, unsimplified readability grade — as "the" combined score shown to the public user. This inverts the product's core value proposition (showing that Juno *improved* readability). **Resolution**: expose **both** `combined_before` and `combined_after` on the public grading model. Showing the delta (e.g., "6th grade → 3rd grade reading level") is itself part of the product's value story, not just a bug avoidance.

**v3 hardening — narrow the public grading entry type.** The public model must not reuse the internal `GradingEntry` type as-is: `GradingEntry` carries `description`/`reasoning` free-text fields that could carry PHI-adjacent or clinician-facing reasoning text in the future (even if empty today). Define a narrow `GradingPublicEntry{grade, grade_breakdown}` with only the two fields the public UI actually needs, matching the same "narrow explicit-field model" pattern already used for `CarePlanV1_2Public`/`CarePlanEnvelopePublic` — enforce minimum-necessary at the model layer, not by convention.

| Field / entry | Public | Internal | Notes |
|---|---|---|---|
| `GradingPublic.combined_after` (`grade`, `grade_breakdown`, typed as `GradingPublicEntry`) | Yes | Yes | The post-simplification combined score — the "your care plan is easier to read" number |
| `GradingPublic.combined_before` (`grade`, `grade_breakdown`, typed as `GradingPublicEntry`) | Yes | Yes | The pre-simplification combined score — shown alongside `combined_after` to demonstrate the readability improvement (v3 addition; v2 only exposed one, and got the wrong one) |
| `smog`, `flesch_kincaid`, `dale_chall`, `pemat`, `sam`, `cdc_cci` entries (either target) | **No** | Yes | Per-method grading detail is internal-only per explicit product decision |
| `enabled`, `graded_at` | Yes | Yes | Metadata about the combined grade only |

**`CarePlanInternal`** envelope (`backend/models/care_plan/envelope.py`) — `{metrics: Metrics, input: Input, grading: Grading, care_plan: CarePlan}`.

| Field | Public | Internal | Notes |
|---|---|---|---|
| `care_plan` | Yes (as `CarePlanV1_2Public`, via `.to_public()`) | Yes | The visible care plan |
| `grading` | Yes (as `GradingPublic`, `combined_before` + `combined_after` only) | Yes | See above |
| `metrics` (session_id, pipeline_version, timing) | **No** | Yes | `session_id` specifically must not leak — it's the same identifier used for the internal trace/log console links; excluding it also closes off the trace-link leakage vector at the data level, in addition to the frontend gate (Section 7.0) |
| `input` (raw source doc reference / text / doc_id) | **No** | Yes | Never exposed; "show original" is served via a dedicated signed-URL mechanism (Section 6/7), not via this field |

### 5.3 Naming and implementation

```python
# backend/models/care_plan/versions/v1_2.py
class CarePlanV1_2(CarePlan):          # unchanged; remains the ONLY VersionedModel subclass for "1.2"
    ...
    note: str | None = None
    raw: RawArtifacts | None = None
    additional_info: list[str] = Field(default_factory=list)

    def to_public(self) -> "CarePlanV1_2Public":
        return CarePlanV1_2Public(
            doc_type=self.doc_type, version=self.version, urgency=self.urgency,
            summary=self.summary, reason_for_visit=self.reason_for_visit,
            diagnosis=self.diagnosis, medications=self.medications, tests=self.tests,
            procedures=self.procedures, other=self.other, follow_up=self.follow_up,
            warning_signs=self.warning_signs, questions=self.questions,
            low_priority=self.low_priority, terms=self.terms,
        )

class CarePlanV1_2Public(JsonModel):   # NOT a VersionedModel subclass — serialization-only
    doc_type: str
    version: str
    urgency: ...
    summary: str = ""
    reason_for_visit: list[ReasonForVisit] = []
    diagnosis: Diagnosis = Diagnosis()
    medications: list[Medication] = []
    tests: list[Test] = []
    procedures: list[Procedure] = []
    other: list[OtherInstruction] = []
    follow_up: list[FollowUp] = []
    warning_signs: list[WarningSign] = []
    questions: list[str] = []
    low_priority: list[str] = []
    terms: dict[str, GlossaryTerm] = {}
    # deliberately NO note, raw, additional_info

# backend/models/grading.py
class GradingPublicEntry(JsonModel):   # v3: narrow, explicit — NOT the internal GradingEntry
    grade: ...
    grade_breakdown: ...
    # deliberately NO name, target, description, reasoning

class GradingPublic(JsonModel):
    combined_before: GradingPublicEntry | None = None   # v3: added — pre-simplification score
    combined_after: GradingPublicEntry | None = None     # v3: this is what v2 called "combined" but got wrong (was grabbing `before`)
    enabled: bool = True
    graded_at: str | None = None

class Grading(JsonModel):              # unchanged name/shape
    entries: list[GradingEntry] = Field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None

    def to_public(self) -> GradingPublic:
        # v3 fix: select on (name, target) pair, not just name, and emit both directions
        combined_before = next(
            (e for e in self.entries if e.name == "combined" and e.target == "before"), None
        )
        combined_after = next(
            (e for e in self.entries if e.name == "combined" and e.target == "after"), None
        )
        return GradingPublic(
            combined_before=GradingPublicEntry(grade=combined_before.grade, grade_breakdown=combined_before.grade_breakdown) if combined_before else None,
            combined_after=GradingPublicEntry(grade=combined_after.grade, grade_breakdown=combined_after.grade_breakdown) if combined_after else None,
            enabled=self.enabled,
            graded_at=self.graded_at,
        )

# backend/models/care_plan/envelope.py
class CarePlanEnvelopePublic(JsonModel):
    grading: GradingPublic
    care_plan: CarePlanV1_2Public
    # deliberately NO metrics, NO input

class CarePlanInternal(JsonModel):     # unchanged name/shape
    metrics: Metrics
    input: Input
    grading: Grading
    care_plan: CarePlan

    def to_public(self) -> CarePlanEnvelopePublic:
        return CarePlanEnvelopePublic(
            grading=self.grading.to_public(),
            care_plan=self.care_plan.to_public(),
        )
```

Same pattern applies to `frontend/src/types/envelope.ts` — define `CarePlanEnvelopePublic`/`CarePlanEnvelopeInternal` TypeScript interfaces mirroring the above (including the `combined_before`/`combined_after` split and the narrow `GradingPublicEntry` shape), and make sure the public frontend build only ever imports the `...Public` types (so a stray reference to an internal-only field is a compile error, not a runtime leak).

### 5.4 Sync guardrail (v3 addition)

Convention ("check the public model whenever you touch the internal model," Section 3, Principle 1) is not durable — it silently rots the first time someone is in a hurry. Add a CI test (e.g. `backend/tests/test_public_model_sync.py`) that:

- Introspects the field sets of `CarePlanV1_2`, `Grading`, `CarePlanInternal` against their `...Public` counterparts.
- **Fails the build** whenever a new field is added to an internal model without an explicit, recorded decision in an allow/deny map for the corresponding public model (i.e., every new internal field must be either added to the public model's explicit field list, or added to a documented "internal-only, deliberately excluded" list that the test also checks against — the test should fail on an *unrecognized* field either way, not just on a missing-from-public field).
- Enforces that the public models keep using the **allow-list style already in place** (explicit field-by-field construction in `to_public()`, as in Section 5.3) — never a denylist pattern like `{**internal.dict(), **{k: None for k in ("raw","note")}}`, which inverts the safety property: a denylist is safe only until someone adds a new sensitive field and forgets to add it to the denylist, whereas an allow-list is safe by construction because a forgotten field is simply absent.

---

## 6. Anonymous 24h Guest Flow + Account Linking

### 6.1 Guest flow

1. On first page load (public build only), frontend calls `signInAnonymously()` (Firebase/Identity Platform Anonymous Auth — now BAA-covered, no caveat). UID persists in IndexedDB across refreshes. **v3 note**: see Section 7.0's UX item on what happens when this UID is lost on a new device.
2. Guest uploads a file or pastes text, hits Care Plan creation. Job is created under `public_care_plan_outputs` (separate Firestore collection) with `uid = <anon uid>` and `expires_at = created_at + 24h`.
3. Uploaded originals go to a public GCS prefix (e.g. `public_care_plan/{anon_uid}/inputs/...`) with a 1-day lifecycle delete rule. **v3 addition — text-input originals need a GCS object too.** `backend/routes/care_plan_jobs.py` currently sets `input_pdf_gcs_uri=None` for text/`doc_id` inputs; only file uploads call `upload_combined_pdf` (`backend/services/care_plan_input.py`). Today's internal "show original" renders pasted text inline from `result.input.text`, but the public envelope deliberately drops `input` entirely (Section 5.2), so there is no field left to render text originals from. **Scope addition (Phase 1/2)**: at public-job-creation time, write pasted text to a GCS object (same `public_care_plan/{anon_uid}/inputs/...` prefix, e.g. as a `.txt` object) and store its URI on the job doc, so `GET /public/output/{job_id}` can mint a signed URL for text-derived originals the same way it does for file uploads.
4. Result page fetches via a backend endpoint (`GET /public/output/{job_id}`, never client Firestore reads — see Section 9) which returns `CarePlanEnvelopePublic` plus a signed GCS URL for "show original" (both file and text-derived originals, per the above).
5. Cleanup at 24h, three overlapping mechanisms (defense in depth, since none of them individually guarantees exact-time deletion):
   - Firestore native TTL policy on `public_care_plan_outputs.expires_at` (async, "within ~24h of expiry," not instant).
   - GCS lifecycle rule (`age: 1` day) on the `public_care_plan/` prefix.
   - Server-side expiry check in `GET /public/output/{job_id}`: if `expires_at < now`, return `410 Gone` regardless of whether the underlying doc/TTL sweep has actually run yet.
   - Cloud Scheduler job (daily) purges Firebase/Identity Platform anonymous accounts older than ~48h via the Admin SDK (`list_users` filtered to anonymous + old, then `delete_users`), so anon accounts don't accumulate indefinitely even though their data is already gone.

   **v3 note — MVP sequencing is fine to start narrower.** All four mechanisms are the compliant end-state and should remain in the plan, but for a first-cut MVP it is acceptable to ship with just the `410` check plus one TTL mechanism (Firestore TTL is the simplest to stand up) and add GCS lifecycle + Cloud Scheduler cleanup as hardening once real guest volume justifies the extra operational surface — as long as they land before general public launch (Section 13, Phase 5 treats them as non-deferrable by that point regardless).

### 6.2 Account linking — new account

If the anonymous user signs up for a new account (Google Sign-In), Firebase's `linkWithCredential` **upgrades the anonymous UID in place** — no UID change, no data migration required for auth. Then the frontend calls `POST /public/claim/{job_id}` (once per pending job) which moves the Firestore doc from `public_care_plan_outputs` → `care_plan_outputs`, clears `expires_at`, and marks it non-anonymous. Because the internal model was always what's stored (Section 5.1), this is a metadata move (collection + owner + expiry fields), not a reshape.

**v3 addition — claim must also move the GCS original, or it silently vanishes.** The claim step above moves the *Firestore* doc, but the underlying GCS object (uploaded original / text-derived original per Section 6.1) stays at `public_care_plan/{anon_uid}/...`, which is still subject to the 1-day lifecycle delete rule. A user who claims their job at, say, hour 20 would keep the *care plan* permanently but silently lose the ability to "show original" at hour 24, because the source file gets deleted out from under the now-permanent doc. **Resolution**: `POST /public/claim/{job_id}` must, as part of the same operation, **copy (or move) the GCS object out of the `public_care_plan/` prefix into the internal `care_plan/{uid}/inputs/...` prefix** (which is not subject to the lifecycle rule), and update the claimed Firestore doc's stored GCS reference to point at the new location, before returning success.

**v3 addition — claim idempotency.** Implement the claim operation as a Firestore transaction with an idempotency check: if the source `public_care_plan_outputs/{job_id}` doc is already gone (e.g. because of a double-tap, a retry after a network blip, or the user re-triggering claim on refresh), look up whether a corresponding internal `care_plan_outputs` doc already exists for this `job_id`/`uid` pair. If it does, return success (not a 404/error) — the operation already happened. This avoids surfacing a confusing error for what is, from the user's perspective, a no-op retry.

### 6.3 Account linking — existing account

If the anonymous user instead signs into an account that **already exists**, `linkWithCredential` throws `auth/credential-already-in-use` (the credential is already bound to a different, real UID; Firebase cannot merge two UIDs). Handling:

1. Frontend catches the error. Before it throws away the anonymous session, it has already been persisting `{ job_id, expires_at }` pairs to `localStorage` for every guest job created (needed anyway for "return to my report" on refresh).
2. Frontend signs into the real account via `signInWithCredential(auth, err.credential)`.
3. For each pending job ID in `localStorage`, frontend calls `POST /public/claim/{job_id}` with the **now-authenticated** request. **v3 hardening — do not trust a client-supplied UID string as proof of ownership.** v2's design had the client pass the bare `anonymous_uid` string in the request body as "proof" of prior ownership, which a leaked or enumerated anonymous UID could be used to hijack (claim someone else's guest job into an attacker's account, since anon UIDs are not secrets and could in principle be guessed/observed). **Resolution**: the frontend must retain and send the anonymous user's **verified Firebase ID token** (captured before the anonymous session is discarded, or re-obtained via a short-lived custom flow) alongside the new authenticated request; the backend verifies that token server-side (same `verify_firebase_token` path, checked for anonymous provenance) and binds the claim to the UID inside the *verified token*, never to a bare copied UID string passed as a body field.
4. Backend validates the verified-token UID against `public_doc.uid`, then moves the doc (and GCS original, per Section 6.2) to `care_plan_outputs` under the real UID.
5. Edge case: multiple pending jobs — claim them all (loop/batch), show a lightweight "saving your reports…" state; don't block sign-in on all claims succeeding (a failed claim just means that one guest job expires normally at 24h — not a fatal error for the login itself). The idempotency handling in Section 6.2 also covers retries within this loop.

---

## 7. Frontend Changes

### 7.0 Critical naming distinction: `isPublicBuild` vs. the existing `isPublicView` (v3 addition — read this before touching any file below)

**Verified during review**: `frontend/src/pages/care-plan/CarePlanJobPage.tsx:51` already defines `const isPublicView = !user`. This is an **existing, different feature** — the internal shared-link viewer, used when someone follows a `/carePlan/:id` link without being logged in (see Section 9's escalated P0-1 discussion). `isPublicView` is threaded through `CarePlanJobPage.tsx` (lines 153, 166, 179, 187, 201, 230, 238), `CarePlanJobResultView.tsx` (lines 16, 41, 63, 75, 77, 84, 135, 164, 218, 252), `CarePlanJobErrorView.tsx` (lines 8, 15, 33), and `NavBar.tsx` (lines 7, 10, 23) — **none of that is the new public-deployment flag**, and it is a real bug risk that v2 did not clearly separate the two.

This plan introduces a **distinct** flag, `isPublicBuild`, driven by the build-time constant `VITE_DEPLOYMENT_MODE === 'public'` (Section 4.2). The two flags answer different questions and are **both independently true or false** in the public build for a logged-in guest:

| Flag | Question it answers | Set by |
|---|---|---|
| `isPublicView` (existing) | "Is this person viewing someone else's shared link without being the owner/logged in?" | `!user`, computed per-request in `CarePlanJobPage.tsx:51` |
| `isPublicBuild` (new) | "Is this the public B2C deployment at all, regardless of who's viewing?" | `VITE_DEPLOYMENT_MODE === 'public'`, a build-time constant |

**Every public-build-exclusive conditional must check `isPublicBuild`, never `user`/`isPublicView`.** The clearest concrete bug this catches: the Share button in `CarePlanJobResultView.tsx:227` is currently gated `{user && (...)}` — that gate is *correct* for the existing shared-link-viewer feature (don't show Share to someone viewing a link they don't own) but is **wrong** for the new public build, where a logged-in guest on `isPublicBuild` should never see Share at all, regardless of `user` being truthy. The same class of bug applies to JSON download, the note editor, grading detail, and trace/session links — all currently reachable via v2's own callouts (e.g. Section 7's trace-link fix) that referenced the wrong flag.

**Required audit**: line-by-line pass over both `CarePlanJobResultView.tsx` and `CarePlanJobErrorView.tsx` (Section 7.4 covers the latter's separate, more serious debug-leak issue) checking every conditional against this table before Phase 3 is considered complete.

### 7.1 Component-by-component changes

| Area | File(s) | Change |
|---|---|---|
| Nav bar | `frontend/src/components/NavBar.tsx` | Confirmed: `NavBar` already accepts `isPublicView` and returns `null` when true (line 23). **v3 correction**: do not simply repoint this prop at the new flag — see Section 7.2, because `NavBar` returning `null` in the public build leaves the app with **no** header at all (no logo/home, no sign-out). A separate minimal public header/footer is required; `NavBar` itself remains internal-only (leave room for future "learning tabs" but do not build them now). |
| Sidebar (saved plans list) | `frontend/src/components/Sidebar/Sidebar.tsx` | Only render for logged-in users. In the public build, guests (anonymous, unauthenticated-by-Google) see no sidebar; once linked via Google Sign-In, sidebar appears and lists their claimed + newly-created saved plans. **v3 addition**: since `NavBar` is absent in public mode, the Sidebar (when present, i.e. for a logged-in public user) is also the only reasonable home for a visible Sign-out control — see Section 7.2. |
| Upload / create flow | `frontend/src/pages/care-plan/CarePlanPage.tsx` | Public build: only file/text upload + "create care plan" action. No batch, no preset dataset picker (`frontend/src/components/PresetDataCard/*`, imported at `CarePlanPage.tsx:10` and rendered at line 217) and **no grading-toggle checkbox** (`frontend/src/components/ConfigurationCard.tsx`, imported at `CarePlanPage.tsx:9` and rendered unconditionally at line 218 — v3 addition, see Section 7.5). Both must be excluded from the public bundle via top-level conditional/lazy import gated on `VITE_DEPLOYMENT_MODE` (Section 4.2's code-splitting requirement), not a runtime `{}` check. **v3 addition**: also add the public-only landing/orientation copy described in Section 7.3. |
| Result view — downloads | `frontend/src/pages/care-plan/CarePlanJobResultView.tsx` | Public build: keep only "Download Care Plan report (PDF, client-side print)." Remove/exclude download-JSON, share button, and note editor from the public bundle (not just hide). **v3 correction**: gate on `isPublicBuild`, not `user`/`isPublicView` — see Section 7.0. The Share button at line 227 (`{user && (...)}`) is the concrete example that needs re-gating. |
| Result view — "Create another" | `frontend/src/pages/care-plan/CarePlanJobResultView.tsx:135` | **v3 addition.** Currently gated `{!isPublicView && (...)}`, which means it is invisible to *every* unauthenticated viewer, including public-build guests who have every right to create another care plan. Remove the `!isPublicView` gate for this action in the public build (it should show for any `isPublicBuild` user, guest or logged-in) — this is part of the "no way back to create a new plan" gap in Section 7.2. |
| Result view — trace/session links (bug found) | `frontend/src/pages/care-plan/CarePlanJobResultView.tsx` (~lines 64–133) | **Must fix.** `sessionId`/`traceId` are read off `jobDoc`/`result.metrics` and rendered as Cloud Console links (`console.cloud.google.com/logs/query...`, `console.cloud.google.com/traces/list...`) with no mode gate today — this block currently renders unconditionally. Two fixes needed together: (a) frontend — wrap this block in an `isPublicBuild` check (not `isPublicView`, per Section 7.0) so it's excluded from the public bundle; (b) backend — `metrics` (which carries `session_id`) is already excluded from `CarePlanEnvelopePublic` (Section 5.2), so even an un-gated public component would have no `session_id`/`trace_id` to render. Belt-and-suspenders: fix both, don't rely on either alone. |
| Error view (v3 addition — not covered in v2 at all) | `frontend/src/pages/care-plan/CarePlanJobErrorView.tsx` | See Section 7.4 — separate, more serious debug/PHI-adjacent-detail leak than the result view. |
| Show original | `frontend/src/components/SplitView/SplitView.tsx`, `frontend/src/components/SplitView/SplitView.css` | Must work for **both** file uploads and text uploads in the public build (this was a "text-only, simplest" fallback in the old scope doc — now a hard requirement, and needs the GCS-object-for-text fix in Section 6.1). Renders using a signed GCS URL returned in the `GET /public/output/{job_id}` response, same rendering path as internal ("show original" via signed URL). **v3 correction**: `SplitView.css` is currently two side-by-side flex panels with no media queries, unreadable on a phone screen — this is now a launch requirement (single-document toggle view on mobile), not a nice-to-have; see Section 7.6. |
| Grading | `frontend/src/components/OutputGradingCard.tsx` | Add `publicMode?: boolean` prop. When true: render `combined_before`/`combined_after` (per Section 5.2/5.3's v3 fix) with a one-line lay explanation of what the score means (Section 7.9). When false (internal default): current full per-method behavior unchanged. |
| Preset datasets | `frontend/src/components/PresetDataCard/*` | Internal-only. Excluded entirely from the public bundle via a mode-gated top-level import/route, not a conditional render. |
| Configuration / grading toggle (v3 addition) | `frontend/src/components/ConfigurationCard.tsx` | Internal-only per Section 7.5 — see below. |
| Types | `frontend/src/types/envelope.ts` | Add `CarePlanEnvelopePublic`/`CarePlanEnvelopeInternal`, `CarePlanV1_2Public`/mirror of internal, `GradingPublic` (with `combined_before`/`combined_after`, per Section 5.3). Public build code should only import the `...Public` types so referencing an internal-only field is a TypeScript compile error. |
| API client | `frontend/src/api/jobs.ts`, `frontend/src/api/savedOutputs.ts` | Add public-build API calls (`createPublicJob`, `getPublicOutput`, `claimPublicJob`) targeting `/public/*` endpoints. Internal-only calls (batch, datasets, grading detail, admin) excluded from the public bundle. |
| Client Firestore reads | `frontend/src/hooks/useJobSnapshot.ts` | Currently reads job/output docs directly via Firestore client `onSnapshot` — this is exactly the pattern responsible for the P0-1 HIPAA gap (Section 9, both the new-collection risk and the escalated *existing* share-link risk). For the **public build**, this hook must not be used to read PHI-bearing output docs directly; the public report page fetches via `GET /public/output/{job_id}` (a backend endpoint that returns the stripped model) instead. Status/progress polling (non-PHI: `status`, `stage`) may still use a client snapshot if desired, but the final care-plan content must go through the backend. |
| Auth | `frontend/src/auth/AuthContext.tsx` | Add `signInAnonymously` (silent, on load, public build only) and `GoogleAuthProvider`/`signInWithPopup` for the "log in to save" action, plus the `linkWithCredential` / `auth/credential-already-in-use` handling described in Section 6 (including the v3 verified-token hardening in Section 6.3). Internal build keeps existing email/password + (if already present) Google. **v3 addition — 30-min inactivity auto-signout must not apply to anonymous guests.** `AuthContext.tsx` implements a 30-minute inactivity timeout (`VITE_SESSION_TIMEOUT_MS`, default `30 * 60 * 1000`) that calls `signOut(firebaseAuth)` for any authenticated user. Applied unmodified to an anonymous guest, this silently signs the guest out mid-flow (e.g., while reading a long care plan) and loses their anonymous UID/session context. **Resolution**: disable, or substantially extend, the inactivity timer specifically for anonymous sessions in the public build — a guest reading their own already-generated care plan is not the same risk profile the 30-minute HIPAA-driven timeout was designed for (that control targets authenticated clinician sessions with access to other patients' data). |
| Login page | `frontend/src/pages/LoginPage.tsx` | Public build: Google-only sign-in button. Internal build: existing email/password (+ Google) unchanged. **v3 addition**: add the "guest mode is the alternative" copy from Section 7.7. |
| Firebase config | `frontend/firebase.json`, `frontend/.firebaserc` | Add a second Hosting target (Section 11). |

### 7.2 Navigation with `NavBar` hidden (v3 addition, CRITICAL)

Verified during review: `NavBar.tsx:23` returns `null` in public/`isPublicView` mode, and `NavBar` is the **only** existing home for the sign-out control and the "+" new-plan link. "Create another care plan" is separately gated `{!isPublicView && ...}` (`CarePlanJobResultView.tsx:135`), so it never shows in any unauthenticated context today — including for public-build guests. `Sidebar.tsx` has no home/new-plan/sign-out affordance of its own. The net effect, if shipped as-is: a public-build user (guest or logged-in) has **no way back to the home/upload screen and no visible way to sign out** once they land on a result page.

**Requirements**:
- Add a persistent minimal public header/footer, independent of `NavBar`, always visible in the public build: a Juno logo/home link plus a "New care plan" action.
- Remove the `!isPublicView` gate on "Create another care plan" (`CarePlanJobResultView.tsx:135`) for the public build — see the table row above.
- Add a visible Sign-out affordance for logged-in public users (e.g., in the Sidebar header, since `NavBar` remains internal-only) — a logged-in guest currently has no way to sign out at all.

### 7.3 Landing orientation copy (v3 addition, CRITICAL)

`CarePlanPage.tsx` today has no heading or explanatory copy — it is the upload card and nothing else. With `NavBar` hidden (Section 7.2) and no prior context, this is a first-time visitor's entire first impression of the product. Add public-build-only static copy above the upload card:
- A one-line value statement (what Juno does).
- A 3-step "how it works" strip: Upload → We simplify it → Read/download your care plan.
- A one-sentence privacy note: "processed securely and deleted within 24 hours unless you sign in to save it."

This also serves as the first-run explainer (Section 7.9) — a first-time visitor should be able to tell what the tool does and roughly how long processing takes without hunting for it.

### 7.4 `CarePlanJobErrorView.tsx` leaks internal debug detail (v3 addition, CRITICAL — not in v2 at all)

Verified during review: `CarePlanJobErrorView.tsx` unconditionally renders Cloud Console links to session/trace logs (lines ~25-28 build the URLs; rendered further down), an error-code badge, a "Retryable: Yes/No" indicator (line 59), the raw developer error message (`devMessage`, lines 20/64/73), and an expandable `<details>` block dumping raw technical error text (lines 79-104) — **none of this is gated on any mode flag today**. This is a materially worse leak surface than the result-view trace links (Section 7.1) because it fires on every error, and error paths are exactly where more internal detail tends to accumulate over time.

**Requirement**: in the public build, render **only** the curated `userMessage`/`user_hint` (already computed at line 18) plus a generic retry/contact affordance. Strip the error-code badge, the "Retryable" flag, `devMessage`, the `<details>` technical dump, and the Cloud Console links **from the render path entirely** (conditionally not rendering the JSX, not just hiding via CSS) — combined with the code-splitting approach in Section 4.2, this component's public variant should not even have the console-link-building code present in the shipped bundle.

### 7.5 `ConfigurationCard` exposes internal jargon (v3 addition, HIGH)

`ConfigurationCard.tsx` renders a bare "Enable grading" checkbox, unconditionally shown in `CarePlanPage.tsx:218` — this was not in v2's exclusion list. "Grading" is internal/pipeline jargon with no meaning to a patient. Add it to the exclusion list in Section 7.1's table: exclude `ConfigurationCard` from the public bundle using the same mode-gated import pattern as `PresetDataCard`. Grading runs automatically (always enabled) in the public build with no user-facing toggle.

### 7.6 Guest 24h-expiry UX and mobile/error-copy specifics (v3 addition)

v2 only specified the backend mechanics of 24h expiry (Section 6.1); v3 fully specifies the UX:

- **Persistent expiry banner**: on the result page, a non-blocking banner with a countdown and a single "Save with Google" call-to-action. Reuse the accessible pattern already established by `SessionTimeoutWarning.tsx` (`role="alert"`, `aria-live`) as the base rather than inventing a new pattern.
- **Dedicated expired-state screen**: when a guest returns after expiry, show a purpose-built screen ("This report has expired. Guest reports are available for 24 hours. [Create a new one →]"), not a raw `410` response rendered as-is.
- **One calm frequency rule**: the banner appears on result-page load and stays persistent; it is never an interrupting modal, and there is no separate escalating "near-expiry" alert on top of it — one steady, low-urgency signal for the whole 24h window.
- **Mobile `SplitView`** (HIGH): `SplitView.css` has no media queries and lays out two side-by-side flex panels — unreadable on a phone. Add `@media (max-width: 768px)` that stacks panels vertically, full width, with an "Original" / "Care Plan" toggle. This **supersedes** v2's "single-view is a nice-to-have" framing (v2 Section 7 table) — it is now a launch requirement, not deferred.
- **Mobile-first upload / camera capture** (from combined PM+UX review): consider mobile-first upload including photo/camera capture, since patients often photograph paper documents rather than having a PDF; ensure the result view's responsive layout (including the `SplitView` fix above) is verified on a real mobile viewport before launch.
- **Unified error copy**: some paths already show curated messages; others fall back to raw `err.message` (e.g. `CarePlanPage.tsx:130`, and the grading catch in `CarePlanJobPage.tsx`). Define one small, closed set of patient-facing error strings and route every public-build catch block through it. Continue logging the raw message server-side for observability (ties into Section 10), but never render it in the public build.
- **New-device guest-loss note**: the anonymous UID lives in IndexedDB/localStorage, so a guest who opens the report on a different device silently loses access to it. Add a one-line UI note ("This report is only saved on this device — sign in to access it anywhere") instead of leaving this as a silent loss.

### 7.7 Copy / disclaimer additions (v3 addition, MEDIUM)

- **Google-only login fallback line**: on the public login/save prompt, add: "We currently support signing in with Google only. You can still use and download your care plan as a guest — sign-in is only needed to save it for later." This reframes the Google-only constraint as a non-blocker by foregrounding guest mode as the alternative.
- **Medical-advice disclaimer**: add a single quiet, informational (not alert-styled) line in the result-page footer, e.g. "This is a plain-language summary to help you understand your visit — always follow up with your care team about your health."
- **AI-disclosure notice**: the internal build's clinic-facing Notice of Privacy Practices normally carries the "this was generated by AI" disclosure (per the HIPAA doc's P2-6); there is no equivalent NPP for a B2C user. Add the public build's own explicit "this care plan was generated by AI" notice to the result view.

### 7.8 Accessibility (v3 addition, MEDIUM)

Public-build action buttons are currently sized around 28–32px tall (`padding: 6px 14px`, `font-size: 0.8rem`), below the ~44px minimum recommended tap target for a patient-facing, likely-mobile-heavy audience; some copy renders at 0.7rem. Require ≥44px tap targets (roughly `padding: 12px 20px`) and ≥14px (`0.875rem`) minimum font size for all patient-facing copy in the public build.

### 7.9 Readability score explainer (v3 addition, LOW)

The public `OutputGradingCard`'s `combined_before`/`combined_after` scores (Section 5.2/7.1) need a one-line lay explanation of what the number means for a non-technical reader — not just the raw score/label.

---

## 8. Backend Changes

### 8.1 Mode gating in `backend/app.py`

```python
DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "internal")  # "public" | "internal"

_blueprints = [bp for bp in _blueprints if _allowed_in_mode(bp, DEPLOYMENT_MODE)]
```

Concretely: define per-blueprint mode allowlists in `backend/routes/__init__.py` (or a small mapping in `app.py`) so that in `DEPLOYMENT_MODE=public`, only `public_bp` (new) and the health-check route are registered — `care_plan_jobs_bp`, `batch_jobs_bp`, `saved_outputs_bp`, `datasets_bp`, `grading_bp`, `admin_bp` are **not** registered at all in the public process, and requests to their paths 404. This composes with the existing `JUNO_MODE` filter (`API_BLUEPRINTS` vs `WORKER_BLUEPRINTS`) as an independent second filter — see Section 4.3.

### 8.2 New `backend/routes/public.py`

| Endpoint | Auth | Behavior |
|---|---|---|
| `POST /public/jobs` | Anonymous or real Firebase/Identity Platform UID (Bearer token) | Accepts file or text input; creates job in `public_care_plan_outputs` with `uid`, `created_at`, `expires_at = created_at + 24h`; for text input, also writes the pasted text to a GCS object and stores its URI (Section 6.1's v3 addition); enqueues pipeline run via the deployment's own Cloud Tasks queue (Section 3, Principle 6) using `backend/services/care_plan_pipeline.py`, `backend/services/care_plan_input.py`, `backend/utils/cloud_tasks.py`. **v3 note**: "pipeline logic itself is unchanged" is true for the grading/AI logic, but the job-lifecycle persistence layer is **not** unchanged — see Section 8.6. |
| `GET /public/jobs/{job_id}` | UID match | Status/stage polling only (`not_started`/`processing`/`completed`/`error`) — no PHI in this response. |
| `GET /public/output/{job_id}` | **UID match required on every call, no exception (v3 fix — see below)** | Loads the stored internal envelope, checks `expires_at` (410 if expired), calls `.to_public()`, returns `CarePlanEnvelopePublic` plus a freshly generated signed GCS URL (short-lived, e.g. 30 min) for "show original" (file or text-derived original alike). |
| `POST /public/claim/{job_id}` | Authenticated (real, non-anonymous UID, verified server-side per Section 6.3's hardening) | Body includes proof bound to a verified anonymous ID token for the existing-account path (Section 6.3) — not a bare `anonymous_uid` string. Validates ownership, moves doc `public_care_plan_outputs` → `care_plan_outputs`, moves the GCS original into the internal prefix (Section 6.2), clears `expires_at`, marks `is_anonymous=False`, and is idempotent (Section 6.2). Returns `{ new_job_id }`. |

**v3 fix — CRITICAL, reintroduces P0-1 if not fixed.** v2's design for `GET /public/output/{job_id}` allowed **"UID match, or none if job is not yet claimed by a different account"** — i.e., an unauthenticated fallback path on a PHI-serving endpoint. This is a direct reintroduction of the P0-1 unauthenticated-PHI-read gap the rest of this plan (and the HIPAA doc) is trying to close, just on the *new* collection instead of the old one. **Remove the unauthenticated fallback entirely.** Require the caller's Firebase UID (anonymous-auth UID, or claimed real UID) to match `public_doc.uid` on **every** call to this endpoint, including the signed-URL generation step for the original document — there is no code path in this endpoint that should ever run without a UID match. The "I lost my session / opened it on a new device" recovery case (Section 7.6) must be solved via an explicit re-auth/relink flow (e.g., prompting sign-in and running the claim/relink logic), never via an unauthenticated fallback on an endpoint that serves PHI.

### 8.3 Routes/files that must NOT be reachable in public mode

`backend/routes/admin.py`, `backend/routes/batch_jobs.py`, `backend/routes/datasets.py` (preset datasets, Athena Health), `backend/routes/grading.py` (per-method grade-detail/regrade endpoints), and any share/JSON-export/note endpoints inside `backend/routes/saved_outputs.py` — none of these blueprints are registered under `DEPLOYMENT_MODE=public` (Section 8.1), so calling them returns 404, not 403. This is the deliberate choice over "auth-gate them at 403" per the confirmed technical decision.

### 8.4 `backend/utils/firebase.py` (`verify_firebase_token`)

**v3 correction to v2's framing.** `verify_firebase_token` in its current form already accepts anonymous UIDs as a valid authenticated identity — it does not check `sign_in_provider` at all, so no work is needed to make it "accept" anonymous tokens for `/public/*` endpoints generally. **The actual new work** is the opposite: a decorator variant that **rejects** anonymous UIDs, by checking `decoded_token.get('firebase', {}).get('sign_in_provider') != 'anonymous'`. This variant is needed for:
- `POST /public/claim/{job_id}`'s final "who owns this now" check (claiming requires a real, non-anonymous identity — Section 6.3), and
- every route registered under the internal blueprints (which should never accept an anonymous identity at all).

### 8.5 Other shared backend files (unchanged logic, mode-aware only where noted)

**v3 correction — location of the hardcoded GCS prefix.** The path prefix `care_plan/{user_id}/inputs/{id}.pdf` is hardcoded in `backend/services/care_plan_input.py::upload_combined_pdf`, **not** in `backend/utils/gcs.py` (v2 misattributed this). The fix (parameterize by mode: `care_plan/` vs `public_care_plan/`) belongs in `care_plan_input.py`; add the public bucket/prefix to lifecycle config separately (Section 11). `backend/observability/*`, `backend/utils/markers/*` — no functional change, but see Section 10 (need mode/label on emitted metrics so public vs internal error rates can be dashboarded separately, and see Section 10's new funnel-analytics workstream). `backend/cloudbuild.yaml` — needs a second build/deploy path for the public Cloud Run service (Section 11).

### 8.6 Job-lifecycle persistence is hardcoded to the internal collection (v3 addition, CRITICAL — corrects v2's "pipeline unchanged" claim)

v2 (Section 8.2, in the `POST /public/jobs` row) claimed the pipeline is "unchanged." This is **incorrect** for the persistence layer specifically. Verified during review:

- `backend/utils/firebase.py` — `create_job_doc`, `get_job_doc`, `update_job_stage`, `complete_job`, `fail_job` (lines ~257, 265-268, 274-277, 286-290, 303-307, 318-321) **all hardcode** `db.collection("care_plan_outputs")`.
- `backend/routes/worker.py:75` inline-hardcodes `firestore_client().collection("care_plan_outputs").document(job_id).update({...})`.

As written, a job created via `/public/jobs` and driven through the shared worker pipeline would still read/write against `care_plan_outputs` — the internal collection — not `public_care_plan_outputs`. **Scope addition**: thread a collection/mode parameter through the `JobDoc` type and all five `backend/utils/firebase.py` functions above, plus the inline update in `backend/routes/worker.py`, so the correct collection is used for the lifetime of a job.

**Important**: this parameter must be sourced from **a field stored on the job doc itself at creation time** (e.g. `job.collection` or `job.deployment_mode`), not solely from the process-level `DEPLOYMENT_MODE` env var — because `JUNO_MODE=combined` (Section 4.3, used for PR previews) runs a single process that can serve jobs for either mode, so the process-level env var alone can't disambiguate which collection a given job belongs to. The job doc's own recorded mode is the source of truth; the process env var is only used to decide which *routes* are registered (Section 8.1), not which collection an individual job's data lives in.

### 8.7 CORS is not mode-aware (v3 addition, MEDIUM — concrete code change, not just an infra checklist item)

`backend/app.py:31-44` calls `CORS(app, origins=[...])` once at import time with a single hardcoded list (`https://juno-medical-clarity.web.app`, `https://juno-medical-clarity.firebaseapp.com`, `http://localhost:3000`, `http://localhost:5173`). This needs to become mode-aware as an actual code edit:

```python
# backend/app.py
_INTERNAL_ORIGINS = [
    "https://juno-medical-clarity.web.app",
    "https://juno-medical-clarity.firebaseapp.com",
    "http://localhost:3000",
    "http://localhost:5173",
]
_PUBLIC_ORIGINS = [
    "https://<public-hosting-domain>",  # tight allowlist, no localhost in prod public
]
_CORS_ORIGINS = _PUBLIC_ORIGINS if DEPLOYMENT_MODE == "public" else _INTERNAL_ORIGINS

CORS(
    app,
    origins=_CORS_ORIGINS,
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Session-Id"],
    expose_headers=["X-Session-Id", "X-Trace-Id"],
    supports_credentials=False,
    max_age=600,
)
```

i.e., the origins list must be computed from `DEPLOYMENT_MODE` **before** the `CORS()` call, giving the public deployment its own tight allowlist rather than sharing the internal list. Cross-ref Section 9 (P1-7).

---

## 9. HIPAA Launch-Blocker Gates

The public deployment is internet-facing and unauthenticated-by-default, which raises the stakes on several already-known gaps from `hipaa-compliance-action-plan.md`. This table folds those into explicit go/no-go gates for public launch.

**v3 reframing of P0-1 — do not mark this row blanket-closed.** v2 marked P0-1 "closed" on the strength of routing the *new* `public_care_plan_outputs` reads through `GET /public/output/{job_id}` instead of client Firestore. That fix is real and necessary, but it only covers the **new** collection. **Escalated finding**: the *existing* `firestore.rules` rule for the *existing* internal collection —

```
match /care_plan_outputs/{docId} {
  allow get: if ... || resource.data.shared == true;
}
```

— is an **unauthenticated, full-internal-document read** (raw text, note, session_id, everything) reachable **today**, in the current shipped app, via the existing internal share feature. `frontend/src/App.tsx:31` allows `/carePlan/:id` without auth, and that route is exactly the `isPublicView` (Section 7.0) code path — a different, older feature than anything new in this plan. This is the *real* P0-1 gap, and it is exploitable right now, independent of whether the public B2C deployment ever ships. The trace/session-link leak (Section 7.1) and the JSON-download path are both reachable via this same unauthenticated share link today.

| Gate | Priority (per HIPAA doc) | Blocks public launch? | Fix required for this project |
|---|---|---|---|
| Unauthenticated share-link reads full PHI via client Firestore SDK — **both** the existing internal share path AND the new public-collection risk | P0-1 | **YES — not fully closed by this plan alone** | For the new surface: public reads must go through `GET /public/output/{job_id}` (backend, returns `CarePlanEnvelopePublic`, with the unauthenticated-fallback bug fixed per Section 8.2) — never a client-side Firestore `onSnapshot`/`get()` against a PHI-bearing collection; `frontend/src/hooks/useJobSnapshot.ts` must not be used for public report content (Section 7.1). Firestore rules for `public_care_plan_outputs` should deny direct client reads of the output content entirely (`allow get: if false;`). **Additionally (v3 escalation, separate task)**: close the hole on the *existing* `care_plan_outputs` share path — route shared reads through a backend endpoint that returns the stripped public model (or a backend-validated signed token) instead of raw client Firestore rules, and audit whether `firestore.rules`'s `shared == true` clause should be removed/replaced entirely. This is in scope for this project because it is the same class of bug this project is otherwise fixing, and shipping the new public deployment without also closing the old hole leaves P0-1 objectively open. |
| Committed service-account key JSON files at repo root | P0-2 | **YES** | Unrelated to the public/internal split technically, but must close before standing up a second, internet-facing, unauthenticated-by-default service — don't multiply the blast radius of a live key exposure. Revoke both keys in GCP IAM, delete from repo, add to `.gitignore`, move all credentials to Secret Manager. |
| Cloud Audit Logs (Data Access) not enabled for Firestore/GCS | P0-3 | **YES** | With a new anonymous-accessible collection (`public_care_plan_outputs`) and GCS prefix, this is the only way to have any record of who/what touched PHI outside the app's own logs. Enable DATA_READ/DATA_WRITE/ADMIN_READ before public launch. |
| No PHI-document-level audit trail (reads/writes/deletes of outputs, GCS uploads/downloads/signed-URL generation, report downloads) | P1-2, P1-3, P1-4, P1-5 | **YES for the public-specific paths** (job creation, output read, claim, signed-URL generation, report download); internal-side audit trail can remain fast-follow per existing P1 timeline | Every `/public/*` endpoint action (job create, output read, claim, signed URL issuance) must emit a structured audit event (`uid`/`anon_uid`, `job_id`, `action`, `timestamp`, `trace_id`) via the existing Markers framework (`backend/utils/markers/`). This is materially more important for public because there's no clinician-side accountability chain otherwise. Note the P1-5 gap (no audit trail on delete) also applies to the new self-service deletion path (Section 9's new compliance items, below). |
| Cloud Logging retention 30 days vs required 6 years (2190 days) | P1-1 | **YES for the public path specifically (v3 escalation — see below)** | Bump retention on the log bucket(s) covering the public service before any real (non-test) public traffic. |
| CORS too broad in prod | P1-7 | **YES** | Public deployment needs its own tight origin allowlist (Section 8.7, Section 11) distinct from and narrower than internal's — see Section 8.7 for the concrete `backend/app.py` code change. Should not allow `localhost` origins in the production public deployment. |
| GCS object versioning not enabled | P1-8 | Should close before launch (cheap to enable, protects against accidental/malicious deletion of the newly-created public bucket/prefix too), not a hard blocker | Enable versioning on the bucket(s) serving both `care_plan/` and `public_care_plan/` prefixes. |
| **Unauthenticated `/public/jobs` cost/abuse exposure (v3 — promoted from Open Question to launch gate)** | New | **YES** | See below — moved out of Section 12; this is now a launch blocker, not an open question. |
| ~~Firebase Auth not BAA-covered (Identity Platform migration)~~ | ~~P0-4~~ | **N/A — already done.** | The Identity Platform migration is complete. This gate is closed; the HIPAA action-plan doc and the old scope doc both list it as open/deferred — that is now stale and should be corrected wherever referenced. This directly unblocks using Firebase Anonymous Auth and Google Sign-In for public without a BAA caveat. |

**v3 rate-limiting escalation (item promoted from Section 12).** Unauthenticated, free, disposable anonymous UIDs can trigger paid LLM pipeline runs with zero auth barrier. This is a direct cost-and-abuse exposure, not merely a "design gap to close before launch" as v2's Section 12 framed it — it is now a launch gate. Recommend Cloud Armor IP-based rate limiting in front of the public Cloud Run service, plus a per-UID/day quota enforced in `POST /public/jobs` itself (defense in depth: infra-level and app-level).

### 9.1 Compliance items new in v3 (additions beyond the existing HIPAA action-plan gates)

| Item | Severity | Detail |
|---|---|---|
| **WA MHMDA / CA CMIA consumer-health-data consent — LEGAL GO/NO-GO BLOCKER** | CRITICAL | A public, patient-facing upload flow is exactly the "direct collection of consumer health data from patients" trigger already flagged as an open question in the sibling docs (`hipaa-compliance-action-plan.md` Open Q#3 / P2-5; `ehr-clinic-compliance-requirements.md`). **This requires a legal opinion on Washington MHMDA "regulated entity" status before launch.** If MHMDA applies, an explicit **opt-in consent screen** (not a ToS checkbox buried at signup) is required before any data collection. MHMDA carries a private right of action, so this cannot be treated as a fast-follow — it is a go/no-go item the team must resolve with counsel, not an engineering task to schedule. |
| **FDA / SaMD re-review — LEGAL GO/NO-GO BLOCKER** | CRITICAL | The existing "not a medical device" posture rests on the internal product being clinician-mediated. The public flow removes the clinician entirely — unmediated direct-to-consumer AI interpretation of an arbitrary clinical document. Regulatory counsel must re-run the intended-use/SaMD analysis specifically for the direct-to-consumer flow before launch; this cannot be assumed to inherit the internal product's classification. Cross-ref `ehr-clinic-compliance-requirements.md`. |
| Breach notification for anonymous guests | HIGH | A guest has no email/phone/account on file, so §164.404 individual notice cannot be delivered in the normal way. Document the "substitute notice" mechanism (45 CFR §164.404(d)(2) — conspicuous website posting) in the Incident Response Plan before real guest traffic, so this isn't improvised during an actual incident. |
| 24h-delete vs. 6-year-retention reasoning | HIGH | Document explicitly (currently implemented but not reasoned in writing): the 6-year retention requirement (§164.316(b)(2)(i)) covers Security-Rule *administrative documentation*, not a mandate to retain a copy of the health record itself; the care plan is derived from data the patient already possesses; ephemeral/minimum-necessary is the defensible posture for guest PHI specifically. `hipaa-compliance-juno.md` already lists this as an open legal question — flag it there as needing confirmation, not a settled fact. |
| AI-disclosure notice | MEDIUM | For B2C there is no clinic Notice of Privacy Practices to carry the "generated by AI" disclosure (P2-6). Add the public build's own explicit AI-disclosure notice — see Section 7.7. |
| Patient rights / self-service deletion | MEDIUM | Once a guest claims a job, it lives permanently in `care_plan_outputs` with no expiry. A public/patient account needs a deletion-on-request path (Privacy Rule access/amendment rights, P2-3). Note the existing P1-5 gap (no audit trail on delete) applies to this new path too — don't ship deletion without also emitting the audit event. |
| Log retention (P1-1) coupled to audit trail (P1-2..5) for the public path specifically | HIGH | For anonymous guest data, the audit log is the **only** surviving record once the underlying PHI is deleted at the 24h mark. If Cloud Logging is purged at the default 30 days, there is zero compliance record past a month for guest activity that already left no other trace. **Couple P1-1 (6-year log retention) to P1-2..5 as a blocker for the public path specifically** — it is not independently deferrable the way it might be for the internal side, where other records persist. |
| `/admin/stats` coverage | LOW | P1-6 (admin endpoint streaming PHI-adjacent aggregate data) needs to cover **both** collections if internal admin tooling will observe `public_care_plan_outputs` in addition to `care_plan_outputs`. |

**Net read (v3)**: P0-1, P0-2, P0-3, P1-2..5 (public-specific paths), P1-7, and the new rate-limiting gate must close before public launch; P1-1 is now coupled to P1-2..5 for the public path (no longer independently deferrable there); P1-8 should close before launch but could slip a few days as fast-follow if genuinely necessary; P0-4 is done and should be struck from any blocker list going forward. **Separately, and gating all of the above**: the MHMDA/CMIA consent question and the FDA/SaMD re-review are **legal go/no-go blockers** that must be resolved with counsel — they are not on the engineering team's critical path to close unilaterally, but the launch cannot proceed without an answer on both.

---

## 10. Observability & Alerting Workstream

**Current state**: structured Cloud Logging + OpenTelemetry → Cloud Trace, a custom log-based Markers framework (`backend/utils/markers/`), and a manual `/admin/stats` page for aggregate visibility. There is **no** alerting system (no Sentry/PagerDuty/equivalent) and **no** Cloud Monitoring dashboards or alert policies today — visibility is entirely "go look at logs/traces/admin page."

This is explicitly called out by the user as a requirement for the public launch: **robust error logging, metrics with Google Cloud dashboards (graphs), and alerting when a user hits an error.**

Scope as its own workstream, roughly:

1. **Log-based metrics**: define Cloud Logging log-based metrics off existing structured logs / Markers events for: request error rate (5xx) on the public service, pipeline job failure rate, job processing latency (p50/p95), guest-job creation rate (abuse signal), claim-flow failure rate.
2. **Cloud Monitoring dashboards**: build a dashboard (or a small set) surfacing the above metrics as graphs, scoped per deployment (public vs internal) so public traffic issues are visible independent of internal usage.
3. **Alert policies**: create Cloud Monitoring alert policies on the above (e.g., 5xx rate above threshold over N minutes, job failure rate above threshold, sustained latency regression) wired to a notification channel — email at minimum for launch; Slack/PagerDuty as a fast-follow if there's an existing integration preference.
4. **Per-deployment labeling**: ensure logs/metrics/traces are labeled by `DEPLOYMENT_MODE` (or by Cloud Run service name, which already differs) so dashboards/alerts can be filtered/scoped to "public only."
5. **Tie into the audit-trail work** (Section 9): the same Markers-based structured events used for HIPAA audit trail can double as the source for error-rate log-based metrics — don't build two separate logging paths.
6. **Product/funnel analytics workstream (v3 addition).** v2's Section 10 covered only ops metrics (5xx, job failures, latency) and treated the guest-job creation rate solely as an abuse signal. Add a **product-funnel metrics workstream**, implemented via the same backend Markers events framework — explicitly **not** Firebase Analytics, which is not BAA-covered and must not be used for anything touching this product surface (consistent with the HIPAA-deferred-items guidance on not removing Firebase Analytics elsewhere in the app, but adding *new* analytics instrumentation here must go through the BAA-covered backend path, not client-side Firebase Analytics). Instrument the funnel: upload started → upload completed → plan viewed → download/show-original used → login initiated → job claimed. Track activation rate, guest→signup conversion rate, and upload→plan-viewed completion rate. Specifically instrument PDF-download and show-original usage on their own, so that a future "should we add share back" decision is made from evidence rather than guesswork.

This workstream has no hard technical blocker dependency on the model-split or mode-gating work and can be built in parallel once the public Cloud Run service exists (needs a running public service to have something to monitor).

---

## 11. Deployment / Infrastructure

| Component | Internal (existing) | Public (new) |
|---|---|---|
| Cloud Run service | `juno-api` (+ worker) | `juno-public-api` (+ public worker), `DEPLOYMENT_MODE=public` |
| Firebase Hosting target | existing target (rename/confirm as `internal` in `firebase.json`) | new target `public`, separate `firebase.json` hosting entry + build output dir |
| Firestore collection | `care_plan_outputs` | `public_care_plan_outputs` (new), TTL enabled on `expires_at` |
| GCS path prefix | `care_plan/{uid}/inputs/...` (hardcoded in `backend/services/care_plan_input.py::upload_combined_pdf` — Section 8.5) | `public_care_plan/{uid}/inputs/...` (new), 1-day lifecycle delete rule |
| Service account | existing internal SA | new, narrower-scoped public SA (only what's needed for `public_care_plan_outputs` + `public_care_plan/` prefix + anonymous-auth admin operations for cleanup) |
| Cloud Tasks queue (v3 addition) | existing internal queue | **new, dedicated public queue** — Section 3, Principle 6 |
| Worker service account (v3 addition) | existing internal worker SA | **new, dedicated public worker SA**, referenced by the public worker's `WORKER_SERVICE_ACCOUNT` env var so `verify_oidc_token` (`backend/utils/cloud_tasks.py`) enforces the isolation — Section 3, Principle 6 |
| CORS allowlist | internal frontend origin(s) only | public frontend origin(s) only — separate, tighter list, computed from `DEPLOYMENT_MODE` in `backend/app.py` per Section 8.7 (P1-7) |
| Cloud Scheduler | n/a today | new daily job: purge anonymous Firebase/Identity Platform accounts older than ~48h (belt-and-suspenders alongside Firestore TTL) |
| CI/CD | existing `backend/cloudbuild.yaml` / deploy workflow | needs a second build/deploy path (either a second Cloud Build trigger/config or a mode parameter in the existing one) targeting `juno-public-api` and the public Hosting target, with `DEPLOYMENT_MODE=public` / `VITE_DEPLOYMENT_MODE=public` set at build time |
| Firestore rules | `firestore.rules` — existing rules for `care_plan_outputs`, including the `shared == true` unauthenticated-read clause flagged as an open P0-1 gap in Section 9 | add rules for `public_care_plan_outputs`: deny direct client reads of PHI-bearing fields (Section 9), deny list (no enumeration), deny direct client writes (backend-only, consistent with existing pattern for `care_plan_outputs`) |

---

## 12. Potential Roadblocks & Open Questions

1. **Existing-Firestore-rules pattern for `public_care_plan_outputs`.** The internal collection already denies client-side writes; the public collection needs the same, plus a decision on whether ANY field (e.g. `status`/`stage` for lightweight polling) is safe for direct client read, or whether even status polling should go through `GET /public/jobs/{job_id}` exclusively. Recommend the latter for simplicity and to avoid a second rules surface to audit.
2. ~~Rate limiting / abuse on unauthenticated `/public/jobs`.~~ **Moved to Section 9 as a launch gate (v3) — no longer an open question.** See Section 9's rate-limiting escalation.
3. **Signed-URL exposure window for "show original."** A signed URL good for the guest's session could, in principle, be shared/leaked (e.g., pasted into a chat) during its validity window. Mitigate with a short expiry (e.g., 15–30 min, regenerated per request rather than cached) rather than a long-lived link; acceptable residual risk for launch given the 24h ephemeral nature of guest data overall.
4. **Anonymous account accumulation prior to Cloud Scheduler cleanup running.** Between launch and the first scheduled cleanup run there's a window where anonymous accounts accumulate; ensure the Cloud Scheduler job is deployed and verified working *before* opening public traffic, not after. (Per Section 6.1's v3 MVP note, an initial launch could rely on the `410` check + one TTL mechanism alone, with GCS lifecycle + Cloud Scheduler landing as hardening shortly after, as long as this lands before general public launch per Section 13 Phase 5.)
5. **Google-only login means no fallback if a user doesn't have/want a Google account.** Explicit product decision accepted this constraint for the public build; the copy fix in Section 7.7 reframes it as "guest mode is the alternative" rather than a dead end. Worth flagging as a UX limitation if adoption data later suggests it's a barrier, but out of scope to solve now.
6. **Firestore native TTL is asynchronous ("eventual").** The server-side `410` check in `GET /public/output/{job_id}` covers the read path, but a determined actor with a still-live signed GCS URL from before expiry could still fetch the original document until the GCS lifecycle rule actually runs (also eventual, not instant-at-24h-mark). Residual exposure window is bounded (lifecycle rules typically run within a day of the age threshold) but not zero; acceptable for launch given data is inherently short-lived and self-uploaded.
7. **`backend/cloudbuild.yaml` structure unknown until this work starts** — whether to parameterize the existing pipeline or add a fully separate one is an implementation-time decision, not resolved here; both are viable, pick whichever keeps the two deploy configs easiest to keep in sync as the app evolves.
8. **Athena Health and preset datasets sharing any code paths with the shared pipeline** (`backend/services/care_plan_pipeline.py`, `backend/services/care_plan_input.py`) should be double-checked during implementation to ensure the public code path can't accidentally reach them (e.g., a default dataset lookup that isn't route-gated but is reachable via a shared service function called from `/public/jobs`).
9. **(v3 addition) WA MHMDA / CA CMIA consumer-health-data consent status** — see Section 9.1. Legal go/no-go blocker, not an engineering open question, but tracked here as a dependency the roadmap (Section 13) cannot fully proceed past without an answer.
10. **(v3 addition) FDA / SaMD classification for the direct-to-consumer flow** — see Section 9.1. Same status as above: legal go/no-go blocker.

---

## 13. Phased Implementation Roadmap

Sequencing below groups work by dependency; phases can overlap where no hard dependency exists (noted).

### Phase 0 — HIPAA blockers that gate everything else
Close P0-2 (revoke/remove committed SA keys), P0-3 (enable Cloud Audit Logs), and begin P1-7 (CORS tightening — can be done for internal now, public CORS config comes with Phase 3 per Section 8.7). **v3 addition**: also start the escalated P0-1 fix for the *existing* internal share-link path (Section 9) in this phase — it's a live gap today, independent of the rest of this project, and doesn't need to wait for the public deployment's own infrastructure. These are prerequisites to standing up any new internet-facing surface responsibly, independent of the public feature work itself. **Gate**: nothing internet-facing-new should ship until P0-2/P0-3 are done, and legal must be engaged on the MHMDA/CMIA and FDA/SaMD questions (Section 9.1) in parallel starting now, since counsel review timelines are typically the longest lead item in this roadmap.

### Phase 1 — Model splitting (backend)
Implement `to_public()` on `CarePlanV1_2`/`Grading`/`CarePlanInternal`, add `CarePlanV1_2Public`/`GradingPublic` (with the `combined_before`/`combined_after` fix, Section 5.2/5.3)/`CarePlanEnvelopePublic` per Section 5, plus the CI sync-guardrail test (Section 5.4). Also land the text-upload GCS-object addition (Section 6.1) and the job-lifecycle collection-threading fix (Section 8.6) here, since both touch the same persistence-layer surface. No new routes yet — this can be unit-tested against existing stored internal docs. **Gate**: this must exist before any `/public/*` endpoint can return anything.

### Phase 2 — Backend mode gating + public endpoints
`DEPLOYMENT_MODE` env var and blueprint filtering in `backend/app.py`/`backend/routes/__init__.py` (Section 8.1); mode-aware CORS (Section 8.7); new `backend/routes/public.py` with `/public/jobs`, `/public/jobs/{id}`, `/public/output/{id}` (with the unauthenticated-fallback bug fixed, Section 8.2), `/public/claim/{id}` (with idempotency + verified-token proof-of-ownership + GCS-original move, Section 6.2/6.3); new `public_care_plan_outputs` collection + `firestore.rules` updates; GCS prefix + lifecycle rule; dedicated public Cloud Tasks queue + worker SA (Section 3/11); anonymous-UID handling and the anonymous-rejecting decorator variant in `verify_firebase_token` (Section 8.4). **Gate**: depends on Phase 1 (needs `to_public()` to exist) and Phase 0 audit-logging groundwork (P1-2..5 for these new endpoints should be built in from the start here, not bolted on after). Rate limiting (Cloud Armor + per-UID quota, Section 9) should be stood up in this phase, not after — it's a launch gate now, not a fast-follow.

### Phase 3 — Frontend: anonymous flow + public build
`VITE_DEPLOYMENT_MODE` build-time constant and mode-gated/lazy imports per the corrected code-splitting scope (Section 4.2 — real effort M, not a trivial conditional import); the `isPublicBuild` flag introduced and threaded correctly, distinct from the existing `isPublicView` (Section 7.0), across `CarePlanJobResultView.tsx` and `CarePlanJobErrorView.tsx` (including the debug-leak fix, Section 7.4); Google Sign-In + anonymous auth + linking flows in `AuthContext.tsx`, including the 30-min-inactivity-timeout exemption for anonymous sessions (Section 7.1); public report page hitting `/public/output/{job_id}` instead of client Firestore; the persistent public header/nav (Section 7.2), landing orientation copy (Section 7.3), guest-expiry UX (Section 7.6), `ConfigurationCard`/grading-toggle exclusion (Section 7.5), mobile `SplitView` fix (Section 7.6), accessibility tap-target/font-size fixes (Section 7.8), and the copy/disclaimer additions (Section 7.7). Second Firebase Hosting target + build config. **Gate**: depends on Phase 2 (needs real public endpoints to call).

### Phase 4 — Observability & alerting
Log-based metrics, Cloud Monitoring dashboards, alert policies, notification channel, per-deployment labeling (Section 10), plus the new product-funnel analytics workstream via backend Markers (Section 10, item 6). Can start in parallel with Phase 3 once the public Cloud Run service from Phase 2 exists to instrument.

### Phase 4.5 — Internal / limited-beta checkpoint (v3 addition)
Before opening the public build to general traffic, run an internal or limited-beta (dogfood) period: a small set of real or synthetic non-clinician users exercise the full guest → result → claim flow on the actual public deployment, with Phase 4's dashboards live to observe it. This replaces v2's implicit big-bang "finish all phases then open to the world" sequencing with an explicit checkpoint to catch UX/operational issues (expiry timing, claim edge cases, mobile layout, error copy) against real usage before legal/compliance exposure scales with traffic volume.

### Phase 5 — Remaining HIPAA fast-follows + infra hardening
P1-8 (GCS versioning), final CORS lock-down verification for the public deployment specifically, Cloud Scheduler cleanup job for stale anonymous accounts (Section 6.1/11, if not already landed as part of the Phase 2 MVP-narrow path), GCS versioning. **v3 note**: P1-1 (log retention) is no longer independently deferrable for the public path — see Section 9's coupling to P1-2..5 — so it should land no later than Phase 2, not here. Some of this (Cloud Scheduler, CORS) should land no later than end of Phase 3 since they're operationally load-bearing for launch, not truly deferrable — treat "Phase 5" here as "must finish before flipping public traffic on," not "can wait indefinitely."

### Phase 6 — Launch readiness / go-live checklist
Verify all Section 9 launch-blocker gates are closed, **including confirmation from legal on both the MHMDA/CMIA consent question and the FDA/SaMD re-review (Section 9.1) — these are hard go/no-go items, not items the engineering team can check off unilaterally**; smoke test full guest flow (upload → result → show original → download PDF → Google sign-in → claim → appears in sidebar, with the GCS-original-move step verified, Section 6.2) for both new-account and existing-account linking paths; verify 24h expiry end-to-end (Firestore TTL + GCS lifecycle + 410 check); verify public backend 404s on all internal-only routes; verify public frontend bundle does not contain internal-only component code (bundle inspection, not just visual check — Section 4.2); confirm dashboards/alerts from Phase 4 are live and firing correctly on a synthetic error before opening real traffic; confirm the Phase 4.5 beta checkpoint surfaced no unresolved blockers.

---

## Decisions taken during review (overridable)

The five-lens review surfaced several places where the plan needed a specific default rather than an open-ended option. These defaults are recorded here so they're visible and easy to override with a deliberate decision later, rather than silently baked in:

- **Grading**: show both the pre-simplification and post-simplification combined scores (`combined_before` + `combined_after`), not a single "combined" score — partly because the v2 single-score design had a bug that returned the wrong one (Section 5.2/5.3), and partly because the before/after delta is itself part of the product's value story.
- **Claim flow**: claiming a guest job copies/moves the GCS original into the internal prefix as part of the same operation, rather than leaving it in the ephemeral public prefix subject to the 1-day lifecycle rule (Section 6.2).
- **Rate limiting**: promoted from an open question to a launch gate — Cloud Armor IP-based limiting plus a per-UID/day quota, both stood up in Phase 2, not after (Section 9).
- **Anonymous sessions**: exempted from the existing 30-minute inactivity auto-signout, rather than inheriting the internal build's clinician-session timeout unmodified (Section 7.1).
- **Analytics**: funnel/product metrics are implemented via the existing backend Markers framework, explicitly not Firebase Analytics (not BAA-covered) — Section 10.

**Legal go/no-go blockers requiring counsel (not engineering decisions):**

- **WA MHMDA / CA CMIA** — whether the public flow triggers "regulated entity" status and requires an explicit opt-in consent screen before any data collection (Section 9.1). Carries a private right of action; cannot be deferred as a fast-follow.
- **FDA / SaMD classification** — whether removing the clinician from the loop changes the product's device classification for the direct-to-consumer flow (Section 9.1).

Both must be resolved with a lawyer before Phase 6 (launch readiness) can be considered complete, regardless of engineering readiness.
