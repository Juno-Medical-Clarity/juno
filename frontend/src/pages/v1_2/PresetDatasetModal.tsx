import { useState, useRef } from 'react';
import { API_URL } from '../../api/firebase';
import { authenticatedFetch } from '../../api/apiClient';

interface ProcessEntry {
  name: string;
  files: File[];
}

interface PresetDatasetModalProps {
  onClose: () => void;
  onProcessComplete: (savedId: string, name: string) => void;
}

function parseProcessesFromFolder(fileList: FileList): ProcessEntry[] {
  const map = new Map<string, File[]>();
  for (const file of Array.from(fileList)) {
    const parts = (file as any).webkitRelativePath.split('/');
    if (parts.length < 3) continue;
    const processKey = parts.slice(0, 2).join('/');
    if (!map.has(processKey)) map.set(processKey, []);
    const allowed = ['pdf', 'txt', 'docx'];
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (allowed.includes(ext ?? '')) {
      map.get(processKey)!.push(file);
    }
  }
  return Array.from(map.entries()).map(([key, files]) => ({
    name: key.split('/').pop() || key,
    files,
  }));
}

export default function PresetDatasetModal({ onClose, onProcessComplete }: PresetDatasetModalProps) {
  const [processes, setProcesses] = useState<ProcessEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [currentIndex, setCurrentIndex] = useState<number | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const folderInputRef = useRef<HTMLInputElement>(null);

  function handleFolderSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files) return;
    const parsed = parseProcessesFromFolder(e.target.files);
    setProcesses(parsed);
    setCompletedIds([]);
    setErrors({});
  }

  async function runProcess(entry: ProcessEntry): Promise<string | null> {
    const formData = new FormData();
    entry.files.forEach(f => formData.append('files', f));

    const response = await authenticatedFetch(`${API_URL}/simplify/v1-2`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) throw new Error(`Server error: ${response.status}`);

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let savedId: string | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;
        try {
          const event = JSON.parse(payload);
          if (event.error) throw new Error(event.error);
          if (event.step === 'result' && event.data?.saved_id) {
            savedId = event.data.saved_id as string;
          }
        } catch { /* skip malformed lines */ }
      }
    }
    return savedId;
  }

  async function handleRun() {
    setRunning(true);
    const newCompleted: string[] = [];
    const newErrors: Record<string, string> = {};

    for (let i = 0; i < processes.length; i++) {
      setCurrentIndex(i);
      const entry = processes[i];
      try {
        const savedId = await runProcess(entry);
        if (savedId) {
          newCompleted.push(savedId);
          onProcessComplete(savedId, entry.name);
        }
      } catch (e) {
        newErrors[entry.name] = e instanceof Error ? e.message : 'Failed';
      }
    }

    setCompletedIds(newCompleted);
    setErrors(newErrors);
    setCurrentIndex(null);
    setRunning(false);
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--surface)', borderRadius: '16px', padding: '32px',
        width: '100%', maxWidth: '520px', maxHeight: '80vh', overflow: 'auto',
        position: 'relative',
      }}>
        <button onClick={onClose} style={{
          position: 'absolute', top: '16px', right: '16px',
          background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer', color: 'var(--text-secondary)',
        }}>✕</button>

        <h2 style={{ margin: '0 0 8px' }}>Preset Dataset</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '20px' }}>
          Upload a folder with subfolders. Each subfolder is one process (one pipeline run).
          <br />Expected structure: <code>GroupName/ProcessName/file.pdf</code>
        </p>

        <input
          ref={folderInputRef}
          type="file"
          // @ts-ignore - webkitdirectory is not in TS types
          webkitdirectory=""
          directory=""
          multiple
          style={{ display: 'none' }}
          onChange={handleFolderSelect}
        />

        <button
          onClick={() => folderInputRef.current?.click()}
          style={{
            padding: '10px 20px', border: '1.5px dashed var(--border)',
            borderRadius: '8px', background: 'var(--bg)', cursor: 'pointer',
            color: 'var(--text-secondary)', fontFamily: 'Inter, sans-serif',
            fontSize: '0.875rem', width: '100%', marginBottom: '20px',
          }}
        >
          Select Folder
        </button>

        {processes.length > 0 && (
          <>
            <p style={{ fontWeight: 600, marginBottom: '10px' }}>
              Found {processes.length} process{processes.length !== 1 ? 'es' : ''}:
            </p>
            {processes.map((entry, i) => {
              const isDone = completedIds.length > i && !running;
              const isCurrent = currentIndex === i;
              const hasError = Boolean(errors[entry.name]);
              return (
                <div key={entry.name} style={{
                  display: 'flex', alignItems: 'center', gap: '10px',
                  padding: '8px 0', borderBottom: '1px solid var(--border)',
                }}>
                  <span style={{ fontSize: '1rem' }}>
                    {hasError ? '✗' : isDone ? '✓' : isCurrent ? '◉' : '○'}
                  </span>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>{entry.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {entry.files.length} file{entry.files.length !== 1 ? 's' : ''}
                      {hasError && <span style={{ color: '#DC2626' }}> — {errors[entry.name]}</span>}
                    </div>
                  </div>
                </div>
              );
            })}

            {!running && currentIndex === null && (
              <button
                onClick={handleRun}
                style={{
                  marginTop: '20px', width: '100%', padding: '12px',
                  background: 'var(--accent-violet)', color: '#fff', border: 'none',
                  borderRadius: '8px', fontFamily: 'Inter, sans-serif',
                  fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer',
                }}
              >
                Run All Processes
              </button>
            )}

            {running && (
              <p style={{ marginTop: '16px', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                Processing {currentIndex !== null ? `${currentIndex + 1} of ${processes.length}` : ''}...
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
