# Tasks: Frontend Alignment to `care_plan`

Read `PRD.md` in this folder first. This sub-project is **PLANNING-followable** for a junior dev:
each task lists exact files, exact changes, and acceptance criteria. Do tasks in order — later tasks
assume earlier renames landed. After each task, run `npm run build` (or `tsc --noEmit`) in
`frontend/` and fix any import breakage before moving on.

All paths are under `frontend/src/` unless stated.

Depends on: **SP1** (CarePlanInternal envelope, inner-key aliasing), **SP2** (`/care_plan*` paths).
**Do not start until SP1 + SP2 have landed** (or are landing in the same release window). The header
work (Task 8) also depends on **SP4** for `X-Trace-Id` and on CORS `Access-Control-Expose-Headers`.

---

### Task 1 — Delete the dead per-version pages

**Delete:**
- `pages/v1/V1Page.tsx`
- `pages/v1_1/V1_1Page.tsx`
- `pages/v1_2/V1_2Page.tsx`

**First** verify they're dead: `grep -rn "V1Page\|V1_1Page\|V1_2Page" src` should show only
self-references plus the `V1_1Page.css` import lines. (Confirmed at planning time — `App.tsx` wires
only `SimplifyPage`.)

**Do NOT yet delete** `pages/v1_1/V1_1Page.css` — it's imported by the live page (Task 3 moves it).

**Acceptance:** files gone; `npm run build` fails only with errors pointing at the still-present
`V1_1Page.css` import in `SimplifyPage.tsx` (fixed in Task 3) — no other references to the deleted
pages remain.

---

### Task 2 — Delete obsolete version-routing helpers

**Delete:**
- `utils/outputVersion.ts` (its only callers were the Task 1 pages).
- `router.test.ts` (tests `versionPath`, removed in this task; SP6 will add replacements).

**Edit `router.tsx`:** remove `versionPath()` and its `VERSIONS` import. **Keep**
`VersionRouteState` (still used by the live page for the result hand-off).

```ts
// router.tsx — after
import type { SimplifyOutput } from './types/envelope';   // becomes CarePlanInternal in Task 6
export interface VersionRouteState {
  output?: SimplifyOutput;
}
```

**Acceptance:** `grep -rn "versionPath\|outputRouteVersionId" src` returns nothing. `router.tsx`
exports only `VersionRouteState`.

---

### Task 3 — Move the shared CSS and rename the live page

1. **Move** `pages/v1_1/V1_1Page.css` → `pages/care-plan/CarePlanPage.css` (contents unchanged).
2. **Move/rename** `pages/simplify/SimplifyPage.tsx` → `pages/care-plan/CarePlanPage.tsx`.
3. In the moved page:
   - First import line: `import './CarePlanPage.css';` (was `import '../v1_1/V1_1Page.css';`).
   - Rename the default export `export default function SimplifyPage()` →
     `export default function CarePlanPage()`.
   - Remove the now-dead `?version=` mount effect (the `useEffect` reading `params.get('version')` /
     `setSelectedVersion`) — single version now. Keep the **other** `useEffect` that reads
     `location.state.output` (the saved/split-view hand-off).
   - `selectedVersion` state: replace with a constant. Either keep `const selectedVersion = 'v1-2'`
     (still appended to the form as `version`) and delete `setSelectedVersion`/`handleVersionChange`,
     or import `DEFAULT_VERSION` from config. The `version` form field MUST still be sent (SP2 accepts
     `v1-2`).
4. Now the directory `pages/v1_1/` and `pages/simplify/` are empty — remove them.

**Edit `App.tsx`:**
```ts
import CarePlanPage from './pages/care-plan/CarePlanPage';   // was SimplifyPage
// ...
<Route path="/" element={<CarePlanPage />} />
```

**Acceptance:** app builds; `/` renders the care-plan page; no `V1_1Page.css` or `pages/simplify`
references remain. The version `<select>` is still present for now (removed in Task 4).

---

### Task 4 — Remove the version chooser UI (depends on §9.2 owner decision)

**Default (recommended) — remove the chooser:**

1. **`config.ts`:** collapse to one version.
   ```ts
   const FALLBACK_VERSION = 'v1-2';
   const VERSION_IDS = ['v1-2'] as const;
   export const CARE_PLAN_API_PATH = '/care_plan';   // renamed from SIMPLIFY_API_PATH (Task 5)
   export const DEFAULT_VERSION = VERSION_IDS.includes(import.meta.env.VITE_DEFAULT_VERSION)
     ? import.meta.env.VITE_DEFAULT_VERSION : FALLBACK_VERSION;
   export const VERSIONS = [
     { id: 'v1-2', label: 'Version 1.2', description: '…(keep current v1-2 text)…',
       steps: ['Read input','Find medical terms','Simplify','Clarify care details','Structure note'],
       isDefault: true },
   ] as const;
   ```
2. **`components/ConfigurationCard.tsx`:** remove the `Version` `<label>` + `<select>` and the
   `VERSIONS` import; keep the "Enable grading" checkbox. Drop the `version` / `onVersionChange` props
   from `ConfigurationCardProps` and the JSX that used them.
