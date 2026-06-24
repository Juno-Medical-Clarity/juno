import { authenticatedFetch, authenticatedFetchJson } from './apiClient';
import { API_URL } from './firebase';
import { SAVED_OUTPUTS_PATH, savedOutputPath, inputPdfUrlPath } from '../constants';
import type { Grading } from '../types/envelope';

export interface SavedOutputMeta {
  id: string;
  name: string;
  source_filename: string;
  created_at: string;
  updated_at: string;
  batch_group_id: string | null;
  status?: 'not_started' | 'processing' | 'completed' | 'error';
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
  // PATCH returns an empty body; use authenticatedFetch (not the JSON variant) to
  // avoid parsing a body that isn't there.
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Failed to rename: ${res.status}`);
}

export async function updateJobComment(id: string, comment: string): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) throw new Error(`Failed to update comment: ${res.status}`);
}

export async function updateCarePlanNote(id: string, note: string): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`Failed to update note: ${res.status}`);
}

export async function updateCarePlanGrading(id: string, grading: Grading): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grading }),
  });
  if (!res.ok) throw new Error(`Failed to update grading: ${res.status}`);
}

export async function shareOutput(id: string, shared: boolean): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}/share`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shared }),
  });
  if (!res.ok) throw new Error('Failed to update share status');
}

export async function deleteSavedOutput(id: string): Promise<void> {
  // DELETE returns an empty body; use authenticatedFetch to avoid JSON parsing.
  const res = await authenticatedFetch(`${API_URL}${savedOutputPath(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete: ${res.status}`);
}

export async function getInputPdfUrl(id: string): Promise<string> {
  const json = await authenticatedFetchJson<{ url: string }>(`${API_URL}${inputPdfUrlPath(id)}`);
  return json.url;
}
