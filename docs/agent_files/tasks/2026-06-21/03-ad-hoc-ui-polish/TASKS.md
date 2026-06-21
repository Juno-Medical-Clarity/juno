# Tasks: Ad Hoc UI Polish (SP3)

Depends on SP1 (`useJobStatuses` hook) for the processing indicator — SP3 degrades gracefully when SP1 has not landed yet. Depends on SP2 (`ApiError` type) in principle, but since SP3 has no new network error surfaces (all new page data is static config), SP2 is not a hard blocker.

Read `PRD.md` in this folder first. Every task below traces to a specific PRD §4.x decision.

---

### Task 1 — Compact Sidebar CSS + remove fixed width

**Files:**
- `frontend/src/components/Sidebar/Sidebar.css`

**Changes:**

1. Replace the hard-coded `.sidebar { width: 260px; min-width: 220px; max-width: 300px; ... }` with a CSS-variable-driven width. Remove `min-width` and `max-width` from the rule (clamping is now handled in JS). Keep all other properties unchanged (height, background, border-right, display, position, left, top, z-index, overflow):
   ```css
   .sidebar {
     width: var(--sidebar-width, 240px);
     height: calc(100vh - 48px);
     background: var(--surface);
     border-right: 1px solid var(--border);
     display: flex;
     flex-direction: column;
     position: fixed;
     left: 0;
     top: 48px;
     z-index: 50;
     overflow: hidden;
   }
   ```

2. Reduce padding on `.sidebar-item` from `10px 16px` to `7px 12px`.

3. Reduce font-size on `.sidebar-item-name` from `0.85rem` to `0.82rem`.

4. Remove the `.sidebar-new-btn` rule entirely (button is removed in Task 2).

5. Add new rules at the end of the file:
   ```css
   /* Collapse toggle */
   .sidebar-collapse-btn {
     background: none;
     border: none;
     color: var(--text-secondary);
     cursor: pointer;
     font-size: 1rem;
     padding: 2px 6px;
     border-radius: 4px;
     line-height: 1;
     flex-shrink: 0;
   }
   .sidebar-collapse-btn:hover {
     color: var(--accent-violet);
   }

   /* Drag resize handle */
   .sidebar-resize-handle {
     position: absolute;
     right: 0;
     top: 0;
     bottom: 0;
     width: 6px;
     cursor: col-resize;
     z-index: 10;
   }
   .sidebar-resize-handle:hover,
   .sidebar-resize-handle.dragging {
     background: rgba(124, 58, 237, 0.18);
   }

   /* Processing spinner */
   @keyframes sidebar-spin {
     to { transform: rotate(360deg); }
   }
   .sidebar-spinner {
     display: inline-block;
     width: 12px;
     height: 12px;
     border: 2px solid rgba(124, 58, 237, 0.2);
     border-top-color: var(--accent-violet);
     border-radius: 50%;
     animation: sidebar-spin 0.7s linear infinite;
     flex-shrink: 0;
   }
   ```

**Acceptance criteria:**
- Sidebar width is controlled by `--sidebar-width` CSS variable (verify in browser DevTools: changing `document.documentElement.style.setProperty('--sidebar-width','300px')` in console updates the sidebar width live).
- Each sidebar row is visibly ~6 px shorter than before.
- No `.sidebar-new-btn` styles remain in the file.
- The new classes `.sidebar-collapse-btn`, `.sidebar-resize-handle`, `.sidebar-spinner` exist in the CSS file.

---

### Task 2 — Sidebar resize, collapse, and processingIds prop (Sidebar.tsx logic)

**Files:**
- `frontend/src/components/Sidebar/Sidebar.tsx`

**Changes (implement all as one coherent rewrite of the component):**

1. **Remove `onNew` from `SidebarProps`** and replace with `processingIds?: Set<string>`:
   ```typescript
   interface SidebarProps {
     activeId: string | null;
     onSelect: (id: string) => void;
     refreshTrigger: number;
     processingIds?: Set<string>;
   }
   ```
   Update the destructure: `export default function Sidebar({ activeId, onSelect, refreshTrigger, processingIds }: SidebarProps)`.

2. **Add localStorage-backed state** for width and collapsed:
   ```typescript
   const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
     const stored = localStorage.getItem('juno_sidebar_width');
     return stored ? Number(stored) : 240;
   });
   const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
     return localStorage.getItem('juno_sidebar_collapsed') === 'true';
   });
   ```

