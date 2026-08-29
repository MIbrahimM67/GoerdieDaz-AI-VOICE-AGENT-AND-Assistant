/**
 * GeordieDaz — Conversation Transcript (JARVIS HUD Panel)
 * Live streaming dialogue feed with high-tech speech bubbles,
 * realtime typing indicators, and persona timestamps.
 */
import { useEffect, useRef } from 'react';
import { MessageSquare, Radio, User, Sparkles, Terminal } from 'lucide-react';
import useAppStore from '../stores/appStore';
import ToolActivity from './ToolActivity';

export default function ConversationLog() {
  const { turns, currentUserTranscript, currentAIResponse, voiceState } = useAppStore();
  const bottomRef = useRef(null);

  // Auto-scroll on new turns or live streaming
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns, currentUserTranscript, currentAIResponse]);

  return (
    <div className="hud-card" style={s.panel}>
      {/* ── Panel Header ────────────────────────────────────────── */}
      <div style={s.header}>
        <div style={s.headerTitleWrap}>
          <div style={s.iconGlow}>
            <Terminal size={15} color="var(--accent)" strokeWidth={2.2} />
          </div>
          <div>
            <h2 className="hud-title" style={s.title}>Conversation Transcript</h2>
            <div style={s.subtitle}>
              <span style={{ ...s.liveDot, background: voiceState === 'speaking' ? 'var(--cyan-core)' : voiceState === 'listening' ? 'var(--green)' : 'var(--accent)' }} />
              <span>LIVE AUDIO LINK</span>
            </div>
          </div>
        </div>

        <div style={s.badge}>
          <span>{turns.length} TURNS</span>
        </div>
      </div>

      {/* ── Chat Stream Area ───────────────────────────────────── */}
      <div style={s.scrollArea}>
        {turns.length === 0 && !currentUserTranscript && !currentAIResponse && (
          <div style={s.emptyState}>
            <Radio size={26} color="var(--text-muted)" style={{ opacity: 0.4 }} />
            <p style={s.emptyTitle}>COMMS CHANNEL OPEN</p>
            <p style={s.emptyDesc}>Activate microphone to begin real-time dialogue with GeordieDaz.</p>
          </div>
        )}

        {/* Historic Turns */}
        {turns.map((t, idx) => {
          const isUser = t.role === 'user';
          return (
            <div
              key={idx}
              style={{
                ...s.turnRow,
                justifyContent: isUser ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  ...s.bubble,
                  ...(isUser ? s.userBubble : s.aiBubble),
                }}
              >
                {/* Speaker Label */}
                <div style={s.bubbleHeader}>
                  <span style={isUser ? s.userLabel : s.aiLabel}>
                    {isUser ? 'YOU' : 'GEORDIEDAZ'}
                  </span>
                  {t.timestamp && (
                    <span style={s.timeTag}>
                      {new Date(t.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  )}
                </div>

                {/* Message Content */}
                <p style={s.bubbleText}>{t.content}</p>
              </div>
            </div>
          );
        })}

        {/* Live User Speech Bubble */}
        {currentUserTranscript && (
          <div style={{ ...s.turnRow, justifyContent: 'flex-end' }}>
            <div style={{ ...s.bubble, ...s.userBubble, borderColor: 'var(--green)', boxShadow: '0 0 15px rgba(16, 185, 129, 0.2)' }}>
              <div style={s.bubbleHeader}>
                <span style={{ ...s.userLabel, color: 'var(--green)' }}>YOU (SPEAKING...)</span>
              </div>
              <p style={s.bubbleText}>{currentUserTranscript}</p>
            </div>
          </div>
        )}

        {/* Live AI Streaming Bubble */}
        {currentAIResponse && (
          <div style={{ ...s.turnRow, justifyContent: 'flex-start' }}>
            <div style={{ ...s.bubble, ...s.aiBubble, borderColor: 'var(--accent)', boxShadow: '0 0 20px var(--accent-dim)' }}>
              <div style={s.bubbleHeader}>
                <span style={s.aiLabel}>GEORDIEDAZ (TRANSMITTING...)</span>
                <span style={s.streamingPulse} />
              </div>
              <p style={s.bubbleText}>{currentAIResponse}</p>
            </div>
          </div>
        )}

        {/* Tool Activity Animation */}
        <ToolActivity />

        <div ref={bottomRef} style={{ height: 4 }} />
      </div>

      {/* ── Footer Telemetry ────────────────────────────────────── */}
      <div style={s.footer}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ ...s.signalBar, height: 6 }} />
          <span style={{ ...s.signalBar, height: 10 }} />
          <span style={{ ...s.signalBar, height: 14 }} />
          <span style={s.footerCodec}>WEBSOCKET DUPLEX // FULL-DUPLEX</span>
        </div>
        <span style={s.footerLatency}>LATENCY: &lt;150ms</span>
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
    boxShadow: '0 0 6px var(--accent)',
  },
  badge: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.625rem',
    color: 'var(--accent)',
    background: 'var(--accent-dim)',
    padding: '2px 6px',
    borderRadius: 'var(--r-xs)',
    border: '1px solid var(--border-hud)',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '0.875rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.75rem',
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
  turnRow: {
    display: 'flex',
    width: '100%',
  },
  bubble: {
    maxWidth: '92%',
    borderRadius: 'var(--r-sm)',
    padding: '0.625rem 0.875rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
    border: '1px solid',
    backdropFilter: 'blur(10px)',
  },
  userBubble: {
    background: 'rgba(0, 180, 216, 0.12)',
    borderColor: 'rgba(0, 240, 255, 0.35)',
    borderBottomRightRadius: '2px',
  },
  aiBubble: {
    background: 'rgba(4, 14, 32, 0.85)',
    borderColor: 'var(--border-hud)',
    borderLeftWidth: '3px',
    borderLeftColor: 'var(--accent)',
    borderBottomLeftRadius: '2px',
  },
  bubbleHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '0.75rem',
  },
  userLabel: {
    fontFamily: 'var(--font-hud)',
    fontSize: '0.5625rem',
    fontWeight: 700,
    color: 'var(--cyan-core)',
    letterSpacing: '0.06em',
  },
  aiLabel: {
    fontFamily: 'var(--font-hud)',
    fontSize: '0.5625rem',
    fontWeight: 700,
    color: 'var(--accent)',
    letterSpacing: '0.06em',
  },
  timeTag: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
  },
  bubbleText: {
    fontSize: '0.8125rem',
    color: 'var(--text-hi)',
    lineHeight: 1.45,
    wordBreak: 'break-word',
  },
  streamingPulse: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: 'var(--accent)',
    boxShadow: '0 0 8px var(--accent)',
    animation: 'laserPulse 0.8s infinite',
  },
  footer: {
    padding: '0.5rem 0.75rem',
    borderTop: '1px solid var(--border-hud-subtle)',
    background: 'rgba(2, 6, 16, 0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  signalBar: {
    width: 2.5,
    background: 'var(--accent)',
    borderRadius: 1,
    display: 'inline-block',
  },
  footerCodec: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  footerLatency: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
  },
};
