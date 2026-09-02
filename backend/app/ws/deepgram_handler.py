"""
GeordieDaz — Open-Source Voice Pipeline
Deepgram STT → Groq LLM → ElevenLabs TTS

Used when LLM_PROVIDER=opensource in .env.
Drop-in replacement for the OpenAI Realtime WebSocket mode.
The browser client sends/receives identical message types — frontend unchanged.

Architecture:
  Browser Mic (PCM16 base64)
    → WS /ws/{user_id}           (our backend)
      → Deepgram WS (STT)        → transcript text
      → Groq API (LLM)           → response text
      → ElevenLabs WS (TTS)      → audio chunks
    ← Audio chunks + transcript  (same as OpenAI mode)

Tool calls (search_memory, store_fact, search_history) are handled
by the parent RealtimeSessionHandler — this class just provides
STT + LLM, inheriting all memory/persona logic.
"""
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

import websockets
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.llm_client import get_llm_client, get_chat_model
from app.services.embedding_service import embed_text
from app.services.memory_service import retrieve_relevant_memories

logger = logging.getLogger(__name__)
settings = get_settings()

# Deepgram streaming STT endpoint
DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model={model}"
    "&language=en-GB"           # British English — closest to Geordie
    "&encoding=linear16"        # PCM16
    "&sample_rate=24000"        # 24kHz (matches ElevenLabs output + frontend)
    "&channels=1"
    "&punctuate=true"
    "&smart_format=true"
    "&endpointing=150"          # 150ms silence = end of utterance (snappy response)
    "&interim_results=true"     # Get partial transcripts for barge-in
    "&utterance_end_ms=400"     # Finalize after 400ms silence (was 1000ms)
)


