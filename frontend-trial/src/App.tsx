import { Routes, Route, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import TrialPage from './pages/TrialPage';
import PrivacyPage from './pages/PrivacyPage';
import TermsPage from './pages/TermsPage';
import { trackEvent } from './analytics/ga';

function usePageViewTracking(): void {
  const location = useLocation();
  useEffect(() => {
    trackEvent({ name: 'page_view', params: { page_path: location.pathname, page_title: document.title } });
  }, [location.pathname]);
}

export default function App() {
  usePageViewTracking();
  return (
    <Routes>
      <Route path="/" element={<TrialPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="*" element={<TrialPage />} />
    </Routes>
  );
}
