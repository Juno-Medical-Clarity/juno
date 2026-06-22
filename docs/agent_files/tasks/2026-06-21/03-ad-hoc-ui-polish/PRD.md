# PRD: Ad Hoc UI Polish (SP3)

Sub-project 3 of 6 — depends on SP1 (Firestore status contract) for the sidebar processing indicator. SP3 itself touches only frontend files, adds two new pages (ModelsPage, GradingVersionDetailPage), and wires the sign-out button. No backend API changes.

## 1. Problem

The current UI has several rough edges:

- The sidebar has a fixed, rigid width — no resize handle and no collapse. On small screens it crowds the content area.
- Sidebar item sort order matches API return order (oldest-first within a date group); the user's most recent work is at the bottom.
- Items with rows that are padding-heavy make the list feel bloated.
- No in-sidebar indicator for in-progress jobs (SP1 is adding async job tracking; SP3 must surface it).
- NavBar has the "+ New" button in the top-right and "Versions" as a link — inconsistent with the locked design (New as center link, Models as center link, Sign Out top-right).
- The `/versions` route and page label say "Versions" everywhere; the locked decision renames it to "Models".
- The Models page (VersionsPage) only shows pipeline versions — it needs a second "Grading Versions" section.
- No grading version detail page exists at all.
- No timestamp is shown under the "Your Care Plan" heading.
- A "🔒 Deleted from servers" badge appears in `CarePlanPage.tsx:521` — this messaging was removed in the locked decisions.
- Spacing between the NavBar and first card, and between cards on the upload page, is tight with no explicit gap.

## 2. Goals

1. Sidebar resize: drag handle on right edge; min 180 px, default 240 px, max 400 px; persist to `localStorage`.
2. Sidebar collapse: collapse/expand icon in header replacing the "+ New" button; collapsed state renders a ~40 px strip; persist to `localStorage`.
3. Sidebar items: sort latest-first within each date group; reduce row padding for compactness.
4. Sidebar processing indicator: items with `status=not_started|processing` show a CSS spinner; three-dot menu hidden while processing. Data source: SP1's Firestore onSnapshot (interface designed here; SP1 implements the data).
5. NavBar: "New" as `<Link to="/">` and "Models" as `<Link to="/models">` in the center; Sign Out button top-right; remove old "+ New" button and "Versions" link.
6. Route `/versions` renamed to `/models`; `VersionsPage` renamed to `ModelsPage`.
7. ModelsPage: keep existing pipeline versions table; add a second "Grading Versions" section (table). Each row links to `/models/grading/<version-id>`.
8. Grading version detail page at `/models/grading/:versionId`: lists scoring methods, sub-scores, and links to `/docs/<slug>` (SP4 owns those pages).
9. Output view: timestamp line "Simplified on `<date>`" rendered under "Your Care Plan" `<h2>` heading.
10. Remove the `🔒 Deleted from servers` `<span>` from `CarePlanPage.tsx`.
11. Spacing: add top gap between NavBar and first card on all pages; add vertical gap between upload page cards.

## 3. Non-Goals

