/**
 * GeordieDaz — Login / Register Page
 * Premium dark glass design with animated form toggle.
 */
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || 'Something went wrong';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = () => {
    setEmail('geordie@geordiedaz.com');
    setPassword('GeordieDaz2026!');
  };

  return (
    <div className="content-layer" style={styles.page}>
      {/* Background glow orb (Hallmark Atmospheric bloom) */}
      <div className="atmospheric-bloom" />

      <div style={styles.card}>
        {/* Logo */}
        <div style={styles.logoArea}>
          <div style={styles.logo}>GD</div>
          <h1 style={styles.title}>GeordieDaz</h1>
          <p style={styles.subtitle}>Your AI Mate from Newcastle</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>Email</label>
            <input
              style={styles.input}
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <input
              style={styles.input}
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
            />
          </div>

          {error && <div style={styles.errorBox}>{error}</div>}

          <button
            type="submit"
            disabled={loading}
            id="auth-submit-btn"
            style={styles.primaryBtn}
          >
            {loading ? <span style={styles.spinner} /> : 'Sign In'}
          </button>
        </form>

        {/* Demo account shortcut */}
        <div style={styles.demoArea}>
          <div style={styles.divider} />
          <button onClick={fillDemo} style={styles.demoBtn} id="demo-login-btn">
            Use Demo Account
          </button>
          <p style={styles.demoHint}>geordie@geordiedaz.com · GeordieDaz2026!</p>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 'var(--space-4)',
  },
  card: {
    width: '100%',
    maxWidth: 400,
    borderRadius: 'var(--radius-panel)',
    padding: 'var(--space-8)',
    position: 'relative',
    zIndex: 1,
    background: 'var(--color-canvas-elevated)',
    border: '1px solid var(--color-border)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
  },
  logoArea: {
    textAlign: 'center',
    marginBottom: 'var(--space-8)',
  },
  logo: {
    width: 64, height: 64,
    borderRadius: 'var(--radius-pill)',
    background: 'var(--color-accent)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-canvas)',
    margin: '0 auto var(--space-4)',
    boxShadow: '0 0 32px var(--color-accent-glow)',
  },
  title: {
    color: 'var(--color-text-display)',
    marginBottom: 'var(--space-2)',
  },
  subtitle: {
    fontSize: '0.875rem',
    color: 'var(--color-text-muted)',
  },
  tabs: {
    display: 'flex',
    background: 'var(--color-canvas)',
    borderRadius: 'var(--radius-pill)',
    padding: 4,
    marginBottom: 'var(--space-6)',
    border: '1px solid var(--color-border)',
  },
  tab: {
    flex: 1,
    padding: 'var(--space-2)',
    borderRadius: 'var(--radius-pill)',
    border: '1px solid transparent',
    background: 'transparent',
    color: 'var(--color-text-muted)',
    fontSize: '0.875rem',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  tabActive: {
    background: 'var(--color-canvas-elevated)',
    color: 'var(--color-text-display)',
    fontWeight: 600,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  label: {
    fontSize: '0.875rem',
    fontWeight: 500,
    color: 'var(--color-text-muted)',
  },
  input: {
    padding: 'var(--space-3) var(--space-4)',
    background: 'var(--color-canvas)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--space-2)',
    color: 'var(--color-text-body)',
    fontFamily: 'inherit',
    fontSize: '1rem',
    outline: 'none',
  },
  errorBox: {
    padding: 'var(--space-3) var(--space-4)',
    borderRadius: 'var(--space-2)',
    background: 'oklch(from var(--color-accent) l c h / 0.15)',
    border: '1px solid oklch(from var(--color-accent) l c h / 0.3)',
    color: 'var(--color-accent)',
    fontSize: '0.875rem',
  },
  spinner: {
    display: 'inline-block',
    width: 18, height: 18,
    border: '2px solid rgba(0,0,0,0.3)',
    borderTopColor: 'var(--color-canvas)',
    borderRadius: 'var(--radius-pill)',
    animation: 'spin 0.7s linear infinite',
  },
  primaryBtn: {
    width: '100%',
    marginTop: 'var(--space-2)',
    padding: 'var(--space-3) var(--space-4)',
    background: 'var(--color-accent)',
    color: 'var(--color-canvas)',
    border: 'none',
    borderRadius: 'var(--space-2)',
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  demoArea: {
    marginTop: 'var(--space-6)',
    textAlign: 'center',
  },
  divider: {
    height: 1,
    background: 'var(--color-border)',
    marginBottom: 'var(--space-4)',
  },
  demoBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    color: 'var(--color-text-body)',
    borderRadius: 'var(--radius-pill)',
    padding: 'var(--space-2) var(--space-4)',
    fontSize: '0.875rem',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  demoHint: {
    fontSize: '0.75rem',
    color: 'var(--color-text-muted)',
    marginTop: 'var(--space-2)',
  },
};
