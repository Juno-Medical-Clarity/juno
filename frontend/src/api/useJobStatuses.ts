import { useEffect, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { collection, onSnapshot, query, where } from 'firebase/firestore';
import { firebaseAuth, firebaseDb } from './firebase';
import type { JobStatus } from '../hooks/useJobSnapshot';

/**
 * Subscribes to the current user's care_plan_outputs docs and exposes a live
 * Map of job_id -> status. Consumed by SP3's Sidebar via its optional
 * `processingIds` prop (SP1 → SP3 interface).
 */
export function useJobStatuses(): { statuses: Map<string, JobStatus> } {
  const [statuses, setStatuses] = useState<Map<string, JobStatus>>(new Map());

  useEffect(() => {
    // Re-subscribe whenever the auth state changes (login/logout) so statuses
    // never go stale for the currently signed-in user.
    let unsubscribeSnapshot: (() => void) | null = null;

    const unsubscribeAuth = onAuthStateChanged(firebaseAuth, (user) => {
      // Tear down any subscription tied to the previous user.
      if (unsubscribeSnapshot) {
        unsubscribeSnapshot();
        unsubscribeSnapshot = null;
      }

      if (!user) {
        setStatuses(new Map());
        return;
      }

      const q = query(
        collection(firebaseDb, 'care_plan_outputs'),
        where('uid', '==', user.uid),
      );

      unsubscribeSnapshot = onSnapshot(
        q,
        (snapshot) => {
          const next = new Map<string, JobStatus>();
          snapshot.forEach((docSnap) => {
            const data = docSnap.data();
            next.set(docSnap.id, (data.status as JobStatus) ?? 'completed');
          });
          setStatuses(next);
        },
        () => {
          setStatuses(new Map());
        },
      );
    });

    return () => {
      if (unsubscribeSnapshot) unsubscribeSnapshot();
      unsubscribeAuth();
    };
  }, []);

  return { statuses };
}
