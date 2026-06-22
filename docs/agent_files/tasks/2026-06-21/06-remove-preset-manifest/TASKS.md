# Tasks: Remove Preset Manifest Dead Code (SP06)

Read `PRD.md` in this folder first. SP06 is **Phase 1** with no dependencies — it can land immediately.

**Assumed state (verify before acting):**
- `frontend/scripts/generate-preset-manifest.cjs` exists and is git-tracked.
- `frontend/public/preset-data/manifest.json` exists on disk but is **not** git-tracked (gitignored via `frontend/public/preset-data/` in `.gitignore`).
- `frontend/package.json` line 8: `"build": "node scripts/generate-preset-manifest.cjs && tsc -b && vite build"`
- `frontend/scripts/` contains exactly one file: `generate-preset-manifest.cjs`.

---

### Task 1 — Edit `frontend/package.json` — remove manifest step from `build` script

- **Files:** `frontend/package.json`
- **Changes:**
  - On line 8, replace the `build` script value:
    - Old: `"build": "node scripts/generate-preset-manifest.cjs && tsc -b && vite build"`
    - New: `"build": "tsc -b && vite build"`
  - Leave `dev`, `lint`, `preview`, and `test` scripts completely unchanged.
- **Acceptance criteria:**
  - `cat frontend/package.json` shows `"build": "tsc -b && vite build"` with no reference to `generate-preset-manifest`.
  - The `dev`, `test`, `lint`, and `preview` scripts are unchanged.

---

### Task 2 — Delete `frontend/scripts/` directory from git

- **Files:** `frontend/scripts/generate-preset-manifest.cjs` (deleted), `frontend/scripts/` (directory removed)
- **Changes:**
  - Run from the repo root:
    ```bash
    git rm -r frontend/scripts/
    ```
  - This stages the deletion of `frontend/scripts/generate-preset-manifest.cjs` and removes the now-empty `frontend/scripts/` directory from the working tree. Do **not** run `git rm` on just the `.cjs` file and leave an empty directory.
- **Acceptance criteria:**
  - `git status` shows `deleted: frontend/scripts/generate-preset-manifest.cjs` as a staged deletion.
  - `ls frontend/scripts/` returns a "No such file or directory" error (directory is gone).
  - No other files in `frontend/` are staged or modified.

---

### Task 3 — Delete `frontend/public/preset-data/manifest.json` from disk

- **Files:** `frontend/public/preset-data/manifest.json` (disk only — not git-tracked)
- **Changes:**
  - Run from the repo root:
    ```bash
    rm frontend/public/preset-data/manifest.json
    ```
  - No `git rm` is needed — the file is gitignored and not tracked by git.
  - The now-empty `frontend/public/preset-data/` directory may also be removed (`rmdir frontend/public/preset-data/`), but leaving it empty is equally acceptable per PRD §4.1.
- **Acceptance criteria:**
  - `ls frontend/public/preset-data/manifest.json` returns "No such file or directory".
  - `git status frontend/` does **not** show `manifest.json` (it was gitignored before and after).
  - `git ls-files frontend/public/preset-data/` produces no output.

---

### Task 4 — Build smoke test and dist verification

- **Files:** none (verification only)
- **Changes:**
  - Run the build from `frontend/`:
    ```bash
    cd frontend && npm run build
    ```
  - After build completes, verify no `preset-data/` directory was created under `dist/`:
    ```bash
    ls dist/preset-data/ 2>/dev/null && echo "UNEXPECTED" || echo "OK — no preset-data in dist"
    ```
  - Also verify the existing test suite still passes:
    ```bash
    npm run test
    ```
- **Acceptance criteria:**
  - `npm run build` exits 0 with no errors.
  - The dist verification command prints `OK — no preset-data in dist`.
  - `npm run test` exits 0 with all existing tests passing (no test file references the manifest script or `manifest.json`, so no changes are expected).
  - No `public/preset-data/manifest.json` error appears in build output.

---

## Summary of what requires you (not a dev agent)

1. **Confirm `frontend/scripts/` directory deletion scope** (PRD §8.1): The PRD assumes it is safe to delete the entire `frontend/scripts/` directory because it currently holds only `generate-preset-manifest.cjs`. If you plan to add other build scripts soon, you may prefer to keep the empty directory. Confirm before Task 2 runs.

2. **Confirm local disk cleanup scope** (PRD §8.2): Task 3 deletes only `frontend/public/preset-data/manifest.json`. If you want the entire `frontend/public/preset-data/` directory removed from disk as housekeeping (it is gitignored and will be empty after the manifest file is gone), say so explicitly — the task as written leaves the empty directory in place.
