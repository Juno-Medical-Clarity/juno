# Tasks: Version Selection via Config

Read `PRD.md` in this folder first.

---

### Task 1 — Backend: explicit `version` param in the dispatcher

**File:** `backend/routes/simplify.py`

In `simplify_document()` (currently lines 93–105), replace the unconditional
`if SIMPLIFY_DEFAULT_VERSION == "v1-2": ...` chain with:
```python
ALLOWED_VERSIONS = {"v1", "v1-1", "v1-2"}

@simplify_bp.route("/simplify", methods=["POST"])
@verify_firebase_token
def simplify_document(user_id: str):
    _ = user_id
    version = request.form.get("version") or (request.get_json(silent=True) or {}).get("version") or SIMPLIFY_DEFAULT_VERSION
    if version not in ALLOWED_VERSIONS:
        return {"error": f"Unknown version '{version}'"}, 400
    if version == "v1-2":
        return simplify_v1_2()
    if version == "v1-1":
        return simplify_v1_1()
    return _simplify_document_v1()
```
(`request.form.get` covers multipart requests; the JSON fallback covers `doc_id`-only requests if
those are sent as JSON — check `simplify_v1_2.py`'s existing input-resolution code to confirm whether
`doc_id` requests arrive as JSON or form data today, and match that.)

**Acceptance criteria:** Existing manual/automated calls that don't pass `version` still get
`SIMPLIFY_DEFAULT_VERSION`'s behavior unchanged. A call with `version=v1-1` reaches the v1-1 pipeline.
A call with `version=bogus` gets a 400.

