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

export interface MethodGroup {
  name: string;
  label: string;
  before: GradingEntry | undefined;
  after: GradingEntry | undefined;
}

const METHOD_ORDER = ['combined', 'smog', 'flesch_kincaid', 'dale_chall', 'pemat', 'sam', 'cdc_cci'];

const METHOD_LABELS: Record<string, string> = {
  combined:       'Combined Score',
  smog:           'SMOG',
  flesch_kincaid: 'Flesch-Kincaid',
  dale_chall:     'Dale-Chall',
  pemat:          'PEMAT',
  sam:            'SAM',
  cdc_cci:        'CDC Clear Comm.',
};

export function groupGradingEntries(entries: GradingEntry[]): MethodGroup[] {
  const map = new Map<string, MethodGroup>();
  for (const entry of entries) {
    if (!map.has(entry.name)) {
      map.set(entry.name, {
        name: entry.name,
        label: METHOD_LABELS[entry.name] ?? entry.name,
        before: undefined,
        after: undefined,
      });
    }
    const g = map.get(entry.name)!;
    if (entry.target === 'before') g.before = entry;
    else g.after = entry;
  }
  const known = METHOD_ORDER.filter(n => map.has(n)).map(n => map.get(n)!);
  const unknown = [...map.values()].filter(g => !METHOD_ORDER.includes(g.name));
  return [...known, ...unknown];
}

export function combinedScoreLabel(groups: MethodGroup[]): string {
  const combined = groups.find(g => g.name === 'combined');
  if (!combined) return 'Score';
  const before = combined.before ? Math.round(combined.before.grade) : null;
  const after  = combined.after  ? Math.round(combined.after.grade)  : null;
  if (before !== null && after !== null) return `Score (${before} → ${after})`;
  if (after  !== null) return `Score (${after})`;
  if (before !== null) return `Score (${before})`;
  return 'Score';
}
