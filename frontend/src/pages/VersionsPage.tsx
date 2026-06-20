import { VERSIONS } from '../config';

export default function VersionsPage() {
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
      </section>
    </main>
  );
}
