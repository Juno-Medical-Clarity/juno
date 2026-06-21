# Tasks: Frontend Code Organization (SP-13)

**Pure structural reorganization — zero logic changes.** All production behaviour is
unchanged; every task is independently verifiable by running `npm run test` and `npm run
build` in `frontend/`. SP-11 must not merge until SP-13 is on `main` (SP-11 edits
`SplitView/SplitView.tsx`, the subfolder path created in Task 2).

---

### Task 1 — Pre-flight: check for name collisions in `src/api/` modules

- **Files (read-only):** `frontend/src/api/apiClient.ts`, `frontend/src/api/datasets.ts`,
  `frontend/src/api/firebase.ts`, `frontend/src/api/savedOutputs.ts`
- **Changes:**
  Run:
  ```
  grep -n "^export" frontend/src/api/apiClient.ts frontend/src/api/datasets.ts \
    frontend/src/api/firebase.ts frontend/src/api/savedOutputs.ts
  ```
  Scan the output for any export name that appears in more than one file. If a collision
  exists, note the name(s) and decide: switch that module's barrel entry (Task 5) to
  `export * as <moduleName> from './<moduleName>'` instead of `export * from './<moduleName>'`.
  If no collision exists, no change is required — proceed directly to Task 2.
- **Acceptance criteria:** You have confirmed whether any name collision exists and have a
  plan (namespace export or none) ready for Task 5.
  > _Note: As of the task-writing date the grep output shows no duplicate export names across
  > the four modules. Verify before landing._

---

### Task 2 — Move CSS-paired components into own subfolders + add `index.ts` stubs

- **Files:**
  - `frontend/src/components/Sidebar.tsx` → `frontend/src/components/Sidebar/Sidebar.tsx`
  - `frontend/src/components/Sidebar.css` → `frontend/src/components/Sidebar/Sidebar.css`
  - `frontend/src/components/Sidebar/index.ts` (NEW)
  - `frontend/src/components/SplitView.tsx` → `frontend/src/components/SplitView/SplitView.tsx`
  - `frontend/src/components/SplitView.css` → `frontend/src/components/SplitView/SplitView.css`
  - `frontend/src/components/SplitView/index.ts` (NEW)
  - `frontend/src/components/PresetDataCard.tsx` → `frontend/src/components/PresetDataCard/PresetDataCard.tsx`
  - `frontend/src/components/PresetDataCard.css` → `frontend/src/components/PresetDataCard/PresetDataCard.css`
  - `frontend/src/components/PresetDataCard/index.ts` (NEW)
- **Changes:**
  Use `git mv` to preserve history:
  ```bash
  # Sidebar
  mkdir -p frontend/src/components/Sidebar
  git mv frontend/src/components/Sidebar.tsx  frontend/src/components/Sidebar/Sidebar.tsx
  git mv frontend/src/components/Sidebar.css  frontend/src/components/Sidebar/Sidebar.css

  # SplitView
  mkdir -p frontend/src/components/SplitView
  git mv frontend/src/components/SplitView.tsx  frontend/src/components/SplitView/SplitView.tsx
  git mv frontend/src/components/SplitView.css  frontend/src/components/SplitView/SplitView.css

  # PresetDataCard
  mkdir -p frontend/src/components/PresetDataCard
  git mv frontend/src/components/PresetDataCard.tsx  frontend/src/components/PresetDataCard/PresetDataCard.tsx
  git mv frontend/src/components/PresetDataCard.css  frontend/src/components/PresetDataCard/PresetDataCard.css
  ```
  Create each `index.ts` stub (same pattern for all three):
  ```ts
  // frontend/src/components/Sidebar/index.ts
  export { default } from './Sidebar';
  ```
  ```ts
  // frontend/src/components/SplitView/index.ts
  export { default } from './SplitView';
  ```
  ```ts
  // frontend/src/components/PresetDataCard/index.ts
  export { default } from './PresetDataCard';
  ```
  **Do NOT edit the bodies of `Sidebar.tsx`, `SplitView.tsx`, or `PresetDataCard.tsx`.** Each
  already has `import './Sidebar.css'` / `import './SplitView.css'` / `import './PresetDataCard.css'`
  — these remain correct because the `.tsx` and `.css` are now co-located in the same subfolder.