**Depends on:** nothing (Sub-project 1's models aren't touched by this task itself, only by the
routes' internals, which already exist by the time this is implemented).

---

### Task 2 — Backend: remove per-version route registrations

**Files:** `backend/routes/simplify.py`, `backend/routes/simplify_v1_1.py`, `backend/routes/simplify_v1_2.py`, `backend/routes/__init__.py`

- In `simplify.py`: delete the `@simplify_bp.route("/simplify/v1", methods=["POST"])` decorator and
  the `simplify_document_v1` wrapper function above it (lines ~84–90); keep `_simplify_document_v1()`
  itself untouched and callable.
- In `simplify_v1_1.py`: find and remove the `@simplify_v1_1_bp.route("/simplify/v1-1", ...)`
  decorator from the `simplify_v1_1` function, keeping the function itself.
- In `simplify_v1_2.py`: same — remove `@simplify_v1_2_bp.route("/simplify/v1-2", ...)` from
  `simplify_v1_2`, keep the function.
- In `routes/__init__.py`: `simplify_v1_1_bp` and `simplify_v1_2_bp` now have zero routes registered
  on them. Flask blueprints with no routes are harmless to keep registered, but cleaner to remove them
  from `all_blueprints` — before doing so, `grep -rn "simplify_v1_1_bp\|simplify_v1_2_bp"
  backend/` to confirm nothing else depends on them being registered blueprints (e.g. blueprint-level
  error handlers or `before_request` hooks scoped to that blueprint). If nothing depends on it, drop
  both from the `all_blueprints` list and the corresponding imports.

**Acceptance criteria:** `POST /simplify/v1`, `/simplify/v1-1`, `/simplify/v1-2` all return 404.
`POST /simplify` with the right `version` param still reaches each pipeline (covered by Task 1's
tests).

**Depends on:** Task 1.

---

### Task 3 — Frontend: simplify `config.ts`

**File:** `frontend/src/config.ts`

Remove `path` and `apiPath` from each entry in `VERSIONS`. Add:
```ts
export const SIMPLIFY_API_PATH = '/simplify';
```
Keep `id`, `label`, `description`, `steps`, `isDefault`, and `DEFAULT_VERSION`.

**Acceptance criteria:** `grep -rn "\.apiPath\|\.path\b" frontend/src` finds no remaining usages tied
to `VERSIONS` entries after Tasks 4–7 are also done (this task alone will temporarily break callers —
that's expected, fixed by later tasks in this list).

**Depends on:** nothing.

---

### Task 4 — Frontend: build `ConfigurationCard` component

**File (new):** `frontend/src/components/ConfigurationCard.tsx`

A card component (reuse the existing `glass-card` styling convention used elsewhere, e.g. in
`VersionsPage.tsx`) with:
```tsx
interface ConfigurationCardProps {
  version: string;
  onVersionChange: (id: string) => void;
}

export default function ConfigurationCard({ version, onVersionChange }: ConfigurationCardProps) {
  return (
    <section className="glass-card configuration-card">
      <h2>Configuration</h2>
      <label className="config-field">
        <span>Version</span>
        <select value={version} onChange={e => onVersionChange(e.target.value)}>
          {VERSIONS.map(v => (
            <option key={v.id} value={v.id}>{v.label}{v.isDefault ? ' (latest)' : ''}</option>
          ))}
        </select>
      </label>
    </section>
  );
}
```
Keep this intentionally small and composable — Sub-project 3 will add a grading-toggle field to this
same component, so leave room (e.g. accept children, or just add the new field directly when that
sub-project is implemented) rather than hardcoding "this card only ever has one field."

**Acceptance criteria:** Renders standalone in isolation (Storybook not required — just confirm it
compiles and looks reasonable when dropped into a page in Task 6).

**Depends on:** Task 3.

---

### Task 5 — Frontend: create `SimplifyPage`, retire `V1_2Page`/`V1Page`/`V1_1Page`

**Files (new):** `frontend/src/pages/simplify/SimplifyPage.tsx` (moved/renamed from
`frontend/src/pages/v1_2/V1_2Page.tsx`)
**Files (deleted, after Task 6's checkpoint is resolved):** `frontend/src/pages/v1/V1Page.tsx`,
`frontend/src/pages/v1_1/V1_1Page.tsx`, and their folders if nothing else lives in them.

1. Copy `V1_2Page.tsx` to the new path/name. Update its internal upload-submit logic to POST to
   `SIMPLIFY_API_PATH` (`/simplify`) with a `version` field equal to the currently-selected version
   from state (default = `DEFAULT_VERSION`), instead of a hardcoded `/simplify/v1-2`.
2. Render `<ConfigurationCard version={version} onVersionChange={setVersion} />` below the existing
   upload cards on the upload screen (`AppState === 'upload'` branch).
3. Add a `version` query-param read on mount: if `?version=v1-1` (etc.) is present in the URL, use it
   to initialize the `version` state, then strip it from the URL (`navigate('/', { replace: true })`
   or equivalent) so it doesn't linger.

**Acceptance criteria:** Visiting `/` shows the upload screen with the Configuration card; submitting
with each version selected reaches the right pipeline (manual check via `/run`).

**Depends on:** Tasks 1, 2, 4.

---

### Task 6 — ⚠️ Checkpoint before deleting V1/V1.1 pages

Before deleting `V1Page.tsx`/`V1_1Page.tsx`: diff their rendering logic against `SimplifyPage.tsx`
(the former `V1_2Page.tsx`). Specifically check whether V1 renders a `lab_result` doc type differently
than V1.2's view component handles it (V1's pipeline historically supported `lab_result` per
`config.ts`'s V1 description: "Supports provider notes, appointment summaries, lab results...").

**This determination needs your sign-off, not a dev agent's** — if lab-result rendering is
meaningfully different and still wanted, port that rendering into the shared result view before
deleting `V1Page.tsx`; if lab results are no longer a supported/used path, confirm that and proceed
with deletion as-is.

**Depends on:** Task 5 (need the new page to diff against).

---

### Task 7 — Frontend: routing cleanup

**Files:** `frontend/src/App.tsx`, `frontend/src/router.tsx`, `frontend/src/components/NavBar.tsx`

- `App.tsx`: replace the `/v1`, `/v1-1` routes and the `/` redirect-to-`versionPath` with a single
  `<Route path="/" element={<SimplifyPage />} />`. Remove the separate `/v1-2` route block (the
  comment about it managing its own NavBar still applies to `SimplifyPage` — keep it outside
  `AuthLayout` the same way the old `/v1-2` route was, or fold it in if `AuthLayout` is now compatible;
  check `AuthLayout.tsx` before deciding).
- `router.tsx`: delete `versionPath()` if nothing else uses it after this change
  (`grep -rn "versionPath" frontend/src`).
- `NavBar.tsx`: change `handleNew`'s fallback from `navigate(versionPath(DEFAULT_VERSION))` to
  `navigate('/')`.

**Acceptance criteria:** `/v1`, `/v1-1` resolve to nothing meaningful (404 or redirect to `/`, your
call — `*` catch-all already redirects to `/` per the existing pattern, so this likely falls out for
free). `/` shows `SimplifyPage`. "+ New" button returns to a clean upload screen.

**Depends on:** Task 5, Task 6 (don't delete routes to pages you haven't confirmed are safe to delete).

---

### Task 8 — Frontend: `VersionDetailPage` CTA

**File:** `frontend/src/pages/VersionDetailPage.tsx`

⚠️ **Checkpoint:** confirm with the user whether to (a) change the "Use this version →" button to
`navigate('/?version=' + version.id)`, or (b) remove the button entirely and leave this page as pure
documentation. PRD.md §8 flags this as your call. Implement whichever is chosen.

**Acceptance criteria:** Clicking the (possibly removed) CTA does not navigate to a dead route.

**Depends on:** Task 7.

---

### Task 9 — Tests

**Files:** `backend/tests/` (new or existing `test_simplify_routes.py`)

Add the three tests described in PRD.md §7 (version dispatch, default fallback, invalid version → 400).
Run the full backend suite and the frontend typecheck/build to confirm nothing references deleted
routes/exports.

**Acceptance criteria:** `pytest backend/tests/` and `npm run build` (in `frontend/`) both pass.

**Depends on:** Tasks 1–8.

---

## Summary of what requires you (not a dev agent)

1. **Task 6** — sign off on whether V1's lab-result rendering needs porting before its page is deleted.
2. **Task 8** — choose between the `?version=` redirect bridge or removing the CTA entirely on
   `VersionDetailPage`.
