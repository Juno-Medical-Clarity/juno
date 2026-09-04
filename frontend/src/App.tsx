import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import ModelsPage from './pages/ModelsPage';
import GradingVersionDetailPage from './pages/GradingVersionDetailPage';
import ClinicianDatasetPage from './pages/ClinicianDatasetPage';
import ClinicianNpiPage from './pages/ClinicianNpiPage';
import ClinicianCmsPage from './pages/ClinicianCmsPage';
import CarePlanPage from './pages/care-plan/CarePlanPage';
import CarePlanJobPage from './pages/care-plan/CarePlanJobPage';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import AuthLayout from './components/AuthLayout';
import DocsPage from './pages/docs/DocsPage';
import AlgorithmDocPage from './pages/docs/AlgorithmDocPage';
import AdminRoute from './components/AdminRoute';
import AdminPage from './pages/AdminPage';
import ErrorBoundary from './components/ErrorBoundary';

export default function App() {
  const { user, loading } = useAuth();
  const location = useLocation();
  const isCarePlanRoute = /^\/carePlan\//.test(location.pathname);

  if (loading) {
    return (
      <main className="auth-page">
        <div className="auth-card glass-card">
          <p className="eyebrow">Juno</p>
          <h1>Loading...</h1>
        </div>
      </main>
    );
  }

  if (!user && !isCarePlanRoute) {
    return <LoginPage />;
  }

  return (
    <ErrorBoundary fallback={<div style={{ padding: '40px', textAlign: 'center' }}>A fatal error occurred. Please refresh.</div>}>
      <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/models/grading/:versionId" element={<GradingVersionDetailPage />} />
          <Route path="/docs" element={<DocsPage />} />
          <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
          <Route path="/clinician-dataset" element={<ClinicianDatasetPage />} />
          <Route path="/clinician-dataset/npi" element={<ClinicianNpiPage />} />
          <Route path="/clinician-dataset/cms" element={<ClinicianCmsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
        {/* CarePlanPage manages its own NavBar */}
        <Route path="/" element={<CarePlanPage />} />
        {/* CarePlanJobPage — async job status / result view */}
        <Route path="/carePlan/:id" element={
          <ErrorBoundary>
            <CarePlanJobPage />
          </ErrorBoundary>
        } />
        {/* Admin — requires admin custom claim */}
        <Route element={<AdminRoute />}>
          <Route path="/admin" element={<AdminPage />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
