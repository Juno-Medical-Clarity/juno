import { authenticatedFetch } from './apiClient';
import { API_URL } from './firebase';
import type { BatchDatasetSelection, Dataset } from '../types/datasets';
import { DATASETS_PATH, BATCH_PATH, datasetFilePath } from '../constants';

export interface DatasetFileContent {
  filename: string;
  content: string;
}

export async function listDatasets(): Promise<Dataset[]> {
  const res = await authenticatedFetch(`${API_URL}${DATASETS_PATH}`);
  if (!res.ok) throw new Error(`Failed to list datasets: ${res.status}`);
  const json = await res.json();
  return json.datasets as Dataset[];
}

export async function getDatasetFileContent(
  group: string,
  input: string,
  filename: string,
): Promise<DatasetFileContent> {
  const res = await authenticatedFetch(`${API_URL}${datasetFilePath(group, input, filename)}`);
  if (!res.ok) throw new Error(`Failed to get dataset file: ${res.status}`);
  return res.json();
}

export async function runBatch(
  selections: BatchDatasetSelection[],
  version: string,
  gradingEnabled: boolean,
  signal?: AbortSignal,
): Promise<Response> {
  return authenticatedFetch(`${API_URL}${BATCH_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      version,
      grading_enabled: gradingEnabled,
      selections,
    }),
    signal,
  });
}
