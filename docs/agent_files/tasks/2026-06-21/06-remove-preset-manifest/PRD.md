# PRD: Remove Preset Manifest Dead Code (SP06)

Phase 1, no dependencies. Deletes the preset-manifest generation script, its build-step
invocation, and the generated output file — removing code that runs on every `npm run build`
but whose output is never consumed at runtime.

## 1. Problem

`frontend/scripts/generate-preset-manifest.cjs` runs as the first step of every production
build (`npm run build`). It scans `../../preset-data/`, writes
`frontend/public/preset-data/manifest.json`, and copies preset files into `public/preset-data/`.

Neither the manifest nor the copied files are read by any frontend code:

- **Grep evidence — zero hits for `manifest` in `frontend/src/`:**
  ```
  grep -r "manifest" frontend/src/ --include="*.ts" --include="*.tsx"
  # (no output)
  ```
  The only hits returned were CSS class names (`preset-data-group`, etc.) in JSX — not any
  `fetch`, `import`, or read of `manifest.json`.

- **Dataset listing is served by the backend API**, not static files: `frontend/src/api/datasets.ts`
  calls `authenticatedFetch(${API_URL}${DATASETS_PATH})` → `GET /care_plan/datasets`, which reads
  `preset-data/` directly on the server. The manifest is never consulted.

- **Invocation is limited to `package.json`:** a repo-wide grep for `generate-preset-manifest`
  returned exactly one hit — line 8 of `frontend/package.json`. No CI workflow, shell script, or
  other config calls the script directly.

- **`frontend/public/preset-data/manifest.json` is not tracked in git.** The root `.gitignore`
  contains the line `frontend/public/preset-data/` which excludes the entire directory. The file
  exists on disk only because it was written by a prior local build run. Confirmed:
  ```
  git ls-files frontend/public/preset-data/
  # (no output)
  ```

- **`frontend/dist/preset-data/manifest.json` is a build artifact.** `frontend/dist/` is also
  excluded by `.gitignore` (`frontend/dist/`). It will vanish on any clean build once the
  generation step is removed.

- **Firebase Hosting config (`frontend/firebase.json`)** deploys `dist/` as the public root with
  a catch-all SPA rewrite. It contains no reference to `preset-data/` or `manifest.json`.

- **`backend/cloudbuild.yaml`** builds only the Docker image for the backend and contains no
  frontend build steps.

- **`.github/workflows/deploy-frontend.yml`** runs `npm run build` and then deploys to Firebase
  Hosting. After SP06 the build step shrinks to `tsc -b && vite build`; no other step in that
  workflow touches the manifest.

- **`.github/workflows/ci.yml`** runs `npm run test` (not `npm run build`) for the frontend CI
  job, so the manifest script does not run in CI today.

The script runs for zero benefit on every production build, introduces a cross-boundary file
operation (Node.js reaching to `../../preset-data/` from inside `frontend/`), and would copy
potentially large medical files into `public/` unnecessarily if `preset-data/` grows.

## 2. Goals

1. Delete `frontend/scripts/generate-preset-manifest.cjs` (the generation script).
2. Delete `frontend/public/preset-data/manifest.json` (the only generated output file tracked
   on disk; the directory itself is gitignored so no directory removal is needed in git).
3. Edit `frontend/package.json` `build` script: remove `node scripts/generate-preset-manifest.cjs &&`
   so the build becomes `tsc -b && vite build`.
4. Leave no build-time or runtime references to the manifest behind.

## 3. Non-Goals

- Not changing how datasets are listed or served — `GET /care_plan/datasets` is unchanged.
- Not removing `preset-data/` itself or any backend logic — those files feed the backend parser.
- Not touching `frontend/public/preset-data/` as a directory (it is already gitignored; the
  directory only exists locally because of a prior build run).
- Not adding any new functionality.
- Not changing CI workflow files — `ci.yml` runs `npm run test`, not `npm run build`, so no CI
  change is needed. `deploy-frontend.yml` calls `npm run build` which will automatically use the
  updated `package.json`.
