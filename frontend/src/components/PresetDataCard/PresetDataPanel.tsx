import { useEffect, useRef, useState } from 'react';
import { getDatasetFileContent } from '../../api/datasets';
import type { Dataset } from '../../types/datasets';

export interface DatasetGroupSelection {
  inputs: Set<string>;
  files: Set<string>;
}

interface PresetDataPanelProps {
  dataset: Dataset;
  selection: DatasetGroupSelection;
  onSelectionChange: (group: string, selection: DatasetGroupSelection) => void;
}

interface PreviewState {
  filename: string;
  content: string;
  loading: boolean;
  error: string | null;
}

export default function PresetDataPanel({
  dataset,
  selection,
  onSelectionChange,
}: PresetDataPanelProps) {
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
    <div className="preset-panel">
      {/* Section 1: Select All */}
      <div className="preset-panel-select-all">
        <label className="preset-data-option">
          <input
            ref={groupCheckboxRef}
            className="preset-data-checkbox"
            type="checkbox"
            checked={groupChecked}
            onChange={toggleGroup}
          />
          <span className="preset-data-option-text">
            Select All ({dataset.inputs.length} appointment{dataset.inputs.length === 1 ? '' : 's'})
          </span>
        </label>
      </div>

      <hr className="preset-panel-divider" />

      {/* Section 2: Appointment list (scrollable) */}
      <div className="preset-panel-appointments">
        {dataset.inputs.length === 0 && (
          <div className="preset-data-status">No appointments found for this group.</div>
        )}
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
      </div>

      <hr className="preset-panel-divider" />

      {/* Section 3: File types + inline preview */}
      <div className="preset-panel-files">
        <div className="preset-panel-files-heading">File types</div>
        {dataset.files.length === 0 && (
          <div className="preset-data-status">No files found for this group.</div>
        )}
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
              Preview
            </button>
          </div>
        ))}

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
      </div>
    </div>
  );
}
