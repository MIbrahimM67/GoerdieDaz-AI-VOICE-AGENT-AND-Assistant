import React, { useState, useEffect } from 'react';
import useAppStore from '../stores/appStore';

export const CURATED_VOICES = [
  {
    id: 'zik8E6YgP11SlhQImASg',
    name: 'GeordieDaz Prime',
    title: 'Alan Robson Flagship Clone',
    accentTag: 'GEORDIE',
    description: 'Warm, calm, late-night Newcastle radio host. Intimate, unhurried cadence.',
    recommendedAccent: 'geordie',
  },
  {
    id: 'QmpNl8yfFeqrwz75IL4C',
    name: 'Geordie Classic',
    title: 'Native Tyneside Voice',
    accentTag: 'GEORDIE',
    description: 'Authentic en-geordie acoustic profile. Rich Newcastle tone.',
    recommendedAccent: 'geordie',
  },
  {
    id: 'JBFqnCBsd6RMkjVDRZzb',
    name: 'George',
    title: 'Warm British Storyteller',
    accentTag: 'BRITISH',
    description: 'Smooth, resonant British delivery. Engaging and captivating.',
    recommendedAccent: 'british',
  },
  {
    id: 'onwK4e9ZLuTAKqWW03F9',
    name: 'Daniel',
    title: 'Steady Broadcaster',
    accentTag: 'BRITISH',
    description: 'Crisp UK broadcaster delivery. Professional, level, and steady.',
    recommendedAccent: 'british',
  },
  {
    id: 'CwhRBWXzGAHq8TQ4Fs17',
    name: 'Roger',
    title: 'Laid-Back Casual',
    accentTag: 'AMERICAN',
    description: 'Deep, resonant, relaxed American voice. Easy-going and friendly.',
    recommendedAccent: 'american',
  },
  {
    id: 'nPczCjzI2devNBz1zQrb',
    name: 'Brian',
    title: 'Deep & Comforting',
    accentTag: 'AMERICAN',
    description: 'Comforting, reassuring American tone. Warm conversational companion.',
    recommendedAccent: 'american',
  },
];

export const ACCENT_OPTIONS = [
  {
    id: 'geordie',
    label: 'Geordie (Newcastle)',
    flag: '⚓',
    tagline: 'Authentic Tyneside Dialect',
    phrases: 'Howay, canny, wey aye, pet, bonny lad, the Toon',
  },
  {
    id: 'british',
    label: 'Standard British',
    flag: '🇬🇧',
    tagline: 'Classic Conversational English',
    phrases: 'Right then, mate, brilliant, proper, spot on, cheers',
  },
  {
    id: 'american',
    label: 'American Casual',
    flag: '🇺🇸',
    tagline: 'Relaxed Friendly Banter',
    phrases: 'Hey buddy, awesome, pretty cool, you bet, folks',
  },
];