- Not modifying `frontend/dist/` — `dist/` is gitignored; removing the generation step means
  `dist/preset-data/` will simply not be created on the next build, which is correct.

## 4. Architecture Decisions

### 4.1 Files deleted

| File | Status | Action |
|------|--------|--------|
| `frontend/scripts/generate-preset-manifest.cjs` | Git-tracked source file | Delete from repo (git rm) |
| `frontend/public/preset-data/manifest.json` | Not git-tracked (gitignored); exists on disk from prior build | Delete from disk (rm); no git action needed |

**Why delete `manifest.json` from disk even though it is gitignored?** Leaving a stale file in
`public/preset-data/manifest.json` could cause confusion — Vite copies everything in `public/`
into `dist/` during build, so a stale manifest would still end up in the deployment bundle even
after the generation step is removed. Deleting it now ensures a clean state.

**What about `frontend/public/preset-data/` directory?** The directory will be empty after the
manifest is deleted (it contained only `manifest.json`). It is gitignored so it is not tracked.
Leaving an empty gitignored directory is harmless; alternatively the implementer may delete the
directory too. Either is acceptable; the PRD does not mandate it.

### 4.2 `frontend/package.json` — build script edit

Old:
```json
"build": "node scripts/generate-preset-manifest.cjs && tsc -b && vite build"
```

New:
```json
"build": "tsc -b && vite build"
```

The `dev` script (`vite`) and `test` script (`vitest run`) are unchanged. The `scripts/`
directory will be empty after the `.cjs` file is removed; if no other scripts are added, the
`scripts/` directory itself may also be removed (optional).

### 4.3 `frontend/scripts/` directory after deletion

Currently `frontend/scripts/` contains exactly one file:
`frontend/scripts/generate-preset-manifest.cjs`

After deletion the directory is empty. Since it is not referenced anywhere, it may be deleted
too. The implementer should `git rm -r frontend/scripts/` rather than `git rm
frontend/scripts/generate-preset-manifest.cjs` followed by a manual directory removal, to keep
the working tree clean.

### 4.4 Vite public directory and `dist/` impact

Vite copies `frontend/public/**` verbatim into `dist/` at build time (no transformation). With
`manifest.json` deleted from `public/preset-data/` and the generation step removed from
`package.json`, the next build will produce a `dist/` with no `preset-data/` directory at all.
This is correct: nothing in the deployed SPA fetches from `/preset-data/manifest.json`.

**Firebase Hosting** (`firebase.json`) deploys `dist/` with a `**` → `/index.html` SPA rewrite.
Any stale browser or CDN request to `/preset-data/manifest.json` will fall through to `index.html`
and render a 200 with the SPA shell. This is the same behavior as any other unknown path — not a
regression.

### 4.5 Evidence that `manifest.json` is unreachable at runtime

Summary of all evidence gathered:

| Check | Result |
|-------|--------|
| `grep -r "manifest" frontend/src/ --include="*.ts" --include="*.tsx"` | No output |
| `grep -r "manifest.json" frontend/src/` | No output |
| `grep -r "generate-preset-manifest" .` (repo-wide) | Only `frontend/package.json:8` |
| `grep -r "manifest" .github/` | No output |
| `grep -r "manifest" frontend/vite.config.*` | No output |
| `git ls-files frontend/public/preset-data/` | No output (not tracked) |
| `frontend/src/api/datasets.ts` | Calls `GET /care_plan/datasets` — no manifest fetch |

### 4.6 No shared files with SP07

SP07 (preset data parser infrastructure + primock57) adds
`backend/utils/preset_data_parser/primock57/parser.py` — a backend offline ingestion script.
SP06 touches only frontend files. There are no shared files between SP06 and SP07.

## 5. API Change Summary

None. SP06 deletes a build-time script only. No backend routes, frontend API calls, or HTTP
contracts are modified.

