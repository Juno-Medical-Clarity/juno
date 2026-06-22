# PRD: Frontend Code Organization (SP-13)

Sub-project 13 of the Juno refactor initiative — a **pure structural reorganization** with no
behavior changes. It can land independently of all other sub-projects because it touches only file
paths and import strings. Its output (the barrel files) is what SP-11 (SplitView changes) needs to
land cleanly: SP-11's SplitView edits go into `components/SplitView/SplitView.tsx` rather than
the flat `components/SplitView.tsx`, so SP-13 must merge first if SP-11 is running in parallel.

## 1. Problem

The frontend `src/` tree mixes concerns that make navigation and tooling harder:

1. **Test files are co-located** with source files across three directories (`api/`, `components/`,
   `utils/`). Running tests on "just the tests" or excluding tests from coverage requires
   glob-hacking. No `src/tests/` tree exists at all today.

2. **Three components (`Sidebar`, `SplitView`, `PresetDataCard`) have companion CSS files** that
   sit flat alongside ~7 other single-file components. The flat directory treats all components
   identically even though these three have multi-file surface area that warrants a subfolder.

3. **No barrel files exist** for `src/components/` or `src/api/`. Every consumer must know the
   exact filename — `import Sidebar from '../../components/Sidebar'` rather than
   `import { Sidebar } from '../../components'`. Adding a new component requires updating every
   import site rather than just the barrel.

There is no production data and no legacy concern; breaking changes are explicitly fine.

## 2. Goals

1. Move all 9 test files into a mirrored `src/tests/` subtree (`api/`, `components/`, `utils/`).
   Update every relative import inside the moved test files.
2. Move `Sidebar`, `SplitView`, and `PresetDataCard` into own subfolders with a co-located CSS
   file and an `index.ts` re-export. Update CSS import paths inside the `.tsx` files (unchanged
   filename, same folder — no-op).
3. Add `src/components/index.ts` barrel that re-exports all components (both flat and
   folder-based).
4. Add `src/api/index.ts` barrel re-exporting all four api modules.
5. Update all production import paths across `CarePlanPage.tsx`, `App.tsx`, and any component
   that imports from `../api/`.
6. Leave tsconfig, vite, and vitest config unchanged (no path aliases exist; relative imports
   are the project convention).

## 3. Non-Goals

- No changes to any component's logic, props, or CSS rules.
- No changes to test logic; only the file path and the relative import strings inside them change.
- Not adding an `src/auth/index.ts` barrel (only two files; consumers are few).
- Not adding an `src/utils/index.ts` barrel (no request for it; utils have diverse exports and
  granular imports are fine).
- Not introducing TypeScript path aliases (`@/components`, etc.) — the project uses relative
  imports throughout and this PRD does not change that convention.
- Not touching backend, CI scripts, or Firebase/Cloud Run configuration.
- Not updating `vitest.config.ts` — the default Vitest test discovery pattern (`**/*.test.*`)
  already matches files anywhere under `src/`, so no config change is needed when tests move.

## 4. Architecture Decisions

### 4.1 Test directory structure — `src/tests/`

Create three subdirectories mirroring the source directories from which the tests came:

```
src/tests/
  api/
    apiClient.test.ts
    savedOutputs.test.ts
  components/
    CarePlanView.test.tsx
    ConfigurationCard.test.tsx
    OutputGradingCard.test.tsx
  utils/
    buildPdfHtml.test.ts
    grading.test.ts
    groupSavedOutputs.test.ts
    normalizeOutput.test.ts
```

No `src/tests/auth/` directory is created (there are no auth test files today; the directory is
defined as in-scope by the initiative spec but there is nothing to put in it — create it only if
needed, or leave it absent).

**Vitest discovery:** `vite.config.ts` has no explicit `include` / `testMatch` pattern under
`test:`. Vitest's default is `**/*.{test,spec}.{ts,tsx,js,jsx}`, which matches anywhere under
the project root. Moving tests from `src/api/` to `src/tests/api/` requires no config change.

**Relative import rewrites inside each test file** (complete table):

