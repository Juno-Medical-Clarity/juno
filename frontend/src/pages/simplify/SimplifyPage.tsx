import '../v1_1/V1_1Page.css';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { API_URL } from '../../api/firebase';
import { authenticatedFetch } from '../../api/apiClient';
import { runBatch } from '../../api/datasets';
import Sidebar from '../../components/Sidebar';
import { getSavedOutput } from '../../api/savedOutputs';
import SplitView from '../../components/SplitView';
import type { AppState, InputMode, PipelineStep, StepStatus } from '../../types/simplify';
import type { SimplifyOutput } from '../../types/envelope';
import type { BatchDatasetSelection } from '../../types/datasets';
import { normalizeSimplifyOutput } from '../../utils/normalizeOutput';
import AppointmentNoteV12View from '../../components/AppointmentNoteV12View';
import { buildPdfHtml } from '../../utils/buildPdfHtml';
import NavBar from '../../components/NavBar';
import ConfigurationCard from '../../components/ConfigurationCard';
import OutputGradingCard from '../../components/OutputGradingCard';
import PresetDataCard from '../../components/PresetDataCard';
import { SIMPLIFY_API_PATH, DEFAULT_VERSION, VERSIONS } from '../../config';
import type { VersionRouteState } from '../../router';

const INITIAL_STEPS: PipelineStep[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input', status: 'waiting' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary', status: 'waiting' },
  { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level', status: 'waiting' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions', status: 'waiting' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow', status: 'waiting' },
];

interface BatchProgress {
  group: string;
  input: string;
  index: number;
  total: number;
  status: 'active' | 'pipeline' | 'done' | 'error';
  error?: string;
}

function stepIcon(status: StepStatus): string {
  if (status === 'done') return '✓';
  if (status === 'active') return '◉';
  return '○';
}

function resetSteps(): PipelineStep[] {
  return INITIAL_STEPS.map(step => ({ ...step, status: 'waiting' }));
}

function outputHasInputPdf(output: SimplifyOutput): boolean {
  return output.input.mode === 'file' && output.input.files.some(file => (
    file.content_type === 'application/pdf' || file.filename.toLowerCase().endsWith('.pdf')
  ));
}