export default function VoiceAccentModal({ isOpen, onClose, onApply }) {
  const currentVoiceId = useAppStore((s) => s.currentVoiceId);
  const currentAccent = useAppStore((s) => s.currentAccent);

  const [selectedVoiceId, setSelectedVoiceId] = useState(currentVoiceId);
  const [selectedAccent, setSelectedAccent] = useState(currentAccent);

  useEffect(() => {
    setSelectedVoiceId(currentVoiceId);
    setSelectedAccent(currentAccent);
  }, [currentVoiceId, currentAccent, isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleApply = (voiceId = selectedVoiceId, accent = selectedAccent) => {
    setSelectedVoiceId(voiceId);
    setSelectedAccent(accent);
    if (onApply) {
      onApply(voiceId, accent);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(5, 8, 15, 0.78)',
        backdropFilter: 'blur(12px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
        animation: 'fadeIn 0.2s ease-out',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '680px',
          background: 'linear-gradient(135deg, rgba(13, 20, 36, 0.95) 0%, rgba(8, 12, 22, 0.98) 100%)',
          border: '1px solid rgba(0, 240, 255, 0.35)',
          borderRadius: '16px',
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.7), 0 0 35px rgba(0, 240, 255, 0.15)',
          padding: '1.75rem',
          color: '#e2e8f0',
          fontFamily: "'Inter', sans-serif",
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: '#00f0ff', fontSize: '1.25rem' }}>🎙️</span>
              <h2 style={{ fontSize: '1.1rem', fontWeight: '700', letterSpacing: '0.08em', textTransform: 'uppercase', margin: 0, color: '#fff' }}>
                Voice & Accent Matrix
              </h2>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.78rem', color: '#94a3b8' }}>
              Calibrate ElevenLabs acoustic models & dialect phrasing in real time
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '8px',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px 12px',
              fontSize: '0.9rem',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)'; }}
          >
            ✕
          </button>
        </div>

        {/* Section 1: Accent Selector */}
        <div style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: '600', letterSpacing: '0.06em', textTransform: 'uppercase', color: '#00f0ff' }}>
              1. Spoken Dialect & Accent
            </span>
            <span style={{ fontSize: '0.7rem', color: '#64748b' }}>Adapts vocabulary & idioms</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.65rem' }}>
            {ACCENT_OPTIONS.map((acc) => {
              const isSelected = selectedAccent === acc.id;
              return (
                <div
                  key={acc.id}
                  onClick={() => {
                    setSelectedAccent(acc.id);
                    handleApply(selectedVoiceId, acc.id);
                  }}
                  style={{
                    background: isSelected ? 'rgba(0, 240, 255, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                    border: isSelected ? '1px solid #00f0ff' : '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '10px',
                    padding: '0.85rem',
                    cursor: 'pointer',
                    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                    boxShadow: isSelected ? '0 0 16px rgba(0, 240, 255, 0.2)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '0.9rem', fontWeight: '600', color: isSelected ? '#00f0ff' : '#f1f5f9' }}>
                      {acc.flag} {acc.label}
                    </span>
                    {isSelected && (
                      <span style={{ fontSize: '0.65rem', background: '#00f0ff', color: '#000', fontWeight: '700', padding: '2px 6px', borderRadius: '4px' }}>
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: isSelected ? '#a5f3fc' : '#94a3b8', marginBottom: '6px' }}>
                    {acc.tagline}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: '#64748b', fontStyle: 'italic' }}>
                    "{acc.phrases}"
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Section 2: ElevenLabs Voice Models */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: '600', letterSpacing: '0.06em', textTransform: 'uppercase', color: '#00f0ff' }}>
              2. Acoustic Voice Model (ElevenLabs)
            </span>
            <span style={{ fontSize: '0.7rem', color: '#64748b' }}>6 Curated Presets</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.65rem' }}>
            {CURATED_VOICES.map((v) => {
              const isSelected = selectedVoiceId === v.id;
              return (
                <div
                  key={v.id}
                  onClick={() => {
                    setSelectedVoiceId(v.id);
                    // Optional auto-match accent if user hasn't customized
                    handleApply(v.id, selectedAccent);
                  }}
                  style={{
                    background: isSelected ? 'rgba(0, 240, 255, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                    border: isSelected ? '1px solid #00f0ff' : '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '10px',
                    padding: '0.85rem',
                    cursor: 'pointer',
                    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                    boxShadow: isSelected ? '0 0 16px rgba(0, 240, 255, 0.2)' : 'none',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                      <div>
                        <span style={{ fontSize: '0.88rem', fontWeight: '600', color: isSelected ? '#00f0ff' : '#f8fafc' }}>
                          {v.name}
                        </span>
                        <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                          {v.title}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: '0.62rem',
                          fontWeight: '700',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: isSelected ? '#00f0ff' : 'rgba(255, 255, 255, 0.08)',
                          color: isSelected ? '#000' : '#94a3b8',
                        }}
                      >
                        {v.accentTag}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '6px', lineHeight: '1.3' }}>
                      {v.description}
                    </div>
                  </div>

                  <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.65rem', color: '#64748b', fontFamily: 'monospace' }}>
                      ID: {v.id.slice(0, 8)}...
                    </span>
                    {isSelected && (
                      <span style={{ fontSize: '0.68rem', color: '#00f0ff', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#00f0ff', boxShadow: '0 0 6px #00f0ff' }} />
                        Active Profile
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '1rem' }}>
          <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
            Switches instantly on your next turn without session disconnect.
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'linear-gradient(135deg, #00f0ff 0%, #00a2ff 100%)',
              color: '#000',
              fontWeight: '700',
              fontSize: '0.8rem',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              padding: '8px 18px',
              borderRadius: '8px',
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 0 16px rgba(0, 240, 255, 0.3)',
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
