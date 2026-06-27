export interface Dataset {
  group: string;
  inputs: string[];
  files: string[];
}

export interface BatchDatasetSelection {
  group: string;
  inputs: 'all' | string[];
  files: string[];
}

export interface AthenaEntry {
  id: string;
  label: string;
  practice_id: string;
  patient_id: string;
  encounter_id?: string;    // present for athena_encounter
  document_id?: string;     // present for athena_clinical_doc
  api_path: string;
  is_preview: boolean;
  preview_content: string | null;
}

export interface AthenaSource {
  source_kind: "athena_encounter" | "athena_clinical_doc";
  label: string;
  tab_id: string;
  preview_entry_id: string;
  entries: AthenaEntry[];
  sandbox_note?: string;
}

export interface AthenaSelection {
  source_kind: "athena_encounter" | "athena_clinical_doc";
  entry: AthenaEntry;
}

export interface ListDatasetsResponse {
  datasets: Dataset[];
  athena_sources: AthenaSource[];
}
