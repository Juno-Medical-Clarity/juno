import { useEffect, useRef, useState } from 'react';
import './Sidebar.css';
import {
  listSavedOutputs,
  renameSavedOutput,
  deleteSavedOutput,
  type SavedOutputMeta,
} from '../../api/savedOutputs';
import { formatDateKey, groupSavedOutputs, localDateKey } from '../../utils/groupSavedOutputs';

interface SidebarProps {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshTrigger: number;
}

export default function Sidebar({ activeId, onSelect, onNew, refreshTrigger }: SidebarProps) {
  const [outputs, setOutputs] = useState<SavedOutputMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  async function fetchOutputs() {
    setLoading(true);
    try {
      const list = await listSavedOutputs();
      setOutputs(list);
    } catch {
      setOutputs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchOutputs(); }, [refreshTrigger]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  async function handleRename(id: string) {
    const trimmed = renameValue.trim();
    if (!trimmed) return;
    try {
      await renameSavedOutput(id, trimmed);
      setOutputs(curr => curr.map(o => o.id === id ? { ...o, name: trimmed } : o));
    } catch { /* ignore */ }
    setRenamingId(null);
    setMenuOpenId(null);
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this saved output? This cannot be undone.')) return;
    try {
      await deleteSavedOutput(id);
      setOutputs(curr => curr.filter(o => o.id !== id));
      if (activeId === id) onNew();
    } catch { /* ignore */ }
    setMenuOpenId(null);
  }

  function isInProgress(output: SavedOutputMeta): boolean {
    return output.status === 'not_started' || output.status === 'processing';
  }

  function renderRow(output: SavedOutputMeta) {
    const inProgress = isInProgress(output);
    return (
      <div
        key={output.id}
        className={`sidebar-item ${activeId === output.id ? 'active' : ''}`}
        style={{ position: 'relative', cursor: inProgress ? 'default' : 'pointer' }}
        onClick={() => { if (!inProgress) onSelect(output.id); }}
      >
        <div className="sidebar-item-meta">
          {renamingId === output.id ? (
            <input
              autoFocus
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onBlur={() => handleRename(output.id)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleRename(output.id);
                if (e.key === 'Escape') setRenamingId(null);
              }}
              onClick={e => e.stopPropagation()}
              style={{
                width: '100%', border: '1px solid var(--accent-violet)',
                borderRadius: '4px', padding: '2px 6px', fontSize: '0.85rem',
                fontFamily: 'Inter, sans-serif', background: 'var(--bg)',
                color: 'var(--text-primary)',
              }}
            />
          ) : (
            <div className="sidebar-item-name">{output.name}</div>
          )}
        </div>
        {inProgress ? (
          <span
            className="sidebar-spinner"
            aria-label="Processing"
            style={{
              display: 'inline-block',
              width: '14px',
              height: '14px',
              border: '2px solid var(--accent-violet)',
              borderTopColor: 'transparent',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }}
          />
        ) : (
          <>
            <button
              className="sidebar-menu-btn"
              onClick={e => {
                e.stopPropagation();
                setMenuOpenId(menuOpenId === output.id ? null : output.id);
              }}
            >
              ⋯
            </button>
            {menuOpenId === output.id && (
              <div className="sidebar-dropdown" ref={menuRef} onClick={e => e.stopPropagation()}>
                <button
                  className="sidebar-dropdown-item"
                  onClick={() => {
                    setRenamingId(output.id);
                    setRenameValue(output.name);
                    setMenuOpenId(null);
                  }}
                >
                  Rename
                </button>
                <button
                  className="sidebar-dropdown-item danger"
                  onClick={() => handleDelete(output.id)}
                >
                  Delete
                </button>
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  const today = localDateKey(new Date());
  const grouped = !loading ? groupSavedOutputs(outputs) : [];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Saved</span>
        <button className="sidebar-new-btn" onClick={onNew}>+ New</button>
      </div>
      <div className="sidebar-list">
        {loading && <div className="sidebar-empty">Loading...</div>}
        {!loading && outputs.length === 0 && (
          <div className="sidebar-empty">No saved outputs yet.</div>
        )}
        {!loading && grouped.map(dateGroup => (
          <div key={dateGroup.date}>
            <div className="sidebar-date-header">
              {formatDateKey(dateGroup.date)}
            </div>
            {dateGroup.batches.map(batch => (
              <details
                key={batch.batch_group_id}
                className="sidebar-batch-group"
                open={dateGroup.date === today}
              >
                <summary className="sidebar-batch-header">{batch.batch_group_id}</summary>
                {batch.items.map(output => renderRow(output))}
              </details>
            ))}
            {dateGroup.standalone.map(output => renderRow(output))}
          </div>
        ))}
      </div>
    </aside>
  );
}
