# PRD: Frontend Alignment to `care_plan`

Sub-project 5 of the Juno refactor. **Phase 2.** Depends on **SP1** (Pydantic models /
`CarePlanInternal` envelope shape — the inner-key decision) and **SP2** (route consolidation —
the `/care_plan*` HTTP paths the frontend now calls). Coordinates with **SP4** (observability —
`X-Session-Id` / `X-Trace-Id` response headers) and **SP6** (frontend tests for the components/pages
this sub-project changes).

## 1. Problem

The frontend still speaks "simplify" and still carries the obsolete v1 / v1.1 surface, even though the
backend is collapsing to a single `care_plan` route running only the v1.2 pipeline:

- **Obsolete version surface.** The app ships dedicated per-version pages
  (`pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`, `pages/v1_2/V1_2Page.tsx`), a generic
  `pages/simplify/SimplifyPage.tsx`, and a version chooser (`VersionsPage.tsx`,
  `VersionDetailPage.tsx`, `ConfigurationCard`'s version `<select>`, `config.ts`'s `VERSIONS` array).
  **Verified:** `V1Page`, `V1_1Page`, and `V1_2Page` are **dead code** — none of them is imported
  anywhere (`App.tsx` wires only `SimplifyPage`, which is a near-clone of `V1_2Page`). The
  `?version=…` bridge, `versionPath()`, and `outputRouteVersionId()` exist solely to route between
  these now-defunct pages. After SP2, `version=v1`/`v1-1` return `400`, so the chooser can offer
  values the backend rejects.

- **`simplify` naming everywhere.** The HTTP path constant (`SIMPLIFY_API_PATH = '/simplify'`),
  hard-coded `/simplify/*` strings in `api/datasets.ts`, `api/savedOutputs.ts`,
  `components/OutputGradingCard.tsx`, the route folder/component (`pages/simplify/SimplifyPage.tsx`),
  and `simplify`-flavoured TS module/symbol names (`types/simplify.ts`, `normalizeSimplifyOutput`,
  `SimplifyOutput`). SP2 has **renamed all backend paths** to `/care_plan*`; the frontend must follow
  or every request 404s after the backend deploys.

- **`appointment` naming.** The owner wants `appointment`/`AppointmentNote` → `care_plan` across the
  frontend (the same intent as backend `appointment_id → care_plan`):
  `components/AppointmentNoteV12View.tsx`, the `AppointmentNote` interface in `types/simplify.ts`, and
  the `import type { AppointmentNote }` in `types/envelope.ts`. The wire field `doc_type:
  "appointment_note"` **is also changed → `"care_plan"`** (resolved; SP1 owns the backend/LLM side, SP5
  updates the frontend literal in lockstep — see §4.6 and §9.4).

- **Correlation headers are wired but inert.** `utils/logger.ts` exposes `setSessionId()`, but
  **nothing ever calls it** (verified). The envelope already carries `metrics.session_id` (rendered as
  "Request ID"), but the frontend never reads the `X-Session-Id` response header, and SP4's
  `X-Trace-Id` is not consumed.

## 2. Goals

1. **Remove the obsolete version surface.** Delete the three dead per-version pages and the dynamic
   version chooser, but keep a static `VersionsPage` (owner extends it with future versions). After SP2
   there is exactly one pipeline (`v1-2`); the UI stops presenting version as a user *choice* (§4.2).
2. **Rename `simplify` → `care_plan`** across HTTP path strings, the path constant, the route
   folder/page/component name, and `simplify`-flavoured TS symbols — with a complete old→new map (§4).
3. **Consume the new envelope cleanly.** Keep the app working against `CarePlanInternal.to_dict()`.
   The inner key is **`care_plan`** — the single decided key (no `simplified_care_plan`, no alias). Read
   `output.care_plan` everywhere (§4.5).
4. **Rename `appointment`/`AppointmentNote` → `care_plan`** in frontend component/type names.
5. **Read correlation headers.** After each `/care_plan` response, read `X-Session-Id` (and
   `X-Trace-Id` if SP4 exposes it) and feed them to `logger.setSessionId()` / `logger`.
6. **Keep the app working end-to-end** with the refactored backend (full alignment — the owner's
   choice).

## 3. Non-Goals

- **Not** redesigning the care-plan rendering UI, the grading cards, or PDF/JSON export logic — only
  renaming/rewiring. `AppointmentNoteV12View`'s render output stays pixel-identical; we only rename
  the file/symbol and its prop/type imports.
