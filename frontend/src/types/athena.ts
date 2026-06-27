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

// ── Manifest models (static config files, not live API responses) ──────────

export interface AthenaEncounterManifestEntry {
  id: string;
  label: string;
  practice_id: string;
  patient_id: string;
  encounter_id: string;
  api_path: string;
  is_preview: boolean;
  preview_content: string | null;
}

export interface AthenaEncounterManifest {
  source_kind: "athena_encounter";
  label: string;
  tab_id: string;
  preview_entry_id: string;
  entries: AthenaEncounterManifestEntry[];
}

export interface AthenaClinicalDocManifestEntry {
  id: string;
  label: string;
  practice_id: string;
  patient_id: string;
  document_id: string;
  api_path: string;
  is_preview: boolean;
  preview_content: string | null;
}

export interface AthenaClinicalDocManifest {
  source_kind: "athena_clinical_doc";
  label: string;
  tab_id: string;
  preview_entry_id: string;
  entries: AthenaClinicalDocManifestEntry[];
}

export type AthenaManifest = AthenaEncounterManifest | AthenaClinicalDocManifest;
