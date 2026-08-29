"""
GeordieDaz — ElevenLabs TTS Streaming Service
Streams text → ElevenLabs WebSocket → audio chunks back to caller.
Uses eleven_flash_v2_5 for low-latency conversational TTS (~75ms).
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
        output_format: str = "pcm_16000",  # 16kHz PCM16 — matches our frontend
    ):
        self.voice_id = voice_id or settings.elevenlabs_voice_id
        self.model_id = model_id or settings.elevenlabs_model_id
        self.api_key = settings.elevenlabs_api_key
        self.on_audio_chunk = on_audio_chunk
        self.output_format = output_format
        self._ws = None
        self._listen_task = None
        self._connected = False

    async def connect(self):
        """Open WebSocket connection to ElevenLabs streaming TTS."""
        if not self.api_key or not self.voice_id:
            raise ValueError("ElevenLabs API key and voice_id are required")

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
            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.8,
                    "style": 0.0,
                    "use_speaker_boost": True,
                },
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290],
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
                    break

        except websockets.ConnectionClosed:
            logger.info("ElevenLabs WS closed")
        except Exception as e:
            logger.error(f"ElevenLabs listen error: {e}")

    async def send_text(self, text: str):
        """Stream a text chunk to ElevenLabs for TTS generation."""
        if not self._connected or not self._ws:
            logger.warning("ElevenLabs not connected — dropping text chunk")
            return

        try:
            await self._ws.send(json.dumps({
                "text": text,
                "try_trigger_generation": True,
            }))
        except Exception as e:
            logger.error(f"ElevenLabs send_text error: {e}")

    async def flush(self):
        """Signal end of text input (EOS — End of Stream)."""
        if not self._connected or not self._ws:
            return

        try:
            await self._ws.send(json.dumps({"text": ""}))
            logger.debug("ElevenLabs flush sent")
        except Exception as e:
            logger.error(f"ElevenLabs flush error: {e}")

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
