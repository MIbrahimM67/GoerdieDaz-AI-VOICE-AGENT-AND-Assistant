/**
 * GeordieDaz — Jarvis Holographic Voice Orb (Canvas Engine)
 * Renders multi-layered rotating HUD rings, audio-reactive pulses, 
 * and floating particle vortex matching Iron Man JARVIS aesthetics.
 */
import { useEffect, useRef } from 'react';
import useAppStore from '../stores/appStore';
import { Mic, MicOff, Volume2, Cpu, AlertCircle } from 'lucide-react';

const STATE_CONFIG = {
  idle:        { label: 'STANDBY // CLICK TO ACTIVATE', color: '#00f0ff', dim: 'rgba(0, 240, 255, 0.15)', speed: 0.005, particles: 25 },
  ready:       { label: 'VOICE ONLINE // LISTENING',    color: '#10b981', dim: 'rgba(16, 185, 129, 0.20)', speed: 0.015, particles: 45 },
  listening:   { label: 'CAPTURING AUDIO...',           color: '#10b981', dim: 'rgba(16, 185, 129, 0.30)', speed: 0.025, particles: 60 },
  processing:  { label: 'NEURAL PROCESSING...',         color: '#ff9e00', dim: 'rgba(255, 158, 0, 0.25)',  speed: 0.035, particles: 55 },
  speaking:    { label: 'TRANSMITTING VOICE...',        color: '#00d4ff', dim: 'rgba(0, 212, 255, 0.35)',  speed: 0.030, particles: 70 },
  interrupted: { label: 'INTERRUPTED',                  color: '#ff9e00', dim: 'rgba(255, 158, 0, 0.20)',  speed: 0.010, particles: 20 },
  disconnected:{ label: 'OFFLINE',                     color: '#50678a', dim: 'rgba(80, 103, 138, 0.10)', speed: 0.002, particles: 10 },
};

