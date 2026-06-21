import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SplitView from './SplitView';

// Mock getInputPdfUrl so no real HTTP calls are made
vi.mock('../api/savedOutputs', () => ({
  getInputPdfUrl: vi.fn(),
}));

// Mock firebase so the module resolves without SDK initialisation
vi.mock('../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

import { getInputPdfUrl } from '../api/savedOutputs';
const mockedGetInputPdfUrl = getInputPdfUrl as ReturnType<typeof vi.fn>;

const noop = () => {};
const dummyContent = <div>Care Plan Content</div>;

describe('SplitView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('PDF mode (savedId provided, originalText null)', () => {
    it('calls getInputPdfUrl with the provided savedId', async () => {
      mockedGetInputPdfUrl.mockResolvedValueOnce('https://example.com/pdf-signed-url');

      render(
        <SplitView
          savedId="abc"
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      await waitFor(() => {
        expect(mockedGetInputPdfUrl).toHaveBeenCalledOnce();
        expect(mockedGetInputPdfUrl).toHaveBeenCalledWith('abc');
      });
    });

    it('renders an iframe on success and no <pre>', async () => {
      mockedGetInputPdfUrl.mockResolvedValueOnce('https://example.com/pdf-signed-url');

      render(
        <SplitView
          savedId="abc"
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTitle('Original document')).toBeInTheDocument();
      });
      // No <pre> should be rendered in PDF mode
      expect(document.querySelector('pre')).toBeNull();
    });

    it('shows panel header "Original Document" in PDF mode', async () => {
      mockedGetInputPdfUrl.mockResolvedValueOnce('https://example.com/pdf-signed-url');

      render(
        <SplitView
          savedId="abc"
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      // Panel header should say "Original Document" even while loading
      expect(screen.getByText('Original Document')).toBeInTheDocument();
      await waitFor(() => expect(mockedGetInputPdfUrl).toHaveBeenCalledOnce());
    });

    it('shows error text and no iframe when getInputPdfUrl rejects', async () => {
      mockedGetInputPdfUrl.mockRejectedValueOnce(new Error('Network failure'));

      render(
        <SplitView
          savedId="abc"
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText(/Could not load PDF: Network failure/i)).toBeInTheDocument();
      });
      expect(screen.queryByTitle('Original document')).toBeNull();
    });
  });

  describe('Text mode (savedId null, originalText provided)', () => {
    it('does NOT call getInputPdfUrl', () => {
      render(
        <SplitView
          savedId={null}
          originalText="Patient note text here"
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      expect(mockedGetInputPdfUrl).not.toHaveBeenCalled();
    });

    it('renders a <pre> element with the original text', () => {
      render(
        <SplitView
          savedId={null}
          originalText="Patient note text here"
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      const pre = document.querySelector('pre');
      expect(pre).not.toBeNull();
      expect(pre!.textContent).toBe('Patient note text here');
    });

    it('shows panel header "Original Text" in text mode', () => {
      render(
        <SplitView
          savedId={null}
          originalText="Patient note text here"
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      expect(screen.getByText('Original Text')).toBeInTheDocument();
    });

    it('does not render an iframe', () => {
      render(
        <SplitView
          savedId={null}
          originalText="Patient note text here"
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      expect(screen.queryByTitle('Original document')).toBeNull();
    });
  });

  describe('Both null (no content available)', () => {
    it('shows "No original content available." error in red', () => {
      render(
        <SplitView
          savedId={null}
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      const errorEl = screen.getByText('No original content available.');
      expect(errorEl).toBeInTheDocument();
      expect(errorEl).toHaveStyle({ color: '#DC2626' });
    });

    it('does NOT call getInputPdfUrl', () => {
      render(
        <SplitView
          savedId={null}
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      expect(mockedGetInputPdfUrl).not.toHaveBeenCalled();
    });

    it('renders no iframe and no pre', () => {
      render(
        <SplitView
          savedId={null}
          originalText={null}
          simplifiedContent={dummyContent}
          onClose={noop}
        />,
      );

      expect(screen.queryByTitle('Original document')).toBeNull();
      expect(document.querySelector('pre')).toBeNull();
    });
  });
});
