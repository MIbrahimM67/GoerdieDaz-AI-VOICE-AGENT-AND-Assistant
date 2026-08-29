/**
 * GeordieDaz — useWebSocket hook
 * Manages the WebSocket connection to the backend.
 * Routes all incoming message types to the appropriate store handlers.
 */
import { useCallback, useEffect, useRef } from 'react';
import useAppStore from '../stores/appStore';

const WS_BASE = `ws://${window.location.host}/ws`;
const MAX_RECONNECT_DELAY = 10000;

export function useWebSocket({ userId, token, onAudioChunk, onBargeIn }) {
  const wsRef = useRef(null);
  const reconnectDelayRef = useRef(1000);
  const reconnectTimerRef = useRef(null);
  const isUnmountingRef = useRef(false);

  const {
    setConnected,
    setVoiceState,
    setPersona,
    addTurn,
    setCurrentTranscript,
    appendAIResponse,
    clearCurrentAIResponse,
    setError,
    setActiveToolCall,
    clearActiveToolCall,
  } = useAppStore();

  // Accumulate full AI response for turn logging
  const aiResponseRef = useRef('');
  const userTranscriptRef = useRef('');

  const connect = useCallback(() => {
    if (!userId || !token) return;

    const url = `${WS_BASE}/${userId}?token=${token}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnected(true);
      reconnectDelayRef.current = 1000; // Reset backoff
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {
        console.error('[WS] Bad message', e);
      }
    };

    ws.onclose = (event) => {
      console.log('[WS] Disconnected', event.code);
      setConnected(false);
      setVoiceState('idle');
      wsRef.current = null;

      if (isUnmountingRef.current) return;
      if (event.code === 4001 || event.code === 4003) {
        // Auth failure — don't reconnect
        setError('Session expired. Please log in again.');
        return;
      }

      // Exponential backoff reconnect
      const delay = reconnectDelayRef.current;
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
      console.log(`[WS] Reconnecting in ${delay}ms...`);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error', err);
    };
  }, [userId, token]);

  function handleMessage(msg) {
    // Don't process messages after disconnect
    if (!wsRef.current) return;

    switch (msg.type) {
      case 'audio_response':
        // Drop audio if we're interrupted — the barge-in killed playback
        if (useAppStore.getState().voiceState === 'interrupted') break;
        if (onAudioChunk) onAudioChunk(msg.data);
        break;

      case 'transcript':
        // User's speech transcript — update live display
        userTranscriptRef.current = msg.text;
        setCurrentTranscript(msg.text);
        break;

      case 'text_response':
        // Streaming AI text delta
        aiResponseRef.current += msg.delta || '';
        appendAIResponse(msg.delta || '');
        break;

      case 'state_change':
        setVoiceState(msg.state);
        if (msg.state === 'idle') {
          const userText = userTranscriptRef.current;
          const aiText   = aiResponseRef.current;
          if (aiText) {
            if (userText) {
              addTurn({ role: 'user', content: userText, persona_id: useAppStore.getState().currentPersona.id });
            }
            addTurn({ role: 'assistant', content: aiText, persona_id: useAppStore.getState().currentPersona.id });
          } else if (userText) {
            addTurn({ role: 'user', content: userText, persona_id: useAppStore.getState().currentPersona.id });
          }
          // Clear BOTH refs AND store live state
          aiResponseRef.current = '';
          userTranscriptRef.current = '';
          setCurrentTranscript('');
          clearCurrentAIResponse();
        }
        break;

      case 'session_ready':
        console.log('[WS] Session ready:', msg);
        setVoiceState('idle');
        break;

      case 'persona_switched':
        setPersona({
          id: msg.persona_id,
          name: msg.persona_name,
          ui_theme_color: msg.ui_theme_color,
        });
        console.log('[WS] Persona switched to:', msg.persona_name);
        break;

      case 'barge_in_detected':
        setVoiceState('interrupted');
        aiResponseRef.current = ''; // Discard partial AI response
        if (onBargeIn) onBargeIn(); // Stop audio playback
        break;

      case 'pong':
        break;

      case 'tool_activity':
        if (msg.status === 'started') {
          setActiveToolCall(msg.tool);
        } else {
          clearActiveToolCall();
        }
        break;

      case 'error':
        console.error('[WS] Server error:', msg.message);
        setError(msg.message);
        break;

      default:
        break;
    }
  }

  // Send helpers
  const sendAudioChunk = useCallback((base64data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'audio_chunk', data: base64data }));
    }
  }, []);

  const sendBargein = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'barge_in' }));
    }
  }, []);

  const sendPersonaSwitch = useCallback((personaId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'persona_switch', persona_id: personaId }));
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }));
    }
  }, []);

  // Intentional disconnect — no auto-reconnect
  const disconnect = useCallback(() => {
    isUnmountingRef.current = true; // Prevent auto-reconnect
    clearTimeout(reconnectTimerRef.current);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
    setVoiceState('idle');
    console.log('[WS] Intentionally disconnected');
  }, []);

  // Reconnect after intentional disconnect
  const reconnect = useCallback(() => {
    isUnmountingRef.current = false;
    reconnectDelayRef.current = 1000;
    connect();
    console.log('[WS] Reconnecting...');
  }, [connect]);

  // Start a new session — summarise current, then reconnect fresh
  const sendNewSession = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'new_session' }));
    }
    // Give backend a moment to summarise, then full reconnect
    setTimeout(() => {
      disconnect();
      setTimeout(() => reconnect(), 300);
    }, 500);
  }, [disconnect, reconnect]);

  // Connect on mount / when credentials change
  useEffect(() => {
    if (!userId || !token) return;
    isUnmountingRef.current = false;
    connect();

    // Heartbeat ping every 30s
    const pingInterval = setInterval(sendPing, 30000);

    return () => {
      isUnmountingRef.current = true;
      clearInterval(pingInterval);
      clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [userId, token]);

  return { sendAudioChunk, sendBargein, sendPersonaSwitch, disconnect, reconnect, sendNewSession };
}