3. **Update the page's** `<ConfigurationCard .../>` usage to pass only `gradingEnabled` /
   `onGradingEnabledChange`.
4. **`App.tsx`:** remove the `/versions` and `/version/:id` routes and the `VersionsPage` /
   `VersionDetailPage` imports.
5. **Delete** `pages/VersionsPage.tsx` and `pages/VersionDetailPage.tsx`.
6. **`components/NavBar.tsx`:** remove the `<Link to="/versions">Versions</Link>`.

**Alternative (if owner keeps a "How it works" page):** keep `VersionsPage.tsx` + its route + the
NavBar link, but still remove the `ConfigurationCard` `<select>` and collapse `config.ts` to one
version. Skip steps 4–6.

**Acceptance:** upload screen shows the grading checkbox and no version dropdown; no route or link
points to a removed page; `grep -rn "VersionsPage\|VersionDetailPage" src` is empty (default path).

---

### Task 5 — Swap `/simplify*` HTTP paths → `/care_plan*`

Apply the §4.4 path table. Mechanical string edits; no logic change.

1. **`config.ts`:** `SIMPLIFY_API_PATH` → `CARE_PLAN_API_PATH`, value `'/simplify'` → `'/care_plan'`
   (done in Task 4 step 1 if you took the default; otherwise do it here).
2. **`api/datasets.ts`:** `/simplify/datasets` → `/care_plan/datasets`;
   `/simplify/datasets/${…}` → `/care_plan/datasets/${…}`; `/simplify/batch` → `/care_plan/batch`.
3. **`api/savedOutputs.ts`:** all five `/simplify/saved…` → `/care_plan/saved…`.
4. **`components/OutputGradingCard.tsx`:** `${API_URL}/simplify/grade` → `${API_URL}/care_plan/grade`.
5. **`CarePlanPage.tsx`:** the submit fetch already uses the path constant — ensure it imports
   `CARE_PLAN_API_PATH` (renamed) and uses `${API_URL}${CARE_PLAN_API_PATH}`.

**Acceptance:** `grep -rn "/simplify" src` returns **zero** matches. App can complete a full
upload→result flow, grade re-run, saved list/open/rename/delete, dataset list/preview, and batch run
against the SP2 backend.

---

### Task 6 — Rename `SimplifyOutput` → `CarePlanInternal` + key-agnostic normalizer

1. **`types/envelope.ts`:**
   - Rename `export interface SimplifyOutput` → `export interface CarePlanInternal`.
   - Add a deprecated alias for one cycle: `export type SimplifyOutput = CarePlanInternal;`
   - Keep the inner field `simplified_care_plan: SimplifiedCarePlan` (Phase 1 wire key — PRD §4.5
     Option A).
2. **`utils/normalizeOutput.ts`:**
   - Rename `normalizeSimplifyOutput` → `normalizeCarePlanOutput`.
   - Add key-agnostic resolution of the inner care plan (handles `simplified_care_plan` OR `care_plan`
     OR legacy flat shape), normalizing to the internal `simplified_care_plan` field:
     ```ts
     export function normalizeCarePlanOutput(raw: any): CarePlanInternal {
       if (raw == null) throw new Error('normalizeCarePlanOutput: null/undefined output');
       const hasEnvelope = 'simplified_care_plan' in raw || 'care_plan' in raw;
       if (hasEnvelope) {
         const plan = ('simplified_care_plan' in raw) ? raw.simplified_care_plan : raw.care_plan;
         return { ...raw, simplified_care_plan: plan };
       }
       // ...existing legacy flat-shape branch, unchanged (still returns grading:{entries:[],…})...
     }
     ```
   - `isLegacyShape` stays but its check should reflect "neither envelope key present":
     `return !('simplified_care_plan' in data) && !('care_plan' in data);`
3. Update all call sites of the old names:
   - `normalizeSimplifyOutput` → `normalizeCarePlanOutput` (live page, plus `normalizeOutput.test.ts`
     left for SP6).
   - `SimplifyOutput` type imports → `CarePlanInternal` in: `CarePlanPage.tsx`, `router.tsx`,
     `OutputGradingCard.tsx`, `utils/outputVersion.ts` (deleted), and `types/envelope.ts` self.

**Acceptance:** `tsc --noEmit` passes. Feeding the normalizer a fixture with `care_plan` as the inner
key produces an envelope whose `simplified_care_plan` is populated; same for the legacy flat shape and
the current `simplified_care_plan` key.

---

### Task 7 — Rename `AppointmentNote*` → `CarePlan*`

1. **Rename file** `types/simplify.ts` → `types/carePlan.ts`.
2. In it, rename interface `AppointmentNote` → `CarePlanContent`. Leave the field
   `doc_type: 'appointment_note'` and its literal value **unchanged** (SP1-owned wire value).
3. **Rename file** `components/AppointmentNoteV12View.tsx` → `components/CarePlanView.tsx`; rename the
   default export `AppointmentNoteV12View` → `CarePlanView`.