class DeepgramVoiceHandler:
    """
    Manages the Deepgram STT WebSocket + Groq LLM pipeline.
    Called by RealtimeSessionHandler when LLM_PROVIDER=opensource.
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        persona_id: str,
        system_prompt: str,
        db: AsyncSession,
        on_transcript: Callable,        # async fn(text: str)
        on_response_text: Callable,     # async fn(delta: str)
        on_response_done: Callable,     # async fn()
        on_audio_chunk: Callable,       # async fn(b64: str)
        on_tool_call: Callable,         # async fn(name: str, args: dict, call_id: str)
        on_state_change: Callable,      # async fn(state: str)
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.persona_id = persona_id
        self.system_prompt = system_prompt
        self.db = db

        # Callbacks to parent handler
        self._on_transcript = on_transcript
        self._on_response_text = on_response_text
        self._on_response_done = on_response_done
        self._on_audio_chunk = on_audio_chunk
        self._on_tool_call = on_tool_call
        self._on_state_change = on_state_change

        # State
        self.deepgram_ws = None
        self._dg_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._llm_client: AsyncOpenAI = get_llm_client()
        self._conversation_history: list[dict] = []
        self._current_response = ""
        self._is_speaking = False
        self._audio_muted = False
        self._elevenlabs_tts = None

        # Groq tool definitions (subset — real tool calls go through Groq function calling)
        self._tools = self._build_tools()

    def _build_tools(self) -> list[dict]:
        """Groq tool definitions matching the OpenAI Realtime tool schema."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Search the user's long-term memory for past facts, preferences, or events.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to search for"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_fact",
                    "description": "Store a fact about the user in long-term memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity_key": {"type": "string"},
                            "content": {"type": "string"},
                            "importance": {"type": "number"}
                        },
                        "required": ["entity_key", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_history",
                    "description": "Search past conversation sessions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "days_back": {"type": "integer"},
                            "date": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    async def connect(self):
        """Open Deepgram STT WebSocket and ElevenLabs TTS."""
        url = DEEPGRAM_WS_URL.format(model=settings.deepgram_model)
        logger.info(f"Connecting to Deepgram STT for user {self.user_id}")
        self.deepgram_ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            ping_interval=10,
            ping_timeout=5,
        )
        self._dg_task = asyncio.create_task(self._listen_deepgram())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Connect ElevenLabs TTS
        if settings.use_elevenlabs:
            from app.services.elevenlabs_service import ElevenLabsTTS
            self._elevenlabs_tts = ElevenLabsTTS(on_audio_chunk=self._on_audio_chunk)
            await self._elevenlabs_tts.connect()
            logger.info("ElevenLabs TTS connected (opensource mode)")

        logger.info("Deepgram STT connected (opensource mode)")

    async def _keepalive_loop(self):
        """Periodically send KeepAlive to prevent Deepgram 1011 stream timeout."""
        try:
            while True:
                await asyncio.sleep(5)
                if self.deepgram_ws:
                    try:
                        await self.deepgram_ws.send(json.dumps({"type": "KeepAlive"}))
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    async def send_audio(self, pcm16_b64: str):
        """Forward PCM16 audio chunk from browser to Deepgram."""
        if self.deepgram_ws:
            try:
                audio_bytes = base64.b64decode(pcm16_b64)
                await self.deepgram_ws.send(audio_bytes)
            except Exception as e:
                logger.warning(f"Deepgram audio send failed: {e}")

    async def cancel_response(self):
        """Barge-in: mute audio and discard current response."""
        self._audio_muted = True
        self._is_speaking = False
        self._current_response = ""
        if self._elevenlabs_tts:
            try:
                await self._elevenlabs_tts.cancel()
            except Exception:
                pass
        await self._on_state_change("listening")

    def unmute(self):
        self._audio_muted = False

    async def _listen_deepgram(self):
        """
        Background task: receive Deepgram STT events.
        When a final transcript arrives → send to Groq LLM.
        """
        try:
            async for msg in self.deepgram_ws:
                if isinstance(msg, bytes):
                    continue  # Ping/keepalive
                try:
                    event = json.loads(msg)
                    if not isinstance(event, dict):
                        continue
                    channel = event.get("channel")
                    if not isinstance(channel, dict):
                        continue
                    alternatives = channel.get("alternatives")
                    if not isinstance(alternatives, list) or not alternatives:
                        continue
                    alt = alternatives[0]
                    if not isinstance(alt, dict):
                        continue
                    transcript = alt.get("transcript", "").strip()
                    is_final = event.get("is_final", False)
                    speech_final = event.get("speech_final", False)

                    if not transcript:
                        continue

                    if not is_final:
                        # User is actively speaking — pre-connect ElevenLabs in background
                        # so the connection is hot and ready the millisecond LLM starts streaming!
                        if self._elevenlabs_tts and not self._elevenlabs_tts.is_connected:
                            asyncio.create_task(self._elevenlabs_tts.ensure_connected())
                        continue

                    # Final transcript from Deepgram
                    if speech_final or is_final:
                        logger.info(f"Deepgram transcript (user {self.user_id}): '{transcript}'")
                        await self._on_transcript(transcript)
                        await self._on_state_change("processing")
                        # Send to Groq
                        asyncio.create_task(self._call_groq(transcript))
                except Exception as msg_err:
                    logger.warning(f"Error processing Deepgram event: {msg_err}")

        except websockets.ConnectionClosed as e:
            logger.info(f"Deepgram WS closed for user {self.user_id}: {e}")
        except Exception as e:
            logger.error(f"Deepgram listener error: {e}")

    async def _call_groq(self, user_text: str):
        """
        Send user transcript to Groq, handle tool calls, stream response text to ElevenLabs.
        """
        # Always unmute when a new user turn arrives
        self._audio_muted = False
        self._is_speaking = True
        self._current_response = ""
        await self._on_state_change("speaking")

        # Add user turn to history
        self._conversation_history.append({"role": "user", "content": user_text})

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self._conversation_history[-20:],  # Last 20 turns context window
        ]

        # Reconnect / prepare ElevenLabs stream for this response
        if self._elevenlabs_tts:
            try:
                await self._elevenlabs_tts.ensure_connected()
            except Exception as e:
                logger.warning(f"ElevenLabs ensure_connected warning: {e}")

        try:
            # Streaming response from Groq
            stream = await self._llm_client.chat.completions.create(
                model=get_chat_model(),
                messages=messages,
                tools=self._tools,
                tool_choice="auto",
                max_tokens=200,
                temperature=0.7,
                stream=True,
            )

            tool_calls_acc: dict[int, dict] = {}  # index → accumulated tool call
            response_text = ""

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # ── Text delta ──────────────────────────────────────────────
                if delta.content:
                    response_text += delta.content
                    await self._on_response_text(delta.content)
                    if self._elevenlabs_tts and not self._audio_muted:
                        await self._elevenlabs_tts.send_text(delta.content)

                # ── Tool call accumulation ──────────────────────────────────
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc.function.arguments

            # ── Flush ElevenLabs ────────────────────────────────────────────
            if self._elevenlabs_tts and response_text and not self._audio_muted:
                await self._elevenlabs_tts.flush()

            # ── Process tool calls ──────────────────────────────────────────
            if tool_calls_acc:
                # Add assistant message with tool_calls to history
                self._conversation_history.append({
                    "role": "assistant",
                    "content": response_text or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]}
                        }
                        for tc in tool_calls_acc.values()
                    ]
                })

                # Execute each tool call via parent handler callbacks
                for tc in tool_calls_acc.values():
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    # Dispatch to parent handler (same logic as OpenAI mode)
                    result = await self._on_tool_call(tc["name"], args, tc["id"])

                    # Add tool result to history
                    self._conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result or "Done.",
                    })

                # Second Groq call with tool results to get final response
                messages2 = [
                    {"role": "system", "content": self.system_prompt},
                    *self._conversation_history[-20:],
                ]
                stream2 = await self._llm_client.chat.completions.create(
                    model=get_chat_model(),
                    messages=messages2,
                    max_tokens=200,
                    temperature=0.7,
                    stream=True,
                )
                async for chunk in stream2:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        response_text += delta.content
                        await self._on_response_text(delta.content)
                        if self._elevenlabs_tts and not self._audio_muted:
                            await self._elevenlabs_tts.send_text(delta.content)

                if self._elevenlabs_tts and not self._audio_muted:
                    await self._elevenlabs_tts.flush()

            # ── Done ────────────────────────────────────────────────────────
            self._current_response = response_text
            if response_text:
                self._conversation_history.append({"role": "assistant", "content": response_text})
            self._is_speaking = False
            await self._on_response_done()

        except Exception as e:
            logger.error(f"Groq LLM call failed for user {self.user_id}: {e}", exc_info=True)
            self._is_speaking = False
            await self._on_state_change("idle")

    async def close(self):
        """Shut down Deepgram WS and ElevenLabs TTS."""
        if self._dg_task and not self._dg_task.done():
            self._dg_task.cancel()
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        if self.deepgram_ws:
            try:
                await self.deepgram_ws.close()
            except Exception:
                pass
        if self._elevenlabs_tts:
            try:
                await self._elevenlabs_tts.close()
            except Exception:
                pass
        logger.info(f"Deepgram handler closed for user {self.user_id}")
