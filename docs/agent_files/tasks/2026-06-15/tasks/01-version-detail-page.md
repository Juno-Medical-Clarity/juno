# Task 01 — Version Detail Pages

**Date:** 2026-06-15
**Project:** Juno (medical appointment note simplifier)
**Estimated effort:** 2–3 hours

---

## 1. Goal

Add a dedicated detail page for each Juno version (`/version/v1`, `/version/v1-1`, `/version/v1-2`). When a user visits the versions overview table and clicks a version name, they land on a clean detail page that explains:

- What this version does (its `description`)
- Its full processing pipeline (the `steps[]` array), displayed as a numbered list
- A "Use This Version" button that navigates to the version's actual tool page (its `path`, e.g. `/v1`)
- A back link to `/versions`

This gives users context before committing to a version, rather than jumping straight into the tool.

---

## 2. Current State

### `/root/projects/juno/frontend/src/config.ts`

The `VERSIONS` array (lines 7–35) is the single source of truth. Each entry has:

| Field | Example | Notes |
|---|---|---|
| `id` | `'v1-1'` | Used as the URL param (e.g. `/version/v1-1`) |
| `label` | `'Version 1.1'` | Human-readable heading |
| `path` | `'/v1-1'` | Route to the actual tool page |
| `description` | long string | Already written, display as-is |
| `steps` | `['Read input', 'Find medical terms', ...]` | Ordered pipeline steps |
| `apiPath` | `'/simplify/v1-1'` | Backend — do NOT display |
| `isDefault` | `true/false` | Show a "Default" badge if true |

The array is typed `as const` (line 35), so all values are readonly literals.

### `/root/projects/juno/frontend/src/pages/VersionsPage.tsx`

Lines 24–43: Renders a `<table>` with one row per version. The version label (line 27–29) is currently a `<Link>` that navigates directly to `version.path` (e.g. `/v1`). This link needs to change to point to `/version/:id` instead.

```tsx
// Current (line 27-29) — links straight to the tool:
<Link className="version-table-link" to={version.path}>
  {version.label}
</Link>

// Target — links to the new detail page:
<Link className="version-table-link" to={`/version/${version.id}`}>
  {version.label}
</Link>
```

### `/root/projects/juno/frontend/src/App.tsx`

Lines 30–38: The `<Routes>` block registers all current routes. There is no `/version/:id` route yet. Routes are defined inline — no separate router file is used for route registration.

### `/root/projects/juno/frontend/src/router.tsx`

Only exports one helper function `versionPath()` (lines 3–5). No route definitions live here. Do not change this file.

### CSS (`/root/projects/juno/frontend/src/App.css`)

Relevant existing classes to reuse (do not redefine them):

| Class | Purpose |
|---|---|
| `.app-shell` | Outermost `<main>` wrapper (line 1173) — `min-height: 100vh; padding: 64px 24px` |
| `.hero-section` | Centered content column, max-width 1120px (line 1178) |
| `.versions-header` | Flex row: left label + right sign-out button (line 1183) |
| `.eyebrow` | Small violet all-caps label above headings (line 1195) |
| `.glass-card` | Frosted-glass card (line 187) |
| `.version-default-badge` | Small teal "Default" pill badge (line 1272) |
| `.version-steps li` | Pill-styled step token, border + background (line 1292) |
| `.version-steps` | Flex-wrap list, no list-style (line 1285) |
| `.cta-btn` | Primary violet gradient button (line 357) |

---

## 3. Exact Changes Required

### 3a. Update `VersionsPage.tsx` — change the version link target

**File:** `/root/projects/juno/frontend/src/pages/VersionsPage.tsx`

Change line 27 only. The `to` prop should point to `/version/${version.id}` instead of `version.path`:

```tsx
// BEFORE (line 27):
<Link className="version-table-link" to={version.path}>

// AFTER:
<Link className="version-table-link" to={`/version/${version.id}`}>
```

No other changes to `VersionsPage.tsx`.

---

### 3b. Register the new route in `App.tsx`

**File:** `/root/projects/juno/frontend/src/App.tsx`

Add one import and one `<Route>` inside the existing `<Routes>` block.

**Import to add** (add after line 7, alongside the other page imports):

```tsx
import VersionDetailPage from './pages/VersionDetailPage';
```

**Route to add** (add after line 32, the `/versions` route):

```tsx
<Route path="/version/:id" element={<VersionDetailPage />} />
```

The complete `<Routes>` block after the change should look like:

```tsx
<Routes>
  <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
  <Route path="/versions" element={<VersionsPage />} />
  <Route path="/version/:id" element={<VersionDetailPage />} />
  <Route path="/v1" element={<V1Page />} />
  <Route path="/v1-1" element={<V1_1Page />} />
  <Route path="/v1-2" element={<V1_2Page />} />
  <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
</Routes>
```

---

### 3c. Add CSS for the detail page

**File:** `/root/projects/juno/frontend/src/App.css`

Append these new rules at the end of the file (after the last `@media` block, currently around line 1312):

