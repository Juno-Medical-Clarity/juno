// frontend/src/types/envelope.ts
// TypeScript types mirroring the backend output envelope models (01-core-output-envelope).

import type { CarePlanContent } from './carePlan';

export interface InputFile {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface FileInput {
  mode: 'file';
  files: InputFile[];
  pdf_gcs_url: string | null;  // stub for SP-11 (Show Original)
}

export interface TextInput {
  mode: 'text';
  text: string | null;
}

export interface DocIdInput {
  mode: 'doc_id';
  doc_id: string;
}

export interface BatchDatasetInput {
  mode: 'batch_dataset';
  text: string;
  dataset_group: string;
  dataset_input: string;
  selected_files: string[];
  batch_group_id: string;
}

export type Input = FileInput | TextInput | DocIdInput | BatchDatasetInput;

export interface GradingEntry {
  name: string;
  target: 'before' | 'after';
  grade: number;
  grade_breakdown: Record<string, unknown> | null;
  reasoning: string | null;
}

export interface Grading {
  entries: GradingEntry[];
  enabled: boolean;
  graded_at: string | null;
}

export interface Metrics {
  session_id: string;
  pipeline_version: string;  // "v1" | "v1-1" | "v1-2"
  input_type: string;        // "file" | "text" | "doc_id"
  created_at: string;        // ISO8601
  total_duration_ms: number | null;
  step_durations_ms: Record<string, number>;
  saved_id: string | null;
}

// SimplifiedCarePlan is the CarePlanContent shape with an overridden (widened) version field.
// CarePlanContent.version is narrowed to '1.2'; here we widen it to string to accommodate
// future schema versions returned by the pipeline.
export type SimplifiedCarePlan = Omit<CarePlanContent, 'version'> & { version: string };

export interface CarePlanInternal {
  metrics: Metrics;
  input: Input;
  grading: Grading;
  care_plan: SimplifiedCarePlan;
}
