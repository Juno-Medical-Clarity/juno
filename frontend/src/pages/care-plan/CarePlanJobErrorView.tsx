import NavBar from '../../components/NavBar';
import type { FirestoreJobError } from '../../types/errors';

interface CarePlanJobErrorViewProps {
  errorData: FirestoreJobError | null;
  sessionId: string | null;
  traceId: string | null;
  isPublicView: boolean;
}

export default function CarePlanJobErrorView({
  errorData,
  sessionId,
  traceId,
  isPublicView,
}: CarePlanJobErrorViewProps) {
  // Prefer user_hint (new rich format) over message for user-facing text
  const userMessage = errorData?.user_hint ?? errorData?.message ?? 'An error occurred processing your care plan.';
  const errorCode = errorData?.code ?? null;
  const devMessage = errorData?.message ?? null;
  const retryable = errorData?.retryable ?? false;
  // Technical detail string from FirestoreJobError.
  const technicalDetail = errorData?.details ?? null;
  const sessionLogUrl = sessionId
    ? `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D"${sessionId}";project=juno-medical-clarity`
    : null;
  const traceUrl = traceId
    ? `https://console.cloud.google.com/traces/list?project=juno-medical-clarity&tid=${traceId}`
    : null;

  return (
    <>
      {!isPublicView && <NavBar />}
      <div style={{ padding: '80px 32px', maxWidth: '640px', margin: '0 auto' }}>
        {/* Primary user-facing error message */}
        <div style={{ textAlign: 'center', color: 'var(--error, #DC2626)', fontWeight: 500, marginBottom: '16px' }}>
          {userMessage}
        </div>

        {/* Error code badge */}
        {errorCode && (
          <div style={{ textAlign: 'center', marginBottom: '8px' }}>
            <code style={{
              background: 'var(--surface-2, #f3f4f6)',
              padding: '2px 10px',
              borderRadius: '4px',
              fontSize: '0.75rem',
              color: 'var(--text-secondary)',
              fontFamily: 'monospace',
            }}>
              {errorCode}
            </code>
          </div>
        )}

        {/* Retryable indicator */}
        {errorData && (
          <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
            Retryable: {retryable ? 'Yes' : 'No'}
          </div>
        )}

        {/* Developer-facing message (muted, italic) */}
        {devMessage && (
          <div style={{
            textAlign: 'center',
            fontSize: '0.73rem',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
            marginBottom: '16px',
            lineHeight: '1.5',
          }}>
            {devMessage}
          </div>
        )}

        {/* Technical detail — collapsible monospace box */}
        {technicalDetail && (
          <details style={{ marginTop: '12px', textAlign: 'left' }}>
            <summary style={{
              fontSize: '0.75rem',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              userSelect: 'none',
            }}>
              Technical detail
            </summary>
            <pre style={{
              marginTop: '8px',
              padding: '12px',
              background: 'var(--surface-2, #f3f4f6)',
              borderRadius: '6px',
              fontSize: '0.7rem',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: '200px',
              overflowY: 'auto',
              color: 'var(--text-secondary)',
              fontFamily: 'monospace',
            }}>
              {technicalDetail}
            </pre>
          </details>
        )}

        {/* Session ID and Trace ID links */}
        {(sessionId || traceId) && (
          <div style={{ marginTop: '24px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.75rem', lineHeight: '1.8' }}>
            {sessionId && (
              <div>
                Session ID:{' '}
                {sessionLogUrl
                  ? <a href={sessionLogUrl} target="_blank" rel="noopener noreferrer">{sessionId}</a>
                  : sessionId}
              </div>
            )}
            <div>
              Trace ID:{' '}
              {traceId && traceUrl
                ? <a href={traceUrl} target="_blank" rel="noopener noreferrer">{traceId}</a>
                : '—'}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
