import type { Grading, GradingEntry } from '../types/envelope';
import type { PatientScore } from '../types/carePlan';

export function patientScoreFromGrading(grading: Grading, target: 'before' | 'after'): PatientScore | null {
  const combined = grading.entries.find(e => e.name === 'combined' && e.target === target);
  if (!combined?.grade_breakdown) return null;
  const bd = combined.grade_breakdown as Record<string, unknown>;
  const dims = bd.dimensions;
  if (!dims) return null;
  return {
    composite:      combined.grade,
    grade_estimate: (bd.grade_estimate as number) ?? 0,
    label:          (bd.label as string) ?? '',
    word_count:     (bd.word_count as number) ?? 0,
    dimensions: Object.fromEntries(
      Object.entries(dims as Record<string, Record<string, unknown>>).map(([k, v]) => [
        k,
        { score: v.score, raw: v.raw, label: v.label, unit: v.unit },
      ])
    ) as PatientScore['dimensions'],
  };
}

export function methodEntriesFromGrading(grading: Grading, target: 'before' | 'after'): GradingEntry[] {
  return grading.entries.filter(e => e.target === target && e.name !== 'combined');
}
