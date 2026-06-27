// frontend/src/types/athena.ts
// TypeScript interfaces mirroring the Athena Health API request/response models.
// These are the contract between Juno and Athena Health.
// Any change to Athena's API response shape must be reflected here first.

// Auth
export interface AthenaTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  [key: string]: unknown;
}

// Encounters
export interface AthenaEncounterSummaryResponse {
  summaryhtml: string;
  [key: string]: unknown;
}

// Clinical Document metadata (from list endpoint)
export interface AthenaClinicalDocumentMeta {
  clinicaldocumentid: number;
  patientid: number;
  documentdescription: string;
  documentclass: string;
  status: string;
  internalnote?: string;
  createddatetime?: string;
  documentsource?: string;
  documentroute?: string;
  priority?: string;
  assignedto?: string;
  lastmodifieddatetime?: string;
  departmentid?: string;
  createddate?: string;
  lastmodifieduser?: string;
  lastmodifieddate?: string;
  observationdate?: string;
  createduser?: string;
  [key: string]: unknown;
}

export interface AthenaClinicalDocumentListResponse {
  clinicaldocuments: AthenaClinicalDocumentMeta[];
  totalcount?: number;
  [key: string]: unknown;
}

// Clinical Document content
export interface AthenaClinicalDocumentContentResponse {
  documentdata?: string;
  pages?: Array<{ pageid?: number; [key: string]: unknown }>;
  [key: string]: unknown;
}

// Push back (future/deferred)
export interface AthenaPushDocumentResponse {
  clinicaldocumentid: number;
  success?: boolean;
  [key: string]: unknown;
}
