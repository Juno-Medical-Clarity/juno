import { useEffect, useState } from 'react';
import './SplitView.css';
import { getInputPdfUrl } from '../api/savedOutputs';

interface SplitViewProps {
  savedId: string;
  simplifiedContent: React.ReactNode;
  onClose: () => void;
}

export default function SplitView({ savedId, simplifiedContent, onClose }: SplitViewProps) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInputPdfUrl(savedId)
      .then(url => { setPdfUrl(url); setLoading(false); })
      .catch(e => { setPdfError((e as Error).message); setLoading(false); });
  }, [savedId]);

  return (
    <div className="split-view-overlay">
      <div className="split-view-toolbar">
        <span className="split-view-title">Compare: Original vs Care Plan</span>
        <button className="split-view-close" onClick={onClose}>✕ Close</button>
      </div>
      <div className="split-view-panels">
        <div className="split-view-panel">
          <div className="split-view-panel-header">Original Document</div>
          {loading && <div className="split-view-loading">Loading PDF...</div>}
          {pdfError && (
            <div className="split-view-loading" style={{ color: '#DC2626' }}>
              Could not load PDF: {pdfError}
            </div>
          )}
          {pdfUrl && !loading && (
            <iframe src={pdfUrl} title="Original document" />
          )}
        </div>
        <div className="split-view-panel">
          <div className="split-view-panel-header">Care Plan</div>
          <div className="split-view-simplified">
            {simplifiedContent}
          </div>
        </div>
      </div>
    </div>
  );
}
