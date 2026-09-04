import { Link } from 'react-router-dom';
import './ClinicianDataset.css';
import { CLINICIAN_NPI_ROUTE, CLINICIAN_CMS_ROUTE } from '../constants';

export default function ClinicianDatasetPage() {
  return (
    <main className="app-shell">
      <section className="hero-section">
        <h1>Clinician Dataset</h1>
        <p className="clinician-intro">
          Search public clinician registries, preview the results, and export a
          standardized 17-column CSV for outreach. Choose a data source below.
        </p>
        <div className="clinician-cards">
          <Link to={CLINICIAN_NPI_ROUTE} className="clinician-card glass-card">
            <div className="clinician-card-title">NPI Registry</div>
            <div className="clinician-card-desc">
              Search the national NPI registry by name, organization, taxonomy,
              location, or NPI number.
            </div>
            <span className="clinician-card-arrow">Search NPI Registry →</span>
          </Link>
          <Link to={CLINICIAN_CMS_ROUTE} className="clinician-card glass-card">
            <div className="clinician-card-title">CMS Doctors &amp; Clinicians</div>
            <div className="clinician-card-desc">
              Search the CMS Doctors &amp; Clinicians dataset by specialty, name,
              facility, and location.
            </div>
            <span className="clinician-card-arrow">Search CMS Data →</span>
          </Link>
        </div>
      </section>
    </main>
  );
}
