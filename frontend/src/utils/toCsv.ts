/**
 * Build a CSV string from an ordered list of columns and rows.
 *
 * Each row is an object keyed by the column strings. Values are RFC-4180
 * escaped: any field containing a comma, double-quote, or newline (CR/LF) is
 * wrapped in double quotes and internal double-quotes are doubled. Fields use
 * CRLF line endings. Missing keys render as empty strings.
 */
export function toCsv(
  columns: readonly string[],
  rows: ReadonlyArray<Record<string, string>>,
): string {
  const escapeCell = (value: string): string => {
    if (/[",\r\n]/.test(value)) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  };

  const headerLine = columns.map(escapeCell).join(',');
  const bodyLines = rows.map(row =>
    columns.map(col => escapeCell(row[col] ?? '')).join(','),
  );

  return [headerLine, ...bodyLines].join('\r\n');
}

/**
 * Trigger a client-side download of the given CSV text as a `.csv` file.
 * Mirrors the Blob download pattern used elsewhere in the app.
 */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
