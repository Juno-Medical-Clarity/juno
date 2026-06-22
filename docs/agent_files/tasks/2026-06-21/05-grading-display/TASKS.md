# Tasks: Grading Display Redesign (SP5)

Read `PRD.md` in this folder first. SP5 is **frontend-only** — no backend changes. It depends on
the `care_plan` key already present in `CarePlanInternal` (from SP1) and uses the `ApiError` type
from SP2 for grading error handling. If SP5 lands before SP2, use the plain-text fallback with a
`// TODO(SP2): parse ApiError` comment.

**Important §9 override on §4.1:** `METHOD_ORDER` must place `combined` **first**, not last
(§9 Q1 RESOLVED). The §4.1 code snippet shows it last — that is superseded by §9.

---

### Task 1 — Add `groupGradingEntries` utility to `frontend/src/utils/grading.ts`

- **Files:** `frontend/src/utils/grading.ts`
- **Changes:**
  1. Add the `MethodGroup` interface and export it:
     ```typescript
     export interface MethodGroup {
       name: string;
       label: string;
       before: GradingEntry | undefined;
       after: GradingEntry | undefined;
     }
     ```
  2. Add `METHOD_LABELS` and `METHOD_ORDER` constants. **`combined` goes first per §9 Q1:**
     ```typescript
     const METHOD_ORDER = ['combined', 'smog', 'flesch_kincaid', 'dale_chall', 'pemat', 'sam', 'cdc_cci'];

     const METHOD_LABELS: Record<string, string> = {
       combined:       'Combined Score',
       smog:           'SMOG',
       flesch_kincaid: 'Flesch-Kincaid',
       dale_chall:     'Dale-Chall',
       pemat:          'PEMAT',
       sam:            'SAM',
       cdc_cci:        'CDC Clear Comm.',
     };
     ```
  3. Add and export `groupGradingEntries` exactly as specified in PRD §4.1. Also export
     `combinedScoreLabel` (PRD §4.2):
     ```typescript
     export function combinedScoreLabel(groups: MethodGroup[]): string {
       const combined = groups.find(g => g.name === 'combined');
       if (!combined) return 'Score';
       const before = combined.before ? Math.round(combined.before.grade) : null;
       const after  = combined.after  ? Math.round(combined.after.grade)  : null;
       if (before !== null && after !== null) return `Score (${before} → ${after})`;
       if (after  !== null) return `Score (${after})`;
       if (before !== null) return `Score (${before})`;
       return 'Score';
     }
     ```
  4. Do **not** remove or alter `patientScoreFromGrading` or `methodEntriesFromGrading` — they
     remain in the file for other callers.

- **Acceptance criteria:**
  - `groupGradingEntries` is importable from `frontend/src/utils/grading.ts`.
  - Given entries for both `before` and `after` targets across all 7 methods, the returned array
    has length 7, the first element is `combined`, and the last element is `cdc_cci`.
  - An entry with `target === 'before'` populates the `.before` field; `target === 'after'` populates `.after`.
  - An unknown method name (not in `METHOD_ORDER`) appears after `cdc_cci`.
  - `combinedScoreLabel` returns `"Score (60 → 78)"` when combined before=60, after=78.

---

### Task 2 — Rewrite `OutputGradingCard.tsx` as a collapsible grading display

