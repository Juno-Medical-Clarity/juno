import { useEffect, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { doc, onSnapshot } from 'firebase/firestore';
import { firebaseAuth, firebaseDb } from '../api/firebase';
import type { ApiErrorDetail } from '../types/errors';

export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

/**
 * Worker-written error_data follows the SP2 ErrorDetail shape (code, message,
 * details, timestamp, path). details/timestamp/path are optional here because
 * older docs may have been written with just {code, message}.
 */
export type JobErrorData = Pick<ApiErrorDetail, 'code' | 'message'> &
  Partial<Pick<ApiErrorDetail, 'details' | 'timestamp' | 'path'>>;

export interface JobDoc {
  status: JobStatus;
  stage: number | null;
  output_data: Record<string, unknown> | null;
  error_data: JobErrorData | null;
  name: string;
  batch_run_id: string | null;
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

    const unsubscribeAuth = onAuthStateChanged(firebaseAuth, (user) => {
      if (unsubscribeSnapshot) {
        unsubscribeSnapshot();
        unsubscribeSnapshot = null;
      }

      if (!user) {
        setJobDoc(null);
        setLoading(false);
        return;
      }

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
          });
          setLoading(false);
        },
        (err) => {
          setError(err);
          setLoading(false);
        },
      );
    });

    return () => {
      if (unsubscribeSnapshot) unsubscribeSnapshot();
      unsubscribeAuth();
    };
  }, [jobId]);

  return { jobDoc, loading, error };
}
