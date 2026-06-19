import { useEffect, useRef, useState } from 'react';
import { getDatasetFileContent } from '../api/datasets';
import type { Dataset } from '../types/datasets';

export interface DatasetGroupSelection {
  inputs: Set<string>;
  files: Set<string>;
}

interface DatasetGroupRowProps {
  dataset: Dataset;
  selection: DatasetGroupSelection;
  onSelectionChange: (group: string, selection: DatasetGroupSelection) => void;
}

type ActiveTab = 'inputs' | 'files';

interface PreviewState {
  filename: string;
  content: string;
  loading: boolean;
  error: string | null;
}

export default function DatasetGroupRow({
  dataset,
  selection,
  onSelectionChange,
}: DatasetGroupRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>('inputs');
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const groupCheckboxRef = useRef<HTMLInputElement>(null);

  const allInputsSelected = dataset.inputs.length > 0 && selection.inputs.size === dataset.inputs.length;
  const allFilesSelected = dataset.files.length > 0 && selection.files.size === dataset.files.length;
  const groupChecked = allInputsSelected && allFilesSelected;
  const groupPartial = !groupChecked && (selection.inputs.size > 0 || selection.files.size > 0);

  useEffect(() => {
    if (groupCheckboxRef.current) {
      groupCheckboxRef.current.indeterminate = groupPartial;
    }
  }, [groupPartial]);

  function replaceSelection(nextSelection: DatasetGroupSelection) {
    onSelectionChange(dataset.group, nextSelection);
  }

  function toggleGroup() {
    if (groupChecked) {
      replaceSelection({ inputs: new Set(), files: new Set() });
      return;
    }
    replaceSelection({
      inputs: new Set(dataset.inputs),
      files: new Set(dataset.files),
    });
  }

  function toggleInput(input: string) {
    const nextInputs = new Set(selection.inputs);
    if (nextInputs.has(input)) {
      nextInputs.delete(input);
    } else {
      nextInputs.add(input);
    }
    replaceSelection({ inputs: nextInputs, files: new Set(selection.files) });
  }

  function toggleFile(filename: string) {
    const nextFiles = new Set(selection.files);
    if (nextFiles.has(filename)) {
      nextFiles.delete(filename);
    } else {
      nextFiles.add(filename);
    }
    replaceSelection({ inputs: new Set(selection.inputs), files: nextFiles });
  }

  async function handleView(filename: string) {
    const previewInput = Array.from(selection.inputs)[0] ?? dataset.inputs[0];
    if (!previewInput) return;

    setPreview({ filename, content: '', loading: true, error: null });
    try {
      const file = await getDatasetFileContent(dataset.group, previewInput, filename);
      setPreview({
        filename,
        content: file.content || '(No extracted text)',
        loading: false,
        error: null,
      });
    } catch (error) {
      setPreview({
        filename,
        content: '',
        loading: false,
        error: error instanceof Error ? error.message : 'Could not load preview.',
      });
    }
  }

  return (
    <div className="preset-data-group">
      <div className="preset-data-group-main">
        <label className="preset-data-group-label">
          <input
            ref={groupCheckboxRef}
            className="preset-data-checkbox"
            type="checkbox"
            checked={groupChecked}
            onChange={toggleGroup}
          />
          <span>
            <span className="preset-data-group-name">{dataset.group}</span>
            <span className="preset-data-group-meta">
              {dataset.inputs.length} input{dataset.inputs.length === 1 ? '' : 's'} / {dataset.files.length} file{dataset.files.length === 1 ? '' : 's'}
            </span>
          </span>
        </label>
        <span className="preset-data-group-meta">
          {selection.inputs.size} inputs, {selection.files.size} files selected
        </span>
        <button
          className="preset-data-toggle"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(current => !current)}
        >
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {expanded && (
        <>
          <div className="preset-data-tabs" role="tablist" aria-label={`${dataset.group} preset data`}>
            <button
              className={`preset-data-tab ${activeTab === 'inputs' ? 'active' : ''}`}
              type="button"
              role="tab"
              aria-selected={activeTab === 'inputs'}
              onClick={() => setActiveTab('inputs')}
            >
              Inputs
            </button>
            <button
              className={`preset-data-tab ${activeTab === 'files' ? 'active' : ''}`}
              type="button"
              role="tab"
              aria-selected={activeTab === 'files'}
              onClick={() => setActiveTab('files')}
            >
              Files
            </button>
          </div>

          {activeTab === 'inputs' ? (
            <div className="preset-data-list">
              {dataset.inputs.map(input => (
                <label className="preset-data-option" key={input}>
                  <input
                    className="preset-data-checkbox"
                    type="checkbox"
                    checked={selection.inputs.has(input)}
                    onChange={() => toggleInput(input)}
                  />
                  <span className="preset-data-option-text">{input}</span>
                </label>
              ))}
              {dataset.inputs.length === 0 && (
                <div className="preset-data-status">No inputs found for this group.</div>
              )}
            </div>
          ) : (
            <div className="preset-data-list">
              {dataset.files.map(filename => (
                <div className="preset-data-option" key={filename}>
                  <label className="preset-data-file-label">
                    <input
                      className="preset-data-checkbox"
                      type="checkbox"
                      checked={selection.files.has(filename)}
                      onChange={() => toggleFile(filename)}
                    />
                    <span className="preset-data-option-text">{filename}</span>
                  </label>
                  <button
                    className="preset-data-view-button"
                    type="button"
                    disabled={dataset.inputs.length === 0}
                    onClick={() => void handleView(filename)}
                  >
                    View
                  </button>
                </div>
              ))}
              {dataset.files.length === 0 && (
                <div className="preset-data-status">No files found for this group.</div>
              )}
            </div>
          )}

          {preview && (
            <div className="preset-data-preview">
              <div className="preset-data-preview-header">
                <div className="preset-data-preview-title">{preview.filename}</div>
                <button
                  className="preset-data-preview-close"
                  type="button"
                  onClick={() => setPreview(null)}
                >
                  Close
                </button>
              </div>
              <div className={`preset-data-preview-content ${preview.error ? 'error' : ''}`}>
                {preview.loading ? 'Loading preview...' : preview.error ?? preview.content}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
