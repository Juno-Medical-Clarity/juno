import { authenticatedFetch } from './apiClient';
import { API_URL } from './firebase';
import type { BatchDatasetSelection, Dataset } from '../types/datasets';

export interface DatasetFileContent {
  filename: string;
  content: string;
}

export async function listDatasets(): Promise<Dataset[]> {
  const res = await authenticatedFetch(`${API_URL}/simplify/datasets`);
  if (!res.ok) throw new Error(`Failed to list datasets: ${res.status}`);
  const json = await res.json();
  return json.datasets as Dataset[];
}

export async function getDatasetFileContent(
  group: string,
  input: string,
  filename: string,
): Promise<DatasetFileContent> {
  const encodedGroup = encodeURIComponent(group);
  const encodedInput = encodeURIComponent(input);
  const encodedFilename = encodeURIComponent(filename);
  const res = await authenticatedFetch(
    `${API_URL}/simplify/datasets/${encodedGroup}/${encodedInput}/${encodedFilename}`,
  );
  if (!res.ok) throw new Error(`Failed to get dataset file: ${res.status}`);
  return res.json();
}

export async function runBatch(
  selections: BatchDatasetSelection[],
  version: string,
  gradingEnabled: boolean,
  signal?: AbortSignal,
): Promise<Response> {
  return authenticatedFetch(`${API_URL}/simplify/batch`, {
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
