// config.ts - single source of truth for version routing
// To change the default version, update VITE_DEFAULT_VERSION in .env files
// and set SIMPLIFY_DEFAULT_VERSION on the backend to match.

export const DEFAULT_VERSION = import.meta.env.VITE_DEFAULT_VERSION ?? 'v1';

export const VERSIONS = [
  {
    id: 'v1',
    label: 'Version 1',
    path: '/v1',
    description: 'Original pipeline. Supports provider notes, appointment summaries, lab results, and DOCX files.',
    steps: ['Read', 'Classify', 'Simplify', 'Define', 'Clarify', 'Structure'],
    apiPath: '/simplify/v1',
    isDefault: DEFAULT_VERSION === 'v1',
  },
  {
    id: 'v1-1',
    label: 'Version 1.1',
    path: '/v1-1',
    description: 'Improved pipeline. Supports provider notes and SOAP notes only (no lab results). Uses a curated medical term database for safer, more consistent simplification. Adds a hover/tap medical term glossary. Text input supported.',
    steps: ['Read input', 'Find medical terms', 'Simplify', 'Structure appointment summary', 'Render glossary'],
    apiPath: '/simplify/v1-1',
    isDefault: DEFAULT_VERSION === 'v1-1',
  },
  {
    id: 'v1-2',
    label: 'Version 1.2',
    path: '/v1-2',
    description: 'Simplify V1.2 patient note display with clearer appointment sections, warning signs, follow-up questions, and patient-friendly care details.',
    steps: ['Read input', 'Find medical terms', 'Simplify', 'Clarify care details', 'Structure V1.2 note'],
    apiPath: '/simplify/v1-2',
    isDefault: DEFAULT_VERSION === 'v1-2',
  },
] as const;
