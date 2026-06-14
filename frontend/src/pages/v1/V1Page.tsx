import { useState, useRef, useCallback, type ReactNode } from 'react';
import { API_URL } from '../../api/firebase';

// ─── Types ────────────────────────────────────────────────────────────────────

type StepStatus = 'waiting' | 'active' | 'done';
type UrgencyLevel = 'immediate' | 'soon' | 'routine' | 'informational';
type DocUrgency = 'normal' | 'caution' | 'concern' | 'urgent';

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

// Legacy result (backward compat — no doc_type field)
interface LegacyResult {
  doc_type?: undefined;
  action_items: { text: string; urgent: boolean }[];
  follow_ups: string[];
  key_findings: string[];
  additional_details: string[];
  definitions: Record<string, string>;
  questions: string[];
  before_score?: PatientScore;
  after_score?: PatientScore;
}

// Lab result (Layered Clarity Model)
interface AbnormalResult {
  name: string;
  value: string;
  unit: string;
  normal_range: string;
  status: 'caution' | 'concern' | 'critical';
  plain_meaning: string;
  why: string;
}

interface LabResult {
  doc_type: 'lab_result';
  urgency: DocUrgency;
  summary: string;
  critical_flags: string[];
  abnormal_results: AbnormalResult[];
  normal_results: { name: string; value: string; unit: string }[];
  action_items: { text: string; urgency: UrgencyLevel }[];
  what_this_means: string;
  follow_ups: string[];
  questions: string[];
  before_score?: PatientScore;
  after_score?: PatientScore;
}

// Appointment note (Narrative Action Model)
interface Finding {
  item: string;
  urgency: UrgencyLevel;
}

interface AppointmentNote {
  doc_type: 'appointment_note';
  urgency: DocUrgency;
  summary: string;
  what_happened: { summary: string; date: string | null; reason: string };
  what_it_means: { headline: string; findings: Finding[] };
  what_to_do: {
    text: string;
    urgency: 'immediate' | 'soon' | 'routine';
    category: 'medication' | 'appointment' | 'lifestyle' | 'monitoring';
    why: string;
  }[];
  low_priority: string[];
  follow_ups: string[];
  questions: string[];
  before_score?: PatientScore;
  after_score?: PatientScore;
}

type SimplifyResult = LegacyResult | LabResult | AppointmentNote;

type AppState = 'upload' | 'processing' | 'result';

// ─── Constants ────────────────────────────────────────────────────────────────

const INITIAL_STEPS: PipelineStep[] = [
  { id: 1, label: 'Reading your document',          description: 'Extracting text from your file',                            status: 'waiting' },
  { id: 2, label: 'Identifying document type',      description: 'Determining if this is a lab report or appointment note',   status: 'waiting' },
  { id: 3, label: 'Simplifying language',           description: 'Rewriting to a 6th-grade reading level',                   status: 'waiting' },
  { id: 4, label: 'Adding term explanations',       description: 'Defining medical jargon in plain language',                 status: 'waiting' },
  { id: 5, label: 'Clarifying numbers and actions', description: 'Converting medical shorthand and emphasising what to do',   status: 'waiting' },
  { id: 6, label: 'Organizing for clarity',         description: 'Structuring into sections that are easy to scan',          status: 'waiting' },
  { id: 7, label: 'Generating follow-up questions', description: 'Creating questions you may want to ask your doctor',        status: 'waiting' },
];