3. **Set `--sidebar-width` CSS variable on every state change** via a `useEffect`:
   ```typescript
   useEffect(() => {
     const effectiveWidth = isCollapsed ? 40 : sidebarWidth;
     document.documentElement.style.setProperty('--sidebar-width', `${effectiveWidth}px`);
   }, [sidebarWidth, isCollapsed]);
   ```
   Also set it once on mount (the `useEffect` above fires on mount, so this is covered).

4. **Collapse toggle function:**
   ```typescript
   function toggleCollapse() {
     setIsCollapsed(prev => {
       const next = !prev;
       localStorage.setItem('juno_sidebar_collapsed', String(next));
       return next;
     });
   }
   ```

5. **Drag resize handle** — add a `dragRef = useRef<boolean>(false)` and wire mouse events. Add a `<div>` at the bottom of `<aside>` (before `</aside>`):
   ```tsx
   {!isCollapsed && (
     <div
       className="sidebar-resize-handle"
       onMouseDown={(e) => {
         e.preventDefault();
         dragRef.current = true;
         function onMove(ev: MouseEvent) {
           if (!dragRef.current) return;
           const clamped = Math.min(400, Math.max(180, ev.clientX));
           setSidebarWidth(clamped);
           document.documentElement.style.setProperty('--sidebar-width', `${clamped}px`);
         }
         function onUp() {
           dragRef.current = false;
           localStorage.setItem('juno_sidebar_width', String(
             Math.min(400, Math.max(180, window.innerWidth))
           ));
           document.removeEventListener('mousemove', onMove);
           document.removeEventListener('mouseup', onUp);
         }
         // Persist on mouseup using the last sidebarWidth value
         // (capture via closure after final onMove fires)
         document.addEventListener('mousemove', onMove);
         document.addEventListener('mouseup', onUp);
       }}
     />
   )}
   ```
   Note: In `onUp`, persist the current `sidebarWidth` state. Because state updates are async, read it from a ref or accept the last value set via `setSidebarWidth`. The cleanest approach: use a `widthRef = useRef(sidebarWidth)` that is kept in sync with `setSidebarWidth` calls, then read `widthRef.current` in `onUp` to persist.

   Full ref pattern:
   ```typescript
   const widthRef = useRef(sidebarWidth);
   // In the setSidebarWidth call inside onMove:
   setSidebarWidth(clamped);
   widthRef.current = clamped;
   // In onUp:
   localStorage.setItem('juno_sidebar_width', String(widthRef.current));
   ```

6. **Replace the sidebar header** — remove the `<button className="sidebar-new-btn" onClick={onNew}>+ New</button>` and replace the entire `<div className="sidebar-header">` block:
   ```tsx
   <div className="sidebar-header">
     {!isCollapsed && <span className="sidebar-title">Saved</span>}
     <button
       className="sidebar-collapse-btn"
       onClick={toggleCollapse}
       aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
     >
       {isCollapsed ? '›' : '‹'}
     </button>
   </div>
   ```

7. **Update `handleDelete`** — the `onNew()` call inside `handleDelete` (currently called when deleting the active item) must be removed since `onNew` no longer exists. Replace the `onNew()` call with a no-op or navigate to `/` directly if needed. The simplest fix: remove the `if (activeId === id) onNew();` line — after delete, the sidebar will just show no active item. (If the caller needs a reset, SP3 can pass nothing; the active item is deselected by the fact that the deleted id is no longer in the list.)

8. **Update `renderRow`** to show spinner or three-dot menu based on `processingIds`:
   ```tsx
   const isProcessing = processingIds?.has(output.id) ?? false;
   ```
   In the JSX, replace the unconditional `<button className="sidebar-menu-btn" ...>` with:
   ```tsx
   {isProcessing ? (
     <span className="sidebar-spinner" aria-label="Processing" />
   ) : (
     <button
       className="sidebar-menu-btn"
       onClick={e => {
         e.stopPropagation();
         setMenuOpenId(menuOpenId === output.id ? null : output.id);
       }}
     >
       ⋯
     </button>
   )}
   ```

9. **Hide sidebar list contents when collapsed** — wrap `<div className="sidebar-list">` contents with a conditional: when `isCollapsed`, render only the empty div (the collapsed 40 px strip shows nothing):
   ```tsx
   <div className="sidebar-list">
     {!isCollapsed && (
       <>
         {loading && <div className="sidebar-empty">Loading...</div>}
         {/* ... rest of the grouped list ... */}
       </>
     )}
   </div>
   ```

