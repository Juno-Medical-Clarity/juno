import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../analytics/ga', () => ({ trackEvent: vi.fn() }));

import ProcessingScreen from '../../components/ProcessingScreen';
import type { TrialJobDoc } from '../../hooks/useTrialJobSnapshot';

const baseJobDoc: TrialJobDoc = {
  status: 'processing', stage: 3, output_data: null, error_data: null, name: '',
};

describe('ProcessingScreen', () => {
  it('renders steps 1-2 done, step 3 active, steps 4-5 waiting for stage=3', () => {
    render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={null} />);
    const nodes = document.querySelectorAll('.step-node');
    expect(nodes[0].className).toContain('done');
    expect(nodes[1].className).toContain('done');
    expect(nodes[2].className).toContain('active');
    expect(nodes[3].className).toContain('waiting');
    expect(nodes[4].className).toContain('waiting');
    expect(screen.getByText('Simplifying language')).toBeInTheDocument();
  });

  it('renders the reconnect message instead of the step list when snapshotError is set', () => {
    render(<ProcessingScreen jobDoc={baseJobDoc} snapshotError={new Error('boom')} />);
    expect(screen.getByText(/lost connection/i)).toBeInTheDocument();
    expect(document.querySelector('.step-list')).toBeNull();
  });
});
