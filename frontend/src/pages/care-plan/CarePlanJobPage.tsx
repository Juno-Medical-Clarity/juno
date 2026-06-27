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
import { shareOutput, updateCarePlanNote, updateCarePlanGrading } from '../../api/savedOutputs';
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

  async function handleSaveComment() {
    if (!id) return;
    setCommentSaving(true);
    try {
      await updateCarePlanNote(id, commentText);
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
    const html = buildPdfHtml(result.care_plan, result.grading ?? undefined);
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
      // Fire-and-forget: persist grading to Firestore
      if (id) {
        updateCarePlanGrading(id, grading).catch(() => {/* ignore save errors */});
      }
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
        {!isPublicView && <NavBar />}
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
        {!isPublicView && <NavBar />}
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
        {!isPublicView && <NavBar />}
        <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          Care plan not found.
        </div>
      </>
    );
  }

  if (isPublicView && jobDoc.shared === false) {
    return (
      <div style={{ padding: '80px 32px', textAlign: 'center', color: 'var(--error, #DC2626)' }}>
        This care plan is private.
      </div>
    );
  }

  if (jobDoc.status === 'completed' && result) {
    const hasInput = (!isPublicView && outputHasInputPdf(result)) || outputHasInputText(result);
    const sessionId = jobDoc.session_id ?? result.metrics.session_id ?? null;
    const traceId = jobDoc.trace_id;
    const sessionLogUrl = sessionId
      ? `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D"${sessionId}";project=juno-medical-clarity`
      : null;
    const traceUrl = traceId
      ? `https://console.cloud.google.com/traces/list?project=juno-medical-clarity&tid=${traceId}`
      : null;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        {!isPublicView && <NavBar />}
        <div style={{ display: 'flex', flex: 1 }}>
          {!isPublicView && (
            <Sidebar
              activeId={id ?? null}
              onSelect={(selectedId) => navigate(`/carePlan/${selectedId}`)}
              refreshTrigger={0}
            />
          )}
          <div style={{ flex: 1, marginLeft: isPublicView ? 0 : 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: isPublicView ? '40px' : 'calc(48px + 40px)' }}>
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

                  {gradingLoading && (
                    <p style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      Recalculating…
                    </p>
                  )}
                  <div style={gradingLoading ? { opacity: 0.5, pointerEvents: 'none' } : undefined}>
                    <OutputGradingCard grading={result.grading} error={gradingError} />
                  </div>

                  {!isPublicView && (
                    <div className="note-card">
                      {result.care_plan.note
                        ? <p className="note-card-text">{result.care_plan.note}</p>
                        : <p className="note-card-placeholder">--Notes--</p>
                      }
                      <button
                        className="download-btn-note note-card-btn"
                        onClick={() => {
                          if (!showCommentArea) {
                            setCommentText(result.care_plan.note ?? '');
                            setCommentSaved(false);
                          }
                          setShowCommentArea(v => !v);
                        }}
                      >
                        {result.care_plan.note ? '✏ Edit Note' : '+ Add Note'}
                      </button>
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
                  )}

                  <div className="download-bar">
                    <div className="download-actions">
                      <button className="download-btn-json" onClick={handleDownloadJson}>
                        ↓ JSON
                      </button>
                      <button className="download-btn-pdf" onClick={handleDownloadPdf}>
                        ↓ Report
                      </button>
                      {!isPublicView && (
                        <button
                          className="download-btn-grading"
                          onClick={handleRunGrading}
                          disabled={gradingLoading}
                        >
                          {gradingLoading ? 'Grading…' : '◎ Grade'}
                        </button>
                      )}
                      {user && (
                        <button
                          className="download-btn-share"
                          onClick={handleToggleShare}
                          disabled={shareLoading}
                          aria-label={shareLoading ? 'Saving…' : jobDoc.shared ? 'Stop sharing' : 'Share'}
                          title={shareLoading ? 'Saving…' : jobDoc.shared ? 'Stop sharing' : 'Share'}
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
    const errData = jobDoc.error_data;
    // Prefer user_hint (new rich format) over message for user-facing text
    const userMessage = errData?.user_hint ?? errData?.message ?? 'An error occurred processing your care plan.';
    const errorCode = errData?.code ?? null;
    const devMessage = errData?.message ?? null;
    // retryable is a boolean; check !== undefined so false renders correctly
    const retryable = errData?.retryable;
    // Use "details" field from FirestoreJobError / legacy ErrorDetail formats
    const technicalDetail = errData?.details ?? null;
    const sessionId = jobDoc.session_id ?? null;
    const traceId = jobDoc.trace_id ?? null;
    const sessionLogUrl = sessionId
      ? `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D"${sessionId}";project=juno-medical-clarity`
      : null;
    const traceUrl = traceId
      ? `https://console.cloud.google.com/traces/list?project=juno-medical-clarity&tid=${traceId}`
      : null;
    return (
      <>
        {!isPublicView && <NavBar />}
        <div style={{ padding: '80px 32px', maxWidth: '640px', margin: '0 auto' }}>
          {/* Primary user-facing error message */}
          <div style={{ textAlign: 'center', color: 'var(--error, #DC2626)', fontWeight: 500, marginBottom: '16px' }}>
            {userMessage}
          </div>

          {/* Error code badge */}
          {errorCode && (
            <div style={{ textAlign: 'center', marginBottom: '8px' }}>
              <code style={{
                background: 'var(--surface-2, #f3f4f6)',
                padding: '2px 10px',
                borderRadius: '4px',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                fontFamily: 'monospace',
              }}>
                {errorCode}
              </code>
            </div>
          )}

          {/* Retryable indicator */}
          {retryable !== undefined && (
            <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
              Retryable: {retryable ? 'Yes' : 'No'}
            </div>
          )}

          {/* Developer-facing message (muted, italic) */}
          {devMessage && (
            <div style={{
              textAlign: 'center',
              fontSize: '0.73rem',
              color: 'var(--text-muted)',
              fontStyle: 'italic',
              marginBottom: '16px',
              lineHeight: '1.5',
            }}>
              {devMessage}
            </div>
          )}

          {/* Technical detail — collapsible monospace box */}
          {technicalDetail && (
            <details style={{ marginTop: '12px', textAlign: 'left' }}>
              <summary style={{
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                userSelect: 'none',
              }}>
                Technical detail
              </summary>
              <pre style={{
                marginTop: '8px',
                padding: '12px',
                background: 'var(--surface-2, #f3f4f6)',
                borderRadius: '6px',
                fontSize: '0.7rem',
                overflowX: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: '200px',
                overflowY: 'auto',
                color: 'var(--text-secondary)',
                fontFamily: 'monospace',
              }}>
                {technicalDetail}
              </pre>
            </details>
          )}

          {/* Session ID and Trace ID links */}
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
        </div>
      </>
    );
  }

  const steps = stepsFromStage(jobDoc.stage);
  return (
    <>
      {!isPublicView && <NavBar />}
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