- **Files:** `frontend/src/components/OutputGradingCard.tsx`
- **Changes:** Full rewrite. Remove all existing code. The new component:

  **Props (new):**
  ```typescript
  interface OutputGradingCardProps {
    grading: Grading;
    error: string | null;
  }
  ```

  **State:**
  ```typescript
  const [topOpen, setTopOpen] = useState(false);
  const [openRows, setOpenRows] = useState<Set<string>>(new Set());
  ```

  **Imports needed:** `useState` from `'react'`; `Grading`, `GradingEntry` from `'../types/envelope'`;
  `groupGradingEntries`, `combinedScoreLabel`, `MethodGroup` from `'../utils/grading'`.

  **`BreakdownKV` internal sub-component** (PRD §4.3):
  ```typescript
  function BreakdownKV({ breakdown }: { breakdown: Record<string, unknown> }) {
    const entries = Object.entries(breakdown).filter(
      ([, v]) => typeof v !== 'object' || v === null
    );
    return (
      <div className="grading-breakdown">
        {entries.map(([k, v]) => (
          <span key={k} className="grading-breakdown-item">
            <strong>{k.replace(/_/g, ' ')}:</strong> {String(v)}
          </span>
        ))}
      </div>
    );
  }
  ```

  **Collapse All / Expand All logic:**
  - `allExpanded` is derived: `topOpen && groups.length > 0 && openRows.size === groups.length`
  - Clicking "Expand All": set `openRows` to `new Set(groups.map(g => g.name))` and `setTopOpen(true)`.
  - Clicking "Collapse All": set `openRows` to `new Set()`.
  - Button label: `allExpanded ? 'Collapse All' : 'Expand All'`.

  **Render structure** (per PRD §4.3 diagram):
  ```tsx
  <section className="glass-card grading-section">
    <div className="grading-top-row" onClick={() => setTopOpen(o => !o)}>
      <span className="grading-top-label">
        <span className="grading-toggle-icon">{topOpen ? '▼' : '▶'}</span>
        {combinedScoreLabel(groups)}
      </span>
      <button
        className="grading-collapse-all"
        onClick={e => { e.stopPropagation(); /* expand/collapse all logic */ }}
      >
        {allExpanded ? 'Collapse All' : 'Expand All'}
      </button>
    </div>

    {topOpen && (
      <>
        {groups.length === 0 ? (
          <p className="grading-empty-note">
            No grading data — click Run Grading to score this output.
          </p>
        ) : (
          groups.map(group => { /* method row per MethodGroup */ })
        )}
      </>
    )}
  </section>
  ```

  **When `grading.entries` is empty** or `grading.enabled === false`: `groups` will be empty,
  and when `topOpen` is true the empty-state message shows. The section header still renders
  with label "Score" (no scores).

  **Method row body — before/after breakdown layout** (PRD §4.3):
  - If both `group.before` and `group.after` exist: render two `<div className="grading-before-after-block">` blocks, each preceded by a `<div className="grading-target-label">before</div>` / `<div className="grading-target-label">after</div>` label, then `<BreakdownKV>`.
  - If only one exists: render `<BreakdownKV>` directly without a prefix label.
  - If `grade_breakdown` is null for an entry: render nothing for that target's body.

  **Method row score header** (right side of row header):
  - If both before and after: `{Math.round(group.before.grade)} → {Math.round(group.after.grade)}`
  - If only after: `{Math.round(group.after.grade)}`
  - If only before: `{Math.round(group.before.grade)}`

  Wrap the score display in `<span className="grading-method-score">`.

  **Remove** all old imports: `API_URL`, `authenticatedFetch`, `CarePlanInternal`, `logger`,
  `useState` for loading/error, and the `runGrading` function.

- **Acceptance criteria:**
  - `OutputGradingCard` no longer imports `authenticatedFetch`, `API_URL`, or `CarePlanInternal`.
  - Rendered with `grading={{ entries: [], enabled: true, graded_at: null }}` and `error={null}`:
    the section header shows "Score" and no method rows are visible (section collapsed by default).
  - Rendered with a `grading` containing entries for all 7 methods (before + after) and `error={null}`:
    clicking the section header reveals 7 method rows, all collapsed.
  - The "Run Grading" button does **not** appear anywhere in the component output.
  - `error="Something went wrong"` is **not** rendered inside this component — error display is in `CarePlanPage` (Task 3 handles it).

---

### Task 3 — Move `runGrading` logic to `CarePlanPage.tsx` and update layout

