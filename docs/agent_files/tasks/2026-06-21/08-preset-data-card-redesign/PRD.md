# PRD: PresetDataCard UI Redesign (SP08)

Sub-project 8 — no upstream dependencies. Frontend-only; zero backend or API changes.

## 1. Problem

The current `PresetDataCard` body uses a per-group accordion pattern (`DatasetGroupRow`). Each group must be expanded individually, and appointments ("inputs") and file types live on separate horizontal tabs inside each accordion. When many groups exist, the user must expand and switch tabs repeatedly. The layout makes it hard to see all file types while selecting appointments, and the file preview appears at the bottom of the accordion — far from the file list on large datasets (57+ inputs forces scrolling away from context).

## 2. Goals

1. Replace per-group accordions with a persistent two-panel layout: a left sidebar of dataset-group tabs + a right content panel.
2. Unify appointment selection and file-type selection into a single view per dataset group (no tab-switching within the panel).
3. Inline preview appears in the right panel directly below the file list — contextually close to the file it previews.
4. The active group is always visible; the user never needs to "expand" a group.
5. Remove `DatasetGroupRow.tsx` entirely; replace with new `PresetDataPanel.tsx`.
6. Preserve all existing state shapes, callback contracts, and header summary logic unchanged.

## 3. Non-Goals

- No backend or API changes. `getDatasetFileContent` signature is unchanged.
- No changes to `BatchDatasetSelection`, `toBatchSelections`, or `onSelectionChange` prop — callers are unaffected.
- No changes to the card header (title, summary totals, "Choose" / "Collapse" toggle).
- No changes to loading/error state rendering in `PresetDataCard`.
- Mobile/responsive layout of the two-panel split is out of scope.
- Virtualization of the appointment list (57 items is manageable with CSS scroll).
- No pagination or search/filter on the appointment list.

## 4. Architecture Decisions

### 4.1 File map — old → new

| Old file | Fate | New file |
|---|---|---|
| `frontend/src/components/DatasetGroupRow.tsx` | DELETED | — |
| `frontend/src/components/PresetDataCard/PresetDataCard.tsx` | MODIFIED | same path |
| `frontend/src/components/PresetDataCard/PresetDataCard.css` | MODIFIED (significant additions) | same path — all new styles go here; no separate PresetDataPanel.css |
| `frontend/src/components/index.ts` | MODIFIED (remove DatasetGroupRow export) | same path |
| — | NEW | `frontend/src/components/PresetDataCard/PresetDataPanel.tsx` |

**Decision: co-locate `PresetDataPanel.css` into `PresetDataCard.css`.**
Both components live in the same folder and share design tokens. Splitting into a second CSS file adds a build import without architectural benefit. All new selectors will be clearly blocked under a `/* ── PresetDataPanel ── */` comment header.

### 4.2 `DatasetGroupSelection` interface — migration

Currently exported from `DatasetGroupRow.tsx`:
```typescript
export interface DatasetGroupSelection {
  inputs: Set<string>;
  files: Set<string>;
}
```

After deletion of `DatasetGroupRow.tsx` this interface moves to `PresetDataPanel.tsx` and is re-exported from there. `PresetDataCard.tsx` updates its import from `'../DatasetGroupRow'` to `'./PresetDataPanel'`. No shape change.

### 4.3 New state in `PresetDataCard` — `activeGroup`

```typescript
const [activeGroup, setActiveGroup] = useState<string | null>(null);
```

**Initialization:** `null` on mount. A `useEffect` watching `datasets` sets `activeGroup` to `datasets[0].group` when datasets first arrive (and `activeGroup` is still `null`). This avoids showing an empty right panel on load without hard-coding a group name.

```typescript
useEffect(() => {
  if (datasets.length > 0 && activeGroup === null) {
    setActiveGroup(datasets[0].group);
  }
}, [datasets, activeGroup]);
```

If datasets change (unlikely in practice), the guard `activeGroup === null` means the active group is never reset involuntarily after the user has clicked a tab.

### 4.4 New `PresetDataCard` body JSX structure

