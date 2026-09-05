import { useEffect } from 'react';
import type { AppState } from '@main/types/carePlan';
import { deleteTrialJob } from '../api/trialApi';

// PRD .dev/trial-simplify/03-trial-frontend/PRD.md §4.13 originally wired the
// DELETE trigger to visibilitychange->hidden for ANY non-upload appState, to
// cover mobile Safari (which may not reliably fire pagehide/unload). That
// reasoning didn't account for the ordinary case of a user switching tabs,
// minimizing the window, or locking their phone screen while their job is
// still running in the background: visibilitychange->hidden fires on all of
// those too, so it was deleting perfectly healthy, still-processing jobs out
// from under the user. The result was left permanently stuck (see
// useTrialJobSnapshot's `exists` handling / ProcessingScreen's "session
// ended" state for what happens client-side once the doc is gone).
//
// visibilitychange->hidden is now only wired up once appState === 'result':
// by then the user has already seen their care plan and there is nothing
// left to lose by cleaning up. While appState === 'processing' we deliberately
// do NOT delete on backgrounding — an abandoned processing job is instead
// caught by the backend's TTL (`expires_at`, set from
// Constants.Trial.JOB_TTL_HOURS in backend/routes/trial.py), which is the
// real safety net for "user closed the tab and never came back".
//
// window.pagehide still fires unconditionally for any non-upload appState:
// unlike visibilitychange, pagehide fires only on genuine navigation-away/
// teardown (including bfcache eviction), so it's safe to treat as "the user
// is done with this tab" regardless of processing vs result.
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

    const onVisibilityChange = () => {
      if (appState === 'result' && document.visibilityState === 'hidden') fireOnce();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', fireOnce);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', fireOnce);
    };
  }, [jobId, appState, deletedRef]);
}
