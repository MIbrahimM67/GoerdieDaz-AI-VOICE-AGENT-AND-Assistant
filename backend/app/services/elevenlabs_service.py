"""
GeordieDaz — ElevenLabs TTS Streaming Service
Streams text → ElevenLabs WebSocket → audio chunks back to caller.
Uses eleven_multilingual_v2 for accent-faithful, high-fidelity conversational TTS.
Handles per-utterance lifecycle and reconnection automatically.
"""
import asyncio
import base64
import json
import logging
from typing import AsyncGenerator, Callable, Optional

import websockets

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ElevenLabsTTS:
    """
    Streams text to ElevenLabs and yields base64-encoded audio chunks.

    Usage:
        tts = ElevenLabsTTS(voice_id="...", on_audio_chunk=callback)
        await tts.connect()
        await tts.send_text("Hello from Newcastle!")
        await tts.send_text(" How are you doing?")
        await tts.flush()  # Signal end of text
        await tts.close()
    """

    WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"

    def __init__(
        self,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        on_audio_chunk: Optional[Callable] = None,
        output_format: Optional[str] = None,
    ):
        self.voice_id = voice_id or settings.elevenlabs_voice_id
        self.model_id = model_id or settings.elevenlabs_model_id
        self.api_key = settings.elevenlabs_api_key
        self.on_audio_chunk = on_audio_chunk
        self.output_format = output_format or settings.elevenlabs_output_format
        self._ws = None
        self._listen_task = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket connection is active and open."""
        if not self._connected or not self._ws:
            return False
        try:
            return getattr(self._ws, "state", None) and self._ws.state.name == "OPEN"
        except Exception:
            return False

    async def set_voice(self, new_voice_id: str):
        """Hot-swap active ElevenLabs voice ID."""
        if not new_voice_id or new_voice_id == self.voice_id:
            return
        logger.info(f"ElevenLabs switching voice: {self.voice_id} → {new_voice_id}")
        self.voice_id = new_voice_id
        self._connected = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def ensure_connected(self):
        """Ensure connection is open. If closed or finished, connect a fresh stream."""
        if self.is_connected:
            return
        await self.connect()

    async def connect(self):
        """Open WebSocket connection to ElevenLabs streaming TTS."""
        if not self.api_key or not self.voice_id:
            raise ValueError("ElevenLabs API key and voice_id are required")

        # Cancel previous listen task if still running
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

        url = self.WS_URL.format(voice_id=self.voice_id)
        url += f"?model_id={self.model_id}&output_format={self.output_format}"

        try:
            self._ws = await websockets.connect(
                url,
                additional_headers={"xi-api-key": self.api_key},
                ping_interval=20,
                ping_timeout=10,
            )
            self._connected = True

            # Send initial config (BOS — Beginning of Stream)
            # chunk_length_schedule: [50] starts audio generation after just 50 chars (~8-10 words)
            # instead of waiting for 120+ characters. Drastically reduces TTFB.
            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": 0.88,
                    "similarity_boost": 0.85,
                    "style": 0.0,
                    "use_speaker_boost": False,
                    "speed": 0.90,
                },
                "generation_config": {
                    "chunk_length_schedule": [50, 90, 140],
                },
                "xi_api_key": self.api_key,
            }
            await self._ws.send(json.dumps(bos_message))

            # Start listening for audio chunks
            self._listen_task = asyncio.create_task(self._listen_loop())
            logger.info(f"ElevenLabs TTS connected: voice={self.voice_id}")

        except Exception as e:
            logger.error(f"ElevenLabs connection failed: {e}")
            self._connected = False
            raise

    async def _listen_loop(self):
        """Receive audio chunks from ElevenLabs and forward them."""
        try:
            async for message in self._ws:
                data = json.loads(message)

                if "audio" in data and data["audio"]:
                    # ElevenLabs sends base64-encoded audio
                    audio_b64 = data["audio"]
                    if self.on_audio_chunk:
                        await self.on_audio_chunk(audio_b64)

                if data.get("isFinal"):
                    logger.debug("ElevenLabs stream complete")
                    self._connected = False
                    break

        except websockets.ConnectionClosed:
            logger.debug("ElevenLabs WS closed")
            self._connected = False
        except Exception as e:
            logger.error(f"ElevenLabs listen error: {e}")
            self._connected = False

    async def send_text(self, text: str, try_trigger_generation: bool = False):
        """Stream a text token or chunk to ElevenLabs for TTS generation."""
        if not text:
            return

        try:
            if not self.is_connected:
                await self.connect()

            msg = {"text": text}
            if try_trigger_generation:
                msg["try_trigger_generation"] = True
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.error(f"ElevenLabs send_text error: {e}")

    async def flush(self):
        """Signal end of text input (EOS — End of Stream)."""
        if not self.is_connected:
            return

        try:
            await self._ws.send(json.dumps({"text": ""}))
            logger.debug("ElevenLabs flush sent")
        except Exception as e:
            logger.debug(f"ElevenLabs flush note: {e}")

    async def cancel(self):
        """Cancel current utterance on barge-in."""
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    async def close(self):
        """Close the WebSocket connection."""
        self._connected = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        logger.debug("ElevenLabs TTS closed")
