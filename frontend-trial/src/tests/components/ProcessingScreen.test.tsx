import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

import ProcessingScreen from '../../components/ProcessingScreen';
import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

const baseJobDoc: TrialJobDoc = {
  status: 'processing', stage: 3, output_data: null, error_data: null, name: '',
};

describe('ProcessingScreen', () => {
  it('renders steps 1-2 done, step 3 active, steps 4-5 waiting for stage=3', () => {
    render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={null} jobExists={true} onRestart={vi.fn()} />);
    const nodes = document.querySelectorAll('.step-node');
    expect(nodes[0].className).toContain('done');
    expect(nodes[1].className).toContain('done');
    expect(nodes[2].className).toContain('active');
    expect(nodes[3].className).toContain('waiting');
    expect(nodes[4].className).toContain('waiting');
    expect(screen.getByText('Simplifying language')).toBeInTheDocument();
  });

  it('renders the normal step list (not a terminal state) while exists is still null (not yet loaded)', () => {
    render(<ProcessingScreen jobDoc={null} snapshotError={null} jobExists={null} onRestart={vi.fn()} />);
    expect(document.querySelector('.step-list')).not.toBeNull();
    expect(screen.queryByText(/session ended/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/lost connection/i)).not.toBeInTheDocument();
  });

  it('renders the reconnect message and a "Start over" button when snapshotError is set', async () => {
    const onRestart = vi.fn();
    const user = userEvent.setup();
    render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={new Error('boom')} jobExists={null} onRestart={onRestart} />);
    expect(screen.getByText(/lost connection/i)).toBeInTheDocument();
    expect(document.querySelector('.step-list')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Start over' }));
    expect(onRestart).toHaveBeenCalledOnce();
  });

  it('renders a "session ended" terminal message and a "Start over" button when the job doc is confirmed missing', async () => {
    const onRestart = vi.fn();
    const user = userEvent.setup();
    render(<ProcessingScreen jobDoc={null} snapshotError={null} jobExists={false} onRestart={onRestart} />);
    expect(screen.getByText(/session ended/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing was saved/i)).toBeInTheDocument();
    expect(document.querySelector('.step-list')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Start over' }));
    expect(onRestart).toHaveBeenCalledOnce();
  });

  it('prioritizes the "session ended" state over a stale snapshotError when the doc is confirmed missing', () => {
    render(<ProcessingScreen jobDoc={null} snapshotError={new Error('boom')} jobExists={false} onRestart={vi.fn()} />);
    expect(screen.getByText(/session ended/i)).toBeInTheDocument();
    expect(screen.queryByText(/lost connection/i)).not.toBeInTheDocument();
  });
});
