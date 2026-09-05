import { useState, useRef } from 'react';
import type { AppState } from '@main/types/carePlan';
import { useAnonAuth } from '../hooks/useAnonAuth';
import { useTrialJobSnapshot } from '../hooks/useTrialJobSnapshot';
import type { TrialJobDoc } from '../hooks/useTrialJobSnapshot';
import { useUnloadCleanup } from '../hooks/useUnloadCleanup';
import UploadScreen from '../components/UploadScreen';
import ProcessingScreen from '../components/ProcessingScreen';
import ResultScreen from '../components/ResultScreen';
import Footer from '../components/Footer';

export default function TrialPage() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [jobId, setJobId] = useState<string | null>(null);
  // Captured once the live snapshot first reaches a terminal state. Rendering
  // the result screen from this copy (rather than the live jobDoc) is what
  // keeps the screen up after the backend deletes the document — see below.
  const [finalJobDoc, setFinalJobDoc] = useState<TrialJobDoc | null>(null);
  const { authState, retry } = useAnonAuth();
  // Once finalJobDoc is captured there is nothing left to watch: passing null
  // here tears down the Firestore listener (useTrialJobSnapshot's existing,
  // tested unsubscribe-on-null-id path) so a subsequent "document deleted"
  // event from the listener can never null out what we render.
  const { jobDoc, error: snapshotError } = useTrialJobSnapshot(finalJobDoc ? null : jobId);
  const deletedRef = useRef<Set<string>>(new Set());

  useUnloadCleanup(jobId, appState, deletedRef);

  function handleJobCreated(id: string) {
    setJobId(id);
    setAppState('processing');
  }

  if (appState === 'processing' && !finalJobDoc && jobDoc && (jobDoc.status === 'completed' || jobDoc.status === 'error')) {
    setFinalJobDoc(jobDoc);
    setAppState('result');
  }

  function handleRestart() {
    setJobId(null);
    setFinalJobDoc(null);
    setAppState('upload');
  }

  return (
    <div className="trial-page">
      {appState === 'upload' && (
        <UploadScreen authState={authState} onAuthRetry={retry} onJobCreated={handleJobCreated} />
      )}
      {appState === 'processing' && (
        <ProcessingScreen jobDoc={jobDoc} snapshotError={snapshotError} />
      )}
      {appState === 'result' && finalJobDoc && (
        <ResultScreen jobDoc={finalJobDoc} jobId={jobId} deletedRef={deletedRef} onRestart={handleRestart} />
      )}
      <Footer />
    </div>
  );
}
