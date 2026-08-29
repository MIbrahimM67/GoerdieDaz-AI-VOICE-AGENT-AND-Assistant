/**
 * GeordieDaz — Error Boundary
 * Prevents uncaught React errors from showing a blank white screen.
 * Displays a graceful fallback UI instead.
 */
import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.card}>
            <div style={styles.icon}>!</div>
            <h2 style={styles.title}>Something went wrong</h2>
            <p style={styles.message}>
              GeordieDaz encountered an unexpected error. This has been logged.
            </p>
            <button onClick={this.handleReload} style={styles.button}>
              Reload App
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--color-canvas)',
    padding: '2rem',
  },
  card: {
    maxWidth: 400,
    textAlign: 'center',
    padding: '3rem 2rem',
    borderRadius: 'var(--radius-panel)',
    background: 'var(--color-canvas-elevated)',
    border: '1px solid var(--color-border)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
  },
  icon: {
    width: 48,
    height: 48,
    borderRadius: '50%',
    background: 'oklch(65% 0.25 25)',
    color: '#fff',
    fontSize: '1.5rem',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    margin: '0 auto 1.5rem',
  },
  title: {
    color: 'var(--color-text-display)',
    marginBottom: '0.75rem',
    fontSize: '1.25rem',
  },
  message: {
    color: 'var(--color-text-muted)',
    fontSize: '0.875rem',
    lineHeight: 1.6,
    marginBottom: '1.5rem',
  },
  button: {
    padding: '0.625rem 1.5rem',
    background: 'var(--color-accent)',
    color: 'var(--color-canvas)',
    border: 'none',
    borderRadius: '8px',
    fontSize: '0.875rem',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'opacity 0.2s',
  },
};
