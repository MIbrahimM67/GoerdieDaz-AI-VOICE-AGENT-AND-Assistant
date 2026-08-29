/**
 * GeordieDaz — PCM Audio Processor (AudioWorklet)
 * Captures microphone audio as PCM16 chunks at 24kHz
 * and sends them to the main thread for WebSocket relay.
 *
 * This file is served as a static asset and loaded via AudioWorklet.addModule()
 */

class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._bufferSize = 4096; // ~170ms at 24kHz
  }

  /**
   * Convert Float32Array (-1.0 to 1.0) to Int16Array (PCM16)
   * This is the format OpenAI Realtime API expects.
   */
  _floatToPCM16(float32Array) {
    const int16 = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const clamped = Math.max(-1, Math.min(1, float32Array[i]));
      int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    }
    return int16;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0]; // Mono channel
    this._buffer.push(...channelData);

    // When buffer is full, send PCM16 chunk to main thread
    while (this._buffer.length >= this._bufferSize) {
      const chunk = new Float32Array(this._buffer.splice(0, this._bufferSize));
      const pcm16 = this._floatToPCM16(chunk);
      // Transfer ArrayBuffer to main thread (zero-copy)
      this.port.postMessage({ pcm16: pcm16.buffer }, [pcm16.buffer]);
    }

    return true; // Keep processor alive
  }
}

registerProcessor('pcm-processor', PCMProcessor);
