import { describe, it, expect } from 'vitest';
import { patientScoreFromGrading, methodEntriesFromGrading, groupGradingEntries, combinedScoreLabel } from '../../utils/grading';
import type { MethodGroup } from '../../utils/grading';
import type { Grading } from '../../types/envelope';

function makeDimensions() {
  return {
    grade_level:         { score: 80, raw: 8.0,  label: 'Grade 8',   unit: 'grade' },
    jargon_density:      { score: 70, raw: 0.05, label: 'Low',       unit: 'ratio' },
    sentence_complexity: { score: 75, raw: 18.0, label: 'Moderate',  unit: 'words' },
    passive_voice:       { score: 65, raw: 0.10, label: 'Low',       unit: 'ratio' },
    actionability:       { score: 85, raw: 0.85, label: 'High',      unit: 'ratio' },
    numeracy_clarity:    { score: 72, raw: 0.72, label: 'Good',      unit: 'ratio' },
    structural_clarity:  { score: 78, raw: 0.78, label: 'Clear',     unit: 'ratio' },
  };
}

function makeGradingWithCombined(): Grading {
  const dims = makeDimensions();
  const combinedBreakdown = {
    grade_estimate: 8,
    label: 'Moderate',
    word_count: 350,
    dimensions: dims,
  };

  return {
    enabled: true,
    graded_at: '2026-06-19T12:00:00Z',
    entries: [
      // combined entries
      {
        name: 'combined',
        target: 'before',
        grade: 60,
        grade_breakdown: { ...combinedBreakdown, label: 'Hard', grade_estimate: 12 },
        reasoning: null,
      },
      {
        name: 'combined',
        target: 'after',
        grade: 78,
        grade_breakdown: combinedBreakdown,
        reasoning: null,
      },
      // 6 method entries for 'after'
      { name: 'smog',           target: 'after', grade: 72, grade_breakdown: { level: 8 }, reasoning: null },
      { name: 'flesch_kincaid', target: 'after', grade: 75, grade_breakdown: { level: 7 }, reasoning: null },
      { name: 'dale_chall',     target: 'after', grade: 68, grade_breakdown: { score: 6.2 }, reasoning: null },
      { name: 'pemat',          target: 'after', grade: 80, grade_breakdown: { score: 0.8 }, reasoning: null },
      { name: 'sam',            target: 'after', grade: 71, grade_breakdown: { level: 'adequate' }, reasoning: null },
      { name: 'cdc_cci',        target: 'after', grade: 76, grade_breakdown: { score: 76 }, reasoning: null },
      // 6 method entries for 'before'
      { name: 'smog',           target: 'before', grade: 52, grade_breakdown: { level: 12 }, reasoning: null },
      { name: 'flesch_kincaid', target: 'before', grade: 48, grade_breakdown: { level: 13 }, reasoning: null },
      { name: 'dale_chall',     target: 'before', grade: 45, grade_breakdown: { score: 9.1 }, reasoning: null },
      { name: 'pemat',          target: 'before', grade: 55, grade_breakdown: { score: 0.55 }, reasoning: null },
      { name: 'sam',            target: 'before', grade: 50, grade_breakdown: { level: 'difficult' }, reasoning: null },
      { name: 'cdc_cci',        target: 'before', grade: 44, grade_breakdown: { score: 44 }, reasoning: null },
    ],
  };
}

describe('patientScoreFromGrading', () => {
  it('reconstructs PatientScore from the combined entry', () => {
    const grading = makeGradingWithCombined();
    const score = patientScoreFromGrading(grading, 'after');

    expect(score).not.toBeNull();
    expect(score!.composite).toBe(78);
    expect(score!.grade_estimate).toBe(8);
    expect(score!.label).toBe('Moderate');
    expect(score!.word_count).toBe(350);
  });

  it('includes all 7 dimensions', () => {
    const grading = makeGradingWithCombined();
    const score = patientScoreFromGrading(grading, 'after');

    const dimKeys = Object.keys(score!.dimensions);
    expect(dimKeys).toHaveLength(7);
    expect(dimKeys).toContain('grade_level');
    expect(dimKeys).toContain('jargon_density');
    expect(dimKeys).toContain('sentence_complexity');
    expect(dimKeys).toContain('passive_voice');
    expect(dimKeys).toContain('actionability');
    expect(dimKeys).toContain('numeracy_clarity');
    expect(dimKeys).toContain('structural_clarity');
  });

  it('returns null when entries are empty', () => {
    const grading: Grading = { entries: [], enabled: false, graded_at: null };
    expect(patientScoreFromGrading(grading, 'before')).toBeNull();
    expect(patientScoreFromGrading(grading, 'after')).toBeNull();
  });

  it('returns null when no combined entry for the target', () => {
    const grading = makeGradingWithCombined();
    // grading has combined for before and after; remove 'before' combined
    const filtered: Grading = {
      ...grading,
      entries: grading.entries.filter(e => !(e.name === 'combined' && e.target === 'before')),
    };
    expect(patientScoreFromGrading(filtered, 'before')).toBeNull();
  });

  it('returns null when combined entry has no grade_breakdown', () => {
    const grading: Grading = {
      enabled: true,
      graded_at: null,
      entries: [{ name: 'combined', target: 'after', grade: 70, grade_breakdown: null, reasoning: null }],
    };
    expect(patientScoreFromGrading(grading, 'after')).toBeNull();
  });
});

