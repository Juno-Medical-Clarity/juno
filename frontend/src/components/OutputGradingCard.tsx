import { useState } from 'react';
import { API_URL } from '../api/firebase';
import { authenticatedFetch } from '../api/apiClient';
import type { SimplifyOutput, Grading } from '../types/envelope';

interface OutputGradingCardProps {
  output: SimplifyOutput;
  onGraded: (grading: Grading) => void;
}

export default function OutputGradingCard({ output, onGraded }: OutputGradingCardProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runGrading() {
    setLoading(true);
    setError(null);
    try {
      const savedId = output.metrics.saved_id;
      const body = savedId
        ? { saved_id: savedId }
        : {
            text: output.simplified_care_plan.raw?.text ?? '',
            clarified_text: output.simplified_care_plan.raw?.clarified_text ?? '',
          };

      const res = await authenticatedFetch(`${API_URL}/care_plan/grade`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || `Server error: ${res.status}`);
      }

      const { grading } = await res.json();
      onGraded(grading);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to run grading');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="glass-card configuration-card" style={{ marginTop: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Grading</h2>
        <button
          onClick={runGrading}
          disabled={loading}
          className="download-btn-pdf"
          style={{ padding: '8px 16px', fontSize: '0.85rem' }}
        >
          {loading ? 'Grading…' : 'Run Grading'}
        </button>
      </div>
      {error && (
        <p style={{ marginTop: '8px', color: 'var(--error, #DC2626)', fontSize: '0.8rem' }}>{error}</p>
      )}
    </section>
  );
}
