import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OutputGradingCard from '../../components/OutputGradingCard';
import type { Grading } from '../../types/envelope';

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

function makeEmptyGrading(): Grading {
  return { entries: [], enabled: true, graded_at: null };
}

function makeFullGrading(): Grading {
  return {
    enabled: true,
    graded_at: '2026-06-01T12:00:00Z',
    entries: [
      { name: 'combined',       target: 'before', grade: 60, grade_breakdown: { grade_estimate: 12.0, label: 'Hard', word_count: 400 }, reasoning: null },
      { name: 'combined',       target: 'after',  grade: 78, grade_breakdown: { grade_estimate: 7.5,  label: 'Moderate', word_count: 400 }, reasoning: null },
      { name: 'smog',           target: 'before', grade: 52, grade_breakdown: { grade: 12.1, insufficient_sample: false }, reasoning: null },
      { name: 'smog',           target: 'after',  grade: 68, grade_breakdown: { grade: 8.2,  insufficient_sample: false }, reasoning: null },
      { name: 'flesch_kincaid', target: 'before', grade: 48, grade_breakdown: { reading_ease: 42.1, grade_level: 9.3 }, reasoning: null },
      { name: 'flesch_kincaid', target: 'after',  grade: 72, grade_breakdown: { reading_ease: 68.5, grade_level: 6.1 }, reasoning: null },
      { name: 'dale_chall',     target: 'before', grade: 45, grade_breakdown: { raw_score: 9.1, grade_range: '9-10' }, reasoning: null },
      { name: 'dale_chall',     target: 'after',  grade: 68, grade_breakdown: { raw_score: 6.2, grade_range: '5-6' }, reasoning: null },
      { name: 'pemat',          target: 'before', grade: 55, grade_breakdown: { understandability: 55, actionability: 60 }, reasoning: null },
      { name: 'pemat',          target: 'after',  grade: 80, grade_breakdown: { understandability: 80, actionability: 85 }, reasoning: null },
      { name: 'sam',            target: 'before', grade: 50, grade_breakdown: { content: 3, literacy_demand: 6, layout_typography: 2 }, reasoning: null },
      { name: 'sam',            target: 'after',  grade: 71, grade_breakdown: { content: 6, literacy_demand: 11, layout_typography: 5 }, reasoning: null },
      { name: 'cdc_cci',        target: 'before', grade: 44, grade_breakdown: { main_message: 0, behavioral_recommendations: 1, numbers: 1, call_to_action: 0 }, reasoning: null },
      { name: 'cdc_cci',        target: 'after',  grade: 76, grade_breakdown: { main_message: 1, behavioral_recommendations: 1, numbers: 1, call_to_action: 1 }, reasoning: null },
    ],
  };
}

