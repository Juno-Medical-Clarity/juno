import { useEffect, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { doc, onSnapshot } from 'firebase/firestore';
import { firebaseAuth, firebaseDb } from '../api/firebase';

export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

/**
 * Worker-written error_data dict stored in Firestore on job failure.
 *
 * New rich format (JunoError-classified jobs):
 *   { code, message, user_hint, retryable, detail }
 *
 * Legacy SP2 ErrorDetail format (older jobs):
 *   { code, message, details?, timestamp?, path? }
 *
 * Both formats include `code` and `message`; new fields are optional so
 * the frontend degrades gracefully for docs written before this schema.
 */
export type JobErrorData = {
  /** Canonical error code, e.g. "LLM_MAX_TOKENS" */
  code: string;
  /** Developer-facing description of the error. */
  message: string;
  /** User-facing actionable hint (new rich format). */
  user_hint?: string;
  /** Whether a retry of the same request is likely to succeed (new rich format). */
  retryable?: boolean;
  /** Exception string or extra technical context (new rich format). */
  detail?: string;
  /** Legacy SP2 ErrorDetail field — specific detail string. */
  details?: string;
  /** Legacy SP2 ErrorDetail field — ISO-8601 UTC timestamp. */
  timestamp?: string;
  /** Legacy SP2 ErrorDetail field — request path; null for worker errors. */
  path?: string | null;
};

export interface JobDoc {
  status: JobStatus;
  stage: number | null;
  output_data: Record<string, unknown> | null;
  error_data: JobErrorData | null;
  name: string;
  batch_run_id: string | null;
  shared: boolean;
  comment: string;
  trace_id: string | null;
  session_id: string | null;
}

export function useJobSnapshot(jobId: string | null): {
  jobDoc: JobDoc | null;
  loading: boolean;
  error: Error | null;
} {
  const [jobDoc, setJobDoc] = useState<JobDoc | null>(null);
  const [loading, setLoading] = useState(jobId !== null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJobDoc(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);

    let unsubscribeSnapshot: (() => void) | null = null;
    let currentUser: string | null = null; // track last known uid to avoid spurious re-subscriptions

    const subscribeToSnapshot = () => {
      unsubscribeSnapshot = onSnapshot(
        doc(firebaseDb, 'care_plan_outputs', jobId),
        (snapshot) => {
          if (!snapshot.exists()) {
            setJobDoc(null);
            setError(null);
            setLoading(false);
            return;
          }
          const data = snapshot.data();
          setJobDoc({
            status: (data.status as JobStatus) ?? 'completed',
            stage: data.stage ?? null,
            output_data: data.output_data ?? null,
            error_data: data.error_data ?? null,
            name: data.name ?? '',
            batch_run_id: data.batch_run_id ?? null,
            shared: data.shared ?? false,
            comment: data.comment ?? '',
            trace_id: data.trace_id ?? null,
            session_id: data.session_id ?? null,
          });
          setLoading(false);
        },
        (err) => {
          setError(err);
          setLoading(false);
        },
      );
    };

    const unsubscribeAuth = onAuthStateChanged(firebaseAuth, (firebaseUser) => {
      const newUserId = firebaseUser?.uid ?? null;
      if (newUserId === currentUser && unsubscribeSnapshot) {
        // Auth state didn't change meaningfully; keep existing subscription.
        return;
      }
      currentUser = newUserId;

      if (unsubscribeSnapshot) {
        unsubscribeSnapshot();
        unsubscribeSnapshot = null;
      }
      // Clear stale data before re-subscribing so private content is not
      // left in the UI when the user signs out or switches accounts.
      setJobDoc(null);
      setError(null);
      subscribeToSnapshot();
    });

    return () => {
      if (unsubscribeSnapshot) unsubscribeSnapshot();
      unsubscribeAuth();
    };
  }, [jobId]);

  return { jobDoc, loading, error };
}
