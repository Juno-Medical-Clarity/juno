import { useEffect, useState } from 'react';
import './SplitView.css';
import { getInputPdfUrl } from '../../api/savedOutputs';

interface SplitViewProps {
  savedId: string | null;          // non-null → fetch signed URL for PDF iframe
  originalText: string | null;     // non-null → render inline text (no API call)
  simplifiedContent: React.ReactNode;
  onClose: () => void;
}

export default function SplitView({ savedId, originalText, simplifiedContent, onClose }: SplitViewProps) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [loading, setLoading] = useState(savedId != null);

  useEffect(() => {
    if (!savedId) return;
    setLoading(true);
    getInputPdfUrl(savedId)
      .then(url => { setPdfUrl(url); setLoading(false); })
      .catch(e => { setPdfError((e as Error).message); setLoading(false); });
  }, [savedId]);

  const panelTitle = savedId ? 'Original Document' : 'Original Text';

  return (
    <div className="split-view-overlay">
      <div className="split-view-toolbar">
        <span className="split-view-title">Compare: Original vs Care Plan</span>
        <button className="split-view-close" onClick={onClose}>✕ Close</button>
      </div>
      <div className="split-view-panels">
        <div className="split-view-panel split-view-panel--original">
          <div className="split-view-panel-header">{panelTitle}</div>

          {/* PDF mode */}
          {savedId && loading && <div className="split-view-loading">Loading PDF...</div>}
          {savedId && pdfError && (
            <div className="split-view-loading" style={{ color: '#DC2626' }}>
              Could not load PDF: {pdfError}
            </div>
          )}
          {savedId && pdfUrl && !loading && (
            <iframe src={pdfUrl} title="Original document" />
          )}

          {/* Text mode */}
          {!savedId && originalText && (
            <div className="split-view-text-content">
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {originalText}
              </pre>
            </div>
          )}

          {/* Error: neither mode available */}
          {!savedId && !originalText && (
            <div className="split-view-loading" style={{ color: '#DC2626' }}>
              No original content available.
            </div>
          )}
        </div>

        <div className="split-view-panel">
          <div className="split-view-panel-header">Care Plan</div>
          <div className="split-view-simplified">{simplifiedContent}</div>
        </div>
      </div>
    </div>
  );
}
