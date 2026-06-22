# PRD: Grading Display Redesign (SP5)

Sub-project 5 of 5. **Independent of SP1–SP4** at implementation time; uses the `care_plan` key
already in place from SP1 and should use the `ApiError` TypeScript type from SP2 for error handling
on the Run Grading API call. No backend changes in this sub-project.

## 1. Problem

The current grading display is fragmented and spatially costly:

- `CarePlanView.tsx` renders a `ReadabilityCard` (composite before→after scores in a large
  dedicated card) and `MethodGradingCards` (one `result-card` per method, always expanded) near the
  **top** of the result view, above the clinical content.
- `OutputGradingCard.tsx` is a separate card below the content containing only a heading and the
  "Run Grading" button. It renders nothing when grading entries are absent, leaving dead whitespace
  when grading has not yet run.
- The Download Report button lives in a sticky `.download-bar` at the bottom of the page. The Run
  Grading button is not near it, creating confusion about where grading is initiated.
- There is no way to collapse any grading output. A user who doesn't need grading data scrolls
  through multiple fully-expanded cards to reach their clinical content.
- There is no combined/final score visible at the top level; the `ReadabilityCard` shows the
  composite but the method cards and it are separate unrelated-looking elements.

## 2. Goals

1. Replace the current grading display with a **single collapsible grading section** at the bottom
   of the result view — below all clinical content.
2. The top-level toggle heading shows `Score (X → Y)` where X = combined before grade (integer),
   Y = combined after grade (integer). If only after exists, show `Score (Y)`. Default: **collapsed**.
3. Within the grading section: **one toggle row per scoring method** — smog, flesch_kincaid,
   dale_chall, pemat, sam, cdc_cci — plus a row for `combined` (the final score). Seven rows total
   when both before and after entries are present.
4. Each row header shows `Method Label  before → after` (or just the score if only one target). Row
   body shows the method's `grade_breakdown` key-value pairs (before and after if both exist).
5. **Collapse All / Expand All** text control at top-right of the scores section. Default: all rows
   collapsed.
6. Move Run Grading button: remove from `OutputGradingCard`'s header, add it beside the Download
   Report button in `CarePlanPage`'s `.download-bar`. Use a distinct (outlined/secondary) style vs
   Download Report's primary violet style.
7. Move grading section to the **bottom** of the result view (after session-id line, before the
   "Create another care plan" button — or after it; the important thing is below all clinical
   content). See §4 for exact placement.
8. When no grading entries exist: show a compact inline message `"No grading data — click Run
   Grading to score this output."` inside the collapsed section, not a large empty card.
9. Use only existing CSS variables; add minimal new CSS in `CarePlanPage.css` or inline. Do not
   introduce a new CSS file for this feature.

## 3. Non-Goals

- No backend changes. The grading API endpoint (`POST /care_plan/grade`) is unchanged.
- No visual charts, bar indicators, or progress rings. Compact text-only toggle rows.
- No new CSS design tokens. Only `--accent-violet`, `--border`, `--text-primary`, `--text-secondary`,
  `--text-muted`, `--bg-card`, `--radius-md`, `--radius-sm`, etc. from `App.css`.
- SP5 does NOT redesign `ConfigurationCard` (the "enable grading" toggle at submission time). That
  component is unchanged.
- SP5 does NOT redesign `CarePlanView.tsx`'s ReadabilityCard or MethodGradingCards permanently;
  those are removed from `CarePlanView`'s render in this sub-project (the grading display moves
  entirely into `OutputGradingCard`). The `ReadabilityCard` and `MethodGradingCards` sub-components
  and the `patientScoreFromGrading` utility may be retained in the codebase for now but are no
  longer rendered by `CarePlanView`.
- No changes to `Sidebar.tsx`, `NavBar.tsx`, or any non-grading component.
- No Firestore or SSE changes.

## 4. Architecture Decisions

### 4.1 Data model: grouping entries by method name

`Grading.entries` is a flat list of `GradingEntry` objects. Before and after for the same method
are **separate entries with the same `name` but different `target`**. The UI must group them.

**Grouping function** (new utility, add to `frontend/src/utils/grading.ts`):