| Moved test file | Import string before | Import string after |
|---|---|---|
| `src/tests/api/apiClient.test.ts` | `vi.mock('./firebase', …)` | `vi.mock('../../api/firebase', …)` |
| `src/tests/api/apiClient.test.ts` | `from './apiClient'` | `from '../../api/apiClient'` |
| `src/tests/api/apiClient.test.ts` | `from './firebase'` | `from '../../api/firebase'` |
| `src/tests/api/savedOutputs.test.ts` | `vi.mock('./firebase', …)` | `vi.mock('../../api/firebase', …)` |
| `src/tests/api/savedOutputs.test.ts` | `from './savedOutputs'` | `from '../../api/savedOutputs'` |
| `src/tests/components/CarePlanView.test.tsx` | `from './CarePlanView'` | `from '../../components/CarePlanView'` |
| `src/tests/components/CarePlanView.test.tsx` | `vi.mock('../api/firebase', …)` | `vi.mock('../../api/firebase', …)` |
| `src/tests/components/CarePlanView.test.tsx` | `from '../types/envelope'` | `from '../../types/envelope'` |
| `src/tests/components/ConfigurationCard.test.tsx` | `from './ConfigurationCard'` | `from '../../components/ConfigurationCard'` |
| `src/tests/components/ConfigurationCard.test.tsx` | `vi.mock('../api/firebase', …)` | `vi.mock('../../api/firebase', …)` |
| `src/tests/components/OutputGradingCard.test.tsx` | `from './OutputGradingCard'` | `from '../../components/OutputGradingCard'` |
| `src/tests/components/OutputGradingCard.test.tsx` | `vi.mock('../api/firebase', …)` | `vi.mock('../../api/firebase', …)` |
| `src/tests/components/OutputGradingCard.test.tsx` | `from '../types/envelope'` | `from '../../types/envelope'` |
| `src/tests/utils/buildPdfHtml.test.ts` | `from './buildPdfHtml'` | `from '../../utils/buildPdfHtml'` |
| `src/tests/utils/buildPdfHtml.test.ts` | `from '../types/envelope'` | `from '../../types/envelope'` |
| `src/tests/utils/grading.test.ts` | `from './grading'` | `from '../../utils/grading'` |
| `src/tests/utils/grading.test.ts` | `from '../types/envelope'` | `from '../../types/envelope'` |
| `src/tests/utils/groupSavedOutputs.test.ts` | `from './groupSavedOutputs'` | `from '../../utils/groupSavedOutputs'` |
| `src/tests/utils/normalizeOutput.test.ts` | `from './normalizeOutput'` | `from '../../utils/normalizeOutput'` |

Notes on the above:
- `groupSavedOutputs.test.ts` imports `SavedOutputMeta` from `'./groupSavedOutputs'` (the type
  is exported from the util, not from `api/savedOutputs`). Path becomes
  `'../../utils/groupSavedOutputs'` — no `types/` import to update.
- `normalizeOutput.test.ts` has no type imports; only `from './normalizeOutput'` to update.
- `vi.mock()` paths must also be updated because Vitest resolves mock paths relative to the
  test file's location, not the project root.

### 4.2 CSS-paired components — move into own subfolders

Three components move from flat files to subfolders. The moves are:

**Sidebar:**
```
BEFORE                                  AFTER
src/components/Sidebar.tsx       →  src/components/Sidebar/Sidebar.tsx
src/components/Sidebar.css       →  src/components/Sidebar/Sidebar.css
                                    src/components/Sidebar/index.ts        (NEW)
```

**SplitView:**
```
BEFORE                                  AFTER
src/components/SplitView.tsx     →  src/components/SplitView/SplitView.tsx
src/components/SplitView.css     →  src/components/SplitView/SplitView.css
                                    src/components/SplitView/index.ts      (NEW)
```

**PresetDataCard:**
```
BEFORE                                  AFTER
src/components/PresetDataCard.tsx  →  src/components/PresetDataCard/PresetDataCard.tsx
src/components/PresetDataCard.css  →  src/components/PresetDataCard/PresetDataCard.css
                                      src/components/PresetDataCard/index.ts  (NEW)
```

**CSS import inside each `.tsx` — no change required.** The CSS import in each component is:
```ts
// Sidebar.tsx
import './Sidebar.css';
// SplitView.tsx
import './SplitView.css';
// PresetDataCard.tsx
import './PresetDataCard.css';
```
Since the `.tsx` and `.css` are co-located in the same subfolder after the move, these relative
imports remain exactly `'./Sidebar.css'` / `'./SplitView.css'` / `'./PresetDataCard.css'` — no
edit needed inside the component bodies.

