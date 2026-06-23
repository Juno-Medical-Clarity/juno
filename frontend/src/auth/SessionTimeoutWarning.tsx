import './SessionTimeoutWarning.css';
import { useAuth } from './AuthContext';

export default function SessionTimeoutWarning() {
  const { sessionWarning, extendSession } = useAuth();

  if (!sessionWarning) return null;

  return (
    <div className="session-warning-banner" role="alert" aria-live="assertive">
      <span>Your session will expire in 2 minutes due to inactivity.</span>
      <button type="button" onClick={extendSession}>
        Stay logged in
      </button>
    </div>
  );
}
