# Code Review — 02-version-config-selection

Branch: `feature/structured-output-grading-batch-input`
Reviewer: automated production-readiness review (review-only, no code modified)
Date: 2026-06-17

---

## Summary verdict — Quality score: 3 / 5

The core mechanism the PRD asked for is implemented and working: the backend collapses to a single
`POST /simplify` route that reads an explicit `version` field, validates it against an allowlist,
falls back to `SIMPLIFY_DEFAULT_VERSION`, rejects unknown values with 400, and dispatches to the
right pipeline. The frontend has a single unified `SimplifyPage` rendered at `/`, a reusable
`ConfigurationCard` with a version dropdown, the `?version=` query-param bridge from
`VersionDetailPage`, and routing has been collapsed. Backend dispatch tests (8) pass, including
invalid-version, default-fallback, JSON-list-injection, empty-string, and old-route-404 cases — this
is genuinely good backend coverage.

The score is held to 3 by one disqualifying defect and several loose ends. **The production frontend
build is broken**: `npm run build` (`tsc -b && vite build`) fails because `router.tsx`'s
`versionPath()` still reads `version.path`, a field the PRD explicitly removed from `config.ts`. The
PRD/TASKS told the implementer to delete `versionPath()` and it was left in. Separately, the three
legacy page files (`V1Page.tsx`, `V1_1Page.tsx`, `V1_2Page.tsx`) were never deleted — they are dead,
no longer routed, and also depend on the removed `version.path`. `SimplifyPage` (632 lines) has zero
tests. There is also a second, likely out-of-scope build error in `normalizeOutput.ts`. As-is this
branch cannot ship a frontend bundle.

---

## Correctness vs PRD / TASKS

| Task | Status | Notes |
|------|--------|-------|
| Task 1 — explicit `version` param in dispatcher | ✅ Done | Reads `request.form` then JSON body, falls back to `SIMPLIFY_DEFAULT_VERSION`, validates against `ALLOWED_VERSIONS`, 400 on unknown. Also hardens against non-str (list/None) — better than the PRD sketch. |
| Task 2 — remove per-version route registrations | ✅ Done | `@route` decorators removed from `simplify_v1_1`/`simplify_v1_2`; `_simplify_document_v1` kept callable; old routes 404 (test-confirmed). |
| `routes/__init__.py` blueprint cleanup | ✅ Done | `simplify_v1_1_bp`/`simplify_v1_2_bp` dropped from `all_blueprints`; grep confirms no remaining routing dependency. |
| Task 3 — simplify `config.ts` | ✅ Done | `path`/`apiPath` removed from `VERSIONS`; `SIMPLIFY_API_PATH = '/simplify'` added; `DEFAULT_VERSION` retained (env-driven, falls back to `v1-2`). Default version is correct (`v1-2`). |
| Task 4 — `ConfigurationCard` | ⚠️ Done with deviation | Built and reused. Markup diverges from the TASKS sketch (no `<h2>Configuration</h2>` heading/`<section>`, uses a flat `glass-card` with label+select). It also already contains the Sub-project-3 grading toggle (`gradingEnabled`/`onGradingEnabledChange`) — scope bleed from SP3, but functional. |
| Task 5 — create `SimplifyPage`, retire legacy pages | ⚠️ Partial | `SimplifyPage` created and POSTs to `SIMPLIFY_API_PATH` with `version` + `grading_enabled`. `?version=` read-on-mount + URL strip implemented. **Legacy `V1Page`/`V1_1Page`/`V1_2Page` were NOT deleted** — dead code still on disk. |
| Task 6 — checkpoint: V1 lab-result rendering | ❓ Unverified | No evidence the lab-result-rendering sign-off was performed before leaving V1Page around. Since V1Page is dead (unrouted) but undeleted, the question is unresolved either way. |
| Task 7 — routing cleanup (`App.tsx`/`router.tsx`/`NavBar.tsx`) | ⚠️ Partial | `App.tsx` collapsed to single `/` route; `*` catch-all redirects to `/`; `NavBar.handleNew` falls back to `navigate('/')`. **`versionPath()` was NOT deleted from `router.tsx`** — TASKS Task 7 explicitly required this, and its presence breaks the build. |
| Task 8 — `VersionDetailPage` CTA | ✅ Done (option b) | The "Use this version" CTA was removed entirely; page is now pure documentation. The `?version=` bridge is still honored by `SimplifyPage` if a link supplies it, but `VersionDetailPage` no longer emits one. Acceptable per PRD §8. |
| Task 9 — tests | ⚠️ Partial | Backend dispatch tests added and passing (exceed the 3 required cases). **`npm run build` does NOT pass** (Task 9 acceptance criterion explicitly requires it). No frontend tests for `SimplifyPage`. |

