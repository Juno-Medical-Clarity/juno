# Tasks: Frontend Alignment to `care_plan`

Read `PRD.md` in this folder first. This sub-project is **PLANNING-followable** for a junior dev:
each task lists exact files, exact changes, and acceptance criteria. Do tasks in order — later tasks
assume earlier renames landed. After each task, run `npm run build` (or `tsc --noEmit`) in
`frontend/` and fix any import breakage before moving on.

All paths are under `frontend/src/` unless stated.

Depends on: **SP1** (`CarePlanInternal` envelope, single `care_plan` inner key), **SP2**
(`/care_plan*` paths). **Do not start until SP1 + SP2 have landed** (or are landing in the same
release window — lockstep, hard cut, no `/simplify*` aliases). The header work (Task 8) also depends on
**SP4** for `X-Trace-Id` and on CORS `Access-Control-Expose-Headers` (owner is exposing the headers).

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
import type { CarePlanInternal } from './types/envelope';   // renamed in Task 6 (no SimplifyOutput alias)
export interface VersionRouteState {
  output?: CarePlanInternal;
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

### Task 4 — Remove the dynamic version chooser; keep a static `VersionsPage` (PRD §4.2, §9.2)

**Owner decision (RESOLVED):** delete the *dynamic* chooser, but keep a static `VersionsPage` the
owner will extend with future versions (next: V1_3). Structure `VERSIONS` so adding a version is a
one-line append.

1. **`config.ts`:** collapse to one version; remove `VITE_DEFAULT_VERSION`; keep `VERSIONS` static.
   ```ts
   const VERSION_IDS = ['v1-2'] as const;
   export const CARE_PLAN_API_PATH = '/care_plan';   // renamed from SIMPLIFY_API_PATH (Task 5)
   export const DEFAULT_VERSION = 'v1-2';   // plain constant — VITE_DEFAULT_VERSION removed (PRD §8.3)
   // Static list rendered by VersionsPage. Append a second entry (e.g. v1-3) to add a version later.
   export const VERSIONS = [
     { id: 'v1-2', label: 'Version 1.2', description: '…(keep current v1-2 text)…',
       steps: ['Read input','Find medical terms','Simplify','Clarify care details','Structure note'],
       isDefault: true },
   ] as const;
   ```
   > Record the `VITE_DEFAULT_VERSION` removal (and any `.env*` cleanup) in the dev-code `code.md`
   > run-summary (PRD §8.3).
2. **`components/ConfigurationCard.tsx`:** remove the `Version` `<label>` + `<select>` and the
   `VERSIONS` import; keep the "Enable grading" checkbox. **Drop** the `version` / `onVersionChange`
   props from `ConfigurationCardProps` and the JSX that used them (no no-op props).
3. **Update the page's** `<ConfigurationCard .../>` usage to pass only `gradingEnabled` /
   `onGradingEnabledChange`. The page sends `DEFAULT_VERSION` (`'v1-2'`) on the form directly.
4. **`App.tsx`:** **keep** the `/versions` route (renders `VersionsPage`); **remove** the
   `/version/:id` route and the `VersionDetailPage` import.
5. **Delete** `pages/VersionDetailPage.tsx`. **Keep** `pages/VersionsPage.tsx` — ensure it renders by
   mapping over `config.ts`'s `VERSIONS` (static, no dynamic selection/routing). Strip any
   `versionPath`/per-version-chooser links it may carry.
6. **`components/NavBar.tsx`:** **keep** the `<Link to="/versions">Versions</Link>`.

**Acceptance:** upload screen shows the grading checkbox and no version dropdown; `/versions` renders a
static list (one row per `VERSIONS` entry); no route/link points to `VersionDetailPage`;
`grep -rn "VersionDetailPage" src` is empty; `grep -rn "VITE_DEFAULT_VERSION" src` is empty.

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

### Task 6 — Rename `SimplifyOutput` → `CarePlanInternal` (hard rename) + `care_plan` inner key

**Single decided inner key is `care_plan` — no `simplified_care_plan`, no alias (PRD §4.5, §9.1).**

1. **`types/envelope.ts`:**
   - Rename `export interface SimplifyOutput` → `export interface CarePlanInternal`. **No** deprecated
     alias / re-export — hard rename (PRD §9.3).
   - Inner field is `care_plan: SimplifiedCarePlan` (rename from `simplified_care_plan`).
2. **`utils/normalizeOutput.ts`:**
   - Rename `normalizeSimplifyOutput` → `normalizeCarePlanOutput`.
   - Resolve the inner care plan from the single `care_plan` key (plus the legacy flat-shape branch for
     old saved Firestore docs), normalizing to the `care_plan` field:
     ```ts
     export function normalizeCarePlanOutput(raw: any): CarePlanInternal {
       if (raw == null) throw new Error('normalizeCarePlanOutput: null/undefined output');
       if ('care_plan' in raw) {
         return { ...raw, care_plan: raw.care_plan };
       }
       // ...existing legacy flat-shape branch, unchanged (still returns grading:{entries:[],…})...
     }
     ```
   - `isLegacyShape` stays but its check reflects "no `care_plan` envelope key present":
     `return !('care_plan' in data);`
3. Update all call sites of the old names:
   - `normalizeSimplifyOutput` → `normalizeCarePlanOutput` (live page, plus `normalizeOutput.test.ts`
     left for SP6).
   - `SimplifyOutput` type imports → `CarePlanInternal` in: `CarePlanPage.tsx`, `router.tsx`,
     `OutputGradingCard.tsx`, and `types/envelope.ts` self.
   - **All `output.simplified_care_plan` reads → `output.care_plan`** in: `CarePlanView.tsx`,
     `CarePlanPage.tsx`, `utils/buildPdfHtml.ts`, `utils/grading.ts`, `OutputGradingCard.tsx`, and the
     `SplitView` call sites.

**Acceptance:** `tsc --noEmit` passes. `grep -rn "simplified_care_plan" src` returns **zero** matches
(the key is gone). `grep -rn "SimplifyOutput" src` returns zero. Feeding the normalizer a fixture with
the `care_plan` inner key, and the legacy flat shape, both produce an envelope whose `care_plan` field
is populated.

---

### Task 7 — Rename `AppointmentNote*` → `CarePlan*`

1. **Rename file** `types/simplify.ts` → `types/carePlan.ts`.
2. In it, rename interface `AppointmentNote` → `CarePlanContent`. **Change the field literal
   `doc_type: 'appointment_note'` → `doc_type: 'care_plan'`** (RESOLVED — PRD §4.6/§9.4; SP1 owns the
   backend model + LLM prompt side, SP5 matches the FE literal in lockstep).
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
returns nothing; `grep -rn "appointment_note\|appointment" src` returns **zero** matches (the
`doc_type` literal is now `'care_plan'`). App renders the care plan identically (no visual diff).

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

### Task 9 — UI copy alignment (RESOLVED — reword; PRD §8.5/§9.5)

Owner approved rewording. In `CarePlanPage.tsx`, apply the PRD §8.5 copy map (strings only, no logic
change):

| Old | New |
|---|---|
| "Simplify My Note →" | "Create My Care Plan →" |
| "Your Simplified Note" | "Your Care Plan" |
| "Simplify another note" | "Create another care plan" |
| "Simplifying your note…" | "Creating your care plan…" |
| document `<title>` (simplify-framed) | "Juno — Care Plan" |
| download filename `simplified-document.json` | `care-plan.json` |

**Acceptance:** user-facing copy matches the §8.5 map; `grep -rn "Simplif\|simplified-document" src`
shows no leftover user-facing simplify copy; no behavioral change.

---

### Task 10 — Final sweep + typecheck

1. `grep -rn "simplify\|Simplify" src` — **zero** hits (hard rename, no alias, copy reworded). No
   `/simplify` HTTP paths, no `SimplifyPage`, no `normalizeSimplifyOutput`, no `SimplifyOutput`, no
   `simplified_care_plan`, no `simplified-document.json`.
2. `grep -rn "appointment" src` — **zero** hits (the `doc_type` literal is now `'care_plan'`).
3. `grep -rn "VITE_DEFAULT_VERSION\|VersionDetailPage\|versionPath\|outputRouteVersionId" src` — zero.
4. `npm run build` and `npm run lint` clean.
5. Manual smoke (against SP1+SP2 backend): upload → SSE progress → result renders (readability + 6
   method cards when grading on); Run Grading re-grades; saved list/open/rename/delete; Show Original
   split view; dataset preview; batch run; JSON + PDF download.

**Acceptance:** all of the above pass; full end-to-end flow works against the refactored backend.

---

## Summary of what requires you (not a dev agent)

All owner decisions are resolved (PRD §9). Remaining human/release actions:

1. **Lockstep / hard-cut deploy (RESOLVED — yes).** Ship this frontend together with SP1 + SP2 in one
   release window. **No `/simplify*` aliases kept** (nothing in production). You own release ordering.
   (Tasks 5, 10.)
2. **CORS `Access-Control-Expose-Headers: X-Session-Id, X-Trace-Id` (RESOLVED — expose them).** Confirm
   the backend/SP4/SP2 CORS config (active `fixing-cors` branch) lists both headers so Task 8's reads
   work. (Task 8.)
3. **`VITE_DEFAULT_VERSION` env var (RESOLVED — owner removes it).** `DEFAULT_VERSION` becomes a plain
   `'v1-2'` constant. **Record the env-var removal + `.env*` cleanup in the dev-code `code.md`
   run-summary** (PRD §8.3). (Task 4.)
4. **`doc_type` literal (RESOLVED — `appointment_note` → `care_plan`).** SP1 owns the backend model +
   LLM prompt; SP5 matches the FE literal in lockstep. Coordinate with SP1. (Task 7.)

*Decided, no action needed:* version chooser → delete dynamic chooser, keep static `VersionsPage`
(§9.2); inner key → single `care_plan`, no alias (§9.1); `SimplifyOutput`/`SimplifyPage` → hard rename,
no aliases (§9.3); UI copy → reword per §8.5 (§9.5).