The `.preset-data-card-body` `<div>` changes from `display: grid; gap: 10px` (stacked accordions) to `display: flex; height: 480px` (fixed-height two-panel). The height is fixed to make the left sidebar and right panel co-terminate; the appointment list scrolls independently inside the right panel.

```tsx
{expanded && (
  <div className="preset-data-card-body">
    {loading && <div className="preset-data-status">Loading preset data...</div>}
    {error && <div className="preset-data-status error">{error}</div>}
    {!loading && !error && datasets.length === 0 && (
      <div className="preset-data-status">No preset datasets found.</div>
    )}
    {!loading && !error && datasets.length > 0 && (
      <div className="preset-panel-layout">
        {/* LEFT: vertical tab list */}
        <nav className="preset-panel-sidebar" aria-label="Dataset groups">
          {datasets.map(dataset => (
            <button
              key={dataset.group}
              type="button"
              className={`preset-panel-tab ${activeGroup === dataset.group ? 'active' : ''}`}
              onClick={() => setActiveGroup(dataset.group)}
              aria-selected={activeGroup === dataset.group}
            >
              <span className="preset-panel-tab-name">{dataset.group}</span>
              <span className="preset-panel-tab-meta">
                {selectionByGroup[dataset.group]?.inputs.size ?? 0}/{dataset.inputs.length}
              </span>
            </button>
          ))}
        </nav>

        {/* RIGHT: content panel for the active group */}
        <div className="preset-panel-content">
          {activeGroup !== null && (() => {
            const dataset = datasets.find(d => d.group === activeGroup);
            if (!dataset) return null;
            return (
              <PresetDataPanel
                dataset={dataset}
                selection={selectionByGroup[activeGroup] ?? emptySelection()}
                onSelectionChange={handleGroupSelectionChange}
              />
            );
          })()}
        </div>
      </div>
    )}
  </div>
)}
```

The IIFE inside the content div is acceptable for clarity; alternatively extract to a variable above the return.

### 4.5 `PresetDataPanel` props interface

```typescript
// frontend/src/components/PresetDataCard/PresetDataPanel.tsx

import { useEffect, useRef, useState } from 'react';
import { getDatasetFileContent } from '../../api/datasets';
import type { Dataset } from '../../types/datasets';

export interface DatasetGroupSelection {
  inputs: Set<string>;
  files: Set<string>;
}

interface PresetDataPanelProps {
  dataset: Dataset;                // { group: string; inputs: string[]; files: string[] }
  selection: DatasetGroupSelection; // current checked state for this group
  onSelectionChange: (group: string, selection: DatasetGroupSelection) => void;
}

interface PreviewState {
  filename: string;
  content: string;
  loading: boolean;
  error: string | null;
}
```

`PresetDataPanel` receives no `activeGroup` prop — the parent controls which group is mounted by rendering only the active dataset's panel. This means the preview state resets whenever the user switches groups, which is intentional (avoids stale preview text from a previous group).

### 4.6 `PresetDataPanel` internal logic

All checkbox logic migrates verbatim from `DatasetGroupRow`:

- `allInputsSelected`, `allFilesSelected`, `groupChecked`, `groupPartial` — same derivations.
- `groupCheckboxRef` + `useEffect` to set `.indeterminate` — unchanged.
- `toggleGroup`, `toggleInput`, `toggleFile` — copied as-is.
- `handleView(filename)` — copied as-is. Preview input: `Array.from(selection.inputs)[0] ?? dataset.inputs[0]` (first selected, or first in list if none selected — same logic as current).

The only logic removed: `expanded` local state and `activeTab` local state (both are now handled by the parent via `activeGroup`).

### 4.7 `PresetDataPanel` JSX structure

