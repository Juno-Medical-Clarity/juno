import { authenticatedFetchJson } from './apiClient';
import { API_URL } from './firebase';
import { SAVED_OUTPUTS_PATH, savedOutputPath, inputPdfUrlPath } from '../constants';

export interface SavedOutputMeta {
  id: string;
  name: string;
  source_filename: string;
  created_at: string;
  updated_at: string;
  batch_group_id: string | null;
}

export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
}

export async function listSavedOutputs(): Promise<SavedOutputMeta[]> {
  const json = await authenticatedFetchJson<{ outputs: SavedOutputMeta[] }>(
    `${API_URL}${SAVED_OUTPUTS_PATH}`,
  );
  return json.outputs;
}

export async function getSavedOutput(id: string): Promise<SavedOutput> {
  return authenticatedFetchJson<SavedOutput>(`${API_URL}${savedOutputPath(id)}`);
}

export async function renameSavedOutput(id: string, name: string): Promise<void> {
  await authenticatedFetchJson(`${API_URL}${savedOutputPath(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function deleteSavedOutput(id: string): Promise<void> {
  await authenticatedFetchJson(`${API_URL}${savedOutputPath(id)}`, { method: 'DELETE' });
}

export async function getInputPdfUrl(id: string): Promise<string> {
  const json = await authenticatedFetchJson<{ url: string }>(`${API_URL}${inputPdfUrlPath(id)}`);
  return json.url;
}
