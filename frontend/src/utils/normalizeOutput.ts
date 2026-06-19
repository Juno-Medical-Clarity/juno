// frontend/src/utils/normalizeOutput.ts

import type { SimplifyOutput } from '../types/envelope';

export function isLegacyShape(data: any): boolean {
  return !('simplified_care_plan' in data);
}

export function normalizeSimplifyOutput(raw: any): SimplifyOutput {
  if (raw == null) {
    throw new Error('normalizeSimplifyOutput: received null or undefined output data');
  }
  if (!isLegacyShape(raw)) return raw as SimplifyOutput;

  // Legacy flat shape: everything except saved_id is the care plan itself.
  const { saved_id, ...rest } = raw;
  return {
    // pipeline_version uses route format ("v1"/"v1-1"/"v1-2"); care plan version uses schema format ("1.0"/"1.1"/"1.2")
    metrics: {
      session_id: '',
      pipeline_version: 'v1',  // legacy documents don't carry pipeline version info
      input_type: 'file',
      created_at: '',
      total_duration_ms: null,
      step_durations_ms: {},
      saved_id: saved_id ?? null,
    },
    input: { mode: 'file', files: [], text: null, doc_id: null },
    grading: { entries: [], enabled: false, graded_at: null },
    simplified_care_plan: { version: rest.version ?? '1.0', ...rest },
  };
}