```tsx
return (
  <div className="preset-panel">
    {/* Section 1: Select All */}
    <div className="preset-panel-select-all">
      <label className="preset-data-option">
        <input
          ref={groupCheckboxRef}
          className="preset-data-checkbox"
          type="checkbox"
          checked={groupChecked}
          onChange={toggleGroup}
        />
        <span className="preset-data-option-text">
          Select All ({dataset.inputs.length} appointment{dataset.inputs.length === 1 ? '' : 's'})
        </span>
      </label>
    </div>

    <hr className="preset-panel-divider" />

    {/* Section 2: Appointment list (scrollable) */}
    <div className="preset-panel-appointments">
      {dataset.inputs.length === 0 && (
        <div className="preset-data-status">No appointments found for this group.</div>
      )}
      {dataset.inputs.map(input => (
        <label className="preset-data-option" key={input}>
          <input
            className="preset-data-checkbox"
            type="checkbox"
            checked={selection.inputs.has(input)}
            onChange={() => toggleInput(input)}
          />
          <span className="preset-data-option-text">{input}</span>
        </label>
      ))}
    </div>

    <hr className="preset-panel-divider" />

    {/* Section 3: File types */}
    <div className="preset-panel-files">
      <div className="preset-panel-files-heading">File types</div>
      {dataset.files.length === 0 && (
        <div className="preset-data-status">No files found for this group.</div>
      )}
      {dataset.files.map(filename => (
        <div className="preset-data-option" key={filename}>
          <label className="preset-data-file-label">
            <input
              className="preset-data-checkbox"
              type="checkbox"
              checked={selection.files.has(filename)}
              onChange={() => toggleFile(filename)}
            />
            <span className="preset-data-option-text">{filename}</span>
          </label>
          <button
            className="preset-data-view-button"
            type="button"
            disabled={dataset.inputs.length === 0}
            onClick={() => void handleView(filename)}
          >
            Preview
          </button>
        </div>
      ))}
    </div>

    {/* Section 4: Inline preview (conditional) */}
    {preview && (
      <div className="preset-data-preview">
        <div className="preset-data-preview-header">
          <div className="preset-data-preview-title">{preview.filename}</div>
          <button
            className="preset-data-preview-close"
            type="button"
            onClick={() => setPreview(null)}
          >
            Close
          </button>
        </div>
        <div className={`preset-data-preview-content ${preview.error ? 'error' : ''}`}>
          {preview.loading ? 'Loading preview...' : preview.error ?? preview.content}
        </div>
      </div>
    )}
  </div>
);
```

Note: the button label changes from "View" to "Preview" to match the locked decision language ("Preview link").

### 4.8 CSS — two-panel layout container

Added to `PresetDataCard.css`, replacing the current `.preset-data-card-body` `display: grid; gap: 10px` rule:

```css
/* ── Two-panel layout ── */

.preset-data-card-body {
  border-top: 1px solid var(--border);
  margin-top: 14px;
  padding-top: 0;   /* panel layout handles its own spacing */
}

.preset-panel-layout {
  display: flex;
  height: 480px;    /* fixed height so both panels co-terminate */
  overflow: hidden;
}
```

**Height rationale:** 480 px fits comfortably below the card header without pushing the ConfigurationCard off-screen on a 1080p viewport. At 57 appointments, each row ~34 px tall, the list needs ~1940 px — it scrolls inside the fixed panel height. If the dataset has few groups and few appointments, the panel will feel spacious.

### 4.9 CSS — left sidebar tabs

```css
.preset-panel-sidebar {
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  gap: 2px;
  overflow-y: auto;
  padding: 10px 6px;
  width: 180px;
}

.preset-panel-tab {
  align-items: flex-start;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  font-family: Inter, sans-serif;
  gap: 2px;
  padding: 8px 10px;
  text-align: left;
  transition: background 0.12s;
  width: 100%;
}

.preset-panel-tab:hover {
  background: var(--surface-hover);
}

.preset-panel-tab.active {
  background: rgba(124, 58, 237, 0.08);  /* violet tint, not full accent */
}

.preset-panel-tab-name {
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

.preset-panel-tab.active .preset-panel-tab-name {
  color: var(--accent-violet);
}

.preset-panel-tab-meta {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 400;
}

.preset-panel-tab.active .preset-panel-tab-meta {
  color: var(--accent-violet);
  opacity: 0.75;
}
```

