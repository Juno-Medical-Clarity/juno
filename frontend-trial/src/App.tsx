// TEMPORARY — replaced by the real router in Task 18. Exists only to prove the
// @main alias resolves and type-checks across the tsc -b project boundary
// (PRD §4.4) before any real screen is written.
import CarePlanView from '@main/components/CarePlanView';
import type { SimplifiedCarePlan, Grading } from '@main/types/envelope';

const EMPTY_CARE_PLAN: SimplifiedCarePlan = {
  doc_type: 'care_plan',
  urgency: 'normal',
  version: '1.2',
  summary: '',
  reason_for_visit: [],
  diagnosis: { details: [] },
  medications: [],
  tests: [],
  procedures: [],
  other: [],
  follow_up: [],
  warning_signs: [],
  questions: [],
  low_priority: [],
};
const EMPTY_GRADING: Grading = { entries: [], enabled: false, graded_at: null };

export default function App() {
  return <CarePlanView result={EMPTY_CARE_PLAN} grading={EMPTY_GRADING} />;
}
