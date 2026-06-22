/**
 * Tests for Run Grading integration in CarePlanPage (SP5).
 * Separate file because the existing CarePlanPage.test.tsx mocks useLocation to return
 * { state: null }, which prevents rendering in result state.
 *
 * Strategy: vi.hoisted creates a mutable `locationState` ref that the useLocation
 * mock delegates to. Each test sets locationState.current before rendering so the
 * component mounts in result state. No vi.resetModules() is needed — the single
 * module load picks up the closure reference for all tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CarePlanInternal, SimplifiedCarePlan, Grading } from '../../../types/envelope';

// ── Hoisted mutable state (evaluated before vi.mock calls) ────────────────────

const locationState = vi.hoisted(() => ({ current: null as unknown }));
const mockAuthFetch = vi.hoisted(() => vi.fn());

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../../api/firebase', () => ({
  firebaseAuth: { currentUser: { getIdToken: async () => 'test-token' } },
  API_URL: 'http://localhost:8082',
}));

vi.mock('../../../api/savedOutputs', () => ({
  getSavedOutput: vi.fn(),
  getInputPdfUrl: vi.fn(),
  listSavedOutputs: vi.fn().mockResolvedValue([]),
  renameSavedOutput: vi.fn(),
  deleteSavedOutput: vi.fn(),
}));

vi.mock('../../../api/datasets', () => ({
  runBatch: vi.fn(),
}));

vi.mock('../../../utils/logger', () => ({
  logger: { setSessionId: vi.fn(), info: vi.fn() },
}));

vi.mock('../../../api/apiClient', () => ({
  authenticatedFetch: (...args: unknown[]) => mockAuthFetch(...args),
}));

vi.mock('react-router-dom', () => ({
  useLocation: () => ({ state: locationState.current, pathname: '/care-plan' }),
  useNavigate: () => vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

// ── Static import (must come after vi.mock calls) ─────────────────────────────

import CarePlanPage from '../../../pages/care-plan/CarePlanPage';

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeCarePlan(): SimplifiedCarePlan {
  return {
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
    raw: { text: 'Original', simplified_text: 'Simplified', clarified_text: 'Clarified' },
  };
}

function makeGrading(overrides: Partial<Grading> = {}): Grading {
  return { entries: [], enabled: true, graded_at: null, ...overrides };
}

function makeResult(overrides: Partial<CarePlanInternal> = {}): CarePlanInternal {
  return {
    metrics: {
      session_id: 'sess-1',
      pipeline_version: 'v1-2',
      input_type: 'text',
      created_at: '2026-06-01T00:00:00Z',
      total_duration_ms: 1000,
      step_durations_ms: {},
      saved_id: null,
    },
    input: { mode: 'text', text: 'Original' },
    grading: makeGrading(),
    care_plan: makeCarePlan(),
    ...overrides,
  };
}

// ── Helper ────────────────────────────────────────────────────────────────────

/**
 * Set locationState.current so the component's useEffect fires with an `output`
 * in location.state, then render and wait until the result-state UI is visible.
 */
async function renderInResultState(result: CarePlanInternal = makeResult()) {
  locationState.current = { output: result };
  render(<CarePlanPage />);
  await waitFor(() => {
    expect(screen.getByText(/Download Report/i)).toBeInTheDocument();
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('handleRunGrading (SP5)', () => {
  beforeEach(() => {
    locationState.current = null;
    mockAuthFetch.mockReset();
  });

  it('Run Grading button is visible in download bar when result exists', async () => {
    await renderInResultState();
    expect(screen.getByRole('button', { name: /run grading/i })).toBeInTheDocument();
  });

  it('Run Grading button shows "Grading…" and is disabled while loading', async () => {
    // never resolves — simulates a pending request
    mockAuthFetch.mockReturnValueOnce(new Promise(() => {}));
    const user = userEvent.setup();
    await renderInResultState();
    await user.click(screen.getByRole('button', { name: /run grading/i }));
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /grading…/i });
      expect(btn).toBeDisabled();
    });
  });

  it('Run Grading button calls /care_plan/grade and updates grading on success', async () => {
    const newGrading: Grading = {
      enabled: true,
      graded_at: '2026-06-01T13:00:00Z',
      entries: [
        {
          name: 'combined',
          target: 'after',
          grade: 78,
          grade_breakdown: null,
          reasoning: null,
        },
      ],
    };
    mockAuthFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ grading: newGrading }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const user = userEvent.setup();
    await renderInResultState();
    await user.click(screen.getByRole('button', { name: /run grading/i }));
    await waitFor(() => {
      // combinedScoreLabel returns "Score (78)" when combined.after.grade === 78
      expect(screen.getByText(/Score \(78\)/)).toBeInTheDocument();
    });
  });

  it('Run Grading button shows gradingError below download bar on failure', async () => {
    mockAuthFetch.mockResolvedValueOnce(
      new Response('Grading service unavailable', { status: 503 }),
    );
    const user = userEvent.setup();
    await renderInResultState();
    await user.click(screen.getByRole('button', { name: /run grading/i }));
    await waitFor(() => {
      expect(screen.getByText(/grading service unavailable/i)).toBeInTheDocument();
    });
  });

  it('grading section renders below session-id line in DOM order', async () => {
    await renderInResultState(
      makeResult({
        metrics: {
          session_id: 'sess-123',
          pipeline_version: 'v1-2',
          input_type: 'text',
          created_at: '2026-06-01T00:00:00Z',
          total_duration_ms: 1000,
          step_durations_ms: {},
          saved_id: null,
        },
      }),
    );
    const sessionIdEl = screen.getByText(/Request ID: sess-123/);
    const gradingSection = document.querySelector('.grading-section');
    expect(gradingSection).not.toBeNull();
    // DOCUMENT_POSITION_FOLLOWING (4) means gradingSection comes after sessionIdEl
    const position = sessionIdEl.compareDocumentPosition(gradingSection!);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