- **Not** writing the test suite — SP6 owns Vitest/RTL. This PRD only flags which pages/components/
  utils need tests after the change (§7).
- **Not** changing the backend, the envelope wire-key *structure*, or the SSE event shapes — SP1/SP2
  own those. SP5 only *consumes* them. (The `doc_type` literal value `appointment_note → care_plan` is
  the one coordinated exception, owned by SP1 on the backend/LLM side; SP5 just matches the FE literal —
  §4.6.)
- **Not** building the `X-Trace-Id` plumbing on the backend — SP4 owns whether/how that header is
  emitted. SP5 reads it defensively if present.
- **Not** migrating Firestore documents or the saved-output legacy-shape handling
  (`normalizeOutput.ts` legacy branch stays as-is; it is still needed for old saved docs).

## 4. Architecture Decisions

### 4.1 Files to DELETE (dead code + obsolete surface)

| File | Why |
|---|---|
| `frontend/src/pages/v1/V1Page.tsx` | Dead — not imported anywhere; v1 pipeline dropped by SP2. |
| `frontend/src/pages/v1_1/V1_1Page.tsx` | Dead — not imported anywhere; v1.1 pipeline dropped by SP2. |
| `frontend/src/pages/v1_2/V1_2Page.tsx` | Dead — not imported anywhere; superseded by `SimplifyPage` (its near-identical, live twin). |

**Verification before deleting:** `grep -rn "V1Page\|V1_1Page\|V1_2Page" frontend/src` returns only
self-references plus the CSS import (`V1_1Page.css`, handled in §4.3). Confirmed at planning time.

### 4.2 Version-chooser decision (RESOLVED — see §9.2)

Only `v1-2` survives. **Owner decision: DELETE the dynamic version chooser, but KEEP a static
`VersionsPage`.** The owner will add more pipeline versions later (next is e.g. `V1_3`), so the page
must be structured for trivial extension — a static, hand-maintained list that grows by appending an
entry. Keep exactly as much scaffolding as that requires; no dynamic selection logic.

- `config.ts`: reduce `VERSION_IDS` / `VERSIONS` to the single `v1-2` entry; keep
  `DEFAULT_VERSION = 'v1-2'` as the constant the submit form sends. The `version` form field is still
  sent (value always `'v1-2'`) so the backend contract is unchanged and SP2's
  `ALLOWED_VERSIONS = {"v1-2"}` accepts it. `VERSIONS` stays as a small static array — this is the
  list `VersionsPage` renders and the owner extends when V1_3 lands (append a second entry).
- `ConfigurationCard.tsx`: **remove the version `<select>`** (a one-option dropdown is dead UX); keep
  the "Enable grading" checkbox. **Drop** the `version` / `onVersionChange` props entirely (nothing is
  in production — no need to keep no-op props; the page sends `DEFAULT_VERSION` directly).
- `VersionsPage.tsx`: **KEEP** as a static "How it works / versions" page that maps over
  `config.ts`'s `VERSIONS` array. No dynamic chooser, no per-version pipeline routing — just a
  read-only list. Keep the `/versions` route in `App.tsx` and the "Versions" link in `NavBar.tsx`.
  Structure so adding V1_3 is a one-line append to `VERSIONS`.
- `VersionDetailPage.tsx` + the `/version/:id` route: **DELETE** — the per-version *detail/chooser*
  routing describes the dynamic chooser the owner is removing. (If a per-version detail view is wanted
  later, the owner re-adds it alongside V1_3; not built now.)
- `router.tsx` (`versionPath`, `VersionRouteState`) + `utils/outputVersion.ts`
  (`outputRouteVersionId`): `versionPath` and `outputRouteVersionId` exist only to route *between*
  the deleted dynamic version pages.
  - **Keep:** `VersionRouteState` (still used by `CarePlanPage` for the saved/split-view → result
    hand-off).
  - **Delete:** `versionPath()` (and its `router.test.ts`) and `utils/outputVersion.ts` +
    `outputVersion` usages — all callers are the deleted dynamic pages. Verified: after deleting
    `V1*Page` and `VersionDetailPage`, `grep versionPath`/`outputRouteVersionId` returns no live
    references.

### 4.3 `V1_1Page.css` (shared stylesheet — must be preserved)

