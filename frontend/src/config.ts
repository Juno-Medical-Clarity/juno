export { CARE_PLAN_API_PATH, DEFAULT_VERSION } from './constants';

// Static list rendered by ModelsPage. Append a second entry (e.g. v1-3) to add a version later.
export const VERSIONS = [
  {
    id: 'v1-2',
    label: 'Version 1.2',
    description: 'Create a V1.2 care plan with clearer appointment sections, warning signs, follow-up questions, and patient-friendly care details.',
    steps: ['Read input', 'Find medical terms', 'Plain language rewrite', 'Clarify care details', 'Structure V1.2 note'],
    isDefault: true,
  },
] as const;

export const GRADING_VERSIONS = [
  {
    id: 'v1-0',
    label: 'Grading Version 1.0',
    description: 'Multi-method readability and patient health literacy scoring. Computes six individual method scores and a combined composite score.',
    methods: ['SMOG', 'Flesch-Kincaid', 'Dale-Chall', 'PEMAT', 'SAM', 'CDC CCI'],
    isDefault: true,
  },
] as const;

export const GRADING_VERSION_DETAILS = [
  {
    id: 'v1-0',
    label: 'Grading Version 1.0',
    description: 'Multi-method readability and patient health literacy scoring. Computes six individual method scores and a combined composite score.',
    isDefault: true,
    combinedDescription:
      'The composite score is a weighted average of the six method scores, normalized to 0–100. A higher score means higher readability/accessibility. The grade_estimate and label fields describe the approximate reading-grade equivalent.',
    methodDetails: [
      {
        id: 'smog',
        label: 'SMOG',
        description: 'Polysyllabic word count; designed for health materials (McLaughlin 1969).',
        breakdownKeys: ['grade', 'insufficient_sample'],
        docsSlug: 'smog',
      },
      {
        id: 'flesch_kincaid',
        label: 'Flesch-Kincaid',
        description: 'Sentence length × syllable load; Reading Ease + Grade Level (1975).',
        breakdownKeys: ['reading_ease', 'grade_level'],
        docsSlug: 'flesch-kincaid',
      },
      {
        id: 'dale_chall',
        label: 'Dale-Chall',
        description: 'Difficult words outside the 3,000 familiar-word list (1948/1995).',
        breakdownKeys: ['raw_score', 'grade_range'],
        docsSlug: 'dale-chall',
      },
      {
        id: 'pemat',
        label: 'PEMAT',
        description: 'Automated AHRQ approximation: understandability + actionability (2013).',
        breakdownKeys: ['understandability', 'actionability'],
        docsSlug: 'pemat',
      },
      {
        id: 'sam',
        label: 'SAM',
        description: 'Content, literacy demand, and layout/typography domains (Doak et al. 1996).',
        breakdownKeys: ['content', 'literacy_demand', 'layout_typography'],
        docsSlug: 'sam',
      },
      {
        id: 'cdc_cci',
        label: 'CDC CCI',
        description: 'Main message, behavioral recommendations, numbers, call-to-action (CDC).',
        breakdownKeys: ['main_message', 'behavioral_recommendations', 'numbers', 'call_to_action'],
        docsSlug: 'cdc-cci',
      },
    ],
  },
] as const;
