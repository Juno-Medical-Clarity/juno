// All API path strings. API_URL stays in api/firebase.ts. VERSIONS (UI config) stays in config.ts.

export const CARE_PLAN_PATH = '/care_plan';
export const SAVED_OUTPUTS_PATH = '/care_plan/saved';
export const BATCH_PATH = '/care_plan/batch';
export const DATASETS_PATH = '/care_plan/datasets';

export const savedOutputPath = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}`;
export const inputPdfUrlPath  = (id: string) => `${SAVED_OUTPUTS_PATH}/${id}/input-pdf-url`;
export const datasetFilePath  = (group: string, input: string, file: string) =>
  `${DATASETS_PATH}/${encodeURIComponent(group)}/${encodeURIComponent(input)}/${encodeURIComponent(file)}`;

export const DEFAULT_VERSION = 'v1-2';
export { CARE_PLAN_PATH as CARE_PLAN_API_PATH };
