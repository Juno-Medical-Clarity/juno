import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TermsPage from '../../pages/TermsPage';

describe('TermsPage', () => {
  it('renders without throwing and contains a Back link to /', () => {
    render(<MemoryRouter><TermsPage /></MemoryRouter>);
    const link = screen.getByRole('link', { name: /back/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('renders the approved Terms & Conditions copy from the PRD, including the rate limit', () => {
    render(<MemoryRouter><TermsPage /></MemoryRouter>);
    expect(
      screen.getByRole('heading', { name: /terms & conditions — simplify \(trial\)/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/currently 5 per hour, subject to change without notice/i)).toBeInTheDocument();
  });
});