```typescript
export interface MethodGroup {
  name: string;           // "smog" | "flesch_kincaid" | ... | "combined"
  label: string;          // display label, e.g. "Flesch-Kincaid"
  before: GradingEntry | undefined;
  after: GradingEntry | undefined;
}

const METHOD_ORDER = ['smog', 'flesch_kincaid', 'dale_chall', 'pemat', 'sam', 'cdc_cci', 'combined'];

const METHOD_LABELS: Record<string, string> = {
  smog:           'SMOG',
  flesch_kincaid: 'Flesch-Kincaid',
  dale_chall:     'Dale-Chall',
  pemat:          'PEMAT',
  sam:            'SAM',
  cdc_cci:        'CDC Clear Comm.',
  combined:       'Combined Score',
};

export function groupGradingEntries(entries: GradingEntry[]): MethodGroup[] {
  const map = new Map<string, MethodGroup>();
  for (const entry of entries) {
    if (!map.has(entry.name)) {
      map.set(entry.name, {
        name: entry.name,
        label: METHOD_LABELS[entry.name] ?? entry.name,
        before: undefined,
        after: undefined,
      });
    }
    const g = map.get(entry.name)!;
    if (entry.target === 'before') g.before = entry;
    else g.after = entry;
  }
  // Return in canonical order; unknown names appended at the end.
  const known = METHOD_ORDER.filter(n => map.has(n)).map(n => map.get(n)!);
  const unknown = [...map.values()].filter(g => !METHOD_ORDER.includes(g.name));
  return [...known, ...unknown];
}
```

This replaces the loose use of `methodEntriesFromGrading` / `patientScoreFromGrading` for display
purposes inside the new component. The existing utilities remain; `groupGradingEntries` is added.

### 4.2 Top-level score label

The top-level heading derives X and Y from the `combined` method group:

```typescript
function combinedScoreLabel(groups: MethodGroup[]): string {
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

### 4.3 `OutputGradingCard.tsx` — complete redesign (old→new)

**Old interface (remove):**
```typescript
interface OutputGradingCardProps {
  output: CarePlanInternal;
  onGraded: (grading: Grading) => void;
}
// Rendered: a header card with title + "Run Grading" button and optional error text.
// No display of grading data.
```

**New interface (keep the same props; the component now also displays):**
```typescript
interface OutputGradingCardProps {
  output: CarePlanInternal;
  onGraded: (grading: Grading) => void;
}
```

The component no longer renders the Run Grading button (that moves to `CarePlanPage`). It does
render all grading data. `runGrading` logic (the API fetch) moves from `OutputGradingCard` to
`CarePlanPage` (see §4.4).

**New render structure:**

```
<section class="glass-card grading-section">
  ┌─ top bar ──────────────────────────────────────────────┐
  │ [▶ / ▼] Score (X → Y)          [Collapse All / Expand All] │
  └────────────────────────────────────────────────────────┘
  [when top-level expanded:]
    ┌─ method row (one per MethodGroup) ─────────────────────┐
    │ [▶ / ▼] Method Label        before → after            │
    │  [when row expanded:]                                  │
    │    breakdown key-value pairs (before + after columns)  │
    └────────────────────────────────────────────────────────┘
  [when entries empty:]
    "No grading data — click Run Grading to score this output."
</section>
```

**State (internal to `OutputGradingCard`):**
```typescript
const [topOpen, setTopOpen] = useState(false);         // default collapsed
const [openRows, setOpenRows] = useState<Set<string>>(new Set());  // all collapsed
```

**Collapse All / Expand All:** a small inline button (text style, no border) at top-right.
Clicking "Expand All" sets `openRows` to a `Set` of all method names and sets `topOpen = true`.
Clicking "Collapse All" clears `openRows`. The label toggles: show "Expand All" when any row is
collapsed, "Collapse All" when all are expanded.

**Simpler approach for the toggle label:** just track a boolean `allExpanded` derived from
`openRows.size === groups.length && topOpen`. Show `allExpanded ? 'Collapse All' : 'Expand All'`.

**Method row body — rendering `grade_breakdown`:**

`grade_breakdown` is `Record<string, unknown> | null`. Each method has different keys:

| Method          | `grade_breakdown` keys (from `scoring_methods.py`)                                            |
|-----------------|-----------------------------------------------------------------------------------------------|
| smog            | `grade` (float), `insufficient_sample` (bool)                                                 |
| flesch_kincaid  | `reading_ease` (float), `grade_level` (float)                                                 |
| dale_chall      | `raw_score` (float), `grade_range` (str)                                                      |
| pemat           | `understandability` (int 0-100), `actionability` (int 0-100)                                  |
| sam             | `content` (int 0-8), `literacy_demand` (int 0-14), `layout_typography` (int 0-6)             |
| cdc_cci         | `main_message` (0/1), `behavioral_recommendations` (0/1), `numbers` (0/1), `call_to_action` (0/1) |
| combined        | `grade_estimate` (float), `label` (str), `word_count` (int), `dimensions` (dict — nested)    |

The breakdown body renders as generic key-value pairs using `Object.entries(breakdown)`. For
`combined`, `dimensions` is a nested dict of dimension scores; render it as a nested sub-table or
just `dimensions: (hidden)` — skip the `dimensions` key for the combined row body to avoid
overwhelming output. Only top-level scalar keys are shown for `combined`.

**Concrete breakdown rendering logic:**

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

This skips nested objects (e.g. `dimensions` in `combined`) automatically. If all values are
objects (no scalars), render nothing for the body — the heading alone is sufficient.

**Before and after breakdown in a single expanded row:**

If both before and after `GradingEntry` exist for a method, show breakdown for both:

```
[before] reading_ease: 42.1  grade_level: 9.3
[after]  reading_ease: 68.5  grade_level: 6.1
```

Use a simple two-row layout with a muted `before` / `after` label prefix. If only one target
exists, show it without a prefix label.

### 4.4 `CarePlanPage.tsx` — Run Grading button + layout changes

**Run Grading fetch logic moves from `OutputGradingCard` to `CarePlanPage`:**

Add state and handler to `CarePlanPage`:
```typescript
const [gradingLoading, setGradingLoading] = useState(false);
const [gradingError, setGradingError] = useState<string | null>(null);

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
      // SP2 ApiError type: use it here when SP2 is merged.
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

