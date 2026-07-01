import './CarePlanPage.css';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useJobSnapshot } from '../../hooks/useJobSnapshot';
import NavBar from '../../components/NavBar';
import { buildPdfHtml } from '../../utils/buildPdfHtml';
import { authenticatedFetchJson } from '../../api/apiClient';
import { shareOutput, updateCarePlanNote, updateCarePlanGrading } from '../../api/savedOutputs';
import { ApiError } from '../../types/errors';
import { API_URL } from '../../api/firebase';
import { useAuth } from '../../auth/AuthContext';
import type { CarePlanInternal, Grading } from '../../types/envelope';
import { INITIAL_STEPS } from './CarePlanPage';
import type { PipelineStep } from '../../types/carePlan';
import CarePlanJobErrorView from './CarePlanJobErrorView';
import CarePlanJobResultView from './CarePlanJobResultView';

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
      ? (jobDoc.output_data as unknown as CarePlanInternal)
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
    return (
      <CarePlanJobResultView
        result={result}
        jobDoc={jobDoc}
        id={id}
        isPublicView={isPublicView}
        user={user}
        gradingLoading={gradingLoading}
        gradingError={gradingError}
        shareLoading={shareLoading}
        showSplitView={showSplitView}
        setShowSplitView={setShowSplitView}
        showCommentArea={showCommentArea}
        setShowCommentArea={setShowCommentArea}
        commentText={commentText}
        setCommentText={setCommentText}
        commentSaving={commentSaving}
        commentSaved={commentSaved}
        setCommentSaved={setCommentSaved}
        handleSaveComment={handleSaveComment}
        handleDownloadJson={handleDownloadJson}
        handleDownloadPdf={handleDownloadPdf}
        handleRunGrading={handleRunGrading}
        handleToggleShare={handleToggleShare}
      />
    );
  }

  if (jobDoc.status === 'error') {
    return (
      <CarePlanJobErrorView
        errorData={jobDoc.error_data}
        sessionId={jobDoc.session_id ?? null}
        traceId={jobDoc.trace_id ?? null}
        isPublicView={isPublicView}
      />
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
