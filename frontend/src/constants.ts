// All API path strings. API_URL stays in api/firebase.ts. VERSIONS (UI config) stays in config.ts.

export const SAVED_OUTPUTS_PATH = '/care_plan/saved';
export const DATASETS_PATH = '/care_plan/datasets';

export const savedOutputPath = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}`;
export const inputPdfUrlPath  = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}/input-pdf-url`;
export const datasetFilePath  = (group: string, input: string, file: string) =>
  `${DATASETS_PATH}/${encodeURIComponent(group)}/${encodeURIComponent(input)}/${encodeURIComponent(file)}`;

export const DEFAULT_VERSION = 'v1-2';

export const ALLOWED_UPLOAD_EXTENSIONS = ['pdf', 'txt', 'docx', 'html', 'htm', 'png', 'jpg', 'jpeg', 'webp', 'heic'];

export const CARE_PLAN_JOBS_PATH = '/care_plan/jobs';
export const CARE_PLAN_BATCH_JOBS_PATH = '/care_plan/batch/jobs';
export const CARE_PLAN_PAGE_ROUTE = '/carePlan';
export const carePlanPagePath = (id: string) => `/carePlan/${id}`;

// Clinician Dataset — API paths
export const CLINICIAN_NPI_PATH = '/clinician_dataset/npi/search';
export const CLINICIAN_CMS_PATH = '/clinician_dataset/cms/search';

// Clinician Dataset — client-side routes
export const CLINICIAN_DATASET_ROUTE = '/clinician-dataset';
export const CLINICIAN_NPI_ROUTE = '/clinician-dataset/npi';
export const CLINICIAN_CMS_ROUTE = '/clinician-dataset/cms';
