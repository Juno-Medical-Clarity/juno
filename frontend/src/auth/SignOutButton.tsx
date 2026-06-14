import { signOut } from 'firebase/auth';
import { firebaseAuth } from '../api/firebase';

export default function SignOutButton() {
  return (
    <button className="sign-out-button" type="button" onClick={() => void signOut(firebaseAuth)}>
      Sign out
    </button>
  );
}