**Acceptance criteria:**
- `SidebarProps` no longer has `onNew`; it has `processingIds?: Set<string>`.
- Clicking `‹` collapses sidebar to 40 px; clicking `›` expands to last width. Refreshing the page preserves state (check `localStorage` in DevTools: keys `juno_sidebar_width` and `juno_sidebar_collapsed`).
- Dragging the right edge changes the sidebar width to the dragged position, clamped between 180 and 400 px. After drag, `juno_sidebar_width` in localStorage is updated.
- When collapsed, the resize handle is not rendered and cannot be dragged.
- When `processingIds` contains an item's id, that item shows the spinner and no three-dot `⋯` button.
- When `processingIds` is `undefined`, every item shows the three-dot `⋯` button (unchanged from before).
- TypeScript compiles with no errors.

---

### Task 3 — Sort sidebar items latest-first within date groups + sort date groups latest-first

**Files:**
- `frontend/src/utils/groupSavedOutputs.ts`

**Changes:**

Inside `groupSavedOutputs`, after building `byDate` and `dateOrder`, make two changes:

1. **Sort `dateOrder` descending** before the `.map()`:
   ```typescript
   dateOrder.sort((a, b) => b.localeCompare(a));
   ```
   (Date keys are `YYYY-MM-DD` strings, so lexicographic descending = newest first.)

2. **Sort items within each date bucket descending by `created_at`** before partitioning into batches and standalone. In the `.map()` callback, add at the top:
   ```typescript
   const items = byDate.get(date)!.sort(
     (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
   );
   ```
   Then iterate `items` (not `byDate.get(date)!`) for the batch/standalone loop.

   Full updated function body for the `return dateOrder.map(date => { ... })` block:
   ```typescript
   return dateOrder.map(date => {
     const items = byDate.get(date)!.sort(
       (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
     );
     const batchOrder: string[] = [];
     const byBatch = new Map<string, SavedOutputMeta[]>();
     const standalone: SavedOutputMeta[] = [];
     for (const o of items) {
       if (!o.batch_group_id) { standalone.push(o); continue; }
       if (!byBatch.has(o.batch_group_id)) { byBatch.set(o.batch_group_id, []); batchOrder.push(o.batch_group_id); }
       byBatch.get(o.batch_group_id)!.push(o);
     }
     return {
       date,
       batches: batchOrder.map(id => ({ batch_group_id: id, items: byBatch.get(id)! })),
       standalone,
     };
   });
   ```

**Acceptance criteria:**
- The existing test file at `frontend/src/tests/utils/groupSavedOutputs.test.ts` passes with no changes to test code. (The test at line 38 already asserts `result[0].date === '2026-06-16'` and `result[1].date === '2026-06-15'` — newest first — so this test now validates the date sort. The batch item order test at line 50 asserts `['a1', 'a2']` which is already newest-first in the fixture timestamps, so it also passes.)
- Add one new test case to `groupSavedOutputs.test.ts` verifying that standalone items within a date group are ordered newest `created_at` first:
  ```typescript
  it('sorts standalone items within a date group newest-first', () => {
    const result = groupSavedOutputs(FIXTURE);
    // s1 created_at 12:00, s2 created_at 11:00 — s1 should come first
    expect(result[0].standalone.map(o => o.id)).toEqual(['s1', 's2']);
  });
  ```
  (This may already pass given the fixture ordering; add it explicitly to lock the contract.)

---

### Task 4 — NavBar restructure (three-column grid, center links, sign-out right)

**Files:**
- `frontend/src/components/NavBar.tsx`
- `frontend/src/App.css`

**Changes to `NavBar.tsx` (full rewrite):**

Replace the entire file content with:
```tsx
import { Link } from 'react-router-dom';
import SignOutButton from '../auth/SignOutButton';

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
        <SignOutButton />
      </div>
    </nav>
  );
}
```

Key changes from the old component:
- `NavBarProps` interface removed entirely (no props).
- `useNavigate` import removed.
- `handleNew` function removed.
- Old `<div className="top-nav-actions">` replaced by `<div className="top-nav-center">` and `<div className="top-nav-right">`.
- `<Link to="/versions">Versions</Link>` replaced by `<Link to="/models">Models</Link>`.
- `<button className="top-nav-new-btn">+ New</button>` replaced by `<Link to="/" className="top-nav-link">New</Link>`.
- `SignOutButton` imported from `../auth/SignOutButton`.

**Changes to `App.css`:**

