# Task 02: Top Navigation Bar

## Goal

Add a persistent top navigation bar that appears on every authenticated page. The bar replaces the scattered per-page sign-out buttons and per-page branding with a single, consistent chrome layer. It gives users two quick actions from anywhere in the app:

- **Versions** — navigate to `/versions` to switch between pipeline versions
- **New** — start a fresh processing session (same behavior as the sidebar's `+ New` button)

This is purely a UI/navigation change. No API routes, no auth logic, and no data model changes are required.

---

## Current State

### Auth gate (`src/App.tsx`, lines 29–38)

All authenticated routes are rendered directly inside a `<Routes>` block in `App.tsx`. There is no shared layout wrapper — each page is completely self-contained.

### VersionsPage (`src/pages/VersionsPage.tsx`, lines 6–49)

- Renders `<main className="app-shell">` as its root element.
- Has an inline `.versions-header` div (line 9) containing the `<p className="eyebrow">` branding text and a `<SignOutButton />`.
- The eyebrow reads: `"Juno Medical Document Simplifier"`.

### V1Page (`src/pages/v1/V1Page.tsx`, lines 798–822)

- No sidebar. Renders an aurora background + `.page-wrapper > .container` structure.
- Branding appears in a `.hero-meta-row` div (line 812) that contains a badge and a `<SignOutButton />`.

### V1_1Page (`src/pages/v1_1/V1_1Page.tsx`, lines 603–629)

- No sidebar. Same aurora + `.page-wrapper > .container` structure.
- Branding appears in a `.hero-meta-row` div (line 614) with a version link, "all versions" link, and `<SignOutButton />`.

### V1_2Page (`src/pages/v1_2/V1_2Page.tsx`, lines 195–399)

- **Has a sidebar.** Root element is `<div style={{ display: 'flex', minHeight: '100vh' }}>` (line 196).
- Sidebar component is rendered at line 197–202. The content wrapper has `marginLeft: '260px'` (line 203) to clear the sidebar.
- Sign-out is an **inline `<button>`** with `position: fixed; top: 16px; right: 16px` (lines 204–215) — not using `SignOutButton`.
- Accepts an `onNew` prop (wired to `handleReset`) which is passed to `<Sidebar onNew={handleReset} />` (line 200).

### Sidebar (`src/components/Sidebar.tsx`, lines 75–151 / `src/components/Sidebar.css`)

- Fixed-position, `width: 260px`, `top: 0`, `z-index: 50` (Sidebar.css lines 1–15).
- Header contains a "Saved" label and a `+ New` button that calls `props.onNew` (Sidebar.tsx line 79).
- The `+ New` behavior in V1_2Page is `handleReset`, which resets all state and sets `appState` back to `'upload'`.

### CSS variables (App.css lines 4–37)

The design system uses:
- `--accent-violet: #7c3aed`
- `--accent-violet-dark: #6d28d9`
- `--border: rgba(124, 58, 237, 0.14)`
- `--text-primary: #1a1340`
- `--text-secondary: #3d3568`
- `--radius-pill: 9999px`
- `--surface: #ffffff`

`.sign-out-button` (App.css lines 250–268): pill-shaped, `border: 1px solid var(--border)`, semi-transparent white background, violet on hover.

`.versions-header` (App.css lines 1183–1193): flex row, space-between, used only on VersionsPage.

---

## Architecture Decision

Wrap all authenticated routes in a shared layout component (`AuthLayout`) that renders the `NavBar` above whatever page is active. This means:

1. Create `NavBar.tsx` — a stateless presentational component.
2. Create `AuthLayout.tsx` — a thin wrapper that renders `<NavBar>` then `<Outlet>`.
3. Update `App.tsx` to nest all authenticated routes inside `AuthLayout`.
4. Remove the per-page sign-out buttons and branding from each page.
5. Add CSS for the nav bar to `App.css`.

The nav bar must sit **above** the sidebar. The sidebar is `position: fixed; top: 0; z-index: 50`. The nav bar must be `position: fixed; top: 0; z-index: 60` (higher) and push content down by its own height (48px). The sidebar must then start at `top: 48px` so it does not overlap the nav bar.

---

## Exact Changes Required

### 1. Create `src/components/NavBar.tsx` (new file)

```tsx
import { Link, useNavigate } from 'react-router-dom';
import { DEFAULT_VERSION } from '../config';
import { versionPath } from '../router';

interface NavBarProps {
  onNew?: () => void;
}

export default function NavBar({ onNew }: NavBarProps) {
  const navigate = useNavigate();

  function handleNew() {
    if (onNew) {
      onNew();
    } else {
      navigate(versionPath(DEFAULT_VERSION));
    }
  }

  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav-brand">
        <span className="top-nav-logo">Juno</span>
      </div>
      <div className="top-nav-actions">
        <Link to="/versions" className="top-nav-link">
          Versions
        </Link>
        <button className="top-nav-new-btn" onClick={handleNew}>
          + New
        </button>
      </div>
    </nav>
  );
}
```

**Notes:**
- `onNew` is optional. On pages without a sidebar (V1Page, V1_1Page, VersionsPage) the prop is not passed, so clicking "New" navigates to the default version path.
- On V1_2Page (which has a sidebar), `onNew` will be wired to `handleReset` so state is cleared in addition to the navigation. See step 5 below for how this is passed down.
- Do NOT import `signOut` or Firebase here. This component has no auth responsibility.

---

### 2. Create `src/components/AuthLayout.tsx` (new file)

```tsx
import { Outlet } from 'react-router-dom';
import NavBar from './NavBar';

export default function AuthLayout() {
  return (
    <>
      <NavBar />
      <Outlet />
    </>
  );
}
```

**Notes:**
- `AuthLayout` does not pass `onNew` to `NavBar`. The default navigate-to-default-version behavior is fine for all pages except V1_2Page.
- V1_2Page passes `onNew` directly to its own `<Sidebar>` already. To wire `onNew` from `NavBar` into V1_2Page's `handleReset`, V1_2Page must render its own local `<NavBar onNew={handleReset} />` inside its page component instead of relying on `AuthLayout`'s `NavBar`. See step 5.

---

### 3. Update `src/App.tsx`

Replace the current flat `<Routes>` block (lines 29–38) with a nested layout route:

**Before (lines 29–38):**
```tsx
return (
  <Routes>
    <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
    <Route path="/versions" element={<VersionsPage />} />
    <Route path="/v1" element={<V1Page />} />
    <Route path="/v1-1" element={<V1_1Page />} />
    <Route path="/v1-2" element={<V1_2Page />} />
    <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
  </Routes>
);
```

**After:**
```tsx
import AuthLayout from './components/AuthLayout';

return (
  <Routes>
    <Route element={<AuthLayout />}>
      <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
      <Route path="/versions" element={<VersionsPage />} />
      <Route path="/v1" element={<V1Page />} />
      <Route path="/v1-1" element={<V1_1Page />} />
      <Route path="/v1-2" element={<V1_2Page />} />
      <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
    </Route>
  </Routes>
);
```

Add `AuthLayout` to the import list at the top of `App.tsx`.

---

### 4. Update `src/pages/VersionsPage.tsx`

Remove the inline `.versions-header` block that contains the `SignOutButton` and eyebrow — the nav bar handles branding and navigation now.

**Before (lines 6–13):**
```tsx
export default function VersionsPage() {
  return (
    <main className="app-shell">
      <section className="hero-section">
        <div className="versions-header">
          <p className="eyebrow">Juno Medical Document Simplifier</p>
          <SignOutButton />
        </div>
        <h1>Choose a version</h1>
```

**After:**
```tsx
export default function VersionsPage() {
  return (
    <main className="app-shell">
      <section className="hero-section">
        <h1>Choose a version</h1>
```

Also remove the `SignOutButton` import from line 3:
```tsx
// Remove this line:
import SignOutButton from '../auth/SignOutButton';
```

---

### 5. Update `src/pages/v1_2/V1_2Page.tsx`

This page is the most complex because it has a sidebar, a fixed sign-out button, and state-aware reset logic.

**5a. Remove the inline sign-out button (lines 204–215):**

Delete this entire block:
```tsx
      <button
        onClick={() => signOut(firebaseAuth)}
        style={{
          position: 'fixed', top: '16px', right: '16px', zIndex: 100,
          background: 'none', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-pill)', padding: '6px 14px',
          fontSize: '0.8rem', color: 'var(--text-secondary)', cursor: 'pointer',
          fontFamily: 'Inter, sans-serif',
        }}
      >
        Sign out
      </button>
```

**5b. Add a local `NavBar` with `onNew={handleReset}` at the top of the content area:**

The nav bar rendered by `AuthLayout` does not have access to `handleReset`. V1_2Page must render its own `NavBar` instance with the prop wired in.

Inside the content wrapper div (currently starting at line 203: `<div style={{ flex: 1, marginLeft: '260px', minWidth: 0 }}>`) — add `NavBar` as the very first child:

```tsx
import NavBar from '../../components/NavBar';

// Inside the return, at the top of the content wrapper:
<div style={{ flex: 1, marginLeft: '260px', minWidth: 0 }}>
  <NavBar onNew={handleReset} />
  {/* rest of existing content */}
```

Wait — this creates two NavBars (one from AuthLayout, one local). To avoid duplication, **do not** nest V1_2Page inside AuthLayout's NavBar render. Instead, render V1_2Page outside the layout that includes NavBar, and have V1_2Page render its own NavBar directly.

**Better approach:** Keep `AuthLayout` for all pages except V1_2Page, which opts out and renders its own `NavBar`:

In `App.tsx`, restructure as:
```tsx
return (
  <Routes>
    <Route element={<AuthLayout />}>
      <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
      <Route path="/versions" element={<VersionsPage />} />
      <Route path="/v1" element={<V1Page />} />
      <Route path="/v1-1" element={<V1_1Page />} />
      <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
    </Route>
    {/* V1_2Page is outside AuthLayout because it manages its own NavBar */}
    <Route path="/v1-2" element={<V1_2Page />} />
  </Routes>
);
```

In `V1_2Page.tsx`, add `NavBar` at the very top of the returned JSX, before the sidebar:

```tsx
import NavBar from '../../components/NavBar';

return (
  <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
    <NavBar onNew={handleReset} />
    <div style={{ display: 'flex', flex: 1 }}>
      <Sidebar
        activeId={activeSavedId}
        onSelect={handleSelectSaved}
        onNew={handleReset}
        refreshTrigger={sidebarRefresh}
      />
      <div style={{ flex: 1, marginLeft: '260px', minWidth: 0 }}>
        {/* remove the old sign-out button entirely */}
        {/* keep aurora-bg, page-wrapper, etc. unchanged */}
```

**5c. Remove the `signOut` and `firebaseAuth` import from V1_2Page.tsx (line 3):**
```tsx
// Remove this line if signOut is no longer used anywhere else in the file:
import { signOut } from 'firebase/auth';
```

Also check whether `firebaseAuth` is still needed after removing the sign-out button. If the only usage was the inline sign-out button (line 205), remove it from the import:
```tsx
// Before:
import { API_URL, firebaseAuth } from '../../api/firebase';
// After:
import { API_URL } from '../../api/firebase';
```

---

### 6. Update `src/pages/v1/V1Page.tsx`

Remove the `<SignOutButton />` from the `.hero-meta-row` div and remove the `SignOutButton` import. The nav bar handles sign-out.

Find the `hero-meta-row` block (around line 812–815):
```tsx
// Before:
<div className="hero-meta-row">
  <div className="hero-badge">✦ AI-Powered Health Literacy</div>
  <SignOutButton />
</div>

// After:
<div className="hero-meta-row">
  <div className="hero-badge">✦ AI-Powered Health Literacy</div>
</div>
```

Remove the import at line 4:
```tsx
// Remove:
import SignOutButton from '../../auth/SignOutButton';
```

---

### 7. Update `src/pages/v1_1/V1_1Page.tsx`

Remove the `<SignOutButton />` from the `.hero-meta-row` block (around line 621) and remove the `SignOutButton` import (line 6).

```tsx
// Before (lines 614–622):
<div className="hero-meta-row">
  <div className="hero-badge">✦ AI-Powered Health Literacy</div>
  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
    <Link to="/versions" style={{ color: 'var(--accent-violet)', textDecoration: 'none' }}>v1.1</Link>
    {' · '}
    <Link to="/versions" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>all versions</Link>
  </span>
  <SignOutButton />
</div>

// After:
<div className="hero-meta-row">
  <div className="hero-badge">✦ AI-Powered Health Literacy</div>
  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
    <Link to="/versions" style={{ color: 'var(--accent-violet)', textDecoration: 'none' }}>v1.1</Link>
    {' · '}
    <Link to="/versions" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>all versions</Link>
  </span>
</div>
```

Remove the `SignOutButton` import:
```tsx
// Remove:
import SignOutButton from '../../auth/SignOutButton';
```

---

### 8. Update `src/components/Sidebar.css`

The sidebar is currently `top: 0`. After adding a 48px nav bar at the top, the sidebar must start below it.

**Before (Sidebar.css lines 7–8):**
```css
height: 100vh;
```
```css
top: 0;
```

**After:**
```css
height: calc(100vh - 48px);
top: 48px;
```

Full change in context:
```css
/* Before: */
.sidebar {
  width: 260px;
  min-width: 220px;
  max-width: 300px;
  height: 100vh;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: fixed;
  left: 0;
  top: 0;
  z-index: 50;
  overflow: hidden;
}

/* After: */
.sidebar {
  width: 260px;
  min-width: 220px;
  max-width: 300px;
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

---

### 9. Add nav bar CSS to `src/App.css`

Add this block after the `.sign-out-button:hover` rule (after line 268 in App.css). Keep it in the same section as other global chrome styles.

```css
/* ============================================================
   Top Navigation Bar
   ============================================================ */
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 48px;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}

