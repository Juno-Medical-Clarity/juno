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
