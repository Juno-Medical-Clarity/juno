import { useEffect, useState } from 'react';
import { API_URL } from '../../api/firebase';
import { authenticatedFetch } from '../../api/apiClient';
import { SIMPLIFY_API_PATH } from '../../config';

interface ManifestFile {
  name: string;
  url: string;
}

interface ManifestProcess {
  group: string;
  name: string;
  files: ManifestFile[];
}

interface ProcessStatus {
  state: 'waiting' | 'running' | 'done' | 'error';
  error?: string;
}

interface PresetDatasetModalProps {
  onClose: () => void;
  onProcessComplete: (savedId: string, name: string) => void;
}

export default function PresetDatasetModal({ onClose, onProcessComplete }: PresetDatasetModalProps) {
  const [processes, setProcesses] = useState<ManifestProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [statuses, setStatuses] = useState<Record<string, ProcessStatus>>({});
  const [running, setRunning] = useState(false);

  useEffect(() => {
    fetch('/preset-data/manifest.json')
      .then(r => r.json())
      .then(data => {
        setProcesses(data.processes ?? []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function setStatus(key: string, status: ProcessStatus) {
    setStatuses(prev => ({ ...prev, [key]: status }));
  }

  async function fetchFileAsFile(entry: ManifestFile): Promise<File> {
    const res = await fetch(entry.url);
    if (!res.ok) throw new Error(`Failed to fetch ${entry.name}`);
    const blob = await res.blob();
    return new File([blob], entry.name, { type: blob.type });
  }

  async function runProcess(proc: ManifestProcess): Promise<string | null> {
    const files = await Promise.all(proc.files.map(fetchFileAsFile));
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('version', 'v1-2');

    const response = await authenticatedFetch(`${API_URL}${SIMPLIFY_API_PATH}`, {
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
        } catch { /* skip */ }
      }
    }
    return savedId;
  }

  async function handleRunAll() {
    setRunning(true);
    for (const proc of processes) {
      const key = `${proc.group}/${proc.name}`;
      setStatus(key, { state: 'running' });
      try {
        const savedId = await runProcess(proc);
        setStatus(key, { state: 'done' });
        if (savedId) onProcessComplete(savedId, proc.name);
      } catch (e) {
        setStatus(key, { state: 'error', error: e instanceof Error ? e.message : 'Failed' });
      }
    }
    setRunning(false);
  }

  async function handleRunOne(proc: ManifestProcess) {
    const key = `${proc.group}/${proc.name}`;
    setStatus(key, { state: 'running' });
    try {
      const savedId = await runProcess(proc);
      setStatus(key, { state: 'done' });
      if (savedId) onProcessComplete(savedId, proc.name);
    } catch (e) {
      setStatus(key, { state: 'error', error: e instanceof Error ? e.message : 'Failed' });
    }
  }

  const statusIcon = (key: string) => {
    const s = statuses[key];
    if (!s || s.state === 'waiting') return '○';
    if (s.state === 'running') return '◉';
    if (s.state === 'done') return '✓';
    return '✗';
  };

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
          background: 'none', border: 'none', fontSize: '1.2rem', cursor: 'pointer',
          color: 'var(--text-secondary)',
        }}>✕</button>

        <h2 style={{ margin: '0 0 6px' }}>Preset Dataset</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '20px' }}>
          Pre-loaded processes from the repository. Add folders to <code>preset-data/</code> and redeploy to update this list.
        </p>

        {loading && <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Loading presets...</div>}

        {!loading && processes.length === 0 && (
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', padding: '20px 0', textAlign: 'center' }}>
            No preset processes found.<br />
            Add folders to <code>preset-data/</code> in the repository and redeploy.
          </div>
        )}

        {processes.length > 0 && (
          <>
            {processes.map(proc => {
              const key = `${proc.group}/${proc.name}`;
              const status = statuses[key];
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 0', borderBottom: '1px solid var(--border)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '1rem', color: status?.state === 'error' ? '#DC2626' : status?.state === 'done' ? '#16A34A' : 'var(--text-secondary)' }}>
                      {statusIcon(key)}
                    </span>
                    <div>
                      <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>{proc.name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {proc.group} · {proc.files.length} file{proc.files.length !== 1 ? 's' : ''}
                        {status?.error && <span style={{ color: '#DC2626' }}> — {status.error}</span>}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleRunOne(proc)}
                    disabled={running || status?.state === 'running'}
                    style={{
                      padding: '5px 12px', background: 'none',
                      border: '1px solid var(--border)', borderRadius: '6px',
                      fontSize: '0.8rem', cursor: 'pointer', fontFamily: 'Inter, sans-serif',
                      color: 'var(--text-secondary)', opacity: running ? 0.5 : 1,
                    }}
                  >
                    Run
                  </button>
                </div>
              );
            })}

            <button
              onClick={handleRunAll}
              disabled={running}
              style={{
                marginTop: '20px', width: '100%', padding: '12px',
                background: 'var(--accent-violet)', color: '#fff', border: 'none',
                borderRadius: '8px', fontFamily: 'Inter, sans-serif',
                fontWeight: 600, fontSize: '0.9rem',
                cursor: running ? 'not-allowed' : 'pointer',
                opacity: running ? 0.7 : 1,
              }}
            >
              {running ? 'Running...' : 'Run All'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
