import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PresetDataPanel from '../../components/PresetDataCard/PresetDataPanel';
import { getDatasetFileContent } from '../../api/datasets';

vi.mock('../../api/datasets', () => ({
  getDatasetFileContent: vi.fn(),
}));

vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

const mockedGetDatasetFileContent = getDatasetFileContent as ReturnType<typeof vi.fn>;

const testDataset = {
  group: 'group-a',
  inputs: ['input-1', 'input-2', 'input-3'],
  files: ['file.pdf', 'file.txt'],
};
const emptySelection = { inputs: new Set<string>(), files: new Set<string>() };

describe('PresetDataPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders appointment list from dataset.inputs', () => {
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={() => {}}
      />
    );
    expect(screen.getByText('input-1')).toBeInTheDocument();
    expect(screen.getByText('input-2')).toBeInTheDocument();
    expect(screen.getByText('input-3')).toBeInTheDocument();
  });

  it('Select All checkbox is unchecked when selection is empty', () => {
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={() => {}}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /Select All/i });
    expect(checkbox).not.toBeChecked();
  });

  it('Select All checkbox is indeterminate when some inputs checked', () => {
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /Select All/i }) as HTMLInputElement;
    expect(checkbox.indeterminate).toBe(true);
  });

  it('Select All checkbox is checked when all inputs and files checked', () => {
    const selection = {
      inputs: new Set(['input-1', 'input-2', 'input-3']),
      files: new Set(['file.pdf', 'file.txt']),
    };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /Select All/i }) as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    expect(checkbox.indeterminate).toBe(false);
  });

  it('clicking Select All when unchecked calls onSelectionChange with all inputs and files', async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={onSelectionChange}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /Select All/i });
    await user.click(checkbox);
    expect(onSelectionChange).toHaveBeenCalledWith('group-a', {
      inputs: new Set(['input-1', 'input-2', 'input-3']),
      files: new Set(['file.pdf', 'file.txt']),
    });
  });

  it('clicking Select All when checked calls onSelectionChange with empty sets', async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    const fullSelection = {
      inputs: new Set(['input-1', 'input-2', 'input-3']),
      files: new Set(['file.pdf', 'file.txt']),
    };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={fullSelection}
        onSelectionChange={onSelectionChange}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /Select All/i });
    await user.click(checkbox);
    expect(onSelectionChange).toHaveBeenCalledWith('group-a', {
      inputs: new Set(),
      files: new Set(),
    });
  });

  it('clicking individual appointment toggles it', async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={onSelectionChange}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: 'input-1' });
    await user.click(checkbox);
    expect(onSelectionChange).toHaveBeenCalledOnce();
    const [group, newSelection] = onSelectionChange.mock.calls[0] as [string, { inputs: Set<string>; files: Set<string> }];
    expect(group).toBe('group-a');
    expect(newSelection.inputs.has('input-1')).toBe(true);
  });

  it('clicking individual file toggles it', async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={onSelectionChange}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: 'file.pdf' });
    await user.click(checkbox);
    expect(onSelectionChange).toHaveBeenCalledOnce();
    const [group, newSelection] = onSelectionChange.mock.calls[0] as [string, { inputs: Set<string>; files: Set<string> }];
    expect(group).toBe('group-a');
    expect(newSelection.files.has('file.pdf')).toBe(true);
  });

  it('clicking Preview button calls getDatasetFileContent with first selected input', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockResolvedValue({ content: 'test content' });
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    // Click preview button next to file.pdf (first Preview button)
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    expect(mockedGetDatasetFileContent).toHaveBeenCalledWith('group-a', 'input-1', 'file.pdf');
  });

  it('Preview shows Loading preview... while fetch pending', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockReturnValue(new Promise(() => {}));
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    expect(screen.getByText('Loading preview...')).toBeInTheDocument();
  });

  it('Preview shows content on success', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockResolvedValue({ content: 'hello world' });
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    await waitFor(() => {
      expect(screen.getByText('hello world')).toBeInTheDocument();
    });
  });

  it('Preview shows error message on failure', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockRejectedValue(new Error('fetch failed'));
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    await waitFor(() => {
      expect(screen.getByText('fetch failed')).toBeInTheDocument();
    });
  });

  it('Close button on preview sets preview to null', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockResolvedValue({ content: 'hello world' });
    const selection = { inputs: new Set(['input-1']), files: new Set<string>() };
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={selection}
        onSelectionChange={() => {}}
      />
    );
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    await waitFor(() => {
      expect(screen.getByText('hello world')).toBeInTheDocument();
    });
    const closeButton = screen.getByRole('button', { name: 'Close' });
    await user.click(closeButton);
    expect(screen.queryByText('hello world')).toBeNull();
  });

  it('Preview input fallback: if no inputs selected, uses dataset.inputs[0]', async () => {
    const user = userEvent.setup();
    mockedGetDatasetFileContent.mockResolvedValue({ content: 'fallback' });
    render(
      <PresetDataPanel
        dataset={testDataset}
        selection={emptySelection}
        onSelectionChange={() => {}}
      />
    );
    const previewButtons = screen.getAllByRole('button', { name: 'Preview' });
    await user.click(previewButtons[0]);
    expect(mockedGetDatasetFileContent).toHaveBeenCalledWith('group-a', 'input-1', 'file.pdf');
  });
});
