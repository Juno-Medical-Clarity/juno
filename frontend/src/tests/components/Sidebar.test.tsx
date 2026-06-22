import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Sidebar from '../../components/Sidebar';

// Stub localStorage (jsdom may not have it fully wired in all envs)
vi.stubGlobal('localStorage', {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
});

// Mock firebase to avoid real auth
vi.mock('../../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

// Mock listSavedOutputs to return a minimal fixture
vi.mock('../../api/savedOutputs', () => ({
  listSavedOutputs: vi.fn().mockResolvedValue([
    {
      id: 'item-1',
      name: 'Test Output',
      source_filename: 'test.pdf',
      created_at: '2026-06-21T10:00:00Z',
      updated_at: '2026-06-21T10:00:00Z',
      batch_group_id: null,
      status: 'done',
    },
  ]),
  renameSavedOutput: vi.fn(),
  deleteSavedOutput: vi.fn(),
}));

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides sidebar-title when collapse button is clicked', async () => {
    render(
      <Sidebar activeId={null} onSelect={() => {}} refreshTrigger={0} />
    );
    // Wait for the component to settle (listSavedOutputs resolves)
    await waitFor(() => {
      expect(screen.getByText('Saved')).toBeInTheDocument();
    }, { timeout: 3000 });
    // Click collapse
    fireEvent.click(screen.getByLabelText('Collapse sidebar'));
    // Sidebar title should be gone
    expect(screen.queryByText('Saved')).not.toBeInTheDocument();
    // Aria label should change to Expand
    expect(screen.getByLabelText('Expand sidebar')).toBeInTheDocument();
  });

  it('shows spinner and hides three-dot menu for processing items', async () => {
    render(
      <Sidebar
        activeId={null}
        onSelect={() => {}}
        refreshTrigger={0}
        processingIds={new Set(['item-1'])}
      />
    );
    // Wait for the item to appear (listSavedOutputs resolves)
    await waitFor(() => {
      expect(screen.getByLabelText('Processing')).toBeInTheDocument();
    }, { timeout: 3000 });
    // Three-dot menu button should not be visible for this item
    expect(screen.queryByText('⋯')).not.toBeInTheDocument();
  });
});
