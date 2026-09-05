import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../analytics/ga', () => ({ trackEvent: vi.fn() }));

// TrialPage pulls in a lot (Firebase, the whole upload/processing/result
// machine); for this test we only care that whatever TrialPage renders is
// wrapped in App's error boundary, so replace it with a component that
// throws on demand.
let trialPageShouldThrow = false;
vi.mock('../pages/TrialPage', () => ({
  default: () => {
    if (trialPageShouldThrow) throw new Error('TrialPage exploded');
    return <div>Trial page content</div>;
  },
}));

import App from '../App';

describe('App', () => {
  it('renders the route content normally when nothing throws', () => {
    trialPageShouldThrow = false;
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(screen.getByText('Trial page content')).toBeInTheDocument();
  });

  it('catches an uncaught exception from a page and shows a recoverable error, never a blank page', () => {
    trialPageShouldThrow = true;
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(<MemoryRouter><App /></MemoryRouter>);
    expect(container).not.toBeEmptyDOMElement();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start over' })).toBeInTheDocument();
    consoleErrorSpy.mockRestore();
    trialPageShouldThrow = false;
  });
});