1. Replace `.top-nav { display: flex; align-items: center; justify-content: space-between; ... }` with grid layout. Keep all existing properties (position, top, left, right, height, z-index, padding, background, backdrop-filter, border-bottom) but change the display rule:
   ```css
   .top-nav {
     position: fixed;
     top: 0;
     left: 0;
     right: 0;
     height: 48px;
     z-index: 60;
     display: grid;
     grid-template-columns: 1fr auto 1fr;
     align-items: center;
     padding: 0 20px;
     background: rgba(255, 255, 255, 0.88);
     backdrop-filter: blur(12px);
     -webkit-backdrop-filter: blur(12px);
     border-bottom: 1px solid var(--border);
   }
   ```

2. Replace `.top-nav-actions { display: flex; align-items: center; gap: 8px; }` with two new rules:
   ```css
   .top-nav-center {
     display: flex;
     align-items: center;
     gap: 4px;
     justify-self: center;
   }

   .top-nav-right {
     display: flex;
     align-items: center;
     justify-content: flex-end;
   }
   ```
   Add `justify-self: start;` to `.top-nav-brand`.

3. Remove (or comment out) `.top-nav-new-btn` and `.top-nav-new-btn:hover` rules (lines 351–365 in current file) — the `+ New` button is gone.

4. Remove (or comment out) `.top-nav-actions` rule (lines 328–332 in current file).

**Acceptance criteria:**
- `NavBar` component has no props, no `useNavigate`, no `onNew`.
- Clicking "New" in the NavBar navigates to `/`.
- Clicking "Models" in the NavBar navigates to `/models`.
- "Sign out" button appears on the right side of the NavBar.
- The "Versions" link and "+ New" button are gone.
- In the browser, the NavBar layout is: brand on the left, "New" and "Models" centered, "Sign out" on the right — even when the window is resized.
- TypeScript compiles with no errors (no remaining references to `onNew` prop in NavBar).

---

### Task 5 — Update CarePlanPage.tsx callers (remove onNew, update sidebar margin, wire processingIds)

**Files:**
- `frontend/src/pages/care-plan/CarePlanPage.tsx`

**Changes:**

1. **Remove `onNew` from `<NavBar>`** (line 387):
   ```tsx
   // OLD
   <NavBar onNew={handleReset} />
   // NEW
   <NavBar />
   ```

2. **Remove `onNew` from `<Sidebar>`** (line 392–394):
   ```tsx
   // OLD
   <Sidebar
     activeId={activeSavedId}
     onSelect={handleSelectSaved}
     onNew={handleReset}
     refreshTrigger={sidebarRefresh}
   />
   // NEW
   <Sidebar
     activeId={activeSavedId}
     onSelect={handleSelectSaved}
     refreshTrigger={sidebarRefresh}
     processingIds={processingIds}
   />
   ```

3. **Update the content wrapper `<div>`** (line 395) to use the CSS variable for `marginLeft` and add the extra top gap:
   ```tsx
   // OLD
   <div style={{ flex: 1, marginLeft: '260px', minWidth: 0, paddingTop: '48px' }}>
   // NEW
   <div style={{ flex: 1, marginLeft: 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: 'calc(48px + 40px)' }}>
   ```

4. **Wire `processingIds` from SP1's hook.** Add the following import and hook call at the top of `CarePlanPage` (conditional on SP1 being landed — see note):

   Add import (only when SP1 has landed):
   ```typescript
   import { useJobStatuses } from '../../api/useJobStatuses';
   ```

   Inside the component body, after the existing state declarations:
   ```typescript
   // SP1 integration — gracefully absent when SP1 is not yet landed
   const { statuses } = typeof useJobStatuses !== 'undefined'
     ? useJobStatuses()
     : { statuses: new Map<string, string>() };

   const processingIds = new Set(
     [...statuses.entries()]
       .filter(([, s]) => s === 'not_started' || s === 'processing')
       .map(([id]) => id)
   );
   ```

   **Simpler approach for SP3 landing before SP1:** Since SP1 may not be landed yet, implement the hook call unconditionally but guard the import with a try/catch at module level — or more practically, just hardcode `processingIds` to `undefined` for now and add a `// TODO SP1: replace with useJobStatuses()` comment. Then when SP1 lands, update this file to import and call `useJobStatuses`. The PRD confirms this degrades gracefully.

   For a clean implementation that works regardless of SP1 landing order:
   ```typescript
   // processingIds: wired from SP1's useJobStatuses hook.
   // When SP1 lands, import useJobStatuses from '../../api/useJobStatuses'
   // and compute this set from statuses Map (status === 'not_started' | 'processing').
   // Until then, undefined causes Sidebar to show no spinners (graceful degradation).
   const processingIds: Set<string> | undefined = undefined; // TODO: wire SP1
   ```

