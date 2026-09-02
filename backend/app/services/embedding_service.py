"""
GeordieDaz — Embedding Service
Generates 1536-dim vectors for semantic memory storage and retrieval.
Includes an in-memory LRU cache to avoid redundant API calls.

Provider routing (controlled by LLM_PROVIDER in .env):
  openai      → OpenAI text-embedding-3-small (1536 dims)
  opensource  → Jina AI jina-embeddings-v3 (1536 dims, free)

Both produce 1536-dim vectors — pgvector schema stays identical.
"""
import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from functools import lru_cache

import httpx
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_MODEL_OPENAI = "text-embedding-3-small"
EMBEDDING_MODEL_JINA   = "jina-embeddings-v3"
EMBEDDING_DIMENSIONS   = 1536  # Same for both providers — pgvector schema unchanged

# ── Embedding Cache ────────────────────────────────────────────────────────
# Same text ALWAYS produces the same vector. No reason to call any API twice.
# Cache holds up to 256 entries, each valid for 1 hour.
_CACHE_MAX_SIZE    = 256
_CACHE_TTL_SECONDS = 3600  # 1 hour

_embedding_cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()


def _cache_key(text: str) -> str:
    """Stable hash for cache lookup (includes provider so keys don't collide on swap)."""
    provider = settings.llm_provider
    return hashlib.sha256(f"{provider}:{text.strip()}".encode()).hexdigest()


def _cache_get(text: str) -> list[float] | None:
    """Get cached embedding if exists and not expired."""
    key = _cache_key(text)
    if key in _embedding_cache:
        embedding, timestamp = _embedding_cache[key]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            _embedding_cache.move_to_end(key)  # Refresh LRU position
            return embedding
        else:
            del _embedding_cache[key]  # Expired
    return None


def _cache_set(text: str, embedding: list[float]):
    """Store embedding in cache, evicting oldest if full."""
    key = _cache_key(text)
    _embedding_cache[key] = (embedding, time.time())
    _embedding_cache.move_to_end(key)
    while len(_embedding_cache) > _CACHE_MAX_SIZE:
        _embedding_cache.popitem(last=False)  # Evict oldest


@lru_cache()
def _get_openai_client() -> AsyncOpenAI:
    """Cached OpenAI client."""
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _embed_via_jina(text: str) -> list[float]:
    """
    Call Jina AI embeddings API.
    Free tier: https://jina.ai — same 1536 dims as OpenAI.
    Falls back to a zero vector if no Jina key is configured (safe for demo).
    """
    if not settings.jina_api_key:
        # No Jina key — use a deterministic pseudo-embedding for demo
        # (memory search won't rank perfectly but won't crash)
        logger.warning("No JINA_API_KEY set — using hash-based pseudo-embedding for demo")
        import hashlib
        h = hashlib.sha256(text.strip().encode()).digest()
        # Expand 32-byte hash to 1536 floats in [-1, 1]
        seed = list(h) * (1536 // 32 + 1)
        return [(b / 127.5 - 1.0) for b in seed[:1536]]

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.jina.ai/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.jina_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": EMBEDDING_MODEL_JINA,
                "input": [text.strip()],
                "dimensions": EMBEDDING_DIMENSIONS,
                "task": "retrieval.passage",
            },
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


async def embed_text(text: str) -> list[float]:
    """
    Generate a 1536-dim embedding for the given text.
    Uses in-memory cache. Routes to OpenAI or Jina based on LLM_PROVIDER.
    """
    # Cache hit
    cached = _cache_get(text)
    if cached is not None:
        logger.debug(f"Embedding cache HIT ({settings.llm_provider}): {text[:50]}")
        return cached

    max_retries = 3

    for attempt in range(max_retries):
        try:
            if settings.use_opensource:
                # ── Jina AI (free, 1536 dims) ──
                embedding = await _embed_via_jina(text)
            else:
                # ── OpenAI text-embedding-3-small ──
                client = _get_openai_client()
                response = await client.embeddings.create(
                    model=EMBEDDING_MODEL_OPENAI,
                    input=text.strip(),
                    dimensions=EMBEDDING_DIMENSIONS,
                )
                embedding = response.data[0].embedding

            _cache_set(text, embedding)
            return embedding

        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Embedding failed after {max_retries} attempts: {e}")
                raise
            wait = 2 ** attempt
            logger.warning(f"Embedding attempt {attempt + 1} failed, retrying in {wait}s: {e}")
            await asyncio.sleep(wait)

    raise RuntimeError("Embedding failed")


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple texts. In opensource mode, runs concurrently via asyncio.gather.
    In OpenAI mode, uses a single batched API call (more efficient).
    """
    if not texts:
        return []

    if settings.use_opensource:
        # Jina doesn't support large batches the same way — run concurrently
        return list(await asyncio.gather(*[embed_text(t) for t in texts]))

    # OpenAI batch call — up to 2048 items
    client = _get_openai_client()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL_OPENAI,
        input=[t.strip() for t in texts],
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