```css
/* ─── Version Detail Page ─────────────────────────────────────────────────── */

.version-detail-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  margin-bottom: 24px;
}

.version-detail-back:hover {
  color: var(--accent-violet);
}

.version-detail-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.version-detail-description {
  color: var(--text-secondary);
  font-size: 1rem;
  line-height: 1.7;
  margin-bottom: 32px;
  max-width: 680px;
}

.version-detail-steps-heading {
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 14px;
}

.version-detail-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
  list-style: none;
  margin-bottom: 40px;
}

.version-detail-step {
  display: flex;
  align-items: center;
  gap: 14px;
}

.version-detail-step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 50%;
  background: rgba(124, 58, 237, 0.10);
  color: var(--accent-violet);
  font-size: 0.78rem;
  font-weight: 700;
}

.version-detail-step-label {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 500;
}

.version-detail-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.version-detail-not-found {
  color: var(--text-secondary);
  font-size: 1rem;
  margin-bottom: 20px;
}
```

---

## 4. New File to Create

### `/root/projects/juno/frontend/src/pages/VersionDetailPage.tsx`

Create this file. Here is the full implementation:

```tsx
import { Link, useNavigate, useParams } from 'react-router-dom';
import { VERSIONS } from '../config';
import SignOutButton from '../auth/SignOutButton';

export default function VersionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const version = VERSIONS.find(v => v.id === id);

  return (
    <main className="app-shell">
      <section className="hero-section">
        <div className="versions-header">
          <p className="eyebrow">Juno Medical Document Simplifier</p>
          <SignOutButton />
        </div>

        <Link className="version-detail-back" to="/versions">
          ← All versions
        </Link>

        {!version ? (
          <>
            <p className="version-detail-not-found">
              Version "{id}" not found.
            </p>
            <Link className="version-table-link" to="/versions">
              Back to versions
            </Link>
          </>
        ) : (
          <div className="glass-card" style={{ padding: '36px 40px' }}>
            {/* Heading row */}
            <div className="version-detail-meta">
              <h1 style={{ fontSize: 'clamp(1.5rem, 4vw, 2.25rem)', fontWeight: 700, margin: 0 }}>
                {version.label}
              </h1>
              {version.isDefault && (
                <span className="version-default-badge">Default</span>
              )}
            </div>

            {/* Description */}
            <p className="version-detail-description">{version.description}</p>

            {/* Pipeline steps */}
            <p className="version-detail-steps-heading">Processing pipeline</p>
            <ol className="version-detail-steps">
              {version.steps.map((step, index) => (
                <li key={step} className="version-detail-step">
                  <span className="version-detail-step-number">{index + 1}</span>
                  <span className="version-detail-step-label">{step}</span>
                </li>
              ))}
            </ol>

            {/* Actions */}
            <div className="version-detail-actions">
              <button
                className="cta-btn"
                onClick={() => navigate(version.path)}
              >
                Use this version →
              </button>
              <Link className="version-detail-back" to="/versions" style={{ marginBottom: 0 }}>
                ← Back to all versions
              </Link>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
```

**Key implementation notes:**

- `useParams<{ id: string }>()` reads the `:id` segment from the URL (e.g. `v1-1`).
- `VERSIONS.find(v => v.id === id)` looks up the version. If not found, shows a graceful "not found" message instead of crashing.
- `useNavigate` is used for the "Use this version" button so it behaves as a proper navigation without opening a new tab.
- `version.steps` is typed `readonly string[]` because of `as const` in `config.ts`. A standard `.map()` works fine — no cast needed.
- Do NOT display `version.apiPath`. It is a backend implementation detail.
- Do NOT import or reference `SignOutButton` from anywhere other than `'../auth/SignOutButton'` — that is the existing path used by `VersionsPage.tsx`.

---

## 5. Acceptance Criteria

Test each of these manually in the browser:

1. **Versions table links updated:** Visiting `/versions` and clicking "Version 1", "Version 1.1", or "Version 1.2" navigates to `/version/v1`, `/version/v1-1`, or `/version/v1-2` respectively — NOT to `/v1`, `/v1-1`, `/v1-2`.

2. **Detail page loads:** Each `/version/:id` URL renders without a white screen or console errors.

3. **Content is correct:** The detail page shows:
   - The correct `label` as the `<h1>` heading
   - A "Default" badge if `version.isDefault` is true (only one version will have this)
   - The full `description` text
   - All pipeline steps in order, numbered from 1
   - A "Use this version →" button

4. **"Use this version" button navigates correctly:** Clicking the button on `/version/v1` goes to `/v1`, on `/version/v1-1` goes to `/v1-1`, on `/version/v1-2` goes to `/v1-2`.

5. **Back navigation works:** The "← All versions" link at the top and "← Back to all versions" link at the bottom both navigate to `/versions`.

6. **Unknown version handled gracefully:** Visiting `/version/v99` shows the "not found" message and a back link — no crash, no blank page.

7. **Sign-out button visible:** The `<SignOutButton />` renders in the top-right of the header on the detail page.

8. **No broken routes:** Existing routes `/v1`, `/v1-1`, `/v1-2`, `/versions`, and `/` still work exactly as before.

---

## 6. Do NOT Change

- `/root/projects/juno/frontend/src/config.ts` — do not modify the `VERSIONS` array or add any fields to it.
- `/root/projects/juno/frontend/src/router.tsx` — do not add route definitions here; routes live in `App.tsx`.
- `/root/projects/juno/frontend/src/pages/v1/V1Page.tsx`, `v1_1/V1_1Page.tsx`, `v1_2/V1_2Page.tsx` — the actual tool pages are unchanged.
- Any existing CSS class definitions — only add new rules, never modify existing ones.
- The `apiPath` field — never render this to the user.
- The catch-all `<Route path="*">` in `App.tsx` — leave it as the last route.
