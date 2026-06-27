export type StepStatus = 'waiting' | 'active' | 'done';
export type DocUrgency = 'normal' | 'caution' | 'concern' | 'urgent';
export type InputMode = 'file' | 'text';
export type AppState = 'upload' | 'processing' | 'result';

export interface PipelineStep {
  id: number;
  label: string;
  description: string;
  status: StepStatus;
}

export interface PatientScoreDimension {
  score: number;
  raw: number;
  label: string;
  unit: string;
}

export interface PatientScore {
  composite: number;
  grade_estimate: number;
  label: string;
  word_count: number;
  low_confidence?: boolean;
  dimensions: {
    grade_level: PatientScoreDimension;
    jargon_density: PatientScoreDimension;
    sentence_complexity: PatientScoreDimension;
    passive_voice: PatientScoreDimension;
    actionability: PatientScoreDimension;
    numeracy_clarity: PatientScoreDimension;
    structural_clarity: PatientScoreDimension;
  };
}

export interface GlossaryTerm {
  definition: string;
  source: string;
  imgUrl?: string | null;
  altText?: string | null;
}

export type TermsMap = Record<string, GlossaryTerm>;

export interface DiagnosisDetail {
  title: string;
  plain_name?: string;
  description: string;
  what_it_means_for_you?: string;
  severity?: 'high' | 'medium' | 'low';
}

export interface Medication {
  title: string;
  plain_name?: string;
  why?: string;
  dosage?: string;
  frequency?: string;
  timing?: string;
  duration?: string;
  instructions?: string;
  side_effects_to_watch?: string;
  importance: 'high' | 'low';
  change?: boolean;
  change_description?: string;
}

export interface WarningSign {
  symptom: string;
  what_it_might_mean?: string;
  what_to_do: string;
  urgency: 'emergency' | 'call_doctor' | 'monitor' | 'normal_side_effect';
  related_to?: string;
  importance: 'high' | 'low';
}

export interface CarePlanContent {
  doc_type: 'care_plan';
  urgency: DocUrgency;
  version: '1.2';
  summary: string;
  reason_for_visit: Array<{ reason: string; description: string }>;
  diagnosis: {
    main_conclusion?: string;
    changed_since_last_visit?: string;
    details: DiagnosisDetail[];
  };
  medications: Medication[];
  tests: Array<{ title: string; plain_name?: string; why?: string; description: string; preparation?: string; importance: 'high' | 'low' }>;
  procedures: Array<{ title: string; plain_name?: string; why?: string; what_to_expect?: string; timeframe?: string; importance: 'high' | 'low' }>;
  other: Array<{ title: string; why?: string; steps?: string[]; description?: string; frequency?: string; duration?: string; importance: 'high' | 'low' }>;
  follow_up: Array<{ time_frame: string; description: string }>;
  warning_signs: WarningSign[];
  questions: string[];
  low_priority: string[];
  note?: string;
  terms?: TermsMap;
  raw?: {
    text: string;
    simplified_text: string;
    clarified_text: string;
  };
  before_score?: PatientScore;
  after_score?: PatientScore;
  additional_info?: string[];
}
