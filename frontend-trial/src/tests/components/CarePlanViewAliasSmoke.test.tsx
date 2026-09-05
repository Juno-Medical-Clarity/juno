import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import CarePlanView from '@main/components/CarePlanView';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

describe('alias smoke: @main/components/CarePlanView', () => {
  it('renders without throwing and without console.error', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const fixture: SimplifiedCarePlan = {
      doc_type: 'care_plan',
      urgency: 'normal',
      version: '1.2',
      summary: 'Take it easy for a week.',
      reason_for_visit: [],
      diagnosis: { details: [] },
      medications: [],
      tests: [],
      procedures: [],
      other: [],
      follow_up: [],
      warning_signs: [],
      questions: [],
      low_priority: [],
    };
    const grading: Grading = { entries: [], enabled: false, graded_at: null };

    const { getByText } = render(<CarePlanView result={fixture} grading={grading} />);
    expect(getByText('Take it easy for a week.')).toBeInTheDocument();
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });
});
