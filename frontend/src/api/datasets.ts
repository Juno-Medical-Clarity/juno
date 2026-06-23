import { authenticatedFetch } from './apiClient';
import { API_URL } from './firebase';
import type { Dataset } from '../types/datasets';
import { DATASETS_PATH, datasetFilePath } from '../constants';

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
