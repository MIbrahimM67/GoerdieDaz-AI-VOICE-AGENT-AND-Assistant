"""
GeordieDaz — FastAPI Application Entry Point
"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import auth, memory, persona, session, usage
from app.config import get_settings
from app.database import AsyncSessionLocal, get_db
from app.middleware.auth_middleware import get_ws_user
from app.redis_client import close_redis, get_redis
from app.services.persona_service import persona_manager
from app.ws.handler import handle_websocket

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle events."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("GeordieDaz starting up...")

    # Load and validate all persona configs from YAML
    persona_manager.initialise()

    # Verify Redis connection
    try:
        redis = get_redis()
        await redis.ping()
        logger.info("Redis connected ✓")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    logger.info("GeordieDaz ready ✓")

    # Start keep-alive ping for Render free tier
    keep_alive_task = None
    render_url = os.getenv("RENDER_EXTERNAL_URL") or "https://goerdiedaz-ai-voice-agent-and-assistant.onrender.com"

    async def keep_alive():
        async with httpx.AsyncClient() as client:
            while True:
                await asyncio.sleep(600)  # 10 minutes
                try:
                    logger.info(f"Keep-alive ping to {render_url}/health")
                    resp = await client.get(f"{render_url}/health", timeout=10.0)
                    logger.debug(f"Keep-alive response: {resp.status_code}")
                except Exception as e:
                    logger.warning(f"Keep-alive ping failed: {e}")

    keep_alive_task = asyncio.create_task(keep_alive())

    yield

    if keep_alive_task:
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("GeordieDaz shutting down...")
    await close_redis()


app = FastAPI(
    title="GeordieDaz API",
    description="Cross-Platform Persistent AI Avatar Assistant",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend origin
origins = settings.allowed_origins_list
if origins == ["*"]:
    # Wildcard with credentials requires reflecting the origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── REST Routers ──────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(persona.router)
app.include_router(session.router)
app.include_router(memory.router)
app.include_router(usage.router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for Docker/load-balancer probes."""
    return {"status": "ok", "service": "GeordieDaz API", "version": "1.0.0"}


# ── WebSocket Endpoint ────────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
):
    """
    Real-time voice WebSocket endpoint.
    Auth via ?token=JWT query parameter (WS cannot send HTTP headers).
    """
    async with AsyncSessionLocal() as db:
        # Authenticate WebSocket connection
        user = await get_ws_user(websocket, db)
        if not user:
            return  # get_ws_user already closed the WS

        # Verify user_id matches token subject (prevent spoofing)
        if str(user.id) != user_id:
            await websocket.close(code=4003, reason="User ID mismatch")
            return

        await handle_websocket(websocket, user_id=str(user.id), db=db)
