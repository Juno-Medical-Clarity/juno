# PRD: Frontend Alignment to `care_plan`

Sub-project 5 of the Juno refactor. **Phase 2.** Depends on **SP1** (Pydantic models /
`CarePlanInternal` envelope shape — the inner-key decision) and **SP2** (route consolidation —
the `/care_plan*` HTTP paths the frontend now calls). Coordinates with **SP4** (observability —
`X-Session-Id` / `X-Trace-Id` response headers) and **SP6** (frontend tests for the components/pages
this sub-project changes).

## 1. Problem

The frontend still speaks "simplify" and still carries the obsolete v1 / v1.1 surface, even though the
backend is collapsing to a single `care_plan` route running only the v1.2 pipeline:

- **Obsolete version surface.** The app ships dedicated per-version pages
  (`pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`, `pages/v1_2/V1_2Page.tsx`), a generic
  `pages/simplify/SimplifyPage.tsx`, and a version chooser (`VersionsPage.tsx`,
  `VersionDetailPage.tsx`, `ConfigurationCard`'s version `<select>`, `config.ts`'s `VERSIONS` array).
  **Verified:** `V1Page`, `V1_1Page`, and `V1_2Page` are **dead code** — none of them is imported
  anywhere (`App.tsx` wires only `SimplifyPage`, which is a near-clone of `V1_2Page`). The
  `?version=…` bridge, `versionPath()`, and `outputRouteVersionId()` exist solely to route between
  these now-defunct pages. After SP2, `version=v1`/`v1-1` return `400`, so the chooser can offer
  values the backend rejects.

- **`simplify` naming everywhere.** The HTTP path constant (`SIMPLIFY_API_PATH = '/simplify'`),
  hard-coded `/simplify/*` strings in `api/datasets.ts`, `api/savedOutputs.ts`,
  `components/OutputGradingCard.tsx`, the route folder/component (`pages/simplify/SimplifyPage.tsx`),
  and `simplify`-flavoured TS module/symbol names (`types/simplify.ts`, `normalizeSimplifyOutput`,
  `SimplifyOutput`). SP2 has **renamed all backend paths** to `/care_plan*`; the frontend must follow
  or every request 404s after the backend deploys.

- **`appointment` naming.** The owner wants `appointment`/`AppointmentNote` → `care_plan` across the
  frontend (the same intent as backend `appointment_id → care_plan`):
  `components/AppointmentNoteV12View.tsx`, the `AppointmentNote` interface in `types/simplify.ts`, and
  the `import type { AppointmentNote }` in `types/envelope.ts`. (Note: the wire field `doc_type:
  "appointment_note"` is the LLM's document-classification value and is **owned by SP1's model**, not
  renamed here — see §4 and §9.)

- **Correlation headers are wired but inert.** `utils/logger.ts` exposes `setSessionId()`, but
  **nothing ever calls it** (verified). The envelope already carries `metrics.session_id` (rendered as
  "Request ID"), but the frontend never reads the `X-Session-Id` response header, and SP4's
  `X-Trace-Id` is not consumed.

## 2. Goals

1. **Remove the obsolete version surface.** Delete the three dead per-version pages and decide the
   fate of the version chooser. After SP2 there is exactly one pipeline (`v1-2`); the UI should stop
   presenting version as a user choice.
2. **Rename `simplify` → `care_plan`** across HTTP path strings, the path constant, the route
   folder/page/component name, and `simplify`-flavoured TS symbols — with a complete old→new map (§4).
3. **Consume the new envelope cleanly.** Keep the app working against `CarePlanInternal.to_dict()`.
   Handle the inner-key ambiguity (`simplified_care_plan` vs `care_plan`) so the frontend works
   whether SP1/SP2 keep the legacy key (Phase 1 default) **or** flip it to `care_plan`.
4. **Rename `appointment`/`AppointmentNote` → `care_plan`** in frontend component/type names.
5. **Read correlation headers.** After each `/care_plan` response, read `X-Session-Id` (and
   `X-Trace-Id` if SP4 exposes it) and feed them to `logger.setSessionId()` / `logger`.