.top-nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.top-nav-logo {
  font-size: 0.95rem;
  font-weight: 800;
  letter-spacing: -0.01em;
  color: var(--accent-violet);
}

.top-nav-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.top-nav-link {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-decoration: none;
  padding: 5px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid transparent;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.top-nav-link:hover {
  color: var(--accent-violet);
  border-color: var(--border);
  background: var(--surface-hover);
}

.top-nav-new-btn {
  font-size: 0.8rem;
  font-weight: 600;
  font-family: Inter, sans-serif;
  color: #ffffff;
  background: var(--accent-violet);
  border: none;
  border-radius: var(--radius-pill);
  padding: 5px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.top-nav-new-btn:hover {
  background: var(--accent-violet-dark);
}
```

### 10. Update page content top-padding

All page content is currently positioned assuming no fixed nav bar above it. After adding a 48px fixed nav bar you must push content down so it is not hidden under the bar.

**For `AuthLayout` pages (VersionsPage, V1Page, V1_1Page):**

The `.app-shell` class (App.css line 1173) uses `padding: 64px 24px`. The top padding of `64px` already gives enough room — but it references the very top of the viewport, not below the nav bar. Change it to account for the 48px nav bar:

```css
/* Before (App.css line 1175): */
.app-shell {
  min-height: 100vh;
  padding: 64px 24px;
}

/* After: */
.app-shell {
  min-height: 100vh;
  padding: calc(48px + 40px) 24px 64px;
}
```

The `.page-wrapper` class (used by V1Page and V1_1Page) may have similar top spacing — check its definition:
```
grep -n "page-wrapper" /root/projects/juno/frontend/src/App.css
```
Adjust its `padding-top` similarly if it exists.

**For V1_2Page (self-managed nav bar):**

The content wrapper div (line 203 of V1_2Page.tsx) uses inline `marginLeft: '260px'`. You also need to add `paddingTop: '48px'` (or `marginTop: '48px'`) to this wrapper so content does not render under the fixed nav bar:

```tsx
<div style={{ flex: 1, marginLeft: '260px', minWidth: 0, paddingTop: '48px' }}>
```

---

## New Files to Create

| File | Purpose |
|---|---|
| `src/components/NavBar.tsx` | The nav bar component — logo on left, Versions link + New button on right |
| `src/components/AuthLayout.tsx` | Layout wrapper for all routes except V1_2Page — renders NavBar then Outlet |

---

## Summary of All Files to Touch

| File | Change |
|---|---|
| `src/App.tsx` | Import `AuthLayout`, nest routes inside layout route, keep `/v1-2` outside layout |
| `src/components/NavBar.tsx` | **Create** — new nav bar component |
| `src/components/AuthLayout.tsx` | **Create** — layout wrapper |
| `src/App.css` | Add `.top-nav*` styles after line 268; update `.app-shell` padding at line 1175 |
| `src/components/Sidebar.css` | Change `.sidebar` `top: 0` → `top: 48px` and `height: 100vh` → `calc(100vh - 48px)` |
| `src/pages/VersionsPage.tsx` | Remove `.versions-header` block and `SignOutButton` import |
| `src/pages/v1/V1Page.tsx` | Remove `<SignOutButton />` from `.hero-meta-row` and its import |
| `src/pages/v1_1/V1_1Page.tsx` | Remove `<SignOutButton />` from `.hero-meta-row` and its import |
| `src/pages/v1_2/V1_2Page.tsx` | Remove inline sign-out button (lines 204–215); add `<NavBar onNew={handleReset} />` at top; update content wrapper padding; clean up unused imports |

---

## Acceptance Criteria

1. **Nav bar visible on every page:** Navigate to `/versions`, `/v1`, `/v1-1`, and `/v1-2`. The nav bar must appear at the top of each page with "Juno" on the left, and "Versions" + "+ New" on the right.

2. **Nav bar does not overlap content:** On each page, scroll to the top. No content should be hidden behind the nav bar.

3. **Sidebar is below the nav bar:** On `/v1-2`, the sidebar must start at the bottom edge of the nav bar (48px from the top), not overlap it.

4. **"Versions" link works:** Clicking "Versions" from any page navigates to `/versions`.

5. **"+ New" clears state on V1_2Page:** While viewing a result on `/v1-2`, click "+ New" in the nav bar. The page must return to the upload state (same as clicking "+ New" in the sidebar).

6. **"+ New" navigates from other pages:** On `/versions`, `/v1`, or `/v1-1`, clicking "+ New" navigates to the default version page (e.g., `/v1-2` if that is the default).

7. **No double sign-out buttons:** There must be zero `<SignOutButton />` instances visible anywhere. The sign-out button previously in V1_2Page's inline style (fixed, top-right) must also be gone.

8. **Sign-out still works:** The sign-out functionality is NOT removed — it is simply no longer in scope for this task. Confirm that `SignOutButton` still exists at `src/auth/SignOutButton.tsx` and is still imported somewhere if needed, OR confirm that the developer removed per-page sign-out deliberately as a follow-up task. Do not delete `src/auth/SignOutButton.tsx` itself.

9. **Styling is consistent:** The nav bar uses only CSS variables from `:root` in App.css. No hardcoded colors that conflict with the violet/purple palette. The frosted glass (`backdrop-filter: blur`) effect should look consistent with the `.glass-card` aesthetic already used across the app.

10. **No TypeScript errors:** `npm run build` (or `tsc --noEmit`) in `/root/projects/juno/frontend` exits with zero errors.

---

## Do NOT Change

- `src/auth/AuthContext.tsx` and `src/auth/SignOutButton.tsx` — do not modify auth logic or delete the `SignOutButton` component (other things may import it in future).
- `src/api/` — no API changes.
- `src/pages/v1/V1Page.css`, `src/pages/v1_1/V1_1Page.css` — do not touch page-specific CSS files unless adjusting top padding is needed and the rule is in those files.
- `src/components/Sidebar.tsx` — do not change the component logic; only `Sidebar.css` needs a top offset update.
- The aurora background orbs in V1Page, V1_1Page, and V1_2Page — leave them in place.
- The `.hero-meta-row` containing the version badge and version links in V1_1Page — leave the badge and links, only remove `<SignOutButton />`.
- The `PresetDatasetModal` and `SplitView` modals in V1_2Page — leave them completely untouched.
- The `download-bar` at the bottom of V1_2Page — leave it completely untouched.
