import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PrivacyPage from '../../pages/PrivacyPage';

describe('PrivacyPage', () => {
  it('renders without throwing and contains a Back link to /', () => {
    render(<MemoryRouter><PrivacyPage /></MemoryRouter>);
    const link = screen.getByRole('link', { name: /back/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('renders the approved Privacy Policy copy from the PRD', () => {
    render(<MemoryRouter><PrivacyPage /></MemoryRouter>);
    expect(
      screen.getByRole('heading', { name: /privacy policy — simplify \(trial\)/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/do not upload real, identifiable patient health information \(phi\)/i)
    ).toBeInTheDocument();
  });
});