**`index.ts` for each subfolder** (same pattern for all three; shown for Sidebar):
```ts
// src/components/Sidebar/index.ts
export { default } from './Sidebar';
```
This makes `import Sidebar from '../components/Sidebar'` resolve the folder via `index.ts` —
identical to how it resolved the flat file before. Consumers that already write
`from '../../components/Sidebar'` continue to work without any path change on their end.

**SP-11 coordination note:** SP-11 edits `SplitView.tsx` to add "Show Original" input display
changes. After SP-13 merges, SP-11 must target
`src/components/SplitView/SplitView.tsx` (not the flat `SplitView.tsx`). If SP-11 is drafted
against the flat path, its diff will have a trivial conflict at merge time.

**Components staying flat** (no CSS companion, no move):
`AuthLayout.tsx`, `CarePlanView.tsx`, `ConfigurationCard.tsx`, `DatasetGroupRow.tsx`,
`MedicalTerm.tsx`, `NavBar.tsx`, `OutputGradingCard.tsx`.

### 4.3 `src/components/index.ts` barrel

```ts
// src/components/index.ts
export { default as AuthLayout }       from './AuthLayout';
export { default as CarePlanView }     from './CarePlanView';
export { default as ConfigurationCard } from './ConfigurationCard';
export { default as DatasetGroupRow }  from './DatasetGroupRow';
export { default as MedicalTerm }      from './MedicalTerm';
export { default as NavBar }           from './NavBar';
export { default as OutputGradingCard } from './OutputGradingCard';
export { default as PresetDataCard }   from './PresetDataCard';   // resolves Sidebar/index.ts
export { default as Sidebar }          from './Sidebar';           // resolves Sidebar/index.ts
export { default as SplitView }        from './SplitView';         // resolves SplitView/index.ts
```

`DatasetGroupRow` exports a named type `DatasetGroupSelection` in addition to its default export.
The barrel re-exports only the default for now; callers that need the named type continue to import
it directly:
```ts
import DatasetGroupRow, { type DatasetGroupSelection } from '../components/DatasetGroupRow';
```
The barrel does not re-export `DatasetGroupSelection` unless it causes a noUnusedLocals error
(it will not — the type import is explicit at the call site, not via the barrel).

**`noUnusedLocals: true` in `tsconfig.app.json`:** TypeScript strict mode is on. The barrel file
itself has no local variables; it is all `export ... from` re-exports, so no unused-locals issue.

### 4.4 `src/api/index.ts` barrel

The four api modules each export named functions and/or constants. The barrel re-exports
everything from each:

```ts
// src/api/index.ts
export * from './apiClient';
export * from './datasets';
export * from './firebase';
export * from './savedOutputs';
```

**Potential name collision:** verify there are no duplicate export names across the four modules
before landing. A quick `grep -n "^export"` across all four files is the check. If a collision
exists, switch the offending module to a named-namespace re-export:
```ts
export * as firebase from './firebase';
```
(This is [OPEN] — see §9.1.)

**Whether consumers should migrate to the barrel:** The barrel is additive. Existing imports like
`import { authenticatedFetch } from '../../api/apiClient'` continue to work unchanged. Migrating
production consumers to `from '../../api'` is optional and can be done incrementally. This PRD
does **not** require that all existing api imports be rewritten — only that the barrel exists so
future code can use it.

### 4.5 Production import path updates — what must change

After §4.2, the subfolder components resolve via their `index.ts` — meaning any import of the
form `from '../components/Sidebar'` still resolves correctly (Node/Vite loads
`components/Sidebar/index.ts`). **No production import path rewrites are required for Sidebar,
SplitView, or PresetDataCard** because the subfolder `index.ts` keeps the import surface identical.

The barrel (§4.3 and §4.4) is additive: existing direct-file imports remain valid. No mandatory
migration of production callers.

**Summary of mandatory production file edits:** None. All path changes are confined to:
- The 9 test files (relative imports updated per §4.1 table).
- The 3 new `index.ts` re-export stubs (new files, §4.2).
- The 2 new barrel files (new files, §4.3, §4.4).

The production component files (`Sidebar.tsx`, `SplitView.tsx`, `PresetDataCard.tsx`) themselves
do not need any internal edits (CSS imports are unchanged; no inter-component import paths change).

**Optional cleanup** (not required by this PRD, but clean to do in the same PR): update
`CarePlanPage.tsx`, `App.tsx`, and any other consumer to use the barrel:

