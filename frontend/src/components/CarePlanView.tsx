import { useState, type ReactNode } from 'react';
import type { PatientScore, PatientScoreDimension, TermsMap } from '../types/carePlan';
import type { SimplifiedCarePlan, Grading } from '../types/envelope';
import { patientScoreFromGrading, methodEntriesFromGrading } from '../utils/grading';
import MedicalTerm from './MedicalTerm';

function scoreColor(composite: number): string {
  if (composite >= 70) return 'score-green';
  if (composite >= 40) return 'score-amber';
  return 'score-red';
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

// TODO(SP5-cleanup): dead code after SP5 — remove in a separate cleanup task
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

// TODO(SP5-cleanup): dead code after SP5 — remove in a separate cleanup task
function MethodGradingCards({ grading }: { grading: Grading }) {
  const afterEntries = methodEntriesFromGrading(grading, 'after');
  const beforeEntries = methodEntriesFromGrading(grading, 'before');
  if (afterEntries.length === 0) return null;

  const METHOD_LABELS: Record<string, string> = {
    smog: 'SMOG',
    flesch_kincaid: 'Flesch-Kincaid',
    dale_chall: 'Dale-Chall',
    pemat: 'PEMAT',
    sam: 'SAM',
    cdc_cci: 'CDC Clear Comm.',
  };

  return (
    <div className="method-grading-cards">
      {afterEntries.map(afterEntry => {
        const beforeEntry = beforeEntries.find(e => e.name === afterEntry.name);
        return (
          <div key={afterEntry.name} className="result-card score-card" style={{ marginTop: '8px' }}>
            <div className="result-card-header">
              <span className="result-card-title">
                <span>{METHOD_LABELS[afterEntry.name] ?? afterEntry.name}</span>
              </span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {beforeEntry && (
                  <span className={`score-bubble ${scoreColor(beforeEntry.grade)} score-bubble-sm`} style={{ fontSize: '0.75rem', padding: '2px 8px' }}>
                    {Math.round(beforeEntry.grade)}
                  </span>
                )}
                {beforeEntry && <span style={{ color: 'var(--text-secondary)' }}>→</span>}
                <span className={`score-bubble ${scoreColor(afterEntry.grade)}`} style={{ fontSize: '0.85rem' }}>
                  {Math.round(afterEntry.grade)}
                </span>
              </div>
            </div>
            {afterEntry.grade_breakdown && (
              <div className="result-card-body" style={{ paddingTop: '8px' }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 16px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {Object.entries(afterEntry.grade_breakdown).map(([k, v]) => (
                    <span key={k}><strong>{k}:</strong> {String(v)}</span>
                  ))}
                </div>
                {afterEntry.reasoning && (
                  <p style={{ marginTop: '8px', fontSize: '0.75rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                    {afterEntry.reasoning}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function CarePlanView({
  result,
  grading,
}: {
  result: SimplifiedCarePlan;
  grading: Grading;
}) {
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