- **Acceptance criteria:**
  - `ls frontend/src/components/Sidebar/` shows `Sidebar.tsx`, `Sidebar.css`, `index.ts`.
  - Same for `SplitView/` and `PresetDataCard/`.
  - No flat `Sidebar.tsx`, `Sidebar.css`, `SplitView.tsx`, `SplitView.css`,
    `PresetDataCard.tsx`, or `PresetDataCard.css` remain directly under `src/components/`.
  - `npm run build` (in `frontend/`) exits 0 with no TypeScript errors (existing callers
    like `CarePlanPage.tsx` resolve via the new `index.ts` transparently).

---

### Task 3 — Add `src/components/index.ts` barrel

- **Files:** `frontend/src/components/index.ts` (NEW)
- **Changes:**
  Create the file with exactly these contents (order is alphabetical for readability):
  ```ts
  // src/components/index.ts
  export { default as AuthLayout }        from './AuthLayout';
  export { default as CarePlanView }      from './CarePlanView';
  export { default as ConfigurationCard } from './ConfigurationCard';
  export { default as DatasetGroupRow }   from './DatasetGroupRow';
  export { default as MedicalTerm }       from './MedicalTerm';
  export { default as NavBar }            from './NavBar';
  export { default as OutputGradingCard } from './OutputGradingCard';
  export { default as PresetDataCard }    from './PresetDataCard';
  export { default as Sidebar }           from './Sidebar';
  export { default as SplitView }         from './SplitView';
  ```
  > The `DatasetGroupRow` named type `DatasetGroupSelection` is intentionally omitted from the
  > barrel (PRD §9.5 RESOLVED). The single consumer (`PresetDataCard.tsx`) imports it directly
  > from `'../components/DatasetGroupRow'` and that import is not changed by this PR.
- **Acceptance criteria:**
  - `frontend/src/components/index.ts` exists with all 10 re-exports.
  - `npm run build` exits 0 (TypeScript does not flag barrel re-exports under
    `noUnusedLocals: true`).
  - Existing direct imports like `import Sidebar from '../../components/Sidebar'` still
    compile — the barrel is additive.

---

### Task 4 — Add `src/api/index.ts` barrel

- **Files:** `frontend/src/api/index.ts` (NEW)
- **Changes:**
  Apply the collision resolution from Task 1. In the expected no-collision case:
  ```ts
  // src/api/index.ts
  export * from './apiClient';
  export * from './datasets';
  export * from './firebase';
  export * from './savedOutputs';
  ```
  If Task 1 found a collision for a module (e.g. `firebase`), switch that line to:
  ```ts
  export * as firebase from './firebase';
  ```
- **Acceptance criteria:**
  - `frontend/src/api/index.ts` exists.
  - `npm run build` exits 0 with no duplicate-identifier TypeScript errors.

---

### Task 5 — Move test files into `src/tests/` subtree

Moves all 9 test files. Use `git mv` for each so git history follows the file.

- **Files (before → after):**
  | Before | After |
  |---|---|
  | `frontend/src/api/apiClient.test.ts` | `frontend/src/tests/api/apiClient.test.ts` |
  | `frontend/src/api/savedOutputs.test.ts` | `frontend/src/tests/api/savedOutputs.test.ts` |
  | `frontend/src/components/CarePlanView.test.tsx` | `frontend/src/tests/components/CarePlanView.test.tsx` |
  | `frontend/src/components/ConfigurationCard.test.tsx` | `frontend/src/tests/components/ConfigurationCard.test.tsx` |
  | `frontend/src/components/OutputGradingCard.test.tsx` | `frontend/src/tests/components/OutputGradingCard.test.tsx` |
  | `frontend/src/utils/buildPdfHtml.test.ts` | `frontend/src/tests/utils/buildPdfHtml.test.ts` |
  | `frontend/src/utils/grading.test.ts` | `frontend/src/tests/utils/grading.test.ts` |
  | `frontend/src/utils/groupSavedOutputs.test.ts` | `frontend/src/tests/utils/groupSavedOutputs.test.ts` |
  | `frontend/src/utils/normalizeOutput.test.ts` | `frontend/src/tests/utils/normalizeOutput.test.ts` |