describe('methodEntriesFromGrading', () => {
  it('returns exactly 6 method entries for "after" target', () => {
    const grading = makeGradingWithCombined();
    const entries = methodEntriesFromGrading(grading, 'after');
    expect(entries).toHaveLength(6);
  });

  it('returns exactly 6 method entries for "before" target', () => {
    const grading = makeGradingWithCombined();
    const entries = methodEntriesFromGrading(grading, 'before');
    expect(entries).toHaveLength(6);
  });

  it('excludes the "combined" entry from method entries', () => {
    const grading = makeGradingWithCombined();
    const entries = methodEntriesFromGrading(grading, 'after');
    expect(entries.every(e => e.name !== 'combined')).toBe(true);
  });

  it('returns empty array when entries are empty', () => {
    const grading: Grading = { entries: [], enabled: false, graded_at: null };
    expect(methodEntriesFromGrading(grading, 'after')).toEqual([]);
  });
});

describe('groupGradingEntries', () => {
  it('groups before and after by name', () => {
    const grading = makeGradingWithCombined();
    const groups = groupGradingEntries(grading.entries);
    const fk = groups.find(g => g.name === 'flesch_kincaid');
    expect(fk).toBeDefined();
    expect(fk!.before).toBeDefined();
    expect(fk!.after).toBeDefined();
    expect(fk!.before!.target).toBe('before');
    expect(fk!.after!.target).toBe('after');
  });

  it('returns in METHOD_ORDER order — combined first', () => {
    const grading = makeGradingWithCombined();
    const groups = groupGradingEntries(grading.entries);
    expect(groups[0].name).toBe('combined');
    expect(groups[groups.length - 1].name).toBe('cdc_cci');
  });

  it('handles entries with only after target', () => {
    const entries = [
      { name: 'smog', target: 'after' as const, grade: 70, grade_breakdown: null, reasoning: null },
    ];
    const groups = groupGradingEntries(entries);
    expect(groups).toHaveLength(1);
    expect(groups[0].before).toBeUndefined();
    expect(groups[0].after).toBeDefined();
  });

  it('handles entries with only before target', () => {
    const entries = [
      { name: 'smog', target: 'before' as const, grade: 70, grade_breakdown: null, reasoning: null },
    ];
    const groups = groupGradingEntries(entries);
    expect(groups).toHaveLength(1);
    expect(groups[0].after).toBeUndefined();
    expect(groups[0].before).toBeDefined();
  });

  it('places unknown method names after known ones', () => {
    const entries = [
      { name: 'custom_method', target: 'after' as const, grade: 70, grade_breakdown: null, reasoning: null },
      { name: 'smog',          target: 'after' as const, grade: 65, grade_breakdown: null, reasoning: null },
    ];
    const groups = groupGradingEntries(entries);
    expect(groups[0].name).toBe('smog');
    expect(groups[1].name).toBe('custom_method');
  });

  it('returns empty array for empty input', () => {
    expect(groupGradingEntries([])).toEqual([]);
  });
});

describe('combinedScoreLabel', () => {
  function makeGroups(before: number | null, after: number | null): MethodGroup[] {
    const group: MethodGroup = {
      name: 'combined',
      label: 'Combined Score',
      before: before !== null
        ? { name: 'combined', target: 'before', grade: before, grade_breakdown: null, reasoning: null }
        : undefined,
      after: after !== null
        ? { name: 'combined', target: 'after', grade: after, grade_breakdown: null, reasoning: null }
        : undefined,
    };
    return [group];
  }

  it('returns "Score (X → Y)" when both targets present', () => {
    expect(combinedScoreLabel(makeGroups(60, 78))).toBe('Score (60 → 78)');
  });

  it('returns "Score (Y)" when only after present', () => {
    expect(combinedScoreLabel(makeGroups(null, 78))).toBe('Score (78)');
  });

  it('returns "Score (X)" when only before present', () => {
    expect(combinedScoreLabel(makeGroups(60, null))).toBe('Score (60)');
  });

  it('returns "Score" when no combined entry', () => {
    const groups: MethodGroup[] = [
      { name: 'smog', label: 'SMOG', before: undefined, after: undefined },
    ];
    expect(combinedScoreLabel(groups)).toBe('Score');
  });

  it('rounds grades to integer (Math.round)', () => {
    expect(combinedScoreLabel(makeGroups(null, 78.7))).toBe('Score (79)');
  });
});