- SP5 redesigns `OutputGradingCard` — SP3 does NOT touch that component's internals.
- SP4 owns `/docs/<slug>` pages — SP3 only links to them.
- SP1 owns the Firestore data model and writes for job status — SP3 only reads from the onSnapshot subscription SP1 exposes.
- SP2 owns backend route changes and the `ApiError` type — SP3 uses SP2's `ApiError` TS type for any new error display, but SP3 itself has no new error flows.
- Backend API changes: none.
- Mobile/responsive layout: not in scope beyond sidebar collapse making the page usable at narrower widths.
- Route `/carePlan/<id>` (SP1's concern): SP3 must not break or re-implement this routing. The Sidebar's `onSelect` callback navigates there; SP3 does not change the navigation target.

## 4. Architecture Decisions

### 4.1 Sidebar resize + collapse — state management

**Current state:** `Sidebar.tsx` is a self-contained `<aside className="sidebar">`. `CarePlanPage.tsx` hard-codes `marginLeft: '260px'` on the content wrapper and the CSS fixes `width: 260px` on `.sidebar`. Both must become dynamic.

**Approach — CSS custom property driven by React state:**

```
// Sidebar.tsx owns sidebarWidth and isCollapsed as local state.
// CarePlanPage.tsx receives sidebarWidth via a ref callback or a lifted state.
```

Because `CarePlanPage.tsx` hard-codes `marginLeft: '260px'` on the content div, SP3 must lift the effective sidebar width to the parent. Two options:

- **Option A (preferred):** Pass a CSS variable to `document.documentElement` so `.sidebar` and the margin are driven by the same token, avoiding prop drilling.
- **Option B:** Lift `sidebarWidth` and `isCollapsed` to `CarePlanPage.tsx` and pass them down.

**Decision: Option A** — simpler, requires no prop change to `CarePlanPage`. The `Sidebar` sets `--sidebar-width` on mount and on every drag/collapse event; the content wrapper reads `marginLeft: var(--sidebar-width)`. The CSS `.sidebar { width: var(--sidebar-width); }` replaces the fixed `260px`.

**Interaction rule (collapse × resize):**
- While `isCollapsed === true`, the resize handle is `pointer-events: none` (not draggable). The CSS variable is set to the collapsed strip width (`40px`), overriding any stored pixel value.
- On expand, `--sidebar-width` is restored to the last persisted `sidebarWidth` value (from localStorage).
- `sidebarWidth` in state always holds the expanded width (never 40 px) — the collapsed strip is an override, not a mutation of the stored width.

**localStorage keys:**

| Key | Value | Default |
|---|---|---|
| `juno_sidebar_width` | number (px) | `240` |
| `juno_sidebar_collapsed` | `"true"` \| `"false"` | `"false"` |

**Collapse toggle placement:** The header row currently has `<span class="sidebar-title">Saved</span>` on the left and `<button class="sidebar-new-btn">+ New</button>` on the right. The "+ New" button is removed from the sidebar header. In its place: a collapse arrow icon (`‹` when expanded, `›` when collapsed). When collapsed, the sidebar-title is hidden (no room); the arrow remains visible and centered in the 40 px strip.

**Old → new in `Sidebar.tsx` header:**
```
// OLD
<div className="sidebar-header">
  <span className="sidebar-title">Saved</span>
  <button className="sidebar-new-btn" onClick={onNew}>+ New</button>
</div>

// NEW
<div className="sidebar-header">
  {!isCollapsed && <span className="sidebar-title">Saved</span>}
  <button className="sidebar-collapse-btn" onClick={toggleCollapse}
    aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
    {isCollapsed ? '›' : '‹'}
  </button>
</div>
```

**Drag handle:** A `<div className="sidebar-resize-handle">` absolutely positioned at `right: 0, top: 0, bottom: 0, width: 6px`. `onMouseDown` attaches a `document.mousemove` listener that updates `sidebarWidth` clamped to [180, 400] and updates `--sidebar-width`. `onMouseUp` detaches the listener and persists to localStorage. Handle is hidden (`display: none`) when `isCollapsed`.

**SidebarProps interface change:** The `onNew` prop is removed (the collapse toggle replaces the "+ New" button). Callers (`CarePlanPage.tsx`) drop `onNew` from the `<Sidebar>` element. `CarePlanPage.tsx` still owns `handleReset` for the NavBar's "New" link.

```typescript
// OLD
interface SidebarProps {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshTrigger: number;
}

// NEW
interface SidebarProps {
  activeId: string | null;
  onSelect: (id: string) => void;
  refreshTrigger: number;
  processingIds?: Set<string>;  // injected by CarePlanPage from Firestore subscription (see 4.4)
}
```

### 4.2 Sidebar item sort order

**File:** `frontend/src/utils/groupSavedOutputs.ts`

The current `groupSavedOutputs` function pushes each `SavedOutputMeta` into a date-bucket in the order `outputs` arrives (API order). The API returns items in Firestore query order — currently unspecified but effectively oldest-first within a date.

**Fix:** After grouping into date buckets, sort each bucket's items by `created_at` descending before partitioning into batches and standalones.

```typescript
// Inside groupSavedOutputs, after collecting items per date:
const items = byDate.get(date)!.sort(
  (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
);
```

The date group order itself (`dateOrder`) also becomes latest-first: push dates into `dateOrder` but sort `dateOrder` descending before mapping.

### 4.3 Sidebar item compactness

**File:** `frontend/src/components/Sidebar/Sidebar.css`

Current `.sidebar-item` padding: `10px 16px`. Reduce to `7px 12px`. Current `.sidebar-item-name` font-size: `0.85rem`. Reduce to `0.82rem`. Net effect: each row is ~6 px shorter; no structural change to the rendered DOM.

| Selector | Old value | New value |
|---|---|---|
| `.sidebar-item` padding | `10px 16px` | `7px 12px` |
| `.sidebar-item-name` font-size | `0.85rem` | `0.82rem` |

### 4.4 Sidebar processing indicator — SP1 interface contract

**Context:** SP1 is adding async Firestore job status. Each `care_plan_output` document will have a `status` field: `not_started`, `processing`, `done`, `error`. SP3 needs to surface `not_started` and `processing` with a spinner.

**Design decision — hybrid data strategy (not full Firestore migration):**
The sidebar list still loads via `listSavedOutputs()` REST call on mount (unchanged). A separate Firestore `onSnapshot` subscription overlays live status for in-progress items. The REST list gives the full ordered list; onSnapshot patches `status` for items that are actively running. When `status` transitions to `done`, the sidebar triggers a refresh (calls `fetchOutputs()`) to pick up the real name if it changed.

**Why not move the whole sidebar to Firestore?** The REST API is already tested, paginated-ready, and handles batch groups. Moving to Firestore means re-implementing grouping logic in a listener. Hybrid keeps existing code stable; only the status overlay is new.

**SP1 contract SP3 needs:**

SP1 must expose a React hook (or a raw Firestore subscription path) that SP3 can subscribe to. Proposed interface:

```typescript
// SP1 owns implementing this hook in e.g. frontend/src/api/useJobStatuses.ts
type JobStatus = 'not_started' | 'processing' | 'done' | 'error';

interface UseJobStatusesResult {
  statuses: Map<string, JobStatus>;  // keyed by care_plan_output document ID
}

export function useJobStatuses(): UseJobStatusesResult;
```

SP3 calls `useJobStatuses()` in `CarePlanPage.tsx`, builds a `Set<string>` of IDs where status is `not_started | processing`, and passes it as `processingIds` to `<Sidebar>`. When a job moves to `done`, SP3 triggers `setSidebarRefresh(r => r + 1)` to force a REST reload.

**Detection of transition to done:** Inside `CarePlanPage`, compare the previous `statuses` Map to the new one in a `useEffect`. When any ID's status changes from `processing` → `done`, trigger `setSidebarRefresh`.

**In-sidebar rendering (in `renderRow`):**

```typescript
// If processingIds?.has(output.id), show spinner; hide three-dot menu
const isProcessing = props.processingIds?.has(output.id) ?? false;

// In JSX:
{isProcessing ? (
  <span className="sidebar-spinner" aria-label="Processing" />
) : (
  <button className="sidebar-menu-btn" ...>⋯</button>
)}
```

CSS for `.sidebar-spinner`: a small 12 px CSS keyframe animation (border-radius 50%, rotating border) using `var(--accent-violet)` color.

**If SP1 is not yet landed:** `processingIds` defaults to `undefined` (the prop is optional). When undefined, the spinner is never shown and the three-dot menu always appears. SP3 degrades gracefully.

### 4.5 NavBar

**File:** `frontend/src/components/NavBar.tsx`

Current structure: brand left, `top-nav-actions` right with `<Link to="/versions">Versions</Link>` + `<button>+ New</button>`.

New structure: brand left, center links, sign-out right.

```tsx
// NEW NavBar.tsx (full replacement)
import { Link } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { firebaseAuth } from '../api/firebase';

export default function NavBar() {
  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav-brand">
        <span className="top-nav-logo">Juno</span>
      </div>
      <div className="top-nav-center">
        <Link to="/" className="top-nav-link">New</Link>
        <Link to="/models" className="top-nav-link">Models</Link>
      </div>
      <div className="top-nav-right">
        <button
          className="sign-out-button"
          type="button"
          onClick={() => void signOut(firebaseAuth)}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
```

The existing `SignOutButton` component (`frontend/src/auth/SignOutButton.tsx`) inlines perfectly here; the import stays clean. SP3 can either import `SignOutButton` or inline the button — both are equivalent. The `onNew` prop is removed entirely from `NavBarProps` (it is no longer needed; "New" is a `<Link to="/">`).

**CSS changes in `App.css`:**

The `.top-nav` currently uses `justify-content: space-between` with two flex children (brand + actions). Three regions (brand, center, right) need `display: grid; grid-template-columns: 1fr auto 1fr` or `position: absolute` centering. Use the grid approach:

```css
/* NEW .top-nav layout */
.top-nav {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  /* existing: position fixed, height 48px, padding, background, etc. — unchanged */
}

.top-nav-brand  { justify-self: start; }
.top-nav-center { display: flex; align-items: center; gap: 4px; }
.top-nav-right  { display: flex; align-items: center; justify-content: flex-end; }
```

Remove `.top-nav-actions` (old right section) and `.top-nav-new-btn` CSS (the "+ New" button class is gone). The `sign-out-button` class already exists in `App.css` (lines 275–293) and needs no change.

**Callers to update:**
- `frontend/src/components/AuthLayout.tsx`: currently `<NavBar />` (no props) — no change needed (onNew is already optional).
- `frontend/src/pages/care-plan/CarePlanPage.tsx`: currently `<NavBar onNew={handleReset} />` — remove the `onNew` prop. `handleReset` is still called by other things internally but no longer wired to the NavBar.

### 4.6 Route rename: `/versions` → `/models`

**Files:** `frontend/src/App.tsx`, `frontend/src/components/NavBar.tsx` (already addressed in 4.5).

In `App.tsx`:
```tsx
// OLD
import VersionsPage from './pages/VersionsPage';
// ...
<Route path="/versions" element={<VersionsPage />} />

// NEW
import ModelsPage from './pages/ModelsPage';
// ...
<Route path="/models" element={<ModelsPage />} />
<Route path="/models/grading/:versionId" element={<GradingVersionDetailPage />} />
```

**File rename:** `frontend/src/pages/VersionsPage.tsx` → `frontend/src/pages/ModelsPage.tsx`. This is a file rename + content update (see 4.7). No other files outside `App.tsx` and `NavBar.tsx` hardcode `/versions` (confirmed by grep — only those two locations).

**`AuthLayout.tsx`:** currently wraps only `/versions`. After SP3 it wraps `/models` and `/models/grading/:versionId`. Both new routes belong inside the `<Route element={<AuthLayout />}>` wrapper since they require auth.

### 4.7 ModelsPage (formerly VersionsPage)

**File:** `frontend/src/pages/ModelsPage.tsx` (renamed from `VersionsPage.tsx`)

The existing pipeline versions table is kept unchanged. A second section is added below:

```tsx
<section style={{ marginTop: '48px' }}>
  <h2>Grading Versions</h2>
  <div className="versions-table-wrap glass-card">
    <table className="versions-table">
      <thead>
        <tr>
          <th>Version</th>
          <th>Description</th>
          <th>Methods</th>
        </tr>
      </thead>
      <tbody>
        {GRADING_VERSIONS.map(v => (
          <tr key={v.id}>
            <td>
              <Link to={`/models/grading/${v.id}`} className="version-table-link">
                {v.label}
              </Link>
              {v.isDefault && <span className="version-default-badge">Default</span>}
            </td>
            <td>{v.description}</td>
            <td>{v.methods.join(', ')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
</section>
```

**Data source for grading versions — config file (static):**

The grading version data is static (only one grading version exists: `"1.0"`). Adding it to `frontend/src/config.ts` is the simplest approach. No backend API needed.

Add to `frontend/src/config.ts`:

```typescript
export const GRADING_VERSIONS = [
  {
    id: 'v1-0',
    label: 'Grading Version 1.0',
    description: 'Multi-method readability and patient health literacy scoring. Computes six individual method scores and a combined composite score.',
    methods: ['SMOG', 'Flesch-Kincaid', 'Dale-Chall', 'PEMAT', 'SAM', 'CDC CCI'],
    isDefault: true,
  },
] as const;
```

### 4.8 Grading version detail page

**File:** `frontend/src/pages/GradingVersionDetailPage.tsx` (new file)

**Route:** `/models/grading/:versionId`

**Data source:** Static config in `frontend/src/config.ts`. The detail page looks up `GRADING_VERSIONS.find(v => v.id === versionId)` using `useParams()`. If not found, renders a "not found" state with a back link.

**Content per grading version detail:**

The page shows two sections:

1. **Individual scoring methods** — a card or table row for each of the six methods with:
   - Method name (e.g. "SMOG")
   - What it measures (from `GradingMethodReason` enum in `backend/models/grading.py` — these strings should be mirrored in the config)
   - Sub-scores in its `grade_breakdown` (described statically per method — see table below)
   - A link to `/docs/<slug>` (SP4's page, which may 404 until SP4 lands — that is acceptable)

2. **Combined / final score** — description of the composite score, how it is weighted.

**Per-method data to hardcode in config:**

| Method ID | Label | Measures (from GradingMethodReason) | Breakdown sub-scores | Docs slug |
|---|---|---|---|---|
| `smog` | SMOG | Polysyllabic word count; designed for health materials (McLaughlin 1969) | `polysyllable_count`, `sentence_count`, `raw_grade` | `smog` |
| `flesch_kincaid` | Flesch-Kincaid | Sentence length × syllable load; Reading Ease + Grade Level (1975) | `reading_ease`, `grade_level`, `avg_sentence_length`, `avg_syllables_per_word` | `flesch-kincaid` |
| `dale_chall` | Dale-Chall | Difficult words outside the 3,000 familiar-word list (1948/1995) | `difficult_word_count`, `pct_difficult`, `raw_score` | `dale-chall` |
| `pemat` | PEMAT | Automated AHRQ approximation: understandability + actionability (2013) | `understandability`, `actionability` | `pemat` |
| `sam` | SAM | Content, literacy demand, and layout/typography domains (Doak et al. 1996) | `content_score`, `literacy_demand`, `layout_score` | `sam` |
| `cdc_cci` | CDC CCI | Main message, behavioral recommendations, numbers, call-to-action (CDC) | `main_message`, `behavioral_recommendations`, `numbers_score`, `call_to_action` | `cdc-cci` |

**Combined score description (hardcoded):**
The composite score is a weighted average of the six method scores, normalized to 0–100. A higher score means higher readability/accessibility. The `grade_estimate` and `label` fields describe the approximate reading-grade equivalent.

**Layout:** Reuse `.app-shell`, `.hero-section`, `.versions-table-wrap`, `.glass-card` from existing CSS. Add a back link using the existing `.version-detail-back` class. The App.css already has `.version-detail-*` classes defined (lines 1405–1492) that were pre-built for a version detail page — reuse them.

```tsx
// Skeleton structure
export default function GradingVersionDetailPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const version = GRADING_VERSION_DETAILS.find(v => v.id === versionId);

  if (!version) {
    return (
      <main className="app-shell">
        <section className="hero-section">
          <Link to="/models" className="version-detail-back">← Back to Models</Link>
          <p className="version-detail-not-found">Grading version not found.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className="hero-section">
        <Link to="/models" className="version-detail-back">← Back to Models</Link>
        <div className="version-detail-meta">
          <h1>{version.label}</h1>
          {version.isDefault && <span className="version-default-badge">Default</span>}
        </div>
        <p className="version-detail-description">{version.description}</p>

        <h2 style={{ ... }}>Scoring Methods</h2>
        {/* one card per method */}
        {version.methodDetails.map(method => (
          <div key={method.id} className="glass-card" style={{ marginBottom: '16px', padding: '20px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <h3>{method.label}</h3>
              <a href={`/docs/${method.docsSlug}`} className="top-nav-link">Docs →</a>
            </div>
            <p>{method.description}</p>
            <p><strong>Sub-scores:</strong> {method.breakdownKeys.join(', ')}</p>
          </div>
        ))}

        <h2 style={{ ... }}>Combined Score</h2>
        <div className="glass-card" style={{ padding: '20px 24px' }}>
          <p>{version.combinedDescription}</p>
        </div>
      </section>
    </main>
  );
}
```

**Config addition:** `GRADING_VERSION_DETAILS` (detail-level array) extends `GRADING_VERSIONS` with `methodDetails` and `combinedDescription`. Add to `frontend/src/config.ts`.

### 4.9 Timestamp under "Your Care Plan" heading

**File:** `frontend/src/pages/care-plan/CarePlanPage.tsx`

The `result-header` block at line 519–535 currently has:
```tsx
<div className="result-header">
  <h2 className="result-title">Your Care Plan</h2>
  <span className="deleted-note">🔒 Deleted from servers</span>
  ...
</div>
```

After SP3:
```tsx
<div className="result-header">
  <div>
    <h2 className="result-title">Your Care Plan</h2>
    {result.metrics.created_at && (
      <p className="result-timestamp">
        Simplified on {new Date(result.metrics.created_at).toLocaleDateString('en-US', {
          month: 'long', day: 'numeric', year: 'numeric',
        })}
      </p>
    )}
  </div>
  {/* deleted-note span REMOVED */}
  ...
</div>
```

The `created_at` field is already on `Metrics` in `frontend/src/types/envelope.ts` (line 57: `created_at: string`). No type changes needed.

Add to `App.css`:
```css
.result-timestamp {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-top: 4px;
  font-weight: 500;
}
```

### 4.10 Remove "Deleted from servers" copy

**File:** `frontend/src/pages/care-plan/CarePlanPage.tsx` line 521.

Remove the entire `<span className="deleted-note">🔒 Deleted from servers</span>` element. The `.deleted-note` CSS class in `App.css` (lines 618–629) can be left or removed — removing it is cleaner since nothing else uses it.

### 4.11 NavBar-to-content spacing + card gaps

**Upload page card gaps:**

The upload page in `CarePlanPage.tsx` renders three cards back-to-back inside `.upload-section`:
1. The main glass card (upload/paste zone) — rendered as `<div className="glass-card" style={{ padding: '32px' }}>`
2. `<PresetDataCard />` — no explicit top margin
3. `<ConfigurationCard />` — no explicit top margin

Apply `margin-top: 16px` to `PresetDataCard` and `ConfigurationCard` via CSS or via wrapping divs. The cleanest approach is a CSS rule for `.upload-section > * + *` (sibling combinator) so any future cards also get the gap:

```css
/* Add to App.css or CarePlanPage.css */
.upload-section > * + * {
  margin-top: 16px;
}
```

**NavBar-to-content gap:**

The content wrapper in `CarePlanPage.tsx` currently has `paddingTop: '48px'` (NavBar height) with no additional gap. The `.app-shell` class (used by VersionsPage/ModelsPage) already adds `padding: calc(48px + 40px) 24px 64px` (40 px above the content). CarePlanPage's content wrapper needs the same treatment:

```tsx
// CarePlanPage.tsx content wrapper:
// OLD
<div style={{ flex: 1, marginLeft: '260px', minWidth: 0, paddingTop: '48px' }}>

// NEW — use CSS variable for sidebar margin, add 40px gap
<div style={{ flex: 1, marginLeft: 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: 'calc(48px + 40px)' }}>
```

`AuthLayout`-wrapped pages (ModelsPage, GradingVersionDetailPage) already use `.app-shell` which has the correct padding. No change needed there.

## 5. API Change Summary

No backend API changes. SP3 reads from SP1's Firestore subscription (via the `useJobStatuses` hook SP1 provides) — this is a frontend-only integration.

## 6. Frontend Change Summary

### Files modified

| File | Change |
|---|---|
| `frontend/src/components/Sidebar/Sidebar.tsx` | Add resize handle, collapse toggle, `isCollapsed` + `sidebarWidth` state, `--sidebar-width` CSS variable, `processingIds` prop, spinner in `renderRow`, sort latest-first items; remove `onNew` prop |
| `frontend/src/components/Sidebar/Sidebar.css` | Add `.sidebar-resize-handle`, `.sidebar-collapse-btn`, `.sidebar-spinner` keyframe, `.sidebar-spinner` styles; reduce `.sidebar-item` padding and `.sidebar-item-name` font-size; make width dynamic |
| `frontend/src/components/NavBar.tsx` | Three-column grid layout; center "New" + "Models" links; right Sign Out button; remove `onNew` prop and "+ New" button and "Versions" link |
| `frontend/src/components/AuthLayout.tsx` | No change needed (already `<NavBar />` with no props) |
| `frontend/src/App.css` | Add `.top-nav-center`, `.top-nav-right`; update `.top-nav` to grid layout; add `.result-timestamp`; add `.upload-section > * + *` gap rule; optionally remove `.deleted-note` and `.top-nav-new-btn` |
| `frontend/src/App.tsx` | Change route `/versions` → `/models`; add route `/models/grading/:versionId`; import `ModelsPage` and `GradingVersionDetailPage` |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | Remove `onNew` from `<Sidebar>` and `<NavBar>`; remove `deleted-note` span; add timestamp under heading; update content wrapper paddingTop and marginLeft to use CSS var; wire `processingIds` from `useJobStatuses` |
| `frontend/src/utils/groupSavedOutputs.ts` | Sort items latest-first within each date group; sort date groups latest-first |
| `frontend/src/config.ts` | Add `GRADING_VERSIONS` and `GRADING_VERSION_DETAILS` exports |

### Files renamed

| Old path | New path |
|---|---|
| `frontend/src/pages/VersionsPage.tsx` | `frontend/src/pages/ModelsPage.tsx` |

### Files added

| File | Purpose |
|---|---|
| `frontend/src/pages/GradingVersionDetailPage.tsx` | New route `/models/grading/:versionId` |

### Interface SP3 needs from SP1

SP1 must ship the following before SP3's processing indicator can be wired up:

```typescript
// File: frontend/src/api/useJobStatuses.ts  (SP1 creates this)
type JobStatus = 'not_started' | 'processing' | 'done' | 'error';
export function useJobStatuses(): { statuses: Map<string, JobStatus> };
```

If SP1 is not yet landed, SP3's `processingIds` prop is `undefined` and the sidebar degrades to current behavior (no spinners, three-dot menu always shown).

### Interface SP3 uses from SP2

SP2 defines a TypeScript `ApiError` type. SP3 currently has no new error display surfaces; if SP3 surfaces any error state (e.g. in the detail page when data fails to load), it must use SP2's `ApiError` shape. Since all grading version data in SP3 is static config, no network errors are expected in the new pages.

### Links SP3 adds for SP4

The grading version detail page links to `/docs/<slug>` for each scoring method. SP4 owns those pages. Until SP4 lands, the links 404. This is acceptable — SP3 renders them as `<a href="/docs/smog">` etc. (not `<Link>` through React Router, since SP4 may implement `/docs` routes separately).

## 7. Testing

### Unit tests (existing test files to update)

- `frontend/src/tests/utils/groupSavedOutputs.test.ts` (create if missing): verify that within a date group, items are ordered latest `created_at` first; verify date groups are ordered latest first.
- `frontend/src/tests/components/` — no existing Sidebar test; add a minimal snapshot or behavior test for the collapse toggle and that `processingIds` hides the three-dot menu.

### Manual tests

1. **Sidebar resize:** Drag the right edge. Width clamps to 180/400 px. Refresh — width restored from localStorage.
2. **Sidebar collapse:** Click arrow. Sidebar shrinks to 40 px strip; content area expands. Click again — restores last width. Refresh — collapsed state restored.
3. **Collapse × resize:** With sidebar collapsed, attempt to drag resize handle — it should not respond.
4. **Processing indicator:** Trigger a job via SP1. The matching sidebar item should show a spinner and no three-dot menu. After job completes, spinner disappears and three-dot menu reappears.
5. **NavBar:** "New" link navigates to `/`. "Models" link navigates to `/models`. "Sign out" signs out and lands on the login page (LoginPage renders when `user === null`).
6. **Route rename:** `/versions` no longer exists (redirected to `/` by the `*` catch-all). `/models` renders the Models page. `/models/grading/v1-0` renders the grading detail.
7. **ModelsPage:** Both tables render. Pipeline versions table unchanged. Grading Versions table shows v1.0 with a link to `/models/grading/v1-0`.
8. **GradingVersionDetailPage:** All six methods render with names, descriptions, sub-score lists, and `/docs/<slug>` links. Combined score section renders.
9. **Timestamp:** After a run completes, `Simplified on <date>` appears under "Your Care Plan" heading.
10. **No deletion copy:** The `🔒 Deleted from servers` badge does not appear anywhere.
11. **Card spacing:** Upload page has visible gaps between the upload card, PresetDataCard, and ConfigurationCard. Top gap between NavBar and first card is consistent with the Models page spacing.

## 8. Manual Intervention Required From You

1. **Confirm `/docs/<slug>` link format with SP4.** SP3 hardcodes links like `/docs/smog`, `/docs/flesch-kincaid`, etc. SP4 should confirm these slugs before SP3 ships; otherwise the links must be updated. If SP4 uses a different URL scheme (e.g. `/docs/grading/smog`), update `GRADING_VERSION_DETAILS` in `config.ts`.

2. **Confirm SP1's `useJobStatuses` hook interface.** SP3 designs this interface; SP1 implements it. Before wiring the processing indicator in `CarePlanPage.tsx`, confirm with SP1 that the hook returns `Map<string, JobStatus>` keyed by care_plan_output document ID (which matches the `id` field on `SavedOutputMeta`). If the key differs (e.g. SP1 uses a job ID separate from the output ID), SP3's `processingIds` lookup must adapt.

3. **Review `GRADING_VERSION_DETAILS` breakdown sub-score lists.** The per-method breakdown key names (e.g. `polysyllable_count`, `reading_ease`) are inferred from `backend/utils/scoring_methods.py`. Verify the actual dict keys match before shipping the detail page, since the detail page displays them as plain text.

## 9. Open Questions & Decisions

1. **How does collapsed sidebar interact with `/models` and other AuthLayout pages?**
   `[RESOLVED: The sidebar only renders on CarePlanPage (the root `/` route). AuthLayout-wrapped pages (ModelsPage, GradingVersionDetailPage) do not render the sidebar. No interaction issue.]`

2. **Should the sidebar width CSS variable affect only CarePlanPage or be global?**
   `[RESOLVED: Set it on document.documentElement so CarePlanPage's content wrapper can read it without prop drilling. No other page uses the sidebar, so no unintended side-effects.]`

3. **Should the `/versions` → `/models` rename add a redirect from `/versions` to `/models`?**
   `[RESOLVED: No explicit redirect needed. The App.tsx `*` catch-all already redirects unknown paths to `/`. Anyone navigating to `/versions` lands on `/`. A 301-style redirect via React Router `<Navigate>` is an option but adds complexity for zero real-world benefit since nothing is in production.]`

4. **Should `onNew` be kept on Sidebar as an optional prop for future use?**
   `[RESOLVED: Remove it. The sidebar's "+ New" button is being replaced by the collapse toggle per locked decisions. The NavBar's "New" link (`<Link to="/">`) handles the new-session flow. Keeping `onNew` as dead optional prop adds confusion.]`

5. **Where does `useJobStatuses` live — in SP1's API layer or SP3's?**
   `[RESOLVED: SP1 creates and owns the hook at `frontend/src/api/useJobStatuses.ts`. SP3 imports it. This is the clean ownership boundary: SP1 owns all Firestore subscription logic; SP3 owns the UI that displays it.]`

6. **What happens if SP1 ships after SP3? Can SP3 land without the processing indicator?**
   `[RESOLVED: Yes. The `processingIds` prop on Sidebar is optional (`processingIds?: Set<string>`). When undefined, no spinners appear and the three-dot menu is always shown — identical to today's behavior. SP3 can ship first; the spinner activates when SP1 lands and `CarePlanPage` starts calling `useJobStatuses`.]`

7. **Should `NavBar` be removed from `CarePlanPage.tsx` and moved into a layout wrapper?**
   `[DEFERRED: CarePlanPage currently manages its own NavBar so it can pass `onNew={handleReset}`. With SP3 removing the `onNew` prop entirely, the NavBar no longer needs a prop. Refactoring into AuthLayout is a cleaner architecture but is out of scope for SP3 — the existing pattern continues (CarePlanPage renders its own `<NavBar />`).]`

8. **Grading version data source: config vs backend API.**
   `[RESOLVED: Static config. Grading version 1.0 is the only version and its metadata is stable. A backend API for this would be overkill — it adds an endpoint, a Firestore document, and a fetch on every page load for data that changes once per year. Config is the right call. When a v2.0 grading version ships, one line is added to `GRADING_VERSIONS` in config.ts.]`

9. **Should the timestamp show the run time or the saved time?**
   `[RESOLVED: Use `result.metrics.created_at`, which is the ISO8601 timestamp of the pipeline run. This is the most meaningful timestamp ("when was this simplified"). The saved_id may be set slightly later (after Firestore write) but created_at is the authoritative run time.]`
