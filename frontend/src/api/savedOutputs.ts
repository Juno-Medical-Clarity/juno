import { authenticatedFetch } from './apiClient';
import { API_URL } from './firebase';

export interface SavedOutputMeta {
  id: string;
  name: string;
  source_filename: string;
  created_at: string;
  updated_at: string;
}

export interface SavedOutput extends SavedOutputMeta {
  output_data: Record<string, unknown>;
  input_pdf_gcs: string;
}

export async function listSavedOutputs(): Promise<SavedOutputMeta[]> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved`);
  if (!res.ok) throw new Error(`Failed to list saved outputs: ${res.status}`);
  const json = await res.json();
  return json.outputs as SavedOutputMeta[];
}

export async function getSavedOutput(id: string): Promise<SavedOutput> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved/${id}`);
  if (!res.ok) throw new Error(`Failed to get saved output: ${res.status}`);
  return res.json();
}

export async function renameSavedOutput(id: string, name: string): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Failed to rename: ${res.status}`);
}

export async function deleteSavedOutput(id: string): Promise<void> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete: ${res.status}`);
}

export async function getInputPdfUrl(id: string): Promise<string> {
  const res = await authenticatedFetch(`${API_URL}/simplify/saved/${id}/input-pdf-url`);
  if (!res.ok) throw new Error(`Failed to get PDF URL: ${res.status}`);
  const json = await res.json();
  return json.url as string;
}
