import { useEffect, useRef } from 'react';
import type { PipelineStep } from '@main/types/carePlan';
import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
import { trackEvent } from '../analytics/ga';

interface ProcessingScreenProps {
  jobDoc: TrialJobDoc | null;
  snapshotError: Error | null;
  // Null until the first Firestore snapshot callback arrives; false only once
  // a real callback has confirmed the doc is gone. See useTrialJobSnapshot's
  // `exists` field — this is deliberately not derived from `jobDoc === null`,
  // which is also true during ordinary initial load.
  jobExists: boolean | null;
  onRestart: () => void;
}

const TRIAL_STEPS: Omit<PipelineStep, 'status'>[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary' },
  { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow' },
];

const STEP_KEYS: Record<number, string> = {
  1: 'read_note', 2: 'find_terms', 3: 'simplify', 4: 'clarify', 5: 'organize',
};

function stepsFromStage(stage: number | null): PipelineStep[] {
  return TRIAL_STEPS.map(step => ({
    ...step,
    status: stage == null ? 'waiting' : step.id < stage ? 'done' : step.id === stage ? 'active' : 'waiting',
  }));
}

function stepIcon(status: string): string {
  if (status === 'done') return '✓';
  if (status === 'active') return '◉';
  return '○';
}

export default function ProcessingScreen({ jobDoc, snapshotError, jobExists, onRestart }: ProcessingScreenProps) {
  const seenActive = useRef<Set<number>>(new Set());
  const seenDone = useRef<Set<number>>(new Set());
  const steps = stepsFromStage(jobDoc?.stage ?? null);

  // Fire pipeline_step_start/pipeline_step_complete the FIRST time a step is
  // computed as 'active'/'done', per PRD §4.9 — idempotent via the two Sets
  // above (React Strict Mode double-invokes effects in dev).
  useEffect(() => {
    for (const step of steps) {
      if (step.status === 'active' && !seenActive.current.has(step.id)) {
        seenActive.current.add(step.id);
        trackEvent({ name: 'pipeline_step_start', params: { step_id: step.id, step_key: STEP_KEYS[step.id] } });
      }
      if (step.status === 'done' && !seenDone.current.has(step.id)) {
        seenDone.current.add(step.id);
        trackEvent({ name: 'pipeline_step_complete', params: { step_id: step.id, step_key: STEP_KEYS[step.id] } });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobDoc?.stage]);

  // A confirmed-missing doc (jobExists === false, set only after a real
  // snapshot callback — see the prop comment above) means the job was
  // deleted or expired out from under us: there is nothing left to wait for,
  // so this is terminal and distinct from a transient connection error.
  const jobGone = jobExists === false;

  return (
    <div className="glass-card">
      <p className="section-title">Creating your simplified care plan…</p>
      {jobGone ? (
        <>
          <p className="error-box">
            This session ended and your care plan was removed. Nothing was saved.
          </p>
          <button className="cta-btn" onClick={onRestart}>Start over</button>
        </>
      ) : snapshotError ? (
        <>
          <p>
            We lost connection while checking your progress. Please check your
            connection — this page will keep trying to reconnect.
          </p>
          <button className="cta-btn" onClick={onRestart}>Start over</button>
        </>
      ) : (
        <div className="step-list">
          {steps.map(step => (
            <div className="step-item" key={step.id}>
              <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
              <div className="step-content">
                <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>{step.label}</p>
                <p className="step-desc">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
