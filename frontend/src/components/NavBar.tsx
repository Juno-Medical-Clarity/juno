import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import SignOutButton from '../auth/SignOutButton';
import { useAuth } from '../auth/AuthContext';

interface NavBarProps {
  isPublicView?: boolean;
}

export default function NavBar({ isPublicView = false }: NavBarProps) {
  const { user } = useAuth();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let mounted = true;
    if (!user) { setIsAdmin(false); return; }
    user.getIdTokenResult()
      .then(result => { if (mounted) setIsAdmin(result.claims.admin === true); })
      .catch(() => { if (mounted) setIsAdmin(false); });
    return () => { mounted = false; };
  }, [user]);

  if (isPublicView) return null;

  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav-brand">
        <Link to="/" className="top-nav-logo-link">
          <span className="top-nav-logo">Juno</span>
        </Link>
      </div>
      <div className="top-nav-center">
        <Link to="/models" className="top-nav-link">Models</Link>
        <Link to="/docs" className="top-nav-link">Docs</Link>
        {isAdmin && <Link to="/admin" className="top-nav-link">Admin</Link>}
      </div>
      <div className="top-nav-right">
        <Link to="/" className="top-nav-link" aria-label="New care plan">+</Link>
        <SignOutButton />
      </div>
    </nav>
  );
}
