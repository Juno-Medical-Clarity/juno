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