5. **Add `useEffect` to detect `processing → done` transitions** (needed when SP1 is wired). Add this block near other `useEffect` calls — leave it stubbed out until SP1 lands:
   ```typescript
   // TODO SP1: detect processing→done transitions to trigger sidebar refresh
   // useEffect(() => {
   //   statuses.forEach((status, id) => {
   //     if (prevStatuses.get(id) === 'processing' && status === 'done') {
   //       setSidebarRefresh(r => r + 1);
   //     }
   //   });
   // }, [statuses]);
   ```

**Acceptance criteria:**
- `<NavBar />` is called with no props in `CarePlanPage.tsx`.
- `<Sidebar />` is called with no `onNew` prop; `processingIds` prop is present (even if `undefined`).
- The content wrapper uses `marginLeft: 'var(--sidebar-width, 240px)'` and `paddingTop: 'calc(48px + 40px)'`.
- TypeScript compiles with no errors.
- Visually: the content area expands/contracts as the sidebar is resized or collapsed (the CSS variable drives both the sidebar width and the content margin simultaneously).
- There is a visible gap (~40 px) between the NavBar and the first card on the care plan page.

---

### Task 6 — Remove "Deleted from servers" span + add timestamp under "Your Care Plan"

**Files:**
- `frontend/src/pages/care-plan/CarePlanPage.tsx`
- `frontend/src/App.css`

**Changes to `CarePlanPage.tsx`:**

Locate the `result-header` block (around line 519–535). Replace:
```tsx
<div className="result-header">
  <h2 className="result-title">Your Care Plan</h2>
  <span className="deleted-note">🔒 Deleted from servers</span>
  {activeSavedId && result && ...}
</div>
```

With:
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
  {activeSavedId && result && (outputHasInputPdf(result) || outputHasInputText(result)) && (
    <button
      onClick={() => setShowSplitView(true)}
      style={{
        background: 'none', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-pill)', padding: '6px 14px',
        fontSize: '0.8rem', cursor: 'pointer',
        color: 'var(--text-secondary)', fontFamily: 'Inter, sans-serif',
      }}
    >
      Show Original
    </button>
  )}
