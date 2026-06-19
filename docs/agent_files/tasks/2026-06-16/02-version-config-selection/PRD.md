# PRD: Version Selection via Config (Single Endpoint + Dropdown)

Sub-project 2 of 5. **Depends on Sub-project 1** (the `Metrics.pipeline_version` field and
`SimplifiedCarePlan.version` field it reads/sets already exist by the time this ships). Can be built
in parallel with Sub-project 1 by a different agent if you want to move faster, but don't deploy this
one before Sub-project 1 lands — it produces envelopes via the Sub-project 1 models.

## 1. Problem

Today, which pipeline version runs is determined by the **URL**: `/simplify/v1`, `/simplify/v1-1`,
`/simplify/v1-2` on the backend; `/v1`, `/v1-1`, `/v1-2` pages on the frontend. There's also a fourth
backend route, `/simplify`, that silently picks a version based on the `SIMPLIFY_DEFAULT_VERSION`
env var — a deploy-time setting, not a per-request choice.

You want version selection to be a **per-request, in-UI choice** (a dropdown in the Configuration
card on the upload screen and on the output screen), defaulting to latest, with no version baked into
the URL at all.

## 2. Goals

- One backend route (`POST /simplify`) that accepts an explicit `version` parameter and dispatches to
  the right pipeline. Default = latest when omitted.
- One frontend page (no more `/v1`, `/v1-1`, `/v1-2` routes) with a version dropdown inside a
  Configuration card, default = latest, can pick an older version.
- Remove the old per-version routes/pages entirely (confirmed decision — no aliasing/redirects kept).

## 3. Non-Goals

- Not changing what each pipeline version does internally.
- Not building the grading toggle yet (Sub-project 3 extends the same Configuration card with it).
- Not touching the batch/dataset flow (Sub-project 4) — version selection there reuses this same
  dropdown/param, no new mechanism.

## 4. Architecture Decisions

**Canonical version identifier.** Keep the existing strings (`"v1"`, `"v1-1"`, `"v1-2"`) as the
identifier used in the API param, `Metrics.pipeline_version`, and the frontend dropdown's `value` —
this matches what Sub-project 1 already wrote into `Metrics.pipeline_version` and avoids a second
naming scheme. `SimplifiedCarePlan.version` keeps its own `"1.0"/"1.1"/"1.2"` strings (already
established in Sub-project 1); the mapping between the two is `v1↔1.0`, `v1-1↔1.1`, `v1-2↔1.2` and
lives in one small lookup table, not duplicated logic.

