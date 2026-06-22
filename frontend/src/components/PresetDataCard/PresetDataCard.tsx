import { useEffect, useMemo, useState } from 'react';
import { listDatasets } from '../../api/datasets';
import type { BatchDatasetSelection, Dataset } from '../../types/datasets';
import PresetDataPanel, { type DatasetGroupSelection } from './PresetDataPanel';
import './PresetDataCard.css';

interface PresetDataCardProps {
  onSelectionChange: (selection: BatchDatasetSelection[]) => void;
}

type SelectionByGroup = Record<string, DatasetGroupSelection>;

function emptySelection(): DatasetGroupSelection {
  return { inputs: new Set(), files: new Set() };
}

function toBatchSelections(
  datasets: Dataset[],
  selectionByGroup: SelectionByGroup,
): BatchDatasetSelection[] {
  return datasets.flatMap(dataset => {
    const selection = selectionByGroup[dataset.group];
    if (!selection || selection.inputs.size === 0 || selection.files.size === 0) return [];

    const inputs =
      selection.inputs.size === dataset.inputs.length
        ? 'all'
        : dataset.inputs.filter(input => selection.inputs.has(input));

    const files = dataset.files.filter(filename => selection.files.has(filename));
    if (files.length === 0) return [];

    return [{
      group: dataset.group,
      inputs,
      files,
    }];
  });
}

export default function PresetDataCard({ onSelectionChange }: PresetDataCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectionByGroup, setSelectionByGroup] = useState<SelectionByGroup>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadDatasets() {
      setLoading(true);
      setError(null);
      try {
        const loadedDatasets = await listDatasets();
        if (!cancelled) setDatasets(loadedDatasets);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Could not load preset data.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadDatasets();

    return () => {
      cancelled = true;
    };
  }, []);

  const batchSelections = useMemo(
    () => toBatchSelections(datasets, selectionByGroup),
    [datasets, selectionByGroup],
  );

  useEffect(() => {
    onSelectionChange(batchSelections);
  }, [batchSelections, onSelectionChange]);

  useEffect(() => {
    if (datasets.length > 0 && activeGroup === null) {
      setActiveGroup(datasets[0].group);
    }
  }, [datasets, activeGroup]);

  function handleGroupSelectionChange(group: string, selection: DatasetGroupSelection) {
    setSelectionByGroup(current => ({
      ...current,
      [group]: selection,
    }));
  }

  const selectedGroupCount = batchSelections.length;
  const selectedInputCount = batchSelections.reduce((total, selection) => {
    if (selection.inputs === 'all') {
      const dataset = datasets.find(item => item.group === selection.group);
      return total + (dataset?.inputs.length ?? 0);
    }
    return total + selection.inputs.length;
  }, 0);
  const selectedFileCount = batchSelections.reduce(
    (total, selection) => total + selection.files.length,
    0,
  );

  return (
    <div className="preset-data-card glass-card">
      <div className="preset-data-card-header">
        <div>
          <div className="preset-data-card-title">Preset Data</div>
          <div className="preset-data-card-summary">
            {selectedGroupCount > 0
              ? `${selectedGroupCount} group${selectedGroupCount === 1 ? '' : 's'}, ${selectedInputCount} input${selectedInputCount === 1 ? '' : 's'}, ${selectedFileCount} file${selectedFileCount === 1 ? '' : 's'} selected`
              : 'Select repository datasets for batch runs.'}
          </div>
        </div>
        <button
          className="preset-data-toggle"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(current => !current)}
        >
          {expanded ? 'Collapse' : 'Choose'}
        </button>
      </div>

      {expanded && (
        <div className="preset-data-card-body">
          {loading && <div className="preset-data-status">Loading preset data...</div>}
          {error && <div className="preset-data-status error">{error}</div>}
          {!loading && !error && datasets.length === 0 && (
            <div className="preset-data-status">No preset datasets found.</div>
          )}
          {!loading && !error && datasets.length > 0 && (
            <div className="preset-panel-layout">
              {/* LEFT: vertical tab list */}
              <nav className="preset-panel-sidebar" aria-label="Dataset groups">
                {datasets.map(dataset => (
                  <button
                    key={dataset.group}
                    type="button"
                    title={dataset.group}
                    className={`preset-panel-tab ${activeGroup === dataset.group ? 'active' : ''}`}
                    onClick={() => setActiveGroup(dataset.group)}
                    aria-selected={activeGroup === dataset.group}
                  >
                    <span className="preset-panel-tab-name">{dataset.group}</span>
                    <span className="preset-panel-tab-meta">
                      {selectionByGroup[dataset.group]?.inputs.size ?? 0}/{dataset.inputs.length}
                    </span>
                  </button>
                ))}
              </nav>

              {/* RIGHT: content panel for the active group */}
              <div className="preset-panel-content">
                {activeGroup !== null && (() => {
                  const dataset = datasets.find(d => d.group === activeGroup);
                  if (!dataset) return null;
                  return (
                    <PresetDataPanel
                      dataset={dataset}
                      selection={selectionByGroup[activeGroup] ?? emptySelection()}
                      onSelectionChange={handleGroupSelectionChange}
                    />
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
