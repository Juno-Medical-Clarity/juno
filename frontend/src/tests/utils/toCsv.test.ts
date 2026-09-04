import { describe, it, expect } from 'vitest';
import { toCsv } from '../../utils/toCsv';
import { CLINICIAN_COLUMNS } from '../../types/clinicianDataset';
import type { ClinicianRow } from '../../types/clinicianDataset';

const COLS = ['NPI', 'Name', 'Notes'] as const;

describe('toCsv', () => {
  it('emits the header row in the given column order', () => {
    const csv = toCsv(COLS, []);
    expect(csv).toBe('NPI,Name,Notes');
  });

  it('emits rows in column order with CRLF line endings', () => {
    const rows = [
      { NPI: '1', Name: 'Alice', Notes: 'x' },
      { NPI: '2', Name: 'Bob', Notes: 'y' },
    ];
    const csv = toCsv(COLS, rows);
    expect(csv).toBe('NPI,Name,Notes\r\n1,Alice,x\r\n2,Bob,y');
  });

  it('quotes and doubles internal quotes', () => {
    const csv = toCsv(COLS, [{ NPI: '1', Name: 'Say "hi"', Notes: '' }]);
    expect(csv).toBe('NPI,Name,Notes\r\n1,"Say ""hi""",');
  });

  it('quotes values containing commas', () => {
    const csv = toCsv(COLS, [{ NPI: '1', Name: 'Smith, John', Notes: '' }]);
    expect(csv).toBe('NPI,Name,Notes\r\n1,"Smith, John",');
  });

  it('quotes values containing newlines', () => {
    const csv = toCsv(COLS, [{ NPI: '1', Name: 'line1\nline2', Notes: '' }]);
    expect(csv).toBe('NPI,Name,Notes\r\n1,"line1\nline2",');
  });

  it('renders missing keys as empty strings', () => {
    const csv = toCsv(COLS, [{ NPI: '1' } as unknown as Record<string, string>]);
    expect(csv).toBe('NPI,Name,Notes\r\n1,,');
  });

  it('produces exactly the 17 canonical clinician headers in order', () => {
    const csv = toCsv(CLINICIAN_COLUMNS, []);
    expect(csv).toBe(
      'NPI,Type,Name,Speciality,Address,City,State,Zip,Website,Phone #,Email,Creds,Why Pilot,EHR,Outreach status,Contact date,Notes',
    );
    expect(CLINICIAN_COLUMNS).toHaveLength(17);
  });

  it('round-trips a full clinician row keyed by the 17 headers', () => {
    const row: ClinicianRow = {
      NPI: '1234567890',
      Type: 'Individual',
      Name: 'Doe, Jane',
      Speciality: 'Family Medicine',
      Address: '1 Main St',
      City: 'Austin',
      State: 'TX',
      Zip: '78701',
      Website: '',
      'Phone #': '512-555-0100',
      Email: '',
      Creds: 'MD',
      'Why Pilot': '',
      EHR: '',
      'Outreach status': '',
      'Contact date': '',
      Notes: '',
    };
    const csv = toCsv(CLINICIAN_COLUMNS, [row]);
    const lines = csv.split('\r\n');
    expect(lines).toHaveLength(2);
    // "Doe, Jane" contains a comma → must be quoted.
    expect(lines[1]).toContain('"Doe, Jane"');
  });
});
