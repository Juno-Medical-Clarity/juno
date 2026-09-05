import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const trackEventMock = vi.fn();
vi.mock('../../analytics/ga', () => ({ trackEvent: (...a: unknown[]) => trackEventMock(...a) }));

import { downloadReport } from '../../utils/downloadReport';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

const fixture: SimplifiedCarePlan = {
  doc_type: 'care_plan', urgency: 'normal', version: '1.2',
  summary: 'Take it easy for a week.', reason_for_visit: [], diagnosis: { details: [] },
  medications: [], tests: [], procedures: [], other: [], follow_up: [],
  warning_signs: [], questions: [], low_priority: [],
};
const grading: Grading = { entries: [], enabled: false, graded_at: null };

describe('downloadReport', () => {
  beforeEach(() => { vi.useFakeTimers(); trackEventMock.mockClear(); });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('writes non-empty HTML and calls print() after the 500ms delay', () => {
    const printSpy = vi.fn();
    const fakeWindow = { document: { write: vi.fn(), close: vi.fn() }, print: printSpy };
    vi.spyOn(window, 'open').mockReturnValue(fakeWindow as unknown as Window);

    downloadReport(fixture, grading);

    expect(fakeWindow.document.write).toHaveBeenCalledOnce();
    const html = fakeWindow.document.write.mock.calls[0][0] as string;
    expect(html).toContain('Take it easy for a week.');
    expect(printSpy).not.toHaveBeenCalled();
    vi.advanceTimersByTime(500);
    expect(printSpy).toHaveBeenCalledOnce();
  });

  it('nulls printWindow.opener after opening the window (defense-in-depth vs stored XSS)', () => {
    const fakeWindow = { document: { write: vi.fn(), close: vi.fn() }, print: vi.fn(), opener: { some: 'window' } };
    vi.spyOn(window, 'open').mockReturnValue(fakeWindow as unknown as Window);

    downloadReport(fixture, grading);

    expect(fakeWindow.document.write).toHaveBeenCalledOnce();
    expect(fakeWindow.opener).toBeNull();
  });

  it('alerts and never calls document.write when the pop-up is blocked', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    downloadReport(fixture, grading);

    expect(alertSpy).toHaveBeenCalledOnce();
  });

  it('calls trackEvent with exactly report_downloaded', () => {
    vi.spyOn(window, 'open').mockReturnValue({ document: { write: vi.fn(), close: vi.fn() }, print: vi.fn() } as unknown as Window);
    downloadReport(fixture, grading);
    expect(trackEventMock).toHaveBeenCalledWith({ name: 'report_downloaded', params: {} });
  });
});
