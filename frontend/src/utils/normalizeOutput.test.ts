import { describe, expect, it } from 'vitest';
import { normalizeCarePlanOutput } from './normalizeOutput';

describe('normalizeCarePlanOutput', () => {
  it('fills required grading fields for legacy outputs', () => {
    const output = normalizeCarePlanOutput({
      saved_id: 'saved-1',
      version: '1.0',
      simplified_summary: 'summary',
    });

    expect(output.grading).toEqual({
      entries: [],
      enabled: false,
      graded_at: null,
    });
  });
});
