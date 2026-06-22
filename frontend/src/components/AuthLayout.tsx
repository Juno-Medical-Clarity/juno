import { Outlet } from 'react-router-dom';
import NavBar from './NavBar';
import SessionTimeoutWarning from '../auth/SessionTimeoutWarning';

export default function AuthLayout() {
  return (
    <>
      <NavBar />
      <SessionTimeoutWarning />
      <Outlet />
    </>
  );
}
