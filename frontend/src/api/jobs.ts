import { authenticatedFetch } from './apiClient';
import { API_URL } from './firebase';
import { CARE_PLAN_JOBS_PATH, CARE_PLAN_BATCH_JOBS_PATH } from '../constants';
import type { BatchDatasetSelection } from '../types/datasets';

export interface CreateJobResponse {
  job_id: string;
}

export interface CreateBatchJobsRequest {
  selections: BatchDatasetSelection[];
  version?: string;
  grading_enabled?: boolean;
}

export interface CreateBatchJobsResponse {
  batch_run_id: string;
  job_ids: string[];
}

export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse> {
  const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_JOBS_PATH}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function createBatchJobs(
  body: CreateBatchJobsRequest,
): Promise<CreateBatchJobsResponse> {
  const res = await authenticatedFetch(`${API_URL}${CARE_PLAN_BATCH_JOBS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Server error: ${res.status}`);
  }
  return res.json();
}