</div>
```

Note: `result.metrics.created_at` is already typed as `string` on `Metrics` in `frontend/src/types/envelope.ts` — no type changes needed.

**Changes to `App.css`:**

1. Add the `.result-timestamp` style (place it near `.result-title`, around line 616):
   ```css
   .result-timestamp {
     font-size: 0.82rem;
     color: var(--text-muted);
     margin-top: 4px;
     font-weight: 500;
   }
   ```

2. Remove (or comment out) the `.deleted-note` rule block (lines 618–629 in the current file):
   ```css
   /* REMOVED — deleted-note is no longer rendered (PRD §4.10) */
   /* .deleted-note { ... } */
   ```

**Acceptance criteria:**
- The `🔒 Deleted from servers` badge does not appear anywhere in the rendered UI.
- After a care plan run completes (or when a saved output is loaded), the text "Simplified on June 21, 2026" (or the actual date) appears directly below "Your Care Plan" in a smaller, muted font.
- If `result.metrics.created_at` is null or empty, no timestamp is shown (no crash).
- TypeScript compiles with no errors.
- Grep for `deleted-note` in all `.tsx` files returns zero hits.

---

### Task 7 — Upload page card gaps + NavBar-to-content spacing via CSS

**Files:**
- `frontend/src/App.css`

**Changes:**

1. Add a sibling-combinator gap rule for the upload section. Place it in the `.upload-section` block (around line 371):
   ```css
   .upload-section > * + * {
     margin-top: 16px;
   }
   ```
   This automatically adds 16 px above `<PresetDataCard>` and `<ConfigurationCard>` (and any future cards) without touching their component files.

No changes needed to `CarePlanPage.tsx` for card spacing — the CSS rule handles it.
No changes needed to AuthLayout-wrapped pages — `.app-shell` already uses `padding: calc(48px + 40px) 24px 64px` (line 1266), which gives the correct NavBar gap. The `paddingTop` change in Task 5 aligns `CarePlanPage.tsx` to match.

**Acceptance criteria:**
- On the upload page, there is a visible gap (~16 px) between the main upload glass card, the PresetDataCard, and the ConfigurationCard.
- No changes were made to `PresetDataCard.tsx` or `ConfigurationCard.tsx`.
- The upload section gap rule is in `App.css` as `.upload-section > * + * { margin-top: 16px; }`.

---

### Task 8 — Rename VersionsPage → ModelsPage + update App.tsx routes

**Files:**
- `frontend/src/pages/VersionsPage.tsx` → `frontend/src/pages/ModelsPage.tsx` (file rename)
- `frontend/src/App.tsx`

**Changes:**

1. **Rename the file**: `git mv frontend/src/pages/VersionsPage.tsx frontend/src/pages/ModelsPage.tsx`.

2. **Update `ModelsPage.tsx`** — change the function name and add the Grading Versions section (full content per PRD §4.7):

   ```tsx
   import { Link } from 'react-router-dom';
   import { VERSIONS, GRADING_VERSIONS } from '../config';

   export default function ModelsPage() {
     return (
       <main className="app-shell">
         <section className="hero-section">
           <h1>Pipeline versions</h1>
           <div className="versions-table-wrap glass-card">
             <table className="versions-table">
               <thead>
                 <tr>
                   <th>Version</th>
                   <th>Description</th>
                   <th>Steps</th>
                 </tr>
               </thead>
               <tbody>
                 {VERSIONS.map(version => (
                   <tr key={version.id}>
                     <td>
                       <strong className="version-table-link">{version.label}</strong>
                       {version.isDefault && (
                         <span className="version-default-badge">Default</span>
                       )}
                     </td>
                     <td>{version.description}</td>
                     <td>
                       <ol className="version-steps">
                         {version.steps.map(step => (
                           <li key={step}>{step}</li>
                         ))}
                       </ol>
                     </td>
                   </tr>
                 ))}
               </tbody>
             </table>
           </div>

           <section style={{ marginTop: '48px' }}>
             <h2>Grading Versions</h2>
             <div className="versions-table-wrap glass-card" style={{ marginTop: '16px' }}>
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
         </section>
       </main>
     );
   }
   ```

3. **Update `App.tsx`** — change the import and routes:
   ```tsx
   // OLD
   import VersionsPage from './pages/VersionsPage';
   // ...
   <Route path="/versions" element={<VersionsPage />} />

   // NEW
   import ModelsPage from './pages/ModelsPage';
   import GradingVersionDetailPage from './pages/GradingVersionDetailPage';
   // ...
   <Route path="/models" element={<ModelsPage />} />
   <Route path="/models/grading/:versionId" element={<GradingVersionDetailPage />} />
   ```
   Both new routes go inside the existing `<Route element={<AuthLayout />}>` wrapper (which also wraps the `*` catch-all). The `/` CarePlanPage route stays outside `<AuthLayout>`.

   Updated `App.tsx` routes block:
   ```tsx
   <Routes>
     <Route element={<AuthLayout />}>
       <Route path="/models" element={<ModelsPage />} />
       <Route path="/models/grading/:versionId" element={<GradingVersionDetailPage />} />
       <Route path="*" element={<Navigate to="/" replace />} />
     </Route>
     {/* CarePlanPage manages its own NavBar */}
     <Route path="/" element={<CarePlanPage />} />
   </Routes>
   ```

**Acceptance criteria:**
- `frontend/src/pages/VersionsPage.tsx` no longer exists; `frontend/src/pages/ModelsPage.tsx` exists.
- Navigating to `/models` shows the Models page with both "Pipeline versions" and "Grading Versions" sections.
- Navigating to `/versions` redirects to `/` (caught by `*` catch-all Navigate).
- The Grading Versions table row for "Grading Version 1.0" links to `/models/grading/v1-0`.
- TypeScript compiles with no errors.
- Grep for `VersionsPage` in all `.ts`/`.tsx` files returns zero hits.

---

### Task 9 — Add `GRADING_VERSIONS` and `GRADING_VERSION_DETAILS` to config.ts

**Files:**
- `frontend/src/config.ts`

**Changes:**

Append the following exports to the end of `frontend/src/config.ts`:

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

export const GRADING_VERSION_DETAILS = [
  {
    id: 'v1-0',
    label: 'Grading Version 1.0',
    description: 'Multi-method readability and patient health literacy scoring. Computes six individual method scores and a combined composite score.',
    isDefault: true,
    combinedDescription:
      'The composite score is a weighted average of the six method scores, normalized to 0–100. A higher score means higher readability/accessibility. The grade_estimate and label fields describe the approximate reading-grade equivalent.',
    methodDetails: [
      {
        id: 'smog',
        label: 'SMOG',
        description: 'Polysyllabic word count; designed for health materials (McLaughlin 1969).',
        breakdownKeys: ['polysyllable_count', 'sentence_count', 'raw_grade'],
        docsSlug: 'smog',
      },
      {
        id: 'flesch_kincaid',
        label: 'Flesch-Kincaid',
        description: 'Sentence length × syllable load; Reading Ease + Grade Level (1975).',
        breakdownKeys: ['reading_ease', 'grade_level', 'avg_sentence_length', 'avg_syllables_per_word'],
        docsSlug: 'flesch-kincaid',
      },
      {
        id: 'dale_chall',
        label: 'Dale-Chall',
        description: 'Difficult words outside the 3,000 familiar-word list (1948/1995).',
        breakdownKeys: ['difficult_word_count', 'pct_difficult', 'raw_score'],
        docsSlug: 'dale-chall',
      },
      {
        id: 'pemat',
        label: 'PEMAT',
        description: 'Automated AHRQ approximation: understandability + actionability (2013).',
        breakdownKeys: ['understandability', 'actionability'],
        docsSlug: 'pemat',
      },
      {
        id: 'sam',
        label: 'SAM',
        description: 'Content, literacy demand, and layout/typography domains (Doak et al. 1996).',
        breakdownKeys: ['content_score', 'literacy_demand', 'layout_score'],
        docsSlug: 'sam',
      },
      {
        id: 'cdc_cci',
        label: 'CDC CCI',
        description: 'Main message, behavioral recommendations, numbers, call-to-action (CDC).',
        breakdownKeys: ['main_message', 'behavioral_recommendations', 'numbers_score', 'call_to_action'],
        docsSlug: 'cdc-cci',
      },
    ],
  },
] as const;
```