**Active state:** Uses a violet background tint (`rgba(124,58,237,0.08)`) rather than filled violet — filled violet is too heavy for a sidebar item (the full accent is reserved for pill-tabs and primary buttons). The tab name and meta text shift to `var(--accent-violet)` to confirm selection without relying on background alone (contrast-safe).

**Truncation:** `.preset-panel-tab-name` uses `white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%`. Long group names like `"primock57_all_conditions_encounter"` truncate to `"primock57_all_condi…"` at 180 px sidebar width. Tooltip via native `title` attribute is added by the implementor (see section 8).

### 4.10 CSS — right content panel

```css
.preset-panel-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* ── PresetDataPanel ── */

.preset-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.preset-panel-select-all {
  flex-shrink: 0;
  padding: 10px 12px 8px;
}

.preset-panel-divider {
  border: none;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  margin: 0;
}

.preset-panel-appointments {
  flex: 1;           /* takes all remaining height between the two dividers */
  overflow-y: auto;  /* scrolls independently */
  padding: 8px 12px;
}

.preset-panel-files {
  flex-shrink: 0;    /* pinned below the appointment list */
  padding: 8px 12px 12px;
}

.preset-panel-files-heading {
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
  text-transform: uppercase;
}
```

**Scrolling strategy:** The `.preset-panel` is `height: 100%; display: flex; flex-direction: column`. Select-All and File types sections are `flex-shrink: 0`. The appointment list is `flex: 1; overflow-y: auto`. This pins Select-All at top and File types at the bottom of the panel height, with the appointment list scrolling in the middle — the file types section is always visible without scrolling.

**Preview panel:** Uses the existing `.preset-data-preview`, `.preset-data-preview-header`, `.preset-data-preview-title`, `.preset-data-preview-close`, `.preset-data-preview-content` classes — all already in `PresetDataCard.css`. No new CSS needed for the preview. The preview appears below `.preset-panel-files`, which means it expands the panel downward; since `.preset-panel` is `overflow: hidden` with fixed height, the preview will push up into the appointment scroll area. To fix this, the preview should be inside `.preset-panel-files` as a sibling after the file list, not after the component root. The flex column will compress the appointment list rather than overflow.

**Alternative (cleaner):** Make `.preset-panel-files` + preview together `flex-shrink: 0` but constrained to `max-height: 50%` of the panel. Implementation detail left to developer — either approach is acceptable. See Open Questions.

### 4.11 `components/index.ts` change

```typescript
// REMOVE this line:
export { default as DatasetGroupRow }   from './DatasetGroupRow';

// ADD nothing — PresetDataPanel is an internal component of PresetDataCard,
// not meant for external consumers. It should NOT be exported from the barrel.
```

### 4.12 `PresetDataCard.tsx` import change

```typescript
// OLD
import DatasetGroupRow, { type DatasetGroupSelection } from '../DatasetGroupRow';

// NEW
import PresetDataPanel, { type DatasetGroupSelection } from './PresetDataPanel';
```

Also add: `import { useState } from 'react';` already present; add `activeGroup` state and its initialization `useEffect` (section 4.3).

## 5. API Change Summary

None. `getDatasetFileContent(group, input, filename)` is called unchanged from `PresetDataPanel`. `listDatasets()` is called unchanged from `PresetDataCard`.

## 6. Frontend Change Summary

### Files deleted

| File | Reason |
|---|---|
| `frontend/src/components/DatasetGroupRow.tsx` | Replaced by `PresetDataPanel.tsx` + parent tab state |

### Files modified

| File | Change summary |
|---|---|
| `frontend/src/components/PresetDataCard/PresetDataCard.tsx` | Add `activeGroup` state + init effect; render `preset-panel-layout` (sidebar + `PresetDataPanel`) instead of mapping `DatasetGroupRow`; update import |
| `frontend/src/components/PresetDataCard/PresetDataCard.css` | Replace `.preset-data-card-body` grid with flex; add `.preset-panel-layout`, `.preset-panel-sidebar`, `.preset-panel-tab*`, `.preset-panel-content`, `.preset-panel`, `.preset-panel-select-all`, `.preset-panel-divider`, `.preset-panel-appointments`, `.preset-panel-files`, `.preset-panel-files-heading` |
| `frontend/src/components/index.ts` | Remove `DatasetGroupRow` export line |

