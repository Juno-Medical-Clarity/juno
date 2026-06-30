/**
 * Unit tests for CarePlanPage.tsx:
 *   - outputHasInputPdf / outputHasInputText helper functions
 *   - the `processingIds` set passed down to <Sidebar>, derived from
 *     useJobStatuses() (SP1 → SP3 interface, Task 10.3)
 *
 * The helper functions determine whether a "Show Original" button is surfaced.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { outputHasInputPdf, outputHasInputText } from '../../../pages/care-plan/CarePlanPage';
import type { CarePlanInternal, SimplifiedCarePlan, Grading } from '../../../types/envelope';

// CarePlanPage imports heavy dependencies — mock them all so the module loads cleanly.
vi.mock('../../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('../../../api/apiClient', () => ({
  authenticatedFetch: vi.fn(),
}));

vi.mock('../../../utils/logger', () => ({
  logger: { setSessionId: vi.fn(), info: vi.fn() },
}));

// Network-touching modules used by CarePlanPage — stub so render is hermetic.
vi.mock('../../../api/jobs', () => ({
  createCarePlanJob: vi.fn(),
  createBatchJobs: vi.fn(),
}));

vi.mock('../../../components/NavBar', () => ({
  default: () => <nav data-testid="navbar">NavBar</nav>,
}));

vi.mock('../../../components/PresetDataCard', () => ({
  default: () => <div data-testid="preset-data-card">PresetDataCard</div>,
}));

vi.mock('../../../components/ConfigurationCard', () => ({
  default: () => <div data-testid="configuration-card">ConfigurationCard</div>,
}));

// Mock useJobStatuses so we control the Map fed into the processingIds derivation.
const mockUseJobStatuses = vi.fn();
vi.mock('../../../api/useJobStatuses', () => ({
  useJobStatuses: () => mockUseJobStatuses(),
}));

// Mock Sidebar to capture the processingIds prop it receives.
const sidebarSpy = vi.fn();
vi.mock('../../../components/Sidebar', () => ({
  default: (props: { processingIds?: Set<string> }) => {
    sidebarSpy(props.processingIds);
    return <div data-testid="sidebar" />;
  },
}));

// Must import after mocks.
import CarePlanPage from '../../../pages/care-plan/CarePlanPage';

// ── Shared fixtures ──────────────────────────────────────────────────────────

function makeMetrics(): CarePlanInternal['metrics'] {
  return {
    session_id: 'sess-1',
    pipeline_version: 'v1-2',
    input_type: 'file',
    created_at: '2026-06-21T00:00:00Z',
    total_duration_ms: null,
    step_durations_ms: {},
    saved_id: null,
  };
}

function makeGrading(): Grading {
  return { entries: [], enabled: false, graded_at: null };
}

function makeCarePlan(): SimplifiedCarePlan {
  return {
    doc_type: 'care_plan',
    urgency: 'normal',
    version: '1.2',
    summary: '',
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

function makeOutput(input: CarePlanInternal['input']): CarePlanInternal {
  return {
    metrics: makeMetrics(),
    input,
    grading: makeGrading(),
    care_plan: makeCarePlan(),
  };
}

// ── outputHasInputPdf ────────────────────────────────────────────────────────

describe('outputHasInputPdf', () => {
  it('returns true when mode=file and pdf_gcs_url is a non-null string', () => {
    const output = makeOutput({
      mode: 'file',
      files: [],
      pdf_gcs_url: 'gs://bucket/path/to.pdf',
    });
    expect(outputHasInputPdf(output)).toBe(true);
  });

  it('returns false when mode=file but pdf_gcs_url is null', () => {
    const output = makeOutput({
      mode: 'file',
      files: [],
      pdf_gcs_url: null,
    });
    expect(outputHasInputPdf(output)).toBe(false);
  });

  it('returns false when mode=text (never a PDF)', () => {
    const output = makeOutput({ mode: 'text', text: 'some text' });
    expect(outputHasInputPdf(output)).toBe(false);
  });

  it('returns false when mode=doc_id', () => {
    const output = makeOutput({ mode: 'doc_id', doc_id: 'doc-abc' });
    expect(outputHasInputPdf(output)).toBe(false);
  });

  it('returns false when mode=batch_dataset', () => {
    const output = makeOutput({
      mode: 'batch_dataset',
      text: 'note',
      dataset_group: 'g',
      dataset_input: 'i',
      selected_files: [],
      batch_group_id: 'bg-1',
    });
    expect(outputHasInputPdf(output)).toBe(false);
  });
});

// ── outputHasInputText ───────────────────────────────────────────────────────

describe('outputHasInputText', () => {
  it('returns true when mode=text and text is non-empty', () => {
    const output = makeOutput({ mode: 'text', text: 'Patient note content' });
    expect(outputHasInputText(output)).toBe(true);
  });

  it('returns true when mode=batch_dataset and text is non-empty', () => {
    const output = makeOutput({
      mode: 'batch_dataset',
      text: 'Batch patient note',
      dataset_group: 'group-A',
      dataset_input: 'input-1',
      selected_files: [],
      batch_group_id: 'bg-2',
    });
    expect(outputHasInputText(output)).toBe(true);
  });

  it('returns false when mode=file (file inputs never have inline text)', () => {
    const output = makeOutput({
      mode: 'file',
      files: [],
      pdf_gcs_url: 'gs://bucket/path/to.pdf',
    });
    expect(outputHasInputText(output)).toBe(false);
  });

  it('returns false when mode=text but text is an empty string', () => {
    const output = makeOutput({ mode: 'text', text: '' });
    expect(outputHasInputText(output)).toBe(false);
  });

  it('returns false when mode=text and text is null', () => {
    const output = makeOutput({ mode: 'text', text: null });
    expect(outputHasInputText(output)).toBe(false);
  });

  it('returns false when mode=doc_id', () => {
    const output = makeOutput({ mode: 'doc_id', doc_id: 'doc-xyz' });
    expect(outputHasInputText(output)).toBe(false);
  });
});

// ── processingIds wiring (Task 10.3 / Task 10.7) ─────────────────────────────

describe('CarePlanPage processingIds wiring', () => {
  it('passes a processingIds set containing only not_started/processing job ids to Sidebar', () => {
    mockUseJobStatuses.mockReturnValue({
      statuses: new Map([
        ['job-a', 'processing'],
        ['job-b', 'completed'],
        ['job-c', 'not_started'],
      ]),
    });

    render(<CarePlanPage />);

    expect(sidebarSpy).toHaveBeenCalled();
    const processingIds = sidebarSpy.mock.calls[sidebarSpy.mock.calls.length - 1][0] as Set<string>;

    expect(processingIds).toBeInstanceOf(Set);
    expect(processingIds.has('job-a')).toBe(true);
    expect(processingIds.has('job-c')).toBe(true);
    expect(processingIds.has('job-b')).toBe(false);
    expect(processingIds.size).toBe(2);
  });
});
