# Tasks: PresetDataCard UI Redesign (SP08)

Read `PRD.md` in this folder first. SP08 is **frontend-only** — zero backend or API changes. No upstream SP dependencies.

**Assumed starting state:**
- `DatasetGroupRow.tsx` currently owns `DatasetGroupSelection`, per-group accordion logic, tabs, and the "View" preview button.
- `PresetDataCard.tsx` maps `<DatasetGroupRow>` components inside `.preset-data-card-body` (currently `display: grid; gap: 10px`).
- `components/index.ts` line 4 exports `DatasetGroupRow`.
- `PresetDataCard.css` has no two-panel or sidebar selectors; all old accordion selectors (`.preset-data-group`, `.preset-data-tabs`, etc.) will become dead code after this SP and should be removed in Task 3.

---

### Task 1 — Create `PresetDataPanel.tsx`

- **Files:** `frontend/src/components/PresetDataCard/PresetDataPanel.tsx` *(new)*
- **Changes:**
  - Create the file. All logic migrates verbatim from `DatasetGroupRow.tsx` with the following differences:
    - Remove `expanded` local state and `activeTab` local state — both are gone in the new design.
    - Remove `DatasetGroupRowProps` interface — replace with `PresetDataPanelProps` (see below).
    - Rename the component function from `DatasetGroupRow` to `PresetDataPanel` and change the default export accordingly.
    - Rename `handleView` callback label on the "View" button to `"Preview"` (the visible button text changes from `"View"` to `"Preview"`; the function name `handleView` can stay).
  - **Interface block at top of file** (copy-paste exactly):
    ```typescript
    import { useEffect, useRef, useState } from 'react';
    import { getDatasetFileContent } from '../../api/datasets';
    import type { Dataset } from '../../types/datasets';

    export interface DatasetGroupSelection {
      inputs: Set<string>;
      files: Set<string>;
    }

    interface PresetDataPanelProps {
      dataset: Dataset;
      selection: DatasetGroupSelection;
      onSelectionChange: (group: string, selection: DatasetGroupSelection) => void;
    }

    interface PreviewState {
      filename: string;
      content: string;
      loading: boolean;
      error: string | null;
    }
    ```
  - **Internal logic to copy as-is from `DatasetGroupRow.tsx`** (lines 35–102):
    - `allInputsSelected`, `allFilesSelected`, `groupChecked`, `groupPartial` derivations.
    - `groupCheckboxRef` + `useEffect` for `.indeterminate`.
    - `replaceSelection`, `toggleGroup`, `toggleInput`, `toggleFile`.
    - `handleView(filename)` — unchanged including the `previewInput` fallback logic (`Array.from(selection.inputs)[0] ?? dataset.inputs[0]`).
  - **JSX structure** — render exactly this (see PRD §4.7):
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

        {/* Section 3: File types + inline preview */}
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

          {/* Preview appears inside .preset-panel-files, after the file list.
              This keeps file types always visible: the flex column compresses
              the appointment scroll area rather than overflowing the panel.
              ALTERNATIVE (safe fallback): if the flex compression looks bad in
              the browser, move the preview block back outside .preset-panel-files
              (as a 5th sibling of .preset-panel) and add
              `max-height: 200px; overflow-y: auto` to .preset-panel-files in CSS.
              Verify in the browser and choose whichever keeps file types visible
              without overflow. See PRD §9 item 7. */}
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
      </div>
    );
    ```
  - Default export: `export default PresetDataPanel;`
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0 with this file present (even before Tasks 2–3 remove `DatasetGroupRow`).
  - The file is located at `frontend/src/components/PresetDataCard/PresetDataPanel.tsx`.
  - The `DatasetGroupSelection` interface is exported from this file (named export, not default).
  - The component renders a `<div className="preset-panel">` root — confirmed by searching JSX.

---

### Task 2 — Update `PresetDataCard.tsx` — add `activeGroup` state and swap rendering

- **Files:** `frontend/src/components/PresetDataCard/PresetDataCard.tsx`
- **Changes:**
  1. **Update the import on line 4** — replace the `DatasetGroupRow` import with `PresetDataPanel`:
     ```typescript
     // OLD (line 4):
     import DatasetGroupRow, { type DatasetGroupSelection } from '../DatasetGroupRow';

     // NEW:
     import PresetDataPanel, { type DatasetGroupSelection } from './PresetDataPanel';
     ```
  2. **Add `activeGroup` state** inside the `PresetDataCard` function, after the existing `useState` declarations (after line 46):
     ```typescript
     const [activeGroup, setActiveGroup] = useState<string | null>(null);
     ```
  3. **Add the initialization `useEffect`** after the existing dataset-load `useEffect` (after line 71):
     ```typescript
     useEffect(() => {
       if (datasets.length > 0 && activeGroup === null) {
         setActiveGroup(datasets[0].group);
       }
     }, [datasets, activeGroup]);
     ```
  4. **Replace the body JSX** — the `{expanded && ...}` block currently at lines 123–139. Replace it with:
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
                   title={dataset.group}
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
  - **IMPORTANT — do NOT touch:**
    - `const [expanded, setExpanded] = useState(false);` — default stays `false`. Do not change the initial value or the toggle logic.
    - The card header JSX (lines 103–121): title, summary totals, "Choose"/"Collapse" button — leave entirely unchanged.
    - `toBatchSelections`, `emptySelection`, `handleGroupSelectionChange`, `batchSelections`, `selectedGroupCount`, `selectedInputCount`, `selectedFileCount` — all unchanged.
- **Acceptance criteria:**
  - `npx tsc --noEmit` from `frontend/` exits 0.
  - Card renders with `expanded = false` on mount (body hidden by default).
  - No import of `DatasetGroupRow` remains in this file.
  - The `title={dataset.group}` attribute is present on `.preset-panel-tab` buttons (added inline here; PRD §8 item 1 is satisfied by the implementor in this task).

---

### Task 3 — Update `PresetDataCard.css` — replace body grid with two-panel layout; remove dead accordion selectors

- **Files:** `frontend/src/components/PresetDataCard/PresetDataCard.css`
- **Changes:**
  1. **Replace the `.preset-data-card-body` rule** (current lines 53–59):
     ```css
     /* OLD: */
     .preset-data-card-body {
       border-top: 1px solid var(--border);
       display: grid;
       gap: 10px;
       margin-top: 14px;
       padding-top: 14px;
     }

     /* NEW: */
     .preset-data-card-body {
       border-top: 1px solid var(--border);
       margin-top: 14px;
       padding-top: 0;
     }
     ```
  2. **Remove dead accordion selectors** — delete these entire rule blocks (they belonged to `DatasetGroupRow`'s old layout and are now unused):
     - `.preset-data-group { ... }` (lines 71–76)
     - `.preset-data-group-main { ... }` (lines 78–84)
     - `.preset-data-group-label { ... }` (lines 86–91)
     - `.preset-data-group-name { ... }` (lines 100–105)
     - `.preset-data-group-meta { ... }` (lines 107–113)
     - `.preset-data-tabs { ... }` (lines 115–119)
     - `.preset-data-tab { ... }` and `.preset-data-tab.active { ... }` (lines 121–137)
     - `.preset-data-list { ... }` (lines 139–143)

     Keep these existing selectors unchanged — they are still used by `PresetDataPanel`:
     - `.preset-data-status`, `.preset-data-status.error`
     - `.preset-data-option`, `.preset-data-option:hover`, `.preset-data-option-text`
     - `.preset-data-checkbox`
     - `.preset-data-file-label`
     - `.preset-data-view-button`, `.preset-data-toggle` (shared rule on lines 27–39), and their hover/disabled variants
     - `.preset-data-preview*` (all preview rules — lines 177–221)

  3. **Append all new two-panel and sidebar CSS** after the last existing rule (after `.preset-data-preview-content`):
     ```css
     /* ── Two-panel layout ── */

     .preset-panel-layout {
       display: flex;
       height: 480px;
       overflow: hidden;
     }

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
       background: rgba(124, 58, 237, 0.08);
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

     /* ── Right content panel ── */

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
       flex: 1;
       overflow-y: auto;
       padding: 8px 12px;
     }

     .preset-panel-files {
       flex-shrink: 0;
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
- **Acceptance criteria:**
  - None of the deleted selectors (`.preset-data-group`, `.preset-data-group-main`, `.preset-data-group-label`, `.preset-data-group-name`, `.preset-data-group-meta`, `.preset-data-tabs`, `.preset-data-tab`, `.preset-data-list`) remain in the file.
  - `.preset-data-card-body` no longer has `display: grid` or `gap:` properties.
  - All new `.preset-panel-*` selectors are present.
  - `npx tsc --noEmit` from `frontend/` still exits 0 (CSS changes do not affect TypeScript).

---

### Task 4 — Update `components/index.ts` — remove `DatasetGroupRow` export

- **Files:** `frontend/src/components/index.ts`
- **Changes:**
  - Remove line 4 exactly:
    ```typescript
    export { default as DatasetGroupRow }   from './DatasetGroupRow';
    ```
  - Do NOT add any export for `PresetDataPanel` — it is an internal component of `PresetDataCard` and must not appear in the barrel.
- **Acceptance criteria:**
  - `DatasetGroupRow` no longer appears anywhere in `index.ts`.
  - `PresetDataPanel` does NOT appear in `index.ts`.
  - `npx tsc --noEmit` from `frontend/` exits 0 — confirm no other file imports `DatasetGroupRow` from the barrel (run `grep -r "DatasetGroupRow" frontend/src` to check; after this task the only remaining reference should be the source file itself until Task 5 deletes it).

---

### Task 5 — Delete `DatasetGroupRow.tsx`

- **Files:** `frontend/src/components/DatasetGroupRow.tsx` *(deleted)*
- **Changes:**
  - Delete the file. The `DatasetGroupSelection` interface has already been re-exported from `PresetDataPanel.tsx` (Task 1); `PresetDataCard.tsx` has already updated its import (Task 2); `index.ts` has already dropped the barrel export (Task 4).
  - Run `grep -r "DatasetGroupRow" frontend/src` after deletion and confirm zero matches.
- **Acceptance criteria:**
  - `frontend/src/components/DatasetGroupRow.tsx` does not exist.
  - `npx tsc --noEmit` from `frontend/` exits 0.
  - `grep -r "DatasetGroupRow" frontend/src` returns no output.

---

### Task 6 — Write unit tests: `PresetDataPanel.test.tsx`

- **Files:** `frontend/src/tests/components/PresetDataPanel.test.tsx` *(new)*
- **Changes:**
  - Create the file. Reference `frontend/src/tests/components/ConfigurationCard.test.tsx` for the project's testing conventions (import style, render helpers, mock patterns).
  - Mock `../../api/datasets` — specifically `getDatasetFileContent`. Do not mock `listDatasets` in this test file (not used by `PresetDataPanel`).
  - Use a fixed `testDataset` fixture:
    ```typescript
    const testDataset = {
      group: 'group-a',
      inputs: ['input-1', 'input-2', 'input-3'],
      files: ['file.pdf', 'file.txt'],
    };
    const emptySelection = { inputs: new Set<string>(), files: new Set<string>() };
    ```
  - Write all 14 tests from PRD §7 (PresetDataPanel table). Exact test names and assertions to implement:

    | Test name | Key assertion |
    |---|---|
    | `renders appointment list from dataset.inputs` | Each of the 3 inputs renders as a labelled checkbox |
    | `Select All checkbox is unchecked when selection is empty` | `groupCheckboxRef` indeterminate false, not checked |
    | `Select All checkbox is indeterminate when some inputs checked` | After checking 1 of 3 inputs, `indeterminate === true` |
    | `Select All checkbox is checked when all inputs and files checked` | With full selection, `checked === true` and `indeterminate === false` |
    | `clicking Select All when unchecked calls onSelectionChange with all inputs and files` | Spy receives `new Set(['input-1','input-2','input-3'])` for inputs and `new Set(['file.pdf','file.txt'])` for files |
    | `clicking Select All when checked calls onSelectionChange with empty sets` | Spy receives empty sets |
    | `clicking individual appointment toggles it` | Spy called with the toggled input added |
    | `clicking individual file toggles it` | Spy called with the toggled file added |
    | `clicking Preview button calls getDatasetFileContent with first selected input` | Mock API; check args: `(group-a, input-1, file.pdf)` when `input-1` is selected |
    | `Preview shows Loading preview... while fetch pending` | Mock with never-resolving promise; assert text `Loading preview...` |
    | `Preview shows content on success` | Mock resolves with `{ content: 'hello' }`; assert `hello` appears |
    | `Preview shows error message on failure` | Mock rejects; assert error message appears |
    | `Close button on preview sets preview to null` | After preview shows, click Close; assert preview div disappears |
    | `Preview input fallback: if no inputs selected, uses dataset.inputs[0]` | selection.inputs empty; click Preview; assert `getDatasetFileContent` called with `input-1` |

- **Acceptance criteria:**
  - `npx vitest run src/tests/components/PresetDataPanel.test.tsx` (or the project's equivalent test command) — all 14 tests pass, none skipped.
  - No test imports `DatasetGroupRow`.

---

### Task 7 — Write unit tests: `PresetDataCard.test.tsx`

- **Files:** `frontend/src/tests/components/PresetDataCard.test.tsx` *(new)*
- **Changes:**
  - Create the file. Mock `../../api/datasets` — specifically `listDatasets`. Also mock `./PresetDataPanel` (or the relative import path from the test file) as a simple `<div data-testid="preset-panel" />` to keep card-level tests focused on tab/sidebar behavior rather than panel internals.
  - Use a fixed `mockDatasets` fixture:
    ```typescript
    const mockDatasets = [
      { group: 'group-a', inputs: ['i1', 'i2'], files: ['f1.pdf'] },
      { group: 'group-b', inputs: ['i3'],       files: ['f2.txt'] },
    ];
    ```
  - Write the 7 tests from PRD §7 (PresetDataCard table):

    | Test name | Key assertion |
    |---|---|
    | `card renders header with Choose toggle; body hidden by default` | "Choose" button present; body `preset-data-card-body` not rendered (expanded=false) |
    | `clicking Choose expands body; shows loading state initially` | Mock `listDatasets` with pending promise; after click, see `Loading preset data...` |
    | `after datasets load left sidebar renders one tab per group` | Mock resolves with `mockDatasets`; two `.preset-panel-tab` buttons present |
    | `first dataset tab is auto-selected; right panel renders` | First tab has class `active`; `preset-panel` (mocked) is present |
    | `clicking second tab switches panel to second dataset` | Simulate click on second tab; second tab gets class `active`, first loses it |
    | `tab meta shows 0/N when nothing selected` | First tab shows `0/2` (0 of 2 inputs selected) |
    | `header summary updates when onSelectionChange fires` | Prop spy called after user interacts; summary text updates |

- **Acceptance criteria:**
  - All 7 tests pass.
  - No test imports `DatasetGroupRow`.
  - The mocked `PresetDataPanel` prevents panel internals from interfering with card-level assertions.

---

## Summary of what requires you (not a dev agent)

1. **Verify panel height in the browser (PRD §8 item 2).** The spec sets `.preset-panel-layout { height: 480px }`. After implementation, open the upload page at your target viewport (1080p). If the page feels cramped with the NavBar + three stacked cards, reduce to `420px` or `440px`. Update the CSS value in `PresetDataCard.css` after visual confirmation — this is one line.

2. **Confirm preview flex placement (PRD §9 item 7).** Task 1 places the preview inside `.preset-panel-files` (preferred approach). After the feature is running, expand a group with several appointments, click Preview, and verify the appointment list compresses upward gracefully without clipping. If the compression looks bad, move the `{preview && ...}` block in `PresetDataPanel.tsx` to be a sibling of `.preset-panel-files` at the `.preset-panel` level, and add `max-height: 200px; overflow-y: auto` to `.preset-panel-files` in the CSS. This is a one-JSX-block move — no other logic changes.

3. **Verify group name truncation with real API data (PRD §8 item 4).** After the feature lands, check actual group names returned by `listDatasets()`. If names are consistently under ~20 characters at 0.82 rem in 180 px, the ellipsis truncation will never trigger (fine). If names are very long (e.g. `primock57_all_conditions_encounter_2026`), widen `.preset-panel-sidebar { width: }` from `180px` to `200–220px` in `PresetDataCard.css`. The `title={dataset.group}` attribute (added in Task 2) already handles hover tooltip disclosure — no extra code needed.

4. **Run the full manual test checklist (PRD §7 manual tests 1–11)** after all tasks land — specifically items 3 (file types stays visible while scrolling appointments), 9 (preview state resets on tab switch), and 10 (header summary totals update correctly across groups). These are observable behaviors that the automated tests do not cover in full.
