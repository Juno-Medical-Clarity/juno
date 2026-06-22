import { Link } from 'react-router-dom';
import SignOutButton from '../auth/SignOutButton';

export default function NavBar() {
  return (
    <nav className="top-nav" aria-label="Main navigation">
      <div className="top-nav-brand">
        <span className="top-nav-logo">Juno</span>
      </div>
      <div className="top-nav-center">
        <Link to="/" className="top-nav-link">New</Link>
        <Link to="/models" className="top-nav-link">Models</Link>
      </div>
      <div className="top-nav-right">
        <SignOutButton />
      </div>
    </nav>
  );
}