6. **Keep the app working end-to-end** with the refactored backend (full alignment — the owner's
   choice).

## 3. Non-Goals

- **Not** redesigning the care-plan rendering UI, the grading cards, or PDF/JSON export logic — only
  renaming/rewiring. `AppointmentNoteV12View`'s render output stays pixel-identical; we only rename
  the file/symbol and its prop/type imports.
- **Not** writing the test suite — SP6 owns Vitest/RTL. This PRD only flags which pages/components/
  utils need tests after the change (§7).
- **Not** changing the backend, the envelope wire keys, or the SSE event shapes — SP1/SP2 own those.
  SP5 only *consumes* them.
- **Not** building the `X-Trace-Id` plumbing on the backend — SP4 owns whether/how that header is
  emitted. SP5 reads it defensively if present.
- **Not** migrating Firestore documents or the saved-output legacy-shape handling
  (`normalizeOutput.ts` legacy branch stays as-is; it is still needed for old saved docs).

## 4. Architecture Decisions

### 4.1 Files to DELETE (dead code + obsolete surface)

| File | Why |
|---|---|
| `frontend/src/pages/v1/V1Page.tsx` | Dead — not imported anywhere; v1 pipeline dropped by SP2. |
| `frontend/src/pages/v1_1/V1_1Page.tsx` | Dead — not imported anywhere; v1.1 pipeline dropped by SP2. |
| `frontend/src/pages/v1_2/V1_2Page.tsx` | Dead — not imported anywhere; superseded by `SimplifyPage` (its near-identical, live twin). |

**Verification before deleting:** `grep -rn "V1Page\|V1_1Page\|V1_2Page" frontend/src` returns only
self-references plus the CSS import (`V1_1Page.css`, handled in §4.3). Confirmed at planning time.

### 4.2 Version-chooser decision (OPEN — see §9, default proposed here)

Only `v1-2` survives. Proposed default: **collapse version to a non-user-facing constant; remove the
chooser UI but keep `VERSIONS` as a single-entry array for labels/metadata.**

- `config.ts`: reduce `VERSION_IDS` / `VERSIONS` to the single `v1-2` entry; keep
  `DEFAULT_VERSION = 'v1-2'`. The `version` form field is still sent (value always `'v1-2'`) so the
  backend contract is unchanged and SP2's `ALLOWED_VERSIONS = {"v1-2"}` accepts it.
- `ConfigurationCard.tsx`: **remove the version `<select>`** (a one-option dropdown is dead UX); keep
  the "Enable grading" checkbox. The component keeps the `version`/`onVersionChange` props as a no-op
  for now **or** drops them (small judgement call — flagged in §9).
- `VersionsPage.tsx` + `VersionDetailPage.tsx` + the `/versions` and `/version/:id` routes in
  `App.tsx` + the "Versions" link in `NavBar.tsx`: **remove** (recommended — they describe pipelines
  that no longer exist). Alternative: keep `VersionsPage` as a read-only "How it works" page. **Owner
  decision — §9.**
- `router.tsx` (`versionPath`, `VersionRouteState`) + `utils/outputVersion.ts`
  (`outputRouteVersionId`): `versionPath` and `outputRouteVersionId` exist only to route *between*
  version pages. With one page, `versionPath` is unused after the dead pages are deleted (only
  `SimplifyPage` reads `VersionRouteState.output`, never calls `versionPath`).
  - **Keep:** `VersionRouteState` (still used by `SimplifyPage` for the saved/split-view → result
    hand-off).
  - **Delete:** `versionPath()` (and its `router.test.ts`) and `utils/outputVersion.ts` +
    `outputVersion` usages — all callers are the deleted pages. Verified: after deleting the three
    pages, `grep versionPath`/`outputRouteVersionId` returns no live references.

### 4.3 `V1_1Page.css` (shared stylesheet — must be preserved)

