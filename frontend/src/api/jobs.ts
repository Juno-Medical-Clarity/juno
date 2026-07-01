import { authenticatedFetchJson } from './apiClient';
import { API_URL } from './firebase';
import { CARE_PLAN_JOBS_PATH, CARE_PLAN_BATCH_JOBS_PATH } from '../constants';
import type { BatchDatasetSelection } from '../types/datasets';

export interface CreateJobResponse {
  job_id: string;
}

export interface AthenaJobInput {
  input_source_kind: 'athena_encounter' | 'athena_clinical_doc';
  athena_practice_id: string;
  athena_patient_id: string;
  athena_encounter_id?: string;
  athena_document_id?: string;
  athena_api_path: string;
}

export type SelectionInput = BatchDatasetSelection | AthenaJobInput;

export interface CreateBatchJobsRequest {
  selections: SelectionInput[];
  version?: string;
  grading_enabled?: boolean;
}

export interface CreateBatchJobsResponse {
  batch_run_id: string;
  job_ids: string[];
}

export async function createCarePlanJob(formData: FormData): Promise<CreateJobResponse> {
  return authenticatedFetchJson<CreateJobResponse>(`${API_URL}${CARE_PLAN_JOBS_PATH}`, {
    method: 'POST',
    body: formData,
    // No Content-Type header — browser sets multipart/form-data with boundary automatically
  });
}

export async function createBatchJobs(body: CreateBatchJobsRequest): Promise<CreateBatchJobsResponse> {
  return authenticatedFetchJson<CreateBatchJobsResponse>(`${API_URL}${CARE_PLAN_BATCH_JOBS_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
