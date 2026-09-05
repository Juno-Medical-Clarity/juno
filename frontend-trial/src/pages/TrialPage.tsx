import { useState, useRef } from 'react';
import type { AppState } from '@main/types/carePlan';
import { useAnonAuth } from '../hooks/useAnonAuth';
import { useTrialJobSnapshot } from '../hooks/useTrialJobSnapshot';
import { useUnloadCleanup } from '../hooks/useUnloadCleanup';
import UploadScreen from '../components/UploadScreen';
import ProcessingScreen from '../components/ProcessingScreen';
import ResultScreen from '../components/ResultScreen';
import Footer from '../components/Footer';

export default function TrialPage() {
  const [appState, setAppState] = useState<AppState>('upload');
  const [jobId, setJobId] = useState<string | null>(null);
  const { authState, retry } = useAnonAuth();
  const { jobDoc, error: snapshotError } = useTrialJobSnapshot(jobId);
  const deletedRef = useRef<Set<string>>(new Set());

  useUnloadCleanup(jobId, appState, deletedRef);

  function handleJobCreated(id: string) {
    setJobId(id);
    setAppState('processing');
  }

  if (appState === 'processing' && jobDoc && (jobDoc.status === 'completed' || jobDoc.status === 'error')) {
    setAppState('result');
  }

  function handleRestart() {
    setJobId(null);
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
      {appState === 'result' && jobDoc && (
        <ResultScreen jobDoc={jobDoc} jobId={jobId} deletedRef={deletedRef} onRestart={handleRestart} />
      )}
      <Footer />
    </div>
  );
}
