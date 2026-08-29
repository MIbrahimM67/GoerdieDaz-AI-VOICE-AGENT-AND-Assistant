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
from typing import Optional

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import run_post_turn, run_pre_turn
from app.agent.state import AgentState
from app.config import get_settings
from app.services.persona_service import persona_manager

logger = logging.getLogger(__name__)
settings = get_settings()

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

    def __init__(self, user_id: str, client_ws: WebSocket, db: AsyncSession):
        self.user_id = user_id
        self.client_ws = client_ws
        self.db = db
        self.session_id = str(uuid.uuid4())
        self.persona_id = "friendly_geordie"
        self.voice_state = VoiceState.IDLE
        self.openai_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._openai_task: Optional[asyncio.Task] = None
        self._current_response_text = ""
        self._current_user_input = ""
        self._agent_state: Optional[AgentState] = None
        self._audio_muted = False  # Set during barge-in, cleared on new response
        # ElevenLabs TTS (Geordie voice)
        self._use_elevenlabs = settings.use_elevenlabs
        self._elevenlabs_tts = None

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
                "description": "Search past conversation sessions. Use when the user asks about previous conversations, e.g. 'what did we talk about last time?', 'where were we driving?', 'what did we do last Friday?'. Returns session summaries with dates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to search for in past conversations, e.g. 'driving', 'health discussion', 'last conversation'"},
                        "days_back": {"type": "integer", "description": "How many days back to search. Default 30."}
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
                "OpenAI-Beta": "realtime=v1",
            },
            ping_interval=20,
            ping_timeout=10,
        )

        # Add memory tool usage instructions to system prompt
        memory_instructions = """

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
   Do NOT say any filler — just call the tool silently.

CRITICAL: If the user asks about themselves and you don't search_memory first, you are FAILING your job. Never say "I don't know" or "I don't have that information" without searching first.

IMPORTANT: When calling tools, do NOT generate any speech or filler text before the tool call. Just call the tool and respond with the result."""

        enhanced_prompt = system_prompt + memory_instructions

        # TESTED WORKING: gpt-realtime-mini accepts ONLY these params.
        # voice set via URL param, transcription via nested audio object.
        # When ElevenLabs is active, set OpenAI to text-only mode
        if self._use_elevenlabs:
            session_config = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "modalities": ["text", "audio"],
                    "instructions": enhanced_prompt,
                    "audio": {
                        "input": {
                            "transcription": {
                                "model": "gpt-4o-transcribe",
                                "language": "en"
                            }
                        },
                        "output": {
                            "voice": voice_id  # Still needed for modality, but we won't use the audio
                        }
                    },
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
            session_config = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": enhanced_prompt,
                    "audio": {
                        "input": {
                            "transcription": {
                                "model": "gpt-4o-transcribe",
                                "language": "en"
                            }
                        },
                        "output": {
                            "voice": voice_id
                        }
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

                # Debug: log every event type to file (except noisy audio deltas)
                if "audio" not in event_type or "transcript" in event_type or "done" in event_type:
                    logger.info(f"[OAI EVENT] {event_type}")
                    with open("oai_events.log", "a") as f:
                        f.write(f"{event_type}\n")

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
                    self._current_user_input = transcript
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
                            
                            from app.services.memory_service import retrieve_relevant_memories
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

                            from app.services.embedding_service import embed_text
                            from app.models.memory import Memory
                            from sqlalchemy.dialects.postgresql import insert as pg_insert
                            from datetime import datetime, timezone
                            import uuid as uuid_mod

                            embedding = await embed_text(content)

                            # Dedup: check if a very similar fact already exists
                            from sqlalchemy import text as sa_text
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
                                    id=uuid_mod.uuid4(),
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
                                        index_elements=None,
                                        constraint="ix_memories_user_entity",
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
                        # Search past conversation sessions
                        await self.send_to_client({
                            "type": "tool_activity",
                            "tool": "search_history",
                            "status": "started"
                        })
                        try:
                            args = json.loads(arguments)
                            query = args.get("query", "")
                            days_back = int(args.get("days_back", 30))
                            logger.info(f"AI searching history: query='{query}' days_back={days_back}")

                            from app.services.embedding_service import embed_text
                            from sqlalchemy import text as sa_text
                            from datetime import datetime, timezone, timedelta

                            query_embedding = await embed_text(query)
                            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

                            # Search episodic session summaries
                            result = await self.db.execute(
                                sa_text("""
                                    SELECT entity_key, content, updated_at,
                                           1 - (embedding <=> :emb::vector) as similarity
                                    FROM memories
                                    WHERE user_id = :uid
                                      AND memory_type = 'episodic'
                                      AND updated_at >= :cutoff
                                      AND 1 - (embedding <=> :emb::vector) > 0.3
                                    ORDER BY similarity DESC
                                    LIMIT 5
                                """),
                                {"uid": self.user_id, "emb": str(query_embedding), "cutoff": cutoff}
                            )
                            summaries = result.fetchall()

                            output = ""
                            if summaries:
                                output = "Past session summaries:\n"
                                for s in summaries:
                                    date_str = str(s.updated_at)[:10] if s.updated_at else "unknown"
                                    output += f"- [{date_str}] {s.content}\n"
                            
                            # Also search raw turns for more detail
                            turn_result = await self.db.execute(
                                sa_text("""
                                    SELECT role, content, created_at
                                    FROM session_turns
                                    WHERE user_id = :uid
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

    async def _on_response_done(self):
        """Called when OpenAI completes a full response. Triggers post-turn processing."""
        self.voice_state = VoiceState.IDLE
        await self.send_to_client({"type": "state_change", "state": "idle"})

        if not self._current_response_text:
            logger.debug(f"Skipping post-turn: no response text captured")
            self._current_response_text = ""
            self._current_user_input = ""
            return

        # Wait briefly for Whisper transcription — it arrives AFTER response.done
        # Without this, _current_user_input is always empty
        if not self._current_user_input:
            await asyncio.sleep(1.5)


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
        try:
            await run_post_turn(state, self.db)
            logger.info("Post-turn completed successfully")
        except Exception as e:
            logger.error(f"Post-turn processing failed: {e}", exc_info=True)

        self._current_response_text = ""
        self._current_user_input = ""

    async def initialise_session(self):
        """
        Run pre-turn graph to prepare context, then open OpenAI Realtime connection.
        Called once when the WebSocket session is established.
        """
        try:
            # Run pre-turn graph (loads session, retrieves memory, assembles context)
            state = await run_pre_turn(
                user_id=self.user_id,
                session_id=self.session_id,
                user_input="",  # No input yet — just loading context
                persona_id=self.persona_id,
                db=self.db,
            )
            self._agent_state = state
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

            # Connect to OpenAI Realtime
            await self.connect_to_openai(system_prompt, voice_id, max_tokens)

            # Start listening to OpenAI events
            self._openai_task = asyncio.create_task(self._listen_openai())

            logger.info(f"Session initialised for user {self.user_id}, persona={self.persona_id}")

        except Exception as e:
            logger.error(f"Session initialisation failed for {self.user_id}: {e}")
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
            # Relay PCM16 audio to OpenAI
            audio_data = msg.get("data", "")
            if audio_data:
                await self.send_to_openai({
                    "type": "input_audio_buffer.append",
                    "audio": audio_data,  # base64 PCM16
                })

        elif msg_type == "barge_in":
            # User interrupted — cancel current response + stop audio
            self._audio_muted = True  # Block further audio forwarding
            self.voice_state = VoiceState.LISTENING
            await self.send_to_openai({"type": "response.cancel"})
            await self.send_to_openai({"type": "input_audio_buffer.clear"})
            await self.send_to_client({"type": "barge_in_detected"})  # Tell client to stop playback
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
            # Reset session ID so the next connection gets a fresh one
            import uuid as uuid_mod
            self.session_id = str(uuid_mod.uuid4())

        elif msg_type == "commit_audio":
            # Manually commit audio buffer (for push-to-talk mode)
            await self.send_to_openai({"type": "input_audio_buffer.commit"})
            await self.send_to_openai({"type": "response.create"})

    async def _handle_persona_switch(self, new_persona_id: str):
        """
        Hot-swap persona (PRD Figure 4 — Persona Switch Flow).
        Memory is completely preserved — only system prompt and voice change.
        """
        if not new_persona_id:
            return
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
            memory_instructions = """

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
   Do NOT say any filler — just call the tool silently.

CRITICAL: If the user asks about themselves and you don't search_memory first, you are FAILING your job. Never say "I don't know" or "I don't have that information" without searching first.

IMPORTANT: When calling tools, do NOT generate any speech or filler text before the tool call. Just call the tool and respond with the result."""

            enhanced_prompt = new_prompt + memory_instructions

            # Full reconnect — the only reliable way to change voice in GA API
            # In-place session.update with voice change is rejected if audio is present
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
        """Clean up both WebSocket connections and generate session summary."""
        if self._openai_task and not self._openai_task.done():
            self._openai_task.cancel()
        if self.openai_ws:
            try:
                await self.openai_ws.close()
            except Exception:
                pass

        # Generate session summary for long-term memory
        try:
            from app.services.session_summary_service import summarise_session
            await summarise_session(
                user_id=self.user_id,
                session_id=self.session_id,
                db=self.db,
            )
        except Exception as e:
            logger.warning(f"Session summary failed for user {self.user_id}: {e}")

        logger.info(f"Session closed for user {self.user_id}")


# ─── FastAPI WebSocket Endpoint Handler ────────────────────────────────────

async def handle_websocket(
    websocket: WebSocket,
    user_id: str,
    db: AsyncSession,
):
    """
    Main WebSocket handler — entry point for /ws/{user_id}.
    Auth is verified by the route before this is called.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: user={user_id}")

    handler = RealtimeSessionHandler(user_id=user_id, client_ws=websocket, db=db)

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
        logger.error(f"WebSocket error for user {user_id}: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "An unexpected error occurred. Please refresh and try again.",
            }))
        except Exception:
            pass
    finally:
        await handler.close()
