import { authenticatedFetchJson } from './apiClient';
import { API_URL } from './firebase';
import { CLINICIAN_NPI_PATH, CLINICIAN_CMS_PATH } from '../constants';
import type {
  NpiSearchFilters,
  CmsSearchFilters,
  ClinicianSearchResponse,
} from '../types/clinicianDataset';

/**
 * Search the NPI Registry. Throws ApiError (surfacing the backend message) on
 * an error envelope — e.g. the backend rejects a state-only query.
 */
export async function searchNpi(
  filters: NpiSearchFilters,
): Promise<ClinicianSearchResponse> {
  return authenticatedFetchJson<ClinicianSearchResponse>(
    `${API_URL}${CLINICIAN_NPI_PATH}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters),
    },
  );
}

/** Search the CMS Doctors & Clinicians dataset. */
export async function searchCms(
  filters: CmsSearchFilters,
): Promise<ClinicianSearchResponse> {
  return authenticatedFetchJson<ClinicianSearchResponse>(
    `${API_URL}${CLINICIAN_CMS_PATH}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters),
    },
  );
}