### Files added

| File | Purpose |
|---|---|
| `frontend/src/components/PresetDataCard/PresetDataPanel.tsx` | Per-group right panel: Select All + appointment list + file types + inline preview |

### Unchanged

- `frontend/src/types/datasets.ts` — `Dataset`, `BatchDatasetSelection` unchanged.
- `frontend/src/api/datasets.ts` — no changes.
- `PresetDataCardProps`, `toBatchSelections`, `SelectionByGroup`, `emptySelection`, `handleGroupSelectionChange` — all unchanged.
- Card header, summary totals, "Choose" / "Collapse" toggle — unchanged.

## 7. Testing

### Existing tests — impact

No existing test file references `DatasetGroupRow` or `PresetDataCard` directly (confirmed by grep: `frontend/src/tests/` has no imports of either). No test updates are required for deletions.

The `CarePlanPage.test.tsx` mocks `'../../../api/datasets'` and only tests helper functions (`outputHasInputPdf`, `outputHasInputText`); it does not mount `PresetDataCard`. No change needed.

### New tests to write

**`frontend/src/tests/components/PresetDataPanel.test.tsx`** (new file):

| Test | What to assert |
|---|---|
| Renders appointment list from `dataset.inputs` | Each input renders as a labelled checkbox |
| "Select All" checkbox is unchecked when selection is empty | `groupCheckboxRef.current.indeterminate === false`, `checked === false` |
| "Select All" checkbox is indeterminate when some inputs checked | `groupCheckboxRef.current.indeterminate === true` |
| "Select All" checkbox is checked when all inputs + all files checked | `checked === true`, `indeterminate === false` |
| Clicking "Select All" when unchecked → calls `onSelectionChange` with all inputs + files | spy on prop |
| Clicking "Select All" when checked → calls `onSelectionChange` with empty sets | spy on prop |
| Clicking individual appointment toggles it | spy on prop |
| Clicking individual file toggles it | spy on prop |
| Clicking "Preview" button calls `getDatasetFileContent` with first selected input | mock API, check args |
| Preview shows "Loading preview…" while fetch pending | mock with deferred promise |
| Preview shows content on success | assert text |
| Preview shows error message on failure | mock rejection |
| "Close" button on preview sets preview to null | assert preview div disappears |
| Preview input fallback: if no inputs selected, uses `dataset.inputs[0]` | mock API, check `input` arg |

**`frontend/src/tests/components/PresetDataCard.test.tsx`** (new file, minimal):

| Test | What to assert |
|---|---|
| Card renders header with "Choose" toggle; body hidden by default | |
| Clicking "Choose" expands body; shows loading state initially | mock `listDatasets` with pending promise |
| After datasets load, left sidebar renders one tab per group | mock `listDatasets` resolved |
| First dataset tab is auto-selected; right panel renders | assert `preset-panel-tab active` on first group |
| Clicking second tab switches panel to second dataset | simulate click, assert active class moves |
| Tab meta shows `0/N` when nothing selected; updates after selection change | |
| Header summary updates when `onSelectionChange` fires | spy on prop |

### Manual tests

1. Expand card — left sidebar shows all dataset groups; first is auto-selected.
2. The right panel shows "Select All (N appointments)" with correct N.
3. Scroll the appointment list — file types section stays visible at bottom.
4. Check two appointments — "Select All" becomes indeterminate.
5. Check all appointments + all files — "Select All" becomes fully checked.
6. Click "Select All" when checked → all clear.
7. Click "Preview" on a file — inline preview appears below file list.
8. Click "Close" on preview — preview disappears; no scroll jump.
9. Switch to a different group tab — preview panel is gone (state reset), new group's content shows.
10. Header summary totals update correctly after making selections across multiple groups.
11. Group name that is longer than ~18 characters truncates with ellipsis in sidebar tab.

## 8. Manual Intervention Required From You