**`OutputGradingCard` props change:**

Old:
```typescript
<OutputGradingCard
  output={result}
  onGraded={(newGrading) => setResult(prev => prev ? { ...prev, grading: newGrading } : prev)}
/>
```

New — `OutputGradingCard` no longer needs `output` to make the API call (the call moved up).
It only needs the grading data and error state:
```typescript
interface OutputGradingCardProps {
  grading: Grading;
  error: string | null;
}
```

Pass props:
```typescript
<OutputGradingCard
  grading={result.grading}
  error={gradingError}
/>
```

**Download bar — add Run Grading button:**

Current `.download-bar`:
```tsx
<div className="download-bar">
  <div className="download-actions">
    <button className="download-btn-json" onClick={handleDownloadJson}>↓ Download JSON</button>
    <button className="download-btn-pdf" onClick={handleDownloadPdf}>↓ Download Report</button>
  </div>
</div>
```

New `.download-bar`:
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
</div>
```

**`download-btn-grading` CSS** (add to `CarePlanPage.css`):
```css
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

This is outlined (transparent bg + violet border) vs Download Report's solid violet, making them
visually distinct while related in placement.

**Result section layout — grading at bottom:**

Current order in `result` appState:
```
result-header
batch selector (if batch)
<CarePlanView result={result.care_plan} grading={result.grading} />
<OutputGradingCard output={result} onGraded={...} />    ← currently here
session_id line
"Create another care plan" button
download-bar
```

New order:
```
result-header
batch selector (if batch)
<CarePlanView result={result.care_plan} grading={result.grading} />
session_id line
"Create another care plan" button
<OutputGradingCard grading={result.grading} error={gradingError} />   ← moved to bottom
download-bar
```

Placing grading above the download-bar keeps it associated with the Run Grading button in the bar.

**`CarePlanView` grading removal:**

`CarePlanView.tsx` currently renders `ReadabilityCard` and `MethodGradingCards` inline at the top
of results (lines 246-253). In SP5, remove these from `CarePlanView`'s output. The `grading` prop
on `CarePlanView` is **no longer needed** for display; it can be retained as a prop if
`CarePlanView` is used elsewhere with grading (e.g. `SplitView`), but SP5 removes the two grading
sub-components from its render. The `ReadabilityCard` and `MethodGradingCards` components may
remain in the file as dead code, but should be removed or flagged for cleanup.

Note: `CarePlanView` is passed `grading={result.grading}` in `SplitView` as well
(line 635 of `CarePlanPage.tsx`). After SP5, that prop can stay but has no visual effect.

### 4.5 CSS additions for grading toggle rows

Add to `CarePlanPage.css` (or inline — prefer CSS class for reuse in tests):

```css
/* Grading section */
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
```

### 4.6 SP2 interface required: `ApiError`

SP2 defines a TypeScript `ApiError` type as part of the structured error contract. SP5 needs it
to handle the Run Grading API response in `CarePlanPage.handleRunGrading`. The catch block should
parse the response JSON as `ApiError` when the response Content-Type is `application/json`, falling
back to plain text otherwise.

