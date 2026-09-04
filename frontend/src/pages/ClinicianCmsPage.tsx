import { Link } from 'react-router-dom';
import { useState } from 'react';
import './ClinicianDataset.css';
import { searchCms } from '../api/clinicianDataset';
import { ApiError } from '../types/errors';
import { CLINICIAN_DATASET_ROUTE } from '../constants';
import {
  US_STATE_CODES,
  type ClinicianRow,
  type CmsSearchFilters,
} from '../types/clinicianDataset';
import ClinicianResults from './ClinicianResults';

const CMS_LIMIT_MAX = 1500;
const CMS_LIMIT_DEFAULT = 500;

export default function ClinicianCmsPage() {
  const [state, setState] = useState('');
  const [citytown, setCitytown] = useState('');
  const [priSpec, setPriSpec] = useState('');
  const [lastName, setLastName] = useState('');
  const [firstName, setFirstName] = useState('');
  const [facilityName, setFacilityName] = useState('');
  const [zipCode, setZipCode] = useState('');
  const [limit, setLimit] = useState<number>(CMS_LIMIT_DEFAULT);

  const [rows, setRows] = useState<ClinicianRow[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch() {
    setLoading(true);
    setError(null);
    const filters: CmsSearchFilters = {
      limit: Math.min(Math.max(1, limit || CMS_LIMIT_DEFAULT), CMS_LIMIT_MAX),
    };
    if (state) filters.state = state;
    if (citytown.trim()) filters.citytown = citytown.trim();
    if (priSpec.trim()) filters.pri_spec = priSpec.trim();
    if (lastName.trim()) filters.provider_last_name = lastName.trim();
    if (firstName.trim()) filters.provider_first_name = firstName.trim();
    if (facilityName.trim()) filters.facility_name = facilityName.trim();
    if (zipCode.trim()) filters.zip_code = zipCode.trim();

    try {
      const res = await searchCms(filters);
      setRows(res.rows);
      setCount(res.count);
      setHasSearched(true);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : 'Search failed.');
      }
      setRows([]);
      setCount(0);
      setHasSearched(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero-section">
        <Link to={CLINICIAN_DATASET_ROUTE} className="version-table-link">
          ← Clinician Dataset
        </Link>
        <h1>CMS Doctors &amp; Clinicians</h1>

        <div className="clinician-filters glass-card">
          <div className="clinician-filter-grid">
            <div className="clinician-field">
              <label htmlFor="cms-state">State</label>
              <select id="cms-state" value={state} onChange={e => setState(e.target.value)}>
                <option value="">Any</option>
                {US_STATE_CODES.map(code => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-city">City</label>
              <input id="cms-city" type="text" value={citytown}
                onChange={e => setCitytown(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-spec">Primary Specialty</label>
              <input id="cms-spec" type="text" value={priSpec}
                onChange={e => setPriSpec(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-last">Provider Last Name</label>
              <input id="cms-last" type="text" value={lastName}
                onChange={e => setLastName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-first">Provider First Name</label>
              <input id="cms-first" type="text" value={firstName}
                onChange={e => setFirstName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-facility">Facility Name</label>
              <input id="cms-facility" type="text" value={facilityName}
                onChange={e => setFacilityName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-zip">Zip Code</label>
              <input id="cms-zip" type="text" value={zipCode}
                onChange={e => setZipCode(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="cms-limit">Limit (max {CMS_LIMIT_MAX})</label>
              <input id="cms-limit" type="number" min={1} max={CMS_LIMIT_MAX} value={limit}
                onChange={e => setLimit(Number(e.target.value))} />
            </div>
          </div>

          <div className="clinician-actions">
            <button type="button" className="clinician-btn" onClick={handleSearch} disabled={loading}>
              {loading ? 'Searching…' : 'Generate'}
            </button>
          </div>

          {error && <div className="clinician-error">⚠ {error}</div>}
        </div>

        {!error && (
          <ClinicianResults
            rows={rows}
            count={count}
            csvFilename="cms-doctors-clinicians.csv"
            hasSearched={hasSearched}
          />
        )}
      </section>
    </main>
  );
}
