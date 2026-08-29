/**
 * GeordieDaz — Persona Switcher (JARVIS HUD Mode Selector)
 */
import useAppStore from '../stores/appStore';

export default function PersonaSwitcher({ onSwitch }) {
  const { currentPersona, availablePersonas } = useAppStore();
  if (!availablePersonas.length) return null;

  return (
    <div style={s.track} role="radiogroup" aria-label="Select persona">
      {availablePersonas.map((p) => {
        const active = p.id === currentPersona.id;
        const color = p.id === 'driving_banter' ? '#ff9e00' : '#00f0ff';
        return (
          <button
            key={p.id}
            id={`persona-btn-${p.id}`}
            role="radio"
            aria-checked={active}
            onClick={() => onSwitch(p.id)}
            style={{
              ...s.btn,
              background: active ? 'rgba(0, 240, 255, 0.12)' : 'transparent',
              color: active ? 'var(--text-laser)' : 'var(--text-muted)',
              borderColor: active ? color : 'transparent',
              boxShadow: active ? `0 0 12px ${color}30` : 'none',
            }}
            title={p.description}
          >
            <span style={{
              ...s.dot,
              background: active ? color : 'var(--text-muted)',
              boxShadow: active ? `0 0 8px ${color}` : 'none',
            }} />
            {p.name.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}

const s = {
  track: {
    display: 'flex',
    background: 'rgba(3, 8, 20, 0.75)',
    border: '1px solid var(--border-hud)',
    borderRadius: 'var(--r-xs)',
    padding: 2,
    gap: 2,
    backdropFilter: 'blur(10px)',
  },
  btn: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.45rem',
    padding: '0.3rem 0.75rem',
    borderRadius: 'var(--r-xs)',
    border: '1px solid transparent',
    fontFamily: 'var(--font-hud)',
    fontSize: '0.625rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    transition: 'all var(--t-mid)',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  dot: {
    width: 5,
    height: 5,
    borderRadius: '50%',
    flexShrink: 0,
    transition: 'all var(--t-mid)',
  },
};
