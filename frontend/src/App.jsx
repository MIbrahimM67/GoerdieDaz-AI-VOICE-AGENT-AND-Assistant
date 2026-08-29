/**
 * GeordieDaz — Root Application
 * Auto-authenticates, no login screen.
 */
import { useEffect, useState } from 'react';
import MainInterface from './components/MainInterface';
import { useAuth } from './hooks/useAuth';

export default function App() {
  const { isAuthenticated, user, accessToken, login } = useAuth();
  const [isBooting, setIsBooting] = useState(true);

  useEffect(() => {
    async function autoLogin() {
      if (isAuthenticated) { setIsBooting(false); return; }
      try {
        await login('geordie@geordiedaz.com', 'GeordieDaz2026!');
      } catch (err) {
        console.error('[App] Auto-login failed:', err);
      } finally {
        setIsBooting(false);
      }
    }
    const timer = setTimeout(autoLogin, 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (isAuthenticated) setIsBooting(false);
  }, [isAuthenticated]);

  if (isBooting || !isAuthenticated) {
    return (
      <div style={boot}>
        <div style={bootOrb} />
        <p style={bootLabel}>GeordieDaz</p>
      </div>
    );
  }

  return <MainInterface userId={user.id} accessToken={accessToken} />;
}

const boot = {
  minHeight: '100vh', display: 'flex', flexDirection: 'column',
  alignItems: 'center', justifyContent: 'center', gap: '1.25rem',
  background: 'var(--bg)',
};
const bootOrb = {
  width: 40, height: 40, borderRadius: '50%',
  background: 'var(--accent)',
  opacity: 0.8,
  animation: 'pulse 1.5s ease-in-out infinite',
};
const bootLabel = {
  color: 'var(--text-muted)', fontSize: '0.8125rem',
  fontWeight: 500, letterSpacing: '0.12em', textTransform: 'uppercase',
};
