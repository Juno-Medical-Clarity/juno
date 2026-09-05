import { useState } from 'react';
import type { AuthState } from '../hooks/useAnonAuth';
import { createTrialJob } from '../api/trialApi';
import { validateFiles, validateText, MAX_FILES } from '../utils/validateFiles';
import { trackEvent } from '../analytics/ga';
import { ApiError } from '@main/types/errors';

type InputMode = 'file' | 'text';

interface UploadScreenProps {
  authState: AuthState;
  onAuthRetry: () => void;
  onJobCreated: (jobId: string) => void;
}

export default function UploadScreen({ authState, onAuthRetry, onJobCreated }: UploadScreenProps) {
  const [mode, setMode] = useState<InputMode>('file');
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function selectMode(next: InputMode) {
    setMode(next);
    setError(null);
    trackEvent({ name: 'input_mode_selected', params: { mode: next } });
  }

  function handleFilesSelected(selected: File[]) {
    const combined = [...files, ...selected].slice(0, MAX_FILES);
    const validationError = validateFiles(combined);
    setError(validationError);
    if (validationError) return;
    setFiles(combined);
    const fileTypes = [...new Set(combined.map(f => f.name.split('.').pop()?.toLowerCase() ?? ''))].sort().join(',');
    trackEvent({ name: 'files_selected', params: { file_count: combined.length, file_types: fileTypes } });
  }

  function removeFile(index: number) {
    setFiles(prev => prev.filter((_, i) => i !== index));
    setError(null);
  }

  function handleTextChange(value: string) {
    setText(value);
    setError(validateText(value));
  }

  const hasValidInput = mode === 'file' ? files.length > 0 && !error : text.trim().length > 0 && !error;
  const disabled = authState !== 'ready' || !hasValidInput || submitting;

  async function handleSubmit() {
    trackEvent({ name: 'simplify_clicked', params: { input_mode: mode, file_count: mode === 'file' ? files.length : 0 } });
    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      if (mode === 'file') {
        files.forEach(f => formData.append('files', f));
      } else {
        formData.append('text', text);
      }
      const { job_id } = await createTrialJob(formData);
      trackEvent({ name: 'simplify_submit_success', params: {} });
      onJobCreated(job_id);
    } catch (err) {
      let errorCode = 'NETWORK_ERROR';
      let message = 'Something went wrong. Please try again.';
      if (err instanceof ApiError) {
        errorCode = err.code;
        message = err.userHint ?? err.message;
      } else if (err instanceof Error) {
        message = err.message;
      }
      trackEvent({ name: 'simplify_submit_error', params: { error_code: errorCode, http_status: null } });
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <header style={{ textAlign: 'center' }}>
        <h1>Juno</h1>
        <p>Turn your care plan into plain language</p>
      </header>

      {authState === 'error' && (
        <div className="error-box">
          Couldn&apos;t start your session.{' '}
          <button onClick={onAuthRetry}>Retry</button>
        </div>
      )}

      <div className="input-tabs">
        <button
          type="button"
          className={`input-tab ${mode === 'file' ? 'active' : ''}`}
          onClick={() => selectMode('file')}
        >
          Upload files
        </button>
        <button
          type="button"
          className={`input-tab ${mode === 'text' ? 'active' : ''}`}
          onClick={() => selectMode('text')}
        >
          Paste text
        </button>
      </div>

      {mode === 'file' ? (
        <div className="upload-zone">
          <input
            type="file"
            multiple
            accept=".pdf,.txt,.docx,.html,.htm,.png,.jpg,.jpeg,.webp,.heic"
            onChange={e => handleFilesSelected(Array.from(e.target.files ?? []))}
          />
          <p>PDF, TXT, DOCX, HTML, or an image (PNG/JPG/WEBP/HEIC) · Up to {MAX_FILES} files</p>
          <ul>
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}>
                {f.name}{' '}
                <button type="button" aria-label={`Remove ${f.name}`} onClick={() => removeFile(i)}>✕</button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <textarea
          className="text-input-area"
          value={text}
          onChange={e => handleTextChange(e.target.value)}
          placeholder="Paste your care plan text here…"
        />
      )}

      {error && <div className="error-box">{error}</div>}

      <button className="cta-btn" disabled={disabled} onClick={handleSubmit}>
        {submitting ? 'Starting…' : 'Simplify'}
      </button>
    </div>
  );
}
