import { useEffect, useRef } from 'react';
import CarePlanView from '@main/components/CarePlanView';
import type { CarePlanInternal } from '@main/types/envelope';
import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
import { deleteTrialJob } from '../api/trialApi';
import { downloadReport } from '../utils/downloadReport';
import { trackEvent } from '../analytics/ga';
import ErrorBoundary from './ErrorBoundary';

interface ResultScreenProps {
  jobDoc: TrialJobDoc;
  jobId: string | null;
  deletedRef: React.MutableRefObject<Set<string>>;
  onRestart: () => void;
}

export default function ResultScreen({ jobDoc, jobId, deletedRef, onRestart }: ResultScreenProps) {
  const trackedRef = useRef(false);

  // Primary DELETE trigger (PRD §4.13, layer 1) — fires once, on reaching this
  // screen, sharing deletedRef with TrialPage's safety-net trigger so the two
  // can never double-fire in a way that matters (DELETE is idempotent anyway).
  useEffect(() => {
    if (!jobId || deletedRef.current.has(jobId)) return;
    deletedRef.current.add(jobId);
    void deleteTrialJob(jobId).catch(() => { /* best-effort */ });
  }, [jobId, deletedRef]);

  const outputData = jobDoc.output_data as unknown as CarePlanInternal | null;

  useEffect(() => {
    if (trackedRef.current) return;
    if (jobDoc.status === 'completed' && outputData) {
      trackedRef.current = true;
      // Defensively-accessed: output_data's shape is only a TypeScript
      // contract, not a runtime guarantee — a partially-populated payload
      // must not crash this effect (see the render body below for the same
      // reasoning applied to what's actually shown on screen).
      const entries = outputData.grading?.entries ?? [];
      const combined = entries.filter(e => e.name === 'combined');
      const before = combined.find(e => e.target === 'before')?.grade ?? 0;
      const after = combined.find(e => e.target === 'after')?.grade ?? 0;
      trackEvent({
        name: 'simplify_complete',
        params: {
          total_duration_ms: outputData.metrics?.total_duration_ms ?? 0,
          score_before: before,
          score_after: after,
        },
      });
    } else if (jobDoc.status === 'error' && jobDoc.error_data) {
      trackedRef.current = true;
      trackEvent({
        name: 'simplify_pipeline_error',
        params: { error_code: jobDoc.error_data.code, stage_reached: jobDoc.stage },
      });
    }
  }, [jobDoc, outputData]);

  if (jobDoc.status === 'error') {
    const message = jobDoc.error_data?.user_hint ?? jobDoc.error_data?.message
      ?? 'Something went wrong while creating your care plan.';
    return (
      <div className="glass-card">
        <p className="error-box">{message}</p>
        <button className="cta-btn" onClick={onRestart}>Try again</button>
      </div>
    );
  }

  // Explicit, honest fallback — this used to be a bare `return null`, which
  // silently rendered nothing (the sibling <Footer/> in TrialPage was the
  // only thing left on screen) whenever a "completed" job somehow carried no
  // output_data. That failure mode must never look like a blank page again.
  if (!outputData) {
    return (
      <div className="glass-card">
        <p className="section-title">{jobDoc.name || 'Your care plan'}</p>
        <p className="error-box">
          Processing finished, but we couldn't load your results. Nothing was saved.
        </p>
        <button className="cta-btn" onClick={onRestart}>Start over</button>
      </div>
    );
  }

  // Everything below reads a payload whose real-world shape can diverge from
  // the CarePlanInternal type (a partial write, a schema drift, an upstream
  // bug) — optional-chain and default every field so a partially-populated
  // payload still shows whatever IS present. The care plan body is the
  // actual product; the score widget and date are nice-to-haves.
  const care_plan = outputData.care_plan;
  const grading = outputData.grading ?? { entries: [], enabled: false, graded_at: null };
  const metrics = outputData.metrics;
  const combined = (grading.entries ?? []).filter(e => e.name === 'combined');
  const before = combined.find(e => e.target === 'before')?.grade;
  const after = combined.find(e => e.target === 'after')?.grade;
  const formattedDate = metrics?.created_at
    ? new Date(metrics.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : null;

  return (
    <div>
      <h1>{jobDoc.name || 'Your care plan'}</h1>
      {formattedDate && <p>{formattedDate}</p>}
      {before != null && after != null && (
        <p className="score-widget">Simplification score {before} (before) → {after} (after)</p>
      )}
      {care_plan ? (
        <>
          {/* Local safety net: CarePlanView is shared with the main app (via
              the @main alias) and reads a payload this component only casts,
              never validates. If it throws on an unexpected shape, degrade to
              a message here instead of losing the whole result screen (or,
              absent the app-root boundary, the whole page). */}
          <ErrorBoundary title="We couldn't display your care plan" onReset={onRestart}>
            <CarePlanView result={care_plan} grading={grading} hideLowPriority />
          </ErrorBoundary>
          <button className="cta-btn" onClick={() => downloadReport(care_plan, grading)}>
            Download report
          </button>
        </>
      ) : (
        <p className="error-box">Your care plan details couldn't be loaded, but processing did finish.</p>
      )}
    </div>
  );
}
