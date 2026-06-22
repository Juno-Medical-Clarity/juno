import { Navigate, Route, Routes } from 'react-router-dom';
import VersionsPage from './pages/VersionsPage';
import CarePlanPage from './pages/care-plan/CarePlanPage';
import { useAuth } from './auth/AuthContext';
import LoginPage from './pages/LoginPage';
import AuthLayout from './components/AuthLayout';

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
        <Route path="/versions" element={<VersionsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
      {/* CarePlanPage manages its own NavBar */}
      <Route path="/" element={<CarePlanPage />} />
    </Routes>
  );
}
