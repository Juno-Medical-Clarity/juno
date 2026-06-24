import { Link, useParams } from 'react-router-dom';
import { GRADING_VERSION_DETAILS } from '../config';

export default function GradingVersionDetailPage() {
  const { versionId } = useParams<{ versionId: string }>();
  const version = GRADING_VERSION_DETAILS.find(v => v.id === versionId);

  if (!version) {
    return (
      <main className="app-shell">
        <section className="hero-section">
          <Link to="/models" className="version-detail-back">← Back to Models</Link>
          <p className="version-detail-not-found">Grading version not found.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <section className="hero-section">
        <Link to="/models" className="version-detail-back">← Back to Models</Link>
        <div className="version-detail-meta">
          <h1>{version.label}</h1>
          {version.isDefault && <span className="version-default-badge">Default</span>}
        </div>
        <p className="version-detail-description">{version.description}</p>

        <h2 style={{ marginTop: '40px', marginBottom: '16px', fontSize: '1.25rem', fontWeight: 700 }}>
          Scoring Methods
        </h2>
        {version.methodDetails.map(method => (
          <div
            key={method.id}
            className="glass-card"
            style={{ marginBottom: '16px', padding: '20px 24px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <h3 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                {method.label}
              </h3>
              <Link to={`/docs/grading/${method.docsSlug}`} className="top-nav-link">
                Docs →
              </Link>
            </div>
            <p style={{ marginTop: '8px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              {method.description}
            </p>
            <p style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>Sub-scores:</strong>{' '}
              {method.breakdownKeys.join(', ')}
            </p>
          </div>
        ))}

        <h2 style={{ marginTop: '40px', marginBottom: '16px', fontSize: '1.25rem', fontWeight: 700 }}>
          Combined Score
        </h2>
        <div className="glass-card" style={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <h3 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)', margin: 0 }}>
              Patient Accessibility Score
            </h3>
            {version.combinedDocsSlug && (
              <Link to={`/docs/grading/${version.combinedDocsSlug}`} className="top-nav-link">
                Docs →
              </Link>
            )}
          </div>
          <p style={{ marginTop: '8px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {version.combinedDescription}
          </p>
        </div>
      </section>
    </main>
  );
}