Default-version correctness: `config.ts` `FALLBACK_VERSION='v1-2'` and backend `SIMPLIFY_DEFAULT_VERSION`
both default to latest. ✅

---

## Bugs & Edge Cases

### CRITICAL

- **C1 — Production frontend build is broken (`router.tsx:9`).**
  `versionPath()` returns `VERSIONS.find(...)?.path ?? '/v1'`, but `path` was removed from every
  `VERSIONS` entry in Task 3. `npm run build` fails:
  `TS2339: Property 'path' does not exist on type ...`. `versionPath()` is now unused by any live page
  (only the dead legacy pages and itself reference it) and must be deleted per TASKS Task 7. **This
  blocks any deploy.** Note: a bare `npx tsc --noEmit` (looser invocation) reports 0 errors, which can
  mask this — the real `tsc -b` build is the source of truth.

### HIGH

- **H1 — Dead legacy pages left on disk** (`pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`,
  `pages/v1_2/V1_2Page.tsx`). They are no longer routed (App.tsx imports only `SimplifyPage`) but are
  still in `src/` (the tsconfig `include: ["src"]` graph) and each imports the now-broken
  `versionPath` and references `version.path`. They contribute to confusion, divergent maintenance,
  and the broken build. PRD/TASKS Task 5/6 required their deletion (after the Task-6 sign-off). Delete
  them (or, if `V1Page`'s lab-result rendering is genuinely needed, port it first — but nothing
  currently routes to it, so this path is effectively already dropped).

- **H2 — Second build error in `normalizeOutput.ts:29`** (`TS2739: Type '{ entries: never[]; }' is
  missing ... enabled, graded_at`). Likely belongs to Sub-project 1/3 (Grading model), not this
  sub-project, but it independently fails the same `npm run build` and must be resolved before the
  frontend ships. Flagged for the aggregating reviewer to route to the correct owner.

### MEDIUM

- **M1 — Selected version is not reset on `handleReset`/"+ New".** `handleReset()` clears files, text,
  steps, result, batch state, etc., but does NOT reset `selectedVersion` or `gradingEnabled` back to
  defaults. This is arguably intentional (a user who picked v1-1 likely wants it to stick across runs),
  but it is undocumented and differs from a "clean upload screen" expectation. Low user impact;
  confirm intent.

- **M2 — `?version=` mount effect can clobber concurrent `location.state` output navigation.** The
  mount effect (lines 78–86) and the `location.state.output` effect (88–103) both call
  `navigate(location.pathname, { replace: true, ... })`. The version effect preserves
  `location.state`, so ordering is probably safe, but the two replace-navigations on mount are
  fragile. An invalid `?version=zzz` is silently ignored (good), but there's no user feedback. Low risk.

- **M3 — Dispatcher reads request body twice.** `simplify_document` calls
  `request.get_json(silent=True)` to look for `version`, and the downstream pipelines
  (`simplify_v1_2`, `_simplify_document_v1`) call `request.get_json`/`request.form` again. For
  multipart form posts this is fine; for a JSON `doc_id` request the body is re-parsed. Flask caches
  the parsed JSON, so this is correct today, but it couples the dispatcher to the inner functions'
  input-resolution assumptions. Not a bug now; a maintenance smell.

### LOW

