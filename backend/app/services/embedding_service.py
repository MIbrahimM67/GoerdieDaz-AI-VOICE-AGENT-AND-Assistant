"""
GeordieDaz — Embedding Service
Wraps OpenAI text-embedding-3-small for semantic memory vectors.
Includes an in-memory LRU cache to avoid redundant API calls.
"""
import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# ── Embedding Cache ────────────────────────────────────────────────────────
# Same text ALWAYS produces the same vector. No reason to call OpenAI twice.
# Cache holds up to 256 entries, each valid for 1 hour.
_CACHE_MAX_SIZE = 256
_CACHE_TTL_SECONDS = 3600  # 1 hour

_embedding_cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()


def _cache_key(text: str) -> str:
    """Stable hash for cache lookup."""
    return hashlib.sha256(text.strip().encode()).hexdigest()


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
    """Cached AsyncOpenAI client."""
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_text(text: str) -> list[float]:
    """
    Generate a 1536-dim embedding for a given text.
    Returns a list of floats. Uses in-memory cache to avoid duplicate API calls.
    Raises on API errors after 3 retries.
    """
    # Check cache first
    cached = _cache_get(text)
    if cached is not None:
        logger.debug(f"Embedding cache HIT for: {text[:50]}...")
        return cached

    client = _get_openai_client()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text.strip(),
                dimensions=EMBEDDING_DIMENSIONS,
            )
            embedding = response.data[0].embedding
            _cache_set(text, embedding)  # Cache the result
            return embedding
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Embedding failed after {max_retries} attempts: {e}")
                raise
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            logger.warning(f"Embedding attempt {attempt + 1} failed, retrying in {wait}s: {e}")
            await asyncio.sleep(wait)
    # unreachable but satisfies type checker
    raise RuntimeError("Embedding failed")


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple texts in a single API call (more efficient than looping).
    OpenAI supports up to 2048 items per batch call.
    """
    if not texts:
        return []

    client = _get_openai_client()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[t.strip() for t in texts],
        dimensions=EMBEDDING_DIMENSIONS,
    )
    # Results are ordered to match input
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
