import { useEffect, useState } from 'react';
import { doc, onSnapshot } from 'firebase/firestore';
import { firebaseDb } from '../api/firebase';
import type { FirestoreJobError } from '@main/types/errors';

export type JobStatus = 'not_started' | 'processing' | 'completed' | 'error';

export interface TrialJobDoc {
  status: JobStatus;
  stage: number | null;
  output_data: Record<string, unknown> | null;
  error_data: FirestoreJobError | null;
  name: string;
}

export function useTrialJobSnapshot(jobId: string | null): {
  jobDoc: TrialJobDoc | null;
  loading: boolean;
  error: Error | null;
} {
  const [jobDoc, setJobDoc] = useState<TrialJobDoc | null>(null);
  const [loading, setLoading] = useState(jobId !== null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!jobId) {
      // Resetting local snapshot state here is synchronizing with the Firestore
      // listener lifecycle (torn down/not started because there's no jobId), not
      // deriving state from a prop — the documented exception to this rule. See
      // https://react.dev/learn/you-might-not-need-an-effect#subscribing-to-an-external-store
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setJobDoc(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);

    const unsubscribe = onSnapshot(
      doc(firebaseDb, 'care_plan_outputs', jobId),
      (snapshot) => {
        if (!snapshot.exists()) {
          setJobDoc(null);
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
        });
        setLoading(false);
      },
      (err) => {
        setError(err);
        setLoading(false);
      },
    );

    return unsubscribe;
  }, [jobId]);

  return { jobDoc, loading, error };
}
