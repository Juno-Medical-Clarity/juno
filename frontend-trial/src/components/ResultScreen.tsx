import { useEffect, useRef } from 'react';
import CarePlanView from '@main/components/CarePlanView';
import type { CarePlanInternal } from '@main/types/envelope';
import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
import { deleteTrialJob } from '../api/trialApi';
import { downloadReport } from '../utils/downloadReport';
import { trackEvent } from '../analytics/ga';

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
      const combined = outputData.grading.entries.filter(e => e.name === 'combined');
      const before = combined.find(e => e.target === 'before')?.grade ?? 0;
      const after = combined.find(e => e.target === 'after')?.grade ?? 0;
      trackEvent({
        name: 'simplify_complete',
        params: {
          total_duration_ms: outputData.metrics.total_duration_ms ?? 0,
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

  if (!outputData) return null;

  const { care_plan, grading, metrics } = outputData;
  const combined = grading.entries.filter(e => e.name === 'combined');
  const before = combined.find(e => e.target === 'before')?.grade;
  const after = combined.find(e => e.target === 'after')?.grade;
  const formattedDate = new Date(metrics.created_at).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  });

  return (
    <div>
      <h1>{jobDoc.name}</h1>
      <p>{formattedDate}</p>
      {before != null && after != null && (
        <p className="score-widget">{before} → {after}</p>
      )}
      <CarePlanView result={care_plan} grading={grading} />
      <button className="cta-btn" onClick={() => downloadReport(care_plan, grading)}>
        Download report
      </button>
    </div>
  );
}
