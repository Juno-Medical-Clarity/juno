// frontend/src/utils/normalizeOutput.ts

import type { SimplifyOutput } from '../types/envelope';

export function isLegacyShape(data: any): boolean {
  return !('simplified_care_plan' in data);
}

export function normalizeSimplifyOutput(raw: any): SimplifyOutput {
  if (!isLegacyShape(raw)) return raw as SimplifyOutput;

  // Legacy flat shape: everything except saved_id is the care plan itself.
  const { saved_id, ...rest } = raw;
  return {
    metrics: {
      session_id: '',
      pipeline_version: rest.version ?? 'v1',
      input_type: 'file',
      created_at: '',
      total_duration_ms: null,
      step_durations_ms: {},
      saved_id: saved_id ?? null,
    },
    input: { mode: 'file', files: [], text: null, doc_id: null },
    grading: { entries: [] },
    simplified_care_plan: { version: rest.version ?? '1.0', ...rest },
  };
}