const CATEGORY_ICONS: Record<string, string> = {
  medication:  '💊',
  appointment: '📅',
  lifestyle:   '🏃',
  monitoring:  '📊',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function stepIcon(status: StepStatus): string {
  if (status === 'done')   return '✓';
  if (status === 'active') return '◉';
  return '○';
}

function buildDownloadText(result: SimplifyResult): string {
  const lines: string[] = ['SIMPLIFIED MEDICAL DOCUMENT', '='.repeat(40), ''];

  if (result.doc_type === 'lab_result') {
    lines.push(`DOCUMENT TYPE: Lab Results`);
    lines.push(`OVERALL STATUS: ${result.urgency.toUpperCase()}`);
    lines.push('');
    lines.push(`SUMMARY: ${result.summary}`);
    lines.push('');

    if (result.critical_flags.length > 0) {
      lines.push('🚨 URGENT — NEEDS ATTENTION TODAY');
      result.critical_flags.forEach(f => lines.push(`  - ${f}`));
      lines.push('');
    }

    if (result.abnormal_results.length > 0) {
      lines.push('⚠️  RESULTS THAT NEED ATTENTION');
      result.abnormal_results.forEach(r => {
        lines.push(`  [${r.status.toUpperCase()}] ${r.name}: ${r.value} ${r.unit} (normal: ${r.normal_range})`);
        lines.push(`    ${r.plain_meaning}`);
      });
      lines.push('');
    }

    if (result.action_items.length > 0) {
      lines.push('⭐ WHAT YOU SHOULD DO');
      result.action_items.forEach(a => lines.push(`  [${a.urgency.toUpperCase()}] ${a.text}`));
      lines.push('');
    }

    if (result.what_this_means) {
      lines.push('📋 WHAT THIS MEANS');
      lines.push(`  ${result.what_this_means}`);
      lines.push('');
    }

    if (result.normal_results.length > 0) {
      lines.push(`✓ RESULTS IN NORMAL RANGE (${result.normal_results.length})`);
      result.normal_results.forEach(r => lines.push(`  ${r.name}: ${r.value} ${r.unit}`));
      lines.push('');
    }

  } else if (result.doc_type === 'appointment_note') {
    lines.push(`DOCUMENT TYPE: Appointment Note`);
    lines.push(`OVERALL STATUS: ${result.urgency.toUpperCase()}`);
    lines.push('');

    lines.push('📅 WHAT HAPPENED');
    if (result.what_happened.date) lines.push(`  Date: ${result.what_happened.date}`);
    lines.push(`  Reason: ${result.what_happened.reason}`);
    lines.push(`  ${result.what_happened.summary}`);
    lines.push('');

    lines.push('🔍 WHAT IT MEANS');
    lines.push(`  ${result.what_it_means.headline}`);
    result.what_it_means.findings.forEach(f =>
      lines.push(`  [${f.urgency.toUpperCase()}] ${f.item}`),
    );
    lines.push('');

    if (result.what_to_do.length > 0) {
      lines.push('✅ WHAT TO DO');
      result.what_to_do.forEach(a =>
        lines.push(`  [${a.urgency.toUpperCase()}][${a.category}] ${a.text}`),
      );
      lines.push('');
    }

    if (result.low_priority.length > 0) {
      lines.push('ℹ️  OTHER ITEMS FROM YOUR VISIT');
      result.low_priority.forEach(item => lines.push(`  - ${item}`));
      lines.push('');
    }

  } else {
    // Legacy format
    if (result.action_items.length > 0) {
      lines.push('⭐ ACTION ITEMS');
      result.action_items.forEach(a =>
        lines.push(`  ${a.urgent ? '[URGENT] ' : ''}- ${a.text}`),
      );
      lines.push('');
    }
    if (result.key_findings.length > 0) {
      lines.push('📋 KEY FINDINGS');
      result.key_findings.forEach(f => lines.push(`  - ${f}`));
      lines.push('');
    }
    if (result.additional_details.length > 0) {
      lines.push('ℹ️  ADDITIONAL DETAILS');
      result.additional_details.forEach(d => lines.push(`  - ${d}`));
      lines.push('');
    }
  }

  if (result.follow_ups.length > 0) {
    lines.push('📅 FOLLOW-UPS');
    result.follow_ups.forEach(f => lines.push(`  - ${f}`));
    lines.push('');
  }

  if (result.questions.length > 0) {
    lines.push('💬 QUESTIONS TO ASK YOUR DOCTOR');
    result.questions.forEach(q => lines.push(`  - ${q}`));
    lines.push('');
  }

  if (!result.doc_type) {
    // Legacy format only
    const defEntries = Object.entries((result as LegacyResult).definitions ?? {});
    if (defEntries.length > 0) {
      lines.push('📖 MEDICAL TERMS GLOSSARY');
      defEntries.forEach(([term, def]) => lines.push(`  ${term}: ${def}`));
      lines.push('');
    }
  }

  lines.push('─'.repeat(40));
  lines.push('Generated by Juno Medical Document Simplifier');
  lines.push('This document was deleted from our servers immediately after processing.');

  return lines.join('\n');
}

// ─── Shared Sub-components ────────────────────────────────────────────────────

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
        onClick={() => collapsible && setOpen(o => !o)}
        style={{ cursor: collapsible ? 'pointer' : 'default' }}
      >
        <span className="result-card-title">
          <span>{icon}</span>
          <span>{title}</span>
        </span>
        {collapsible && (
          <span className={`result-card-toggle ${open ? 'open' : ''}`}>▼</span>
        )}
      </div>
      <div className={`result-card-body ${open ? '' : 'collapsed'}`}>
        {children}
      </div>
    </div>
  );
}