1. **Add `title` attribute for truncated tab names.** The CSS truncates long group names with ellipsis. The implementor should add `title={dataset.group}` to the `.preset-panel-tab` button so the full name appears on hover. This is a one-line addition but requires confirmation of the group name strings in production — if they are already short (under ~20 chars at 180 px), the title attribute is still good hygiene.

2. **Decide final panel height.** The PRD specifies `480px` for `.preset-panel-layout`. Verify this works at the actual viewport heights the app targets. If the upload page feels cramped at 1080p (NavBar 48px + page top padding + three cards), reduce to `420px`. If users regularly have 10+ groups, consider making the sidebar scrollable (it is already `overflow-y: auto`) and reducing height to `400px`.

3. **Confirm the preview overflow behavior is acceptable.** Section 4.10 notes two approaches for when the preview panel expands: (a) preview pushes the appointment list up (preferred — keeps file types always visible), or (b) the panel just grows taller and potentially overflows `.preset-panel-layout`. Approach (a) is described in the CSS; verify in the browser that the flex layout compresses the appointment scroll area gracefully at common dataset sizes.

4. **Verify group name strings from the real dataset API.** The PRD assumes group names fit reasonably in a 180 px sidebar at 0.82 rem. If real group names from `listDatasets()` are very long (e.g. `"primock57_all_conditions_encounter_2026"`), consider widening the sidebar to 200–220 px or adding a second line of text. Check against the real API response before shipping.

## 9. Open Questions & Decisions

1. **Should `PresetDataPanel` styles go in `PresetDataCard.css` or a new `PresetDataPanel.css`?**
   `[RESOLVED: PresetDataCard.css. Both components are in the same folder and share tokens. One CSS file is simpler; new selectors are clearly blocked under a comment header.]`

2. **Should `activeGroup` default to `null` or immediately to the first group?**
   `[RESOLVED: null on mount, set to first group via useEffect when datasets arrive. Avoids hard-coding a group index before data is loaded; the right panel shows nothing for the ~100ms fetch window (loading state covers this). Simpler than trying to initialize from the datasets array before the first render.]`

3. **Does switching dataset groups reset the preview?**
   `[RESOLVED: Yes — by design. PresetDataPanel is re-mounted when activeGroup changes (it's a new instance of the component keyed implicitly by group). The PreviewState lives in PresetDataPanel local state; unmounting clears it. This avoids stale preview text from a previous group appearing in the new group's panel.]`

4. **Should the appointment list use a virtual scroll library for 57+ items?**
   `[RESOLVED: No. 57 items at ~34 px each is ~1940 px of DOM content — well within browser rendering budget. CSS overflow-y scroll is sufficient. Virtualization adds complexity with no user-perceptible benefit at this scale.]`

5. **Should the left sidebar tabs render as `<button>` or `<a>` elements?**
   `[RESOLVED: button. There is no route change; switching tabs is a pure state update inside the component tree. Using button with aria-selected is the correct ARIA pattern for tab-like controls that don't navigate.]`

6. **Should the preview fetch fire on "Preview" click or on file checkbox check?**
   `[RESOLVED: On "Preview" click — same as current DatasetGroupRow behavior. Fetching on checkbox change would trigger API calls immediately and may surprise users who are scanning the list before selecting. The explicit "Preview" button remains the trigger.]`

7. **Where exactly does the preview panel render relative to flex layout — after `.preset-panel-files` or inside it?**
   `[OPEN: Section 4.10 describes two approaches. The preferred approach (preview inside .preset-panel-files as a sibling of the file list, inside the flex column) compresses the appointment area gracefully. The implementor should verify in browser and choose whichever approach keeps the file types section visible without overflow. If neither works cleanly, a `max-height: 200px; overflow-y: auto` on `.preset-panel-files` with the preview inside it is a safe fallback.]`

8. **Should the tab meta (`0/N`) count only inputs or both inputs and files?**
   `[RESOLVED: Inputs only — it shows selected-inputs / total-inputs. Files are typically fewer and the tab meta is primarily a "how many appointments have I selected in this group" at-a-glance signal. Format: `{selection.inputs.size}/{dataset.inputs.length}`.]`
