import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

// --- api/trialApi -----------------------------------------------------
const createTrialJobMock = vi.fn();
const deleteTrialJobMock = vi.fn().mockResolvedValue(undefined);
vi.mock('../../api/trialApi', () => ({
  createTrialJob: (...a: unknown[]) => createTrialJobMock(...a),
  deleteTrialJob: (...a: unknown[]) => deleteTrialJobMock(...a),
}));

// --- utils/downloadReport ----------------------------------------------
vi.mock('../../utils/downloadReport', () => ({ downloadReport: vi.fn() }));

// --- analytics/ga --------------------------------------------------------
vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

// --- hooks/useAnonAuth ---------------------------------------------------
vi.mock('../../hooks/useAnonAuth', () => ({
  useAnonAuth: () => ({ authState: 'ready', user: null, retry: vi.fn() }),
}));

// --- hooks/useTrialJobSnapshot -------------------------------------------
// TrialPage's whole job is to stop depending on this hook's live value once a
// terminal snapshot has been captured. We fully control what this mock
// returns (and record the jobId TrialPage passes in) so we can simulate the
// backend deleting the doc out from under a still-subscribed listener.
const useTrialJobSnapshotMock = vi.fn();
vi.mock('../../hooks/useTrialJobSnapshot', () => ({
  useTrialJobSnapshot: (...a: unknown[]) => useTrialJobSnapshotMock(...a),
}));

import TrialPage from '../../pages/TrialPage';

function makeFile(name: string) {
  return new File(['hello'], name, { type: 'text/plain' });
}

const completedDoc: TrialJobDoc = {
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

const errorDoc: TrialJobDoc = {
  status: 'error', stage: 2, name: '', output_data: null,
  error_data: { code: 'INTERNAL_ERROR', message: 'boom', user_hint: 'Something went wrong. Please try again.', retryable: true, details: null, timestamp: '2026-01-05T10:00:00Z' },
};

async function createJob(user: ReturnType<typeof userEvent.setup>) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(input, makeFile('note.txt'));
  await user.click(screen.getByRole('button', { name: 'Simplify' }));
}

describe('TrialPage', () => {
  beforeEach(() => {
    createTrialJobMock.mockReset().mockResolvedValue({ job_id: 'job-1' });
    deleteTrialJobMock.mockClear();
    useTrialJobSnapshotMock.mockReset().mockReturnValue({ jobDoc: null, loading: false, error: null });
  });

  it('keeps the completed result rendered after the listener reports the doc as gone (post-delete)', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<MemoryRouter><TrialPage /></MemoryRouter>);

    await createJob(user);
    // Now in 'processing' — hook should be watching job-1.
    expect(useTrialJobSnapshotMock).toHaveBeenLastCalledWith('job-1');

    // Simulate Firestore pushing the terminal snapshot.
    useTrialJobSnapshotMock.mockReturnValue({ jobDoc: completedDoc, loading: false, error: null });
    await act(async () => { rerender(<MemoryRouter><TrialPage /></MemoryRouter>); });

    // Result is visible and the primary delete trigger fired.
    expect(screen.getByText('Jan 5 Care Plan')).toBeInTheDocument();
    expect(screen.getByText('42 → 78')).toBeInTheDocument();
    expect(deleteTrialJobMock).toHaveBeenCalledWith('job-1');
    // Documented exclusion: no "Another care plan" button on the success view.
    expect(screen.queryByRole('button', { name: /another care plan/i })).not.toBeInTheDocument();

    // Once captured, TrialPage must stop watching the live doc.
    expect(useTrialJobSnapshotMock).toHaveBeenLastCalledWith(null);

    // Now simulate the listener subsequently reporting the document as gone —
    // this is exactly what happened before the fix: backend delete propagates,
    // onSnapshot fires with !exists(), jobDoc goes null.
    useTrialJobSnapshotMock.mockReturnValue({ jobDoc: null, loading: false, error: null });
    await act(async () => { rerender(<MemoryRouter><TrialPage /></MemoryRouter>); });

    // The screen must NOT go blank — it renders from the captured copy.
    expect(screen.getByText('Jan 5 Care Plan')).toBeInTheDocument();
    expect(screen.getByText('42 → 78')).toBeInTheDocument();
    expect(screen.getByText('Rest up.')).toBeInTheDocument();
  });

  it('keeps the error result rendered after the listener reports the doc as gone, and "Try again" fully resets', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<MemoryRouter><TrialPage /></MemoryRouter>);

    await createJob(user);
    expect(useTrialJobSnapshotMock).toHaveBeenLastCalledWith('job-1');

    useTrialJobSnapshotMock.mockReturnValue({ jobDoc: errorDoc, loading: false, error: null });
    await act(async () => { rerender(<MemoryRouter><TrialPage /></MemoryRouter>); });

    expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
    expect(deleteTrialJobMock).toHaveBeenCalledWith('job-1');
    expect(useTrialJobSnapshotMock).toHaveBeenLastCalledWith(null);

    // Listener subsequently reports the doc as gone — error view must survive.
    useTrialJobSnapshotMock.mockReturnValue({ jobDoc: null, loading: false, error: null });
    await act(async () => { rerender(<MemoryRouter><TrialPage /></MemoryRouter>); });
    expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();

    // "Try again" resets fully: back to upload, no stale result, watcher cleared.
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByRole('button', { name: 'Simplify' })).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong. Please try again.')).not.toBeInTheDocument();
    expect(useTrialJobSnapshotMock).toHaveBeenLastCalledWith(null);
  });
});
