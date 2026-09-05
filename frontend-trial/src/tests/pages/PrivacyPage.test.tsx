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
});