- **Changes:**
  ```bash
  mkdir -p frontend/src/tests/api frontend/src/tests/components frontend/src/tests/utils
  git mv frontend/src/api/apiClient.test.ts            frontend/src/tests/api/apiClient.test.ts
  git mv frontend/src/api/savedOutputs.test.ts         frontend/src/tests/api/savedOutputs.test.ts
  git mv frontend/src/components/CarePlanView.test.tsx  frontend/src/tests/components/CarePlanView.test.tsx
  git mv frontend/src/components/ConfigurationCard.test.tsx frontend/src/tests/components/ConfigurationCard.test.tsx
  git mv frontend/src/components/OutputGradingCard.test.tsx frontend/src/tests/components/OutputGradingCard.test.tsx
  git mv frontend/src/utils/buildPdfHtml.test.ts       frontend/src/tests/utils/buildPdfHtml.test.ts
  git mv frontend/src/utils/grading.test.ts            frontend/src/tests/utils/grading.test.ts
  git mv frontend/src/utils/groupSavedOutputs.test.ts  frontend/src/tests/utils/groupSavedOutputs.test.ts
  git mv frontend/src/utils/normalizeOutput.test.ts    frontend/src/tests/utils/normalizeOutput.test.ts
  ```
  > Do NOT create `src/tests/auth/` — no auth test files exist today (PRD §9.3 RESOLVED).
- **Acceptance criteria:**
  - All 9 test files exist under `src/tests/`. No test files remain under `src/api/`,
    `src/components/`, or `src/utils/`.
  - `npm run test` fails with import errors at this point (import paths inside the moved
    files are still stale). That is expected — fix in Task 6.

---

### Task 6 — Update import paths inside the moved test files

This is the import-rewrite step. Apply every change in the table below. **Do not alter any
test logic — only the path strings change.**

- **Files:** all 9 moved test files under `frontend/src/tests/`
- **Changes (complete table, cross-referenced with real file contents):**

  **`src/tests/api/apiClient.test.ts`** (4 path strings):
  ```diff
  -vi.mock('./firebase', () => ({
  +vi.mock('../../api/firebase', () => ({
  ```
  ```diff
  -import { authenticatedFetch } from './apiClient';
  +import { authenticatedFetch } from '../../api/apiClient';
  ```
  ```diff
  -import * as firebaseModule from './firebase';
  +import * as firebaseModule from '../../api/firebase';
  ```
  > The `import * as firebaseModule` line is not in the PRD's §4.1 table but is present
  > in the actual file (line 10). It must be updated — leaving it at `'./firebase'` would
  > break the test.

  **`src/tests/api/savedOutputs.test.ts`** (2 path strings):
  ```diff
  -vi.mock('./firebase', () => ({
  +vi.mock('../../api/firebase', () => ({
  ```
  ```diff
  -import { listSavedOutputs, getSavedOutput, renameSavedOutput, deleteSavedOutput } from './savedOutputs';
  +import { listSavedOutputs, getSavedOutput, renameSavedOutput, deleteSavedOutput } from '../../api/savedOutputs';
  ```

  **`src/tests/components/CarePlanView.test.tsx`** (3 path strings):
  ```diff
  -import CarePlanView from './CarePlanView';
  +import CarePlanView from '../../components/CarePlanView';
  ```
  ```diff
  -import type { SimplifiedCarePlan, Grading } from '../types/envelope';
  +import type { SimplifiedCarePlan, Grading } from '../../types/envelope';
  ```
  ```diff
  -vi.mock('../api/firebase', () => ({
  +vi.mock('../../api/firebase', () => ({
  ```

  **`src/tests/components/ConfigurationCard.test.tsx`** (2 path strings):
  ```diff
  -import ConfigurationCard from './ConfigurationCard';
  +import ConfigurationCard from '../../components/ConfigurationCard';
  ```
  ```diff
  -vi.mock('../api/firebase', () => ({
  +vi.mock('../../api/firebase', () => ({
  ```

  **`src/tests/components/OutputGradingCard.test.tsx`** (3 path strings):
  ```diff
  -import OutputGradingCard from './OutputGradingCard';
  +import OutputGradingCard from '../../components/OutputGradingCard';
  ```
  ```diff
  -import type { CarePlanInternal, Grading } from '../types/envelope';
  +import type { CarePlanInternal, Grading } from '../../types/envelope';
  ```
  ```diff
  -vi.mock('../api/firebase', () => ({
  +vi.mock('../../api/firebase', () => ({
  ```

  **`src/tests/utils/buildPdfHtml.test.ts`** (2 path strings):
  ```diff
  -import { buildPdfHtml, escapeHtml } from './buildPdfHtml';
  +import { buildPdfHtml, escapeHtml } from '../../utils/buildPdfHtml';
  ```
  ```diff
  -import type { SimplifiedCarePlan } from '../types/envelope';
  +import type { SimplifiedCarePlan } from '../../types/envelope';
  ```

  **`src/tests/utils/grading.test.ts`** (2 path strings):
  ```diff
  -import { patientScoreFromGrading, methodEntriesFromGrading } from './grading';
  +import { patientScoreFromGrading, methodEntriesFromGrading } from '../../utils/grading';
  ```
  ```diff
  -import type { Grading } from '../types/envelope';
  +import type { Grading } from '../../types/envelope';
  ```

  **`src/tests/utils/groupSavedOutputs.test.ts`** (2 path strings):
  ```diff
  -import { formatDateKey, groupSavedOutputs, localDateKey } from './groupSavedOutputs';
  +import { formatDateKey, groupSavedOutputs, localDateKey } from '../../utils/groupSavedOutputs';
  ```
  ```diff
  -import type { SavedOutputMeta } from './groupSavedOutputs';
  +import type { SavedOutputMeta } from '../../utils/groupSavedOutputs';
  ```

  **`src/tests/utils/normalizeOutput.test.ts`** (1 path string):
  ```diff
  -import { normalizeCarePlanOutput } from './normalizeOutput';
  +import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
  ```

