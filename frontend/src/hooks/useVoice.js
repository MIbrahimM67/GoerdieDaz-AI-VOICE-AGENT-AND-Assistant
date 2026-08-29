/**
 * GeordieDaz — useVoice hook
 * Manages microphone capture (AudioWorklet → PCM16) and speaker playback.
 * Implements client-side VAD for immediate barge-in UI feedback.
 */
import { useCallback, useRef, useState, useEffect } from 'react';
import useAppStore from '../stores/appStore';

const SAMPLE_RATE = 24000; // OpenAI Realtime API requires 24kHz

export function useVoice({ sendAudioChunk, sendBargein }) {
  const [isCapturing, setIsCapturing] = useState(false);
  const { voiceState, setVoiceState, isMicActive, setMicActive } = useAppStore();

  // Audio capture refs
  const audioContextRef = useRef(null);
  const workletNodeRef = useRef(null);
  const streamRef = useRef(null);


  // Audio playback refs
  const playbackContextRef = useRef(null);
  const gainNodeRef = useRef(null);       // Master gain gate — set to 0 for instant silence
  const activeSourcesRef = useRef([]);     // Track all scheduled BufferSourceNodes
  const nextPlayTimeRef = useRef(0);

  // ── Microphone Capture ────────────────────────────────────

  const startCapture = useCallback(async () => {
    if (isCapturing) return;

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // Create AudioContext at 24kHz
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioContextRef.current = ctx;

      // Load the AudioWorklet processor
      await ctx.audioWorklet.addModule('/audio-processor.js');

      // Source node from mic stream
      const source = ctx.createMediaStreamSource(stream);

      // Worklet node — receives PCM16 chunks
      const worklet = new AudioWorkletNode(ctx, 'pcm-processor');
      workletNodeRef.current = worklet;

      worklet.port.onmessage = (event) => {
        const { pcm16 } = event.data;

        // Send ALL audio to OpenAI — let server-side VAD handle speech detection
        // Client-side noise gate was clipping speech and breaking transcription
        const base64 = _arrayBufferToBase64(pcm16);
        sendAudioChunk(base64);

        // Client-side barge-in detection (still uses RMS)
        const int16 = new Int16Array(pcm16);
        let sumSq = 0;
        for (let i = 0; i < int16.length; i++) {
          const n = int16[i] / 32768;
          sumSq += n * n;
        }
        const rms = Math.sqrt(sumSq / int16.length);
        _detectBargein(pcm16, rms);
      };

      source.connect(worklet);
      // Don't connect worklet to destination (we don't want mic playback)

      setIsCapturing(true);
      setMicActive(true);
      console.log('[Voice] Capture started at', SAMPLE_RATE, 'Hz');
    } catch (err) {
      console.error('[Voice] Microphone access denied:', err);
      throw new Error('Microphone access denied. Please allow microphone access and try again.');
    }
  }, [isCapturing, sendAudioChunk]);

  const stopCapture = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setIsCapturing(false);
    setMicActive(false);
    console.log('[Voice] Capture stopped');
  }, []);

  // ── Barge-in Detection ────────────────────────────────────

  const _isSpeaking = useRef(false);
  const _speechTailRef = useRef(0);
  const BARGE_IN_THRESHOLD = 0.02; // RMS energy threshold for barge-in

  function _detectBargein(pcm16Buffer, rms) {
    // Read voiceState from store directly — NOT from closure (which would be stale)
    const currentVoiceState = useAppStore.getState().voiceState;
    if (currentVoiceState !== 'speaking') return;

    if (rms > BARGE_IN_THRESHOLD && !_isSpeaking.current) {
      _isSpeaking.current = true;
      console.log('[Voice] Barge-in detected, RMS:', rms.toFixed(4));
      sendBargein();
      stopPlayback(); // Immediately stop AI audio
      useAppStore.getState().setVoiceState('interrupted');
    } else if (rms <= BARGE_IN_THRESHOLD) {
      _isSpeaking.current = false;
    }
  }

  // ── Speaker Playback ──────────────────────────────────────

  const playbackMutedRef = useRef(false); // Set on barge-in, cleared on new response

  const _getPlaybackContext = () => {
    if (!playbackContextRef.current || playbackContextRef.current.state === 'closed') {
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      playbackContextRef.current = ctx;
      const gain = ctx.createGain();
      gain.gain.value = 1.0;
      gain.connect(ctx.destination);
      gainNodeRef.current = gain;
      activeSourcesRef.current = [];
      nextPlayTimeRef.current = 0;
    }
    return playbackContextRef.current;
  };

  const playAudioChunk = useCallback(async (base64data) => {
    // If muted (barge-in active), silently drop the chunk
    if (playbackMutedRef.current) return;

    try {
      const ctx = _getPlaybackContext();
      if (ctx.state === 'suspended') await ctx.resume();

      const arrayBuffer = _base64ToArrayBuffer(base64data);
      const int16 = new Int16Array(arrayBuffer);

      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768;
      }

      const audioBuffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
      audioBuffer.copyToChannel(float32, 0);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(gainNodeRef.current);

      activeSourcesRef.current.push(source);
      source.onended = () => {
        activeSourcesRef.current = activeSourcesRef.current.filter(s => s !== source);
      };

      const now = ctx.currentTime;
      const startTime = Math.max(now, nextPlayTimeRef.current);
      source.start(startTime);
      nextPlayTimeRef.current = startTime + audioBuffer.duration;

    } catch (err) {
      console.error('[Voice] Playback error:', err);
    }
  }, []);

  const stopPlayback = useCallback(() => {
    // 1. Mute flag — prevents ANY new chunks from playing
    playbackMutedRef.current = true;

    // 2. Kill gain instantly — immediate silence on currently playing audio
    if (gainNodeRef.current) {
      try { gainNodeRef.current.gain.value = 0; } catch {}
    }

    // 3. Stop every tracked source node
    for (const src of activeSourcesRef.current) {
      try { src.stop(); } catch {}
    }
    activeSourcesRef.current = [];

    // 4. Close context — will be recreated on next play
    if (playbackContextRef.current && playbackContextRef.current.state !== 'closed') {
      playbackContextRef.current.close().catch(() => {});
    }
    playbackContextRef.current = null;
    gainNodeRef.current = null;
    nextPlayTimeRef.current = 0;
    console.log('[Voice] Playback killed — muted + all sources stopped');
  }, []);

  // Unmute when new response starts
  const unmute = useCallback(() => {
    playbackMutedRef.current = false;
  }, []);

  // Auto-unmute when server says AI is speaking (new response)
  useEffect(() => {
    if (voiceState === 'speaking') {
      playbackMutedRef.current = false;
    }
  }, [voiceState]);

  // ── Utility ────────────────────────────────────────────────

  function _arrayBufferToBase64(buffer) {
    const uint8 = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < uint8.length; i++) {
      binary += String.fromCharCode(uint8[i]);
    }
    return btoa(binary);
  }

  function _base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const buffer = new ArrayBuffer(binary.length);
    const view = new Uint8Array(buffer);
    for (let i = 0; i < binary.length; i++) {
      view[i] = binary.charCodeAt(i);
    }
    return buffer;
  }

  return {
    isCapturing,
    startCapture,
    stopCapture,
    playAudioChunk,
    stopPlayback,
    unmute,
  };
}
