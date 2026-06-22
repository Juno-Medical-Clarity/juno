import { useParams } from 'react-router-dom';
import { useJobSnapshot } from '../../hooks/useJobSnapshot';
import { normalizeCarePlanOutput } from '../../utils/normalizeOutput';
import CarePlanView from '../../components/CarePlanView';
import NavBar from '../../components/NavBar';
import { INITIAL_STEPS } from './CarePlanPage';
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
  const { jobDoc, loading, error } = useJobSnapshot(id ?? null);

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

  if (jobDoc.status === 'completed' && jobDoc.output_data) {
    const result = normalizeCarePlanOutput(jobDoc.output_data);
    return (
      <>
        <NavBar />
        <div style={{ maxWidth: '860px', margin: '0 auto', padding: '80px 32px 32px' }}>
          <CarePlanView result={result.care_plan} grading={result.grading} />
        </div>
      </>
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
