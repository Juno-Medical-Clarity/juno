import { Link } from 'react-router-dom';
import { VERSIONS } from '../config';

export default function VersionsPage() {
  return (
    <main className="app-shell">
      <section className="hero-section">
        <p className="eyebrow">Juno Medical Document Simplifier</p>
        <h1>Choose a version</h1>
        <div className="versions-table-wrap glass-card">
          <table className="versions-table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Description</th>
                <th>Steps</th>
              </tr>
            </thead>
            <tbody>
              {VERSIONS.map(version => (
                <tr key={version.id}>
                  <td>
                    <Link className="version-table-link" to={version.path}>
                      {version.label}
                    </Link>
                    {version.isDefault && (
                      <span className="version-default-badge">Default</span>
                    )}
                  </td>
                  <td>{version.description}</td>
                  <td>
                    <ol className="version-steps">
                      {version.steps.map(step => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
