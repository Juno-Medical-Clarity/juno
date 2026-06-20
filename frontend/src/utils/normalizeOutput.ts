// frontend/src/utils/normalizeOutput.ts

import type { CarePlanInternal } from '../types/envelope';

export function isLegacyShape(data: unknown): boolean {
  return typeof data === 'object' && data !== null && !('care_plan' in data);
}

export function normalizeCarePlanOutput(raw: unknown): CarePlanInternal {
  if (raw == null) {
    throw new Error('normalizeCarePlanOutput: received null or undefined output data');
  }
  if (!isLegacyShape(raw)) return raw as CarePlanInternal;

  // Legacy flat shape: old saved Firestore documents without the envelope wrapper.
  const { saved_id, ...rest } = raw as Record<string, unknown>;
  return {
    metrics: {
      session_id: '',
      pipeline_version: 'v1',
      input_type: 'file',
      created_at: '',
      total_duration_ms: null,
      step_durations_ms: {},
      saved_id: (saved_id as string | null) ?? null,
    },
    input: { mode: 'file', files: [], text: null, doc_id: null },
    grading: { entries: [], enabled: false, graded_at: null },
    care_plan: { version: (rest.version as string) ?? '1.0', ...rest },
  } as unknown as CarePlanInternal;
}