**Backend: collapse to one route.** `backend/routes/simplify.py` already contains a dispatcher
(`simplify_document`, registered at `POST /simplify`) that picks a version via
`SIMPLIFY_DEFAULT_VERSION` and calls straight through to `_simplify_document_v1()`, `simplify_v1_1()`,
or `simplify_v1_2()` as plain Python functions (not via Flask routing — it imports the view functions
and calls them directly). This means the dispatch plumbing already exists; this sub-project's backend
work is smaller than it looks:
1. Make the dispatcher read an explicit `version` request field (form field for multipart requests,
   JSON field for `doc_id`/JSON requests) instead of only `SIMPLIFY_DEFAULT_VERSION`. Validate against
   `{"v1", "v1-1", "v1-2"}`; reject unknown values with 400. Fall back to `SIMPLIFY_DEFAULT_VERSION`
   only when the field is absent (so deploy-time default behavior is preserved for any caller that
   doesn't pass `version` yet).
2. Delete the route registrations for `/simplify/v1` (in `simplify.py`), `/simplify/v1-1` (in
   `simplify_v1_1.py`), `/simplify/v1-2` (in `simplify_v1_2.py`) — **keep the underlying functions**
   (`_simplify_document_v1`, `simplify_v1_1`, `simplify_v1_2`), just remove their `@blueprint.route(...)`
   decorators/registrations so they're plain callables again, only reachable through the `/simplify`
   dispatcher.
3. Update `backend/routes/__init__.py` `all_blueprints` if removing a route empties a blueprint
   (it won't — `simplify_v1_1_bp` and `simplify_v1_2_bp` still need to exist as the modules' blueprint
   objects even with zero registered routes on them, OR simplest: stop registering those two
   blueprints in `all_blueprints` entirely since after this change they have no routes left. Confirm
   no other code imports `simplify_v1_1_bp`/`simplify_v1_2_bp` for routing purposes before removing).

**Frontend: collapse to one page.** Keep `V1_2Page.tsx` as the surviving page (it's the most complete
implementation and already manages its own NavBar per the `App.tsx` comment) — rename it
`SimplifyPage.tsx` under `frontend/src/pages/simplify/` to avoid the version number being baked into
the filename of what's now a version-agnostic page. Delete `V1Page.tsx` and `V1_1Page.tsx` and their
folders once their unique logic (if any beyond what V1.2's page already does — check before deleting,
e.g. V1 may have lab-result-specific UI that V1.2 doesn't) is confirmed redundant or ported.

**Configuration card (new, scaffolded here, extended in Sub-project 3).** A new card on the upload
screen, below the existing upload-mode cards, titled "Configuration", containing for now just:
- A version `<select>` populated from `VERSIONS` in `config.ts`, default = the entry where
  `isDefault` is true, value passed as the `version` field on the `/simplify` request.

The PRD for Sub-project 3 will add a grading on/off toggle into this same card — building it as a
reusable `ConfigurationCard` component now (not page-specific markup) means that addition is a prop,
not a rewrite.

**`config.ts` changes.** `VERSIONS` entries drop `path` and `apiPath` (no longer meaningful — there's
one path and one API endpoint now). Keep `id`, `label`, `description`, `steps`, `isDefault`. Add a
single constant `SIMPLIFY_API_PATH = '/simplify'`.

**Versions browsing pages (`VersionsPage.tsx`, `VersionDetailPage.tsx`).** These remain — they're
useful read-only documentation of what each version's pipeline does, and nothing in the user's request
asks to remove the ability to browse version descriptions. What changes is their call-to-action:
`VersionDetailPage`'s "Use this version →" button currently does `navigate(version.path)` (navigates to
a dead route after this change). Replace it with `navigate(`/?version=${version.id}`)` — the single
`SimplifyPage` reads a `?version=` query param on mount (if present) to pre-select that option in the
Configuration card's dropdown, then the param can be dropped from the URL (don't keep version in the
URL long-term, per your explicit instruction — it's just used once to carry the click-through intent).

**Routing (`App.tsx`).** Replace the `/v1`, `/v1-1`, `/v1-2` routes and the `Navigate to={versionPath(...)}`
redirects with a single `/` route rendering `SimplifyPage`. `versionPath()` helper in `router.tsx` is
deleted (no longer has a use). `NavBar`'s "+ New" button navigates to `/` (or calls the page's own
reset handler, as it already optionally does via the `onNew` prop) instead of
`versionPath(DEFAULT_VERSION)`.

## 5. API Change Summary

```
POST /simplify
  multipart/form-data or application/json, adds one new optional field:
    version: "v1" | "v1-1" | "v1-2"   (default: SIMPLIFY_DEFAULT_VERSION env var, i.e. "latest")

Removed:
  POST /simplify/v1
  POST /simplify/v1-1
  POST /simplify/v1-2
```

## 6. Frontend Change Summary

- Routes: `/` → `SimplifyPage` (only top-level functional route besides `/versions`, `/version/:id`,
  login).
- New `ConfigurationCard` component (`frontend/src/components/ConfigurationCard.tsx`) with a version
  dropdown, rendered on the upload screen below existing cards.
- `VersionDetailPage`'s CTA redirects to `/?version=<id>` instead of a dead per-version route.
- `config.ts` simplified as described above.

## 7. Testing

- Backend: route test hits `POST /simplify` with `version: "v1-1"` and asserts
  `metrics.pipeline_version == "v1-1"` and `simplified_care_plan.version == "1.1"`; a second test omits
  `version` and asserts it falls back to `SIMPLIFY_DEFAULT_VERSION`'s mapped version; a third test
  passes an invalid value and asserts 400.
- Frontend: manual run (`/run` skill) — submit through the Configuration card with each version
  selected, confirm the right pipeline steps/labels show in the SSE progress UI for each.
- Confirm `/simplify/v1`, `/simplify/v1-1`, `/simplify/v1-2` now 404.

## 8. Manual Intervention Required From You

- **Decide before deleting `V1Page.tsx`/`V1_1Page.tsx`:** confirm neither has UI behavior unique to it
  (e.g. V1 supports `lab_result` doc type display that V1.2 might not render). If V1 has unique
  rendering for non-appointment doc types, that rendering needs to be ported into the single page
  before the old page is deleted — flagged as a checkpoint in TASKS.md Task 6, not something a dev
  agent should decide unilaterally.
- **Confirm the `?version=` query-param bridge from `VersionDetailPage`** is acceptable, versus simply
  removing the "Use this version" button entirely and leaving `VersionsPage`/`VersionDetailPage` as
  pure documentation with no CTA. Either is a small change; pick one before Task 9.
