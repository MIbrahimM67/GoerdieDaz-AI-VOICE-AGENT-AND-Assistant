/**
 * GeordieDaz — Status Indicator
 * Minimal top bar: connection status, active persona, memory button.
 */
import useAppStore from '../stores/appStore';
import { Brain } from 'lucide-react';

export default function StatusIndicator({ onOpenProfile }) {
  const { isConnected, voiceState, currentPersona } = useAppStore();

  const statusDotClass = isConnected
    ? voiceState === 'listening' ? 'listening'
    : voiceState === 'speaking' ? 'speaking'
    : 'connected'
    : 'error';

  const statusText = isConnected
    ? voiceState === 'listening' ? 'Listening'
    : voiceState === 'processing' ? 'Thinking'
    : voiceState === 'speaking' ? 'Speaking'
    : 'Connected'
    : 'Disconnected';

  return (
    <div style={styles.bar} className="glass">
      {/* Left: connection status */}
      <div style={styles.statusGroup}>
        <div className={`status-dot ${statusDotClass}`} />
        <span style={styles.statusText}>{statusText}</span>
      </div>

      {/* Centre: active persona */}
      <div style={styles.personaChip}>
        <div style={{ ...styles.personaDot, background: currentPersona.ui_theme_color }} />
        <span style={styles.personaName}>{currentPersona.name}</span>
      </div>

      {/* Right: memory button */}
      <div style={styles.rightGroup}>
        <button
          onClick={onOpenProfile}
          style={styles.iconBtn}
          title="Core Memory"
          aria-label="Core Memory"
        >
          <Brain size={16} />
        </button>
      </div>
    </div>
  );
}

const styles = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0.625rem 1.25rem',
    borderRadius: 'var(--radius-panel)',
    margin: '0.75rem',
    flexShrink: 0,
    background: 'var(--color-canvas-elevated)',
    border: '1px solid var(--color-border)',
  },
  statusGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    minWidth: 100,
  },
  statusText: {
    fontSize: '0.75rem',
    color: 'var(--color-text-muted)',
    fontWeight: 500,
    letterSpacing: '0.02em',
  },
  personaChip: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    padding: '0.25rem 0.75rem',
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-pill)',
  },
  personaDot: {
    width: 6, height: 6,
    borderRadius: '50%',
  },
  personaName: {
    fontSize: '0.75rem',
    fontWeight: 700,
    color: 'var(--color-accent)',
    letterSpacing: '0.03em',
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    minWidth: 100,
    justifyContent: 'flex-end',
  },
  iconBtn: {
    background: 'transparent',
    border: '1px solid var(--color-border)',
    borderRadius: '6px',
    color: 'var(--color-text-muted)',
    cursor: 'pointer',
    padding: '0.3rem 0.4rem',
    lineHeight: 1,
    transition: 'all 0.2s',
    display: 'flex',
    alignItems: 'center',
  },
};
