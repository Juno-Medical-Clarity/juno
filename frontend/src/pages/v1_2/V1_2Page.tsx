import '../v1_1/V1_1Page.css';
import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { API_URL } from '../../api/firebase';
import MedicalTerm from '../../components/MedicalTerm';

type StepStatus = 'waiting' | 'active' | 'done';
type DocUrgency = 'normal' | 'caution' | 'concern' | 'urgent';
type InputMode = 'file' | 'text';
type AppState = 'upload' | 'processing' | 'result';

interface PipelineStep {
  id: number;
  label: string;
  description: string;
  status: StepStatus;
}

interface PatientScoreDimension {
  score: number;
  raw: number;
  label: string;
  unit: string;
}

interface PatientScore {
  composite: number;
  grade_estimate: number;
  label: string;
  word_count: number;
  low_confidence?: boolean;
  dimensions: {
    grade_level: PatientScoreDimension;
    jargon_density: PatientScoreDimension;
    sentence_complexity: PatientScoreDimension;
    passive_voice: PatientScoreDimension;
    actionability: PatientScoreDimension;
    numeracy_clarity: PatientScoreDimension;
    structural_clarity: PatientScoreDimension;
  };
}

interface GlossaryTerm {
  definition: string;
  source: string;
  imgUrl?: string | null;
  altText?: string | null;
}

type TermsMap = Record<string, GlossaryTerm>;

interface DiagnosisDetail {
  title: string;
  plain_name?: string;
  description: string;
  what_it_means_for_you?: string;
  severity?: 'high' | 'medium' | 'low';
}

interface Medication {
  title: string;
  plain_name?: string;
  why?: string;
  dosage?: string;
  frequency?: string;
  timing?: string;
  duration?: string;
  instructions?: string;
  side_effects_to_watch?: string;
  importance: 'high' | 'low';
  change?: boolean;
  change_description?: string;
}

interface WarningSign {
  symptom: string;
  what_it_might_mean?: string;
  what_to_do: string;
  urgency: 'emergency' | 'call_doctor' | 'monitor' | 'normal_side_effect';
  related_to?: string;
  importance: 'high' | 'low';
}

interface AppointmentNote {
  doc_type: 'appointment_note';
  urgency: DocUrgency;
  version: '1.2';
  summary: string;
  reason_for_visit: Array<{ reason: string; description: string }>;
  diagnosis: {
    main_conclusion?: string;
    changed_since_last_visit?: string;
    details: DiagnosisDetail[];
  };
  medications: Medication[];
  tests: Array<{ title: string; plain_name?: string; why?: string; description: string; preparation?: string; importance: 'high' | 'low' }>;
  procedures: Array<{ title: string; plain_name?: string; why?: string; what_to_expect?: string; timeframe?: string; importance: 'high' | 'low' }>;
  other: Array<{ title: string; why?: string; steps?: string[]; description?: string; frequency?: string; duration?: string; importance: 'high' | 'low' }>;
  follow_up: Array<{ time_frame: string; description: string }>;
  warning_signs: WarningSign[];
  questions: string[];
  low_priority: string[];
  terms?: TermsMap;
  raw?: {
    text: string;
    simplified_text: string;
    clarified_text: string;
  };
  before_score?: PatientScore;
  after_score?: PatientScore;
}

const INITIAL_STEPS: PipelineStep[] = [
  { id: 1, label: 'Reading your note', description: 'Extracting text from your input', status: 'waiting' },
  { id: 2, label: 'Finding difficult and medical terms', description: 'Matching terms from AHRQ and medical dictionary', status: 'waiting' },
  { id: 3, label: 'Simplifying language', description: 'Rewriting to a 6th-grade reading level', status: 'waiting' },
  { id: 4, label: 'Clarifying actions and numbers', description: 'Active voice, plain action verbs, clear instructions', status: 'waiting' },
  { id: 5, label: 'Organizing your care plan', description: 'Structuring into sections that are easy to follow', status: 'waiting' },
];

function stepIcon(status: StepStatus): string {
  if (status === 'done') return '✓';
  if (status === 'active') return '◉';
  return '○';
}

