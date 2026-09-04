import { CLINICIAN_COLUMNS } from '../types/clinicianDataset';
import type { ClinicianRow } from '../types/clinicianDataset';
import { toCsv, downloadCsv } from '../utils/toCsv';

interface ClinicianResultsProps {
  rows: ClinicianRow[];
  count: number;
  csvFilename: string;
  /** Whether a search has been run yet (controls the initial empty state). */
  hasSearched: boolean;
}

export default function ClinicianResults({
  rows,
  count,
  csvFilename,
  hasSearched,
}: ClinicianResultsProps) {
  function handleDownloadCsv() {
    const csv = toCsv(CLINICIAN_COLUMNS, rows);
    downloadCsv(csvFilename, csv);
  }

  if (!hasSearched) return null;

  if (rows.length === 0) {
    return (
      <div className="glass-card clinician-empty">
        No results found. Try adjusting your filters.
      </div>
    );
  }

  return (
    <section>
      <div className="clinician-actions">
        <span className="clinician-result-count">
          {count.toLocaleString()} result{count === 1 ? '' : 's'}
          {rows.length < count ? ` (showing ${rows.length.toLocaleString()})` : ''}
        </span>
        <button type="button" className="clinician-btn secondary" onClick={handleDownloadCsv}>
          Download CSV
        </button>
      </div>
      <div className="clinician-table-wrap glass-card">
        <table className="clinician-table">
          <thead>
            <tr>
              {CLINICIAN_COLUMNS.map(col => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={`${row.NPI || 'row'}-${i}`}>
                {CLINICIAN_COLUMNS.map(col => (
                  <td key={col}>{row[col] ?? ''}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