- **L1 — Deep links to `/v1`, `/v1-1`, `/v1-2` silently redirect to `/`** via the `*` catch-all. PRD
  considered both 404 and redirect acceptable; redirect-to-root is fine but means an old bookmarked
  `/v1-1` link loses the user's version intent (it does NOT pre-select v1-1). Consider mapping legacy
  paths to `/?version=...` if old links matter. Minor.

- **L2 — `ConfigurationCard` dropdown shows both "(latest, default)"** when the latest version is also
  the default (the common case), producing `Version 1.2 (latest, default)`. Slightly redundant label;
  cosmetic.

---

## Test Coverage Gaps

### Backend — strong, a couple of additions

Backend dispatch coverage is good (8 tests): form `version`, JSON `version`, omitted→default, omitted→
latest without monkeypatch, invalid→400, JSON list→400, empty string→400, old routes→404. Add:

- **Form field takes precedence over JSON body** when both are present (precedence is implemented but
  untested).
- **End-to-end pipeline_version assertion**: PRD §7 asked that a `version=v1-1` request actually
  produces `metrics.pipeline_version == "v1-1"` and `simplified_care_plan.version == "1.1"`. Current
  tests mock `simplify_v1_1`/`simplify_v1_2` and only assert the dispatch target — they do NOT verify
  the version actually flows into the emitted envelope. Add one integration test that exercises a real
  (or lightly-stubbed) pipeline and asserts the version mapping (`v1-1↔1.1`, `v1-2↔1.2`).

### Frontend — essentially absent (only 5 tests total, none for SimplifyPage)

`SimplifyPage` (632 lines, the central user-facing component) has zero tests. Highest-value cases:

1. **Version submission**: select `v1-1` in `ConfigurationCard`, submit a file, assert the POST
   `FormData` contains `version=v1-1` and `grading_enabled`.
2. **`?version=` bridge**: mount `SimplifyPage` at `/?version=v1-1`, assert dropdown pre-selects
   `v1-1` and the URL is stripped to `/` (replace navigation).
3. **Invalid `?version=zzz`** is ignored and defaults to `DEFAULT_VERSION`.
4. **`location.state.output` hydration**: navigating in with an output in router state renders the
   result view and strips state.
5. **`handleReset` / "+ New"** returns to the upload screen and clears result/error (and document
   whether version is intentionally preserved — see M1).
6. **SSE result handling**: a `{step:"result", data:...}` event transitions to the result view; a
   malformed line is skipped without crashing.
7. **`ConfigurationCard` unit test**: renders all `VERSIONS`, fires `onVersionChange`, toggles grading.
8. **Build-guard test**: a CI step that runs the real `npm run build` (not just `tsc --noEmit`) so a
   regression like C1 is caught — the current 5 vitest tests do not compile the whole graph.

---

## Security

- ✅ **Server-side version validation** is correct: `version` is checked against
  `ALLOWED_VERSIONS = {"v1","v1-1","v1-2"}` before any dispatch; the client is never trusted. Unknown,
  empty, list, and non-string values all 400. No version string is ever interpolated into a route,
  path, filename, SQL, or shell — dispatch is a fixed `if/elif` over the allowlist, so no injection
  surface.
- ✅ **Auth still enforced**: `@verify_firebase_token` wraps `simplify_document` (the only entry
  point); the inner `simplify_v1_1`/`simplify_v1_2`/`_simplify_document_v1` functions are no longer
  independently routed, so there is no unauthenticated path to them. `simplify_v1_2` reads
  `g.user_id`, which the decorator populates.
- ✅ Old per-version routes are gone (404), removing the alternate ingress.
- ⚠️ Minor: the 400 error echoes the raw rejected version back to the client
  (`"Unknown version '['v1-2']'"`). Low risk (no sensitive data, value is client-supplied), but
  reflecting arbitrary client input in error strings is a mild habit to avoid; consider a generic
  `"Unsupported version"` message.

---

## Logging & Metrics

