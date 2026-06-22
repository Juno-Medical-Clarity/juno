import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import AlgorithmDocPage from '../../pages/docs/AlgorithmDocPage';

function renderAtSlug(slug: string) {
  return render(
    <MemoryRouter initialEntries={[`/docs/grading/${slug}`]}>
      <Routes>
        <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AlgorithmDocPage', () => {
  it('renders SMOG page without crashing', () => {
    renderAtSlug('smog');
  });

  it('renders SMOG page with SMOG content in the DOM', () => {
    renderAtSlug('smog');
    expect(document.body.innerHTML).toContain('SMOG');
  });

  it('shows not-found state for unknown slug', () => {
    renderAtSlug('unknown-slug');
    expect(screen.getByText('Not found')).toBeInTheDocument();
    expect(screen.getByText(/unknown-slug/)).toBeInTheDocument();
  });

  it('shows a back link to /docs on the not-found page', () => {
    renderAtSlug('unknown-slug');
    const link = screen.getByText('Back to Docs');
    expect(link.closest('a')).toHaveAttribute('href', '/docs');
  });

  it('shows a back link to /docs on a valid algorithm page', () => {
    renderAtSlug('smog');
    // The back link uses &larr; which renders as ← in the DOM
    const link = screen.getByText(/← Docs|Docs/);
    expect(link.closest('a')).toHaveAttribute('href', '/docs');
  });
});