## 6. Frontend Change Summary

Three filesystem changes; no source-code logic changes.

| File | Change |
|------|--------|
| `frontend/scripts/generate-preset-manifest.cjs` | Deleted (git rm -r frontend/scripts/) |
| `frontend/public/preset-data/manifest.json` | Deleted from disk (not git-tracked; rm) |
| `frontend/package.json` | Remove `node scripts/generate-preset-manifest.cjs &&` from `build` script |

No TypeScript, JSX, CSS, or test files change.

## 7. Testing

### 7.1 Build smoke test

After applying the changes, run:

```bash
cd frontend
npm run build
```

Expected: exits 0, `dist/` is created without a `preset-data/` subdirectory. No
`public/preset-data/manifest.json` error.

### 7.2 Dev server smoke test

```bash
cd frontend
npm run dev
```

Expected: Vite starts without errors. Navigating to the batch page loads dataset list from the
backend API as before.

### 7.3 Existing frontend tests pass unchanged

```bash
cd frontend
npm run test
```

No test file references the manifest script or `manifest.json`. All existing tests should
continue to pass without modification.

### 7.4 Verify no manifest in dist

After `npm run build`, confirm:

```bash
ls dist/preset-data/ 2>/dev/null && echo "UNEXPECTED" || echo "OK — no preset-data in dist"
```

Expected output: `OK — no preset-data in dist`

### 7.5 Verify git state is clean

```bash
git status frontend/
```

Expected: only the deleted `frontend/scripts/generate-preset-manifest.cjs` file shown as
deleted. `frontend/public/preset-data/manifest.json` is gitignored so it should not appear in
`git status` before or after deletion.

## 8. Manual Intervention Required From You

1. **Confirm the `frontend/scripts/` directory may be deleted.** If there are plans to add other
   build scripts in the near future, the directory can be preserved (empty) or re-created later.
   The PRD assumes it is safe to delete the entire `scripts/` directory since it currently holds
   only this one file.

2. **Confirm local disk cleanup scope.** The implementer will `rm` `frontend/public/preset-data/manifest.json`
   from disk as part of this task. If you want the entire `frontend/public/preset-data/` directory
   removed from disk too (it is gitignored and will be empty after the manifest is gone), confirm
   that explicitly — it is harmless either way but good housekeeping.

## 9. Open Questions & Decisions

1. **Delete entire `frontend/scripts/` directory or just the `.cjs` file?**
   `[RESOLVED: Delete the entire directory via git rm -r frontend/scripts/. The directory contains
   exactly one file (the manifest script) and has no other purpose. An empty scripts/ directory
   adds noise.]`

2. **Does removing the generation step break any local dev workflow?**
   `[RESOLVED: No. The script was never needed for local dev (npm run dev uses Vite's dev server,
   not the public/ directory for serving preset files). The backend API serves preset-data files
   directly, so local development is unaffected.]`

3. **Is `frontend/public/preset-data/manifest.json` tracked in git?**
   `[RESOLVED: No. Confirmed by git ls-files frontend/public/preset-data/ returning no output.
   The root .gitignore contains frontend/public/preset-data/ which excludes the whole directory.
   The file exists on disk from a prior build run and must be deleted from disk only — no git
   action required for the manifest file itself.]`

4. **Does Firebase Hosting or any CDN cache the manifest URL?**
   `[DEFERRED: Unknown whether any CDN layer caches /preset-data/manifest.json. Since it was never
   in the deployed bundle (git-tracked source never included it), this is very unlikely. The SPA
   rewrite (`**` → `/index.html`) handles any stale request gracefully. No cache-bust action
   is required for this cleanup.]`

5. **Could the script ever be resurrected for a future use case?**
   `[RESOLVED: No. The initiative decision (locked) is that the frontend calls GET /care_plan/datasets
   to list datasets — it does NOT read manifest.json at runtime. Any future static-serving approach
   would require a new design rather than reviving this script. Deleting it is the correct
   permanent action.]`