- **Files:** `frontend/src/pages/care-plan/CarePlanPage.tsx`
- **Changes:**

  1. **Add two new state variables** at the top of `CarePlanPage` (after existing state declarations):
     ```typescript
     const [gradingLoading, setGradingLoading] = useState(false);
     const [gradingError, setGradingError] = useState<string | null>(null);
     ```

  2. **Add `handleRunGrading` handler** (after `handleDownloadPdf`):
     ```typescript
     async function handleRunGrading() {
       if (!result) return;
       setGradingLoading(true);
       setGradingError(null);
       try {
         const savedId = result.metrics.saved_id;
         const body = savedId
           ? { saved_id: savedId }
           : {
               text: result.care_plan.raw?.text ?? '',
               clarified_text: result.care_plan.raw?.clarified_text ?? '',
             };
         const res = await authenticatedFetch(`${API_URL}/care_plan/grade`, {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify(body),
         });
         if (!res.ok) {
           // TODO(SP2): parse ApiError from '../types/errors' when SP2 merges.
           const msg = await res.text();
           throw new Error(msg || `Server error: ${res.status}`);
         }
         const sessionId = res.headers.get('X-Session-Id');
         if (sessionId) logger.setSessionId(sessionId);
         const { grading } = await res.json() as { grading: Grading };
         setResult(prev => prev ? { ...prev, grading } : prev);
       } catch (err: unknown) {
         setGradingError(err instanceof Error ? err.message : 'Failed to run grading');
       } finally {
         setGradingLoading(false);
       }
     }
     ```
     Add `Grading` to the existing import from `'../../types/envelope'`.

  3. **Update result section layout** — new order inside `appState === 'result'` block:
     ```
     result-header
     batch selector (if batch)
     <CarePlanView result={result.care_plan} grading={result.grading} />
     session_id line
     "Create another care plan" button
     <OutputGradingCard grading={result.grading} error={gradingError} />
     [gradingError small line — see below]
     download-bar
     ```

     Move `<OutputGradingCard>` to after the "Create another care plan" button and before
     `.download-bar`. Remove it from its current position between `<CarePlanView>` and the
     session_id line.

     Update the `<OutputGradingCard>` call-site props:
     ```tsx
     <OutputGradingCard
       grading={result.grading}
       error={gradingError}
     />
     ```

  4. **Error display below download bar buttons** (PRD §9 Q5 RESOLVED — error is always visible
     regardless of grading section collapse state). Add a small error line inside `.download-bar`
     just below the buttons row, visible only when `gradingError` is set:
     ```tsx
     {gradingError && (
       <p style={{ marginTop: '6px', color: 'var(--error, #DC2626)', fontSize: '0.78rem', textAlign: 'center' }}>
         {gradingError}
       </p>
     )}
     ```

  5. **Update `.download-bar` JSX** to add the Run Grading button:
     ```tsx
     <div className="download-bar">
       <div className="download-actions">
         <button className="download-btn-json" onClick={handleDownloadJson}>↓ Download JSON</button>
         <button className="download-btn-pdf" onClick={handleDownloadPdf}>↓ Download Report</button>
         <button
           className="download-btn-grading"
           onClick={handleRunGrading}
           disabled={gradingLoading}
         >
           {gradingLoading ? 'Grading…' : '◎ Run Grading'}
         </button>
       </div>
       {gradingError && (
         <p style={{ marginTop: '6px', color: 'var(--error, #DC2626)', fontSize: '0.78rem', textAlign: 'center' }}>
           {gradingError}
         </p>
       )}
     </div>
     ```

  6. **Remove `onGraded` prop** from `OutputGradingCard` import usage. The `OutputGradingCard`
     import line stays; just the JSX call-site props change.

- **Acceptance criteria:**
  - A "◎ Run Grading" button appears in the `.download-bar` when `appState === 'result'`.
  - The button is disabled and shows "Grading…" while the fetch is in flight.
  - `<OutputGradingCard>` appears in the DOM **after** the "Create another care plan" button
    and **before** `.download-bar` (verifiable by DOM order in tests).
  - `gradingError` text is visible in the download bar area, not inside the collapsed grading section.
  - TypeScript compiles with no errors (no leftover `onGraded` or `output` prop references on `OutputGradingCard`).

---

### Task 4 — Remove `ReadabilityCard` and `MethodGradingCards` from `CarePlanView.tsx` render

