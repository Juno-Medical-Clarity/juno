import { useState } from 'react';
import type { Grading } from '../types/envelope';
import { groupGradingEntries, combinedScoreLabel } from '../utils/grading';
import type { MethodGroup } from '../utils/grading';

interface OutputGradingCardProps {
  grading: Grading;
  error: string | null;
}

const BREAKDOWN_KEY_ORDER = ['grade_estimate', 'label'];

function sortBreakdownEntries(
  entries: [string, unknown][]
): [string, unknown][] {
  return [...entries].sort(([a], [b]) => {
    const ai = BREAKDOWN_KEY_ORDER.indexOf(a);
    const bi = BREAKDOWN_KEY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
}

function BreakdownKV({ breakdown }: { breakdown: Record<string, unknown> }) {
  const filtered = Object.entries(breakdown).filter(
    ([k, v]) => k !== 'word_count' && (typeof v !== 'object' || v === null)
  );
  const entries = sortBreakdownEntries(filtered);
  return (
    <div className="grading-breakdown">
      {entries.map(([k, v]) => (
        <span key={k} className="grading-breakdown-item">
          <strong>{k.replace(/_/g, ' ')}:</strong> {String(v)}
        </span>
      ))}
    </div>
  );
}

function methodScoreLabel(group: MethodGroup): string {
  const before = group.before ? Math.round(group.before.grade) : null;
  const after = group.after ? Math.round(group.after.grade) : null;
  if (before !== null && after !== null) return `${before} → ${after}`;
  if (after !== null) return `${after}`;
  if (before !== null) return `${before}`;
  return '';
}

export default function OutputGradingCard({ grading }: OutputGradingCardProps) {
  const [topOpen, setTopOpen] = useState(false);
  const [openRows, setOpenRows] = useState<Set<string>>(new Set());

  const groups = groupGradingEntries(grading.entries);
  const allExpanded = topOpen && groups.length > 0 && openRows.size === groups.length;

  function toggleRow(name: string) {
    setOpenRows(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function handleExpandCollapseAll(e: React.MouseEvent) {
    e.stopPropagation();
    if (allExpanded) {
      setOpenRows(new Set());
    } else {
      setOpenRows(new Set(groups.map(g => g.name)));
      setTopOpen(true);
    }
  }

  return (
    <section className="glass-card grading-section">
      <div className="grading-top-row" onClick={() => setTopOpen(o => !o)}>
        <span className="grading-top-label">
          <span className="grading-toggle-icon">{topOpen ? '▼' : '▶'}</span>
          {combinedScoreLabel(groups)}
        </span>
        <button className="grading-collapse-all" onClick={handleExpandCollapseAll}>
          {allExpanded ? 'Collapse All' : 'Expand All'}
        </button>
      </div>

      {topOpen && (
        <>
          {groups.length === 0 ? (
            <p className="grading-empty-note">
              No grading data — click Run Grading to score this output.
            </p>
          ) : (
            groups.map(group => {
              const isOpen = openRows.has(group.name);
              return (
                <div key={group.name} className="grading-method-row">
                  <div
                    className="grading-method-header"
                    onClick={() => toggleRow(group.name)}
                  >
                    <span className="grading-method-label">
                      <span className="grading-toggle-icon">{isOpen ? '▼' : '▶'}</span>
                      {group.label}
                    </span>
                    <span className="grading-method-score">{methodScoreLabel(group)}</span>
                  </div>
                  {isOpen && (
                    <div>
                      {group.before && group.after ? (
                        <>
                          <div className="grading-before-after-block">
                            <div className="grading-target-label">before</div>
                            {group.before.grade_breakdown && (
                              <BreakdownKV breakdown={group.before.grade_breakdown as Record<string, unknown>} />
                            )}
                          </div>
                          <div className="grading-before-after-block">
                            <div className="grading-target-label">after</div>
                            {group.after.grade_breakdown && (
                              <BreakdownKV breakdown={group.after.grade_breakdown as Record<string, unknown>} />
                            )}
                          </div>
                        </>
                      ) : group.before ? (
                        group.before.grade_breakdown && (
                          <BreakdownKV breakdown={group.before.grade_breakdown as Record<string, unknown>} />
                        )
                      ) : group.after ? (
                        group.after.grade_breakdown && (
                          <BreakdownKV breakdown={group.after.grade_breakdown as Record<string, unknown>} />
                        )
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </>
      )}
    </section>
  );
}