`pages/v1_1/V1_1Page.css` is imported by the **live** `SimplifyPage.tsx` (and the dead v1_2 page). It
holds the result-card / score / upload styles the app actually renders. Deleting `pages/v1_1/`
wholesale would break styling. **Move/rename** it to `pages/care-plan/CarePlanPage.css` and update the
import in the renamed page (§4.4). Do not delete it.

### 4.4 Rename `simplify` → `care_plan` (and the route page)

The live page `pages/simplify/SimplifyPage.tsx` becomes `pages/care-plan/CarePlanPage.tsx`
(component `CarePlanPage`). Update `App.tsx`'s import + JSX. The route path stays `/` (this is the
app's single working surface).

#### Complete old → new rename map

**HTTP path strings & constant** (backend contract from SP2 — mandatory):

| Location | Old | New |
|---|---|---|
| `config.ts` const name | `SIMPLIFY_API_PATH` | `CARE_PLAN_API_PATH` |
| `config.ts` const value | `'/simplify'` | `'/care_plan'` |
| `api/datasets.ts` | `GET /simplify/datasets` | `GET /care_plan/datasets` |
| `api/datasets.ts` | `GET /simplify/datasets/<g>/<i>/<f>` | `GET /care_plan/datasets/<g>/<i>/<f>` |
| `api/datasets.ts` | `POST /simplify/batch` | `POST /care_plan/batch` |
| `api/savedOutputs.ts` | `GET /simplify/saved` | `GET /care_plan/saved` |
| `api/savedOutputs.ts` | `GET /simplify/saved/<id>` | `GET /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `PATCH /simplify/saved/<id>` | `PATCH /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `DELETE /simplify/saved/<id>` | `DELETE /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `GET /simplify/saved/<id>/input-pdf-url` | `GET /care_plan/saved/<id>/input-pdf-url` |
| `components/OutputGradingCard.tsx` | `POST ${API_URL}/simplify/grade` | `POST ${API_URL}/care_plan/grade` |
| (live page) form submit | `POST ${API_URL}${SIMPLIFY_API_PATH}` | `POST ${API_URL}${CARE_PLAN_API_PATH}` |

**TS files / symbols** (frontend-internal naming — SP2 §6 says these are SP5's call):

| Kind | Old | New |
|---|---|---|
| Route folder + page file | `pages/simplify/SimplifyPage.tsx` | `pages/care-plan/CarePlanPage.tsx` |
| Page component | `SimplifyPage` | `CarePlanPage` |
| Shared CSS | `pages/v1_1/V1_1Page.css` | `pages/care-plan/CarePlanPage.css` |
| Type module | `types/simplify.ts` | `types/carePlan.ts` |
| Normalizer fn | `normalizeSimplifyOutput` | `normalizeCarePlanOutput` |
| Normalizer file | `utils/normalizeOutput.ts` | `utils/normalizeOutput.ts` (keep file name; rename fn) |
| Envelope type | `SimplifyOutput` | `CarePlanInternal` (HARD RENAME — **no** deprecated alias; nothing is in production) |
| Component file | `components/AppointmentNoteV12View.tsx` | `components/CarePlanView.tsx` |
| Component symbol | `AppointmentNoteV12View` | `CarePlanView` |
| Interface | `AppointmentNote` (in `types/simplify.ts`) | `CarePlanContent` (in `types/carePlan.ts`) |

**UI copy** (RESOLVED — owner approves rewording; see §8.5/§9.5): reword user-facing strings to
"care plan" framing: "Simplify My Note →" → "Create My Care Plan →", "Your Simplified Note" →
"Your Care Plan", "Simplify another note" → "Create another care plan", "Simplifying your note…" →
"Creating your care plan…", and the `<title>` / download filename `simplified-document.json` →
`care-plan.json`. See §8.5 for the full copy map.

> **Renames are mechanical but wide.** Do them with a symbol-rename refactor (or careful
> find-replace + `tsc --noEmit`) so every import site updates. After deleting the dead pages (§4.1)
> the only live consumers are `App.tsx`, the renamed page, `OutputGradingCard.tsx`, `SplitView`
> (receives the rendered view as a child), and the `api/*` modules.

### 4.5 Envelope consumption — single decided inner key `care_plan` (RESOLVED, no ambiguity)

**Owner decision (RESOLVED — see §9.1): there is NO inner-key ambiguity and NO alias.** The single
decided inner key is **`care_plan`** ("care_plan everywhere"). FE and BE deploy in lockstep; nothing
is in production, so there is no `simplified_care_plan` legacy key to support and no dual-accept
aliasing to mirror. SP1/SP2 emit `care_plan`; SP5 reads `care_plan`.

**What the envelope is:**
- The envelope type is `CarePlanInternal`. JSON wire keys: `{ metrics, input, grading, care_plan }`.
- The inner care-plan key is **`care_plan`** — the only key. No `simplified_care_plan` reads, writes,
  or fallbacks anywhere in the frontend.

**Decision — internal field is `care_plan`.** The TS `CarePlanInternal` type carries
`care_plan: SimplifiedCarePlan`. All consumers (`CarePlanView`, `buildPdfHtml`, `OutputGradingCard`,
`CarePlanPage`) read `output.care_plan`. `normalizeCarePlanOutput` (formerly `normalizeSimplifyOutput`)
returns the envelope with the inner field named `care_plan`:

```ts
// utils/normalizeOutput.ts
export function normalizeCarePlanOutput(raw: any): CarePlanInternal {
  if (raw == null) throw new Error('normalizeCarePlanOutput: null/undefined output');
  if ('care_plan' in raw) {
    return { ...raw, care_plan: raw.care_plan };
  }
  // ...existing legacy flat-shape branch unchanged (old saved Firestore docs)...
}
```

The **legacy flat-shape branch stays** only for old *saved Firestore documents* (per §3 Non-Goals) —
that is a pre-existing saved-output concern, not the live envelope key. The live envelope key is
`care_plan`, full stop.

> **No `simplified_care_plan` anywhere.** Do not add a `simplified_care_plan` alias, fallback, or
> deprecated re-export. The earlier "keep `simplified_care_plan` for one phase / read key-agnostically"
> plan is **withdrawn** by owner decision.

**`metrics.session_id`** is unchanged and already read (rendered as "Request ID"); keep it.

### 4.6 `appointment` → `care_plan`

- `components/AppointmentNoteV12View.tsx` → `components/CarePlanView.tsx`, symbol
  `AppointmentNoteV12View` → `CarePlanView`. Update both call sites (the live page renders it twice —
  inline result + inside `SplitView`).
- `types/simplify.ts`'s `AppointmentNote` interface → `CarePlanContent` in `types/carePlan.ts`. Update
  `types/envelope.ts`'s `import type { AppointmentNote }` accordingly. The derived
  `SimplifiedCarePlan = Omit<CarePlanContent,'version'> & { version: string }` keeps its name (it is
  already "care plan"-named and is the inner type of the `care_plan` field).
- **CHANGE `doc_type: 'appointment_note'` → `doc_type: 'care_plan'`** (RESOLVED — see §9.4). The owner's
  "appointment → care_plan everywhere" intent **does** apply to this wire literal; it is NOT left
  unchanged. SP1 owns the backend `CarePlan` model + LLM-prompt side of this change; SP5 updates the
  frontend type literal to `'care_plan'` to match. Coordinate so the FE literal and the SP1 model agree
  (lockstep — nothing in production).

### 4.7 Correlation headers (`X-Session-Id` / `X-Trace-Id`)

The SSE responses go through `authenticatedFetch`. After the streaming `POST /care_plan` (and
`/care_plan/batch`, `/care_plan/grade`) responses arrive, read the headers off the `Response` object
and hand them to the logger:

```ts
const sessionId = response.headers.get('X-Session-Id');
if (sessionId) logger.setSessionId(sessionId);
const traceId = response.headers.get('X-Trace-Id');   // SP4 — may be absent
if (traceId) logger.info('trace_id', { traceId });
```

Place this in the renamed page right after each `authenticatedFetch(...)` returns and `response.ok` is
confirmed, before reading the body stream. `setSessionId` is currently never called — this is the
fix. Prefer the **header** value; fall back to the envelope's `metrics.session_id` for the
"Request ID" display (the header is the correlation source of truth; the body value is the display
value, and they should match).

> **CORS (RESOLVED — §8.2).** `X-Session-Id` / `X-Trace-Id` are non-simple headers; the browser only
> exposes them to JS if the backend sends `Access-Control-Expose-Headers: X-Session-Id, X-Trace-Id`.
> **Owner decision: the backend WILL expose these headers** (SP4/SP2 CORS config; active `fixing-cors`
> branch). SP5 still reads defensively — if a header is absent, `response.headers.get(...)` returns
> `null` and the frontend falls back to the body `session_id` (no crash) — but the expected state is
> headers present.

### 4.8 Router / Nav changes (summary)

- `App.tsx`: import `CarePlanPage` (was `SimplifyPage`); **keep** the `/versions` route (static
  `VersionsPage`); **remove** the `/version/:id` route and the `VersionDetailPage` import (§4.2).
- `NavBar.tsx`: **keep** the "Versions" `<Link to="/versions">` (static page survives).
- `router.tsx`: keep `VersionRouteState`; remove `versionPath` (+ delete `router.test.ts` or replace
  with a SP6 test for whatever helper remains). `utils/outputVersion.ts` deleted.

## 5. API Change Summary

The frontend now calls only the `/care_plan*` surface (SP2 contract). No request/response **body**
changes — bodies and SSE event shapes are byte-identical; only **path strings** change, plus the new
**header reads**.

| Frontend caller | Method + new path |
|---|---|
| `CarePlanPage` submit | `POST /care_plan` (multipart: `files[]`/`file`/`text`, `version`=`v1-2`, `grading_enabled`) → SSE, final `data` = `CarePlanInternal.to_dict()` |
| `api/datasets.ts` `runBatch` | `POST /care_plan/batch` (JSON `{version, selections, grading_enabled}`) → SSE |
| `api/datasets.ts` `listDatasets` | `GET /care_plan/datasets` |
| `api/datasets.ts` `getDatasetFileContent` | `GET /care_plan/datasets/<g>/<i>/<f>` |
| `api/savedOutputs.ts` list/get/rename/delete/pdf-url | `GET/PATCH/DELETE /care_plan/saved[/<id>][/input-pdf-url]` |
| `components/OutputGradingCard.tsx` | `POST /care_plan/grade` (JSON `{saved_id}` or `{text, clarified_text}`) → `{ grading }` |

**Headers read (new):** `X-Session-Id` (correlation; → `logger.setSessionId`), `X-Trace-Id`
(SP4, optional; → `logger`). Both depend on backend `Access-Control-Expose-Headers` (§8).

## 6. Frontend Change Summary (file-by-file plan)

**DELETE**
- `pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`, `pages/v1_2/V1_2Page.tsx` (dead).
- `utils/outputVersion.ts` (only the dead pages used `outputRouteVersionId`).
- `router.test.ts` (tests the soon-deleted `versionPath`; SP6 replaces).
- `pages/VersionDetailPage.tsx` (dynamic per-version chooser routing — removed per §4.2).
- **KEEP** `pages/VersionsPage.tsx` (static "versions / how it works" page — owner extends with V1_3).

**MOVE / RENAME**
- `pages/v1_1/V1_1Page.css` → `pages/care-plan/CarePlanPage.css` (live styles; keep contents).
- `pages/simplify/SimplifyPage.tsx` → `pages/care-plan/CarePlanPage.tsx`, component `CarePlanPage`;
  update its CSS import to the moved file.
- `components/AppointmentNoteV12View.tsx` → `components/CarePlanView.tsx` (symbol `CarePlanView`).
- `types/simplify.ts` → `types/carePlan.ts`; interface `AppointmentNote` → `CarePlanContent`.
- `normalizeSimplifyOutput` → `normalizeCarePlanOutput` (file stays `utils/normalizeOutput.ts`).
- `SimplifyOutput` type → `CarePlanInternal` (HARD RENAME — no re-export alias).

**EDIT**
- `config.ts`: rename `SIMPLIFY_API_PATH` → `CARE_PLAN_API_PATH = '/care_plan'`; collapse `VERSION_IDS`
  to the single `v1-2` entry; keep `DEFAULT_VERSION='v1-2'`; **keep `VERSIONS` as a static array**
  (single `v1-2` entry now; `VersionsPage` renders it and the owner appends V1_3 later — §4.2).
  **Remove `VITE_DEFAULT_VERSION` usage** — the owner is removing the env var; `DEFAULT_VERSION`
  becomes a plain `'v1-2'` constant (record this config change in the implementation `code.md` — §8.3).
- `App.tsx`: import/render `CarePlanPage`; keep `/versions` route; remove `/version/:id` route +
  `VersionDetailPage` import (§4.2/§4.8).
- `NavBar.tsx`: **keep** the "Versions" link (static page survives).
- `ConfigurationCard.tsx`: remove the version `<select>` + `VERSIONS` import; keep grading checkbox;
  **drop** the `version`/`onVersionChange` props entirely (§4.2).
- `api/datasets.ts`, `api/savedOutputs.ts`, `components/OutputGradingCard.tsx`: swap `/simplify*` →
  `/care_plan*` path strings (and use `CARE_PLAN_API_PATH` where a const fits).
- `utils/normalizeOutput.ts`: rename fn; resolve the inner key as **`care_plan`** (the single decided
  key — §4.5); keep the legacy flat-shape branch for old saved Firestore docs.
- `utils/grading.ts`, `utils/buildPdfHtml.ts`: update type imports (`AppointmentNote`→`CarePlanContent`,
  `types/simplify`→`types/carePlan`, `SimplifyOutput`→`CarePlanInternal`) and any
  `output.simplified_care_plan` reads → `output.care_plan`; no logic change.
- `CarePlanPage.tsx` (renamed): use `CARE_PLAN_API_PATH`; render `CarePlanView`; call
  `normalizeCarePlanOutput`; read `output.care_plan`; **add the `X-Session-Id`/`X-Trace-Id` header
  reads** after each fetch; remove the now-defunct `?version=` mount effect + version-selection wiring
  (send `DEFAULT_VERSION` constant); **reword UI copy per §8.5**.
- `types/envelope.ts`: rename `SimplifyOutput`→`CarePlanInternal` (no alias); update the
  `AppointmentNote`→`CarePlanContent` import; inner field is `care_plan: SimplifiedCarePlan` (§4.5).

**UNCHANGED (no edits)**
- `Sidebar.tsx`, `SplitView.tsx`, `PresetDataCard.tsx`, `DatasetGroupRow.tsx`, `MedicalTerm.tsx`,
  `LoginPage.tsx`, `auth/*`, `api/firebase.ts`, `api/apiClient.ts`, `utils/logger.ts`,
  `utils/groupSavedOutputs.ts`, `types/datasets.ts`. (They reference renamed symbols only through the
  page/types, which the rename updates — no hand edits.) `apiClient.ts` does **not** need changes for
  headers; the page reads them off the returned `Response`.

## 7. Testing (handed to SP6)

After this sub-project, SP6 should add/adjust:

- `utils/normalizeOutput.test.ts` — **extend**: assert the envelope with the `care_plan` inner key and
  the legacy flat shape both normalize to an envelope with a populated `care_plan` field. (No
  `simplified_care_plan` case — that key no longer exists.) The existing legacy-grading test stays.
- `utils/grading.ts` — `patientScoreFromGrading` / `methodEntriesFromGrading` selectors (empty
  entries → `null`; combined+method extraction; before/after split).
- `components/CarePlanView.tsx` (RTL) — renders summary/sections; readability + method cards appear
  only when grading entries exist; medical-term highlighting.
- `components/OutputGradingCard.tsx` (RTL) — POSTs to `/care_plan/grade`; `saved_id` vs
  `text/clarified_text` body selection; `onGraded` updates.
- `pages/care-plan/CarePlanPage.tsx` (RTL/integration) — SSE parse → result render; **reads
  `X-Session-Id` and calls `logger.setSessionId`**; sends `grading_enabled`.
- `ConfigurationCard.tsx` — grading checkbox toggles (version select + props removed).
- `pages/VersionsPage.tsx` (RTL) — renders one row per `VERSIONS` entry (static list; trivially grows
  when V1_3 is appended).
- **Delete/replace** `router.test.ts` (its `versionPath` subject is removed).

## 8. Manual Intervention Required From You

1. **Lockstep deploy (RESOLVED — yes, hard cut).** FE + BE deploy **together**. Once the backend serves
   `/care_plan*` only, the old frontend 404s, and once this frontend ships, an old backend 404s. **No
   `/simplify*` aliases are kept** — nothing is in production, breaking changes are fine. Deploy SP2
   (and SP1) with this frontend in the same release window. You own release ordering.
2. **`Access-Control-Expose-Headers` for `X-Session-Id` / `X-Trace-Id` (RESOLVED — YES, expose them).**
   The browser will not expose these response headers to JS unless the backend sends them in
   `Access-Control-Expose-Headers`. **Owner decision: expose the session/trace headers** (e.g.
   `Access-Control-Expose-Headers: X-Session-Id, X-Trace-Id`). This is backend/SP4/SP2 CORS config
   (note the active `fixing-cors` branch); confirm it lists both headers so Task 8's reads work.
3. **`VITE_DEFAULT_VERSION` env var (RESOLVED — owner WILL remove it).** `config.ts` currently reads it;
   with a single version it is dead. **The owner is removing the env var.** `DEFAULT_VERSION` becomes a
   plain `'v1-2'` constant in `config.ts` (no `import.meta.env.VITE_DEFAULT_VERSION`). **This
   removal/config change MUST be recorded in the `code.md` run-summary produced at implementation
   (dev-code) time** — note the env-var deletion and any `.env*` cleanup there.
4. **No Firebase / `VITE_*` / deployed-URL changes** beyond §8.3 are needed by SP5 (`api/firebase.ts`,
   `VITE_API_PROCESSING_URL` unchanged — leave them).
5. **UI copy review (RESOLVED — reword approved).** The owner approves rewording user-facing
   "simplify"/"note" strings to "care plan". See §8.5 for the copy map; apply it (not optional).

### 8.5 UI copy map (RESOLVED — apply)

Reword the user-facing strings in `CarePlanPage.tsx` (and the `<title>` / download filename):

| Location | Old copy | New copy |
|---|---|---|
| Submit CTA | "Simplify My Note →" | "Create My Care Plan →" |
| Result heading | "Your Simplified Note" | "Your Care Plan" |
| Reset / new action | "Simplify another note" | "Create another care plan" |
| In-progress status | "Simplifying your note…" | "Creating your care plan…" |
| Document `<title>` | (current "simplify"-framed title) | "Juno — Care Plan" |
| JSON download filename | `simplified-document.json` | `care-plan.json` |

Keep any other surrounding copy that is already neutral. No behavioral change — strings only.

## 9. Open Questions & Decisions

1. **Inner envelope key (the headline ambiguity).**
   **[RESOLVED: No ambiguity and no alias. The single decided inner key is `care_plan` ("care_plan
   everywhere"). FE + BE deploy in lockstep; nothing is in production, so there is no
   `simplified_care_plan` legacy wire key and no dual-accept aliasing to mirror. The earlier
   "key-agnostic normalizer / Option A vs Option B / keep `simplified_care_plan` for a phase" plan is
   withdrawn. SP5 reads `output.care_plan` everywhere; the normalizer's legacy flat-shape branch stays
   only for old *saved Firestore docs* (§3 Non-Goal), not the live envelope. See §4.5.]**
2. **Version chooser fate (§4.2).**
   **[RESOLVED: DELETE the dynamic version chooser (the `<select>`, `VersionDetailPage`, `/version/:id`
   route, `versionPath`, `outputVersion`). KEEP a static `VersionsPage` (route `/versions` + NavBar
   link) that renders the static `VERSIONS` array. The owner will add more versions later (next:
   V1_3); structure `VERSIONS` and the page so adding a version is a one-line append. Keep exactly as
   much scaffolding as that requires — no dynamic selection logic. See §4.2/§4.8.]**
3. **`SimplifyOutput` / `SimplifyPage` aliases — keep for a cycle or hard rename now?**
   **[RESOLVED: HARD RENAME NOW. No deprecated aliases or re-exports. `SimplifyOutput` →
   `CarePlanInternal`, `SimplifyPage` → `CarePlanPage`, etc., fully removed. Nothing is in production;
   breaking changes are fine. See §4.4.]**
4. **`doc_type: 'appointment_note'`.**
   **[RESOLVED: CHANGE it to `'care_plan'` everywhere — it is NOT left unchanged. The owner's
   "appointment → care_plan everywhere" intent applies to this wire literal too. SP1 owns the backend
   `CarePlan` model + LLM-prompt side; SP5 updates the frontend type literal to `'care_plan'` to match,
   coordinated in lockstep. See §4.6.]**
5. **UI copy (§8.5) — reword or keep?**
   **[RESOLVED: REWORD. The owner approves rewording user-facing "simplify"/"note" strings to "care
   plan". Apply the copy map in §8.5 (not optional).]**

### Recorded for implementation (`code.md`)
- **`VITE_DEFAULT_VERSION` removal (§8.3).** The owner is removing this env var; `DEFAULT_VERSION`
  becomes a plain `'v1-2'` constant. The env-var deletion and any `.env*` cleanup MUST be recorded in
  the `code.md` run-summary produced at dev-code (implementation) time.
