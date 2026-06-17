import { describe, it, expect } from 'vitest';
import { groupSavedOutputs } from './groupSavedOutputs';
import type { SavedOutputMeta } from './groupSavedOutputs';

function makeOutput(overrides: Partial<SavedOutputMeta> & { id: string }): SavedOutputMeta {
  return {
    name: overrides.id,
    source_filename: 'test.pdf',
    created_at: '2026-06-16T10:00:00Z',
    updated_at: '2026-06-16T10:00:00Z',
    batch_group_id: null,
    ...overrides,
  };
}

const FIXTURE: SavedOutputMeta[] = [
  // Date: 2026-06-16, batch: DocConv-A
  makeOutput({ id: 'a1', created_at: '2026-06-16T15:00:00Z', batch_group_id: 'DocConv-A' }),
  makeOutput({ id: 'a2', created_at: '2026-06-16T14:00:00Z', batch_group_id: 'DocConv-A' }),
  // Date: 2026-06-16, batch: DocConv-B
  makeOutput({ id: 'b1', created_at: '2026-06-16T13:00:00Z', batch_group_id: 'DocConv-B' }),
  // Date: 2026-06-16, standalone
  makeOutput({ id: 's1', created_at: '2026-06-16T12:00:00Z', batch_group_id: null }),
  makeOutput({ id: 's2', created_at: '2026-06-16T11:00:00Z', batch_group_id: null }),
  // Date: 2026-06-15, standalone only
  makeOutput({ id: 'c1', created_at: '2026-06-15T10:00:00Z', batch_group_id: null }),
];

describe('groupSavedOutputs', () => {
  it('produces two date groups in newest-first order', () => {
    const result = groupSavedOutputs(FIXTURE);
    expect(result).toHaveLength(2);
    expect(result[0].date).toBe('2026-06-16');
    expect(result[1].date).toBe('2026-06-15');
  });

  it('groups batch items correctly under the first date', () => {
    const result = groupSavedOutputs(FIXTURE);
    const day1 = result[0];
    expect(day1.batches).toHaveLength(2);
    expect(day1.batches[0].batch_group_id).toBe('DocConv-A');
    expect(day1.batches[0].items.map(o => o.id)).toEqual(['a1', 'a2']);
    expect(day1.batches[1].batch_group_id).toBe('DocConv-B');
    expect(day1.batches[1].items.map(o => o.id)).toEqual(['b1']);
  });

  it('puts null batch_group_id items in standalone', () => {
    const result = groupSavedOutputs(FIXTURE);
    const day1 = result[0];
    expect(day1.standalone.map(o => o.id)).toEqual(['s1', 's2']);
  });

  it('second date has no batches and one standalone', () => {
    const result = groupSavedOutputs(FIXTURE);
    const day2 = result[1];
    expect(day2.batches).toHaveLength(0);
    expect(day2.standalone.map(o => o.id)).toEqual(['c1']);
  });

  it('returns empty array for empty input', () => {
    expect(groupSavedOutputs([])).toEqual([]);
  });
});
