import { useState } from 'react';
import type { AthenaEntry, AthenaSelection, AthenaSource } from '../../types/datasets';

interface AthenaPresetPanelProps {
  source: AthenaSource;
  onSelectionChange: (selections: AthenaSelection[]) => void;
}

type PanelMode = 'preview' | 'list';

export default function AthenaPresetPanel({
  source,
  onSelectionChange,
}: AthenaPresetPanelProps) {
  const [mode, setMode] = useState<PanelMode>('preview');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const previewEntry = source.entries.find(e => e.is_preview) ?? null;
  const listEntries = source.entries.filter(e => !e.is_preview);

  function handlePreviewSubmit() {
    if (!previewEntry) return;
    onSelectionChange([{ source_kind: source.source_kind, entry: previewEntry }]);
  }

  function handleCheckboxChange(entry: AthenaEntry) {
    const next = new Set(selected);
    if (next.has(entry.id)) {
      next.delete(entry.id);
    } else {
      next.add(entry.id);
    }
    setSelected(next);
    onSelectionChange(
      listEntries
        .filter(e => next.has(e.id))
        .map(e => ({ source_kind: source.source_kind, entry: e }))
    );
  }

  return (
    <div className="preset-panel">
      {/* Mode toggle */}
      <div className="athena-mode-toggle">
        <button
          type="button"
          className={`athena-mode-btn ${mode === 'preview' ? 'active' : ''}`}
          onClick={() => setMode('preview')}
        >
          Preview
        </button>
        <button
          type="button"
          className={`athena-mode-btn ${mode === 'list' ? 'active' : ''}`}
          onClick={() => setMode('list')}
        >
          List ({listEntries.length})
        </button>
      </div>

      <hr className="preset-panel-divider" />

      {/* Preview mode */}
      {mode === 'preview' && (
        <div className="preset-panel-appointments" style={{ overflowY: 'auto', flex: 1 }}>
          {previewEntry ? (
            <div className="athena-preview-card">
              <div className="athena-preview-label">{previewEntry.label}</div>
              <div className="athena-preview-api-path" style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                {previewEntry.api_path}
              </div>
              <div className="athena-preview-content">
                {previewEntry.preview_content?.slice(0, 500)}
                {(previewEntry.preview_content?.length ?? 0) > 500 ? '…' : ''}
              </div>
              <button
                type="button"
                className="athena-preview-submit"
                onClick={handlePreviewSubmit}
              >
                Use This Record
              </button>
            </div>
          ) : (
            <div className="preset-data-status">No preview entry found.</div>
          )}
          {source.sandbox_note && (
            <div className="preset-data-status" style={{ marginTop: '12px', fontStyle: 'italic' }}>
              {source.sandbox_note}
            </div>
          )}
        </div>
      )}

      {/* List mode */}
      {mode === 'list' && (
        <div className="preset-panel-appointments" style={{ overflowY: 'auto', flex: 1 }}>
          {listEntries.length === 0 ? (
            <div className="preset-data-status">No list entries available.</div>
          ) : (
            listEntries.map(entry => (
              <label key={entry.id} className="preset-data-option">
                <input
                  type="checkbox"
                  className="preset-data-checkbox"
                  checked={selected.has(entry.id)}
                  onChange={() => handleCheckboxChange(entry)}
                />
                <span className="preset-data-option-text">{entry.label}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
