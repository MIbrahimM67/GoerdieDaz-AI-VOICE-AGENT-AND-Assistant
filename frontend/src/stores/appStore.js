/**
 * GeordieDaz — Global App State (Zustand)
 * Single source of truth for the entire frontend.
 */
import { create } from 'zustand';

const useAppStore = create((set, get) => ({
  // ── Auth ──────────────────────────────────────────────────
  user: null,          // { id, username, email, current_persona_id }
  accessToken: null,   // Stored in memory only — never localStorage

  setAuth: (user, token) => set({ user, accessToken: token }),
  clearAuth: () => set({ user: null, accessToken: null }),

  // ── Persona ───────────────────────────────────────────────
  currentPersona: {
    id: 'friendly_geordie',
    name: 'Friendly Geordie',
    ui_theme_color: '#00d4aa',
  },
  availablePersonas: [],

  setPersona: (persona) => {
    set({ currentPersona: persona });
    // Apply persona theme to body
    document.body.classList.remove('persona-driving', 'persona-geordie');
    if (persona.id === 'driving_banter') {
      document.body.classList.add('persona-driving');
    }
    // Trigger CSS transition
    document.body.classList.add('persona-transition');
    setTimeout(() => document.body.classList.remove('persona-transition'), 600);
  },
  setAvailablePersonas: (personas) => set({ availablePersonas: personas }),

  // ── Voice State ───────────────────────────────────────────
  // State machine: idle → listening → processing → speaking → (interrupted →) idle
  voiceState: 'idle',  // 'idle' | 'listening' | 'processing' | 'speaking' | 'interrupted'
  setVoiceState: (state) => set({ voiceState: state }),

  isMicActive: false,
  setMicActive: (v) => set({ isMicActive: v }),

  // ── Connection ────────────────────────────────────────────
  isConnected: false,
  setConnected: (v) => set({ isConnected: v }),

  // ── Conversation ──────────────────────────────────────────
  turns: [],           // [{ role, content, persona_id, timestamp }]
  currentUserTranscript: '',   // Live transcript while speaking
  currentAIResponse: '',       // Streaming AI text response

  addTurn: (turn) => set((s) => ({
    turns: [...s.turns, { ...turn, timestamp: Date.now() }],
  })),
  clearTurns: () => set({ turns: [], currentUserTranscript: '', currentAIResponse: '' }),

  setCurrentTranscript: (text) => set({ currentUserTranscript: text }),
  appendAIResponse: (delta) => set((s) => ({
    currentAIResponse: s.currentAIResponse + delta,
  })),
  clearCurrentAIResponse: () => set({ currentAIResponse: '' }),

  // ── Error ─────────────────────────────────────────────────
  errorMessage: null,
  setError: (msg) => set({ errorMessage: msg }),
  clearError: () => set({ errorMessage: null }),

  // ── Tool Activity ───────────────────────────────────────
  // null | 'search_memory' | 'store_fact'
  activeToolCall: null,
  setActiveToolCall: (tool) => set({ activeToolCall: tool }),
  clearActiveToolCall: () => set({ activeToolCall: null }),

  // ── Navigation Views ───────────────────────────────────────
  // 'cockpit' | 'telemetry'
  activeView: 'cockpit',
  setActiveView: (view) => set({ activeView: view }),

  // ── Live Telemetry & Audit Stream ──────────────────────────
  telemetryEvents: [],
  addTelemetryEvent: (evt) => set((s) => ({
    telemetryEvents: [
      {
        ...evt,
        _clientTimestamp: Date.now(),
      },
      ...s.telemetryEvents.slice(0, 249), // Keep latest 250 in-memory events
    ],
  })),
  clearTelemetryEvents: () => set({ telemetryEvents: [] }),
}));

export default useAppStore;
