import { Navigate, Route, Routes } from 'react-router-dom';
import { DEFAULT_VERSION } from './config';
import { versionPath } from './router';
import VersionsPage from './pages/VersionsPage';
import VersionDetailPage from './pages/VersionDetailPage';
import V1Page from './pages/v1/V1Page';
import V1_1Page from './pages/v1_1/V1_1Page';
import V1_2Page from './pages/v1_2/V1_2Page';
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
        <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
        <Route path="/versions" element={<VersionsPage />} />
        <Route path="/version/:id" element={<VersionDetailPage />} />
        <Route path="/v1" element={<V1Page />} />
        <Route path="/v1-1" element={<V1_1Page />} />
        <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
      </Route>
      {/* V1_2Page is outside AuthLayout because it manages its own NavBar */}
      <Route path="/v1-2" element={<V1_2Page />} />
    </Routes>
  );
}
