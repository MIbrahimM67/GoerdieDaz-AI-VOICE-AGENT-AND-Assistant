"""
GeordieDaz — Embedding Service
Wraps OpenAI text-embedding-3-small for semantic memory vectors.
"""
import asyncio
import logging
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@lru_cache()
def _get_openai_client() -> AsyncOpenAI:
    """Cached AsyncOpenAI client."""
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def embed_text(text: str) -> list[float]:
    """
    Generate a 1536-dim embedding for a given text.
    Returns a list of floats.
    Raises on API errors after 3 retries.
    """
    client = _get_openai_client()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text.strip(),
                dimensions=EMBEDDING_DIMENSIONS,
            )
            return response.data[0].embedding
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