```ts
// CarePlanPage.tsx — optional, current imports work either way
// Before (still valid after SP-13):
import Sidebar from '../../components/Sidebar';
import SplitView from '../../components/SplitView';
import CarePlanView from '../../components/CarePlanView';
import NavBar from '../../components/NavBar';
import ConfigurationCard from '../../components/ConfigurationCard';
import OutputGradingCard from '../../components/OutputGradingCard';
import PresetDataCard from '../../components/PresetDataCard';

// After (uses barrel — cleaner, still correct):
import { Sidebar, SplitView, CarePlanView, NavBar, ConfigurationCard, OutputGradingCard, PresetDataCard } from '../../components';

// App.tsx — optional:
// Before:
import AuthLayout from './components/AuthLayout';
// After:
import { AuthLayout } from './components';
```

Whether to migrate callers in this PR or leave them is the implementer's call; both are
correct after SP-13.

### 4.6 No tsconfig / vite / vitest config changes needed

- `tsconfig.app.json` has no `paths` aliases and uses `moduleResolution: "bundler"`. Folder-with-
  index resolution is standard bundler behavior — no config change needed.
- `vite.config.ts` has no `resolve.alias` entries. Vite already resolves `index.ts` in subfolders.
- `vite.config.ts` `test:` section has no `include` or `testMatch` override. Vitest default
  `**/*.{test,spec}.*` finds test files anywhere under the project root, including `src/tests/**`.
  Moving tests does not require a config update.

### 4.7 TypeScript `noUnusedLocals` / `noUnusedParameters` interaction

The barrel files use `export * from '...'` / `export { default as X } from '...'` — these are
re-export statements, not local declarations. TypeScript's `noUnusedLocals` does not flag them.
No suppression comments needed.

The `index.ts` stubs in each subfolder are `export { default } from './Sidebar'` — again a
re-export, not a local. Clean.

## 5. API Change Summary

N/A — this sub-project makes no backend changes and no wire-protocol changes.

## 6. Frontend Change Summary

**New files created (10 total):**

| File | Purpose |
|---|---|
| `src/tests/api/apiClient.test.ts` | Moved from `src/api/apiClient.test.ts` |
| `src/tests/api/savedOutputs.test.ts` | Moved from `src/api/savedOutputs.test.ts` |
| `src/tests/components/CarePlanView.test.tsx` | Moved from `src/components/CarePlanView.test.tsx` |
| `src/tests/components/ConfigurationCard.test.tsx` | Moved from `src/components/ConfigurationCard.test.tsx` |
| `src/tests/components/OutputGradingCard.test.tsx` | Moved from `src/components/OutputGradingCard.test.tsx` |
| `src/tests/utils/buildPdfHtml.test.ts` | Moved from `src/utils/buildPdfHtml.test.ts` |
| `src/tests/utils/grading.test.ts` | Moved from `src/utils/grading.test.ts` |
| `src/tests/utils/groupSavedOutputs.test.ts` | Moved from `src/utils/groupSavedOutputs.test.ts` |
| `src/tests/utils/normalizeOutput.test.ts` | Moved from `src/utils/normalizeOutput.test.ts` |
| `src/components/Sidebar/index.ts` | Re-exports Sidebar default |
| `src/components/SplitView/index.ts` | Re-exports SplitView default |
| `src/components/PresetDataCard/index.ts` | Re-exports PresetDataCard default |
| `src/components/index.ts` | Barrel: all 10 components |
| `src/api/index.ts` | Barrel: all 4 api modules |

**Files moved (12 total: 9 test files + 3 component files + 3 CSS files = 15 file operations,
but 3 of those are CSS files that move with their component):**

| Old path | New path |
|---|---|
| `src/api/apiClient.test.ts` | `src/tests/api/apiClient.test.ts` |
| `src/api/savedOutputs.test.ts` | `src/tests/api/savedOutputs.test.ts` |
| `src/components/CarePlanView.test.tsx` | `src/tests/components/CarePlanView.test.tsx` |
| `src/components/ConfigurationCard.test.tsx` | `src/tests/components/ConfigurationCard.test.tsx` |
| `src/components/OutputGradingCard.test.tsx` | `src/tests/components/OutputGradingCard.test.tsx` |
| `src/utils/buildPdfHtml.test.ts` | `src/tests/utils/buildPdfHtml.test.ts` |
| `src/utils/grading.test.ts` | `src/tests/utils/grading.test.ts` |
| `src/utils/groupSavedOutputs.test.ts` | `src/tests/utils/groupSavedOutputs.test.ts` |
| `src/utils/normalizeOutput.test.ts` | `src/tests/utils/normalizeOutput.test.ts` |
| `src/components/Sidebar.tsx` | `src/components/Sidebar/Sidebar.tsx` |
| `src/components/Sidebar.css` | `src/components/Sidebar/Sidebar.css` |
| `src/components/SplitView.tsx` | `src/components/SplitView/SplitView.tsx` |
| `src/components/SplitView.css` | `src/components/SplitView/SplitView.css` |
| `src/components/PresetDataCard.tsx` | `src/components/PresetDataCard/PresetDataCard.tsx` |
| `src/components/PresetDataCard.css` | `src/components/PresetDataCard/PresetDataCard.css` |

