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
  const [serverState, setServerState] = useState('idle'); // idle | waking | ready
  const [healthCheckAttempts, setHealthCheckAttempts] = useState(0);

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:7860';

  const startServer = async () => {
    setServerState('waking');
    let attempts = 0;
    const poll = async () => {
      attempts++;
      setHealthCheckAttempts(attempts);
      try {
        const res = await fetch(`${API_URL}/health`);
        if (res.ok) {
          setServerState('ready');
          return;
        }
      } catch (err) {
        // Server still sleeping / not reachable
      }
      setTimeout(poll, 5000); // Poll every 5 seconds
    };
    poll();
  };

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
    
    if (serverState === 'ready') {
      const timer = setTimeout(autoLogin, 500);
      return () => clearTimeout(timer);
    }
  }, [serverState, isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) setIsBooting(false);
  }, [isAuthenticated]);

  if (serverState !== 'ready') {
    return (
      <div style={boot}>
        <h1 style={{ color: 'var(--accent)', fontFamily: 'Orbitron, sans-serif', letterSpacing: '0.1em' }}>JARVIS SYSTEM</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '2rem' }}>
          Render Free Tier: The backend server sleeps after inactivity.
        </p>
        
        {serverState === 'idle' ? (
          <button onClick={startServer} style={startBtn}>
            START SERVER
          </button>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
            <div style={bootOrb} />
            <p style={bootLabel}>WAKING SERVER... (ATTEMPT {healthCheckAttempts})</p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>This usually takes 1-2 minutes.</p>
          </div>
        )}
      </div>
    );
  }

  if (isBooting || !isAuthenticated) {
    return (
      <div style={boot}>
        <div style={bootOrb} />
        <p style={bootLabel}>GeordieDaz Auto-login...</p>
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

const startBtn = {
  background: 'rgba(0, 255, 255, 0.1)',
  border: '1px solid var(--accent)',
  color: 'var(--accent)',
  padding: '0.75rem 2rem',
  fontSize: '1rem',
  fontWeight: 'bold',
  letterSpacing: '0.15em',
  textTransform: 'uppercase',
  cursor: 'pointer',
  borderRadius: '4px',
  boxShadow: '0 0 15px rgba(0, 255, 255, 0.2)',
  transition: 'all 0.3s ease',
};
