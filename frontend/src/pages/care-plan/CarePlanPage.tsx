import './CarePlanPage.css';
import { useCallback, useState } from 'react';
import type { DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '../../components/Sidebar';
import type { InputMode, PipelineStep } from '../../types/carePlan';
import type { CarePlanInternal } from '../../types/envelope';
import NavBar from '../../components/NavBar';
import ConfigurationCard from '../../components/ConfigurationCard';
import PresetDataCard from '../../components/PresetDataCard';
import { DEFAULT_VERSION, carePlanPagePath } from '../../constants';
import type { BatchDatasetSelection } from '../../types/datasets';
import { createCarePlanJob, createBatchJobs } from '../../api/jobs';

export const INITIAL_STEPS: PipelineStep[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input', status: 'waiting' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary', status: 'waiting' },
  { id: 3, label: 'Rewriting to plain language', description: 'Rewriting to a 6th-grade reading level', status: 'waiting' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions', status: 'waiting' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow', status: 'waiting' },
];

export function outputHasInputPdf(output: CarePlanInternal): boolean {
  return output.input.mode === 'file' && output.input.pdf_gcs_url != null;
}

export function outputHasInputText(output: CarePlanInternal): boolean {
  return (output.input.mode === 'text' || output.input.mode === 'batch_dataset')
    && typeof output.input.text === 'string'
    && output.input.text.length > 0;
}

export default function CarePlanPage() {
  const navigate = useNavigate();
  const [inputMode, setInputMode] = useState<InputMode>('file');
  const selectedVersion = DEFAULT_VERSION;
  const [gradingEnabled, setGradingEnabled] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [textInput, setTextInput] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [presetDataSelection, setPresetDataSelection] = useState<BatchDatasetSelection[]>([]);

  // processingIds: wired from SP1's useJobStatuses hook.
  // When SP1 lands, import useJobStatuses from '../../api/useJobStatuses'
  // and compute this set from statuses Map (status === 'not_started' | 'processing').
  // Until then, undefined causes Sidebar to show no spinners (graceful degradation).
  const processingIds: Set<string> | undefined = undefined; // TODO: wire SP1

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

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (event.dataTransfer.files) handleFiles(Array.from(event.dataTransfer.files));
  };

  const hasSingleRunInput = inputMode === 'file' ? files.length > 0 : textInput.trim().length > 0;
  const hasPresetDataSelection = presetDataSelection.length > 0;
  const canSubmit = hasPresetDataSelection || hasSingleRunInput;
  const presetDataSelectionCount = presetDataSelection.length;

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setError(null);

    if (hasPresetDataSelection) {
      try {
        const { job_ids } = await createBatchJobs({
          selections: presetDataSelection,
          version: selectedVersion,
          grading_enabled: gradingEnabled,
        });
        if (job_ids.length > 0) {
          navigate(carePlanPagePath(job_ids[0]));
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
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
      const { job_id } = await createCarePlanJob(formData);
      navigate(carePlanPagePath(job_id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    }
  };

  function handleSelectSaved(id: string) {
    navigate(carePlanPagePath(id));
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <NavBar />
      <div style={{ display: 'flex', flex: 1 }}>
      <Sidebar
        activeId={null}
        onSelect={handleSelectSaved}
        refreshTrigger={0}
        processingIds={processingIds}
      />
      <div style={{ flex: 1, marginLeft: 'var(--sidebar-width, 240px)', minWidth: 0, paddingTop: 'calc(48px + 40px)' }}>
      <div className="aurora-bg" aria-hidden="true">
        <div className="aurora-orb aurora-orb-1" />
        <div className="aurora-orb aurora-orb-2" />
        <div className="aurora-orb aurora-orb-3" />
      </div>

      <div className="page-wrapper">
        <div className="container">
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
            </div>
            <PresetDataCard onSelectionChange={setPresetDataSelection} />
            <ConfigurationCard
              gradingEnabled={gradingEnabled}
              onGradingEnabledChange={setGradingEnabled}
            />
            <button className="cta-btn" disabled={!canSubmit} onClick={handleSubmit}>
              Create My Care Plan →
            </button>
          </section>
        </div>
      </div>
      </div>
      </div>
    </div>
  );
}
