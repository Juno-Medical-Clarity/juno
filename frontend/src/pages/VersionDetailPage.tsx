import { Link, useParams } from 'react-router-dom';
import { VERSIONS } from '../config';
import SignOutButton from '../auth/SignOutButton';

export default function VersionDetailPage() {
  const { id } = useParams<{ id: string }>();

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

            <div className="version-detail-actions">
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
