"""
GeordieDaz — LLM Client Factory
Returns an AsyncOpenAI client pointed at either OpenAI or Groq
based on the LLM_PROVIDER env var.

To switch providers: change LLM_PROVIDER in .env and restart.
No code changes needed anywhere else.

Usage:
    from app.services.llm_client import get_llm_client, get_chat_model
    client = get_llm_client()
    model  = get_chat_model()
    resp   = await client.chat.completions.create(model=model, ...)
"""
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_llm_client() -> AsyncOpenAI:
    """
    Return an async OpenAI-compatible LLM client.
    - opensource mode → Groq (llama-3.3-70b-versatile, free)
    - openai mode     → OpenAI (gpt-4o-mini)
    """
    if settings.use_opensource:
        logger.debug("LLM client: Groq (opensource mode)")
        return AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )
    logger.debug("LLM client: OpenAI (production mode)")
    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_chat_model() -> str:
    """Return the chat model name for the active provider."""
    if settings.use_opensource:
        return settings.groq_model          # llama-3.3-70b-versatile
    return "gpt-4o-mini"


def log_provider():
    """Log which provider is active — call on startup."""
    if settings.use_opensource:
        logger.info(
            "LLM Provider: OPENSOURCE (Groq + Deepgram + Jina) — "
            "set LLM_PROVIDER=openai to revert"
        )
    else:
        logger.info("LLM Provider: OpenAI (production mode)")