- The **dispatcher (`simplify_document`) emits no log line or metric recording which version was
  selected.** Per-pipeline modules do their own logging/metrics (`simplify_v1_2.py` uses
  `JunoLogger(api_version="v1-2")` and `JunoMetrics` with `labels={"version": "v1-2"}`; `Metrics.start`
  sets `pipeline_version`), so version IS captured downstream in the envelope and per-pipeline metrics.
  **Gap**: there is no single dispatch-level event (e.g. `logger.info("simplify: dispatch version=%s
  default_used=%s", version, used_default)` plus a `juno_metrics` counter `simplify_dispatch` labeled
  by version and whether the default fallback fired). That dispatch counter is the natural place to
  observe per-version request mix and how often callers omit `version` (rely on the deploy default) —
  currently unobservable at the routing layer. Recommended addition.
- The legacy `_simplify_document_v1` path still uses the stdlib `logging` logger, not `JunoLogger`/
  `JunoMetrics` like v1-1/v1-2 — inconsistent observability across versions (pre-existing, not
  introduced here, but worth noting since all three are now reachable through one route).

---

## Extensibility

- **Adding a new version** today requires: (1) add an entry to `VERSIONS` in `config.ts`; (2) add the
  id to backend `ALLOWED_VERSIONS`; (3) add a branch to the dispatcher `if/elif` chain; (4) add the
  pipeline module. The version↔care-plan-version mapping (`v1↔1.0` etc.) is NOT in a single lookup
  table as the PRD called for — it's hardcoded inside each pipeline (`SimplifiedCarePlan.from_pipeline_result("1.0", ...)`).
  The `ALLOWED_VERSIONS` set is duplicated between `config.ts` (`VERSION_IDS`) and `simplify.py`
  (`ALLOWED_VERSIONS`); they must be kept in sync manually. A shared/derived source (or at least a
  comment cross-referencing them) would reduce drift risk.
- The dispatcher's `if version == "v1-2" ... elif ...` chain is a minor code smell but acceptable at 3
  versions; a `{version: callable}` dict would be cleaner and remove the ordering subtlety.
- **`SimplifyPage` is monolithic (632 lines).** It owns upload UI, single-run SSE parsing, batch SSE
  parsing, result rendering, split-view, download (JSON/PDF), saved-output loading, and two
  `useEffect` navigation bridges. The two SSE-reader loops (single vs batch, lines 169–249 and 272–318)
  are near-duplicate stream-decoding boilerplate that should be factored into a shared
  `readSseStream(response, onEvent)` helper. Extracting the result view, the batch-selector, and the
  SSE plumbing into hooks/components would materially improve testability and is a prerequisite for the
  frontend tests above. `ConfigurationCard` is appropriately small and composable (good — it already
  absorbed the SP3 grading field as a prop, exactly as the PRD intended).

---

## Must-fix before production

1. **[CRITICAL] Delete `versionPath()` from `router.tsx`** (and any remaining `version.path` usage) so
   `npm run build` (`tsc -b`) passes. This is the deploy blocker. (TASKS Task 7.)
2. **[HIGH] Delete the dead legacy pages** `pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`,
   `pages/v1_2/V1_2Page.tsx` (and their now-empty folders) — they are unrouted dead code and also
   depend on the removed `version.path`. Resolve the Task-6 lab-result sign-off (currently nothing
   routes to V1, so the path is already effectively dropped).
3. **[HIGH] Fix `normalizeOutput.ts:29` Grading type error** (or route it to the owning sub-project) —
   it independently fails the production build.
4. **[MEDIUM] Add the missing end-to-end backend test** asserting `metrics.pipeline_version` and
   `simplified_care_plan.version` for a real `version=v1-1` request (PRD §7 wanted this; current tests
   only assert dispatch target via mocks).
5. **[MEDIUM] Add a dispatch-level log + metric** for the selected version and default-fallback usage
   in `simplify_document`.
6. **[MEDIUM] Add minimal `SimplifyPage`/`ConfigurationCard` frontend tests** (version-in-payload,
   `?version=` bridge, reset) and a CI step that runs the real `npm run build`.
7. **[LOW] Confirm intended `selectedVersion`/`gradingEnabled` persistence across "+ New"** (M1) and
   de-duplicate the `ALLOWED_VERSIONS` allowlist between frontend and backend.