Tentative usage (exact shape to be confirmed from SP2's PRD):
```typescript
import type { ApiError } from '../types/errors';   // SP2 exports this

// in catch block after res.ok check:
const contentType = res.headers.get('Content-Type') ?? '';
if (contentType.includes('application/json')) {
  const apiErr = await res.json() as ApiError;
  throw new Error(apiErr.message ?? `Server error: ${res.status}`);
} else {
  throw new Error(await res.text() || `Server error: ${res.status}`);
}
```

Until SP2 lands, use the inline fallback (plain text) and add a TODO comment.

### 4.7 Old→New file change summary

| File | Change |
|------|--------|
| `frontend/src/components/OutputGradingCard.tsx` | Full rewrite: remove API call + Run Grading button; add collapsible display with toggle rows. Props: `{ grading: Grading; error: string \| null }` |
| `frontend/src/pages/care-plan/CarePlanPage.tsx` | Move `runGrading` logic here as `handleRunGrading`. Add `gradingLoading`, `gradingError` state. Update `OutputGradingCard` call-site. Move grading below session-id line. Add Run Grading button to `.download-bar`. Remove grading from `CarePlanView`'s render scope (see §4.4). |
| `frontend/src/pages/care-plan/CarePlanPage.css` | Add `.download-btn-grading` and grading toggle row CSS classes |
| `frontend/src/components/CarePlanView.tsx` | Remove `ReadabilityCard` and `MethodGradingCards` from the render output (leave component defs or delete; retain `grading` prop but unused) |
| `frontend/src/utils/grading.ts` | Add `groupGradingEntries`, `MethodGroup`, and `METHOD_LABELS` / `METHOD_ORDER` exports |
| `frontend/src/tests/components/OutputGradingCard.test.tsx` | Update tests: remove "Run Grading" button tests (button no longer in this component), add tests for toggle rows, collapse/expand behavior, empty-state message |
| `frontend/src/tests/pages/care-plan/CarePlanPage.test.tsx` | Add tests for Run Grading button in download bar, `gradingLoading` / `gradingError` states |
| `frontend/src/tests/utils/grading.test.ts` | Add tests for `groupGradingEntries` |

## 5. API Change Summary

No backend changes. The Run Grading endpoint (`POST /care_plan/grade`) is unchanged. The only
change is that the fetch call moves from `OutputGradingCard.tsx` to `CarePlanPage.tsx`.

## 6. Frontend Change Summary

### 6.1 `OutputGradingCard.tsx` full rewrite

- **Remove:** Run Grading button, `loading` / `error` state, `runGrading` async function, `output:
  CarePlanInternal` prop.
- **Add:** Collapsible top-level "Score (X → Y)" toggle. Seven inner method rows (collapsible).
  Collapse All / Expand All control. Empty-state inline message. `BreakdownKV` sub-component for
  rendering `grade_breakdown` key-value pairs.
- **Props (new):** `{ grading: Grading; error: string | null }`.

### 6.2 `CarePlanPage.tsx` changes

- **Add state:** `gradingLoading: boolean`, `gradingError: string | null`.
- **Add handler:** `handleRunGrading()` — extracted from old `OutputGradingCard.runGrading()`, with
  SP2 `ApiError` parsing.
- **Update download-bar JSX:** add `<button className="download-btn-grading" ...>`.
- **Move `<OutputGradingCard>` element:** from between `CarePlanView` and session-id, to between
  session-id line and download-bar.
- **Update `<OutputGradingCard>` props:** from `{ output, onGraded }` to `{ grading: result.grading, error: gradingError }`.

### 6.3 `CarePlanView.tsx` change

Remove the block rendering `ReadabilityCard` and `MethodGradingCards` (lines 246-253). The `grading`
prop signature remains in place to avoid breaking the `SplitView` call-site, but is no longer used
in the render.

### 6.4 `utils/grading.ts` additions

Add `groupGradingEntries(entries: GradingEntry[]): MethodGroup[]` and the supporting
`MethodGroup` interface, `METHOD_ORDER`, `METHOD_LABELS` constants.

## 7. Testing

### 7.1 `OutputGradingCard.test.tsx` — update existing + add new tests

**Remove (tests no longer valid after refactor):**
- `renders the "Run Grading" button` — button no longer in this component.
- `button shows "Grading…" text while loading` — loading state removed from this component.
- `calls onGraded with grading data from a successful response` — API call moved to `CarePlanPage`.
- `uses saved_id in request body when output has a saved_id` — fetch moved to parent.
- `uses text/clarified_text body when no saved_id` — fetch moved to parent.
- `shows error message when server returns non-200` — error now passed as prop.

**Add:**
- `renders empty-state message when grading.entries is empty and no error`.
- `renders empty-state message when grading.enabled is false`.
- `shows error message when error prop is set`.
- `top-level toggle is collapsed by default`.
- `clicking top-level toggle expands the section (shows method rows)`.
- `Expand All opens all method rows; Collapse All closes them`.
- `renders Score (X → Y) label with correct values from combined entry`.
- `renders Score (Y) when only after combined entry exists`.
- `renders "Score" label when no combined entry`.
- `renders 7 method rows when both before and after entries exist`.
- `renders grade_breakdown key-value pairs in expanded row body` (for flesch_kincaid:
  `reading_ease` and `grade_level` should appear).
- `skips nested object values in breakdown (combined dimensions not shown)`.

### 7.2 `CarePlanPage.test.tsx` additions

- `Run Grading button is visible in download bar when result exists`.
- `Run Grading button shows "Grading…" and is disabled while loading`.
- `Run Grading button calls /care_plan/grade and updates result.grading on success`.
- `Run Grading button shows error via gradingError passed to OutputGradingCard`.
- `grading section renders below session-id line (DOM order check)`.

### 7.3 `grading.test.ts` additions

- `groupGradingEntries groups before and after by name`.
- `groupGradingEntries returns in METHOD_ORDER order`.
- `groupGradingEntries handles entries with only after target`.
- `groupGradingEntries handles entries with only before target`.
- `groupGradingEntries places unknown method names after known ones`.
- `combinedScoreLabel returns "Score (X → Y)" when both targets present`.
- `combinedScoreLabel returns "Score (Y)" when only after present`.

## 8. Manual Intervention Required From You

1. **Coordinate SP2 `ApiError` type location before implementation.** The `handleRunGrading` error
   handler in `CarePlanPage` should import `ApiError` from wherever SP2 exports it (likely
   `frontend/src/types/errors.ts`). If SP5 lands before SP2, use the plain-text fallback with a
   `// TODO(SP2): parse ApiError` comment.

2. **Review `CarePlanView` grading prop after SP5.** Once SP5 ships, the `grading: Grading` prop
   on `CarePlanView` has no effect on rendering. If `SplitView` is redesigned later, the prop can
   be removed then. No action required for SP5 itself, but flag this as tech debt.

3. **Confirm `combined` is always the last entry.** The current `build_grading()` in `grading.py`
   appends `combined` after the six method entries per target. The `groupGradingEntries` function
   handles any order, but the `combined` row in the UI is placed last in `METHOD_ORDER`. Verify
   this matches user expectations — i.e., that the combined/final score appears as the last method
   row, not first.

## 9. Open Questions & Decisions

1. **Position of `combined` row in the toggle list.**
   [RESOLVED: `combined` appears first in `METHOD_ORDER`, before all other method rows. It is the
   headline number and should be the first thing the user sees when expanding the score section.]

2. **Top-level heading behavior when there is no `combined` entry.**
   [RESOLVED: Show "Score" as the label with no score values. The section is still collapsible and
   shows whatever method rows are present. This handles edge cases like grading run before combined
   is computed, without crashing.]

3. **`CarePlanView` grading prop: keep or remove in SP5?**
   [RESOLVED: Keep the prop signature in `CarePlanView`; remove only the JSX that renders
   `ReadabilityCard` and `MethodGradingCards`. Prop removal is a separate cleanup task.]

4. **`SplitView` grading display.**
   [DEFERRED] `SplitView` passes `grading={result.grading}` to `CarePlanView`. After SP5, no
   grading is shown in SplitView. Whether to add a grading panel to SplitView is out of scope.

5. **`gradingError` visibility when `OutputGradingCard` is collapsed.**
   [RESOLVED: Show error as a small line below the download bar buttons (beneath Run Grading),
   not inside the collapsed grading section. Error is always visible regardless of collapse state.]

6. **SP2 `ApiError` import path.**
   [RESOLVED: `import type { ApiError } from '../types/errors'` — SP2 delivers this file at
   `frontend/src/types/errors.ts`. Use a TODO comment + plain-text fallback until SP2 merges.]

7. **Breakdown for `combined` — show or hide `dimensions`?**
   [RESOLVED: Skip nested objects in `BreakdownKV` (filter `typeof v !== 'object'`). For combined,
   this shows `grade_estimate`, `label`, and `word_count` only. `dimensions` (a large nested dict)
   is suppressed. This keeps the breakdown concise.]

8. **Score display precision.**
   [RESOLVED: All grades are displayed as integers using `Math.round(entry.grade)`. The raw float
   is not shown to users.]
