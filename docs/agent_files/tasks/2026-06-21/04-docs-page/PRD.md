# PRD: Docs Page (SP4)

Sub-project 4 of 5. Depends on SP3 (which adds the "Docs" NavBar link and the grading version detail page that links into SP4's routes). SP4 adds the new `/docs` section: an index page with sections and local search, plus one Markdown-rendered page per grading algorithm.

## 1. Problem

The grading algorithms used by Juno (SMOG, Flesch-Kincaid, Dale-Chall, PEMAT, SAM, CDC CCI) are opaque to end-users. SP3's grading version detail page will display per-algorithm scores and link to documentation, but those doc pages do not exist yet. There is no `/docs` route at all. Users who want to understand what a score means or where the algorithm comes from have nowhere to go.

Additionally, the owner needs a place to add more documentation sections over time (e.g., pipeline architecture, API reference). The docs section must be structured so adding a new section is a one-line config change, not structural surgery.

## 2. Goals

1. Add a `/docs` route with a `DocsPage` index: lists all sections, lists all algorithm pages under Grading, and includes a local search bar that filters by name + content.
2. Add a `/docs/grading/:slug` route with an `AlgorithmDocPage` that renders a single algorithm's Markdown file.
3. Provide one Markdown file per algorithm in `frontend/src/docs/grading/`: smog.md, flesch-kincaid.md, dale-chall.md, pemat.md, sam.md, cdc-cci.md. Each file contains a real description, what breakdown fields the algorithm produces, how the score is computed, and one external link.
4. Search is local, synchronous, no backend: on each keystroke filter the flat doc list by whether the query string appears in name or content (case-insensitive `includes()`). Load all `.md` content at build time via Vite's `?raw` import.
5. URL slugs — `smog`, `flesch-kincaid`, `dale-chall`, `pemat`, `sam`, `cdc-cci` — must match exactly what SP3 links to from the grading version detail page.
6. `/docs/grading/unknown-slug` must show a graceful not-found state, not crash.
7. The owner can add a new docs section (e.g., "Pipeline") by adding one entry to a config array. No structural changes required.

## 3. Non-Goals

- No backend involvement of any kind.
- No fancy styling. Functional layout only; no theming, no syntax highlighting, no animations.
- No fuzzy search, no Algolia, no search index file generated at build time. Plain `includes()`.
- No navigation sidebar within a doc page. No breadcrumbs. No previous/next links.
- No versioning of doc content.
- SP4 does NOT touch NavBar — SP3 adds the "Docs" link. SP4 only adds the routes and pages.
- No pagination. All algorithms are listed on the index with no pagination.

## 4. Architecture Decisions

### 4.1 Markdown rendering — no new dependency needed

The project has no `react-markdown`, no `marked`, no `remark` in `package.json`. Two options:

**Option A (recommended): `?raw` import + `dangerouslySetInnerHTML` with a minimal inline parser**
Vite supports `import content from './foo.md?raw'` natively with zero plugins — the `?raw` suffix tells Vite to import the file as a plain string. This works today without any vite.config.ts change. The content is then converted to HTML with a minimal inline transform (see §4.3) and rendered with `dangerouslySetInnerHTML`. Content is authored by the owner and lives in the repo, so XSS risk is owned by the repo — the same risk as any inline HTML in the codebase.

**Option B: install `react-markdown`**
~50KB gzipped. Cleaner rendering. But adds a dep and a lockfile change for what the PRD describes as "functional, not fancy."

**Decision: Option A.** No new dependency. The Markdown content is simple (headings, paragraphs, links, bullet lists, bold) and an inline converter handles it. If the owner later wants proper rendering they can swap in `react-markdown` at any time with no structural change — the `.md` files and the `?raw` import pattern are fully compatible.

### 4.2 File layout

```
frontend/src/
  docs/
    grading/
      smog.md
      flesch-kincaid.md
      dale-chall.md
      pemat.md
      sam.md
      cdc-cci.md
  pages/
    docs/
      DocsPage.tsx          (index: sections list + search)
      AlgorithmDocPage.tsx  (single algorithm Markdown renderer)
  docs-config.ts            (DOCS_SECTIONS config array — see §4.4)
```

No CSS files added (per non-goal: functional only; reuse existing `app-shell`, `glass-card`, etc. classes).

### 4.3 Minimal Markdown-to-HTML converter

A small pure function in `frontend/src/utils/renderMarkdown.ts`:

```ts
export function renderMarkdown(md: string): string {
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')     // wrap contiguous list items
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<[hul])(.+)$/gm, '$1')
    // Wrap bare text blocks in <p>
    .split('\n\n').map(block =>
      block.startsWith('<') ? block : `<p>${block}</p>`
    ).join('\n');
}
```

Note: This is a starter implementation. It handles the content patterns actually used in the six `.md` files (headings h1-h3, bold, links, bullet lists, paragraphs). The implementer should verify it renders all six files correctly and adjust regex as needed. The function lives in `utils/` so it can be tested independently.

### 4.4 Docs config array — extensible sections

`frontend/src/docs-config.ts`:

```ts
export interface DocEntry {
  slug: string;         // URL slug, e.g. "smog"
  name: string;         // Display name, e.g. "SMOG"
  content: string;      // Full .md content, loaded via ?raw import
}

export interface DocsSection {
  id: string;           // e.g. "grading"
  title: string;        // e.g. "Grading"
  basePath: string;     // e.g. "/docs/grading"
  entries: DocEntry[];
}

import smogMd from './docs/grading/smog.md?raw';
import fkMd from './docs/grading/flesch-kincaid.md?raw';
import dcMd from './docs/grading/dale-chall.md?raw';
import pematMd from './docs/grading/pemat.md?raw';
import samMd from './docs/grading/sam.md?raw';
import cdcMd from './docs/grading/cdc-cci.md?raw';

export const DOCS_SECTIONS: DocsSection[] = [
  {
    id: 'grading',
    title: 'Grading',
    basePath: '/docs/grading',
    entries: [
      { slug: 'smog',           name: 'SMOG',                    content: smogMd },
      { slug: 'flesch-kincaid', name: 'Flesch-Kincaid',          content: fkMd },
      { slug: 'dale-chall',     name: 'Dale-Chall',              content: dcMd },
      { slug: 'pemat',          name: 'PEMAT',                   content: pematMd },
      { slug: 'sam',            name: 'SAM',                     content: samMd },
      { slug: 'cdc-cci',        name: 'CDC Clear Communication Index', content: cdcMd },
    ],
  },
  // To add a new section: add one entry here. No structural changes needed.
];
```

All `.md` content is bundled at build time. The search index is derived from `DOCS_SECTIONS` at runtime on app load — no separate build step.

**TypeScript `?raw` import type declaration**: Vite supports `?raw` natively but TypeScript needs a type hint to avoid `TS2307`. Add a declaration in `frontend/src/vite-env.d.ts` (or create `frontend/src/env.d.ts`):

```ts
declare module '*.md?raw' {
  const content: string;
  export default content;
}
```

### 4.5 Search implementation

Search lives entirely in `DocsPage.tsx`. No separate hook needed.

```ts
// Flat list built once from DOCS_SECTIONS at module load time
const ALL_DOCS: Array<{ slug: string; name: string; content: string; basePath: string }> =
  DOCS_SECTIONS.flatMap(section =>
    section.entries.map(e => ({
      slug: e.slug,
      name: e.name,
      content: e.content,
      basePath: section.basePath,
    }))
  );

// In DocsPage component:
const [query, setQuery] = useState('');
const q = query.trim().toLowerCase();
const filtered = q
  ? ALL_DOCS.filter(d => d.name.toLowerCase().includes(q) || d.content.toLowerCase().includes(q))
  : null; // null = no active search; show full section tree instead
```

When `filtered` is null (no query), render the full section tree (grouped by section). When `filtered` is a non-null array, render a flat list of matching results with their section label. An empty `filtered` array shows a "No results" message.

### 4.6 DocsPage layout

```tsx
export default function DocsPage() {
  const [query, setQuery] = useState('');
  // ... search logic from §4.5

  return (
    <main className="app-shell">
      <section className="hero-section">
        <h1>Documentation</h1>
        <input
          type="search"
          placeholder="Search docs..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="docs-search-input"
        />

        {filtered !== null ? (
          // Search results view
          <div className="docs-search-results">
            {filtered.length === 0
              ? <p>No results for "{query}".</p>
              : filtered.map(d => (
                  <div key={d.slug}>
                    <Link to={`${d.basePath}/${d.slug}`}>{d.name}</Link>
                  </div>
                ))
            }
          </div>
        ) : (
          // Section tree view
          DOCS_SECTIONS.map(section => (
            <div key={section.id} className="glass-card">
              <h2>{section.title}</h2>
              <ul>
                {section.entries.map(e => (
                  <li key={e.slug}>
                    <Link to={`${section.basePath}/${e.slug}`}>{e.name}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
    </main>
  );
}
```

### 4.7 AlgorithmDocPage layout

```tsx
import { useParams, Link } from 'react-router-dom';
import { DOCS_SECTIONS } from '../../docs-config';
import { renderMarkdown } from '../../utils/renderMarkdown';

export default function AlgorithmDocPage() {
  const { slug } = useParams<{ slug: string }>();
  const gradingSection = DOCS_SECTIONS.find(s => s.id === 'grading');
  const entry = gradingSection?.entries.find(e => e.slug === slug);

  if (!entry) {
    return (
      <main className="app-shell">
        <section className="hero-section">
          <h1>Not found</h1>
          <p>No documentation page for "{slug}".</p>
          <Link to="/docs">Back to Docs</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className="hero-section">
        <Link to="/docs" className="top-nav-link">&larr; Docs</Link>
        <div
          className="glass-card docs-content"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }}
        />
      </section>
    </main>
  );
}
```

The not-found path uses `slug` directly from `useParams` — this is safe to display because it is just shown as a string in text, not injected as HTML.

### 4.8 Router changes

`frontend/src/router.tsx` currently exports an object with route definitions (verified: two routes, `/` and `/versions`). SP3 will have added `/models` and `/models/grading/:versionId` and a `/docs` nav link. SP4 adds:

```ts
{ path: '/docs', element: <DocsPage /> },
{ path: '/docs/grading/:slug', element: <AlgorithmDocPage /> },
```

These are added as peers to the existing routes. No nested route layout needed (DocsPage and AlgorithmDocPage each render their own `app-shell`).

### 4.9 Markdown content — per-algorithm files

The content below is the starter content to write into each `.md` file. The implementer writes these files verbatim (or with minor wording fixes). The owner edits them later.

---

**`smog.md`**

```markdown
# SMOG

**SMOG** (Simple Measure of Gobbledygook) was developed by G. Harry McLaughlin in 1969 specifically for health education materials. It is widely used by the CDC and health literacy researchers as a standard measure for patient-facing documents.

## How it works

SMOG counts the number of polysyllabic words (words with 3 or more syllables) in a sample of 30 sentences and applies a formula to estimate the reading grade level. The assumption is that polysyllabic words are the primary driver of reading difficulty.

SMOG requires at least 30 sentences to produce a valid result. Texts with fewer than 30 sentences return a score of 0 and are flagged as insufficient sample.

## Score breakdown

| Field | Description |
|---|---|
| `grade` | Estimated US reading grade level (e.g., 8.0 = 8th grade) |
| `insufficient_sample` | `true` if the text has fewer than 30 sentences |

The normalized score (0–100) is derived from the grade level: lower grade = higher score.

## External reference

[McLaughlin, G. H. (1969). SMOG Grading — a New Readability Formula. *Journal of Reading*, 12(8), 639–646.](https://doi.org/10.1598/jor.1969.12.8.1)
```

---

**`flesch-kincaid.md`**

```markdown
# Flesch-Kincaid

The **Flesch-Kincaid** formulas were developed by Rudolf Flesch (1948) and later adapted by J. Peter Kincaid for the U.S. Navy (1975). They are among the most widely used readability measures in English and are built into Microsoft Word.

## How it works

Two related formulas are computed:

- **Reading Ease** (Flesch): a 0–100 score where higher is easier. Scores above 60 are considered plain language; scores below 30 are very difficult.
- **Grade Level** (Flesch-Kincaid): the estimated US school grade level required to understand the text.

Both formulas weight average sentence length and average syllable count per word.

## Score breakdown

| Field | Description |
|---|---|
| `reading_ease` | Flesch Reading Ease score (0–100; higher = easier) |
| `grade_level` | Flesch-Kincaid Grade Level |

The normalized score (0–100) used for comparison is the Reading Ease score clamped to [0, 100].

## External reference

[Kincaid, J. P., et al. (1975). Derivation of New Readability Formulas for Navy Enlisted Personnel. *Naval Technical Training Command Research Branch*.](https://apps.dtic.mil/sti/citations/ADA006655)
```

---

**`dale-chall.md`**

```markdown
# Dale-Chall

**Dale-Chall** was developed by Edgar Dale and Jeanne Chall in 1948 and revised in 1995. It is unique among readability formulas in that it uses a reference list of familiar words rather than purely structural features like sentence length.

## How it works

Dale-Chall computes the percentage of "difficult" words — words not on the Dale-Chall list of approximately 3,000 words familiar to most 4th-grade students — alongside average sentence length. A higher percentage of difficult words yields a higher raw score and a higher estimated grade level.

## Score breakdown

| Field | Description |
|---|---|
| `raw_score` | The raw Dale-Chall score (typically 4.0–9.0+) |
| `grade_range` | Estimated grade range (e.g., "7th–8th grade", "College level") |

The normalized score (0–100) maps the estimated grade level to the 0–100 scale inversely (lower grade = higher score).

## External reference

[Chall, J. S., & Dale, E. (1995). *Readability Revisited: The New Dale-Chall Readability Formula*. Brookline Books.](https://www.brooklinebooks.com/readabilityrevisited.html)
```

---

**`pemat.md`**

```markdown
# PEMAT

**PEMAT** (Patient Education Materials Assessment Tool) was developed by AHRQ (Agency for Healthcare Research and Quality) in 2013 to evaluate the understandability and actionability of patient education materials.

## How it works

Juno computes an automated approximation of PEMAT using five internal dimension scores:

- **Understandability** is a weighted combination of: jargon density (25%), sentence complexity (25%), passive voice (20%), numeracy clarity (15%), and structural clarity (15%).
- **Actionability** maps directly to the internal actionability dimension score.

The combined PEMAT score is the average of the two sub-scores.

## Score breakdown

| Field | Description |
|---|---|
| `understandability` | Weighted understandability sub-score (0–100) |
| `actionability` | Actionability sub-score (0–100) |

Note: This is an automated approximation. PEMAT was designed for human raters reviewing actual printed materials. The full PEMAT includes items that cannot be assessed from text alone (e.g., visual aids, layout).

## External reference

[AHRQ Patient Education Materials Assessment Tool (PEMAT)](https://www.ahrq.gov/health-literacy/patient-education/pemat.html)
```

---

**`sam.md`**

```markdown
# SAM

**SAM** (Suitability Assessment of Materials) was developed by Leonard and Cecilia Doak (1996) as a structured checklist for evaluating the appropriateness of health education materials for low-literacy audiences.

## How it works

Juno computes an automated approximation of three SAM domains using internal dimension scores:

- **Content** (0–8 points): weighted combination of grade level and jargon density.
- **Literacy demand** (0–14 points): weighted combination of grade level, sentence complexity, and passive voice.
- **Layout/typography** (0–6 points): based on structural clarity.

Only the three automatable domains are scored, out of SAM's full set (28 out of a possible 28 points in these domains). The score is the percentage of points earned.

## Score breakdown

| Field | Description |
|---|---|
| `content` | Content domain points (0–8) |
| `literacy_demand` | Literacy demand domain points (0–14) |
| `layout_typography` | Layout/typography domain points (0–6) |

Note: Full SAM includes visual, cultural, and stimulation/motivation domains that require human review.

## External reference

[Doak, C. C., Doak, L. G., & Root, J. H. (1996). *Teaching Patients with Low Literacy Skills* (2nd ed.). J.B. Lippincott.](https://www.ahrq.gov/sites/default/files/publications/files/LowLiteracyGuide_0.pdf)
```

---

**`cdc-cci.md`**

```markdown
# CDC Clear Communication Index

The **CDC Clear Communication Index** (CDC CCI) is a research-based tool developed by the Centers for Disease Control and Prevention to help public health professionals create clear, actionable health communication materials.

## How it works

Juno computes an automated approximation of four CDC CCI items using internal dimension scores:

| Item | Condition |
|---|---|
| Main message present | Actionability score >= 50 |
| Behavioral recommendation present | Average of actionability + numeracy clarity >= 50 |
| Numbers used correctly | Numeracy clarity score >= 50 |
| Call to action present | Actionability score >= 60 |

The score is the percentage of the four items met (0, 25, 50, 75, or 100).

## Score breakdown

| Field | Description |
|---|---|
| `main_message` | 1 if main message criterion met, else 0 |
| `behavioral_recommendations` | 1 if behavioral recommendation criterion met, else 0 |
| `numbers` | 1 if numeracy criterion met, else 0 |
| `call_to_action` | 1 if call-to-action criterion met, else 0 |

Note: Full CDC CCI has 20 scored items. Juno approximates the 4 most automatable items from text alone.

## External reference

[CDC Clear Communication Index](https://www.cdc.gov/healthliteracy/develop/clear-communication-index.html)
```

## 5. API Change Summary

N/A. SP4 is entirely frontend, no backend changes.

## 6. Frontend Change Summary

### Files to create

| File | Purpose |
|---|---|
| `frontend/src/docs/grading/smog.md` | SMOG algorithm doc content |
| `frontend/src/docs/grading/flesch-kincaid.md` | Flesch-Kincaid doc content |
| `frontend/src/docs/grading/dale-chall.md` | Dale-Chall doc content |
| `frontend/src/docs/grading/pemat.md` | PEMAT doc content |
| `frontend/src/docs/grading/sam.md` | SAM doc content |
| `frontend/src/docs/grading/cdc-cci.md` | CDC CCI doc content |
| `frontend/src/docs-config.ts` | DOCS_SECTIONS config + all `?raw` imports |
| `frontend/src/pages/docs/DocsPage.tsx` | Index page with sections + search |
| `frontend/src/pages/docs/AlgorithmDocPage.tsx` | Single algorithm Markdown renderer |
| `frontend/src/utils/renderMarkdown.ts` | Minimal MD→HTML converter |

### Files to modify

| File | Change |
|---|---|
| `frontend/src/router.tsx` | Add two routes: `/docs` and `/docs/grading/:slug` |
| `frontend/src/vite-env.d.ts` (or create `env.d.ts`) | Add `declare module '*.md?raw'` type declaration |

### Files NOT touched by SP4

- `frontend/src/components/NavBar.tsx` — SP3 owns the "Docs" nav link.
- All backend files.
- All existing pages.

### URL slug contract with SP3

The following slugs are the binding contract between SP4 (which defines the pages) and SP3 (which links to them from the grading version detail page):

| Algorithm | Slug | Full URL |
|---|---|---|
| SMOG | `smog` | `/docs/grading/smog` |
| Flesch-Kincaid | `flesch-kincaid` | `/docs/grading/flesch-kincaid` |
| Dale-Chall | `dale-chall` | `/docs/grading/dale-chall` |
| PEMAT | `pemat` | `/docs/grading/pemat` |
| SAM | `sam` | `/docs/grading/sam` |
| CDC Clear Communication Index | `cdc-cci` | `/docs/grading/cdc-cci` |

These are the exact strings SP3 must use in its `<Link to="/docs/grading/smog">` etc. calls. The slug also matches the `.md` filename (minus the `.md` extension).

## 7. Testing

Tests live in `frontend/src/tests/` alongside existing tests.

### Unit tests

**`renderMarkdown.test.ts`**
- Converts `# Heading` to `<h1>Heading</h1>`.
- Converts `**bold**` to `<strong>bold</strong>`.
- Converts `[text](url)` to `<a href="url" ...>text</a>` with `target="_blank"` and `rel="noopener noreferrer"`.
- Converts `- item` to `<li>item</li>` (wrapped in `<ul>`).
- Does not crash on empty string.
- Does not crash on a multi-section real Markdown file (smoke test with `smogMd` content).

**`docs-config.test.ts`**
- `DOCS_SECTIONS` has at least one section.
- Each section has at least one entry.
- All entries in the grading section have non-empty `slug`, `name`, `content`.
- Each slug is unique within its section.
- The six expected slugs are all present: `['smog', 'flesch-kincaid', 'dale-chall', 'pemat', 'sam', 'cdc-cci']`.
- Each entry's `content` is a non-empty string (confirms `?raw` import worked).

### Component tests (React Testing Library)

**`DocsPage.test.tsx`**
- Renders without crashing.
- Shows all section titles (at minimum "Grading").
- Shows all algorithm names as links when no search query.
- After typing a query that matches one algorithm name, only that algorithm is shown.
- After typing a query that matches content (a word from `smog.md`), matching results appear.
- After typing a query with no matches, shows "No results" message.
- Clearing the query restores the full section view.

**`AlgorithmDocPage.test.tsx`**
- Renders SMOG page at slug `smog` and contains "SMOG" heading.
- Renders unknown slug and shows "Not found" text and a back link to `/docs`.
- Back link (`/docs`) is present on a valid algorithm page.

### Manual verification

- Visit `/docs` in dev server: all six algorithm links appear under "Grading".
- Click each algorithm link: page renders Markdown content with no `[object Object]` or raw Markdown text visible.
- Visit `/docs/grading/unknown-slug`: not-found state shown, no JS error in console.
- Type "sentence" in search box on `/docs`: Flesch-Kincaid and at least SMOG should match (both mention sentences). Verify results appear and are links.
- Clear the search: section view returns.
- Confirm SP3's grading version detail page links navigate correctly to SP4 pages (cross-SP integration check, done after both SP3 and SP4 land).

## 8. Manual Intervention Required From You

1. **Verify the `?raw` import type declaration location.** The project may already have a `frontend/src/vite-env.d.ts`. If it does, add the `declare module '*.md?raw'` line there. If not, create `frontend/src/env.d.ts`. Do not create a second declaration file if one already exists.

2. **Review the Markdown content.** The content in §4.9 is starter content written from the algorithm descriptions and scoring code. Review each file for accuracy and add any clarifications you want users to see. In particular, the PEMAT, SAM, and CDC CCI notes about "automated approximation" may want more nuance.

3. **Coordinate slug contract with SP3 author.** Before SP3 is implemented, share the slug table in §6 with the SP3 implementer so their links target the correct URLs. This is especially important for `flesch-kincaid` and `dale-chall` (hyphenated) and `cdc-cci`.

## 9. Open Questions & Decisions

1. **`vite-env.d.ts` already exists?**
   [OPEN] The file `frontend/src/vite-env.d.ts` may already exist (generated by Vite's scaffold). The implementer should read it before adding the `?raw` declaration to avoid duplicating the file.

2. **`renderMarkdown` — table support.**
   [RESOLVED: Rewrite starter `.md` content as bullet lists. No table renderer needed. Consistent
   with the "no fancy styling" constraint. If the owner later needs tables, react-markdown can be
   swapped in without structural changes.]

3. **CSS class for `.docs-search-input`.**
   [RESOLVED: use existing classes or write minimal inline style.] The docs pages use `app-shell`, `hero-section`, `glass-card` from existing CSS. The search input can use an existing input class if one exists, or a one-line inline style (`width: 100%; padding: 8px; margin-bottom: 1rem;`) on the element. Do not create a new CSS file.

4. **Should `docs-config.ts` live in `src/` root or `src/docs/`?**
   [RESOLVED: `src/docs-config.ts` at the src root.] This matches the convention of `config.ts` living at the root. The `src/docs/` directory is for content files only, not config.

5. **`AlgorithmDocPage` — hardcoded to grading section?**
   [RESOLVED: yes, hardcoded to grading for now.] The route is `/docs/grading/:slug`, so `AlgorithmDocPage` looks up the entry in the `grading` section by slug. If the owner adds a new section with its own doc pages (e.g., `/docs/pipeline/:slug`), they will create a new page component for it — or the page can be generalized then. Do not over-engineer a generic lookup now.

6. **Search: should it search across all sections or just grading?**
   [RESOLVED: search across all sections.] The flat list `ALL_DOCS` is built from `DOCS_SECTIONS.flatMap(...)`, so it automatically includes any future sections without code changes. Correct behavior now and forward-compatible.

7. **SP3 landing before SP4.**
   [RESOLVED: acceptable.] SP3 adds the "Docs" NavBar link before SP4 ships its routes. Clicking "Docs" before SP4 lands will show a React Router 404/fallback. This is acceptable given the development sequence. The owner should deploy SP3 and SP4 together or be aware of the interim state.
