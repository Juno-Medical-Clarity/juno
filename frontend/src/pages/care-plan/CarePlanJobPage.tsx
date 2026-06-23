import './CarePlanPage.css';
import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useJobSnapshot } from '../../hooks/useJobSnapshot';
import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
import CarePlanView from '../../components/CarePlanView';
import NavBar from '../../components/NavBar';
import Sidebar from '../../components/Sidebar';
import OutputGradingCard from '../../components/OutputGradingCard';
import SplitView from '../../components/SplitView';
import { buildPdfHtml } from '../../utils/buildPdfHtml';
import { authenticatedFetchJson } from '../../api/apiClient';
import { ApiError } from '../../types/errors';
import { API_URL } from '../../api/firebase';
import type { CarePlanInternal, Grading } from '../../types/envelope';
import { INITIAL_STEPS, outputHasInputPdf, outputHasInputText } from './CarePlanPage';
import type { PipelineStep } from '../../types/carePlan';

function stepsFromStage(stage: number | null): PipelineStep[] {
  return INITIAL_STEPS.map(step => ({
    ...step,
    status: stage == null
      ? 'waiting'
      : step.id < stage
        ? 'done'
        : step.id === stage
          ? 'active'
          : 'waiting',
  }));
}

function stepIcon(status: string): string {
  if (status === 'done') return '✓';
  if (status === 'active') return '◉';
  return '○';
}

export default function CarePlanJobPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { jobDoc, loading, error } = useJobSnapshot(id ?? null);
  const [result, setResult] = useState<CarePlanInternal | null>(null);
  const [gradingLoading, setGradingLoading] = useState(false);
  const [gradingError, setGradingError] = useState<string | null>(null);
  const [showSplitView, setShowSplitView] = useState(false);

  useEffect(() => {
    if (jobDoc?.status === 'completed' && jobDoc.output_data) {
      setResult(normalizeCarePlanOutput(jobDoc.output_data));
    }
  }, [jobDoc]);

  function handleDownloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'care-plan.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleDownloadPdf() {
    if (!result) return;
    const html = buildPdfHtml(result.care_plan);
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;
    printWindow.document.write(html);
    printWindow.document.close();
    setTimeout(() => printWindow.print(), 500);
  }

  async function handleRunGrading() {
    if (!result) return;
    setGradingLoading(true);
    setGradingError(null);
    try {
      const savedId = result.metrics.saved_id ?? id;
      const body = savedId
        ? { saved_id: savedId }
        : {
            text: result.care_plan.raw?.text ?? '',
            clarified_text: result.care_plan.raw?.clarified_text ?? '',
          };
      const { grading } = await authenticatedFetchJson<{ grading: Grading }>(
        `${API_URL}/care_plan/grade`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        },
      );
      setResult(prev => prev ? { ...prev, grading } : prev);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGradingError(err.message);
      } else {
        setGradingError(err instanceof Error ? err.message : 'Failed to run grading');
      }
    } finally {
      setGradingLoading(false);
    }
  }

  if (loading) {
    return (
      <>
        <NavBar />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Loading…
        </div>
      </>
    );
  }

  if (error) {
    const isPermission = error.message?.toLowerCase().includes('permission') ||
      error.message?.toLowerCase().includes('missing or insufficient');
    return (
      <>
        <NavBar />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
          {isPermission
            ? 'You do not have permission to view this care plan.'
            : `Error loading care plan: ${error.message}`}
        </div>
      </>
    );
  }

  if (!jobDoc) {
    return (
      <>
        <NavBar />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Care plan not found.
        </div>
      </>
    );
  }

  if (jobDoc.status === 'completed' && result) {
    const hasInput = outputHasInputPdf(result) || outputHasInputText(result);
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <NavBar />
        <div style={{ display: 'flex', flex: 1 }}>
          <Sidebar
            activeId={id ?? null}
            onSelect={(selectedId) => navigate(`/carePlan/${selectedId}`)}
            refreshTrigger={0}
          />
          <div style={{ flex: 1, marginLeft: 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: 'calc(48px + 40px)' }}>
            <div className="page-wrapper">
              <div className="container">
                <section className="result-section">
                  <div className="result-header">
                    <div>
                      <h2 className="result-title">Your Care Plan</h2>
                      {result.metrics.created_at && (
                        <p className="result-timestamp">
                          Simplified on {new Date(result.metrics.created_at).toLocaleDateString('en-US', {
                            month: 'long', day: 'numeric', year: 'numeric',
                          })}
                        </p>
                      )}
                    </div>
                    {hasInput && (
                      <button
                        onClick={() => setShowSplitView(true)}
                        style={{
                          background: 'none', border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-pill)', padding: '6px 14px',
                          fontSize: '0.8rem', cursor: 'pointer',
                          color: 'var(--text-secondary)', fontFamily: 'Inter, sans-serif',
                        }}
                      >
                        Show Original
                      </button>
                    )}
                  </div>

                  <CarePlanView result={result.care_plan} grading={result.grading} />

                  {result.metrics.session_id && (
                    <div style={{ marginTop: '24px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                      Request ID: {result.metrics.session_id}
                    </div>
                  )}

                  <div style={{ marginTop: '32px', textAlign: 'center' }}>
                    <button
                      onClick={() => navigate('/')}
                      style={{
                        background: 'none',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-pill)',
                        color: 'var(--text-secondary)',
                        fontSize: '0.85rem',
                        padding: '8px 20px',
                        cursor: 'pointer',
                        fontFamily: 'Inter, sans-serif',
                      }}
                    >
                      ← Create another care plan
                    </button>
                  </div>

                  <OutputGradingCard grading={result.grading} error={gradingError} />

                  <div className="download-bar">
                    <div className="download-actions">
                      <button className="download-btn-json" onClick={handleDownloadJson}>
                        ↓ Download JSON
                      </button>
                      <button className="download-btn-pdf" onClick={handleDownloadPdf}>
                        ↓ Download Report
                      </button>
                      <button
                        className="download-btn-grading"
                        onClick={handleRunGrading}
                        disabled={gradingLoading}
                      >
                        {gradingLoading ? 'Grading…' : '◎ Run Grading'}
                      </button>
                    </div>
                    {gradingError && (
                      <p style={{ marginTop: '6px', color: 'var(--error, #DC2626)', fontSize: '0.78rem', textAlign: 'center' }}>
                        {gradingError}
                      </p>
                    )}
                  </div>
                </section>
              </div>
            </div>
          </div>
        </div>
        {showSplitView && (
          <SplitView
            savedId={result.input.mode === 'file' ? id ?? null : null}
            originalText={
              (result.input.mode === 'text' || result.input.mode === 'batch_dataset')
                ? result.input.text ?? null
                : null
            }
            simplifiedContent={<CarePlanView result={result.care_plan} grading={result.grading} />}
            onClose={() => setShowSplitView(false)}
          />
        )}
      </div>
    );
  }

  if (jobDoc.status === 'error') {
    const message = jobDoc.error_data?.message ?? 'An error occurred processing your care plan.';
    return (
      <>
        <NavBar />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
          {message}
        </div>
      </>
    );
  }

  const steps = stepsFromStage(jobDoc.stage);
  return (
    <>
      <NavBar />
      <div style={{ maxWidth: '600px', margin: '0 auto', padding: '80px 32px' }}>
        <div className="glass-card" style={{ padding: '32px' }}>
          <p className="section-title">Creating your care plan…</p>
          <div className="step-list">
            {steps.map(step => (
              <div className="step-item" key={step.id}>
                <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
                <div className="step-content">
                  <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>
                    {step.label}
                  </p>
                  <p className="step-desc">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
