import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OutputGradingCard from './OutputGradingCard';
import type { CarePlanInternal, Grading } from '../types/envelope';

// Mock firebase so no real SDK initializes
vi.mock('../api/firebase', () => ({
  firebaseAuth: {
    currentUser: { getIdToken: async () => 'test-token' },
  },
  API_URL: 'http://localhost:8082',
}));

function makeOutput(overrides: Partial<CarePlanInternal> = {}): CarePlanInternal {
  return {
    metrics: {
      session_id: 'session-1',
      pipeline_version: 'v1-2',
      input_type: 'file',
      created_at: '2026-06-01T00:00:00Z',
      total_duration_ms: 1000,
      step_durations_ms: {},
      saved_id: null,
    },
    input: {
      mode: 'file',
      text: null,
      doc_id: null,
      files: [],
    },
    grading: {
      entries: [],
      enabled: true,
      graded_at: null,
    },
    care_plan: {
      doc_type: 'care_plan',
      urgency: 'normal',
      version: '1.2',
      summary: 'Test summary',
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
      raw: {
        text: 'Original text',
        simplified_text: 'Simplified',
        clarified_text: 'Clarified',
      },
    },
    ...overrides,
  };
}

function makeGrading(): Grading {
  return {
    entries: [
      { name: 'combined', target: 'after', grade: 75, grade_breakdown: null, reasoning: null },
    ],
    enabled: true,
    graded_at: '2026-06-01T12:00:00Z',
  };
}

describe('OutputGradingCard', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the "Run Grading" button', () => {
    render(<OutputGradingCard output={makeOutput()} onGraded={() => {}} />);
    expect(screen.getByRole('button', { name: /run grading/i })).toBeInTheDocument();
  });

  it('renders the "Grading" section heading', () => {
    render(<OutputGradingCard output={makeOutput()} onGraded={() => {}} />);
    expect(screen.getByText('Grading')).toBeInTheDocument();
  });

  it('button shows "Grading…" text while loading', async () => {
    // Make fetch hang so we can observe the loading state
    fetchSpy.mockReturnValueOnce(new Promise(() => {})); // never resolves

    const user = userEvent.setup();
    render(<OutputGradingCard output={makeOutput()} onGraded={() => {}} />);

    const btn = screen.getByRole('button', { name: /run grading/i });
    await user.click(btn);

    expect(screen.getByRole('button', { name: /grading…/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /grading…/i })).toBeDisabled();
  });

  it('calls onGraded with grading data from a successful response', async () => {
    const gradingResult = makeGrading();
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ grading: gradingResult }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const onGraded = vi.fn();
    const user = userEvent.setup();
    render(<OutputGradingCard output={makeOutput()} onGraded={onGraded} />);

    await user.click(screen.getByRole('button', { name: /run grading/i }));

    await waitFor(() => {
      expect(onGraded).toHaveBeenCalledOnce();
      expect(onGraded).toHaveBeenCalledWith(gradingResult);
    });
  });

  it('uses saved_id in request body when output has a saved_id', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ grading: makeGrading() }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const output = makeOutput();
    output.metrics.saved_id = 'saved-123';

    const user = userEvent.setup();
    render(<OutputGradingCard output={output} onGraded={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run grading/i }));

    await waitFor(() => {
      const [, init] = fetchSpy.mock.calls[0] as [unknown, RequestInit];
      expect((init as RequestInit).body).toBe(JSON.stringify({ saved_id: 'saved-123' }));
    });
  });

  it('uses text/clarified_text body when no saved_id', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ grading: makeGrading() }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const user = userEvent.setup();
    render(<OutputGradingCard output={makeOutput()} onGraded={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run grading/i }));

    await waitFor(() => {
      const [, init] = fetchSpy.mock.calls[0] as [unknown, RequestInit];
      const body = JSON.parse((init as RequestInit).body as string) as Record<string, unknown>;
      expect(body).toHaveProperty('text');
      expect(body).toHaveProperty('clarified_text');
      expect(body).not.toHaveProperty('saved_id');
    });
  });

  it('shows error message when server returns non-200', async () => {
    fetchSpy.mockResolvedValueOnce(
      new Response('Internal Server Error', { status: 500 }),
    );

    const user = userEvent.setup();
    render(<OutputGradingCard output={makeOutput()} onGraded={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run grading/i }));

    await waitFor(() => {
      expect(screen.getByText(/internal server error/i)).toBeInTheDocument();
    });
  });
});
