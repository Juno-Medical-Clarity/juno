// Types for the Clinician Dataset feature (NPI Registry + CMS Doctors & Clinicians).

/**
 * Canonical order of the 17 CSV columns. This single constant is the source of
 * truth for BOTH the preview-table headers and the downloaded CSV header/row
 * order. Backend rows are keyed by these exact strings.
 */
export const CLINICIAN_COLUMNS = [
  'NPI',
  'Type',
  'Name',
  'Speciality',
  'Address',
  'City',
  'State',
  'Zip',
  'Website',
  'Phone #',
  'Email',
  'Creds',
  'Why Pilot',
  'EHR',
  'Outreach status',
  'Contact date',
  'Notes',
] as const;

export type ClinicianColumn = (typeof CLINICIAN_COLUMNS)[number];

/** A single result row — every one of the 17 columns keyed by its exact header. */
export type ClinicianRow = Record<ClinicianColumn, string>;

/** Standard search response shared by both datasets. */
export interface ClinicianSearchResponse {
  rows: ClinicianRow[];
  count: number;
}

export type NpiEnumerationType = 'NPI-1' | 'NPI-2';

/** Request body for POST /clinician_dataset/npi/search. All fields optional. */
export interface NpiSearchFilters {
  number?: string;
  enumerationType?: NpiEnumerationType;
  firstName?: string;
  lastName?: string;
  organizationName?: string;
  taxonomyDescription?: string;
  city?: string;
  state?: string;
  postalCode?: string;
  limit?: number;
  skip?: number;
}

/** Request body for POST /clinician_dataset/cms/search. All fields optional. */
export interface CmsSearchFilters {
  state?: string;
  citytown?: string;
  pri_spec?: string;
  provider_last_name?: string;
  provider_first_name?: string;
  facility_name?: string;
  zip_code?: string;
  limit?: number;
  offset?: number;
}

/** US states + DC + territories (2-letter codes) for the State dropdown. */
export const US_STATE_CODES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL',
  'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT',
  'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
  'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
  'DC', 'PR', 'VI', 'GU', 'AS', 'MP',
] as const;
