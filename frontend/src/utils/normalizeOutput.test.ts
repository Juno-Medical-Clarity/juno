import { describe, expect, it } from 'vitest';
import { normalizeSimplifyOutput } from './normalizeOutput';

describe('normalizeSimplifyOutput', () => {
  it('fills required grading fields for legacy outputs', () => {
    const output = normalizeSimplifyOutput({
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
