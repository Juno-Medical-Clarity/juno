import { useEffect, useRef, useState } from 'react';
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

// Client-side watchdog for a job stuck in `processing` forever (edge-case
// review #1): if the worker is hard-killed (OOM, container crash) after
// Cloud Tasks dispatches the task but before its own outer try/except gets a
// chance to run, `fail_job()` never fires and the Firestore doc never reaches
// a terminal status. The only backend backstop is `expires_at`
// (backend/routes/trial.py, JOB_TTL_HOURS), a Firestore-native TTL field
// whose documented SLA is "typically within 24 hours" of expiry -- far too
// slow to be the only signal a real visitor gets. The backend's own soft
// per-job deadline is 270s (Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S)
// and the Cloud Tasks dispatch deadline is 300s (JOB_TIMEOUT_SECONDS_SINGLE);
// a healthy job that hits either of those still reaches a terminal `error`
// status through the normal Firestore listener path, no watchdog needed. This
// timeout is set comfortably above both of those (with slack for queueing
// delay and a possible Cloud Tasks retry) so it only fires for the genuinely
// stuck case, while staying far below the ~24h TTL backstop.
const WATCHDOG_TIMEOUT_MS = 6 * 60 * 1000;

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
  const [timedOut, setTimedOut] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const steps = stepsFromStage(jobDoc?.stage ?? null);

  // Move focus to this screen's heading on arrival (edge-case review #3) so
  // screen-reader/keyboard users get an announcement that the upload was
  // accepted and processing has started. Mount-only: this component is
  // freshly mounted each time TrialPage swaps into the 'processing' screen,
  // so a plain empty-deps effect fires exactly once per transition.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // Watchdog timer for a job that never reaches a terminal status (see the
  // WATCHDOG_TIMEOUT_MS comment above). Independent of the Firestore
  // listener — it fires purely on wall-clock time since this screen mounted.
  // Cleared on unmount, which also covers "any terminal status": once jobDoc
  // reaches 'completed'/'error', TrialPage swaps ProcessingScreen out for
  // ResultScreen, unmounting this component and its timer along with it.
  useEffect(() => {
    const timer = setTimeout(() => setTimedOut(true), WATCHDOG_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

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
  const activeStep = steps.find(step => step.status === 'active');
  // A single polite live region for the whole screen: its text is a pure
  // function of props/state that only actually change when there's something
  // worth announcing (a new active step, a timeout, a terminal condition), so
  // this never re-announces the same content on an unrelated re-render.
  // Deliberately worded differently from the adjacent visible copy below
  // (rather than repeating it verbatim) so this sr-only text can't collide
  // with a getByText query aimed at that visible copy.
  const liveMessage = jobGone
    ? 'Your previous submission could not be completed and was removed.'
    : snapshotError
      ? "We're having trouble reaching the server. Retrying automatically."
      : timedOut
        ? 'Processing is taking longer than usual.'
        : activeStep
          ? `Step ${activeStep.id} of ${TRIAL_STEPS.length}: ${activeStep.label}`
          : '';

  return (
    <div className="glass-card">
      <h1 ref={headingRef} tabIndex={-1} className="section-title">Creating your simplified care plan…</h1>
      <p className="sr-only" role="status" aria-live="polite">{liveMessage}</p>
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
        <>
          {timedOut && (
            <div className="watchdog-notice">
              <p>
                This is taking longer than expected. You're welcome to keep
                waiting, or start over.
              </p>
              <button className="cta-btn" onClick={onRestart}>Start over</button>
            </div>
          )}
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
        </>
      )}
    </div>
  );
}