- **Acceptance criteria:**
  - `npm run test` (in `frontend/`) passes with zero failures.
  - No `./firebase`, `../api/firebase`, `'./apiClient'`, etc. remain in any file under
    `src/tests/` — verify with:
    ```bash
    grep -rn "from '\.\." frontend/src/tests/
    ```
    Adjust for any relative paths that could still be wrong.
  - `vi.mock()` calls in all 5 component/api test files use `'../../api/firebase'`.

---

### Task 7 — Final verification: build + test + spot-check

- **Files:** no edits — read-only verification pass
- **Changes:**
  Run both commands from `frontend/`:
  ```bash
  npm run build
  npm run test
  ```
  Additionally, spot-check every `vi.mock(` in `src/tests/` to confirm paths point to
  `../../api/firebase` (not `./firebase` or `../api/firebase`):
  ```bash
  grep -rn "vi\.mock" frontend/src/tests/
  ```
  All results should show `'../../api/firebase'`.
- **Acceptance criteria:**
  - `npm run build` exits 0 with zero TypeScript errors.
  - `npm run test` exits 0 with all 9 test files collected and passing.
  - `grep -rn "vi\.mock" frontend/src/tests/` shows only `../../api/firebase` — no stale
    relative paths that could silently mis-apply the mock.

---

## Summary of what requires you (not a dev agent)

**None required** (PRD §8). No environment variables, no Firebase/Cloud Run config, no
dependency changes, and no deployment steps are part of SP-13.

One optional decision left to the implementer's discretion (PRD §9.2 DEFERRED): whether
to migrate `CarePlanPage.tsx` and `App.tsx` to use the new barrels in the same PR:
```ts
// Optional — both styles are valid after SP-13 lands
import { Sidebar, SplitView, CarePlanView } from '../../components';
import { AuthLayout } from './components';
```
This is not required and can be done in a follow-up PR.

**SP-11 note:** after SP-13 merges, SP-11 must target
`frontend/src/components/SplitView/SplitView.tsx` (not the flat `SplitView.tsx`).
