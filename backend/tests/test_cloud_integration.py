"""
GeordieDaz — Deep Cloud Integration Test
Tests every critical path against LIVE cloud infrastructure (Supabase + Upstash Redis).

Run: python -m tests.test_cloud_integration  (from backend/)
"""
import asyncio
import json
import sys
import os
import uuid
from datetime import datetime, timezone

# Add parent to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from dotenv import load_dotenv
load_dotenv()

# Track results
results = []

def log_result(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"test": test_name, "passed": passed, "detail": detail})
    print(f"  [{status}] {test_name}" + (f" -- {detail}" if detail else ""))


async def main():
    print("=" * 70)
    print("  GeordieDaz -- Deep Cloud Integration Test Suite")
    print("  Testing LIVE Supabase (Postgres) + Upstash (Redis)")
    print("=" * 70)

    # ─── 1. CONFIG LOAD ─────────────────────────────────────────────────
    print("\n[1/8] Configuration Load")
    try:
        from app.config import get_settings
        settings = get_settings()
        log_result("Config loads", True)
        log_result("OpenAI key present", bool(settings.openai_api_key), 
                   f"Key starts with: {settings.openai_api_key[:10]}...")
        log_result("Database URL present", bool(settings.database_url),
                   "Supabase" if "supabase" in settings.database_url else "Local")
        log_result("Redis URL present", bool(settings.redis_url),
                   "Upstash" if "upstash" in settings.redis_url else "Local")
        log_result("ElevenLabs configured", settings.use_elevenlabs,
                   f"Voice ID: {settings.elevenlabs_voice_id[:8]}..." if settings.elevenlabs_voice_id else "Not set")
        log_result("ElevenLabs model", settings.elevenlabs_model_id == "eleven_v3",
                   f"Model: {settings.elevenlabs_model_id}")
    except Exception as e:
        log_result("Config loads", False, str(e))
        print("\n  FATAL: Cannot proceed without config. Exiting.")
        return

    # ─── 2. POSTGRES (SUPABASE) CONNECTION ──────────────────────────────
    print("\n[2/8] PostgreSQL / Supabase Connection")
    try:
        from app.database import engine, AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.scalar()
            log_result("Postgres connection", row == 1, "SELECT 1 returned 1")

            # Check pgvector extension
            result = await session.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            has_vector = result.scalar()
            log_result("pgvector extension", has_vector == "vector", 
                       "Installed" if has_vector else "NOT INSTALLED -- memories will fail!")

            # Check tables exist
            result = await session.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ('users', 'memories', 'usage_logs')"
            ))
            tables = [r[0] for r in result.fetchall()]
            log_result("users table", "users" in tables)
            log_result("memories table", "memories" in tables)
            log_result("usage_logs table", "usage_logs" in tables)

    except Exception as e:
        log_result("Postgres connection", False, str(e))

    # ─── 3. REDIS (UPSTASH) CONNECTION ──────────────────────────────────
    print("\n[3/8] Redis / Upstash Connection")
    try:
        from app.redis_client import get_redis
        redis = get_redis()

        # Test write
        test_key = f"test:geordiedaz:{uuid.uuid4().hex[:8]}"
        await redis.set(test_key, "cloud_test_ok", ex=60)
        log_result("Redis write", True, f"Key: {test_key}")

        # Test read
        val = await redis.get(test_key)
        log_result("Redis read", val == "cloud_test_ok" or val == b"cloud_test_ok",
                   f"Got: {val}")

        # Test delete
        await redis.delete(test_key)
        log_result("Redis delete", True)

        # Test working memory pattern
        wm_key = f"working_memory:test_{uuid.uuid4().hex[:8]}"
        test_turns = [
            {"role": "user", "content": "What car do I drive?", "persona_id": "friendly_geordie"},
            {"role": "assistant", "content": "Wey aye man, you drive a proper mint Tesla!", "persona_id": "friendly_geordie"}
        ]
        await redis.set(wm_key, json.dumps(test_turns), ex=60)
        raw = await redis.get(wm_key)
        parsed = json.loads(raw)
        log_result("Working memory pattern", len(parsed) == 2 and parsed[0]["role"] == "user",
                   f"{len(parsed)} turns stored and retrieved")
        await redis.delete(wm_key)

    except Exception as e:
        log_result("Redis connection", False, str(e))

    # ─── 4. MEMORY STORE + RETRIEVE (FULL PIPELINE) ────────────────────
    print("\n[4/8] Memory Store & Retrieve (Full Pipeline)")
    try:
        from app.models.memory import Memory
        from app.services.embedding_service import embed_text
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy import select

        # Get demo user ID
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": settings.demo_email}
            )
            user_row = result.fetchone()
            if not user_row:
                log_result("Demo user exists", False, f"No user with email {settings.demo_email}")
                print("  Creating demo user for tests...")
                # Try creating one
                from app.services.auth_service import create_demo_user
                user_id = await create_demo_user(session)
                await session.commit()
                log_result("Demo user created", True, f"ID: {user_id}")
            else:
                user_id = str(user_row[0])
                log_result("Demo user exists", True, f"ID: {user_id}")

        # Store test memories
        test_memories = [
            {
                "entity_key": "user.car",
                "content": "The user drives a white Tesla Model 3 Performance",
                "importance": 0.9,
                "type": "semantic",
            },
            {
                "entity_key": "user.name",
                "content": "The user's name is Hamad",
                "importance": 0.95,
                "type": "semantic",
            },
            {
                "entity_key": "user.city",
                "content": "The user lives in Newcastle upon Tyne",
                "importance": 0.85,
                "type": "semantic",
            },
            {
                "entity_key": "user.football",
                "content": "The user supports Newcastle United (the Toon)",
                "importance": 0.8,
                "type": "semantic",
            },
            {
                "entity_key": "user.food",
                "content": "The user's favourite food is chicken parmo from the Toon",
                "importance": 0.75,
                "type": "semantic",
            },
        ]

        stored_count = 0
        async with AsyncSessionLocal() as session:
            for mem in test_memories:
                try:
                    embedding = await embed_text(mem["content"])
                    
                    stmt = pg_insert(Memory).values(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        entity_key=mem["entity_key"],
                        content=mem["content"],
                        memory_type=mem["type"],
                        importance_score=mem["importance"],
                        confidence_score=1.0,
                        source_persona_id="friendly_geordie",
                        embedding=embedding,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_id", "entity_key"],
                        set_={
                            "content": stmt.excluded.content,
                            "importance_score": stmt.excluded.importance_score,
                            "embedding": stmt.excluded.embedding,
                            "updated_at": stmt.excluded.updated_at,
                        },
                    )
                    await session.execute(stmt)
                    stored_count += 1
                except Exception as e:
                    log_result(f"Store memory '{mem['entity_key']}'", False, str(e))
                    
            await session.commit()
        
        log_result("Store test memories", stored_count == len(test_memories),
                   f"{stored_count}/{len(test_memories)} stored via UPSERT")

        # Retrieve test memories via vector search
        from app.services.memory_service import retrieve_relevant_memories

        async with AsyncSessionLocal() as session:
            search_queries = [
                ("what car does the user drive?", "user.car"),
                ("what is the user's name?", "user.name"),
                ("what football team?", "user.football"),
            ]
            for query, expected_key in search_queries:
                try:
                    memories = await retrieve_relevant_memories(
                        user_id=user_id, query=query, db=session, top_k=3
                    )
                    found_expected = any(
                        m.get("entity_key") == expected_key 
                        for m in memories
                    )
                    log_result(
                        f"Retrieve '{expected_key}'",
                        found_expected,
                        f"Got {len(memories)} results, "
                        + (f"found '{expected_key}'" if found_expected else f"MISSING '{expected_key}'")
                    )
                except Exception as e:
                    log_result(f"Retrieve '{expected_key}'", False, str(e))

    except Exception as e:
        log_result("Memory pipeline", False, str(e))

    # ─── 5. PERSONA LOADING ─────────────────────────────────────────────
    print("\n[5/8] Persona Loading")
    try:
        from app.services.persona_service import persona_manager
        
        personas = persona_manager.list_personas()
        log_result("Personas loaded", len(personas) >= 2, f"Found {len(personas)} personas")
        
        for pid in ["friendly_geordie", "driving_banter"]:
            p = persona_manager.get_persona(pid)
            if p:
                has_slang = "howay" in p.get("system_prompt", "").lower()
                log_result(f"Persona '{pid}'", True, 
                           f"Has Geordie slang: {has_slang}, Color: {p.get('ui_theme_color')}")
            else:
                log_result(f"Persona '{pid}'", False, "NOT FOUND")

    except Exception as e:
        log_result("Persona loading", False, str(e))

    # ─── 6. LangGraph Agent Graphs ──────────────────────────────────────
    print("\n[6/8] LangGraph Agent Graphs")
    try:
        from app.agent.graph import pre_turn_graph, post_turn_graph
        log_result("Pre-turn graph compiled", pre_turn_graph is not None)
        log_result("Post-turn graph compiled", post_turn_graph is not None)
        
        # Check nodes
        pre_nodes = list(pre_turn_graph.nodes.keys()) if hasattr(pre_turn_graph, 'nodes') else []
        post_nodes = list(post_turn_graph.nodes.keys()) if hasattr(post_turn_graph, 'nodes') else []
        log_result("Pre-turn nodes", len(pre_nodes) > 0, f"Nodes: {pre_nodes}")
        log_result("Post-turn nodes", len(post_nodes) > 0, f"Nodes: {post_nodes}")
        
    except Exception as e:
        log_result("LangGraph graphs", False, str(e))

    # ─── 7. ElevenLabs Voice Test ───────────────────────────────────────
    print("\n[7/8] ElevenLabs Voice API")
    try:
        import httpx
        
        if settings.use_elevenlabs:
            url = f"https://api.elevenlabs.io/v1/voices/{settings.elevenlabs_voice_id}"
            headers = {"xi-api-key": settings.elevenlabs_api_key}
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    voice_data = resp.json()
                    log_result("ElevenLabs API reachable", True,
                               f"Voice: {voice_data.get('name', 'Unknown')}")
                else:
                    log_result("ElevenLabs API reachable", False,
                               f"HTTP {resp.status_code}: {resp.text[:100]}")
        else:
            log_result("ElevenLabs configured", False, "API key or Voice ID not set")

    except Exception as e:
        log_result("ElevenLabs voice", False, str(e))

    # ─── 8. Session Summary Service ─────────────────────────────────────
    print("\n[8/8] Session Summary Service")
    try:
        from app.services.session_summary_service import (
            consolidate_daily_digest,
            ensure_previous_day_digest,
        )
        log_result("Session summary imports", True, "consolidate + ensure_previous_day_digest")
    except Exception as e:
        log_result("Session summary imports", False, str(e))

    # ─── SUMMARY ────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)
    
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print("=" * 70)
    
    if failed > 0:
        print("\n  FAILURES:")
        for r in results:
            if not r["passed"]:
                print(f"    - {r['test']}: {r['detail']}")
    
    print()
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