describe('OutputGradingCard', () => {
  it('top-level toggle is collapsed by default', () => {
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    expect(screen.queryByText('SMOG')).not.toBeInTheDocument();
    expect(screen.queryByText('Combined Score')).not.toBeInTheDocument();
  });

  it('clicking top-level toggle expands the section (shows method rows)', async () => {
    const user = userEvent.setup();
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    await user.click(screen.getByText(/Score \(60 → 78\)/));
    expect(screen.getByText('Combined Score')).toBeInTheDocument();
  });

  it('renders Score (X → Y) label with correct values from combined entry', () => {
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    expect(screen.getByText(/Score \(60 → 78\)/)).toBeInTheDocument();
  });

  it('renders Score (Y) when only after combined entry exists', () => {
    const grading: Grading = {
      enabled: true,
      graded_at: null,
      entries: [
        { name: 'combined', target: 'after', grade: 78, grade_breakdown: null, reasoning: null },
      ],
    };
    render(<OutputGradingCard grading={grading} error={null} />);
    expect(screen.getByText(/Score \(78\)/)).toBeInTheDocument();
  });

  it('renders "Score" label when no combined entry', () => {
    const grading: Grading = {
      enabled: true,
      graded_at: null,
      entries: [
        { name: 'smog', target: 'after', grade: 70, grade_breakdown: null, reasoning: null },
      ],
    };
    render(<OutputGradingCard grading={grading} error={null} />);
    // Should show "Score" without parentheses
    const heading = screen.getByText('Score');
    expect(heading).toBeInTheDocument();
  });

  it('renders empty-state message when grading.entries is empty and no error', async () => {
    const user = userEvent.setup();
    render(<OutputGradingCard grading={makeEmptyGrading()} error={null} />);
    await user.click(screen.getByText('Score'));
    expect(screen.getByText(/No grading data — click Run Grading to score this output\./)).toBeInTheDocument();
  });

  it('renders empty-state message when grading.enabled is false', async () => {
    const user = userEvent.setup();
    const grading: Grading = { enabled: false, entries: [], graded_at: null };
    render(<OutputGradingCard grading={grading} error={null} />);
    await user.click(screen.getByText('Score'));
    expect(screen.getByText(/No grading data — click Run Grading to score this output\./)).toBeInTheDocument();
  });

  it('does not render error text inside the component (error is shown in CarePlanPage)', () => {
    render(<OutputGradingCard grading={makeEmptyGrading()} error="Grading failed" />);
    expect(screen.queryByText('Grading failed')).not.toBeInTheDocument();
  });

  it('Expand All opens all method rows; Collapse All closes them', async () => {
    const user = userEvent.setup();
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);

    // Expand top first
    await user.click(screen.getByText(/Score \(60 → 78\)/));
    // Click Expand All
    await user.click(screen.getByText('Expand All'));
    // All 7 method labels should be visible
    expect(screen.getByText('Combined Score')).toBeInTheDocument();
    expect(screen.getByText('SMOG')).toBeInTheDocument();
    expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
    expect(screen.getByText('Dale-Chall')).toBeInTheDocument();
    expect(screen.getByText('PEMAT')).toBeInTheDocument();
    expect(screen.getByText('SAM')).toBeInTheDocument();
    expect(screen.getByText('CDC Clear Comm.')).toBeInTheDocument();
    // Breakdown should be visible for Flesch-Kincaid (check for a specific leaf element)
    expect(screen.getAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('reading ease:') === true;
    }).length).toBeGreaterThan(0);

    // Click Collapse All
    await user.click(screen.getByText('Collapse All'));
    // Breakdown should be gone
    expect(screen.queryAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('reading ease:') === true;
    }).length).toBe(0);
  });

  it('renders 7 method rows when both before and after entries exist', async () => {
    const user = userEvent.setup();
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    await user.click(screen.getByText(/Score \(60 → 78\)/));
    // All 7 method label texts should be present
    expect(screen.getByText('Combined Score')).toBeInTheDocument();
    expect(screen.getByText('SMOG')).toBeInTheDocument();
    expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
    expect(screen.getByText('Dale-Chall')).toBeInTheDocument();
    expect(screen.getByText('PEMAT')).toBeInTheDocument();
    expect(screen.getByText('SAM')).toBeInTheDocument();
    expect(screen.getByText('CDC Clear Comm.')).toBeInTheDocument();
  });

  it('renders grade_breakdown key-value pairs in expanded row body', async () => {
    const user = userEvent.setup();
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    // Expand top
    await user.click(screen.getByText(/Score \(60 → 78\)/));
    // Expand Flesch-Kincaid row
    await user.click(screen.getByText('Flesch-Kincaid'));
    // Should show breakdown keys (underscores replaced with spaces)
    expect(screen.getAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('reading ease:') === true;
    }).length).toBeGreaterThan(0);
    expect(screen.getAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('grade level:') === true;
    }).length).toBeGreaterThan(0);
  });

  it('skips nested object values in breakdown (combined dimensions not shown)', async () => {
    const user = userEvent.setup();
    const grading: Grading = {
      enabled: true,
      graded_at: null,
      entries: [
        {
          name: 'combined',
          target: 'after',
          grade: 78,
          grade_breakdown: {
            grade_estimate: 7.5,
            label: 'Moderate',
            word_count: 400,
            dimensions: { grade_level: { score: 80, raw: 8.0 } },
          },
          reasoning: null,
        },
      ],
    };
    render(<OutputGradingCard grading={grading} error={null} />);
    await user.click(screen.getByText(/Score \(78\)/));
    await user.click(screen.getByText('Combined Score'));
    // Scalar keys should appear (word_count is intentionally hidden)
    expect(screen.getAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('grade estimate:') === true;
    }).length).toBeGreaterThan(0);
    // word_count is filtered out of combined score breakdown
    expect(screen.queryAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('word count:') === true;
    }).length).toBe(0);
    // Nested dimensions should NOT appear
    expect(screen.queryAllByText((content, element) => {
      return element?.tagName === 'STRONG' && element?.textContent?.toLowerCase().includes('dimensions:') === true;
    }).length).toBe(0);
  });

  it('Run Grading button does not appear anywhere in the component', () => {
    render(<OutputGradingCard grading={makeFullGrading()} error={null} />);
    expect(screen.queryByRole('button', { name: /run grading/i })).not.toBeInTheDocument();
  });
});
