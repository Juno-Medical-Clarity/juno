import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DocsPage from '../../pages/docs/DocsPage';

function renderDocsPage() {
  return render(
    <MemoryRouter>
      <DocsPage />
    </MemoryRouter>
  );
}

describe('DocsPage', () => {
  it('renders without crashing', () => {
    renderDocsPage();
  });

  it('shows Grading section heading', () => {
    renderDocsPage();
    expect(screen.getByText('Grading')).toBeInTheDocument();
  });

  it('shows all six algorithm names as links in default view', () => {
    renderDocsPage();
    expect(screen.getByText('SMOG')).toBeInTheDocument();
    expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
    expect(screen.getByText('Dale-Chall')).toBeInTheDocument();
    expect(screen.getByText('PEMAT')).toBeInTheDocument();
    expect(screen.getByText('SAM')).toBeInTheDocument();
    expect(screen.getByText('CDC Clear Communication Index')).toBeInTheDocument();
  });

  it('filters to a single result when query matches one algorithm name', () => {
    renderDocsPage();
    const input = screen.getByPlaceholderText('Search docs...');
    fireEvent.change(input, { target: { value: 'smog' } });
    expect(screen.getByText('SMOG')).toBeInTheDocument();
    expect(screen.queryByText('Flesch-Kincaid')).not.toBeInTheDocument();
  });

  it('shows no-results message when query has no matches', () => {
    renderDocsPage();
    const input = screen.getByPlaceholderText('Search docs...');
    fireEvent.change(input, { target: { value: 'zzznomatch999' } });
    expect(screen.getByText(/No results/i)).toBeInTheDocument();
  });

  it('restores section view when query is cleared', () => {
    renderDocsPage();
    const input = screen.getByPlaceholderText('Search docs...');
    fireEvent.change(input, { target: { value: 'smog' } });
    fireEvent.change(input, { target: { value: '' } });
    expect(screen.getByText('Grading')).toBeInTheDocument();
    expect(screen.getByText('Flesch-Kincaid')).toBeInTheDocument();
  });
});