`pages/v1_1/V1_1Page.css` is imported by the **live** `SimplifyPage.tsx` (and the dead v1_2 page). It
holds the result-card / score / upload styles the app actually renders. Deleting `pages/v1_1/`
wholesale would break styling. **Move/rename** it to `pages/care-plan/CarePlanPage.css` and update the
import in the renamed page (§4.4). Do not delete it.

### 4.4 Rename `simplify` → `care_plan` (and the route page)

The live page `pages/simplify/SimplifyPage.tsx` becomes `pages/care-plan/CarePlanPage.tsx`
(component `CarePlanPage`). Update `App.tsx`'s import + JSX. The route path stays `/` (this is the
app's single working surface).

#### Complete old → new rename map

**HTTP path strings & constant** (backend contract from SP2 — mandatory):

| Location | Old | New |
|---|---|---|
| `config.ts` const name | `SIMPLIFY_API_PATH` | `CARE_PLAN_API_PATH` |
| `config.ts` const value | `'/simplify'` | `'/care_plan'` |
| `api/datasets.ts` | `GET /simplify/datasets` | `GET /care_plan/datasets` |
| `api/datasets.ts` | `GET /simplify/datasets/<g>/<i>/<f>` | `GET /care_plan/datasets/<g>/<i>/<f>` |
| `api/datasets.ts` | `POST /simplify/batch` | `POST /care_plan/batch` |
| `api/savedOutputs.ts` | `GET /simplify/saved` | `GET /care_plan/saved` |
| `api/savedOutputs.ts` | `GET /simplify/saved/<id>` | `GET /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `PATCH /simplify/saved/<id>` | `PATCH /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `DELETE /simplify/saved/<id>` | `DELETE /care_plan/saved/<id>` |
| `api/savedOutputs.ts` | `GET /simplify/saved/<id>/input-pdf-url` | `GET /care_plan/saved/<id>/input-pdf-url` |
| `components/OutputGradingCard.tsx` | `POST ${API_URL}/simplify/grade` | `POST ${API_URL}/care_plan/grade` |
| (live page) form submit | `POST ${API_URL}${SIMPLIFY_API_PATH}` | `POST ${API_URL}${CARE_PLAN_API_PATH}` |

