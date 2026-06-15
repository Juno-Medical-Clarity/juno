import '../v1_1/V1_1Page.css';
import { useCallback, useRef, useState } from 'react';
import { API_URL } from '../../api/firebase';
import { authenticatedFetch } from '../../api/apiClient';
import Sidebar from '../../components/Sidebar';
import { getSavedOutput } from '../../api/savedOutputs';
import PresetDatasetModal from './PresetDatasetModal';
import SplitView from '../../components/SplitView';
import type { AppState, AppointmentNote, InputMode, PipelineStep, StepStatus } from '../../types/simplify';
import AppointmentNoteV12View from '../../components/AppointmentNoteV12View';
import { buildPdfHtml } from '../../utils/buildPdfHtml';

const INITIAL_STEPS: PipelineStep[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input', status: 'waiting' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary', status: 'waiting' },
  { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level', status: 'waiting' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions', status: 'waiting' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow', status: 'waiting' },
];

function stepIcon(status: StepStatus): string {
  if (status === 'done') return '✓';
  if (status === 'active') return '◉';
  return '○';
}

export default function V1_2Page() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [inputMode, setInputMode] = useState<InputMode>('file');
  const [files, setFiles] = useState<File[]>([]);
  const [textInput, setTextInput] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [steps, setSteps] = useState<PipelineStep[]>(INITIAL_STEPS);
  const [result, setResult] = useState<AppointmentNote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [showPresetModal, setShowPresetModal] = useState(false);
  const [showSplitView, setShowSplitView] = useState(false);

  const handleFiles = useCallback((selectedFiles: File[]) => {
    const invalid = selectedFiles.filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase();
      return !['pdf', 'txt', 'docx'].includes(ext ?? '');
    });
    if (invalid.length > 0) {
      setError(`Unsupported file type: ${invalid.map(f => f.name).join(', ')}. Use PDF, TXT, or DOCX.`);
      return;
    }
    setError(null);
    setFiles(selectedFiles);
  }, []);

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files) handleFiles(Array.from(event.dataTransfer.files));
  };

  const updateStep = useCallback((stepId: number, status: StepStatus) => {
    setSteps(currentSteps =>
      currentSteps.map(step => (step.id === stepId ? { ...step, status } : step)),
    );
  }, []);

  const canSubmit = inputMode === 'file' ? files.length > 0 : textInput.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setError(null);
    setResult(null);
    setSteps(INITIAL_STEPS.map(step => ({ ...step, status: 'waiting' })));
    setAppState('processing');

    const formData = new FormData();
    if (inputMode === 'file') {
      files.forEach(f => formData.append('files', f));
    } else {
      formData.append('text', textInput);
    }

    abortRef.current = new AbortController();

    try {
      const response = await authenticatedFetch(`${API_URL}/simplify/v1-2`, {
        method: 'POST',
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Server error: ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (!payload || payload === '[DONE]') continue;

          try {
            const event = JSON.parse(payload) as {
              step: number | 'result';
              status?: 'active' | 'done';
              data?: AppointmentNote & { saved_id?: string };
              error?: string;
            };

            if (event.error) throw new Error(event.error);

            if (event.step === 'result' && event.data) {
              setResult(event.data);
              setAppState('result');
              if (event.data.saved_id) {
                setActiveSavedId(event.data.saved_id);
                setSidebarRefresh(r => r + 1);
              }
            } else if (typeof event.step === 'number' && event.status) {
              updateStep(event.step, event.status);
            }
          } catch {
            // Skip malformed SSE lines.
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setAppState('upload');
    }
  };

  const handleDownloadJson = () => {
    if (!result) return;

    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'simplified-document.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = () => {
    if (!result) return;
    const html = buildPdfHtml(result);
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      setError('Could not open print window. Please allow pop-ups for this site.');
      return;
    }
    printWindow.document.write(html);
    printWindow.document.close();
    setTimeout(() => printWindow.print(), 500);
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setFiles([]);
    setTextInput('');
    setSteps(INITIAL_STEPS.map(step => ({ ...step, status: 'waiting' })));
    setResult(null);
    setError(null);
    setAppState('upload');
    setActiveSavedId(null);
  };

  async function handleSelectSaved(id: string) {
    try {
      const saved = await getSavedOutput(id);
      setResult(saved.output_data as unknown as AppointmentNote);
      setActiveSavedId(id);
      setAppState('result');
    } catch {
      setError('Could not load saved output.');
    }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar
        activeId={activeSavedId}
        onSelect={handleSelectSaved}
        onNew={handleReset}
        refreshTrigger={sidebarRefresh}
      />
      <div style={{ flex: 1, marginLeft: '260px', minWidth: 0 }}>
      <div className="aurora-bg" aria-hidden="true">
        <div className="aurora-orb aurora-orb-1" />
        <div className="aurora-orb aurora-orb-2" />
        <div className="aurora-orb aurora-orb-3" />
      </div>

      <div className="page-wrapper">
        <div className="container">
          {appState === 'upload' && (
            <section className="upload-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <div className="input-tabs">
                  <button
                    className={`input-tab ${inputMode === 'file' ? 'active' : ''}`}
                    onClick={() => setInputMode('file')}
                  >
                    Upload file
                  </button>
                  <button
                    className={`input-tab ${inputMode === 'text' ? 'active' : ''}`}
                    onClick={() => setInputMode('text')}
                  >
                    Paste text
                  </button>
                </div>

                {inputMode === 'file' ? (
                  <div
                    className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
                    onDragOver={event => {
                      event.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={onDrop}
                  >
                    <input
                      type="file"
                      accept=".pdf,.txt,.docx"
                      multiple
                      onChange={e => {
                        if (e.target.files) handleFiles(Array.from(e.target.files));
                      }}
                    />
                    <div className="upload-icon">📄</div>
                    {files.length > 0 ? (
                      <div>
                        {files.map(f => (
                          <p key={f.name} className="upload-file-name">✓ {f.name}</p>
                        ))}
                      </div>
                    ) : (
                      <>
                        <p className="upload-title">Drag & drop your document(s) here</p>
                        <p className="upload-hint">PDF, TXT, or DOCX · Multiple files = one combined process</p>
                      </>
                    )}
                  </div>
                ) : (
                  <textarea
                    className="text-input-area"
                    placeholder="Paste your provider note, appointment summary, or SOAP note here..."
                    value={textInput}
                    onChange={event => setTextInput(event.target.value)}
                  />
                )}

                {error && <div className="error-box">⚠ {error}</div>}

                <button className="cta-btn" disabled={!canSubmit} onClick={handleSubmit}>
                  Simplify My Note →
                </button>
                <div style={{ textAlign: 'center', marginTop: '12px' }}>
                  <button
                    onClick={() => setShowPresetModal(true)}
                    style={{
                      background: 'none', border: 'none', color: 'var(--text-secondary)',
                      fontSize: '0.8rem', cursor: 'pointer', fontFamily: 'Inter, sans-serif',
                      textDecoration: 'underline',
                    }}
                  >
                    Or run a preset dataset (multiple processes)
                  </button>
                </div>
              </div>
            </section>
          )}

          {appState === 'processing' && (
            <section className="progress-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <p className="section-title">Simplifying your note...</p>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '-8px', marginBottom: '16px' }}>
                  Finding medical terms, rewriting to plain language, and organizing your care plan.
                </p>
                <div className="step-list">
                  {steps.map(step => (
                    <div className="step-item" key={step.id}>
                      <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
                      <div className="step-content">
                        <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>{step.label}</p>
                        <p className="step-desc">{step.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                <h2 className="result-title">Your Simplified Note</h2>
                <span className="deleted-note">🔒 Deleted from servers</span>
                {activeSavedId && (
                  <button
                    onClick={() => setShowSplitView(true)}
                    style={{
                      background: 'none', border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-pill)', padding: '6px 14px',
                      fontSize: '0.8rem', cursor: 'pointer',
                      color: 'var(--text-secondary)', fontFamily: 'Inter, sans-serif',
                    }}
                  >
                    Show Original
                  </button>
                )}
              </div>

              <AppointmentNoteV12View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button
                  onClick={handleReset}
                  style={{
                    background: 'none',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-pill)',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                    padding: '8px 20px',
                    cursor: 'pointer',
                    fontFamily: 'Inter, sans-serif',
                  }}
                >
                  ← Simplify another note
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download Report
            </button>
          </div>
        </div>
      )}
      </div>
      {showPresetModal && (
        <PresetDatasetModal
          onClose={() => setShowPresetModal(false)}
          onProcessComplete={(_savedId, _name) => {
            setSidebarRefresh(r => r + 1);
          }}
        />
      )}
      {showSplitView && result && activeSavedId && (
        <SplitView
          savedId={activeSavedId}
          simplifiedContent={<AppointmentNoteV12View result={result} />}
          onClose={() => setShowSplitView(false)}
        />
      )}
    </div>
  );
}
