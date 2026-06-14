import './V1_1Page.css';
import { useCallback, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { API_URL } from '../../api/firebase';
import MedicalTerm from '../../components/MedicalTerm';

type StepStatus = 'waiting' | 'active' | 'done';
type UrgencyLevel = 'immediate' | 'soon' | 'routine' | 'informational';
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
    category: string;
    why: string;
  }[];
  low_priority: string[];
  follow_ups: string[];
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

const CATEGORY_ICONS: Record<string, string> = {
  medication: '💊',
  appointment: '📅',
  lifestyle: '🏃',
  monitoring: '📊',
  test: '🧪',
  referral: '👨‍⚕️',
  home_instruction: '🏠',
  warning_sign: '⚠️',
};

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
    sections.push(`${h2('Summary')}<p style="color:#374151;line-height:1.6;margin:0;">${escapeHtml(result.summary)}</p>`);
  }

  if (result.what_happened) {
    const whatHappened = result.what_happened;
    sections.push(`${h2('What Happened')}
      ${whatHappened.date ? `<p style="color:#6B7280;margin:0 0 4px 0;"><strong>Date:</strong> ${escapeHtml(whatHappened.date)}</p>` : ''}
      ${whatHappened.reason ? `<p style="color:#374151;margin:0 0 4px 0;">${escapeHtml(whatHappened.reason)}</p>` : ''}
      <p style="color:#374151;margin:0;">${escapeHtml(whatHappened.summary)}</p>`);
  }

  if (result.what_to_do.length > 0) {
    const items = result.what_to_do.map(action =>
      `<div style="padding:8px 12px;margin-bottom:6px;background:#F9FAFB;border-radius:6px;">
        <strong>[${escapeHtml(action.urgency.toUpperCase())}]</strong> ${escapeHtml(action.text)}
        ${action.why ? `<br><span style="color:#6B7280;font-size:13px;">${escapeHtml(action.why)}</span>` : ''}
      </div>`,
    ).join('');
    sections.push(`${h2('What To Do')}${items}`);
  }

  if (result.what_it_means) {
    const whatItMeans = result.what_it_means;
    const findings = whatItMeans.findings.map(finding =>
      `<div style="padding:6px 12px;margin-bottom:4px;background:#F0FDF4;border-radius:6px;">
        <span style="color:#166534;font-weight:600;">[${escapeHtml(finding.urgency.toUpperCase())}]</span> ${escapeHtml(finding.item)}
      </div>`,
    ).join('');
    sections.push(`${h2('What It Means')}
      ${whatItMeans.headline ? `<p style="color:#374151;font-weight:500;margin:0 0 8px 0;">${escapeHtml(whatItMeans.headline)}</p>` : ''}
      ${findings}`);
  }

  if (result.low_priority.length > 0) {
    const items = result.low_priority.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    sections.push(`${h2('Other Items')}<ul style="margin:0;padding-left:20px;color:#6B7280;">${items}</ul>`);
  }

  if (result.follow_ups.length > 0) {
    const items = result.follow_ups.map(followUp => `<li>${escapeHtml(followUp)}</li>`).join('');
    sections.push(`${h2('Follow-Ups')}<ul style="margin:0;padding-left:20px;color:#374151;">${items}</ul>`);
  }

  if (result.terms && Object.keys(result.terms).length > 0) {
    const items = Object.entries(result.terms).map(([term, glossary]) =>
      `<div style="margin-bottom:6px;"><strong>${escapeHtml(term)}:</strong> <span style="color:#6B7280;">${escapeHtml(glossary.definition)}</span></div>`,
    ).join('');
    sections.push(`${h2('Medical Terms Glossary')}${items}`);
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

function UrgencyChip({ urgency }: { urgency: string }) {
  return <span className={`urgency-chip urgency-chip-${urgency}`}>{urgency}</span>;
}

function WhyToggle({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div className="why-wrapper">
      <button className="why-btn" onClick={() => setOpen(current => !current)}>
        {open ? 'Less ▲' : 'Why? ▼'}
      </button>
      {open && <div className="why-content">{text}</div>}
    </div>
  );
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

function AppointmentNoteV11View({ result }: { result: AppointmentNote }) {
  const terms = result.terms ?? {};
  const withTerms = (text: string) => renderTextWithTerms(text, terms);

  return (
    <div className="result-cards">
      {result.before_score && result.after_score && (
        <ReadabilityCard before={result.before_score} after={result.after_score} />
      )}

      {result.summary && (
        <div className="result-card">
          <div className="result-card-body" style={{ paddingTop: '16px' }}>
            <p className="summary-paragraph">{withTerms(result.summary)}</p>
          </div>
        </div>
      )}

      <ResultCard color="blue" icon="📅" title="What Happened">
        {result.what_happened.date && <p className="narrative-date">{result.what_happened.date}</p>}
        {result.what_happened.reason && <p className="narrative-reason">{withTerms(result.what_happened.reason)}</p>}
        <p className="narrative-summary">{withTerms(result.what_happened.summary)}</p>
      </ResultCard>

      {result.what_to_do.length > 0 && (
        <ResultCard color="violet" icon="✅" title="What To Do">
          <div className="action-list">
            {result.what_to_do.map((action, index) => (
              <div key={index} className="action-row-with-why">
                <div className="action-row">
                  <span className="action-category-icon">{CATEGORY_ICONS[action.category] ?? '•'}</span>
                  <div className="action-content">
                    <UrgencyChip urgency={action.urgency} />
                    <span className="action-text">{withTerms(action.text)}</span>
                  </div>
                </div>
                <WhyToggle text={action.why} />
              </div>
            ))}
          </div>
        </ResultCard>
      )}

      <ResultCard color="teal" icon="🔍" title="What It Means">
        {result.what_it_means.headline && (
          <p className="narrative-headline">{withTerms(result.what_it_means.headline)}</p>
        )}
        <div className="findings-list">
          {result.what_it_means.findings.map((finding, index) => (
            <div key={index} className="finding-row">
              <div className="finding-header">
                <UrgencyChip urgency={finding.urgency} />
                <span className="finding-text">{withTerms(finding.item)}</span>
              </div>
            </div>
          ))}
        </div>
      </ResultCard>

      {result.low_priority.length > 0 && (
        <ResultCard color="gray" icon="ℹ️" title="Other Items From Your Visit" collapsible defaultOpen={false}>
          <ul className="result-list">
            {result.low_priority.map((item, index) => <li key={index}>{withTerms(item)}</li>)}
          </ul>
        </ResultCard>
      )}

      {result.follow_ups.length > 0 && (
        <ResultCard color="blue" icon="📅" title="Follow-Ups">
          <ul className="result-list">
            {result.follow_ups.map((followUp, index) => <li key={index}>{followUp}</li>)}
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

export default function V1_1Page() {
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
      const response = await fetch(`${API_URL}/simplify/v1-1`, {
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
                <Link to="/versions" style={{ color: 'var(--accent-violet)', textDecoration: 'none' }}>v1.1</Link>
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

              <AppointmentNoteV11View result={result} />

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
