# Review: SP-13 Frontend Code Organization

**Status: Complete (with one fix applied)**

---

## What Was Implemented (Correctly)

All five structural tasks were executed correctly by the original agent run (commit range b4fcb86–9eea2ce):

1. **CSS-paired components moved to subfolders** — `Sidebar/`, `SplitView/`, `PresetDataCard/` each contain their `.tsx`, `.css`, and a correct `index.ts` re-export stub. Internal imports inside the component `.tsx` files were correctly updated to `../../api/` and `../../utils/` (not left as stale `../api/`).

2. **`src/components/index.ts` barrel** — All 10 components re-exported via `export { default as X } from './X'`. Correct; no name conflicts.

3. **`src/api/index.ts` barrel** — All 4 modules re-exported via `export * from './X'`. Name collision pre-flight check confirmed: no duplicates across `apiClient`, `datasets`, `firebase`, `savedOutputs`. The `export *` form is safe.

4. **Test files moved to `src/tests/{api,components,utils,pages/care-plan}/`** — All 11 test files (9 from PRD + 2 added by SP-11) are under `src/tests/`. No test files remain in `src/api/`, `src/components/`, or `src/utils/`.

5. **Import paths inside test files** — All imports updated correctly. `vi.mock()` paths all point to `../../api/firebase` (or `../../../api/firebase` for the `pages/` depth). No stale `./firebase` or `../api/firebase` paths remain.

---

## Issue Found

**`tsconfig.app.json` excluded `src/tests/` — build failed.**

`tsconfig.app.json` uses `"include": ["src"]`, which captures `src/tests/` after the move. The test files use `@testing-library/jest-dom` matchers (`toBeInTheDocument`, `toBeDisabled`, `toHaveStyle`) that are not in the `"types": ["vite/client"]` list. This caused `tsc -b` to emit ~20+ TS2339 errors during `npm run build`, failing the build acceptance criterion.

This was noted as a pre-existing concern in the implementation log but was not fixed.

---

## Fix Applied

Added `"exclude": ["src/tests"]` to `frontend/tsconfig.app.json`.

- Tests are discovered and type-checked by vitest via `vite.config.ts` (which uses jsdom environment and `vitest.setup.ts` that imports `@testing-library/jest-dom/vitest`).
- The app `tsc` compilation should not include test files; they are not production code.
- Commit: `14c0db3` — "13-frontend-code-organization: Fix tsconfig.app.json to exclude src/tests/"

---

## Final Verification

After the fix:

- `npm run build` — exits 0, no TypeScript errors, vite bundle produced (371 kB JS, 31 kB CSS)
- `npm run test` — 85/85 passed across 11 test files

---

## Deferred Items (Not Required by PRD)

- **`tsconfig.test.json`** — A separate test tsconfig with `@testing-library/jest-dom` in `types` would be cleaner, but `vitest` does not require it. The exclude approach is sufficient.
- **Barrel migration of `CarePlanPage.tsx` / `App.tsx`** — PRD §9.2 explicitly deferred; both still use direct-path imports, which remain valid.
- **`src/tests/auth/`** — Not created; no auth test files exist (PRD §9.3 resolved: skip).
