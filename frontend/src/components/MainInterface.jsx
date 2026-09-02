/**
 * GeordieDaz — Main Interface (JARVIS Holographic HUD)
 * 3-Panel Cinematic Interface:
 * Left: Neural Memory Bank | Center: Holographic Voice Orb Stage | Right: Live Transcript
 */
import { useEffect, useRef, useState } from 'react';
import { Power, AlertTriangle, X, User, RotateCcw, Activity, ShieldAlert, Radio, Sliders } from 'lucide-react';
import BrainPanel from './BrainPanel';
import ConversationLog from './ConversationLog';
import PersonaSwitcher from './PersonaSwitcher';
import VoiceOrb from './VoiceOrb';
import ClientProfileModal from './ClientProfileModal';
import VoiceAccentModal from './VoiceAccentModal';
import { useWebSocket } from '../hooks/useWebSocket';
import { useVoice } from '../hooks/useVoice';
import useAppStore from '../stores/appStore';

export default function MainInterface({ userId, accessToken }) {
  const {
    setError,
    errorMessage,
    clearError,
    voiceState,
    isConnected,
    currentPersona,
    clearCurrentAIResponse,
    setCurrentTranscript,
    clearTurns,
  } = useAppStore();

  const [micError, setMicError] = useState('');
  const [profileOpen, setProfileOpen] = useState(false);
  const [voiceModalOpen, setVoiceModalOpen] = useState(false);
  const [isSessionActive, setIsSessionActive] = useState(true);
  const [sessionSeconds, setSessionSeconds] = useState(0);

  // ── Session Timer ─────────────────────────────────────────────
  useEffect(() => {
    if (!isSessionActive) return;
    const t = setInterval(() => setSessionSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [isSessionActive]);

  // ── Voice Hooks ───────────────────────────────────────────────
  const stopPlaybackRef = useRef(() => {});

  const { sendAudioChunk, sendBargein, sendPersonaSwitch, sendVoiceSwitch, disconnect, reconnect, sendNewSession } = useWebSocket({
    userId,
    token: accessToken,
    onAudioChunk: (b64) => playAudioChunk(b64),
    onBargeIn: () => stopPlaybackRef.current(),
  });

  const { isCapturing, startCapture, stopCapture, playAudioChunk, stopPlayback } = useVoice({
    sendAudioChunk,
    sendBargein,
  });

  stopPlaybackRef.current = stopPlayback;

  // Auto-start microphone stream on load
  useEffect(() => {
    if (!isCapturing && isSessionActive) {
      startCapture().catch(() => setMicError('Mic access denied — click the central orb to activate.'));
    }
  }, []);

  // ── Persona Theme Class Binding ──────────────────────────────
  useEffect(() => {
    if (currentPersona?.id === 'driving_banter') {
      document.body.className = 'persona-driving';
    } else {
      document.body.className = 'persona-geordie';
    }
  }, [currentPersona]);

  // ── Interaction Handlers ─────────────────────────────────────
  const handleActivate = async () => {
    setMicError('');
    try {
      await startCapture();
    } catch (err) {
      setMicError(err.message);
    }
  };

  const handleDeactivate = () => {
    stopCapture();
    stopPlayback();
  };

  const handlePersonaSwitch = (personaId) => {
    const persona = useAppStore.getState().availablePersonas.find((p) => p.id === personaId);
    if (persona) useAppStore.getState().setPersona(persona);
    sendPersonaSwitch(personaId);
  };

  const handleToggleSession = () => {
    if (isSessionActive) {
      stopCapture();
      stopPlayback();
      disconnect();
      clearCurrentAIResponse();
      setCurrentTranscript('');
      setIsSessionActive(false);
    } else {
      reconnect();
      setIsSessionActive(true);
      setSessionSeconds(0);
      setTimeout(() => {
        startCapture().catch(() => setMicError('Click the orb to activate microphone.'));
      }, 800);
    }
  };

  const handleNewConversation = () => {
    clearTurns();
    sendNewSession();
    setSessionSeconds(0);
    // Refresh Neural Memory Bank after summary writes
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('memory-updated'));
    }, 1200);
  };

  const fmtTime = (s) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return `${m}:${sec}`;
  };

  return (
    <div className="jarvis-shell">
      {/* ── JARVIS Command Topbar ──────────────────────────────── */}
      <header className="jarvis-topbar">
        {/* Left: Brand / Logo */}
        <div style={s.brandGroup}>
          <div style={s.reactorCore}>
            <span style={s.reactorDot} />
          </div>
          <div style={s.brandTitles}>
            <span style={s.brandName}>GEORDIEDAZ <span style={{ color: 'var(--accent)' }}>AI</span></span>
            <span style={s.brandSub}>JARVIS HUD // CORE v2.4</span>
          </div>
        </div>

        {/* Center: Persona Switcher & New Session */}
        <div style={s.centerControls}>
          <PersonaSwitcher onSwitch={handlePersonaSwitch} />

          <button
            id="new-convo-btn"
            onClick={handleNewConversation}
            style={s.hudBtn}
            title="Reset Conversation Buffer & Summarize"
          >
            <RotateCcw size={12} color="var(--accent)" />
            <span>NEW CONVERSATION</span>
          </button>

          <button
            id="voice-accent-btn"
            onClick={() => setVoiceModalOpen(true)}
            style={{
              ...s.hudBtn,
              border: '1px solid rgba(0, 240, 255, 0.35)',
              background: 'rgba(0, 240, 255, 0.05)',
            }}
            title="Calibrate ElevenLabs Voice Model & Spoken Accent Dialect"
          >
            <Sliders size={12} color="var(--accent)" />
            <span>VOICE & ACCENT</span>
          </button>
        </div>

        {/* Right: Telemetry & Power */}
        <div style={s.rightControls}>
          {/* Status Badge */}
          <div style={s.statusBadge}>
            <span className={`dot dot--${isSessionActive ? voiceState : 'idle'}`} />
            <span style={s.statusText}>
              {isSessionActive ? voiceState.toUpperCase() : 'OFFLINE'}
            </span>
          </div>

          {/* Session Timer */}
          {isSessionActive && (
            <div style={s.timerBadge}>
              <Activity size={12} color="var(--accent)" />
              <span>{fmtTime(sessionSeconds)}</span>
            </div>
          )}

          {/* Power Switch */}
          <button
            id="session-toggle-btn"
            onClick={handleToggleSession}
            style={{
              ...s.powerBtn,
              borderColor: isSessionActive ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)',
              color: isSessionActive ? 'var(--red)' : 'var(--green)',
              background: isSessionActive ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)',
            }}
            title={isSessionActive ? 'Shutdown System' : 'Boot Core'}
          >
            <Power size={13} strokeWidth={2.5} />
            <span>{isSessionActive ? 'STANDBY' : 'ENGAGE'}</span>
          </button>

          {/* Profile Trigger */}
          <button
            style={s.profileBtn}
            onClick={() => setProfileOpen(true)}
            title="User Profile & Settings"
            aria-label="Open profile"
          >
            <User size={14} color="var(--text-hi)" />
          </button>
        </div>
      </header>

      {/* ── Error Banner Overlay ───────────────────────────────── */}
      {(errorMessage || micError) && (
        <div style={s.errorBanner}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={14} color="var(--red)" />
            <span>{errorMessage || micError}</span>
          </div>
          <button onClick={() => { clearError(); setMicError(''); }} style={s.errorClose}>
            <X size={13} color="var(--red)" />
          </button>
        </div>
      )}

      {/* ── 3-Panel Cockpit HUD ─────────────────────────────── */}
      <main className="jarvis-viewport">
          {/* Left Column: Neural Memory Bank */}
          <BrainPanel />

          {/* Center Column: Holographic Core Stage */}
          <section style={s.centerStage}>
            {/* Top HUD Frame Element */}
            <div style={s.hudHeaderOrnament}>
              <div style={s.ornamentLine} />
              <span style={s.ornamentTitle}>ACOUSTIC SPATIAL SYNAPSE</span>
              <div style={s.ornamentLine} />
            </div>

            {/* Center Canvas Voice Orb */}
            <div style={s.orbWrapper}>
              <VoiceOrb
                onActivate={handleActivate}
                onDeactivate={handleDeactivate}
                disabled={!isSessionActive}
              />
            </div>

            {/* Bottom HUD Spectrum Bar Decorator */}
            <div style={s.spectrumContainer}>
              <div style={s.spectrumGrid}>
                {Array.from({ length: 28 }).map((_, i) => (
                  <span
                    key={i}
                    style={{
                      ...s.spectrumBar,
                      height: voiceState === 'speaking' || voiceState === 'listening'
                        ? `${6 + Math.abs(Math.sin(i * 0.4 + sessionSeconds * 2)) * 22}px`
                        : '4px',
                      opacity: 0.3 + (i % 3) * 0.25,
                    }}
                  />
                ))}
              </div>
              <div style={s.spectrumLegend}>
                <span>FREQ 16.0 kHz</span>
                <span>BUFFER DUPLEX</span>
                <span>NOISE SUPPRESSION: ACTIVE</span>
              </div>
            </div>
          </section>

          {/* Right Column: Conversation Transcript */}
          <ConversationLog />
        </main>

      {/* Modals */}
      <ClientProfileModal isOpen={profileOpen} onClose={() => setProfileOpen(false)} />
      <VoiceAccentModal
        isOpen={voiceModalOpen}
        onClose={() => setVoiceModalOpen(false)}
        onApply={(voiceId, accent) => sendVoiceSwitch(voiceId, accent)}
      />
    </div>
  );
}

