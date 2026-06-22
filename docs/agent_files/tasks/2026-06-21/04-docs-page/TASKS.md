# Tasks: Docs Page (SP4)

Read `PRD.md` in this folder first. SP4 lands after SP3 (which adds the "Docs" NavBar link and the `/docs/grading/:versionId` grading version detail page that links into SP4's routes).

**Critical routing note (read before Task 7):** The actual route tree lives in `frontend/src/App.tsx`, NOT in `frontend/src/router.tsx`. The file `router.tsx` only exports a `VersionRouteState` type. All `<Route>` additions go in `App.tsx`.

**Critical MD content note (read before Task 2):** PRD §4.9 provides starter content for each `.md` file, but that starter content includes Markdown tables (`| col | col |`). PRD §9 item 2 is RESOLVED: no table renderer — all starter content must be rewritten as bullet lists. The tasks below specify the bullet-list equivalents. Do not copy the table rows verbatim; write them as `- **Field:** description` bullet items instead.

---

### Task 1 — Add `?raw` TypeScript declaration

- Files:
  - `frontend/src/vite-env.d.ts` (create new — confirmed absent)
- Changes:
  - Create the file with the following content exactly:
    ```ts
    /// <reference types="vite/client" />

    declare module '*.md?raw' {
      const content: string;
      export default content;
    }
    ```
  - The `/// <reference types="vite/client" />` line is the standard Vite scaffold line. Including it here means no second file is needed.
- Acceptance criteria:
  - The file exists at `frontend/src/vite-env.d.ts`.
  - Running `npx tsc --noEmit` (or the project's type-check command) produces no `TS2307` error for `'*.md?raw'` imports.

---

### Task 2 — Create the six algorithm Markdown files

- Files (all new):
  - `frontend/src/docs/grading/smog.md`
  - `frontend/src/docs/grading/flesch-kincaid.md`
  - `frontend/src/docs/grading/dale-chall.md`
  - `frontend/src/docs/grading/pemat.md`
  - `frontend/src/docs/grading/sam.md`
  - `frontend/src/docs/grading/cdc-cci.md`
- Changes:
  - Create the directory `frontend/src/docs/grading/` (it does not exist).
  - Write each file using the PRD §4.9 starter content as a base, but replace every Markdown table with a bullet list. The "Score breakdown" sections in PRD §4.9 use `| Field | Description |` tables — convert each table row to `- **\`field_name\`**: description text` bullets under the `## Score breakdown` heading.
  - Example conversion for smog.md's Score breakdown section:
    ```markdown
    ## Score breakdown

    - **`grade`**: Estimated US reading grade level (e.g., 8.0 = 8th grade)
    - **`insufficient_sample`**: `true` if the text has fewer than 30 sentences

    The normalized score (0–100) is derived from the grade level: lower grade = higher score.
    ```
  - Apply the same bullet conversion to all six files. All other content (headings, paragraphs, bold, links) copies from §4.9 verbatim.
  - The `cdc-cci.md` file also has a table in the "How it works" section (four items with conditions). Convert that table to bullets too:
    ```markdown
    - **Main message present**: actionability score >= 50
    - **Behavioral recommendation present**: average of actionability + numeracy clarity >= 50
    - **Numbers used correctly**: numeracy clarity score >= 50
    - **Call to action present**: actionability score >= 60
    ```
- Acceptance criteria:
  - All six `.md` files exist under `frontend/src/docs/grading/`.
  - None of the six files contain any `|` pipe characters (no Markdown tables).
  - Each file has an `# AlgorithmName` h1, at least one `## ` h2 section, at least one `- ` bullet item, and at least one `[text](url)` external link.

---

### Task 3 — Create `renderMarkdown` utility

- Files:
  - `frontend/src/utils/renderMarkdown.ts` (create new)
- Changes:
  - Create the file. Since the `.md` files contain no tables (bullet lists only, per Task 2), implement the converter per PRD §4.3 with the `(<li>.*<\/li>)` list-wrapping regex corrected to handle multiple consecutive `<li>` items. A working implementation:
    ```ts
    export function renderMarkdown(md: string): string {
      const lines = md
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        .replace(/^- (.+)$/gm, '<li>$1</li>');

      // Wrap contiguous <li> runs in <ul>
      const withLists = lines.replace(/(<li>[\s\S]*?<\/li>)(\n<li>[\s\S]*?<\/li>)*/g, match => `<ul>${match}</ul>`);

      // Wrap non-tag blocks in <p>
      return withLists
        .split(/\n{2,}/)
        .map(block => block.trim())
        .filter(Boolean)
        .map(block => (block.startsWith('<') ? block : `<p>${block}</p>`))
        .join('\n');
    }
    ```
  - Verify manually that passing the full text of `smog.md` (Task 2) through this function produces readable HTML with no raw Markdown syntax visible.
- Acceptance criteria:
  - `renderMarkdown('# Hello')` returns a string containing `<h1>Hello</h1>`.
  - `renderMarkdown('**bold**')` returns a string containing `<strong>bold</strong>`.
  - `renderMarkdown('[text](http://example.com)')` returns a string containing `<a href="http://example.com" target="_blank" rel="noopener noreferrer">text</a>`.
  - `renderMarkdown('- item one\n- item two')` returns a string containing `<ul>` and two `<li>` elements.
  - `renderMarkdown('')` returns `''` without throwing.

---

### Task 4 — Create `docs-config.ts` with DOCS_SECTIONS

- Files:
  - `frontend/src/docs-config.ts` (create new)
- Changes:
  - Create the file at the `src/` root (not inside `src/docs/`). Copy the exact code from PRD §4.4:
    ```ts
    export interface DocEntry {
      slug: string;
      name: string;
      content: string;
    }

    export interface DocsSection {
      id: string;
      title: string;
      basePath: string;
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
          { slug: 'smog',           name: 'SMOG',                         content: smogMd },
          { slug: 'flesch-kincaid', name: 'Flesch-Kincaid',               content: fkMd },
          { slug: 'dale-chall',     name: 'Dale-Chall',                   content: dcMd },
          { slug: 'pemat',          name: 'PEMAT',                        content: pematMd },
          { slug: 'sam',            name: 'SAM',                          content: samMd },
          { slug: 'cdc-cci',        name: 'CDC Clear Communication Index', content: cdcMd },
        ],
      },
      // To add a new section: append one object here. No structural changes needed.
    ];
    ```
  - Note: the `interfaces` must be declared before the `import` statements or TypeScript will complain. Move the `interface` declarations to the top of the file, then the `import` statements, then `DOCS_SECTIONS`.
- Acceptance criteria:
  - `import { DOCS_SECTIONS } from './docs-config'` compiles without TS errors.
  - `DOCS_SECTIONS[0].entries` has exactly 6 items.
  - Each entry's `content` is a non-empty string at runtime (confirms `?raw` import bundled the file).
  - The six slugs in order are: `smog`, `flesch-kincaid`, `dale-chall`, `pemat`, `sam`, `cdc-cci`.

---

### Task 5 — Create `DocsPage.tsx`

- Files:
  - `frontend/src/pages/docs/DocsPage.tsx` (create new; create the `docs/` subdirectory under `pages/`)
- Changes:
  - Implement the component exactly per PRD §4.5 and §4.6. The flat search list is built at module level (outside the component). The component uses `useState` for the query string. Key structure:
    ```tsx
    import { useState } from 'react';
    import { Link } from 'react-router-dom';
    import { DOCS_SECTIONS } from '../../docs-config';

    const ALL_DOCS = DOCS_SECTIONS.flatMap(section =>
      section.entries.map(e => ({
        slug: e.slug,
        name: e.name,
        content: e.content,
        basePath: section.basePath,
      }))
    );

    export default function DocsPage() {
      const [query, setQuery] = useState('');
      const q = query.trim().toLowerCase();
      const filtered = q
        ? ALL_DOCS.filter(d =>
            d.name.toLowerCase().includes(q) || d.content.toLowerCase().includes(q)
          )
        : null;

      return (
        <main className="app-shell">
          <section className="hero-section">
            <h1>Documentation</h1>
            <input
              type="search"
              placeholder="Search docs..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{ width: '100%', padding: '8px', marginBottom: '1rem' }}
            />
            {filtered !== null ? (
              <div>
                {filtered.length === 0 ? (
                  <p>No results for "{query}".</p>
                ) : (
                  filtered.map(d => (
                    <div key={d.slug}>
                      <Link to={`${d.basePath}/${d.slug}`}>{d.name}</Link>
                    </div>
                  ))
                )}
              </div>
            ) : (
              DOCS_SECTIONS.map(section => (
                <div key={section.id} className="glass-card" style={{ padding: '24px', marginBottom: '16px' }}>
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
  - Use inline `style` for the search input and glass-card padding rather than adding a CSS class (per PRD §9 item 3: no new CSS file; minimal inline style acceptable).
- Acceptance criteria:
  - Visiting `/docs` in the dev server shows a "Documentation" heading, a search input, and a "Grading" section with all six algorithm names as links.
  - Typing "smog" in the search box filters to show only the SMOG link.
  - Typing a word from `smog.md` body (e.g., "polysyllabic") shows SMOG in results.
  - Typing "zzz" shows the "No results" message.
  - Clearing the input restores the full section view.

---

### Task 6 — Create `AlgorithmDocPage.tsx`

- Files:
  - `frontend/src/pages/docs/AlgorithmDocPage.tsx` (create new, in the same `pages/docs/` directory as Task 5)
- Changes:
  - Implement exactly per PRD §4.7:
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
              className="glass-card"
              style={{ padding: '24px', marginTop: '16px' }}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }}
            />
          </section>
        </main>
      );
    }
    ```
  - The `top-nav-link` class already exists in `App.css` and gives the back link a consistent pill style.
- Acceptance criteria:
  - Visiting `/docs/grading/smog` renders HTML content with "SMOG" as a heading, no raw Markdown syntax (`#`, `**`, `- `) visible in the page.
  - Visiting `/docs/grading/unknown-slug` shows a "Not found" heading, the unknown slug in the message, and a "Back to Docs" link pointing to `/docs`. No JS error in the console.
  - All six slugs render their respective algorithm content without crashing.

---

### Task 7 — Register routes in `App.tsx`

- Files:
  - `frontend/src/App.tsx`
- Changes:
  - Add two imports at the top:
    ```ts
    import DocsPage from './pages/docs/DocsPage';
    import AlgorithmDocPage from './pages/docs/AlgorithmDocPage';
    ```
  - Inside the `<Routes>` block, add two routes as siblings to the existing routes, inside the `<Route element={<AuthLayout />}>` wrapper (so DocsPage and AlgorithmDocPage get the NavBar with the "Docs" link that SP3 adds):
    ```tsx
    <Route path="/docs" element={<DocsPage />} />
    <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
    ```
  - Place them before the `path="*"` catch-all redirect.
  - The resulting `<Route element={<AuthLayout />}>` block should look like:
    ```tsx
    <Route element={<AuthLayout />}>
      <Route path="/versions" element={<VersionsPage />} />
      <Route path="/docs" element={<DocsPage />} />
      <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>
    ```
  - Do NOT touch `router.tsx` — it only exports a type and has no route registration.
  - Do NOT touch `NavBar.tsx` — SP3 owns the "Docs" link.
- Acceptance criteria:
  - `npx tsc --noEmit` passes with no new type errors.
  - Navigating to `/docs` in the dev server renders DocsPage (not the 404 redirect).
  - Navigating to `/docs/grading/flesch-kincaid` renders AlgorithmDocPage for Flesch-Kincaid.
  - The existing `/versions` route still works correctly.

---

### Task 8 — Write unit tests for `renderMarkdown`

- Files:
  - `frontend/src/tests/utils/renderMarkdown.test.ts` (create new)
- Changes:
  - Create the test file following the same import style as `grading.test.ts` (which imports from `../../utils/grading`):
    ```ts
    import { describe, it, expect } from 'vitest';
    import { renderMarkdown } from '../../utils/renderMarkdown';
    import smogContent from '../../docs/grading/smog.md?raw';

    describe('renderMarkdown', () => {
      it('converts # heading to <h1>', () => {
        expect(renderMarkdown('# Hello')).toContain('<h1>Hello</h1>');
      });

      it('converts ## heading to <h2>', () => {
        expect(renderMarkdown('## Section')).toContain('<h2>Section</h2>');
      });

      it('converts **bold** to <strong>', () => {
        expect(renderMarkdown('**bold**')).toContain('<strong>bold</strong>');
      });

      it('converts [text](url) to <a> with target and rel', () => {
        const result = renderMarkdown('[click](http://example.com)');
        expect(result).toContain('<a href="http://example.com"');
        expect(result).toContain('target="_blank"');
        expect(result).toContain('rel="noopener noreferrer"');
        expect(result).toContain('>click</a>');
      });

      it('converts - item to <li> wrapped in <ul>', () => {
        const result = renderMarkdown('- item one\n- item two');
        expect(result).toContain('<ul>');
        expect(result).toContain('<li>item one</li>');
        expect(result).toContain('<li>item two</li>');
      });

      it('does not crash on empty string', () => {
        expect(() => renderMarkdown('')).not.toThrow();
      });

      it('smoke test: renders smog.md without crashing and without raw markdown', () => {
        const result = renderMarkdown(smogContent);
        expect(result).not.toContain('# SMOG');   // h1 should be converted
        expect(result).toContain('<h1>');
        expect(result).not.toMatch(/^\*\*/m);       // no raw bold at line start
      });
    });
    ```
- Acceptance criteria:
  - `npx vitest run src/tests/utils/renderMarkdown.test.ts` passes with all tests green.

---

### Task 9 — Write unit tests for `docs-config`

- Files:
  - `frontend/src/tests/utils/docs-config.test.ts` (create new)
- Changes:
  - Create the test file:
    ```ts
    import { describe, it, expect } from 'vitest';
    import { DOCS_SECTIONS } from '../../docs-config';

    describe('DOCS_SECTIONS', () => {
      it('has at least one section', () => {
        expect(DOCS_SECTIONS.length).toBeGreaterThan(0);
      });

      it('each section has at least one entry', () => {
        DOCS_SECTIONS.forEach(section => {
          expect(section.entries.length).toBeGreaterThan(0);
        });
      });

      it('grading section has all six expected slugs', () => {
        const grading = DOCS_SECTIONS.find(s => s.id === 'grading');
        expect(grading).toBeDefined();
        const slugs = grading!.entries.map(e => e.slug);
        expect(slugs).toEqual(['smog', 'flesch-kincaid', 'dale-chall', 'pemat', 'sam', 'cdc-cci']);
      });

      it('all grading entries have non-empty slug, name, and content', () => {
        const grading = DOCS_SECTIONS.find(s => s.id === 'grading')!;
        grading.entries.forEach(e => {
          expect(e.slug).toBeTruthy();
          expect(e.name).toBeTruthy();
          expect(e.content).toBeTruthy();
          expect(e.content.length).toBeGreaterThan(10);
        });
      });

      it('all slugs within grading section are unique', () => {
        const grading = DOCS_SECTIONS.find(s => s.id === 'grading')!;
        const slugs = grading.entries.map(e => e.slug);
        const unique = new Set(slugs);
        expect(unique.size).toBe(slugs.length);
      });
    });
    ```
- Acceptance criteria:
  - `npx vitest run src/tests/utils/docs-config.test.ts` passes with all tests green.

---

### Task 10 — Write component tests for `DocsPage` and `AlgorithmDocPage`

- Files:
  - `frontend/src/tests/pages/DocsPage.test.tsx` (create new)
  - `frontend/src/tests/pages/AlgorithmDocPage.test.tsx` (create new)
- Changes:
  - Follow the same import and test structure as `frontend/src/tests/components/CarePlanView.test.tsx` or similar existing component tests. Use React Testing Library (`render`, `screen`, `fireEvent`) with the `MemoryRouter` from `react-router-dom` to provide routing context.

  - `DocsPage.test.tsx`:
    ```tsx
    import { render, screen, fireEvent } from '@testing-library/react';
    import { MemoryRouter } from 'react-router-dom';
    import DocsPage from '../../pages/docs/DocsPage';

    function renderDocsPage() {
      return render(
        <MemoryRouter>
          <DocsPage />
        </MemoryRouter>
      );
    }

    describe('DocsPage', () => {
      it('renders without crashing', () => {
        renderDocsPage();
      });

      it('shows Grading section heading', () => {
        renderDocsPage();
        expect(screen.getByText('Grading')).toBeInTheDocument();
      });

      it('shows all six algorithm names as links in default view', () => {
        renderDocsPage();
        expect(screen.getByText('SMOG')).toBeInTheDocument();
        expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
        expect(screen.getByText('Dale-Chall')).toBeInTheDocument();
        expect(screen.getByText('PEMAT')).toBeInTheDocument();
        expect(screen.getByText('SAM')).toBeInTheDocument();
        expect(screen.getByText('CDC Clear Communication Index')).toBeInTheDocument();
      });

      it('filters to a single result when query matches one algorithm name', () => {
        renderDocsPage();
        const input = screen.getByPlaceholderText('Search docs...');
        fireEvent.change(input, { target: { value: 'smog' } });
        expect(screen.getByText('SMOG')).toBeInTheDocument();
        expect(screen.queryByText('Flesch-Kincaid')).not.toBeInTheDocument();
      });

      it('shows no-results message when query has no matches', () => {
        renderDocsPage();
        const input = screen.getByPlaceholderText('Search docs...');
        fireEvent.change(input, { target: { value: 'zzznomatch999' } });
        expect(screen.getByText(/No results/i)).toBeInTheDocument();
      });

      it('restores section view when query is cleared', () => {
        renderDocsPage();
        const input = screen.getByPlaceholderText('Search docs...');
        fireEvent.change(input, { target: { value: 'smog' } });
        fireEvent.change(input, { target: { value: '' } });
        expect(screen.getByText('Grading')).toBeInTheDocument();
        expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
      });
    });
    ```

  - `AlgorithmDocPage.test.tsx`:
    ```tsx
    import { render, screen } from '@testing-library/react';
    import { MemoryRouter, Route, Routes } from 'react-router-dom';
    import AlgorithmDocPage from '../../pages/docs/AlgorithmDocPage';

    function renderAtSlug(slug: string) {
      return render(
        <MemoryRouter initialEntries={[`/docs/grading/${slug}`]}>
          <Routes>
            <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
          </Routes>
        </MemoryRouter>
      );
    }

    describe('AlgorithmDocPage', () => {
      it('renders SMOG page without crashing', () => {
        renderAtSlug('smog');
      });

      it('renders SMOG page with SMOG content in the DOM', () => {
        renderAtSlug('smog');
        // The rendered HTML should contain SMOG content (h1 rendered via dangerouslySetInnerHTML)
        expect(document.body.innerHTML).toContain('SMOG');
      });

      it('shows not-found state for unknown slug', () => {
        renderAtSlug('unknown-slug');
        expect(screen.getByText('Not found')).toBeInTheDocument();
        expect(screen.getByText(/unknown-slug/)).toBeInTheDocument();
      });

      it('shows a back link to /docs on the not-found page', () => {
        renderAtSlug('unknown-slug');
        const link = screen.getByText('Back to Docs');
        expect(link.closest('a')).toHaveAttribute('href', '/docs');
      });

      it('shows a back link to /docs on a valid algorithm page', () => {
        renderAtSlug('smog');
        const link = screen.getByText(/Docs/);
        expect(link.closest('a')).toHaveAttribute('href', '/docs');
      });
    });
    ```
- Acceptance criteria:
  - `npx vitest run src/tests/pages/DocsPage.test.tsx` passes with all tests green.
  - `npx vitest run src/tests/pages/AlgorithmDocPage.test.tsx` passes with all tests green.

---

### Task 11 — Full integration smoke test (manual)

- Files: none — manual verification only
- Changes:
  - Start the dev server (`npm run dev` from `frontend/`).
  - Visit `/docs`: confirm all six algorithm names appear under a "Grading" heading.
  - Click each of the six links: confirm each page renders Markdown content as HTML (no raw `#`, `**`, or `- ` visible).
  - Visit `/docs/grading/unknown-slug` directly: confirm "Not found" state with no JS console error.
  - On the `/docs` page, type "sentence" in the search box: Flesch-Kincaid and SMOG should both appear (both `.md` files mention sentences).
  - Clear the search: section view returns with all six links.
  - Verify the "← Docs" back link on any algorithm page returns to `/docs`.
  - Confirm the existing `/versions` route still works.
- Acceptance criteria (observable):
  - No "Cannot read properties of undefined" or similar JS errors in the browser console on any of the above pages.
  - No raw Markdown characters visible in the rendered page body.
  - All six algorithm URLs resolve correctly.

---

## Summary of what requires you (not a dev agent)

1. **Review and edit the Markdown content** (PRD §8 item 2). The six `.md` files written in Task 2 are starter content. Review each — especially the "automated approximation" notes in `pemat.md`, `sam.md`, and `cdc-cci.md` — and add any nuance or corrections you want users to see. This is owner-authored content; a dev agent should not change it beyond the initial write.

2. **Coordinate slug contract with SP3** (PRD §8 item 3). Before SP3 is implemented, share the slug table from PRD §6 with the SP3 implementer. The slugs `flesch-kincaid`, `dale-chall`, and `cdc-cci` are hyphenated and easy to mis-type. SP3's `<Link to="/docs/grading/...">` calls must use these exact strings.

3. **Interim deploy state** (PRD §9 item 7, RESOLVED). If SP3 ships before SP4, clicking "Docs" in the NavBar will show a React Router fallback (redirects to `/`). This is expected. Deploy SP3 and SP4 together or accept the interim gap.

4. **Cross-SP integration check** (PRD §7 manual verification). After both SP3 and SP4 are deployed, click through from the SP3 grading version detail page to each SP4 algorithm doc page and confirm the links navigate correctly end-to-end.
