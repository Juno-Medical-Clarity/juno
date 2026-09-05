import { useEffect } from 'react';
import type { AppState } from '@main/types/carePlan';
import { deleteTrialJob } from '../api/trialApi';

export function useUnloadCleanup(
  jobId: string | null,
  appState: AppState,
  deletedRef: React.MutableRefObject<Set<string>>,
): void {
  useEffect(() => {
    if (!jobId || appState === 'upload') return;

    const fireOnce = () => {
      if (deletedRef.current.has(jobId)) return;
      deletedRef.current.add(jobId);
      void deleteTrialJob(jobId).catch(() => { /* best-effort; expires_at is the safety net */ });
    };

    const onVisibilityChange = () => { if (document.visibilityState === 'hidden') fireOnce(); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', fireOnce);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', fireOnce);
    };
  }, [jobId, appState, deletedRef]);
}