function SummaryCard({ summary }: { summary: string }) {
  if (!summary) return null;
  return (
    <div className="result-card">
      <div className="result-card-body" style={{ paddingTop: '16px' }}>
        <p className="summary-paragraph">{summary}</p>
      </div>
    </div>
  );
}

function UrgencyChip({ urgency }: { urgency: UrgencyLevel }) {
  return (
    <span className={`urgency-chip urgency-chip-${urgency}`}>{urgency}</span>
  );
}

function WhyToggle({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <div className="why-wrapper">
      <button className="why-btn" onClick={() => setOpen(o => !o)}>
        {open ? 'Less ▲' : 'Why? ▼'}
      </button>
      {open && <div className="why-content">{text}</div>}
    </div>
  );
}

function SharedTailCards({ result }: { result: { follow_ups: string[]; questions: string[]; definitions?: Record<string, string> } }) {
  return (
    <>
      {result.follow_ups.length > 0 && (
        <ResultCard color="blue" icon="📅" title="Follow-Ups">
          <ul className="result-list">
            {result.follow_ups.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </ResultCard>
      )}

      {result.questions.length > 0 && (
        <ResultCard color="indigo" icon="💬" title="Questions to Ask Your Doctor">
          <ul className="result-list">
            {result.questions.map((q, i) => <li key={i}>{q}</li>)}
          </ul>
        </ResultCard>
      )}

      {Object.keys(result.definitions ?? {}).length > 0 && (
        <ResultCard color="gray" icon="📖" title="Medical Terms Glossary" collapsible defaultOpen={false}>
          <div className="glossary-list">
            {Object.entries(result.definitions!).map(([term, def]) => (
              <div className="glossary-item" key={term}>
                <span className="glossary-term">{term}</span>
                <span className="glossary-def">{def}</span>
              </div>
            ))}
          </div>
        </ResultCard>
      )}
    </>
  );
}

function scoreColor(composite: number): string {
  if (composite >= 70) return 'score-green';
  if (composite >= 40) return 'score-amber';
  return 'score-red';
}

function ReadabilityCard({ before, after }: { before: PatientScore; after: PatientScore }) {
  const [expanded, setExpanded] = useState(false);

  const jargonBefore = `${Math.round(before.dimensions.jargon_density.raw * 100)}%`;
  const jargonAfter  = `${Math.round(after.dimensions.jargon_density.raw * 100)}%`;

  return (
    <div className="result-card score-card">
      <div className="result-card-header">
        <span className="result-card-title">
          <span>📊</span>
          <span>Readability</span>
        </span>
        {before.low_confidence && (
          <span className="score-low-confidence">low confidence</span>
        )}
      </div>
      <div className="result-card-body">
        <div className="score-comparison">
          <div className="score-side">
            <div className={`score-bubble ${scoreColor(before.composite)}`}>
              {before.composite}
            </div>
            <div className={`score-label-tag ${scoreColor(before.composite)}`}>{before.label}</div>
            <div className="score-side-caption">Before</div>
          </div>
          <div className="score-arrow">→</div>
          <div className="score-side">
            <div className={`score-bubble ${scoreColor(after.composite)}`}>
              {after.composite}
            </div>
            <div className={`score-label-tag ${scoreColor(after.composite)}`}>{after.label}</div>
            <div className="score-side-caption">After</div>
          </div>
        </div>

        <div className="score-highlights">
          <span>Grade level: {before.grade_estimate} → {after.grade_estimate}</span>
          <span>Jargon density: {jargonBefore} → {jargonAfter}</span>
        </div>

        <button className="score-expand-btn" onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Hide breakdown ▲' : 'View full breakdown ▼'}
        </button>

        {expanded && (
          <div className="score-breakdown">
            {(Object.entries(after.dimensions) as [keyof PatientScore['dimensions'], PatientScoreDimension][]).map(
              ([key, dim]) => {
                const beforeDim = before.dimensions[key];
                return (
                  <div className="score-breakdown-row" key={key}>
                    <span className="score-breakdown-label">{dim.label}</span>
                    <div className="score-breakdown-bars">
                      <div className="score-bar-wrap">
                        <div className={`score-bar ${scoreColor(beforeDim.score)}`} style={{ width: `${beforeDim.score}%` }} />
                      </div>
                      <div className="score-bar-wrap">
                        <div className={`score-bar ${scoreColor(dim.score)}`} style={{ width: `${dim.score}%` }} />
                      </div>
                    </div>
                    <span className="score-breakdown-vals">{beforeDim.score} → {dim.score}</span>
                  </div>
                );
              },
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Lab Result Components ────────────────────────────────────────────────────

function AbnormalResultRow({ result }: { result: AbnormalResult }) {
  return (
    <div className={`abnormal-result-item status-${result.status}`}>
      <div className="abnormal-result-header">
        <span className="abnormal-result-name">{result.name}</span>
        <span className={`abnormal-result-value status-${result.status}`}>
          {result.value}{result.unit ? ` ${result.unit}` : ''}
        </span>
        <span className={`abnormal-status-chip status-${result.status}`}>{result.status}</span>
      </div>
      {result.normal_range && (
        <div className="abnormal-result-range">Normal range: {result.normal_range}</div>
      )}
      <p className="abnormal-result-meaning">{result.plain_meaning}</p>
      <WhyToggle text={result.why} />
    </div>
  );
}

function LabResultView({ result }: { result: LabResult }) {
  return (
    <div className="result-cards">
      {result.before_score && result.after_score && (
        <ReadabilityCard before={result.before_score} after={result.after_score} />
      )}

      <SummaryCard summary={result.summary} />

      {result.critical_flags.length > 0 && (
        <ResultCard color="red" icon="🚨" title="Urgent — Action Needed Today">
          <ul className="result-list">
            {result.critical_flags.map((f, i) => (
              <li key={i} className="urgent">{f}</li>
            ))}
          </ul>
        </ResultCard>
      )}

      {result.abnormal_results.length > 0 && (
        <ResultCard color="amber" icon="⚠️" title="Results That Need Attention">
          <div className="abnormal-list">
            {result.abnormal_results.map((r, i) => (
              <AbnormalResultRow key={i} result={r} />
            ))}
          </div>
        </ResultCard>
      )}

      {result.action_items.length > 0 && (
        <ResultCard color="violet" icon="⭐" title="What You Should Do">
          <ul className="result-list">
            {result.action_items.map((item, i) => (
              <li key={i} className="action-item-row">
                <UrgencyChip urgency={item.urgency} />
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        </ResultCard>
      )}

      {result.what_this_means && (
        <ResultCard color="teal" icon="📋" title="What This Means">
          <p className="what-this-means-text">{result.what_this_means}</p>
        </ResultCard>
      )}

      {result.normal_results.length > 0 && (
        <ResultCard
          color="gray"
          icon="✓"
          title={`${result.normal_results.length} result${result.normal_results.length !== 1 ? 's' : ''} in the normal range`}
          collapsible
          defaultOpen={false}
        >
          <div className="normal-results-grid">
            {result.normal_results.map((r, i) => (
              <div key={i} className="normal-result-row">
                <span className="normal-result-name">{r.name}</span>
                <span className="normal-result-value">{r.value}{r.unit ? ` ${r.unit}` : ''}</span>
              </div>
            ))}
          </div>
        </ResultCard>
      )}

      <SharedTailCards result={result} />
    </div>
  );
}

// ─── Appointment Note Components ──────────────────────────────────────────────

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <div className="finding-row">
      <div className="finding-header">
        <UrgencyChip urgency={finding.urgency} />
        <span className="finding-text">{finding.item}</span>
      </div>
    </div>
  );
}

function AppointmentNoteView({ result }: { result: AppointmentNote }) {
  return (
    <div className="result-cards">
      {result.before_score && result.after_score && (
        <ReadabilityCard before={result.before_score} after={result.after_score} />
      )}

      <SummaryCard summary={result.summary} />

      {/* Card 1: What Happened */}
      <ResultCard color="blue" icon="📅" title="What Happened">
        {result.what_happened.date && (
          <p className="narrative-date">{result.what_happened.date}</p>
        )}
        {result.what_happened.reason && (
          <p className="narrative-reason">{result.what_happened.reason}</p>
        )}
        <p className="narrative-summary">{result.what_happened.summary}</p>
      </ResultCard>

      {/* Card 2: What To Do */}
      {result.what_to_do.length > 0 && (
        <ResultCard color="violet" icon="✅" title="What To Do">
          <div className="action-list">
            {result.what_to_do.map((a, i) => (
              <div key={i} className="action-row-with-why">
                <div className="action-row">
                  <span className="action-category-icon">
                    {CATEGORY_ICONS[a.category] ?? '•'}
                  </span>
                  <div className="action-content">
                    <UrgencyChip urgency={a.urgency} />
                    <span className="action-text">{a.text}</span>
                  </div>
                </div>
                <WhyToggle text={a.why} />
              </div>
            ))}
          </div>
        </ResultCard>
      )}

      {/* Card 3: What It Means */}
      <ResultCard color="teal" icon="🔍" title="What It Means">
        {result.what_it_means.headline && (
          <p className="narrative-headline">{result.what_it_means.headline}</p>
        )}
        <div className="findings-list">
          {result.what_it_means.findings.map((f, i) => (
            <FindingRow key={i} finding={f} />
          ))}
        </div>
      </ResultCard>

      {result.low_priority.length > 0 && (
        <ResultCard color="gray" icon="ℹ️" title="Other Items From Your Visit" collapsible defaultOpen={false}>
          <ul className="result-list">
            {result.low_priority.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </ResultCard>
      )}

      <SharedTailCards result={result} />
    </div>
  );
}

// ─── Legacy Result View (backward compat) ────────────────────────────────────

function LegacyResultView({ result }: { result: LegacyResult }) {
  return (
    <div className="result-cards">
      {result.before_score && result.after_score && (
        <ReadabilityCard before={result.before_score} after={result.after_score} />
      )}

      {result.action_items.length > 0 && (
        <ResultCard color="violet" icon="⭐" title="Action Items">
          <ul className="result-list">
            {result.action_items.map((item, i) => (
              <li key={i} className={item.urgent ? 'urgent' : ''}>{item.text}</li>
            ))}
          </ul>
        </ResultCard>
      )}

      {result.key_findings.length > 0 && (
        <ResultCard color="teal" icon="📋" title="Key Findings">
          <ul className="result-list">
            {result.key_findings.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </ResultCard>
      )}

      {result.additional_details.length > 0 && (
        <ResultCard color="gray" icon="ℹ️" title="Additional Details" collapsible>
          <ul className="result-list">
            {result.additional_details.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </ResultCard>
      )}

      <SharedTailCards result={result} />
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function V1Page() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [steps, setSteps] = useState<PipelineStep[]>(INITIAL_STEPS);
  const [result, setResult] = useState<SimplifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── File handlers ──────────────────────────────────────────────────────────

  const handleFile = useCallback((f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    if (!['pdf', 'txt', 'docx'].includes(ext ?? '')) {
      setError('Please upload a PDF, .txt, or .docx file.');
      return;
    }
    setError(null);
    setFile(f);
  }, []);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  // ── Pipeline ────────────────────────────────────────────────────────────────

  const updateStep = useCallback((stepId: number, status: StepStatus) => {
    setSteps(prev =>
      prev.map(s => (s.id === stepId ? { ...s, status } : s)),
    );
  }, []);

  const handleSubmit = async () => {
    if (!file) return;

    setError(null);
    setResult(null);
    setSteps(INITIAL_STEPS.map(s => ({ ...s, status: 'waiting' })));
    setAppState('processing');

    const formData = new FormData();
    formData.append('file', file);

    abortRef.current = new AbortController();

    try {
      const response = await fetch(`${API_URL}/simplify`, {
        method: 'POST',
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        const msg = await response.text();
        throw new Error(msg || `Server error: ${response.status}`);
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
              label?: string;
              data?: SimplifyResult;
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
            // skip malformed SSE lines
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setAppState('upload');
    }
  };

  const handleDownload = () => {
    if (!result) return;
    const text = buildDownloadText(result);
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'simplified-medical-document.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setFile(null);
    setSteps(INITIAL_STEPS.map(s => ({ ...s, status: 'waiting' })));
    setResult(null);
    setError(null);
    setAppState('upload');
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Aurora background */}
      <div className="aurora-bg" aria-hidden="true">
        <div className="aurora-orb aurora-orb-1" />
        <div className="aurora-orb aurora-orb-2" />
        <div className="aurora-orb aurora-orb-3" />
      </div>

      <div className="page-wrapper">
        <div className="container">

          {/* ── Hero ── */}
          <section className="hero">
            <div className="hero-badge">✦ AI-Powered Health Literacy</div>
            <h1>Understand Your Medical Documents</h1>
            <p className="hero-sub">Built with experienced neuro professionals</p>
            <p className="hero-desc">
              Upload any medical document and get a plain-language version you can actually
              understand — with action steps, definitions, and questions to ask your doctor.
            </p>
          </section>

          {/* ── Upload ── */}
          {appState === 'upload' && (
            <section className="upload-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <div
                  className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
                  onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                >
                  <input
                    type="file"
                    accept=".pdf,.txt,.docx"
                    onChange={onFileChange}
                  />
                  <div className="upload-icon">📄</div>
                  {file ? (
                    <p className="upload-file-name">✓ {file.name}</p>
                  ) : (
                    <>
                      <p className="upload-title">
                        {dragOver ? 'Drop to upload' : 'Drag & drop your document here'}
                      </p>
                      <p className="upload-hint">or click to browse — PDF, TXT, DOCX</p>
                    </>
                  )}
                </div>

                <div className="privacy-note">
                  <span className="privacy-note-icon">🔒</span>
                  <span>Your data is deleted immediately after processing.</span>
                </div>

                {error && <div className="error-box">⚠ {error}</div>}

                <button
                  className="cta-btn"
                  disabled={!file}
                  onClick={handleSubmit}
                >
                  Simplify My Document →
                </button>
              </div>
            </section>
          )}

          {/* ── Progress ── */}
          {appState === 'processing' && (
            <section className="progress-section">
              <div className="glass-card" style={{ padding: '32px' }}>
                <p className="section-title">Simplifying your document…</p>
                <div className="step-list">
                  {steps.map(step => (
                    <div className="step-item" key={step.id}>
                      <div className={`step-node ${step.status}`}>
                        {stepIcon(step.status)}
                      </div>
                      <div className="step-content">
                        <p className={`step-label ${step.status === 'waiting' ? 'waiting' : ''}`}>
                          {step.label}
                        </p>
                        <p className="step-desc">{step.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* ── Result ── */}
          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                <h2 className="result-title">Your Simplified Document</h2>
                <span className="deleted-note">🔒 Deleted from servers</span>
              </div>

              {result.doc_type === 'lab_result' ? (
                <LabResultView result={result} />
              ) : result.doc_type === 'appointment_note' ? (
                <AppointmentNoteView result={result} />
              ) : (
                <LegacyResultView result={result as LegacyResult} />
              )}

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
                  ← Simplify another document
                </button>
              </div>
            </section>
          )}

        </div>
      </div>

      {/* Sticky download bar */}
      {appState === 'result' && result && (
        <div className="download-bar">
          <button className="download-btn" onClick={handleDownload}>
            ↓ Download simplified document
          </button>
        </div>
      )}
    </>
  );
}
