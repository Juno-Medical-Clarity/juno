import { Navigate, Route, Routes } from 'react-router-dom';
import { DEFAULT_VERSION } from './config';
import { versionPath } from './router';
import VersionsPage from './pages/VersionsPage';
import V1Page from './pages/v1/V1Page';
import V1_1Page from './pages/v1_1/V1_1Page';
import V1_2Page from './pages/v1_2/V1_2Page';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
      <Route path="/versions" element={<VersionsPage />} />
      <Route path="/v1" element={<V1Page />} />
      <Route path="/v1-1" element={<V1_1Page />} />
      <Route path="/v1-2" element={<V1_2Page />} />
      <Route path="*" element={<Navigate to={versionPath(DEFAULT_VERSION)} replace />} />
    </Routes>
  );
}
