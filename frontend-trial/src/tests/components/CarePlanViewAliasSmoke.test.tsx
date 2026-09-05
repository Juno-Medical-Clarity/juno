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

  // The above fixture is entirely empty (no reason_for_visit, medications,
  // terms, etc.), so it never renders ResultCard (which calls useState) or
  // MedicalTerm (useState/useId/useRef/useEffect) — the only parts of
  // CarePlanView that actually call a hook. That blind spot is exactly how a
  // real production bug (frontend/ and frontend-trial/ each resolving their
  // own separate copy of "react", so a hook call inside this @main-aliased
  // component hit a second copy's unset dispatcher) shipped without this
  // smoke test catching it: "Cannot read properties of null (reading
  // 'useState')", uncaught, blanking the whole page. This case forces both
  // hook-bearing branches to actually render.
  it('renders hook-bearing branches (ResultCard, MedicalTerm) without throwing', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const fixture: SimplifiedCarePlan = {
      doc_type: 'care_plan',
      urgency: 'caution',
      version: '1.2',
      summary: 'Your hypertension needs attention.',
      reason_for_visit: [{ reason: 'Checkup', description: 'Routine visit.' }],
      diagnosis: { main_conclusion: 'Blood pressure is high.', details: [] },
      medications: [],
      tests: [],
      procedures: [],
      other: [],
      follow_up: [],
      warning_signs: [],
      questions: [],
      low_priority: [],
      terms: { hypertension: { definition: 'High blood pressure.', source: 'preserved' } },
    };
    const grading: Grading = { entries: [], enabled: false, graded_at: null };

    const { getByText, container } = render(<CarePlanView result={fixture} grading={grading} />);
    expect(getByText('Checkup')).toBeInTheDocument();
    // "hypertension" appears wrapped in a <MedicalTerm> — assert on the
    // component's marker class rather than text, since the term legitimately
    // renders more than once (summary text + glossary entry).
    expect(container.querySelectorAll('.medical-term').length).toBeGreaterThan(0);
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });
});