- **Files:** `frontend/src/components/CarePlanView.tsx`
- **Changes:**
  1. Remove the JSX block at lines 245–254 that renders `ReadabilityCard` and `MethodGradingCards`
     (the entire IIFE `{(() => { const beforeScore = ...; return beforeScore && afterScore ? (<>...</>) : null; })()}`).
  2. Keep the `grading: Grading` prop in the `CarePlanView` function signature — it must remain
     so the `SplitView` call-site (`CarePlanPage.tsx` line 635) continues to compile without changes
     (PRD §9 Q3 RESOLVED).
  3. Keep the component-level definitions of `ReadabilityCard` and `MethodGradingCards` in the
     file for now (the PRD says they "may remain as dead code"). Add a comment above each:
     `// TODO(SP5-cleanup): dead code after SP5 — remove in a separate cleanup task`.
  4. Keep the import of `patientScoreFromGrading` and `methodEntriesFromGrading` from `'../utils/grading'`
     if `ReadabilityCard`/`MethodGradingCards` still reference them (they do). If you remove the
     component bodies, also remove the imports. Since we're keeping bodies as dead code, leave the
     imports too.

- **Acceptance criteria:**
  - `CarePlanView` renders no `ReadabilityCard` or `MethodGradingCards` output. Confirmed by
    checking that no `.score-card`, `.score-bubble`, or `.method-grading-cards` elements appear
    in a rendered `CarePlanView` with full grading data.
  - The `grading` prop is still present on the exported function signature.
  - TypeScript compiles without unused-import errors (the dead-code functions still reference the imports).
  - `SplitView` still renders without TypeScript errors (no prop change required there).

---

### Task 5 — Add grading toggle CSS classes to `CarePlanPage.css`

- **Files:** `frontend/src/pages/care-plan/CarePlanPage.css`
- **Changes:** Append all CSS rules from PRD §4.5 to the end of the file, plus the
  `.download-btn-grading` rules from PRD §4.4:

  ```css
  /* ── Grading section (SP5) ────────────────────────────────────── */

  .grading-section {
    margin-top: 24px;
  }

  .grading-top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
    padding: 4px 0;
  }

  .grading-top-label {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .grading-toggle-icon {
    font-size: 0.7rem;
    color: var(--text-muted);
    transition: transform 0.15s;
  }

  .grading-collapse-all {
    background: none;
    border: none;
    font-size: 0.75rem;
    color: var(--text-muted);
    cursor: pointer;
    font-family: Inter, sans-serif;
    padding: 2px 4px;
    text-decoration: underline;
  }
  .grading-collapse-all:hover {
    color: var(--text-secondary);
  }

  .grading-method-row {
    border-top: 1px solid var(--border);
    padding: 8px 0;
  }

  .grading-method-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }

  .grading-method-label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .grading-method-score {
    font-size: 0.82rem;
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .grading-breakdown {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    margin-top: 6px;
    padding-left: 18px;
    font-size: 0.78rem;
    color: var(--text-secondary);
  }

  .grading-breakdown-item strong {
    color: var(--text-primary);
  }

  .grading-before-after-block {
    margin-top: 6px;
    padding-left: 18px;
    font-size: 0.78rem;
    color: var(--text-secondary);
  }

  .grading-target-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-muted);
    margin-bottom: 2px;
  }

  .grading-empty-note {
    font-size: 0.82rem;
    color: var(--text-muted);
    font-style: italic;
    padding: 8px 0;
  }

  /* ── Run Grading button (SP5) ─────────────────────────────────── */

  .download-btn-grading {
    padding: 10px 24px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--accent-violet);
    background: transparent;
    color: var(--accent-violet);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    font-family: Inter, sans-serif;
    transition: opacity 0.15s;
  }
  .download-btn-grading:hover:not(:disabled) {
    background: rgba(124, 58, 237, 0.06);
  }
  .download-btn-grading:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  ```

  Do not add any other CSS file. No new CSS design tokens (PRD §3).