**TS files / symbols** (frontend-internal naming — SP2 §6 says these are SP5's call):

| Kind | Old | New |
|---|---|---|
| Route folder + page file | `pages/simplify/SimplifyPage.tsx` | `pages/care-plan/CarePlanPage.tsx` |
| Page component | `SimplifyPage` | `CarePlanPage` |
| Shared CSS | `pages/v1_1/V1_1Page.css` | `pages/care-plan/CarePlanPage.css` |
| Type module | `types/simplify.ts` | `types/carePlan.ts` |
| Normalizer fn | `normalizeSimplifyOutput` | `normalizeCarePlanOutput` |
| Normalizer file | `utils/normalizeOutput.ts` | `utils/normalizeOutput.ts` (keep file name; rename fn) |
| Envelope alias type | `SimplifyOutput` | `CarePlanInternal` (keep `SimplifyOutput` as a deprecated re-export alias for one cycle — mirrors SP1's backend alias) |
| Component file | `components/AppointmentNoteV12View.tsx` | `components/CarePlanView.tsx` |
| Component symbol | `AppointmentNoteV12View` | `CarePlanView` |
| Interface | `AppointmentNote` (in `types/simplify.ts`) | `CarePlanContent` (in `types/carePlan.ts`) |

**UI copy** (cosmetic, non-blocking; align language with "care plan"): "Simplify My Note →",
"Your Simplified Note", "Simplify another note", "Simplifying your note…", and the `<title>` /
download filenames (`simplified-document.json`) can be reworded to "care plan" framing. Flagged in §9
as owner copy review — not required for correctness.

> **Renames are mechanical but wide.** Do them with a symbol-rename refactor (or careful
> find-replace + `tsc --noEmit`) so every import site updates. After deleting the dead pages (§4.1)
> the only live consumers are `App.tsx`, the renamed page, `OutputGradingCard.tsx`, `SplitView`
> (receives the rendered view as a child), and the `api/*` modules.

### 4.5 Envelope consumption + the inner-key ambiguity (the important part)

**What SP1/SP2 actually decided (verified in their PRDs):**
- The envelope class `SimplifyOutput` → `CarePlanInternal`. **JSON wire keys are unchanged**:
  `{ metrics, input, grading, simplified_care_plan }`.
- SP1 keeps the **serialized inner key as `simplified_care_plan`** via a Pydantic
  `serialization_alias="simplified_care_plan"` while the Python attribute becomes `care_plan`, and
  accepts **both** keys on input via `validation_alias=AliasChoices("care_plan",
  "simplified_care_plan")`.
- SP2's default is **keep `simplified_care_plan` in Phase 1** (wire stability); flipping the wire key
  to `care_plan` is explicitly deferred to "a later phase, frontend in lockstep."

**Therefore SP5's stance:** the response key the frontend reads **today** is `simplified_care_plan`.
But to be robust to (a) old saved Firestore docs, (b) a future SP2 flip to `care_plan`, and (c) SP1's
dual-accept aliasing, SP5 must read the inner care plan **key-agnostically**.

**Decision — centralize key access in the normalizer.** `normalizeCarePlanOutput` (formerly
`normalizeSimplifyOutput`) becomes the single place that resolves the inner key, and it always
produces an envelope with a stable internal key. Two sub-options:

- **Option A (recommended, lowest churn): keep the internal field name `simplified_care_plan`** in the
  TS `CarePlanInternal` type, and have the normalizer accept either wire key:

  ```ts
  // utils/normalizeOutput.ts
  export function normalizeCarePlanOutput(raw: any): CarePlanInternal {
    if (raw == null) throw new Error('normalizeCarePlanOutput: null/undefined output');
    // Resolve inner key from either alias (SP1/SP2 may emit `care_plan` or `simplified_care_plan`).
    const innerKey = 'simplified_care_plan' in raw ? 'simplified_care_plan'
                   : 'care_plan' in raw ? 'care_plan'
                   : null;
    if (innerKey) {
      const plan = raw[innerKey];
      return { ...raw, simplified_care_plan: plan };   // normalize to one internal key
    }
    // ...existing legacy flat-shape branch unchanged...
  }
  ```
  All downstream consumers (`CarePlanView`, `buildPdfHtml`, `OutputGradingCard`) keep reading
  `output.simplified_care_plan`. When SP2 flips the wire key, **only the normalizer changes** (one
  line already handles it). Net frontend churn for the flip: zero.

- **Option B: rename the internal field to `care_plan`** in the TS type and everywhere it's read, with
  the normalizer mapping `simplified_care_plan → care_plan`. This is the "fully consistent" end state
  but touches every read site (`CarePlanView`, `SimplifyPage`/`CarePlanPage`, `buildPdfHtml`,
  `OutputGradingCard`, `SplitView` call sites). **Defer to whenever SP2 flips the wire key** —
  pairing the internal rename with the wire flip keeps it one coordinated change instead of two.

**Recommendation:** ship **Option A now** (key-agnostic normalizer, internal name stays
`simplified_care_plan`). It satisfies "consume the new envelope" and de-risks the future flip without
a large rename. Note in §9 that the Option B internal rename is the natural follow-up when SP2 flips
the wire key.

**`metrics.session_id`** is unchanged and already read (rendered as "Request ID"); keep it.

### 4.6 `appointment` → `care_plan`

- `components/AppointmentNoteV12View.tsx` → `components/CarePlanView.tsx`, symbol
  `AppointmentNoteV12View` → `CarePlanView`. Update both call sites (the live page renders it twice —
  inline result + inside `SplitView`).
- `types/simplify.ts`'s `AppointmentNote` interface → `CarePlanContent` in `types/carePlan.ts`. Update
  `types/envelope.ts`'s `import type { AppointmentNote }` accordingly. The derived
  `SimplifiedCarePlan = Omit<CarePlanContent,'version'> & { version: string }` keeps its name (it's
  already "care plan"-named) **or** is renamed to match Option A/B — keep as `SimplifiedCarePlan` for
  now.
- **Do NOT rename** `doc_type: 'appointment_note'` — that's the LLM document-classification literal,
  owned by SP1's `CarePlan` model. Leave the field and its literal value as-is (§9 notes SP1 owns any
  future change there).

### 4.7 Correlation headers (`X-Session-Id` / `X-Trace-Id`)

The SSE responses go through `authenticatedFetch`. After the streaming `POST /care_plan` (and
`/care_plan/batch`, `/care_plan/grade`) responses arrive, read the headers off the `Response` object
and hand them to the logger:

```ts
const sessionId = response.headers.get('X-Session-Id');
if (sessionId) logger.setSessionId(sessionId);
const traceId = response.headers.get('X-Trace-Id');   // SP4 — may be absent
if (traceId) logger.info('trace_id', { traceId });
```

Place this in the renamed page right after each `authenticatedFetch(...)` returns and `response.ok` is
confirmed, before reading the body stream. `setSessionId` is currently never called — this is the
fix. Prefer the **header** value; fall back to the envelope's `metrics.session_id` for the
"Request ID" display (the header is the correlation source of truth; the body value is the display
value, and they should match).

> **CORS caveat (manual — §8).** `X-Session-Id` / `X-Trace-Id` are non-simple headers; the browser
> only exposes them to JS if the backend sends `Access-Control-Expose-Headers: X-Session-Id,
> X-Trace-Id`. SP4/SP2 own the backend CORS config (there is an active `fixing-cors` branch). If those
> headers aren't exposed, `response.headers.get(...)` returns `null` and the frontend silently falls
> back to the body `session_id` — no crash, but no header correlation either.

### 4.8 Router / Nav changes (summary)

- `App.tsx`: import `CarePlanPage` (was `SimplifyPage`); remove `/versions` + `/version/:id` routes
  and their imports (if version pages removed per §4.2/§9).
- `NavBar.tsx`: remove the "Versions" `<Link to="/versions">` (if removed) — leaves "Juno" brand +
  "+ New".
- `router.tsx`: keep `VersionRouteState`; remove `versionPath` (+ delete `router.test.ts` or replace
  with a SP6 test for whatever helper remains). `utils/outputVersion.ts` deleted.

## 5. API Change Summary

The frontend now calls only the `/care_plan*` surface (SP2 contract). No request/response **body**
changes — bodies and SSE event shapes are byte-identical; only **path strings** change, plus the new
**header reads**.

| Frontend caller | Method + new path |
|---|---|
| `CarePlanPage` submit | `POST /care_plan` (multipart: `files[]`/`file`/`text`, `version`=`v1-2`, `grading_enabled`) → SSE, final `data` = `CarePlanInternal.to_dict()` |
| `api/datasets.ts` `runBatch` | `POST /care_plan/batch` (JSON `{version, selections, grading_enabled}`) → SSE |
| `api/datasets.ts` `listDatasets` | `GET /care_plan/datasets` |
| `api/datasets.ts` `getDatasetFileContent` | `GET /care_plan/datasets/<g>/<i>/<f>` |
| `api/savedOutputs.ts` list/get/rename/delete/pdf-url | `GET/PATCH/DELETE /care_plan/saved[/<id>][/input-pdf-url]` |
| `components/OutputGradingCard.tsx` | `POST /care_plan/grade` (JSON `{saved_id}` or `{text, clarified_text}`) → `{ grading }` |

**Headers read (new):** `X-Session-Id` (correlation; → `logger.setSessionId`), `X-Trace-Id`
(SP4, optional; → `logger`). Both depend on backend `Access-Control-Expose-Headers` (§8).

## 6. Frontend Change Summary (file-by-file plan)

**DELETE**
- `pages/v1/V1Page.tsx`, `pages/v1_1/V1_1Page.tsx`, `pages/v1_2/V1_2Page.tsx` (dead).
- `utils/outputVersion.ts` (only the dead pages used `outputRouteVersionId`).
- `router.test.ts` (tests the soon-deleted `versionPath`; SP6 replaces).
- *(pending §9 owner call)* `pages/VersionsPage.tsx`, `pages/VersionDetailPage.tsx`.

**MOVE / RENAME**
- `pages/v1_1/V1_1Page.css` → `pages/care-plan/CarePlanPage.css` (live styles; keep contents).
- `pages/simplify/SimplifyPage.tsx` → `pages/care-plan/CarePlanPage.tsx`, component `CarePlanPage`;
  update its CSS import to the moved file.
- `components/AppointmentNoteV12View.tsx` → `components/CarePlanView.tsx` (symbol `CarePlanView`).
- `types/simplify.ts` → `types/carePlan.ts`; interface `AppointmentNote` → `CarePlanContent`.
- `normalizeSimplifyOutput` → `normalizeCarePlanOutput` (file stays `utils/normalizeOutput.ts`).
- `SimplifyOutput` type → `CarePlanInternal` (keep `SimplifyOutput` re-export alias one cycle).

**EDIT**
- `config.ts`: rename `SIMPLIFY_API_PATH` → `CARE_PLAN_API_PATH = '/care_plan'`; collapse `VERSION_IDS`
  / `VERSIONS` to the single `v1-2` entry; keep `DEFAULT_VERSION='v1-2'`.
- `App.tsx`: import/render `CarePlanPage`; remove version routes + imports (per §9).
- `NavBar.tsx`: remove "Versions" link (per §9).
- `ConfigurationCard.tsx`: remove the version `<select>` + `VERSIONS` import; keep grading checkbox;
  drop/neutralize `version`/`onVersionChange` props.
- `api/datasets.ts`, `api/savedOutputs.ts`, `components/OutputGradingCard.tsx`: swap `/simplify*` →
  `/care_plan*` path strings (and use `CARE_PLAN_API_PATH` where a const fits).
- `utils/normalizeOutput.ts`: rename fn; add the **key-agnostic inner-key resolution** (§4.5 Option A);
  keep the legacy flat-shape branch.
- `utils/grading.ts`, `utils/buildPdfHtml.ts`: update type imports (`AppointmentNote`→`CarePlanContent`,
  `types/simplify`→`types/carePlan`, `SimplifyOutput`→`CarePlanInternal`); no logic change.
- `CarePlanPage.tsx` (renamed): use `CARE_PLAN_API_PATH`; render `CarePlanView`; call
  `normalizeCarePlanOutput`; **add the `X-Session-Id`/`X-Trace-Id` header reads** after each fetch;
  remove the now-defunct `?version=` mount effect + version-selection wiring (single version);
  reword UI copy per §9 (optional).
- `types/envelope.ts`: rename `SimplifyOutput`→`CarePlanInternal` (+alias); update the
  `AppointmentNote`→`CarePlanContent` import; keep wire-key field `simplified_care_plan` (§4.5 A).

**UNCHANGED (no edits)**
- `Sidebar.tsx`, `SplitView.tsx`, `PresetDataCard.tsx`, `DatasetGroupRow.tsx`, `MedicalTerm.tsx`,
  `LoginPage.tsx`, `auth/*`, `api/firebase.ts`, `api/apiClient.ts`, `utils/logger.ts`,
  `utils/groupSavedOutputs.ts`, `types/datasets.ts`. (They reference renamed symbols only through the
  page/types, which the rename updates — no hand edits.) `apiClient.ts` does **not** need changes for
  headers; the page reads them off the returned `Response`.

## 7. Testing (handed to SP6)

After this sub-project, SP6 should add/adjust:

- `utils/normalizeOutput.test.ts` — **extend**: assert key-agnostic resolution (input with
  `care_plan` key, input with `simplified_care_plan` key, and legacy flat shape all normalize to one
  internal `simplified_care_plan`). The existing legacy-grading test stays.
- `utils/grading.ts` — `patientScoreFromGrading` / `methodEntriesFromGrading` selectors (empty
  entries → `null`; combined+method extraction; before/after split).
- `components/CarePlanView.tsx` (RTL) — renders summary/sections; readability + method cards appear
  only when grading entries exist; medical-term highlighting.
- `components/OutputGradingCard.tsx` (RTL) — POSTs to `/care_plan/grade`; `saved_id` vs
  `text/clarified_text` body selection; `onGraded` updates.
- `pages/care-plan/CarePlanPage.tsx` (RTL/integration) — SSE parse → result render; **reads
  `X-Session-Id` and calls `logger.setSessionId`**; sends `grading_enabled`.
- `ConfigurationCard.tsx` — grading checkbox toggles (version select removed).
- **Delete/replace** `router.test.ts` (its `versionPath` subject is removed).

## 8. Manual Intervention Required From You

1. **Lockstep deploy (hard cut).** SP2's default is a hard path cut: once the backend serves
   `/care_plan*` only, the old frontend 404s, and once this frontend ships, an old backend 404s.
   **Deploy backend (SP2) and this frontend together**, or have SP2 keep `/simplify*` aliases live for
   one release first (SP2 §9.1). You own release ordering.
2. **`Access-Control-Expose-Headers` for `X-Session-Id` / `X-Trace-Id`.** The browser will not expose
   these response headers to JS unless the backend sends them in `Access-Control-Expose-Headers`. This
   is backend/SP4/SP2 CORS config (note the active `fixing-cors` branch). Without it, header
   correlation silently no-ops (frontend falls back to the body `session_id`). Confirm the CORS config
   exposes them.
3. **`VITE_DEFAULT_VERSION` env var.** `config.ts` reads it. With one version it's effectively dead;
   you can leave it (ignored) or remove it from `.env*` files. No deploy action strictly required.
4. **No Firebase / `VITE_*` / deployed-URL changes** are needed by SP5 (`api/firebase.ts`,
   `VITE_API_PROCESSING_URL` unchanged).
5. **UI copy review** (cosmetic, §9): approve reworded "simplify"→"care plan" user-facing strings, or
   keep current copy.

## 9. Open Questions

1. **Inner envelope key (the headline ambiguity).** SP1/SP2 default to keeping the wire key
   `simplified_care_plan` (SP1 accepts both via `AliasChoices`; SP2 defers the flip). **SP5 assumes
   `simplified_care_plan` is the live key and reads key-agnostically (§4.5 Option A).** If/when SP2
   flips the wire key to `care_plan`, SP5 needs only the one-line normalizer change (Option A) — or
   pairs the internal-field rename (Option B) with that flip. **Confirm: ship Option A now?**
2. **Version chooser fate (§4.2).** Recommended: remove `VersionsPage`/`VersionDetailPage`, the
   `/versions` + `/version/:id` routes, the NavBar "Versions" link, and `ConfigurationCard`'s version
   `<select>` (only `v1-2` exists). Alternative: keep `VersionsPage` as a static "How it works" page.
   **Owner call.** (Affects how much of `router.tsx`/`config.ts` is trimmed.)
3. **Keep `SimplifyOutput`/`SimplifyPage` aliases for one cycle, or hard rename now?** Recommended:
   hard rename internally (frontend has no external consumers of these symbols) but keep a
   `SimplifyOutput` type re-export alias to mirror SP1's backend alias and ease review. **Owner call.**
4. **`doc_type: 'appointment_note'`.** Left unchanged (LLM classification literal, SP1-owned). Confirm
   the owner's "appointment→care_plan everywhere" intent applies to **frontend symbol names only**,
   not this wire literal. (Renaming the literal is a coordinated SP1 model + LLM-prompt change, out of
   SP5 scope.)
5. **UI copy** (§8.5) — reword user-facing "simplify"/"note" strings to "care plan", or keep?
