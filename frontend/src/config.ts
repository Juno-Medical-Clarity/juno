export const CARE_PLAN_API_PATH = '/care_plan';

export const DEFAULT_VERSION = 'v1-2';

// Static list rendered by VersionsPage. Append a second entry (e.g. v1-3) to add a version later.
export const VERSIONS = [
  {
    id: 'v1-2',
    label: 'Version 1.2',
    description: 'Simplify V1.2 patient note display with clearer appointment sections, warning signs, follow-up questions, and patient-friendly care details.',
    steps: ['Read input', 'Find medical terms', 'Simplify', 'Clarify care details', 'Structure V1.2 note'],
    isDefault: true,
  },
] as const;
