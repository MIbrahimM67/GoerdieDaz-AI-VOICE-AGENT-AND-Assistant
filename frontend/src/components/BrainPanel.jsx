/**
 * GeordieDaz — Neural Memory Bank (JARVIS HUD Panel)
 * Displays long-term categorized memories, real-time facts,
 * and episodic session recollections in a frosted glass HUD card.
 */
import { useEffect, useState } from 'react';
import { Brain, RefreshCw, Database, Clock, Sparkles, User, ShieldCheck } from 'lucide-react';
import useAppStore from '../stores/appStore';

const API_BASE = '';

const CATEGORY_STYLES = {
  semantic:   { label: 'FACT',       color: 'var(--cyan-core)', bg: 'var(--cyan-dim)' },
  preference: { label: 'PREF',       color: 'var(--green)',     bg: 'rgba(16, 185, 129, 0.12)' },
  episodic:   { label: 'SESSION',    color: 'var(--amber)',     bg: 'rgba(255, 158, 0, 0.12)' },
  default:    { label: 'MEMORY',     color: 'var(--text-body)', bg: 'rgba(255,255,255,0.06)' },
};

export default function BrainPanel() {
  const { currentPersona, accessToken } = useAppStore();
  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchMemories = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/memory/brain`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMemories(data.memories || []);
        setLastRefresh(new Date());
      }
    } catch (e) {
      console.warn('[Brain] Failed to fetch memories:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMemories();
    const interval = setInterval(fetchMemories, 12000);
    return () => clearInterval(interval);
  }, [accessToken]);

  return (
    <div className="hud-card" style={s.panel}>
      {/* ── Panel Header ────────────────────────────────────────── */}
      <div style={s.header}>
        <div style={s.headerTitleWrap}>
          <div style={s.iconGlow}>
            <Brain size={16} color="var(--accent)" strokeWidth={2.2} />
          </div>
          <div>
            <h2 className="hud-title" style={s.title}>Neural Memory Bank</h2>
            <div style={s.subtitle}>
              <span style={s.liveDot} />
              <span>PERSISTENT CORTEX</span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={s.countBadge}>{memories.length} ENTRIES</span>
          <button
            style={s.refreshBtn}
            onClick={fetchMemories}
            title="Force Neural Sync"
            aria-label="Refresh memories"
          >
            <RefreshCw
              size={12}
              color="var(--accent)"
              style={{ animation: loading ? 'ringRotateClockwise 0.8s linear infinite' : 'none' }}
            />
          </button>
        </div>
      </div>

      {/* ── Memory List Readout ─────────────────────────────────── */}
      <div style={s.scrollArea}>
        {memories.length === 0 ? (
          <div style={s.emptyState}>
            <Database size={24} color="var(--text-muted)" style={{ opacity: 0.5 }} />
            <p style={s.emptyTitle}>NO MEMORY NODES ACTIVE</p>
            <p style={s.emptyDesc}>Speak with Daz to register facts, vehicles, preferences, and personal context.</p>
          </div>
        ) : (
          memories.map((m, idx) => {
            const cat = CATEGORY_STYLES[m.memory_type] || CATEGORY_STYLES.default;
            return (
              <div key={m.id || idx} style={s.memoryNode}>
                {/* Node Top: Category & Key */}
                <div style={s.nodeTop}>
                  <span style={{ ...s.catTag, color: cat.color, background: cat.bg, borderColor: cat.color }}>
                    {cat.label}
                  </span>
                  <span style={s.nodeKey} title={m.entity_key}>
                    {m.entity_key || 'cortex.entry'}
                  </span>
                  {m.confidence && (
                    <span style={s.nodeConfidence}>
                      {(m.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>

                {/* Node Content */}
                <p style={s.nodeContent}>{m.content}</p>

                {/* Node Footer: Timestamp */}
                <div style={s.nodeFooter}>
                  <Clock size={10} color="var(--text-muted)" />
                  <span style={s.nodeDate}>
                    {m.updated_at ? new Date(m.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'SYNCED'}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Panel Telemetry Footer ──────────────────────────────── */}
      <div style={s.footer}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <ShieldCheck size={11} color="var(--green)" />
          <span style={s.footerStatus}>POSTGRES VECTOR (pgvector) ACTIVE</span>
        </div>
        <span style={s.footerSync}>
          {lastRefresh ? `SYNC: ${lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'SYNCING...'}
        </span>
      </div>
    </div>
  );
}

const s = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    borderRadius: 'var(--r-md)',
  },
  header: {
    padding: '0.875rem 1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottom: '1px solid var(--border-hud-subtle)',
    background: 'rgba(3, 8, 22, 0.4)',
  },
  headerTitleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.625rem',
  },
  iconGlow: {
    width: 28,
    height: 28,
    borderRadius: 'var(--r-xs)',
    background: 'var(--accent-dim)',
    border: '1px solid var(--border-hud)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 0 10px var(--accent-dim)',
  },
  title: {
    fontSize: '0.75rem',
    color: 'var(--text-laser)',
    margin: 0,
  },
  subtitle: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.5625rem',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
    letterSpacing: '0.08em',
  },
  liveDot: {
    width: 4,
    height: 4,
    borderRadius: '50%',
    background: 'var(--accent)',
    boxShadow: '0 0 6px var(--accent)',
  },
  countBadge: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.625rem',
    fontWeight: 600,
    color: 'var(--accent)',
    background: 'var(--accent-dim)',
    padding: '2px 6px',
    borderRadius: 'var(--r-xs)',
    border: '1px solid var(--border-hud)',
  },
  refreshBtn: {
    width: 24,
    height: 24,
    borderRadius: 'var(--r-xs)',
    border: '1px solid var(--border-hud)',
    background: 'rgba(0, 240, 255, 0.05)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all var(--t-fast)',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '0.75rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    padding: '2rem 1rem',
    textAlign: 'center',
    gap: '0.5rem',
  },
  emptyTitle: {
    fontFamily: 'var(--font-hud)',
    fontSize: '0.6875rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    color: 'var(--text-muted)',
  },
  emptyDesc: {
    fontSize: '0.75rem',
    color: 'var(--text-muted)',
    maxWidth: '200px',
    lineHeight: 1.4,
  },
  memoryNode: {
    background: 'rgba(4, 12, 28, 0.65)',
    border: '1px solid var(--border-hud-subtle)',
    borderRadius: 'var(--r-sm)',
    padding: '0.625rem 0.75rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.375rem',
    transition: 'border-color var(--t-fast), background var(--t-fast)',
  },
  nodeTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '0.5rem',
  },
  catTag: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    fontWeight: 700,
    letterSpacing: '0.05em',
    padding: '1px 5px',
    borderRadius: 2,
    border: '1px solid',
  },
  nodeKey: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.625rem',
    color: 'var(--text-muted)',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  nodeConfidence: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--green)',
  },
  nodeContent: {
    fontSize: '0.8125rem',
    color: 'var(--text-hi)',
    lineHeight: 1.4,
    wordBreak: 'break-word',
  },
  nodeFooter: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    marginTop: '2px',
  },
  nodeDate: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
  },
  footer: {
    padding: '0.5rem 0.75rem',
    borderTop: '1px solid var(--border-hud-subtle)',
    background: 'rgba(2, 6, 16, 0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  footerStatus: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  footerSync: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
  },
};
