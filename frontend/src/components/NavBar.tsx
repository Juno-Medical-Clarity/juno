import { Link, useNavigate } from 'react-router-dom';
import { DEFAULT_VERSION } from '../config';
import { versionPath } from '../router';

interface NavBarProps {
  onNew?: () => void;
}

export default function NavBar({ onNew }: NavBarProps) {
  const navigate = useNavigate();

  function handleNew() {
    if (onNew) {
      onNew();
    } else {
      navigate(versionPath(DEFAULT_VERSION));
    }
  }

  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav-brand">
        <span className="top-nav-logo">Juno</span>
      </div>
      <div className="top-nav-actions">
        <Link to="/versions" className="top-nav-link">
          Versions
        </Link>
        <button className="top-nav-new-btn" onClick={handleNew}>
          + New
        </button>
      </div>
    </nav>
  );
}