export default function VoiceOrb({ onActivate, onDeactivate, disabled }) {
  const canvasRef = useRef(null);
  const { voiceState, isMicActive, isConnected } = useAppStore();

  let stateKey = voiceState;
  if (!isConnected || disabled) stateKey = 'disconnected';
  else if (voiceState === 'idle' && isMicActive) stateKey = 'ready';

  const cfg = STATE_CONFIG[stateKey] || STATE_CONFIG.idle;
  const canClick = !disabled && isConnected;

  // ── HTML5 Canvas Hologram Loop ──────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;
    let angle = 0;

    // Initialize particle cloud
    const count = cfg.particles;
    const particles = Array.from({ length: count }, () => ({
      r: 30 + Math.random() * 55,
      theta: Math.random() * Math.PI * 2,
      size: 1 + Math.random() * 2.2,
      speed: (0.004 + Math.random() * 0.01) * (Math.random() > 0.5 ? 1 : -1),
      alpha: 0.2 + Math.random() * 0.7,
    }));

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      angle += cfg.speed;

      // 1. Central Radial Glow
      const glowGrad = ctx.createRadialGradient(cx, cy, 10, cx, cy, 95);
      glowGrad.addColorStop(0, cfg.dim);
      glowGrad.addColorStop(0.7, 'rgba(0,0,0,0)');
      ctx.fillStyle = glowGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 95, 0, Math.PI * 2);
      ctx.fill();

      // 2. Outer Dashed Ring (Clockwise)
      ctx.save();
      ctx.strokeStyle = cfg.color;
      ctx.lineWidth = 1.5;
      ctx.globalAlpha = 0.45;
      ctx.setLineDash([8, 12]);
      ctx.beginPath();
      ctx.arc(cx, cy, 98, angle, angle + Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // 3. Segmented HUD Outer Ring (Counter-Clockwise)
      ctx.save();
      ctx.strokeStyle = cfg.color;
      ctx.lineWidth = 2.5;
      ctx.globalAlpha = 0.75;
      ctx.setLineDash([35, 25, 10, 25]);
      ctx.beginPath();
      ctx.arc(cx, cy, 84, -angle * 1.5, -angle * 1.5 + Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // 4. Tick Marks Circle
      ctx.save();
      ctx.strokeStyle = cfg.color;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.3;
      const numTicks = 24;
      for (let i = 0; i < numTicks; i++) {
        const a = (i / numTicks) * Math.PI * 2 + angle * 0.5;
        const x1 = cx + Math.cos(a) * 70;
        const y1 = cy + Math.sin(a) * 70;
        const x2 = cx + Math.cos(a) * 75;
        const y2 = cy + Math.sin(a) * 75;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      ctx.restore();

      // 5. Pulsing Core Hologram Sphere
      const pulse = 1 + (stateKey === 'speaking' || stateKey === 'listening' ? Math.sin(Date.now() * 0.008) * 0.08 : 0);
      const coreGrad = ctx.createRadialGradient(cx, cy, 5, cx, cy, 55 * pulse);
      coreGrad.addColorStop(0, cfg.color);
      coreGrad.addColorStop(0.5, cfg.dim);
      coreGrad.addColorStop(1, 'rgba(0,0,0,0.1)');
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 55 * pulse, 0, Math.PI * 2);
      ctx.fill();

      // 6. Particle Energy Field
      particles.forEach((p) => {
        p.theta += p.speed;
        const px = cx + Math.cos(p.theta) * p.r * pulse;
        const py = cy + Math.sin(p.theta) * p.r * pulse;
        ctx.fillStyle = cfg.color;
        ctx.globalAlpha = p.alpha;
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [cfg, stateKey]);

  const handleClick = () => {
    if (!canClick) return;
    if (isMicActive) onDeactivate?.();
    else onActivate?.();
  };

  return (
    <div style={styles.container}>
      {/* Telemetry Header Badge */}
      <div style={styles.telemetryTag}>
        <span style={{ ...styles.radarDot, background: cfg.color, boxShadow: `0 0 8px ${cfg.color}` }} />
        <span style={{ ...styles.telemetryText, color: cfg.color }}>{cfg.label}</span>
      </div>

      {/* Central Canvas Orb with Interactive Trigger */}
      <div style={styles.orbStage}>
        <canvas
          ref={canvasRef}
          width={240}
          height={240}
          style={styles.canvas}
        />

        {/* Center Control Button */}
        <button
          id="voice-orb-btn"
          onClick={handleClick}
          disabled={!canClick}
          aria-label={cfg.label}
          style={{
            ...styles.centerTrigger,
            borderColor: cfg.color,
            boxShadow: `0 0 25px ${cfg.dim}`,
            cursor: canClick ? 'pointer' : 'default',
          }}
          title={isMicActive ? "Mute Microphone" : "Activate Speech"}
        >
          {stateKey === 'speaking' && <Volume2 size={24} color={cfg.color} />}
          {stateKey === 'processing' && <Cpu size={24} color={cfg.color} />}
          {(stateKey === 'listening' || stateKey === 'ready') && <Mic size={24} color={cfg.color} />}
          {stateKey === 'idle' && <MicOff size={22} color={cfg.color} />}
          {stateKey === 'disconnected' && <AlertCircle size={22} color="var(--text-muted)" />}
        </button>
      </div>

      {/* Futuristic Bottom Status Readout */}
      <div style={styles.readoutBox}>
        <span style={styles.readoutLabel}>NEURAL CORE</span>
        <span style={styles.readoutDivider}>//</span>
        <span style={{ ...styles.readoutStatus, color: cfg.color }}>
          {isConnected ? 'ONLINE (16kHz PCM)' : 'OFFLINE'}
        </span>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.875rem',
    position: 'relative',
    userSelect: 'none',
  },
  telemetryTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 12px',
    background: 'rgba(4, 12, 28, 0.75)',
    border: '1px solid var(--border-hud)',
    borderRadius: 'var(--r-pill)',
    backdropFilter: 'blur(8px)',
  },
  radarDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  telemetryText: {
    fontFamily: 'var(--font-hud)',
    fontSize: '0.6875rem',
    fontWeight: 700,
    letterSpacing: '0.1em',
  },
  orbStage: {
    position: 'relative',
    width: 240,
    height: 240,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  canvas: {
    position: 'absolute',
    top: 0,
    left: 0,
    pointerEvents: 'none',
  },
  centerTrigger: {
    width: 68,
    height: 68,
    borderRadius: '50%',
    background: 'rgba(3, 8, 20, 0.85)',
    border: '1.5px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    zIndex: 2,
    transition: 'all var(--t-mid)',
  },
  readoutBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontFamily: 'var(--font-mono)',
    fontSize: '0.6875rem',
    letterSpacing: '0.08em',
  },
  readoutLabel: {
    color: 'var(--text-muted)',
  },
  readoutDivider: {
    color: 'var(--border-hud)',
  },
  readoutStatus: {
    fontWeight: 600,
  },
};
