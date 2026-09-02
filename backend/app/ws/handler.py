"""
GeordieDaz — WebSocket Session Handler
The core real-time voice bridge between the browser and OpenAI Realtime API.

Architecture (PRD Figure 7 — Voice Pipeline):
  Browser Mic (WebRTC/PCM16)
    → WS /ws/{user_id}?token=JWT      (our backend)
      → OpenAI Realtime WS            (gpt-4o-realtime-preview)
      ← Audio chunks + transcript
    ← Browser Speaker playback

Barge-in (PRD Figure 8 — State Machine):
  SPEAKING → [user speaks] → INTERRUPTED
    → send response.cancel to OpenAI
    → clear audio buffer
    → return to LISTENING
"""
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import run_post_turn, run_pre_turn
from app.agent.state import AgentState
from app.config import get_settings
from app.models.memory import Memory
from app.services.embedding_service import embed_text
from app.services.memory_service import retrieve_relevant_memories
from app.services.persona_service import persona_manager


logger = logging.getLogger(__name__)
settings = get_settings()

# ── Shared constant: memory tool instructions appended to every system prompt ──
MEMORY_TOOL_INSTRUCTIONS = """

MEMORY TOOLS — YOU MUST USE THESE:

1. search_memory: ALWAYS call this tool BEFORE answering when the user:
   - Asks "what car do I drive?", "do you remember my name?", "what did I tell you about..."
   - Asks about ANY personal fact (health, family, possessions, preferences, location, job)
   - References something they told you before
   - Says "do you remember", "what do you know about me", etc.
   DO NOT guess or make up answers. ALWAYS search first, then respond based on results.
   Do NOT say "let me check" or any filler — just call the tool silently.

2. store_fact: Call this when the user:
   - Shares personal information (name, car, health condition, family, etc.)
   - Says "remember that...", "store this...", "don't forget..."
   - Mentions a new fact about themselves, even casually
   Do NOT say "let me store that" or any filler — just call the tool silently.

3. search_history: Call this when the user:
   - Asks about a previous conversation ("what did we talk about last time?")
   - References past events ("where were we driving?", "what did we do last Friday?")
   - Asks about something that happened in an earlier session
   - Uses TEMPORAL references like "yesterday", "last week", "3 days ago", "last Monday"
   IMPORTANT: When the user asks about a specific day (e.g. "what did I do yesterday?"),
   use the 'date' parameter with an ISO date like "2025-08-29" or relative term "yesterday".
   Do NOT say any filler — just call the tool silently.

CRITICAL: If the user asks about themselves and you don't search_memory first, you are FAILING your job. Never say "I don't know" or "I don't have that information" without searching first.

IMPORTANT: When calling tools, do NOT generate any speech or filler text before the tool call. Just call the tool and respond with the result."""

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini"


