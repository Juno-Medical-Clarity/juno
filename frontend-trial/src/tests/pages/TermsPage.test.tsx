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
});