function scoreColor(composite: number): string {
  if (composite >= 70) return 'score-green';
  if (composite >= 40) return 'score-amber';
  return 'score-red';
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderTextWithTerms(text: string, terms: TermsMap): ReactNode {
  if (!terms || Object.keys(terms).length === 0) return text;

  // Sort longest-first so that supersets ("hyper multiple sclerosis") beat subsets ("multiple sclerosis")
  // when they start at the same position.
  const sortedTerms = Object.keys(terms).sort((a, b) => b.length - a.length);
  const lowerText = text.toLowerCase();
  const parts: ReactNode[] = [];
  let offset = 0;
  let key = 0;

  while (offset < text.length) {
    // Find the earliest match among all terms; on tie (same start), longest wins (sortedTerms order).
    let bestStart = -1;
    let bestTerm = '';

    for (const term of sortedTerms) {
      const idx = lowerText.indexOf(term.toLowerCase(), offset);
      if (idx === -1) continue;
      if (bestStart === -1 || idx < bestStart) {
        bestStart = idx;
        bestTerm = term;
      }
    }

    if (bestStart === -1) {
      parts.push(<span key={key++}>{text.slice(offset)}</span>);
      break;
    }

    if (bestStart > offset) {
      parts.push(<span key={key++}>{text.slice(offset, bestStart)}</span>);
    }

    const displayTerm = text.slice(bestStart, bestStart + bestTerm.length);
    const glossaryEntry = terms[bestTerm];
    parts.push(
      <MedicalTerm
        key={key++}
        term={displayTerm}
        definition={glossaryEntry.definition}
        imgUrl={glossaryEntry.imgUrl}
        altText={glossaryEntry.altText}
      />,
    );
    offset = bestStart + bestTerm.length;
  }

  return <>{parts}</>;
}

function buildPdfHtml(result: AppointmentNote): string {
  const sections: string[] = [];
  const h2 = (title: string) =>
    `<h2 style="font-size:16px;font-weight:600;color:#1a1a2e;margin:20px 0 10px;padding-bottom:6px;border-bottom:2px solid #E5E7EB;">${escapeHtml(title)}</h2>`;

  if (result.summary) {
    sections.push(`${h2('What You Need to Know')}<p style="color:#374151;line-height:1.6;margin:0;">${escapeHtml(result.summary)}</p>`);
  }

  if (result.reason_for_visit?.length) {
    const items = result.reason_for_visit.map(r =>
      `<p style="color:#374151;margin:0 0 8px 0;"><strong>${escapeHtml(r.reason)}</strong>${r.description ? `: ${escapeHtml(r.description)}` : ''}</p>`,
    ).join('');
    sections.push(`${h2('Why You Came In')}${items}`);
  }

  if (result.diagnosis && (result.diagnosis.main_conclusion || result.diagnosis.details?.length)) {
    let diagnosis = '';
    if (result.diagnosis.main_conclusion) {
      diagnosis += `<p style="color:#374151;font-weight:500;margin:0 0 8px 0;">${escapeHtml(result.diagnosis.main_conclusion)}</p>`;
    }
    if (result.diagnosis.changed_since_last_visit) {
      diagnosis += `<p style="color:#0F766E;margin:0 0 8px 0;">Compared to last visit: ${escapeHtml(result.diagnosis.changed_since_last_visit)}</p>`;
    }
    diagnosis += (result.diagnosis.details ?? []).map(det =>
      `<div style="padding:8px 12px;margin-bottom:6px;background:#F0FDF4;border-radius:6px;">
        <strong>${escapeHtml(det.plain_name ? `${det.plain_name} (${det.title})` : det.title)}</strong>
        ${det.description ? `<br><span style="color:#6B7280;font-size:13px;">${escapeHtml(det.description)}</span>` : ''}
        ${det.what_it_means_for_you ? `<br><span style="color:#B45309;font-size:13px;">What this means for you: ${escapeHtml(det.what_it_means_for_you)}</span>` : ''}
      </div>`,
    ).join('');
    sections.push(`${h2('What the Doctor Found')}${diagnosis}`);
  }

  if (result.medications?.length) {
    const items = result.medications.map(m =>
      `<div style="padding:8px 12px;margin-bottom:6px;background:#F9FAFB;border-radius:6px;">
        <strong>${escapeHtml(m.plain_name ? `${m.plain_name} (${m.title})` : m.title)}</strong>
        ${m.change ? `<span style="color:#D97706;font-size:11px;font-weight:700;margin-left:6px;">[${escapeHtml(m.change_description || 'CHANGED')}]</span>` : ''}
        ${m.why ? `<br><span style="color:#1D4ED8;font-size:13px;">Why: ${escapeHtml(m.why)}</span>` : ''}
        ${m.dosage || m.frequency ? `<br><span style="color:#374151;font-size:13px;">${[m.dosage, m.frequency, m.timing, m.duration].filter(Boolean).map(value => escapeHtml(value as string)).join(' · ')}</span>` : ''}
        ${m.side_effects_to_watch ? `<br><span style="color:#D97706;font-size:13px;">Watch for: ${escapeHtml(m.side_effects_to_watch)}</span>` : ''}
      </div>`,
    ).join('');
    sections.push(`${h2('Your Medications')}${items}`);
  }

  if (result.tests?.length) {
    const items = result.tests.map(t =>
      `<div style="padding:8px 12px;margin-bottom:6px;background:#F9FAFB;border-radius:6px;">
        <strong>${escapeHtml(t.plain_name ? `${t.plain_name} (${t.title})` : t.title)}</strong>
        ${t.why ? `<br><span style="color:#1D4ED8;font-size:13px;">Why: ${escapeHtml(t.why)}</span>` : ''}
        ${t.description ? `<br><span style="color:#6B7280;font-size:13px;">${escapeHtml(t.description)}</span>` : ''}
        ${t.preparation ? `<p><strong>Preparation:</strong> ${t.preparation}</p>` : ''}
      </div>`,
    ).join('');
    sections.push(`${h2('Tests')}${items}`);
  }

  if (result.procedures?.length) {
    const items = result.procedures.map(p =>
      `<div style="padding:8px 12px;margin-bottom:6px;background:#F9FAFB;border-radius:6px;">
        <strong>${escapeHtml(p.plain_name ? `${p.plain_name} (${p.title})` : p.title)}</strong>
        ${p.why ? `<br><span style="color:#1D4ED8;font-size:13px;">Why: ${escapeHtml(p.why)}</span>` : ''}
        ${p.what_to_expect ? `<br><span style="color:#6B7280;font-size:13px;">What to expect: ${escapeHtml(p.what_to_expect)}</span>` : ''}
      </div>`,
    ).join('');
    sections.push(`${h2('Procedures')}${items}`);
  }

  if (result.other?.length) {
    const items = result.other.map(o => {
      const steps = o.steps?.length ? `<ul style="margin:4px 0 0 20px;padding:0;color:#374151;">${o.steps.map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ul>` : '';
      return `<div style="padding:8px 12px;margin-bottom:6px;background:#F9FAFB;border-radius:6px;">
        <strong>${escapeHtml(o.title)}</strong>
        ${o.why ? `<br><span style="color:#1D4ED8;font-size:13px;">Why: ${escapeHtml(o.why)}</span>` : ''}
        ${o.description ? `<br><span style="color:#6B7280;font-size:13px;">${escapeHtml(o.description)}</span>` : ''}
        ${steps}
      </div>`;
    }).join('');
    sections.push(`${h2('Other Instructions')}${items}`);
  }

  if (result.warning_signs?.length) {
    const items = [...result.warning_signs]
      .sort((a, b) => {
        const order: Record<string, number> = { emergency: 0, call_doctor: 1, monitor: 2, normal_side_effect: 3 };
        return (order[a.urgency] ?? 4) - (order[b.urgency] ?? 4);
      })
      .map(w =>
        `<div style="padding:8px 12px;margin-bottom:6px;background:#FFF7ED;border-radius:6px;">
          <strong>${escapeHtml(w.symptom)}</strong> [${escapeHtml(w.urgency)}]
          ${w.what_it_might_mean ? `<br><span style="color:#6B7280;font-size:13px;">${escapeHtml(w.what_it_might_mean)}</span>` : ''}
          <br><span style="font-size:13px;">${escapeHtml(w.what_to_do)}</span>
        </div>`,
      ).join('');
    sections.push(`${h2('What to Watch For')}${items}`);
  }

  if (result.questions?.length) {
    const items = result.questions.map(q => `<li>${escapeHtml(q)}</li>`).join('');
    sections.push(`${h2('Questions to Ask')}<ul style="margin:0;padding-left:20px;color:#0369A1;">${items}</ul>`);
  }

  if (result.follow_up?.length) {
    const items = result.follow_up.map(f => `<li>${escapeHtml(f.description)} - ${escapeHtml(f.time_frame)}</li>`).join('');
    sections.push(`${h2('Follow-Up')}<ul style="margin:0;padding-left:20px;color:#374151;">${items}</ul>`);
  }

  if (result.terms && Object.keys(result.terms).length > 0) {
    const items = Object.entries(result.terms).map(([term, glossary]) =>
      `<div style="margin-bottom:6px;"><strong>${escapeHtml(term)}:</strong> <span style="color:#6B7280;">${escapeHtml(glossary.definition)}</span></div>`,
    ).join('');
    sections.push(`${h2('Medical Terms Glossary')}${items}`);
  }

  if (result.low_priority?.length) {
    const items = result.low_priority.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    sections.push(`${h2('Other Items')}<ul style="margin:0;padding-left:20px;color:#6B7280;">${items}</ul>`);
  }

  return `<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a2e; margin: 0 auto; padding: 32px; max-width: 800px; background: #fff; }
.header { border-bottom: 3px solid #4F46E5; padding-bottom: 16px; margin-bottom: 8px; }
.header h1 { font-size: 22px; font-weight: 700; color: #4F46E5; margin: 0; }
.footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #E5E7EB; text-align: center; color: #9CA3AF; font-size: 11px; }
</style></head><body>
<div class="header"><h1>Simplified Appointment Summary</h1></div>
${sections.join('')}
<div class="footer">Generated by Juno - Simplified for patient understanding - Data deleted after processing</div>
</body></html>`;
}

function ResultCard({
  color,
  icon,
  title,
  collapsible = false,
  defaultOpen = true,
  children,
}: {
  color: string;
  icon: string;
  title: string;
  collapsible?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(collapsible ? defaultOpen : true);

  return (
    <div className={`result-card ${color}`}>
      <div
        className="result-card-header"
        onClick={() => collapsible && setOpen(current => !current)}
        style={{ cursor: collapsible ? 'pointer' : 'default' }}
      >
        <span className="result-card-title">
          <span>{icon}</span>
          <span>{title}</span>
        </span>
        {collapsible && <span className={`result-card-toggle ${open ? 'open' : ''}`}>▼</span>}
      </div>
      <div className={`result-card-body ${open ? '' : 'collapsed'}`}>{children}</div>
    </div>
  );
}

function ReadabilityCard({ before, after }: { before: PatientScore; after: PatientScore }) {
  const [expanded, setExpanded] = useState(false);
  const jargonBefore = `${Math.round(before.dimensions.jargon_density.raw * 100)}%`;
  const jargonAfter = `${Math.round(after.dimensions.jargon_density.raw * 100)}%`;

  return (
    <div className="result-card score-card">
      <div className="result-card-header">
        <span className="result-card-title">
          <span>📊</span>
          <span>Readability</span>
        </span>
        {before.low_confidence && <span className="score-low-confidence">low confidence</span>}
      </div>
      <div className="result-card-body">
        <div className="score-comparison">
          <div className="score-side">
            <div className={`score-bubble ${scoreColor(before.composite)}`}>{before.composite}</div>
            <div className={`score-label-tag ${scoreColor(before.composite)}`}>{before.label}</div>
            <div className="score-side-caption">Before</div>
          </div>
          <div className="score-arrow">→</div>
          <div className="score-side">
            <div className={`score-bubble ${scoreColor(after.composite)}`}>{after.composite}</div>
            <div className={`score-label-tag ${scoreColor(after.composite)}`}>{after.label}</div>
            <div className="score-side-caption">After</div>
          </div>
        </div>

        <div className="score-highlights">
          <span>Grade level: {before.grade_estimate} → {after.grade_estimate}</span>
          <span>Jargon density: {jargonBefore} → {jargonAfter}</span>
        </div>

        <button className="score-expand-btn" onClick={() => setExpanded(current => !current)}>
          {expanded ? 'Hide breakdown ▲' : 'View full breakdown ▼'}
        </button>

        {expanded && (
          <div className="score-breakdown">
            {(Object.entries(after.dimensions) as [keyof PatientScore['dimensions'], PatientScoreDimension][]).map(([key, dimension]) => {
              const beforeDimension = before.dimensions[key];
              return (
                <div className="score-breakdown-row" key={key}>
                  <span className="score-breakdown-label">{dimension.label}</span>
                  <div className="score-breakdown-bars">
                    <div className="score-bar-wrap">
                      <div className={`score-bar ${scoreColor(beforeDimension.score)}`} style={{ width: `${beforeDimension.score}%` }} />
                    </div>
                    <div className="score-bar-wrap">
                      <div className={`score-bar ${scoreColor(dimension.score)}`} style={{ width: `${dimension.score}%` }} />
                    </div>
                  </div>
                  <span className="score-breakdown-vals">{beforeDimension.score} → {dimension.score}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function AppointmentNoteV12View({ result }: { result: AppointmentNote }) {
  const terms = result.terms ?? {};
  const withTerms = (text: string) => renderTextWithTerms(text, terms);
  const URGENCY_COLORS: Record<string, string> = {
    emergency: '#DC2626',
    call_doctor: '#D97706',
    monitor: '#6B7280',
    normal_side_effect: '#6B7280',
  };
  const URGENCY_LABELS: Record<string, string> = {
    emergency: 'EMERGENCY',
    call_doctor: 'CALL DOCTOR',
    monitor: 'WATCH',
    normal_side_effect: 'NORMAL',
  };
  const URGENCY_ORDER: Record<string, number> = { emergency: 0, call_doctor: 1, monitor: 2, normal_side_effect: 3 };

  return (
    <div className="result-cards">
      {result.before_score && result.after_score && (
        <ReadabilityCard before={result.before_score} after={result.after_score} />
      )}

      {result.summary && (
        <div className="result-card" style={{ background: 'var(--surface-green-muted, #E8EDE3)' }}>
          <div className="result-card-body" style={{ paddingTop: '16px' }}>
            <h2 style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: '0.5rem' }}>What You Need to Know</h2>
            <p className="summary-paragraph">{withTerms(result.summary)}</p>
          </div>
        </div>
      )}

      {result.reason_for_visit?.length > 0 && (
        <ResultCard color="blue" icon="📅" title="Why You Came In">
          {result.reason_for_visit.map((r, i) => (
            <div key={i} style={{ marginBottom: '8px' }}>
              <strong>{withTerms(r.reason)}</strong>
              {r.description && <p style={{ color: 'var(--text-secondary)', margin: '4px 0 0 0', fontSize: '0.9rem' }}>{withTerms(r.description)}</p>}
            </div>
          ))}
        </ResultCard>
      )}

      {result.diagnosis && (result.diagnosis.main_conclusion || result.diagnosis.details?.length > 0) && (
        <ResultCard color="teal" icon="🔍" title="What the Doctor Found">
          {result.diagnosis.main_conclusion && (
            <p className="narrative-headline" style={{ background: '#F0FDFA', padding: '10px', borderRadius: '8px', marginBottom: '12px' }}>
              {withTerms(result.diagnosis.main_conclusion)}
            </p>
          )}
          {result.diagnosis.changed_since_last_visit && (
            <p style={{ color: '#0F766E', fontSize: '0.875rem', marginBottom: '12px' }}>
              Compared to last visit: {withTerms(result.diagnosis.changed_since_last_visit)}
            </p>
          )}
          {(() => {
            const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
            const sortedDetails = [...(result.diagnosis.details ?? [])].sort(
              (a, b) => (SEVERITY_ORDER[a.severity?.toLowerCase() ?? ''] ?? 99) - (SEVERITY_ORDER[b.severity?.toLowerCase() ?? ''] ?? 99)
            );
            return sortedDetails;
          })().map((det, i) => (
            <div key={i} style={{ paddingLeft: '12px', borderLeft: '4px solid #EF4444', marginBottom: '10px' }}>
              <strong>{withTerms(det.plain_name ? `${det.plain_name} (${det.title})` : det.title)}</strong>
              <p style={{ color: 'var(--text-secondary)', margin: '4px 0', fontSize: '0.9rem' }}>{withTerms(det.description)}</p>
              {det.what_it_means_for_you && (
                <p style={{ color: '#B45309', fontSize: '0.85rem', fontStyle: 'italic', margin: '4px 0 0 0' }}>
                  What this means for you: {withTerms(det.what_it_means_for_you)}
                </p>
              )}
            </div>
          ))}
        </ResultCard>
      )}

      {result.medications?.length > 0 && (
        <ResultCard color="violet" icon="💊" title="Your Medications">
          {result.medications.map((med, i) => (
            <div key={i} style={{ borderLeft: '4px solid #3B82F6', marginBottom: '12px', background: '#F9FAFB', padding: '10px 12px', borderRadius: '0 6px 6px 0' }}>
              <strong>{withTerms(med.plain_name ? `${med.plain_name} (${med.title})` : med.title)}</strong>
              {med.change && <span style={{ marginLeft: '8px', color: '#D97706', fontSize: '0.8rem', fontWeight: '700' }}>[{med.change_description || 'CHANGED'}]</span>}
              {med.why && <p style={{ color: '#1D4ED8', fontSize: '0.875rem', margin: '6px 0 4px 0' }}>Why: {withTerms(med.why)}</p>}
              {(med.dosage || med.frequency) && (
                <p style={{ color: '#374151', fontSize: '0.875rem', margin: '4px 0' }}>
                  {[med.dosage, med.frequency, med.timing, med.duration].filter(Boolean).join(' · ')}
                </p>
              )}
              {med.instructions && (
                <p style={{ color: '#374151', fontSize: '0.875rem', margin: '4px 0' }}>{withTerms(med.instructions)}</p>
              )}
              {med.side_effects_to_watch && (
                <p style={{ color: '#D97706', fontSize: '0.85rem', margin: '4px 0 0 0' }}>Watch for: {withTerms(med.side_effects_to_watch)}</p>
              )}
            </div>
          ))}
        </ResultCard>
      )}

      {result.tests?.length > 0 && (
        <ResultCard color="blue" icon="🧪" title="Tests">
          {result.tests.map((test, i) => (
            <div key={i} style={{ marginBottom: '10px' }}>
              <strong>{withTerms(test.plain_name ? `${test.plain_name} (${test.title})` : test.title)}</strong>
              {test.why && <p style={{ color: '#1D4ED8', fontSize: '0.875rem', margin: '4px 0' }}>Why: {withTerms(test.why)}</p>}
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: '4px 0' }}>{withTerms(test.description)}</p>
              {test.preparation && <p style={{ color: '#374151', fontSize: '0.85rem', margin: '4px 0 0 0' }}>Prepare: {withTerms(test.preparation)}</p>}
            </div>
          ))}
        </ResultCard>
      )}

      {result.procedures?.length > 0 && (
        <ResultCard color="violet" icon="🏥" title="Procedures">
          {result.procedures.map((procedure, i) => (
            <div key={i} style={{ marginBottom: '10px' }}>
              <strong>{withTerms(procedure.plain_name ? `${procedure.plain_name} (${procedure.title})` : procedure.title)}</strong>
              {procedure.why && <p style={{ color: '#1D4ED8', fontSize: '0.875rem', margin: '4px 0' }}>Why: {withTerms(procedure.why)}</p>}
              {procedure.what_to_expect && <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: '4px 0' }}>What to expect: {withTerms(procedure.what_to_expect)}</p>}
              {procedure.timeframe && <p style={{ color: '#374151', fontSize: '0.85rem', margin: '4px 0 0 0' }}>Timeframe: {withTerms(procedure.timeframe)}</p>}
            </div>
          ))}
        </ResultCard>
      )}

      {result.other?.length > 0 && (
        <ResultCard color="gray" icon="ℹ️" title="Other Instructions" collapsible defaultOpen={true}>
          {result.other.map((item, i) => (
            <div key={i} style={{ marginBottom: '10px' }}>
              <strong>{withTerms(item.title)}</strong>
              {item.why && <p style={{ color: '#1D4ED8', fontSize: '0.875rem', margin: '4px 0' }}>Why: {withTerms(item.why)}</p>}
              {item.description && <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: '4px 0' }}>{withTerms(item.description)}</p>}
              {(item.steps?.length ?? 0) > 0 && (
                <ul className="result-list">
                  {item.steps?.map((step, stepIndex) => <li key={stepIndex}>{withTerms(step)}</li>)}
                </ul>
              )}
              {(item.frequency || item.duration) && (
                <p style={{ color: '#374151', fontSize: '0.85rem', margin: '4px 0 0 0' }}>
                  {[item.frequency, item.duration].filter(Boolean).join(' · ')}
                </p>
              )}
            </div>
          ))}
        </ResultCard>
      )}

      {result.warning_signs?.length > 0 && (
        <ResultCard color="gray" icon="⚠️" title="What to Watch For">
          {[...result.warning_signs]
            .sort((a, b) => (URGENCY_ORDER[a.urgency] ?? 4) - (URGENCY_ORDER[b.urgency] ?? 4))
            .map((sign, i) => {
              const color = URGENCY_COLORS[sign.urgency] ?? '#6B7280';
              return (
                <div key={i} style={{ borderLeft: `4px solid ${color}`, paddingLeft: '12px', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <strong>{withTerms(sign.symptom)}</strong>
                    <span style={{ color, fontSize: '0.75rem', fontWeight: '700' }}>[{URGENCY_LABELS[sign.urgency] ?? sign.urgency}]</span>
                  </div>
                  {sign.what_it_might_mean && <p style={{ color: '#6B7280', fontSize: '0.875rem', margin: '4px 0' }}>{withTerms(sign.what_it_might_mean)}</p>}
                  <p style={{ color, fontWeight: '500', fontSize: '0.875rem', margin: '4px 0 0 0' }}>{withTerms(sign.what_to_do)}</p>
                </div>
              );
            })}
        </ResultCard>
      )}

      {result.questions?.length > 0 && (
        <ResultCard color="blue" icon="❓" title="Questions to Ask at Your Next Visit">
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '12px' }}>
            These are suggested questions based on what was discussed.
          </p>
          <ul className="result-list">
            {result.questions.map((q, i) => (
              <li key={i} style={{ color: '#0369A1', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <span style={{ flex: 1 }}>{withTerms(q)}</span>
                <button
                  onClick={() => navigator.clipboard.writeText(q)}
                  style={{
                    background: 'none',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-pill)',
                    color: 'var(--text-secondary)',
                    fontSize: '0.75rem',
                    padding: '2px 10px',
                    cursor: 'pointer',
                    fontFamily: 'Inter, sans-serif',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  Copy
                </button>
              </li>
            ))}
          </ul>
        </ResultCard>
      )}

      {result.follow_up?.length > 0 && (
        <ResultCard color="blue" icon="📅" title="Follow-Up">
          {result.follow_up.map((f, i) => (
            <div key={i} style={{ background: '#EFF6FF', padding: '10px', borderRadius: '6px', marginBottom: '6px' }}>
              <span>{withTerms(f.description)}</span>
              {f.time_frame && <span style={{ color: '#1D4ED8', marginLeft: '8px' }}>📅 {withTerms(f.time_frame)}</span>}
            </div>
          ))}
        </ResultCard>
      )}

      {result.low_priority?.length > 0 && (
        <ResultCard color="gray" icon="ℹ️" title="Other Items From Your Visit" collapsible defaultOpen={false}>
          <ul className="result-list">
            {result.low_priority.map((item, i) => <li key={i}>{withTerms(item)}</li>)}
          </ul>
        </ResultCard>
      )}

      {Object.keys(terms).length > 0 && (
        <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
          <div className="glossary-list">
            {Object.entries(terms).map(([term, glossary]) => (
              <div className="glossary-item" key={term}>
                <span className="glossary-term">{term}</span>
                <span className="glossary-def">{glossary.definition}</span>
              </div>
            ))}
          </div>
        </ResultCard>
      )}
    </div>
  );
}

export default function V1_2Page() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [inputMode, setInputMode] = useState<InputMode>('file');
  const [file, setFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [steps, setSteps] = useState<PipelineStep[]>(INITIAL_STEPS);
  const [result, setResult] = useState<AppointmentNote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleFile = useCallback((selectedFile: File) => {
    const extension = selectedFile.name.split('.').pop()?.toLowerCase();
    if (!['pdf', 'txt', 'docx'].includes(extension ?? '')) {
      setError('Please upload a PDF, .txt, or .docx file.');
      return;
    }

    setError(null);
    setFile(selectedFile);
  }, []);

  const onFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) handleFile(selectedFile);
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    const selectedFile = event.dataTransfer.files?.[0];
    if (selectedFile) handleFile(selectedFile);
  };

  const updateStep = useCallback((stepId: number, status: StepStatus) => {
    setSteps(currentSteps =>
      currentSteps.map(step => (step.id === stepId ? { ...step, status } : step)),
    );
  }, []);

  const canSubmit = inputMode === 'file' ? Boolean(file) : textInput.trim().length > 0;

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setError(null);
    setResult(null);
    setSteps(INITIAL_STEPS.map(step => ({ ...step, status: 'waiting' })));
    setAppState('processing');

    const formData = new FormData();
    if (inputMode === 'file' && file) {
      formData.append('file', file);
    } else {
      formData.append('text', textInput);
    }

    abortRef.current = new AbortController();

    try {
      const response = await fetch(`${API_URL}/simplify/v1-2`, {
        method: 'POST',
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Server error: ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (!payload || payload === '[DONE]') continue;

          try {
            const event = JSON.parse(payload) as {
              step: number | 'result';
              status?: 'active' | 'done';
              data?: AppointmentNote;
              error?: string;
            };

            if (event.error) throw new Error(event.error);

            if (event.step === 'result' && event.data) {
              setResult(event.data);
              setAppState('result');
            } else if (typeof event.step === 'number' && event.status) {
              updateStep(event.step, event.status);
            }
          } catch {
            // Skip malformed SSE lines.
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setAppState('upload');
    }
  };

  const handleDownloadJson = () => {
    if (!result) return;

    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'simplified-document.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadPdf = () => {
    if (!result) return;

    const html = buildPdfHtml(result);
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;

    printWindow.document.write(html);
    printWindow.document.close();
    setTimeout(() => printWindow.print(), 400);
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setFile(null);
    setTextInput('');
    setSteps(INITIAL_STEPS.map(step => ({ ...step, status: 'waiting' })));
    setResult(null);
    setError(null);
    setAppState('upload');
  };

  return (
    <>
      <div className="aurora-bg" aria-hidden="true">
        <div className="aurora-orb aurora-orb-1" />
        <div className="aurora-orb aurora-orb-2" />
        <div className="aurora-orb aurora-orb-3" />
      </div>

      <div className="page-wrapper">
        <div className="container">
          <section className="hero">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', justifyContent: 'center', marginBottom: '8px' }}>
              <div className="hero-badge">✦ AI-Powered Health Literacy</div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                <Link to="/versions" style={{ color: 'var(--accent-violet)', textDecoration: 'none' }}>v1.2</Link>
                {' · '}
                <Link to="/versions" style={{ color: 'var(--text-secondary)', textDecoration: 'none' }}>all versions</Link>
              </span>
            </div>
            <h1>Understand Your Appointment Note</h1>
            <p className="hero-sub">Built with experienced neuro professionals</p>
            <p className="hero-desc">
              Upload a provider note, appointment summary, or SOAP note.
              Juno will turn it into plain-language next steps you can understand and follow.
            </p>
          </section>

          {appState === 'upload' && (
            <section className="upload-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <div className="input-tabs">
                  <button
                    className={`input-tab ${inputMode === 'file' ? 'active' : ''}`}
                    onClick={() => setInputMode('file')}
                  >
                    Upload file
                  </button>
                  <button
                    className={`input-tab ${inputMode === 'text' ? 'active' : ''}`}
                    onClick={() => setInputMode('text')}
                  >
                    Paste text
                  </button>
                </div>

                {inputMode === 'file' ? (
                  <div
                    className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
                    onDragOver={event => {
                      event.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={onDrop}
                  >
                    <input type="file" accept=".pdf,.txt,.docx" onChange={onFileChange} />
                    <div className="upload-icon">📄</div>
                    {file ? (
                      <p className="upload-file-name">✓ {file.name}</p>
                    ) : (
                      <>
                        <p className="upload-title">
                          {dragOver ? 'Drop to upload' : 'Drag & drop your document here'}
                        </p>
                        <p className="upload-hint">
                          PDF, TXT, or DOCX · Best for provider notes, appointment summaries, and SOAP notes
                        </p>
                      </>
                    )}
                  </div>
                ) : (
                  <textarea
                    className="text-input-area"
                    placeholder="Paste your provider note, appointment summary, or SOAP note here..."
                    value={textInput}
                    onChange={event => setTextInput(event.target.value)}
                  />
                )}

                <div className="privacy-note">
                  <span className="privacy-note-icon">🔒</span>
                  <span>Your data is deleted immediately after processing.</span>
                </div>

                {error && <div className="error-box">⚠ {error}</div>}

                <button className="cta-btn" disabled={!canSubmit} onClick={handleSubmit}>
                  Simplify My Note →
                </button>
              </div>
            </section>
          )}

          {appState === 'processing' && (
            <section className="progress-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <p className="section-title">Simplifying your note...</p>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '-8px', marginBottom: '16px' }}>
                  Finding medical terms, rewriting to plain language, and organizing your care plan.
                </p>
                <div className="step-list">
                  {steps.map(step => (
                    <div className="step-item" key={step.id}>
                      <div className={`step-node ${step.status}`}>{stepIcon(step.status)}</div>
                      <div className="step-content">
                        <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>{step.label}</p>
                        <p className="step-desc">{step.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                <h2 className="result-title">Your Simplified Note</h2>
                <span className="deleted-note">🔒 Deleted from servers</span>
              </div>

              <AppointmentNoteV12View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button
                  onClick={handleReset}
                  style={{
                    background: 'none',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-pill)',
                    color: 'var(--text-secondary)',
                    fontSize: '0.85rem',
                    padding: '8px 20px',
                    cursor: 'pointer',
                    fontFamily: 'Inter, sans-serif',
                  }}
                >
                  ← Simplify another note
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download PDF
            </button>
          </div>
        </div>
      )}
    </>
  );
}