export default function SimplifyPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [appState, setAppState] = useState<AppState>('upload');
  const [inputMode, setInputMode] = useState<InputMode>('file');
  const [selectedVersion, setSelectedVersion] = useState(DEFAULT_VERSION);
  const [gradingEnabled, setGradingEnabled] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [textInput, setTextInput] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [steps, setSteps] = useState<PipelineStep[]>(INITIAL_STEPS);
  const [result, setResult] = useState<SimplifyOutput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null);
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [showSplitView, setShowSplitView] = useState(false);
  const [presetDataSelection, setPresetDataSelection] = useState<BatchDatasetSelection[]>([]);
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);
  const [batchOutputs, setBatchOutputs] = useState<SimplifyOutput[]>([]);
  const [batchGroupIds, setBatchGroupIds] = useState<Record<string, string>>({});
  const [selectedBatchIndex, setSelectedBatchIndex] = useState<number | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const versionParam = params.get('version');
    if (versionParam && VERSIONS.some(v => v.id === versionParam)) {
      setSelectedVersion(versionParam);
      navigate(location.pathname, { replace: true, state: location.state });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once on mount

  useEffect(() => {
    const output = (location.state as VersionRouteState | null)?.output;
    if (!output) return;

    setResult(output);
    setBatchOutputs([]);
    setBatchGroupIds({});
    setSelectedBatchIndex(null);
    setAppState('result');
    const savedId = output.metrics.saved_id;
    if (savedId) {
      setActiveSavedId(savedId);
      setSidebarRefresh(r => r + 1);
    }
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

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

  const hasSingleRunInput = inputMode === 'file' ? files.length > 0 : textInput.trim().length > 0;
  const hasPresetDataSelection = presetDataSelection.length > 0;
  const canSubmit = hasPresetDataSelection || hasSingleRunInput;
  const presetDataSelectionCount = presetDataSelection.length;

  const handleVersionChange = (versionId: string) => {
    setSelectedVersion(versionId);
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setError(null);
    setResult(null);
    setBatchOutputs([]);
    setBatchGroupIds({});
    setSelectedBatchIndex(null);
    setBatchProgress(null);
    setActiveSavedId(null);
    setShowSplitView(false);
    setSteps(resetSteps());
    setAppState('processing');

    abortRef.current = new AbortController();

    if (hasPresetDataSelection) {
      try {
        const response = await runBatch(
          presetDataSelection,
          selectedVersion,
          gradingEnabled,
          abortRef.current.signal,
        );

        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || `Server error: ${response.status}`);
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentBatchInputKey: string | null = null;

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

            let event: {
              step: 'batch_progress' | 'batch_result' | 'error';
              group?: string;
              input?: string;
              index?: number;
              total?: number;
              status?: 'active' | 'pipeline' | 'done' | 'error';
              event?: { step?: number | string; status?: StepStatus };
              data?: { batch_group_ids?: Record<string, string>; outputs?: unknown[] };
              error?: string;
            };
            try {
              event = JSON.parse(payload);
            } catch {
              continue;
            }

            if (event.step === 'error') {
              throw new Error(event.error || 'Batch processing failed.');
            }

            if (event.step === 'batch_progress') {
              if (event.group && event.input && event.index && event.total && event.status) {
                const inputKey = `${event.group}/${event.input}`;
                if (event.status === 'active' || inputKey !== currentBatchInputKey) {
                  currentBatchInputKey = inputKey;
                  setSteps(resetSteps());
                }
                setBatchProgress({
                  group: event.group,
                  input: event.input,
                  index: event.index,
                  total: event.total,
                  status: event.status,
                  error: event.error,
                });
              }

              if (event.event && typeof event.event.step === 'number' && event.event.status) {
                updateStep(event.event.step, event.event.status);
              }
              continue;
            }

            if (event.step === 'batch_result') {
              const outputs = (event.data?.outputs ?? []).map(output => normalizeSimplifyOutput(output));
              setBatchOutputs(outputs);
              setBatchGroupIds(event.data?.batch_group_ids ?? {});
              setSelectedBatchIndex(outputs.length > 0 ? 0 : null);
              setResult(outputs[0] ?? null);
              setAppState('result');
              const savedId = outputs[0]?.metrics.saved_id;
              setActiveSavedId(savedId ?? null);
              setSidebarRefresh(r => r + 1);
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
        setAppState('upload');
      }
      return;
    }

    const formData = new FormData();
    if (inputMode === 'file') {
      files.forEach(f => formData.append('files', f));
    } else {
      formData.append('text', textInput);
    }
    formData.append('version', selectedVersion);
    formData.append('grading_enabled', gradingEnabled.toString());

    try {
      const response = await authenticatedFetch(`${API_URL}${SIMPLIFY_API_PATH}`, {
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
              data?: unknown;
              error?: string;
            };

            if (event.error) throw new Error(event.error);

            if (event.step === 'result' && event.data) {
              const normalized = normalizeSimplifyOutput(event.data);
              setBatchOutputs([]);
              setBatchGroupIds({});
              setSelectedBatchIndex(null);
              setResult(normalized);
              setAppState('result');
              const savedId = normalized.metrics.saved_id;
              if (savedId) {
                setActiveSavedId(savedId);
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
    const html = buildPdfHtml(result.simplified_care_plan);
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
    setSteps(resetSteps());
    setResult(null);
    setBatchOutputs([]);
    setBatchGroupIds({});
    setSelectedBatchIndex(null);
    setBatchProgress(null);
    setError(null);
    setAppState('upload');
    setActiveSavedId(null);
    setShowSplitView(false);
  };

  async function handleSelectSaved(id: string) {
    try {
      const saved = await getSavedOutput(id);
      const normalized = normalizeSimplifyOutput(saved.output_data);
      setResult(normalized);
      setBatchOutputs([]);
      setBatchGroupIds({});
      setSelectedBatchIndex(null);
      setActiveSavedId(id);
      setAppState('result');
    } catch {
      setError('Could not load saved output.');
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <NavBar onNew={handleReset} />
      <div style={{ display: 'flex', flex: 1 }}>
      <Sidebar
        activeId={activeSavedId}
        onSelect={handleSelectSaved}
        onNew={handleReset}
        refreshTrigger={sidebarRefresh}
      />
      <div style={{ flex: 1, marginLeft: '260px', minWidth: 0, paddingTop: '48px' }}>
      <div className="aurora-bg" aria-hidden="true">
        <div className="aurora-orb aurora-orb-1" />
        <div className="aurora-orb aurora-orb-2" />
        <div className="aurora-orb aurora-orb-3" />
      </div>

      <div className="page-wrapper">
        <div className="container">
          {appState === 'upload' && (
            <section className="upload-section" data-preset-selection-count={presetDataSelectionCount}>
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
              </div>
              <PresetDataCard onSelectionChange={setPresetDataSelection} />
              <ConfigurationCard
                version={selectedVersion}
                onVersionChange={handleVersionChange}
                gradingEnabled={gradingEnabled}
                onGradingEnabledChange={setGradingEnabled}
              />
            </section>
          )}

          {appState === 'processing' && (
            <section className="progress-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <p className="section-title">Simplifying your note...</p>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '-8px', marginBottom: '16px' }}>
                  Finding medical terms, rewriting to plain language, and organizing your care plan.
                </p>
                {batchProgress && (
                  <div style={{
                    marginBottom: '20px',
                    padding: '12px 14px',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                  }}>
                    <strong style={{ color: 'var(--text-primary)' }}>
                      Input {batchProgress.index} of {batchProgress.total}
                    </strong>
                    <span> · {batchProgress.group} / {batchProgress.input}</span>
                    {batchProgress.status === 'error' && batchProgress.error && (
                      <div style={{ color: 'var(--error, #DC2626)', marginTop: '6px' }}>{batchProgress.error}</div>
                    )}
                  </div>
                )}
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
                {activeSavedId && result && outputHasInputPdf(result) && (
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

              {batchOutputs.length > 0 && (
                <div className="glass-card" style={{ padding: '20px', marginBottom: '24px' }}>
                  <p style={{ margin: 0, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {batchOutputs.length} report{batchOutputs.length === 1 ? '' : 's'} generated
                  </p>
                  {Object.keys(batchGroupIds).length > 0 && (
                    <p style={{ margin: '6px 0 16px', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                      Batch groups: {Object.entries(batchGroupIds).map(([group, id]) => `${group}: ${id}`).join(', ')}
                    </p>
                  )}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {batchOutputs.map((output, index) => {
                      const savedId = output.metrics.saved_id;
                      const isActive = selectedBatchIndex === index;
                      return (
                        <button
                          key={savedId ?? index}
                          type="button"
                          onClick={() => {
                            setSelectedBatchIndex(index);
                            setResult(output);
                            setActiveSavedId(savedId ?? null);
                            setShowSplitView(false);
                          }}
                          style={{
                            border: isActive ? '1px solid var(--accent-violet)' : '1px solid var(--border)',
                            background: isActive ? 'rgba(124, 58, 237, 0.1)' : 'transparent',
                            borderRadius: 'var(--radius-pill)',
                            color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                            cursor: 'pointer',
                            fontFamily: 'Inter, sans-serif',
                            fontSize: '0.8rem',
                            padding: '7px 14px',
                          }}
                        >
                          Report {index + 1}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <AppointmentNoteV12View result={result.simplified_care_plan} grading={result.grading} />

              <OutputGradingCard
                output={result}
                onGraded={(newGrading) => setResult(prev => prev ? { ...prev, grading: newGrading } : prev)}
              />

              {result.metrics.session_id && (
                <div style={{ marginTop: '24px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                  Request ID: {result.metrics.session_id}
                </div>
              )}

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
            </section>
          )}
        </div>
      </div>
      </div>
      </div>
      {showSplitView && result && activeSavedId && (
        <SplitView
          savedId={activeSavedId}
          simplifiedContent={<AppointmentNoteV12View result={result.simplified_care_plan} grading={result.grading} />}
          onClose={() => setShowSplitView(false)}
        />
      )}
    </div>
  );
}
