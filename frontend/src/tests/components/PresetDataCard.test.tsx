import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PresetDataCard from '../../components/PresetDataCard/PresetDataCard';
import { listDatasets } from '../../api/datasets';

vi.mock('../../api/datasets', () => ({
  listDatasets: vi.fn(),
  getDatasetFileContent: vi.fn(),
}));

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

// Mock PresetDataPanel so card-level tests don't deal with panel internals
vi.mock('../../components/PresetDataCard/PresetDataPanel', () => ({
  default: ({ dataset }: { dataset: { group: string } }) => (
    <div data-testid="preset-panel" data-group={dataset.group} />
  ),
}));

const mockDatasets = [
  { group: 'group-a', inputs: ['i1', 'i2'], files: ['f1.pdf'] },
  { group: 'group-b', inputs: ['i3'],       files: ['f2.txt'] },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PresetDataCard', () => {
  it('card renders header with Choose toggle; body hidden by default', () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(<PresetDataCard onSelectionChange={() => {}} />);

    expect(screen.getByText('Choose')).toBeInTheDocument();
    expect(document.querySelector('.preset-data-card-body')).toBeNull();
  });

  it('clicking Choose expands body; shows loading state initially', async () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    const user = userEvent.setup();
    render(<PresetDataCard onSelectionChange={() => {}} />);

    await user.click(screen.getByText('Choose'));

    expect(screen.getByText('Loading preset data...')).toBeInTheDocument();
  });

  it('after datasets load left sidebar renders one tab per group', async () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue(mockDatasets);

    const user = userEvent.setup();
    render(<PresetDataCard onSelectionChange={() => {}} />);

    await user.click(screen.getByText('Choose'));

    await waitFor(() => {
      expect(document.querySelectorAll('.preset-panel-tab')).toHaveLength(2);
    });
  });

  it('first dataset tab is auto-selected; right panel renders', async () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue(mockDatasets);

    const user = userEvent.setup();
    render(<PresetDataCard onSelectionChange={() => {}} />);

    await user.click(screen.getByText('Choose'));

    await waitFor(() => {
      const tabs = document.querySelectorAll('.preset-panel-tab');
      expect(tabs).toHaveLength(2);
      expect(tabs[0]).toHaveClass('active');
    });

    expect(screen.getByTestId('preset-panel')).toBeInTheDocument();
  });

  it('clicking second tab switches panel to second dataset', async () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue(mockDatasets);

    const user = userEvent.setup();
    render(<PresetDataCard onSelectionChange={() => {}} />);

    await user.click(screen.getByText('Choose'));

    await waitFor(() => {
      expect(document.querySelectorAll('.preset-panel-tab')).toHaveLength(2);
    });

    const tabs = document.querySelectorAll('.preset-panel-tab');
    await user.click(tabs[1]);

    expect(tabs[1]).toHaveClass('active');
    expect(tabs[0]).not.toHaveClass('active');
  });

  it('tab meta shows 0/N when nothing selected', async () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue(mockDatasets);

    const user = userEvent.setup();
    render(<PresetDataCard onSelectionChange={() => {}} />);

    await user.click(screen.getByText('Choose'));

    await waitFor(() => {
      expect(document.querySelectorAll('.preset-panel-tab')).toHaveLength(2);
    });

    // group-a has 2 inputs, nothing selected => 0/2
    expect(screen.getByText('0/2')).toBeInTheDocument();
  });

  it('header summary shows default text when nothing selected', () => {
    (listDatasets as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(<PresetDataCard onSelectionChange={() => {}} />);

    expect(screen.getByText('Select repository datasets for batch runs.')).toBeInTheDocument();
  });
});
