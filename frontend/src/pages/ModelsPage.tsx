import { Link } from 'react-router-dom';
import { VERSIONS, GRADING_VERSIONS } from '../config';

export default function ModelsPage() {
  return (
    <main className="app-shell">
      <section className="hero-section">
        <h1>Pipeline versions</h1>
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
                    <strong className="version-table-link">{version.label}</strong>
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

        <section style={{ marginTop: '48px' }}>
          <h2>Grading Versions</h2>
          <div className="versions-table-wrap glass-card" style={{ marginTop: '16px' }}>
            <table className="versions-table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Description</th>
                  <th>Methods</th>
                </tr>
              </thead>
              <tbody>
                {GRADING_VERSIONS.map(v => (
                  <tr key={v.id}>
                    <td>
                      <Link to={`/models/grading/${v.id}`} className="version-table-link">
                        {v.label}
                      </Link>
                      {v.isDefault && <span className="version-default-badge">Default</span>}
                    </td>
                    <td>{v.description}</td>
                    <td>{v.methods.join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}