const s = {
  brandGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  reactorCore: {
    width: 26,
    height: 26,
    borderRadius: '50%',
    border: '1.5px solid var(--accent)',
    boxShadow: '0 0 12px var(--accent-glow), inset 0 0 8px var(--accent-dim)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  reactorDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: 'var(--accent)',
    boxShadow: '0 0 8px var(--accent)',
  },
  brandTitles: {
    display: 'flex',
    flexDirection: 'column',
  },
  brandName: {
    fontFamily: 'var(--font-hud)',
    fontSize: '0.875rem',
    fontWeight: 800,
    letterSpacing: '0.12em',
    color: 'var(--text-laser)',
  },
  brandSub: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.08em',
  },
  centerControls: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  hudBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    padding: '0.375rem 0.75rem',
    borderRadius: 'var(--r-xs)',
    background: 'rgba(4, 14, 32, 0.75)',
    border: '1px solid var(--border-hud)',
    color: 'var(--text-laser)',
    fontFamily: 'var(--font-hud)',
    fontSize: '0.625rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    cursor: 'pointer',
    transition: 'all var(--t-fast)',
  },
  rightControls: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  statusBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.3rem 0.625rem',
    borderRadius: 'var(--r-xs)',
    background: 'rgba(3, 8, 20, 0.6)',
    border: '1px solid var(--border-hud-subtle)',
  },
  statusText: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.625rem',
    fontWeight: 600,
    color: 'var(--text-body)',
    letterSpacing: '0.08em',
  },
  timerBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6875rem',
    color: 'var(--accent)',
    padding: '0.3rem 0.625rem',
    borderRadius: 'var(--r-xs)',
    background: 'rgba(4, 12, 28, 0.6)',
    border: '1px solid var(--border-hud-subtle)',
  },
  powerBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.375rem',
    padding: '0.375rem 0.75rem',
    borderRadius: 'var(--r-xs)',
    border: '1px solid',
    fontFamily: 'var(--font-hud)',
    fontSize: '0.625rem',
    fontWeight: 700,
    letterSpacing: '0.08em',
    cursor: 'pointer',
    transition: 'all var(--t-fast)',
  },
  profileBtn: {
    width: 30,
    height: 30,
    borderRadius: 'var(--r-xs)',
    background: 'rgba(4, 14, 32, 0.8)',
    border: '1px solid var(--border-hud)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
  },
  errorBanner: {
    margin: '0.5rem 1.25rem 0',
    padding: '0.5rem 0.875rem',
    borderRadius: 'var(--r-xs)',
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.35)',
    color: 'var(--red)',
    fontSize: '0.8125rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    zIndex: 20,
  },
  errorClose: {
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
  },
  centerStage: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '1rem',
    position: 'relative',
  },
  hudHeaderOrnament: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    width: '100%',
    maxWidth: '420px',
  },
  ornamentLine: {
    flex: 1,
    height: 1,
    background: 'linear-gradient(90deg, transparent, var(--border-hud), transparent)',
  },
  ornamentTitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5625rem',
    letterSpacing: '0.14em',
    color: 'var(--text-muted)',
  },
  orbWrapper: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spectrumContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.5rem',
    width: '100%',
    maxWidth: '380px',
  },
  spectrumGrid: {
    display: 'flex',
    alignItems: 'flex-end',
    justifyContent: 'center',
    gap: '4px',
    height: '30px',
  },
  spectrumBar: {
    width: 4,
    background: 'var(--accent)',
    borderRadius: '2px',
    transition: 'height 80ms ease, background var(--t-mid)',
    boxShadow: '0 0 6px var(--accent-glow)',
  },
  spectrumLegend: {
    display: 'flex',
    justifyContent: 'space-between',
    width: '100%',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.5rem',
    color: 'var(--text-muted)',
    letterSpacing: '0.08em',
  },
};
