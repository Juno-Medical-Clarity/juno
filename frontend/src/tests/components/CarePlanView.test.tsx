/**
 * Smoke tests for CarePlanView (was AppointmentNoteV12View before SP5 rename).
 * Tests that:
 *   - combined + method cards render when grading is present
 *   - readability section absent when grading entries are empty
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CarePlanView from './CarePlanView';
import type { SimplifiedCarePlan, Grading } from '../types/envelope';

vi.mock('../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

function makeDimensions() {
  return {
    grade_level:         { score: 80, raw: 8.0,  label: 'Grade 8',   unit: 'grade' },
    jargon_density:      { score: 70, raw: 0.05, label: 'Low',       unit: 'ratio' },
    sentence_complexity: { score: 75, raw: 18.0, label: 'Moderate',  unit: 'words' },
    passive_voice:       { score: 65, raw: 0.10, label: 'Low',       unit: 'ratio' },
    actionability:       { score: 85, raw: 0.85, label: 'High',      unit: 'ratio' },
    numeracy_clarity:    { score: 72, raw: 0.72, label: 'Good',      unit: 'ratio' },
    structural_clarity:  { score: 78, raw: 0.78, label: 'Clear',     unit: 'ratio' },
  };
}

function makeGradingWithEntries(): Grading {
  const dims = makeDimensions();
  return {
    enabled: true,
    graded_at: '2026-06-19T12:00:00Z',
    entries: [
      {
        name: 'combined',
        target: 'before',
        grade: 55,
        grade_breakdown: { grade_estimate: 12, label: 'Hard', word_count: 400, dimensions: dims },
        reasoning: null,
      },
      {
        name: 'combined',
        target: 'after',
        grade: 78,
        grade_breakdown: { grade_estimate: 8, label: 'Moderate', word_count: 350, dimensions: dims },
        reasoning: null,
      },
      { name: 'smog',           target: 'after', grade: 72, grade_breakdown: { level: 8 },   reasoning: null },
      { name: 'flesch_kincaid', target: 'after', grade: 75, grade_breakdown: { level: 7 },   reasoning: null },
      { name: 'dale_chall',     target: 'after', grade: 68, grade_breakdown: { score: 6.2 }, reasoning: null },
      { name: 'pemat',          target: 'after', grade: 80, grade_breakdown: { score: 0.8 }, reasoning: null },
      { name: 'sam',            target: 'after', grade: 71, grade_breakdown: { level: 'adequate' }, reasoning: null },
      { name: 'cdc_cci',        target: 'after', grade: 76, grade_breakdown: { score: 76 },  reasoning: null },
    ],
  };
}

function makeEmptyGrading(): Grading {
  return { entries: [], enabled: false, graded_at: null };
}

function makeMinimalCarePlan(summary = 'You are doing well.'): SimplifiedCarePlan {
  return {
    doc_type: 'care_plan',
    urgency: 'normal',
    version: '1.2',
    summary,
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
}

describe('CarePlanView (formerly AppointmentNoteV12View)', () => {
  it('renders the summary text', () => {
    render(<CarePlanView result={makeMinimalCarePlan()} grading={makeEmptyGrading()} />);
    expect(screen.getByText('You are doing well.')).toBeInTheDocument();
  });

  it('renders ReadabilityCard (combined scores) when grading has before+after combined entries', () => {
    render(<CarePlanView result={makeMinimalCarePlan()} grading={makeGradingWithEntries()} />);
    expect(screen.getByText('Readability')).toBeInTheDocument();
  });

  it('renders method grading cards when method entries present', () => {
    render(<CarePlanView result={makeMinimalCarePlan()} grading={makeGradingWithEntries()} />);
    // Method names are shown as labels
    expect(screen.getByText('SMOG')).toBeInTheDocument();
    expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
    expect(screen.getByText('Dale-Chall')).toBeInTheDocument();
  });

  it('does not render ReadabilityCard when grading entries are empty', () => {
    render(<CarePlanView result={makeMinimalCarePlan()} grading={makeEmptyGrading()} />);
    expect(screen.queryByText('Readability')).not.toBeInTheDocument();
  });

  it('does not render method cards when grading entries are empty', () => {
    render(<CarePlanView result={makeMinimalCarePlan()} grading={makeEmptyGrading()} />);
    expect(screen.queryByText('SMOG')).not.toBeInTheDocument();
  });

  it('renders "What You Need to Know" section for summary text', () => {
    render(<CarePlanView result={makeMinimalCarePlan('Important info')} grading={makeEmptyGrading()} />);
    expect(screen.getByText('What You Need to Know')).toBeInTheDocument();
    expect(screen.getByText('Important info')).toBeInTheDocument();
  });
});
