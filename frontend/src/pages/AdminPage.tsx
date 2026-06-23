import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import NavBar from '../components/NavBar';
import { authenticatedFetchJson } from '../api/apiClient';
import { API_URL } from '../api/firebase';

interface StatusCounts {
  not_started: number;
  processing: number;
  completed: number;
  error: number;
}

interface ActiveJob {
  id: string;
  name: string | null;
  stage: number | null;
  started_at: string | null;
  uid: string | null;
}

interface RecentError {
  id: string;
  name: string | null;
  created_at: string | null;
  error_data: { code?: string; message?: string } | null;
}

interface AdminStats {
  status_counts: StatusCounts;
  total: number;
  active_jobs: ActiveJob[];
  recent_errors: RecentError[];
}

const QUICK_LINKS = [
  {
    label: 'Cloud Tasks Queue',
    url: 'https://console.cloud.google.com/cloudtasks/queue/us-central1/care-plan-jobs?project=juno-medical-clarity',
  },
  {
    label: 'Cloud Trace',
    url: 'https://console.cloud.google.com/traces/list?project=juno-medical-clarity',
  },
  {
    label: 'Cloud Logging',
    url: 'https://console.cloud.google.com/logs/query?project=juno-medical-clarity',
  },
  {
    label: 'Firestore',
    url: 'https://console.cloud.google.com/firestore/databases/-default-/data/panel/care_plan_outputs?project=juno-medical-clarity',
  },
  {
    label: 'Cloud Run (API)',
    url: 'https://console.cloud.google.com/run/detail/us-central1/juno-api/metrics?project=juno-medical-clarity',
  },
  {
    label: 'Cloud Run (Worker)',
    url: 'https://console.cloud.google.com/run/detail/us-central1/juno-worker/metrics?project=juno-medical-clarity',
  },
];

const tdStyle: CSSProperties = {
  padding: '6px 10px',
  borderBottom: '1px solid #ddd',
  fontSize: '0.85rem',
  verticalAlign: 'top',
};

const thStyle: CSSProperties = {
  ...tdStyle,
  fontWeight: 600,
  textAlign: 'left',
  background: '#f5f5f5',
};

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authenticatedFetchJson<AdminStats>(`${API_URL}/admin/stats`)
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        setLoadError(err instanceof Error ? err.message : 'Failed to load admin stats');
        setLoading(false);
      });
  }, []);

  return (
    <div style={{ minHeight: '100vh' }}>
      <NavBar />
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: '80px 24px 40px' }}>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '24px' }}>Admin Dashboard</h1>

        {/* Quick links */}
        <section style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '1rem', marginBottom: '10px' }}>Quick Links</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {QUICK_LINKS.map(link => (
              <li key={link.label} style={{ marginBottom: '4px', fontSize: '0.875rem' }}>
                <span style={{ display: 'inline-block', width: '180px', color: '#555' }}>
                  {link.label}:
                </span>
                <a href={link.url} target="_blank" rel="noopener noreferrer">
                  {link.url}
                </a>
              </li>
            ))}
          </ul>
        </section>

        {loading && <p>Loading stats…</p>}
        {loadError && (
          <p style={{ color: 'var(--error, #DC2626)' }}>Error: {loadError}</p>
        )}

        {stats && (
          <>
            {/* Status counts */}
            <section style={{ marginBottom: '32px' }}>
              <h2 style={{ fontSize: '1rem', marginBottom: '10px' }}>Job Status Overview</h2>
              <table style={{ borderCollapse: 'collapse', minWidth: '320px' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Status</th>
                    <th style={thStyle}>Count</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={tdStyle}>Queue (not started)</td>
                    <td style={tdStyle}>{stats.status_counts.not_started}</td>
                  </tr>
                  <tr>
                    <td style={tdStyle}>Processing (active)</td>
                    <td style={tdStyle}>{stats.status_counts.processing}</td>
                  </tr>
                  <tr>
                    <td style={tdStyle}>Completed</td>
                    <td style={tdStyle}>{stats.status_counts.completed}</td>
                  </tr>
                  <tr>
                    <td style={tdStyle}>Error</td>
                    <td style={tdStyle}>{stats.status_counts.error}</td>
                  </tr>
                  <tr>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>Total</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{stats.total}</td>
                  </tr>
                </tbody>
              </table>
            </section>

            {/* Active jobs */}
            <section style={{ marginBottom: '32px' }}>
              <h2 style={{ fontSize: '1rem', marginBottom: '10px' }}>
                Active Jobs ({stats.active_jobs.length})
              </h2>
              {stats.active_jobs.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: '#666' }}>No active jobs.</p>
              ) : (
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Job ID</th>
                      <th style={thStyle}>Name</th>
                      <th style={thStyle}>Stage</th>
                      <th style={thStyle}>Started At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.active_jobs.map(job => (
                      <tr key={job.id}>
                        <td style={tdStyle}>
                          <code style={{ fontSize: '0.78rem' }}>{job.id}</code>
                        </td>
                        <td style={tdStyle}>{job.name ?? '—'}</td>
                        <td style={tdStyle}>{job.stage ?? '—'}</td>
                        <td style={tdStyle}>{job.started_at ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            {/* Recent errors */}
            <section style={{ marginBottom: '32px' }}>
              <h2 style={{ fontSize: '1rem', marginBottom: '10px' }}>
                Recent Errors (last {stats.recent_errors.length})
              </h2>
              {stats.recent_errors.length === 0 ? (
                <p style={{ fontSize: '0.85rem', color: '#666' }}>No recent errors.</p>
              ) : (
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={thStyle}>Job ID</th>
                      <th style={thStyle}>Name</th>
                      <th style={thStyle}>Error Code</th>
                      <th style={thStyle}>Error Message</th>
                      <th style={thStyle}>Created At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent_errors.map(err => (
                      <tr key={err.id}>
                        <td style={tdStyle}>
                          <code style={{ fontSize: '0.78rem' }}>{err.id}</code>
                        </td>
                        <td style={tdStyle}>{err.name ?? '—'}</td>
                        <td style={tdStyle}>{err.error_data?.code ?? '—'}</td>
                        <td style={tdStyle}>{err.error_data?.message ?? '—'}</td>
                        <td style={tdStyle}>{err.created_at ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
