import './CarePlanPage.css';
import { useState } from 'react';
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
import { shareOutput, updateJobComment } from '../../api/savedOutputs';
import { ApiError } from '../../types/errors';
import { API_URL } from '../../api/firebase';
import { useAuth } from '../../auth/AuthContext';
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
  const { user, getIdToken } = useAuth();
  const { jobDoc, loading, error } = useJobSnapshot(id ?? null);
  const [gradingOverride, setGradingOverride] = useState<Grading | null>(null);
  const [gradingLoading, setGradingLoading] = useState(false);
  const [gradingError, setGradingError] = useState<string | null>(null);
  const [showSplitView, setShowSplitView] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [showCommentArea, setShowCommentArea] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [commentSaving, setCommentSaving] = useState(false);
  const [commentSaved, setCommentSaved] = useState(false);

  const isPublicView = !user;

  const baseResult: CarePlanInternal | null =
    jobDoc?.status === 'completed' && jobDoc.output_data
      ? normalizeCarePlanOutput(jobDoc.output_data)
      : null;
  const result: CarePlanInternal | null =
    baseResult && gradingOverride ? { ...baseResult, grading: gradingOverride } : baseResult;

  // Sync commentText with jobDoc.comment when opening the textarea
  function handleToggleComment() {
    if (!showCommentArea) {
      setCommentText(jobDoc?.comment ?? '');
      setCommentSaved(false);
    }
    setShowCommentArea(v => !v);
  }

  async function handleSaveComment() {
    if (!id) return;
    setCommentSaving(true);
    try {
      await updateJobComment(id, commentText);
      setCommentSaved(true);
      setTimeout(() => {
        setCommentSaved(false);
        setShowCommentArea(false);
      }, 1500);
    } catch {
      // Keep area open on error so user can retry
    } finally {
      setCommentSaving(false);
    }
  }

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
    if (!printWindow) {
      alert('Pop-up blocked. Please allow pop-ups to download the report.');
      return;
    }
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
      setGradingOverride(grading);
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

  async function handleToggleShare() {
    if (!jobDoc || !user || !id) return;
    setShareLoading(true);
    try {
      await getIdToken();
      await shareOutput(id, !jobDoc.shared);
    } catch (e) {
      console.error('Failed to toggle share:', e);
    } finally {
      setShareLoading(false);
    }
  }

  if (loading) {
    return (
      <>
        <NavBar isPublicView={isPublicView} />
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
        <NavBar isPublicView={isPublicView} />
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
        <NavBar isPublicView={isPublicView} />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Care plan not found.
        </div>
      </>
    );
  }

  if (isPublicView && jobDoc.shared === false) {
    return (
      <>
        <NavBar isPublicView={isPublicView} />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
          This care plan is private.
        </div>
      </>
    );
  }

  if (jobDoc.status === 'completed' && result) {
    const hasInput = (!isPublicView && outputHasInputPdf(result)) || outputHasInputText(result);
    const sessionId = result.metrics.session_id ?? id ?? null;
    const traceId = jobDoc.trace_id;
    const sessionLogUrl = sessionId
      ? `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D"${sessionId}";project=juno-medical-clarity`
      : null;
    const traceUrl = traceId
      ? `https://console.cloud.google.com/traces/list?project=juno-medical-clarity&tid=${traceId}`
      : null;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <NavBar isPublicView={isPublicView} />
        <div style={{ display: 'flex', flex: 1 }}>
          {!isPublicView && (
            <Sidebar
              activeId={id ?? null}
              onSelect={(selectedId) => navigate(`/carePlan/${selectedId}`)}
              refreshTrigger={0}
            />
          )}
          <div style={{ flex: 1, marginLeft: isPublicView ? 0 : 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: 'calc(48px + 40px)' }}>
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

                  {(sessionId || traceId) && (
                    <div style={{ marginTop: '24px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.75rem', lineHeight: '1.8' }}>
                      {sessionId && (
                        <div>
                          Session ID:{' '}
                          {sessionLogUrl
                            ? <a href={sessionLogUrl} target="_blank" rel="noopener noreferrer">{sessionId}</a>
                            : sessionId}
                        </div>
                      )}
                      <div>
                        Trace ID:{' '}
                        {traceId && traceUrl
                          ? <a href={traceUrl} target="_blank" rel="noopener noreferrer">{traceId}</a>
                          : '—'}
                      </div>
                    </div>
                  )}

                  {!isPublicView && (
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
                  )}

                  <OutputGradingCard grading={result.grading} error={gradingError} />

                  <div className="download-bar">
                    <div className="download-actions">
                      <button className="download-btn-json" onClick={handleDownloadJson}>
                        ↓ Download JSON
                      </button>
                      <button className="download-btn-pdf" onClick={handleDownloadPdf}>
                        ↓ Download Report
                      </button>
                      {!isPublicView && (
                        <button
                          className="download-btn-grading"
                          onClick={handleRunGrading}
                          disabled={gradingLoading}
                        >
                          {gradingLoading ? 'Grading…' : '◎ Run Grading'}
                        </button>
                      )}
                      {!isPublicView && (
                        <button
                          className="download-btn-note"
                          onClick={handleToggleComment}
                        >
                          {showCommentArea
                            ? 'Cancel Note'
                            : (jobDoc.comment ? '✏ Edit Note' : '✏ Add Note')}
                        </button>
                      )}
                      {user && (
                        <button
                          className="download-btn-share"
                          onClick={handleToggleShare}
                          disabled={shareLoading}
                        >
                          {shareLoading ? 'Saving…' : jobDoc.shared ? '🔒 Stop sharing' : '🔗 Share'}
                        </button>
                      )}
                    </div>
                    {gradingError && (
                      <p style={{ marginTop: '6px', color: 'var(--error, #DC2626)', fontSize: '0.78rem', textAlign: 'center' }}>
                        {gradingError}
                      </p>
                    )}
                    {showCommentArea && (
                      <div className="comment-area">
                        <textarea
                          value={commentText}
                          onChange={e => setCommentText(e.target.value)}
                          placeholder="Add a note about this care plan…"
                          maxLength={2000}
                        />
                        <div className="comment-actions">
                          <button
                            className="comment-cancel-btn"
                            onClick={() => setShowCommentArea(false)}
                          >
                            Cancel
                          </button>
                          <button
                            className="comment-save-btn"
                            onClick={handleSaveComment}
                            disabled={commentSaving}
                          >
                            {commentSaved ? 'Saved!' : commentSaving ? 'Saving…' : 'Save'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </div>
          </div>
        </div>
        {showSplitView && (
          <SplitView
            savedId={!isPublicView && result.input.mode === 'file' ? id ?? null : null}
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
        <NavBar isPublicView={isPublicView} />
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
          {message}
        </div>
      </>
    );
  }

  const steps = stepsFromStage(jobDoc.stage);
  return (
    <>
      <NavBar isPublicView={isPublicView} />
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
