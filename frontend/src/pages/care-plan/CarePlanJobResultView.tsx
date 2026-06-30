import { useNavigate } from 'react-router-dom';
import type { User } from 'firebase/auth';
import NavBar from '../../components/NavBar';
import Sidebar from '../../components/Sidebar';
import CarePlanView from '../../components/CarePlanView';
import OutputGradingCard from '../../components/OutputGradingCard';
import SplitView from '../../components/SplitView';
import { outputHasInputPdf, outputHasInputText } from './CarePlanPage';
import type { CarePlanInternal } from '../../types/envelope';
import type { JobDoc } from '../../hooks/useJobSnapshot';

interface CarePlanJobResultViewProps {
  result: CarePlanInternal;
  jobDoc: JobDoc;
  id: string | undefined;
  isPublicView: boolean;
  user: User | null;
  gradingLoading: boolean;
  gradingError: string | null;
  shareLoading: boolean;
  showSplitView: boolean;
  setShowSplitView: (value: boolean) => void;
  showCommentArea: boolean;
  setShowCommentArea: (value: boolean | ((prev: boolean) => boolean)) => void;
  commentText: string;
  setCommentText: (value: string) => void;
  commentSaving: boolean;
  commentSaved: boolean;
  setCommentSaved: (value: boolean) => void;
  handleSaveComment: () => void;
  handleDownloadJson: () => void;
  handleDownloadPdf: () => void;
  handleRunGrading: () => void;
  handleToggleShare: () => void;
}

export default function CarePlanJobResultView({
  result,
  jobDoc,
  id,
  isPublicView,
  user,
  gradingLoading,
  gradingError,
  shareLoading,
  showSplitView,
  setShowSplitView,
  showCommentArea,
  setShowCommentArea,
  commentText,
  setCommentText,
  commentSaving,
  commentSaved,
  setCommentSaved,
  handleSaveComment,
  handleDownloadJson,
  handleDownloadPdf,
  handleRunGrading,
  handleToggleShare,
}: CarePlanJobResultViewProps) {
  const navigate = useNavigate();

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
