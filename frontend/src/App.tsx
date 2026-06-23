import { Navigate, Route, Routes } from 'react-router-dom';
import ModelsPage from './pages/ModelsPage';
import GradingVersionDetailPage from './pages/GradingVersionDetailPage';
import CarePlanPage from './pages/care-plan/CarePlanPage';
import CarePlanJobPage from './pages/care-plan/CarePlanJobPage';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import AuthLayout from './components/AuthLayout';
import DocsPage from './pages/docs/DocsPage';
import AlgorithmDocPage from './pages/docs/AlgorithmDocPage';

export default function App() {
  const { user, loading } = useAuth();

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

  if (!user) {
    return <LoginPage />;
  }

  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/models/grading/:versionId" element={<GradingVersionDetailPage />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="/docs/grading/:slug" element={<AlgorithmDocPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
      {/* CarePlanPage manages its own NavBar */}
      <Route path="/" element={<CarePlanPage />} />
      {/* CarePlanJobPage — async job status / result view */}
      <Route path="/carePlan/:id" element={<CarePlanJobPage />} />
    </Routes>
  );
}