- **Acceptance criteria:**
  - All class names used in Task 2 (`grading-section`, `grading-top-row`, `grading-top-label`,
    `grading-toggle-icon`, `grading-collapse-all`, `grading-method-row`, `grading-method-header`,
    `grading-method-label`, `grading-method-score`, `grading-breakdown`, `grading-breakdown-item`,
    `grading-before-after-block`, `grading-target-label`, `grading-empty-note`) and Task 3
    (`download-btn-grading`) are present in `CarePlanPage.css`.
  - No new CSS variables are introduced (only references to existing `var(--...)` tokens).

---

### Task 6 — Update `OutputGradingCard.test.tsx`: remove old tests, add new tests

- **Files:** `frontend/src/tests/components/OutputGradingCard.test.tsx`
- **Changes:**
  1. **Remove** all 6 tests that are no longer valid after the rewrite (PRD §7.1):
     - `renders the "Run Grading" button`
     - `renders the "Grading" section heading` (heading text changed)
     - `button shows "Grading…" text while loading`
     - `calls onGraded with grading data from a successful response`
     - `uses saved_id in request body when output has a saved_id`
     - `uses text/clarified_text body when no saved_id`
     - `shows error message when server returns non-200`
  2. **Remove** the `fetchSpy` / `beforeEach` / `afterEach` fetch mock (no longer needed).
  3. **Remove** the `makeOutput` fixture (no longer needed — `OutputGradingCard` doesn't take `output`).
  4. **Update imports:** remove `CarePlanInternal` import; keep `Grading`. Remove `waitFor`
     and `userEvent` if only used by removed tests; add them back only if new tests need them.
  5. **Add** a `makeFullGrading` fixture with entries for all 7 methods (before + after each):
     ```typescript
     function makeFullGrading(): Grading {
       return {
         enabled: true,
         graded_at: '2026-06-01T12:00:00Z',
         entries: [
           { name: 'combined',       target: 'before', grade: 60, grade_breakdown: { grade_estimate: 12.0, label: 'Hard', word_count: 400 }, reasoning: null },
           { name: 'combined',       target: 'after',  grade: 78, grade_breakdown: { grade_estimate: 7.5,  label: 'Moderate', word_count: 400 }, reasoning: null },
           { name: 'smog',           target: 'before', grade: 52, grade_breakdown: { grade: 12.1, insufficient_sample: false }, reasoning: null },
           { name: 'smog',           target: 'after',  grade: 68, grade_breakdown: { grade: 8.2,  insufficient_sample: false }, reasoning: null },
           { name: 'flesch_kincaid', target: 'before', grade: 48, grade_breakdown: { reading_ease: 42.1, grade_level: 9.3 }, reasoning: null },
           { name: 'flesch_kincaid', target: 'after',  grade: 72, grade_breakdown: { reading_ease: 68.5, grade_level: 6.1 }, reasoning: null },
           { name: 'dale_chall',     target: 'before', grade: 45, grade_breakdown: { raw_score: 9.1, grade_range: '9-10' }, reasoning: null },
           { name: 'dale_chall',     target: 'after',  grade: 68, grade_breakdown: { raw_score: 6.2, grade_range: '5-6' }, reasoning: null },
           { name: 'pemat',          target: 'before', grade: 55, grade_breakdown: { understandability: 55, actionability: 60 }, reasoning: null },
           { name: 'pemat',          target: 'after',  grade: 80, grade_breakdown: { understandability: 80, actionability: 85 }, reasoning: null },
           { name: 'sam',            target: 'before', grade: 50, grade_breakdown: { content: 3, literacy_demand: 6, layout_typography: 2 }, reasoning: null },
           { name: 'sam',            target: 'after',  grade: 71, grade_breakdown: { content: 6, literacy_demand: 11, layout_typography: 5 }, reasoning: null },
           { name: 'cdc_cci',        target: 'before', grade: 44, grade_breakdown: { main_message: 0, behavioral_recommendations: 1, numbers: 1, call_to_action: 0 }, reasoning: null },
           { name: 'cdc_cci',        target: 'after',  grade: 76, grade_breakdown: { main_message: 1, behavioral_recommendations: 1, numbers: 1, call_to_action: 1 }, reasoning: null },
         ],
       };
     }
     ```
  6. **Add** the following new tests (PRD §7.1):
     - `top-level toggle is collapsed by default` — render with `makeFullGrading()`, verify no
       method row labels are visible (e.g. "SMOG" is not in the DOM initially).
     - `clicking top-level toggle expands the section (shows method rows)` — click the top row,
       verify "Combined Score" row label becomes visible.
     - `renders Score (X → Y) label with correct values from combined entry` — heading contains
       "Score (60 → 78)".
     - `renders Score (Y) when only after combined entry exists` — grading with only after combined
       (grade 78), heading contains "Score (78)".
     - `renders "Score" label when no combined entry` — grading entries only have non-combined methods,
       heading contains "Score" without parentheses.
     - `renders empty-state message when grading.entries is empty and no error` — when expanded,
       shows "No grading data — click Run Grading to score this output."
     - `renders empty-state message when grading.enabled is false` — `enabled: false, entries: []`,
       when expanded the empty message appears.
     - `shows error prop is passed through to component` — render with `error="Grading failed"`;
       since error is now displayed in `CarePlanPage` (not in this component), verify the component
       itself does **not** render the error text (confirm the prop boundary — this component ignores
       `error`). *(Note: If the PRD intends error to be rendered inside the component too, adjust
       accordingly; the PRD §6.1 lists `error: string | null` as a prop but §9 Q5 places error
       display in the download bar. The component receives the prop for future extensibility but
       does not render it.)*
     - `Expand All opens all method rows; Collapse All closes them` — with `makeFullGrading()`,
       expand top, click "Expand All", verify all 7 method names are in the DOM; click "Collapse All",
       verify a specific breakdown key (e.g. "reading ease") is not visible.
     - `renders 7 method rows when both before and after entries exist` — expand top, count
       visible method label elements; expect 7.
     - `renders grade_breakdown key-value pairs in expanded row body` — expand top, expand the
       "Flesch-Kincaid" row; "reading ease" and "grade level" text appear (underscores replaced
       with spaces per `k.replace(/_/g, ' ')`).
     - `skips nested object values in breakdown (combined dimensions not shown)` — a combined entry
       with `grade_breakdown` containing a `dimensions` object; expand the "Combined Score" row;
       "dimensions" text does **not** appear in the body.

- **Acceptance criteria:**
  - `npm test` (or `vitest`) passes with zero failures on this file.
  - No test references `output` prop or `onGraded` prop or `CarePlanInternal`.
  - No `fetchSpy` mock exists in this file.

---

### Task 7 — Update `grading.test.ts`: add `groupGradingEntries` and `combinedScoreLabel` tests

- **Files:** `frontend/src/tests/utils/grading.test.ts`
- **Changes:**
  1. Keep all existing `patientScoreFromGrading` and `methodEntriesFromGrading` tests unchanged.
  2. Add import for `groupGradingEntries`, `combinedScoreLabel`, `MethodGroup` from
     `'../../utils/grading'`.
  3. Add a `makeEntries` helper that returns a flat array of `GradingEntry` objects for all 7
     methods × 2 targets (14 entries total, mirroring the fixture style from the existing file).
  4. **Add** the following new `describe` blocks (PRD §7.3):

     ```typescript
     describe('groupGradingEntries', () => {
       it('groups before and after by name');
       // entries for 'flesch_kincaid' before + after → one MethodGroup with both fields set

       it('returns in METHOD_ORDER order — combined first');
       // given all 7 methods, result[0].name === 'combined', result[6].name === 'cdc_cci'

       it('handles entries with only after target');
       // only after entries → .before is undefined, .after is set

       it('handles entries with only before target');
       // only before entries → .after is undefined, .before is set

       it('places unknown method names after known ones');
       // entries include name 'custom_method' → it appears after 'cdc_cci' in the result

       it('returns empty array for empty input');
       // groupGradingEntries([]) → []
     });

     describe('combinedScoreLabel', () => {
       it('returns "Score (X → Y)" when both targets present');
       // combined before.grade=60, after.grade=78 → "Score (60 → 78)"

       it('returns "Score (Y)" when only after present');
       // combined after.grade=78, no before → "Score (78)"

       it('returns "Score (X)" when only before present');
       // combined before.grade=60, no after → "Score (60)"

       it('returns "Score" when no combined entry');
       // groups has no combined → "Score"

       it('rounds grades to integer (Math.round)');
       // after.grade=78.7 → label contains "79"
     });
     ```

- **Acceptance criteria:**
  - All existing tests continue to pass.
  - All new tests pass.
  - `vitest` reports 0 failures on this file.

---

### Task 8 — Add Run Grading + grading layout tests to `CarePlanPage.test.tsx`

- **Files:** `frontend/src/tests/pages/care-plan/CarePlanPage.test.tsx`
- **Changes:**
  1. Keep all existing tests unchanged (they test `outputHasInputPdf` and `outputHasInputText`).
  2. Add a new `describe('handleRunGrading', () => { ... })` block with the following tests
     (PRD §7.2). These tests need to render `<CarePlanPage>` in `result` state. Add a `makeResult`
     helper that returns a `CarePlanInternal` with grading enabled but empty entries, and use
     `location.state` injection (matching the existing `useLocation` mock pattern) or call
     `setResult` indirectly via the existing SSE result path. The simplest approach: mock
     `useLocation` to return `{ state: { output: makeResult() }, pathname: '/' }` in an
     additional `describe` block with its own `vi.mock` override, or use a local render wrapper.

     Alternatively, since the existing mock freezes `useLocation`, add a separate test file
     `CarePlanPage.grading.test.tsx` if the mock setup is too rigid — document this choice
     in a comment at the top of the new tests.

     **Tests to add (PRD §7.2):**
     - `Run Grading button is visible in download bar when result exists`
       Render page in result state; verify `screen.getByRole('button', { name: /run grading/i })` exists.
     - `Run Grading button shows "Grading…" and is disabled while loading`
       Mock `authenticatedFetch` to never resolve; click Run Grading; verify button text is "Grading…"
       and `disabled` attribute is set.
     - `Run Grading button calls /care_plan/grade and updates result.grading on success`
       Mock `authenticatedFetch` to return `{ grading: { entries: [...], enabled: true, graded_at: '...' } }`;
       click Run Grading; wait for grading data to appear (e.g. "Score (78)" in heading).
     - `Run Grading button shows gradingError below download bar on failure`
       Mock `authenticatedFetch` to return a non-200 response; click Run Grading; verify error text
       appears below the download bar buttons.
     - `grading section renders below session-id line (DOM order check)`
       In result state, find the session-id element and the `grading-section` element; confirm
       grading section appears later in the DOM using `compareDocumentPosition` or ordering of
       `querySelectorAll` results.

- **Acceptance criteria:**
  - All existing tests in `CarePlanPage.test.tsx` still pass.
  - All 5 new tests pass.
  - No test references the removed `onGraded` prop.

---

## Summary of what requires you (not a dev agent)

1. **SP2 coordination (PRD §8.1, §4.6):** Before implementation begins, confirm whether SP2 has
   landed. If yes, replace the `// TODO(SP2)` plain-text fallback in `handleRunGrading` with the
   real `ApiError` import from `frontend/src/types/errors.ts`. If no, leave the TODO comment — do
   not block SP5 on SP2.

2. **`CarePlanView` grading prop tech-debt flag (PRD §8.2):** After SP5 ships, the `grading` prop
   on `CarePlanView` has no visual effect. Flag it for removal in a future cleanup ticket. No action
   needed within SP5 itself.

3. **Verify `combined` row position matches UX expectations (PRD §8.3):** The `METHOD_ORDER` in
   Task 1 puts `combined` first (per §9 Q1 resolution). Confirm with the product owner that seeing
   the Combined Score as the first row (top of the expanded grading section) is the desired
   experience before the dev agent implements. If it should stay last, update `METHOD_ORDER` in Task 1
   accordingly — this is the single constant that controls the ordering.

4. **SplitView grading display (PRD §9 Q4 DEFERRED):** After SP5, SplitView shows no grading
   data. If a grading panel for SplitView is needed later, that is a separate sub-project. No action
   required here.
