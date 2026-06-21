export { CARE_PLAN_API_PATH, DEFAULT_VERSION } from './constants';

// Static list rendered by VersionsPage. Append a second entry (e.g. v1-3) to add a version later.
export const VERSIONS = [
  {
    id: 'v1-2',
    label: 'Version 1.2',
    description: 'Create a V1.2 care plan with clearer appointment sections, warning signs, follow-up questions, and patient-friendly care details.',
    steps: ['Read input', 'Find medical terms', 'Plain language rewrite', 'Clarify care details', 'Structure V1.2 note'],
    isDefault: true,
  },
] as const;