**Files with internal edits (9 test files only — the 19 import rewrites listed in §4.1).**

**Files with no changes (production source, config):**
`CarePlanPage.tsx`, `App.tsx`, `router.tsx`, `AuthContext.tsx`, `SignOutButton.tsx`,
`DatasetGroupRow.tsx`, `OutputGradingCard.tsx`, `CarePlanView.tsx`, `ConfigurationCard.tsx`,
`NavBar.tsx`, `MedicalTerm.tsx`, `AuthLayout.tsx`, `vite.config.ts`, `tsconfig.app.json`,
`tsconfig.json`.

## 7. Testing

This sub-project is itself a testing reorganization; the validation criteria are:

1. **`npm run test` (vitest) passes with zero failures** after all moves. This is the primary
   acceptance criterion — if tests were green before, they must be green after. No test logic
   changes, so any failure is an import-path error.

2. **`npm run build` (vite) produces no TypeScript errors** — confirms barrel type exports are
   sound and no production file broke.

3. **Manual spot-check of `vi.mock()` paths.** Vitest resolves `vi.mock()` paths relative to the
   test file. The nine updated `vi.mock('../../api/firebase', …)` calls must be double-checked
   after the move; a stale path causes the mock to silently not apply, which turns an auth-guarded
   test into a false pass (or a confusing error).

4. **No new test infrastructure needed.** This PRD introduces no new test files, no new fixtures,
   and no coverage configuration changes. The moved tests are structurally identical to the
   originals minus path corrections.

## 8. Manual Intervention Required From You

None. This sub-project makes no dependency changes, no environment variable changes, no Firebase
or Cloud Run configuration changes, and no data-migration steps. The implementer can execute it
end-to-end.

One optional human decision: whether to migrate existing production callers (e.g.
`CarePlanPage.tsx`) to use the new barrels in the same PR. Both styles are valid after SP-13;
the choice is stylistic. See §4.5.

## 9. Open Questions & Decisions

1. **`src/api/index.ts` — name collision risk.**
   `[RESOLVED: Check and fix]` — Run:
   ```
   grep -n "^export" src/api/apiClient.ts src/api/datasets.ts src/api/firebase.ts src/api/savedOutputs.ts
   ```
   If any name appears in more than one file, switch the conflicting module to a namespace export
   (`export * as <name> from './<name>'`) or rename the conflicting symbol. Implementer must run
   this check and fix any collision before landing.

2. **Barrel adoption in production callers.**
   [DEFERRED] Whether `CarePlanPage.tsx`, `App.tsx`, and other consumers should be migrated to
   use `import { Sidebar, … } from '../../components'` is left to the implementer's discretion.
   Both styles are correct post-SP-13. A follow-up cleanup PR can do this mechanically if desired.

3. **`src/tests/auth/` directory.**
   [RESOLVED: skip] The initiative spec lists `src/tests/auth/` as a target subdirectory, but
   there are no auth test files today. Do not create an empty directory; add `src/tests/auth/`
   only if an auth test is created as part of another sub-project.

4. **Git move vs delete+create for test files.**
   [RESOLVED: use `git mv`] The implementer should use `git mv` (or equivalent) rather than
   deleting and recreating files, so git history follows the file. This is a quality-of-life
   decision with no functional impact.

5. **`DatasetGroupRow` named type export in the barrel.**
   [RESOLVED: omit from barrel] `DatasetGroupRow.tsx` exports both a default (`DatasetGroupRow`)
   and a named type (`DatasetGroupSelection`). The barrel re-exports only the default. The one
   consumer of `DatasetGroupSelection` (`PresetDataCard.tsx`) imports it directly from the file.
   No change needed and no barrel re-export of the type is added — it would be unused by any
   production caller that uses the barrel.
