import { firebaseAuth } from './firebase';

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const user = firebaseAuth.currentUser;
  if (!user) {
    throw new Error('You must be signed in to use Juno.');
  }

  const token = await user.getIdToken();
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${token}`);

  return fetch(input, {
    ...init,
    headers,
  });
}
