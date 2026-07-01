import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: 'job-123' }),
  useNavigate: () => vi.fn(),
  useLocation: () => ({ state: null, pathname: '/' }),
}));

vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: null, getIdToken: vi.fn() }),
}));

// Mock firebase
vi.mock('../../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  firebaseDb: {},
  API_URL: 'http://localhost:8082',
}));

// Mock the hook
const mockUseJobSnapshot = vi.fn();
vi.mock('../../../hooks/useJobSnapshot', () => ({
  useJobSnapshot: (id: string) => mockUseJobSnapshot(id),
}));

// Mock CarePlanView
vi.mock('../../../components/CarePlanView', () => ({
  default: () => <div data-testid="care-plan-view">CarePlanView</div>,
}));

// Mock NavBar
vi.mock('../../../components/NavBar', () => ({
  default: () => <nav data-testid="navbar">NavBar</nav>,
}));

// Must import after mocks
import CarePlanJobPage from '../../../pages/care-plan/CarePlanJobPage';

describe('CarePlanJobPage', () => {
  beforeEach(() => {
    mockUseJobSnapshot.mockClear();
  });

  it('shows loading text while loading', () => {
    mockUseJobSnapshot.mockReturnValue({ jobDoc: null, loading: true, error: null });
    render(<CarePlanJobPage />);
    expect(screen.getByText('Loading…')).toBeTruthy();
  });

  it('shows error message on error', () => {
    mockUseJobSnapshot.mockReturnValue({
      jobDoc: null,
      loading: false,
      error: new Error('Network error'),
    });
    render(<CarePlanJobPage />);
    expect(screen.getByText(/Error loading care plan: Network error/)).toBeTruthy();
  });

  it('shows permission message for permission errors', () => {
    mockUseJobSnapshot.mockReturnValue({
      jobDoc: null,
      loading: false,
      error: new Error('missing or insufficient permissions'),
    });
    render(<CarePlanJobPage />);
    expect(screen.getByText('You do not have permission to view this care plan.')).toBeTruthy();
  });

  it('shows "not found" when jobDoc is null and not loading', () => {
    mockUseJobSnapshot.mockReturnValue({ jobDoc: null, loading: false, error: null });
    render(<CarePlanJobPage />);
    expect(screen.getByText('Care plan not found.')).toBeTruthy();
  });

  it('renders CarePlanView when status is completed with output_data', () => {
    mockUseJobSnapshot.mockReturnValue({
      jobDoc: {
        status: 'completed',
        stage: 5,
        output_data: {
          care_plan: { summary: 'ok' },
          grading: { entries: [], enabled: false, graded_at: null },
          metrics: { session_id: '', pipeline_version: 'v1-2', input_type: 'text', created_at: '', total_duration_ms: null, step_durations_ms: {}, saved_id: null },
          input: { mode: 'text', files: [], text: 'test', doc_id: null },
        },
        error_data: null,
        name: 'Test Plan',
        batch_run_id: null,
      },
      loading: false,
      error: null,
    });
    render(<CarePlanJobPage />);
    expect(screen.getByTestId('care-plan-view')).toBeTruthy();
  });

  it('shows error_data message when status is error', () => {
    mockUseJobSnapshot.mockReturnValue({
      jobDoc: {
        status: 'error',
        stage: null,
        output_data: null,
        error_data: { code: 'PIPELINE_ERROR', message: 'Pipeline failed', user_hint: 'An error occurred' },
        name: 'Test',
        batch_run_id: null,
      },
      loading: false,
      error: null,
    });
    render(<CarePlanJobPage />);
    expect(screen.getByText('Pipeline failed')).toBeTruthy();
  });

  it('shows processing steps with correct status for stage=3', () => {
    mockUseJobSnapshot.mockReturnValue({
      jobDoc: {
        status: 'processing',
        stage: 3,
        output_data: null,
        error_data: null,
        name: 'Processing…',
        batch_run_id: null,
      },
      loading: false,
      error: null,
    });
    render(<CarePlanJobPage />);

    // Step 1 and 2 should be done (◉ for active step 3, ✓ for done)
    // We check for the "Creating your care plan" text which appears when processing
    expect(screen.getByText('Creating your care plan…')).toBeTruthy();

    // ✓ should appear for done steps (1,2)
    const doneIcons = screen.getAllByText('✓');
    expect(doneIcons).toHaveLength(2);

    // ◉ should appear for step 3 (active)
    const activeIcons = screen.getAllByText('◉');
    expect(activeIcons).toHaveLength(1);

    // ○ should appear for waiting steps (4,5)
    const waitingIcons = screen.getAllByText('○');
    expect(waitingIcons).toHaveLength(2);
  });
});