class VoiceState:
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class RealtimeSessionHandler:
    """
    Manages a single user's voice session.
    Maintains two WebSocket connections:
      - client_ws:  Browser ↔ Our Backend
      - openai_ws:  Our Backend ↔ OpenAI Realtime API
    """

    def __init__(self, user_id: str, client_ws: WebSocket, db: AsyncSession, initial_persona_id: Optional[str] = None):
        self.user_id = user_id
        self.client_ws = client_ws
        self.db = db
        self.session_id = str(uuid.uuid4())
        self._initial_persona_id = initial_persona_id
        self.persona_id = initial_persona_id or "friendly_geordie"
        self.voice_state = VoiceState.IDLE
        self.openai_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._openai_task: Optional[asyncio.Task] = None
        self._current_response_text = ""
        self._current_user_input = ""
        self._agent_state: Optional[AgentState] = None
        self._audio_muted = False  # Set during barge-in, cleared on new response
        self._transcript_event = asyncio.Event()  # Signalled when user transcript arrives
        self._tool_stored_facts_this_turn = False  # Track if AI already stored facts via tool
        self._turn_count = 0  # Track number of completed turns for session summary guard
        self._last_persona_switch_time = 0.0  # Cooldown for persona switches (Fix #4)
        # ElevenLabs TTS (Geordie voice)
        self._use_elevenlabs = settings.use_elevenlabs
        self._elevenlabs_tts = None
        # Open-source mode (Deepgram STT + Groq LLM)
        self._deepgram: Optional["DeepgramVoiceHandler"] = None


    async def send_to_client(self, message: dict):
        """Send a JSON message to the browser client."""
        try:
            await self.client_ws.send_text(json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to send to client {self.user_id}: {e}")

    async def send_to_openai(self, message: dict):
        """Send a JSON message to OpenAI Realtime API."""
        if self.openai_ws:
            try:
                await self.openai_ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send to OpenAI: {e}")

    # ── Noise Rejection Gate ──────────────────────────────────────────────────

    # Common Whisper noise transcription artefacts
    _NOISE_PATTERNS = {
        "[music]", "[noise]", "[laughter]", "[applause]", "[silence]",
        "[inaudible]", "[blank_audio]", "[music playing]", "[background noise]",
        "(inaudible)", "(music)", "(noise)", "(silence)", "(laughter)",
        "...", "…", "♪", "♫", "thank you.", "thanks for watching.",
        "bye.", "bye bye.", "goodbye.", "you", "hmm", "hm", "uh",
        "um", "ah", "oh", "eh", "mhm", "mm", "mmm", "uhh", "umm",
        "ahh", "ohh", "huh", "ha", "haha",
    }

    def _is_valid_speech(self, transcript: str) -> bool:
        """
        Multi-layer noise rejection for car/phone deployment.
        Returns True only if the transcript looks like genuine human speech
        that warrants an AI response.

        Rejects:
        - Empty / whitespace-only transcripts
        - Very short transcripts (< 2 chars after stripping)
        - Known Whisper noise artefacts ([music], [noise], etc.)
        - Transcripts that are only punctuation or repeated single characters
        - Single meaningless syllables (uh, um, hmm, etc.)
        """
        if not transcript:
            return False

        cleaned = transcript.strip()

        # Layer 1: Too short to be meaningful speech
        if len(cleaned) < 2:
            return False

        # Layer 2: Known Whisper noise transcription artefacts
        lower = cleaned.lower().strip(".,!? ")
        if lower in self._NOISE_PATTERNS:
            return False

        # Layer 3: Transcript is only punctuation / special characters
        import re
        alpha_content = re.sub(r'[^a-zA-Z]', '', cleaned)
        if len(alpha_content) < 2:
            return False

        # Layer 4: All same character repeated (e.g. "aaaa", "hhhh")
        if len(set(alpha_content.lower())) <= 1 and len(alpha_content) < 6:
            return False

        # Layer 5: Very short single word that's just noise
        words = cleaned.split()
        if len(words) == 1 and len(alpha_content) <= 3:
            # Single very short word — likely noise unless it's a real command
            # Allow common single-word commands
            real_words = {"yes", "no", "hey", "hi", "stop", "go", "play", "pause",
                          "help", "what", "who", "why", "how", "when", "where", "next",
                          "back", "home", "call", "end", "mute", "start", "okay", "sure",
                          "yep", "nah", "nope", "bye", "thanks", "cool", "fine", "good",
                          "bad", "left", "right", "open", "close", "on", "off", "map",
                          "aye", "howay", "pet", "alreet", "canny"}
            if lower not in real_words:
                return False

        # Passed all checks — this is valid speech
        return True

    # ── Temporal Date Reference Parser ────────────────────────────────────────

    def _parse_date_reference(self, date_str: str) -> "date_type | None":
        """
        Parse a temporal date reference into a concrete date object.
        Supports ISO format and relative references.
        Returns None if parsing fails.
        """
        from datetime import date as date_cls, timedelta as td
        import re

        if not date_str:
            return None

        cleaned = date_str.strip().lower()
        today = datetime.now(timezone.utc).date()

        # ISO format: "2025-08-29"
        try:
            return date_cls.fromisoformat(cleaned)
        except (ValueError, TypeError):
            pass

        # Relative references
        if cleaned in ("today", "now"):
            return today
        if cleaned == "yesterday":
            return today - td(days=1)
        if cleaned == "day before yesterday":
            return today - td(days=2)

        # "N days ago"
        match = re.match(r'(\d+)\s*days?\s*ago', cleaned)
        if match:
            return today - td(days=int(match.group(1)))

        # "last week" → 7 days ago
        if cleaned in ("last week", "a week ago"):
            return today - td(days=7)

        # "last monday", "last tuesday", etc.
        day_names = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        match = re.match(r'last\s+(\w+)', cleaned)
        if match:
            day_name = match.group(1).lower()
            if day_name in day_names:
                target_weekday = day_names[day_name]
                current_weekday = today.weekday()
                days_back = (current_weekday - target_weekday) % 7
                if days_back == 0:
                    days_back = 7  # "last Monday" when today IS Monday means 7 days ago
                return today - td(days=days_back)

        logger.warning(f"Could not parse date reference: '{date_str}'")
        return None

    def _get_tools(self):
        """Return the tool definitions for the OpenAI Realtime session."""
        return [
            {
                "type": "function",
                "name": "search_memory",
                "description": "Search the user's long-term memory for past facts, preferences, meals, or events. Use this when the user asks about the past or you need context you don't currently have.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query, e.g. 'what did the user eat', 'user's car', 'how was the user feeling'"}
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "function",
                "name": "store_fact",
                "description": "Explicitly store a fact about the user in long-term memory. Use this when the user says things like 'remember that I...', 'store this fact', 'don't forget that...', or explicitly asks you to remember something.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_key": {"type": "string", "description": "A specific snake_case identifier. Use item-specific keys for things the user can own multiples of: 'user.car.ferrari', 'user.car.tesla', 'user.pet.dog.max', 'user.child.emma'. Use generic keys only for single-value facts: 'user.name', 'user.city', 'user.job'. Same key = overwrite, different key = coexist."},
                        "content": {"type": "string", "description": "The fact as a clear, complete sentence, e.g. 'The user drives a red Ferrari.'"},
                        "importance": {"type": "number", "description": "How important this fact is, 0.0-1.0. Explicit storage requests should be 1.0."}
                    },
                    "required": ["entity_key", "content"]
                }
            },
            {
                "type": "function",
                "name": "search_history",
                "description": "Search past conversation sessions and daily summaries. Use when the user asks about previous conversations or what happened on a specific day. For temporal queries like 'yesterday', 'last week', 'what did I do on Monday', set the 'date' parameter. Returns daily digests and session summaries grouped by date.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to search for in past conversations, e.g. 'driving', 'health discussion', 'last conversation', 'everything'"},
                        "days_back": {"type": "integer", "description": "How many days back to search. Default 30."},
                        "date": {"type": "string", "description": "Specific date to search. ISO format 'YYYY-MM-DD' or relative like 'yesterday', 'today', '2 days ago', 'last monday'. When user asks 'what did I do yesterday?' use 'yesterday'."}
                    },
                    "required": ["query"]
                }
            }
        ]

    async def connect_to_openai(self, system_prompt: str, voice_id: str, max_tokens: int):
        """Establish connection to OpenAI Realtime API and configure the session."""
        logger.info(f"Connecting to OpenAI Realtime for user {self.user_id}")

        self.openai_ws = await websockets.connect(
            f"{OPENAI_REALTIME_URL}&voice={voice_id}",
            additional_headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
            },
            ping_interval=20,
            ping_timeout=10,
        )

        # Add memory tool usage instructions to system prompt
        enhanced_prompt = system_prompt + MEMORY_TOOL_INSTRUCTIONS

        # TESTED WORKING: gpt-realtime-mini accepts ONLY these params.
        # voice set via URL param, transcription via nested audio object.
        if self._use_elevenlabs:
            # When ElevenLabs is active, set OpenAI to text-only mode
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text"],
                    "instructions": enhanced_prompt,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    # No voice or server_vad for ElevenLabs mode (we handle audio manually)
                    "turn_detection": None,
                    "tools": self._get_tools(),
                    "tool_choice": "auto",
                },
            }
            # Connect ElevenLabs TTS
            from app.services.elevenlabs_service import ElevenLabsTTS
            self._elevenlabs_tts = ElevenLabsTTS(
                on_audio_chunk=self._on_elevenlabs_audio,
            )
            await self._elevenlabs_tts.connect()
            logger.info(f"ElevenLabs TTS active: voice={settings.elevenlabs_voice_id}")
        else:
            # Full native OpenAI Realtime mode
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": enhanced_prompt,
                    "voice": voice_id,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.65,
                        "prefix_padding_ms": 400,
                        "silence_duration_ms": 500
                    },
                    "tools": self._get_tools(),
                    "tool_choice": "auto",
                },
            }

        await self.openai_ws.send(json.dumps(session_config))
        logger.info(f"OpenAI Realtime session configured: voice={voice_id}, elevenlabs={self._use_elevenlabs}")

    async def _listen_openai(self):
        """
        Background task: relay events from OpenAI Realtime → browser client.
        Handles all Realtime API event types.
        """
        try:
            async for raw_msg in self.openai_ws:
                event = json.loads(raw_msg)
                event_type = event.get("type", "")

                # Log event types (except noisy audio deltas)
                if "audio" not in event_type or "transcript" in event_type or "done" in event_type:
                    logger.debug(f"[OAI EVENT] {event_type}")

                # ── Audio output chunk → relay to browser ──────────────────
                if event_type in ["response.audio.delta", "response.output_audio.delta"]:
                    # When ElevenLabs is active, ignore OpenAI audio
                    if self._use_elevenlabs:
                        continue
                    # BLOCK audio only during active barge-in window
                    if self._audio_muted:
                        continue
                    delta = event.get("delta", "")
                    if delta:
                        await self.send_to_client({
                            "type": "audio_response",
                            "data": delta,  # base64 PCM16
                        })
                        if self.voice_state != VoiceState.SPEAKING:
                            self.voice_state = VoiceState.SPEAKING
                            await self.send_to_client({"type": "state_change", "state": "speaking"})

                # ── Text transcript of AI output ───────────────────────────
                elif event_type in ["response.audio_transcript.delta", "response.output_audio_transcript.delta",
                                    "response.text.delta", "response.output_text.delta"]:
                    delta = event.get("delta", "")
                    self._current_response_text += delta
                    await self.send_to_client({
                        "type": "text_response",
                        "delta": delta,
                    })
                    # Stream text to ElevenLabs for Geordie TTS
                    if self._use_elevenlabs and self._elevenlabs_tts and delta:
                        await self._elevenlabs_tts.send_text(delta)
                        if self.voice_state != VoiceState.SPEAKING:
                            self.voice_state = VoiceState.SPEAKING
                            await self.send_to_client({"type": "state_change", "state": "speaking"})

                # ── User speech transcript (input) ─────────────────────────
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")

                    # ── Noise rejection gate ──────────────────────────────────
                    if not self._is_valid_speech(transcript):
                        logger.info(f"Noise rejected (user {self.user_id}): '{transcript[:80]}'")
                        # Discard the audio buffer — don't let OpenAI respond to noise
                        await self.send_to_openai({"type": "input_audio_buffer.clear"})
                        await self.send_to_client({
                            "type": "noise_rejected",
                            "transcript": transcript,
                        })
                        # Reset voice state back to listening
                        self.voice_state = VoiceState.LISTENING
                        await self.send_to_client({"type": "state_change", "state": "listening"})
                        continue

                    self._current_user_input = transcript
                    self._transcript_event.set()  # Signal that transcript is ready
                    await self.send_to_client({
                        "type": "transcript",
                        "text": transcript,
                    })
                    self.voice_state = VoiceState.PROCESSING
                    await self.send_to_client({"type": "state_change", "state": "processing"})

                # ── User started speaking (for barge-in feedback) ──────────
                elif event_type == "input_audio_buffer.speech_started":
                    await self.send_to_client({"type": "state_change", "state": "listening"})
                    # If AI was speaking, this is a server-side barge-in
                    if self.voice_state == VoiceState.SPEAKING:
                        logger.info(f"Server-side barge-in detected for user {self.user_id}")
                        self._audio_muted = True  # Block stale audio chunks
                        self.voice_state = VoiceState.LISTENING
                        await self.send_to_openai({"type": "response.cancel"})
                        await self.send_to_openai({"type": "input_audio_buffer.clear"})
                        await self.send_to_client({"type": "barge_in_detected"})
                        self._current_response_text = ""

                # ── New response starting — unmute audio ────────────────────
                elif event_type == "response.created":
                    self._audio_muted = False  # Allow audio from new response

                # ── Response fully complete ────────────────────────────────
                elif event_type == "response.done":
                    self._audio_muted = False  # Safety reset
                    response_obj = event.get("response", {})
                    output_items = response_obj.get("output", [])
                    
                    # Check if this response has text/audio output (not just a tool call)
                    has_text_output = False
                    for item in output_items:
                        if item.get("type") == "message":
                            has_text_output = True
                            for content_part in item.get("content", []):
                                if content_part.get("type") in ["audio", "text"] and content_part.get("transcript"):
                                    if not self._current_response_text:
                                        self._current_response_text = content_part["transcript"]
                                        logger.info(f"Recovered response text from response.done: {self._current_response_text[:100]}")
                    
                    # Only process post-turn for actual text responses, not tool-call-only responses
                    if has_text_output:
                        # Flush ElevenLabs to generate remaining audio
                        if self._use_elevenlabs and self._elevenlabs_tts:
                            await self._elevenlabs_tts.flush()
                        logger.info(f"response.done (text): user='{self._current_user_input[:80] if self._current_user_input else '(empty)'}', response='{self._current_response_text[:80] if self._current_response_text else '(empty)'}'")
                        await self._on_response_done()
                    else:
                        logger.debug(f"response.done (tool-call only): skipping post-turn")

                # ── Tool execution (Real Brain active retrieval) ───────────
                elif event_type == "response.function_call_arguments.done":
                    call_id = event.get("call_id")
                    name = event.get("name")
                    arguments = event.get("arguments", "{}")
                    
                    if name == "search_memory":
                        # Notify frontend to show thinking animation
                        await self.send_to_client({
                            "type": "tool_activity",
                            "tool": "search_memory",
                            "status": "started"
                        })
                        try:
                            args = json.loads(arguments)
                            query = args.get("query", "")
                            logger.info(f"AI searching memory for: {query}")
                            results = await retrieve_relevant_memories(self.user_id, query, self.db, top_k=5)


                            
                            output_str = "Memory search results:\n"
                            if results:
                                for i, r in enumerate(results):
                                    output_str += f"{i+1}. {r['content']}\n"
                            else:
                                output_str += "No relevant memories found in the database."
                                
                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": output_str
                                }
                            })
                            await self.send_to_openai({
                                "type": "response.create"
                            })
                            await self.send_to_client({"type": "tool_activity", "tool": "search_memory", "status": "done"})
                        except Exception as e:
                            logger.error(f"Failed to execute search_memory: {e}")
                            # CRITICAL: Always send output back or OpenAI hangs forever
                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": "Memory search failed. Please answer from what you already know."
                                }
                            })
                            await self.send_to_openai({"type": "response.create"})
                            await self.send_to_client({"type": "tool_activity", "tool": "search_memory", "status": "done"})

                    elif name == "store_fact":
                        # Mark that AI stored facts via tool — skip duplicate extraction in post-turn
                        self._tool_stored_facts_this_turn = True
                        # Notify frontend to show memory update animation
                        await self.send_to_client({
                            "type": "tool_activity",
                            "tool": "store_fact",
                            "status": "started"
                        })
                        try:
                            args = json.loads(arguments)
                            entity_key = args.get("entity_key", "")
                            content = args.get("content", "")
                            importance = float(args.get("importance", 1.0))
                            logger.info(f"AI storing fact: {entity_key} = {content}")

                            embedding = await embed_text(content)

                            # Dedup: check if a very similar fact already exists
                            dedup_result = await self.db.execute(
                                sa_text("""
                                    SELECT id, entity_key, content,
                                           1 - (embedding <=> :emb::vector) as similarity
                                    FROM memories
                                    WHERE user_id = :uid
                                      AND 1 - (embedding <=> :emb::vector) > 0.92
                                    ORDER BY similarity DESC
                                    LIMIT 1
                                """),
                                {"uid": self.user_id, "emb": str(embedding)}
                            )
                            existing = dedup_result.fetchone()

                            if existing:
                                # Update existing record instead of creating duplicate
                                logger.info(f"Dedup: updating existing memory '{existing.entity_key}' instead of creating '{entity_key}'")
                                await self.db.execute(
                                    sa_text("""
                                        UPDATE memories
                                        SET content = :content,
                                            importance_score = :importance,
                                            embedding = :emb::vector,
                                            updated_at = :now,
                                            source_persona_id = :persona
                                        WHERE id = :mid
                                    """),
                                    {
                                        "content": content,
                                        "importance": importance,
                                        "emb": str(embedding),
                                        "now": datetime.now(timezone.utc),
                                        "persona": self.persona_id,
                                        "mid": str(existing.id),
                                    }
                                )
                            else:
                                stmt = pg_insert(Memory).values(
                                    id=uuid.uuid4(),
                                    user_id=self.user_id,
                                    entity_key=entity_key,
                                    content=content,
                                    memory_type="semantic",
                                    importance_score=importance,
                                    confidence_score=1.0,
                                    source_persona_id=self.persona_id,
                                    embedding=embedding,
                                    updated_at=datetime.now(timezone.utc),
                                )
                                if entity_key:
                                    stmt = stmt.on_conflict_do_update(
                                        index_elements=["user_id", "entity_key"],
                                        index_where=sa_text("entity_key IS NOT NULL"),
                                        set_={
                                            "content": stmt.excluded.content,
                                            "importance_score": stmt.excluded.importance_score,
                                            "confidence_score": stmt.excluded.confidence_score,
                                            "embedding": stmt.excluded.embedding,
                                            "updated_at": stmt.excluded.updated_at,
                                            "source_persona_id": stmt.excluded.source_persona_id,
                                        }
                                    )
                                else:
                                    stmt = stmt.on_conflict_do_nothing()

                                await self.db.execute(stmt)

                            await self.db.commit()



                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": f"Fact stored successfully: {content}"
                                }
                            })
                            await self.send_to_openai({"type": "response.create"})
                            await self.send_to_client({"type": "tool_activity", "tool": "store_fact", "status": "done"})
                        except Exception as e:
                            logger.error(f"Failed to store fact: {e}")
                            await self.send_to_client({"type": "tool_activity", "tool": "store_fact", "status": "done"})
                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": "Failed to store fact, but I'll remember it for this session."
                                }
                            })
                            await self.send_to_openai({"type": "response.create"})

                    elif name == "search_history":
                        # Search past conversation sessions — date-aware with daily digest priority
                        await self.send_to_client({
                            "type": "tool_activity",
                            "tool": "search_history",
                            "status": "started"
                        })
                        try:
                            args = json.loads(arguments)
                            query = args.get("query", "")
                            days_back = int(args.get("days_back", 30))
                            date_param = args.get("date", None)
                            logger.info(f"AI searching history: query='{query}' days_back={days_back} date={date_param}")

                            from datetime import timedelta

                            # ── Parse temporal date reference ──────────────────
                            target_date = None
                            if date_param:
                                target_date = self._parse_date_reference(date_param)

                            output = ""

                            # ── Strategy 1: Date-specific query → daily digest first ──
                            if target_date:
                                date_str = target_date.isoformat()
                                logger.info(f"Date-aware history search for {date_str}")

                                # First: try daily digest
                                digest_result = await self.db.execute(
                                    sa_text("""
                                        SELECT entity_key, content, updated_at
                                        FROM memories
                                        WHERE user_id = CAST(:uid AS uuid)
                                          AND entity_key = :digest_key
                                    """),
                                    {"uid": self.user_id, "digest_key": f"daily_digest.{date_str}"}
                                )
                                digest = digest_result.fetchone()

                                if digest:
                                    output += f"Daily summary for {date_str}:\n{digest.content}\n"
                                else:
                                    # No daily digest — fall back to individual session summaries for that date
                                    session_result = await self.db.execute(
                                        sa_text("""
                                            SELECT entity_key, content, updated_at
                                            FROM memories
                                            WHERE user_id = CAST(:uid AS uuid)
                                              AND memory_type = 'episodic'
                                              AND entity_key LIKE :pattern
                                            ORDER BY updated_at ASC
                                        """),
                                        {"uid": self.user_id, "pattern": f"session.{date_str}.%"}
                                    )
                                    sessions = session_result.fetchall()
                                    if sessions:
                                        output += f"Sessions from {date_str}:\n"
                                        for i, s in enumerate(sessions):
                                            output += f"  {i+1}. {s.content}\n"

                                # Also search raw turns for that date for detail
                                date_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                                date_end = date_start + timedelta(days=1)
                                turn_result = await self.db.execute(
                                    sa_text("""
                                        SELECT role, content, created_at
                                        FROM session_turns
                                        WHERE user_id = CAST(:uid AS uuid)
                                          AND created_at >= :start AND created_at < :end
                                        ORDER BY created_at DESC
                                        LIMIT 10
                                    """),
                                    {"uid": self.user_id, "start": date_start, "end": date_end}
                                )
                                turns = turn_result.fetchall()
                                if turns:
                                    output += f"\nConversation excerpts from {date_str}:\n"
                                    for t in turns:
                                        ts = str(t.created_at)[:16] if t.created_at else "unknown"
                                        role = "User" if t.role == "user" else "GeordieDaz"
                                        output += f"- [{ts}] {role}: {t.content[:150]}\n"

                            # ── Strategy 2: General query → vector similarity search ──
                            else:
                                query_embedding = await embed_text(query)
                                cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

                                # Prioritise daily digests, then individual sessions
                                result = await self.db.execute(
                                    sa_text("""
                                        SELECT entity_key, content, updated_at,
                                               1 - (embedding <=> :emb::vector) as similarity
                                        FROM memories
                                        WHERE user_id = CAST(:uid AS uuid)
                                          AND memory_type = 'episodic'
                                          AND updated_at >= :cutoff
                                          AND 1 - (embedding <=> :emb::vector) > 0.3
                                        ORDER BY
                                          CASE WHEN entity_key LIKE 'daily_digest.%' THEN 0 ELSE 1 END,
                                          similarity DESC
                                        LIMIT 8
                                    """),
                                    {"uid": self.user_id, "emb": str(query_embedding), "cutoff": cutoff}
                                )
                                summaries = result.fetchall()

                                if summaries:
                                    output = "Past conversation history:\n"
                                    for s in summaries:
                                        date_str = str(s.updated_at)[:10] if s.updated_at else "unknown"
                                        prefix = "📅 Daily" if s.entity_key and s.entity_key.startswith("daily_digest.") else "💬 Session"
                                        output += f"- [{date_str}] {prefix}: {s.content}\n"

                                # Also search raw turns for more detail
                                turn_result = await self.db.execute(
                                    sa_text("""
                                        SELECT role, content, created_at
                                        FROM session_turns
                                        WHERE user_id = CAST(:uid AS uuid)
                                          AND created_at >= :cutoff
                                          AND content ILIKE :pattern
                                        ORDER BY created_at DESC
                                        LIMIT 10
                                    """),
                                    {"uid": self.user_id, "cutoff": cutoff, "pattern": f"%{query.split()[0] if query.split() else ''}%"}
                                )
                                turns = turn_result.fetchall()
                                if turns:
                                    output += "\nRelevant conversation excerpts:\n"
                                    for t in turns:
                                        date_str = str(t.created_at)[:16] if t.created_at else "unknown"
                                        role = "User" if t.role == "user" else "GeordieDaz"
                                        output += f"- [{date_str}] {role}: {t.content[:150]}\n"



                            if not output:
                                output = "No matching conversation history found for the given query and time range."

                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": output
                                }
                            })
                            await self.send_to_openai({"type": "response.create"})
                            await self.send_to_client({"type": "tool_activity", "tool": "search_history", "status": "done"})
                        except Exception as e:
                            logger.error(f"Failed to search history: {e}")
                            await self.send_to_client({"type": "tool_activity", "tool": "search_history", "status": "done"})
                            await self.send_to_openai({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": "History search failed. I don't have access to past sessions right now."
                                }
                            })
                            await self.send_to_openai({"type": "response.create"})

                # ── Input buffer committed (VAD detected end of speech) ────
                elif event_type == "input_audio_buffer.speech_stopped":
                    self.voice_state = VoiceState.PROCESSING
                    await self.send_to_client({"type": "state_change", "state": "processing"})

                # ── Session created/updated confirmation ───────────────────
                elif event_type == "session.created":
                    logger.info(f"OpenAI Realtime session created for user {self.user_id}")
                    await self.send_to_client({
                        "type": "session_ready",
                        "session_id": self.session_id,
                        "persona_id": self.persona_id,
                    })

                # ── Error from OpenAI ──────────────────────────────────────
                elif event_type == "error":
                    error_msg = event.get("error", {}).get("message", "Unknown error")
                    # Suppress harmless barge-in timing errors
                    if "no active response" in error_msg.lower() or "cancellation failed" in error_msg.lower():
                        logger.debug(f"Suppressed harmless error: {error_msg}")
                    else:
                        logger.error(f"OpenAI Realtime error: {error_msg}")
                        await self.send_to_client({
                            "type": "error",
                            "message": f"Voice error: {error_msg}",
                        })

        except websockets.ConnectionClosed as e:
            logger.info(f"OpenAI WS closed for user {self.user_id}: {e}")
        except Exception as e:
            logger.error(f"OpenAI listener error: {e}")
            await self.send_to_client({"type": "error", "message": "Voice connection lost"})

    async def _on_elevenlabs_audio(self, audio_b64: str):
        """Callback: receive audio chunk from ElevenLabs, forward to client."""
        if self._audio_muted:
            return
        await self.send_to_client({
            "type": "audio_response",
            "data": audio_b64,  # base64 PCM16
        })
        if self.voice_state != VoiceState.SPEAKING:
            self.voice_state = VoiceState.SPEAKING
            await self.send_to_client({"type": "state_change", "state": "speaking"})

    # ── Open-source mode callbacks (Deepgram STT + Groq LLM) ──────────────

    async def _on_deepgram_transcript(self, transcript: str):
        """Called when Deepgram produces a final STT transcript."""
        self._current_user_input = transcript
        self.voice_state = VoiceState.PROCESSING
        await self.send_to_client({
            "type": "transcript",
            "text": transcript,
            "role": "user",
        })

    async def _on_deepgram_response_text(self, delta: str):
        """Called for each Groq streaming text delta."""
        self._current_response_text += delta
        await self.send_to_client({
            "type": "text_response",
            "delta": delta,
        })

    async def _on_deepgram_state_change(self, state: str):
        """Called by Deepgram handler to signal voice state changes."""
        state_map = {
            "listening": VoiceState.LISTENING,
            "processing": VoiceState.PROCESSING,
            "speaking": VoiceState.SPEAKING,
            "idle": VoiceState.IDLE,
        }
        self.voice_state = state_map.get(state, VoiceState.IDLE)
        await self.send_to_client({"type": "state_change", "state": state})

    async def _handle_tool_call_opensource(self, name: str, args: dict, call_id: str) -> str:
        """
        Execute a tool call from Groq and return the result string.
        Mirrors the tool handling in _listen_openai but returns a result instead
        of sending it back to OpenAI (Groq handles that via conversation history).
        """
        import json as _json
        result = "Done."
        try:
            if name == "search_memory":
                query = args.get("query", "")
                logger.info(f"[OS Tool] search_memory: {query}")
                results = await retrieve_relevant_memories(self.user_id, query, self.db, top_k=5)
                if results:
                    lines = [f"- {r.get('content', '')} (importance: {r.get('importance_score', 0):.2f})" for r in results]
                    result = "Memory search results:\n" + "\n".join(lines)
                else:
                    result = "No relevant memories found."

            elif name == "store_fact":
                entity_key = args.get("entity_key", "")
                content = args.get("content", "")
                importance = float(args.get("importance", 0.7))
                logger.info(f"[OS Tool] store_fact: {entity_key}")
                if entity_key and content:
                    entity_key = entity_key.replace("_", ".")
                    from sqlalchemy import text as sa_text
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    from app.models.memory import Memory
                    embedding = await embed_text(content)
                    stmt = pg_insert(Memory).values(
                        id=str(uuid.uuid4()),
                        user_id=self.user_id,
                        entity_key=entity_key,
                        content=content,
                        memory_type="semantic",
                        importance_score=importance,
                        confidence_score=0.9,
                        source_persona_id=self.persona_id,
                        embedding=embedding,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    ).on_conflict_do_update(
                        index_elements=["user_id", "entity_key"],
                        index_where=sa_text("entity_key IS NOT NULL"),
                        set_={
                            "content": content,
                            "importance_score": importance,
                            "embedding": embedding,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                    await self.db.execute(stmt)
                    await self.db.commit()
                    self._tool_stored_facts_this_turn = True
                    result = f"Stored: {entity_key}"

            elif name == "search_history":
                query = args.get("query", "")
                logger.info(f"[OS Tool] search_history: {query}")
                from sqlalchemy import select as sa_select
                from app.models.session import SessionTurn
                from sqlalchemy.ext.asyncio import AsyncSession
                from app.models.memory import Memory
                # 1. Fetch episodic memories (daily digests and session summaries)
                ep_rows = await self.db.execute(
                    sa_select(Memory)
                    .where(Memory.user_id == self.user_id, Memory.memory_type == "episodic")
                    .order_by(Memory.updated_at.desc())
                    .limit(6)
                )
                episodes = ep_rows.scalars().all()

                # 2. Fetch recent turns
                rows = await self.db.execute(
                    sa_select(SessionTurn)
                    .where(SessionTurn.user_id == self.user_id)
                    .order_by(SessionTurn.created_at.desc())
                    .limit(10)
                )
                turns = rows.scalars().all()

                lines = []
                if episodes:
                    lines.append("Past session and day summaries:")
                    for ep in episodes:
                        lines.append(f"  • [{ep.entity_key}] {ep.content}")
                if turns:
                    lines.append("\nRecent conversation turns:")
                    for t in reversed(turns):
                        lines.append(f"  • {t.role}: {t.content[:100]}")

                result = "\n".join(lines) if lines else "No past history found."

        except Exception as e:
            logger.error(f"[OS Tool] {name} failed: {e}")
            result = f"Tool error: {e}"

        return result

    async def _on_response_done(self):
        """Called when OpenAI completes a full response. Triggers post-turn processing."""
        self.voice_state = VoiceState.IDLE
        await self.send_to_client({"type": "state_change", "state": "idle"})

        if not self._current_response_text:
            logger.debug(f"Skipping post-turn: no response text captured")
            self._current_response_text = ""
            self._current_user_input = ""
            return

        # Wait for Whisper transcription — it arrives AFTER response.done
        # Use event-based wait with timeout instead of fragile sleep
        if not self._current_user_input:
            self._transcript_event.clear()
            try:
                await asyncio.wait_for(self._transcript_event.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning(f"Transcript not received within 3s for user {self.user_id}")


        user_input = self._current_user_input or "(speech detected but transcript unavailable)"
        response_text = self._current_response_text

        logger.info(f"Post-turn starting: user='{user_input[:60]}' ai='{response_text[:60]}'")

        # Run post-turn: write memory + update session
        state = self._agent_state
        if not state:
            logger.warning("No agent state found — creating minimal state for memory extraction")
            state = {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "persona_id": self.persona_id,
                "persona_config": None,
                "user_input": user_input,
                "response_text": response_text,
                "assembled_system_prompt": "",
                "turn_index": 0,
            }
        
        state["user_input"] = user_input
        state["response_text"] = response_text
        state["interrupted"] = False  # Reset — each turn decides independently
        # FIX #1: Skip duplicate extraction if AI already stored facts via tool calls
        state["skip_extraction"] = self._tool_stored_facts_this_turn
        if self._tool_stored_facts_this_turn:
            logger.info("Skipping background extraction — AI already stored facts via store_fact tool")
        try:
            await run_post_turn(state, self.db)
            logger.info("Post-turn completed successfully")


        except Exception as e:
            logger.error(f"Post-turn processing failed: {e}", exc_info=True)

        # Reset per-turn state
        self._current_response_text = ""
        self._current_user_input = ""
        self._tool_stored_facts_this_turn = False  # Reset for next turn
        self._turn_count += 1

        # Signal turn complete to client: transition to idle and notify memory HUD
        self.voice_state = VoiceState.IDLE
        await self.send_to_client({"type": "state_change", "state": "idle"})
        await self.send_to_client({"type": "memory_updated"})

    async def initialise_session(self):
        """
        Run pre-turn graph to prepare context, then open OpenAI Realtime connection.
        Called once when the WebSocket session is established.
        """
        try:
            # Backfill any missing daily digests (lazy consolidation)
            try:
                from app.services.session_summary_service import ensure_previous_day_digest
                await ensure_previous_day_digest(user_id=self.user_id, db=self.db)
            except Exception as e:
                logger.warning(f"Daily digest backfill failed (non-fatal): {e}")

            # If client explicitly provided a persona_id in query params, enforce it!
            if self._initial_persona_id:
                self.persona_id = self._initial_persona_id
                from app.services.persona_service import persona_manager
                await persona_manager.hot_swap(
                    user_id=self.user_id,
                    new_persona_id=self._initial_persona_id,
                    session_id=self.session_id,
                )

            # Run pre-turn graph (loads session, retrieves memory, assembles context)
            state = await run_pre_turn(
                user_id=self.user_id,
                session_id=self.session_id,
                user_input="",  # No input yet — just loading context
                persona_id=self.persona_id,
                db=self.db,
            )
            self._agent_state = state
            if not self._initial_persona_id:
                self.persona_id = state.get("persona_id", "friendly_geordie")
            # Sync session_id — load_session may have loaded it from Redis
            self.session_id = state.get("session_id", self.session_id)

            # Get persona config for voice settings
            persona_config = state.get("persona_config", {})
            voice_profile = persona_config.get("voice_profile", {})
            voice_id = voice_profile.get("voice_id", "alloy")
            response_rules = persona_config.get("response_rules", {})
            max_tokens = response_rules.get("max_tokens", 150)
            system_prompt = state.get("assembled_system_prompt", "You are GeordieDaz.")

            # ── Provider Branch ─────────────────────────────────────────────
            if settings.use_opensource:
                # Open-source mode: Deepgram STT + Groq LLM + ElevenLabs TTS
                logger.info(f"Starting opensource voice pipeline (Deepgram+Groq) for user {self.user_id}")
                from app.ws.deepgram_handler import DeepgramVoiceHandler
                self._deepgram = DeepgramVoiceHandler(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    persona_id=self.persona_id,
                    system_prompt=system_prompt,
                    db=self.db,
                    on_transcript=self._on_deepgram_transcript,
                    on_response_text=self._on_deepgram_response_text,
                    on_response_done=self._on_response_done,
                    on_audio_chunk=self._on_elevenlabs_audio,
                    on_tool_call=self._handle_tool_call_opensource,
                    on_state_change=self._on_deepgram_state_change,
                )
                await self._deepgram.connect()
            else:
                # OpenAI Realtime mode
                await self.connect_to_openai(system_prompt, voice_id, max_tokens)
                self._openai_task = asyncio.create_task(self._listen_openai())

            logger.info(f"Session initialised for user {self.user_id}, persona={self.persona_id}")
            # Broadcast confirmed active persona to client immediately so HUD never desyncs!
            await self.send_to_client({
                "type": "persona_switched",
                "persona_id": self.persona_id,
                "persona_name": persona_config.get("name", self.persona_id),
                "ui_theme_color": persona_config.get("ui_theme_color", "#00f0ff"),
                "message": f"Active persona: {persona_config.get('name')}",
            })

        except Exception as e:
            logger.error(f"Session initialisation failed for {self.user_id}: {e}", exc_info=True)
            await self.send_to_client({
                "type": "error",
                "message": f"Failed to initialise voice session: {str(e)}",
            })
            raise

    async def handle_client_message(self, raw: str):
        """Route incoming messages from the browser to appropriate handlers."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from client {self.user_id}")
            return

        msg_type = msg.get("type")

        if msg_type == "audio_chunk":
            audio_data = msg.get("data", "")
            if audio_data:
                if settings.use_opensource and self._deepgram:
                    # Route to Deepgram STT
                    await self._deepgram.send_audio(audio_data)
                else:
                    # Route to OpenAI Realtime buffer
                    await self.send_to_openai({
                        "type": "input_audio_buffer.append",
                        "audio": audio_data,
                    })

        elif msg_type == "barge_in":
            # User interrupted — cancel current response
            self._audio_muted = True
            self.voice_state = VoiceState.LISTENING
            if settings.use_opensource and self._deepgram:
                await self._deepgram.cancel_response()
            else:
                await self.send_to_openai({"type": "response.cancel"})
                await self.send_to_openai({"type": "input_audio_buffer.clear"})
            await self.send_to_client({"type": "barge_in_detected"})
            if self._agent_state:
                self._agent_state["interrupted"] = True
            self._current_response_text = ""
            logger.info(f"Barge-in processed for user {self.user_id}")

        elif msg_type == "persona_switch":
            # Hot-swap persona without losing memory
            new_persona_id = msg.get("persona_id", "")
            await self._handle_persona_switch(new_persona_id)

        elif msg_type == "ping":
            await self.send_to_client({"type": "pong"})

        elif msg_type == "new_session":
            # User wants a fresh conversation — summarise current session first
            logger.info(f"New session requested by user {self.user_id}")
            try:
                from app.services.session_summary_service import summarise_session
                await summarise_session(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    db=self.db,
                )
                logger.info(f"Session {self.session_id[:12]}... summarised before new session")
            except Exception as e:
                logger.warning(f"Session summary failed on new_session: {e}")
            # Reset session ID and turn counter so next conversation starts fresh
            import uuid as uuid_mod
            self.session_id = str(uuid_mod.uuid4())
            self._turn_count = 0
            try:
                from app.redis_client import get_redis
                redis = get_redis()
                session_key = f"session:{self.user_id}"
                await redis.hset(session_key, "session_id", self.session_id)
                await redis.hset(session_key, "turn_index", 0)
            except Exception as e:
                logger.debug(f"Failed to reset session in Redis: {e}")
            await self.send_to_client({"type": "memory_updated"})

        elif msg_type == "commit_audio":
            # Manually commit audio buffer (for push-to-talk mode)
            await self.send_to_openai({"type": "input_audio_buffer.commit"})
            await self.send_to_openai({"type": "response.create"})

    async def _handle_persona_switch(self, new_persona_id: str):
        """
        Hot-swap persona (PRD Figure 4 — Persona Switch Flow).
        Memory is completely preserved — only system prompt and voice change.
        FIX #4: 5-second cooldown to prevent rapid toggling (each switch creates a new Realtime session).
        """
        if not new_persona_id:
            return

        # Cooldown only needed for OpenAI Realtime API mode (slow TLS reconnects)
        if not settings.use_opensource:
            import time
            now = time.time()
            if now - self._last_persona_switch_time < 3.0:
                await self.send_to_client({
                    "type": "error",
                    "message": "Whoa, slow down! Wait a few seconds before switching persona again.",
                })
                return
            self._last_persona_switch_time = now
        try:
            config = await persona_manager.hot_swap(
                user_id=self.user_id,
                new_persona_id=new_persona_id,
                session_id=self.session_id,
            )
            self.persona_id = new_persona_id

            # Update agent state persona
            if self._agent_state:
                self._agent_state["persona_id"] = new_persona_id
                self._agent_state["persona_config"] = config.model_dump()

            # Re-assemble context with new persona (preserves existing memories)
            if self._agent_state:
                from app.agent.nodes.assemble_context import assemble_context
                self._agent_state = await assemble_context(self._agent_state)
                new_prompt = self._agent_state.get("assembled_system_prompt", "")
            else:
                new_prompt = config.system_prompt

            # Update OpenAI Realtime session with new persona
            voice_id = config.voice_profile.voice_id
            max_tokens = config.response_rules.max_tokens

            # Add same memory tool instructions as initial config
            enhanced_prompt = new_prompt + MEMORY_TOOL_INSTRUCTIONS

            if settings.use_opensource and self._deepgram:
                # In opensource mode (Deepgram STT + Groq LLM + ElevenLabs TTS):
                # Simply update the system prompt in the deepgram/groq handler!
                self._deepgram.system_prompt = enhanced_prompt
                logger.info(f"Persona switched in opensource mode: user={self.user_id} → {new_persona_id}")
            else:
                # Full reconnect — for OpenAI Realtime API mode
                try:
                    await self.send_to_client({"type": "state_change", "state": "reconnecting"})

                    # Cancel active response and close OpenAI connection
                    try:
                        await self.send_to_openai({"type": "response.cancel"})
                    except Exception:
                        pass

                    if self._openai_task and not self._openai_task.done():
                        self._openai_task.cancel()
                    if self.openai_ws:
                        try:
                            await self.openai_ws.close()
                        except Exception:
                            pass

                    # Reconnect with new voice + instructions
                    await self.connect_to_openai(enhanced_prompt, voice_id, max_tokens)
                    self._openai_task = asyncio.create_task(self._listen_openai())
                    logger.info(f"Persona switched via reconnect: user={self.user_id} → {new_persona_id}")
                except Exception as e:
                    logger.error(f"Persona switch failed: {e}")
                    await self.send_to_client({"type": "error", "message": f"Persona switch failed: {e}"})

            await self.send_to_client({
                "type": "persona_switched",
                "persona_id": new_persona_id,
                "persona_name": config.name,
                "ui_theme_color": config.ui_theme_color,
                "message": f"Switched to {config.name} — memory preserved.",
            })
            logger.info(f"Persona switched: user={self.user_id} → {new_persona_id}")

        except KeyError as e:
            await self.send_to_client({
                "type": "error",
                "message": f"Unknown persona: {new_persona_id}",
            })

    async def close(self):
        """Clean up connections and generate session summary."""
        # Cancel OpenAI task (no-op in opensource mode)
        if self._openai_task and not self._openai_task.done():
            self._openai_task.cancel()
        if self.openai_ws:
            try:
                await self.openai_ws.close()
            except Exception:
                pass

        # Close Deepgram handler (opensource mode)
        if self._deepgram:
            try:
                await self._deepgram.close()
            except Exception:
                pass

        # FIX #3: Only summarise sessions with 2+ completed turns.
        # Prevents wasted GPT calls on dropped connections / very short sessions.
        if self._turn_count >= 2:
            try:
                from app.services.session_summary_service import summarise_session
                await summarise_session(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    db=self.db,
                )
            except Exception as e:
                logger.warning(f"Session summary failed for user {self.user_id}: {e}")
        else:
            logger.info(f"Skipping session summary — only {self._turn_count} turns (need 2+)")

        logger.info(f"Session closed for user {self.user_id}")

        # Rotate session ID in Redis so the next connection starts a fresh session
        try:
            from app.redis_client import get_redis
            import uuid as uuid_mod
            redis = get_redis()
            session_key = f"session:{self.user_id}"
            await redis.hset(session_key, "session_id", str(uuid_mod.uuid4()))
            await redis.hset(session_key, "turn_index", 0)
        except Exception:
            pass


# ─── FastAPI WebSocket Endpoint Handler ────────────────────────────────────

async def handle_websocket(
    websocket: WebSocket,
    user_id: str,
    db: AsyncSession,
    initial_persona_id: Optional[str] = None,
):
    """
    Main WebSocket handler — entry point for /ws/{user_id}.
    Auth is verified by the route before this is called.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: user={user_id}, persona_param={initial_persona_id}")

    handler = RealtimeSessionHandler(user_id=user_id, client_ws=websocket, db=db, initial_persona_id=initial_persona_id)

    try:
        # Initialise the session (runs LangGraph pre-turn, connects to OpenAI)
        await handler.initialise_session()

        # Listen for client messages
        while True:
            raw = await websocket.receive_text()
            await handler.handle_client_message(raw)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}", exc_info=True)
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "An unexpected error occurred. Please refresh and try again.",
            }))
        except Exception:
            pass
    finally:
        await handler.close()