**Acceptance criteria:**
- `import { GRADING_VERSIONS, GRADING_VERSION_DETAILS } from '../config'` resolves without TypeScript errors in both `ModelsPage.tsx` and `GradingVersionDetailPage.tsx`.
- `GRADING_VERSIONS` has exactly 1 entry with `id: 'v1-0'` and 6 methods.
- `GRADING_VERSION_DETAILS[0].methodDetails` has exactly 6 entries matching the table in PRD §4.8.
- TypeScript compiles with no errors.

---

### Task 10 — Create GradingVersionDetailPage.tsx

**Files:**
- `frontend/src/pages/GradingVersionDetailPage.tsx` (new file)

**Changes:**

Create the file with the following content:

```tsx
import { Link, useParams } from 'react-router-dom';
import { GRADING_VERSION_DETAILS } from '../config';

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

        <h2 style={{ marginTop: '40px', marginBottom: '16px', fontSize: '1.25rem', fontWeight: 700 }}>
          Scoring Methods
        </h2>
        {version.methodDetails.map(method => (
          <div
            key={method.id}
            className="glass-card"
            style={{ marginBottom: '16px', padding: '20px 24px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <h3 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                {method.label}
              </h3>
              <a href={`/docs/${method.docsSlug}`} className="top-nav-link">
                Docs →
              </a>
            </div>
            <p style={{ marginTop: '8px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              {method.description}
            </p>
            <p style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>Sub-scores:</strong>{' '}
              {method.breakdownKeys.join(', ')}
            </p>
          </div>
        ))}

        <h2 style={{ marginTop: '40px', marginBottom: '16px', fontSize: '1.25rem', fontWeight: 700 }}>
          Combined Score
        </h2>
        <div className="glass-card" style={{ padding: '20px 24px' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {version.combinedDescription}
          </p>
        </div>
      </section>
    </main>
  );
}
```

Note: The `/docs/<slug>` links are rendered as plain `<a href>` (not React Router `<Link>`), because SP4 may implement the `/docs` route structure separately and the links are acceptable 404s until SP4 lands (PRD §4.8).

**Acceptance criteria:**
- Navigating to `/models/grading/v1-0` renders the detail page with a "← Back to Models" link, the version label, description, 6 method cards (each with label, description, sub-scores, and a "Docs →" anchor), and a "Combined Score" section.
- Navigating to `/models/grading/does-not-exist` renders the "not found" state with the back link — no crash.
- All 6 `Docs →` anchors point to `/docs/smog`, `/docs/flesch-kincaid`, `/docs/dale-chall`, `/docs/pemat`, `/docs/sam`, `/docs/cdc-cci` respectively.
- TypeScript compiles with no errors.
- The page is wrapped in `AuthLayout` (via the route in App.tsx), so the NavBar is visible and the user must be authenticated.

