import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string,
};

export const firebaseApp = initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);

// Guard against a missing/misconfigured VITE_API_PROCESSING_URL (edge-case
// review #6). Left unset, `${API_URL}/trial/jobs` becomes the literal string
// "undefined/trial/jobs" — a same-origin relative path that 404s against the
// static hosting bucket instead of reaching the backend, surfacing to a
// developer debugging a fresh deployment as nothing more than a generic
// "Request failed: 404 Not Found" with no hint of what's actually wrong. Fail
// loudly here instead, at module load, well before any request is made.
const rawApiUrl = import.meta.env.VITE_API_PROCESSING_URL as string | undefined;
if (!rawApiUrl) {
  const message =
    'VITE_API_PROCESSING_URL is not set. Configure it in .env.local (see .env.example) before building or running the trial app.';
  console.error(message);
  throw new Error(message);
}
// Strip any trailing slash so a value like "https://host/" doesn't produce a
// double slash ("https://host//trial/jobs") that most route tables 404 on.
export const API_URL = rawApiUrl.replace(/\/+$/, '');

const firestoreDatabaseId = import.meta.env.VITE_FIRESTORE_DATABASE_ID as string | undefined;
export const firebaseDb = firestoreDatabaseId
  ? getFirestore(firebaseApp, firestoreDatabaseId)
  : getFirestore(firebaseApp);