4. Update imports across the codebase:
   - `types/envelope.ts`: `import type { AppointmentNote } from './simplify'` →
     `import type { CarePlanContent } from './carePlan'`; update
     `SimplifiedCarePlan = Omit<CarePlanContent,'version'> & {version:string}`.
   - `utils/grading.ts`, `utils/buildPdfHtml.ts`, `CarePlanView.tsx` (self): change
     `from '../types/simplify'` → `from '../types/carePlan'`, and any `PatientScore`/`TermsMap`/
     `PatientScoreDimension`/`AppointmentNote` imports follow the moved file.
   - `CarePlanPage.tsx`: import `CarePlanView` (was `AppointmentNoteV12View`); update the **two** JSX
     usages (inline result + the `SplitView simplifiedContent={<CarePlanView .../>}`).
   - `types/simplify` import in `CarePlanPage.tsx` (`AppState, InputMode, PipelineStep, StepStatus`)
     → `types/carePlan`.

**Acceptance:** `grep -rn "AppointmentNoteV12View\|from '.*types/simplify'\|types/simplify" src`
returns nothing; `grep -rn "doc_type: 'appointment_note'\|appointment_note" src` still shows the wire
literal (intentionally kept). App renders the care plan identically (no visual diff).

---

### Task 8 — Read correlation headers (`X-Session-Id` / `X-Trace-Id`)

In `CarePlanPage.tsx`, after **each** `authenticatedFetch(...)` returns and `response.ok` is
confirmed (the single-run `POST /care_plan` path and the batch path), before consuming the stream:

```ts
import { logger } from '../../utils/logger';
// ...after `if (!response.ok) {…throw…}`:
const sessionId = response.headers.get('X-Session-Id');
if (sessionId) logger.setSessionId(sessionId);
const traceId = response.headers.get('X-Trace-Id');   // SP4; may be null
if (traceId) logger.info('care_plan_request', { traceId });
```

Also apply to `OutputGradingCard.tsx`'s `/care_plan/grade` fetch (read `X-Session-Id` after `res.ok`).

For the "Request ID" display in the result view: keep using `result.metrics.session_id` as the
display value (it should equal the header).

**Acceptance:** when the backend sends `X-Session-Id` (and `Access-Control-Expose-Headers` lists it),
`logger.setSessionId` is called with that value (verify via a console/log in dev, or an SP6 test
mocking the fetch response headers). When the header is absent/blocked, no error — display still shows
the body `session_id`.

---

### Task 9 — Optional UI copy alignment (cosmetic; owner-gated, §9.5)

In `CarePlanPage.tsx`, optionally reword user-facing strings from "simplify/note" to "care plan":
CTA "Simplify My Note →", "Your Simplified Note", "Simplifying your note…", "Simplify another note",
the JSON download filename `simplified-document.json`. Skip if the owner prefers current copy. No
logic change.

**Acceptance:** copy matches the owner's choice; no behavioral change.

---

### Task 10 — Final sweep + typecheck

1. `grep -rn "simplify\|Simplify" src` — remaining hits should be only: the deprecated
   `SimplifyOutput` re-export alias (Task 6, intentional) and any owner-kept copy. No `/simplify` HTTP
   paths, no `SimplifyPage`, no `normalizeSimplifyOutput`.
2. `grep -rn "appointment" src` — only the `doc_type: 'appointment_note'` wire literal remains.
3. `npm run build` and `npm run lint` clean.
4. Manual smoke (against SP2 backend): upload → SSE progress → result renders (readability + 6 method
   cards when grading on); Run Grading re-grades; saved list/open/rename/delete; Show Original split
   view; dataset preview; batch run; JSON + PDF download.

**Acceptance:** all of the above pass; full end-to-end flow works against the refactored backend.

---

## Summary of what requires you (not a dev agent)

1. **Lockstep / hard-cut deploy** — ship this frontend together with the SP2 backend (or have SP2 keep
   `/simplify*` aliases for one release first). You own release ordering. (Tasks 5, 10.)
2. **CORS `Access-Control-Expose-Headers: X-Session-Id, X-Trace-Id`** — confirm the backend/SP4/SP2
   CORS config exposes these, or Task 8's header reads silently no-op (note the active `fixing-cors`
   branch). (Task 8.)
3. **Decide the version-chooser fate (PRD §9.2)** — remove `VersionsPage`/`VersionDetailPage` + routes
   + NavBar link (recommended), or keep `VersionsPage` as a static info page. Gates Task 4's scope.
4. **Confirm inner-key handling (PRD §9.1)** — ship Option A now (key-agnostic normalizer, internal
   field stays `simplified_care_plan`); pair Option B (internal field → `care_plan`) with SP2's future
   wire-key flip. (Task 6.)
5. **Confirm `doc_type:'appointment_note'` stays** (SP1-owned wire literal; rename is frontend symbols
   only). (Task 7.)
6. **Optional UI copy review (PRD §9.5)** — approve "simplify"→"care plan" wording or keep current.
   (Task 9.)
7. **`VITE_DEFAULT_VERSION` env var** — now effectively dead (single version); leave (ignored) or
   remove from `.env*`. No deploy action required. (Task 4.)