---

### Task 11 — Unit test: Sidebar collapse toggle + processingIds behavior

**Files:**
- `frontend/src/tests/components/Sidebar.test.tsx` (new file)

**Changes:**

Create a minimal behavior test for the two new Sidebar behaviors that are not covered by existing tests. Use the same Vitest + React Testing Library pattern as the existing component tests in `frontend/src/tests/components/`.

The test should cover:
1. **Collapse toggle:** Rendering the Sidebar, clicking the collapse button, asserting the sidebar-title is hidden and the aria-label changes to "Expand sidebar".
2. **processingIds hides three-dot menu:** Rendering the Sidebar with a `processingIds` set containing an item's id, asserting the `⋯` button is not rendered for that item and the spinner element is rendered.

Stub `listSavedOutputs` (used inside the Sidebar) to return a minimal fixture so the component renders without network calls. Look at `ConfigurationCard.test.tsx` for the mock/stub pattern used in this codebase.

```tsx
// Sketch — adapt to match the project's existing test helper style:
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import Sidebar from '../../components/Sidebar';

vi.mock('../../api/savedOutputs', () => ({
  listSavedOutputs: vi.fn().mockResolvedValue([
    { id: 'item-1', name: 'Test Output', source_filename: 'test.pdf',
      created_at: '2026-06-21T10:00:00Z', updated_at: '2026-06-21T10:00:00Z',
      batch_group_id: null },
  ]),
  renameSavedOutput: vi.fn(),
  deleteSavedOutput: vi.fn(),
}));

describe('Sidebar', () => {
  it('hides sidebar-title when collapse button is clicked', async () => {
    render(
      <Sidebar activeId={null} onSelect={() => {}} refreshTrigger={0} />
    );
    expect(screen.getByText('Saved')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Collapse sidebar'));
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
  });

  it('shows spinner and hides three-dot menu for processing items', async () => {
    render(
      <Sidebar
        activeId={null}
        onSelect={() => {}}
        refreshTrigger={0}
        processingIds={new Set(['item-1'])}
      />
    );
    // Wait for listSavedOutputs to resolve
    await screen.findByLabelText('Processing');
    expect(screen.queryByText('⋯')).not.toBeInTheDocument();
  });
});
```

**Acceptance criteria:**
- The test file exists at `frontend/src/tests/components/Sidebar.test.tsx`.
- Both test cases pass when running `npm test` (or `npx vitest run`) from the frontend directory.
- The collapse test verifies `sidebar-title` disappears on toggle.
- The processingIds test verifies spinner is shown and `⋯` is absent for a processing item.

---

## Summary of what requires you (not a dev agent)

1. **Confirm `/docs/<slug>` URL scheme with SP4 before SP3 ships (PRD §8.1).** SP3 hardcodes links like `/docs/smog`, `/docs/flesch-kincaid`, `/docs/dale-chall`, `/docs/pemat`, `/docs/sam`, `/docs/cdc-cci`. If SP4 uses a different URL pattern (e.g. `/docs/grading/smog`), update `docsSlug` values in `GRADING_VERSION_DETAILS` in `config.ts`. Until confirmed, the links will 404 — that is acceptable per PRD §4.8.

2. **Confirm SP1's `useJobStatuses` hook interface (PRD §8.2) before wiring Task 5.** SP3 designs the interface as `useJobStatuses(): { statuses: Map<string, JobStatus> }` keyed by `care_plan_output` document ID. If SP1 uses a different key (e.g. a job ID separate from the output ID), Task 5's `processingIds` lookup must be adapted. Until confirmed, Task 5 leaves `processingIds = undefined` (graceful degradation, no spinners shown).

3. **Verify `GRADING_VERSION_DETAILS` breakdown sub-score key names (PRD §8.3).** The `breakdownKeys` arrays in Task 9's config (e.g. `polysyllable_count`, `reading_ease`) were inferred from the PRD's table of backend scoring method keys. Before shipping the GradingVersionDetailPage, grep `backend/utils/scoring_methods.py` and verify each method's actual dict keys match. If they differ, update `breakdownKeys` in `config.ts` — no code changes elsewhere are needed.
