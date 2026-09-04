import { Link } from 'react-router-dom';
import { useState } from 'react';
import './ClinicianDataset.css';
import { searchNpi } from '../api/clinicianDataset';
import { ApiError } from '../types/errors';
import { CLINICIAN_DATASET_ROUTE } from '../constants';
import {
  US_STATE_CODES,
  type ClinicianRow,
  type NpiSearchFilters,
  type NpiEnumerationType,
} from '../types/clinicianDataset';
import ClinicianResults from './ClinicianResults';

const NPI_LIMIT_MAX = 200;
const NPI_LIMIT_DEFAULT = 200;

export default function ClinicianNpiPage() {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [taxonomyDescription, setTaxonomyDescription] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [number, setNumber] = useState('');
  const [enumerationType, setEnumerationType] = useState<'' | NpiEnumerationType>('');
  const [limit, setLimit] = useState<number>(NPI_LIMIT_DEFAULT);

  const [rows, setRows] = useState<ClinicianRow[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch() {
    setLoading(true);
    setError(null);
    const filters: NpiSearchFilters = {
      limit: Math.min(Math.max(1, limit || NPI_LIMIT_DEFAULT), NPI_LIMIT_MAX),
    };
    if (firstName.trim()) filters.firstName = firstName.trim();
    if (lastName.trim()) filters.lastName = lastName.trim();
    if (organizationName.trim()) filters.organizationName = organizationName.trim();
    if (taxonomyDescription.trim()) filters.taxonomyDescription = taxonomyDescription.trim();
    if (city.trim()) filters.city = city.trim();
    if (state) filters.state = state;
    if (postalCode.trim()) filters.postalCode = postalCode.trim();
    if (number.trim()) filters.number = number.trim();
    if (enumerationType) filters.enumerationType = enumerationType;

    try {
      const res = await searchNpi(filters);
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
        <h1>NPI Registry</h1>

        <div className="clinician-filters glass-card">
          <div className="clinician-filter-grid">
            <div className="clinician-field">
              <label htmlFor="npi-first">First Name</label>
              <input id="npi-first" type="text" value={firstName}
                onChange={e => setFirstName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-last">Last Name</label>
              <input id="npi-last" type="text" value={lastName}
                onChange={e => setLastName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-org">Organization Name</label>
              <input id="npi-org" type="text" value={organizationName}
                onChange={e => setOrganizationName(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-tax">Taxonomy Description</label>
              <input id="npi-tax" type="text" value={taxonomyDescription}
                onChange={e => setTaxonomyDescription(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-city">City</label>
              <input id="npi-city" type="text" value={city}
                onChange={e => setCity(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-state">State</label>
              <select id="npi-state" value={state} onChange={e => setState(e.target.value)}>
                <option value="">Any</option>
                {US_STATE_CODES.map(code => (
                  <option key={code} value={code}>{code}</option>
                ))}
              </select>
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-zip">Postal Code</label>
              <input id="npi-zip" type="text" value={postalCode}
                onChange={e => setPostalCode(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-number">NPI Number</label>
              <input id="npi-number" type="text" value={number}
                onChange={e => setNumber(e.target.value)} />
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-enum">Enumeration Type</label>
              <select id="npi-enum" value={enumerationType}
                onChange={e => setEnumerationType(e.target.value as '' | NpiEnumerationType)}>
                <option value="">Any</option>
                <option value="NPI-1">Individual (NPI-1)</option>
                <option value="NPI-2">Organization (NPI-2)</option>
              </select>
            </div>
            <div className="clinician-field">
              <label htmlFor="npi-limit">Limit (max {NPI_LIMIT_MAX})</label>
              <input id="npi-limit" type="number" min={1} max={NPI_LIMIT_MAX} value={limit}
                onChange={e => setLimit(Number(e.target.value))} />
            </div>
          </div>

          <div className="clinician-actions">
            <button type="button" className="clinician-btn" onClick={handleSearch} disabled={loading}>
              {loading ? 'Searching…' : 'Search'}
            </button>
          </div>

          {error && <div className="clinician-error">⚠ {error}</div>}
        </div>

        {!error && (
          <ClinicianResults
            rows={rows}
            count={count}
            csvFilename="npi-registry.csv"
            hasSearched={hasSearched}
          />
        )}
      </section>
    </main>
  );
}
