import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const deleteTrialJobMock = vi.fn().mockResolvedValue(undefined);
vi.mock('../../api/trialApi', () => ({ deleteTrialJob: (...a: unknown[]) => deleteTrialJobMock(...a) }));
const downloadReportMock = vi.fn();
vi.mock('../../utils/downloadReport', () => ({ downloadReport: (...a: unknown[]) => downloadReportMock(...a) }));
vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

import ResultScreen from '../../components/ResultScreen';
import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

const completedJobDoc: TrialJobDoc = {
  status: 'completed', stage: 5, name: 'Jan 5 Care Plan', error_data: null,
  output_data: {
    metrics: { created_at: '2026-01-05T10:00:00Z', total_duration_ms: 12000 },
    grading: { entries: [
      { name: 'combined', target: 'before', grade: 42, grade_breakdown: null, reasoning: null },
      { name: 'combined', target: 'after', grade: 78, grade_breakdown: null, reasoning: null },
    ], enabled: true, graded_at: null },
    care_plan: { doc_type: 'care_plan', urgency: 'normal', version: '1.2', summary: 'Rest up.', reason_for_visit: [], diagnosis: { details: [] }, medications: [], tests: [], procedures: [], other: [], follow_up: [], warning_signs: [], questions: [], low_priority: [] },
  },
};

const errorJobDoc: TrialJobDoc = {
  status: 'error', stage: 2, name: '', output_data: null,
  error_data: { code: 'INTERNAL_ERROR', message: 'boom', user_hint: 'Something went wrong. Please try again.', retryable: true, details: null, timestamp: '2026-01-05T10:00:00Z' },
};

describe('ResultScreen', () => {
  const deletedRef = { current: new Set<string>() };
  beforeEach(() => { deletedRef.current = new Set(); deleteTrialJobMock.mockClear(); downloadReportMock.mockClear(); });

  it('renders title, date (no prefix), before->after score, and CarePlanView content on completed', () => {
    render(<ResultScreen jobDoc={completedJobDoc} jobId="job-1" deletedRef={deletedRef} onRestart={vi.fn()} />);
    expect(screen.getByText('Jan 5 Care Plan')).toBeInTheDocument();
    expect(screen.getByText('January 5, 2026')).toBeInTheDocument();
    expect(screen.queryByText(/Simplified on/)).not.toBeInTheDocument();
    expect(screen.getByText('42 → 78')).toBeInTheDocument();
    expect(screen.getByText('Rest up.')).toBeInTheDocument();
  });

  it('renders the error message and Try again button on error, calling onRestart when clicked', async () => {
    const onRestart = vi.fn();
    const user = userEvent.setup();
    render(<ResultScreen jobDoc={errorJobDoc} jobId="job-2" deletedRef={deletedRef} onRestart={onRestart} />);
    expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRestart).toHaveBeenCalledOnce();
  });

  it('calls downloadReport when "Download report" is clicked', async () => {
    const user = userEvent.setup();
    render(<ResultScreen jobDoc={completedJobDoc} jobId="job-1" deletedRef={deletedRef} onRestart={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Download report' }));
    expect(downloadReportMock).toHaveBeenCalledOnce();
  });
});
