import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ErrorBoundary } from '../ErrorBoundary';

const ThrowOnRender = (): never => {
  throw new Error('Test render error');
};

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('ErrorBoundary', () => {
  it('renders fallback on render error', () => {
    render(
      <ErrorBoundary fallback={<div>fallback content</div>}>
        <ThrowOnRender />
      </ErrorBoundary>
    );
    expect(screen.getByText('fallback content')).toBeInTheDocument();
  });

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>child content</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('child content')).toBeInTheDocument();
  });
});
