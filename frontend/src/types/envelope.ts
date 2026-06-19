// frontend/src/types/envelope.ts
// TypeScript types mirroring the backend output envelope models (01-core-output-envelope).

import type { AppointmentNote } from './simplify';

export interface InputFile {
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface Input {
  mode: string;  // "file" | "text" | "doc_id"
  text: string | null;
  doc_id: string | null;
  files: InputFile[];
}

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

// SimplifiedCarePlan is the AppointmentNote shape with an overridden (widened) version field.
// AppointmentNote.version is narrowed to '1.2'; here we widen it to string to accommodate
// future schema versions returned by the pipeline.
export type SimplifiedCarePlan = Omit<AppointmentNote, 'version'> & { version: string };

export interface SimplifyOutput {
  metrics: Metrics;
  input: Input;
  grading: Grading;
  simplified_care_plan: SimplifiedCarePlan;
}
