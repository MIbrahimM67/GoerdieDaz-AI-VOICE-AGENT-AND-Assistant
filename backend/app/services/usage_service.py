"""
GeordieDaz — Usage Tracking Service
Logs and calculates costs for every API call.

Pricing (as of Aug 2026):
  - GPT-4o-mini:            $0.15 / 1M input tokens, $0.60 / 1M output tokens
  - text-embedding-3-small: $0.02 / 1M tokens
  - OpenAI Realtime (mini): $0.06 / min audio in, $0.24 / min audio out (approx)
  - Whisper-1:              $0.006 / min
  - ElevenLabs Flash v2.5:  ~$0.15 / 1K characters (varies by plan)
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)

# Cost lookup (USD) — update when pricing changes
PRICING = {
    "gpt-4o-mini": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
    "text-embedding-3-small": {
        "input_per_1m": 0.02,
    },
    "openai_realtime_mini": {
        "audio_in_per_min": 0.06,
        "audio_out_per_min": 0.24,
    },
    "whisper-1": {
        "per_min": 0.006,
    },
    "elevenlabs_flash_v2_5": {
        "per_1k_chars": 0.15,
    },
}


def calculate_cost(
    service: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    characters: int = 0,
    duration_seconds: float = 0.0,
) -> float:
    """Calculate the cost of an API call based on pricing tables."""

    if service == "gpt4o_extraction":
        rates = PRICING["gpt-4o-mini"]
        return (tokens_in / 1_000_000 * rates["input_per_1m"]) + \
               (tokens_out / 1_000_000 * rates["output_per_1m"])

    elif service == "embedding":
        rates = PRICING["text-embedding-3-small"]
        return tokens_in / 1_000_000 * rates["input_per_1m"]

    elif service == "openai_realtime":
        rates = PRICING["openai_realtime_mini"]
        minutes = duration_seconds / 60.0
        # Approximate: half in, half out
        return minutes * (rates["audio_in_per_min"] + rates["audio_out_per_min"]) / 2

    elif service == "whisper":
        rates = PRICING["whisper-1"]
        return (duration_seconds / 60.0) * rates["per_min"]

    elif service == "elevenlabs_tts":
        rates = PRICING["elevenlabs_flash_v2_5"]
        return (characters / 1000.0) * rates["per_1k_chars"]

    return 0.0


async def log_usage(
    db: AsyncSession,
    user_id: str,
    service: str,
    operation: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    characters: int = 0,
    duration_seconds: float = 0.0,
    metadata: Optional[dict] = None,
):
    """Log a single API call with calculated cost."""
    cost = calculate_cost(
        service=service,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        characters=characters,
        duration_seconds=duration_seconds,
    )

    log_entry = UsageLog(
        id=uuid.uuid4(),
        user_id=user_id,
        service=service,
        operation=operation,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        characters=characters,
        duration_seconds=duration_seconds,
        cost_usd=cost,
        metadata_json=json.dumps(metadata) if metadata else None,
    )

    try:
        db.add(log_entry)
        await db.commit()
        logger.debug(
            f"Usage logged: {service}/{operation} cost=${cost:.6f} "
            f"tokens={tokens_in}+{tokens_out} chars={characters} dur={duration_seconds:.1f}s"
        )
    except Exception as e:
        logger.warning(f"Usage logging failed (non-fatal): {e}")
        await db.rollback()

    created_iso = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(log_entry.id),
        "user_id": str(user_id),
        "service": service,
        "operation": operation,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "characters": characters,
        "duration_seconds": duration_seconds,
        "cost_usd": cost,
        "metadata": metadata or {},
        "created_at": created_iso,
    }


async def get_usage_summary(
    db: AsyncSession,
    user_id: Optional[str] = None,
    days: int = 30,
) -> dict:
    """Get aggregated usage summary by service."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    where_clauses = "WHERE created_at >= :cutoff"
    params = {"cutoff": cutoff}

    if user_id:
        where_clauses += " AND user_id = CAST(:user_id AS uuid)"
        params["user_id"] = user_id

    result = await db.execute(
        text(f"""
            SELECT
                service,
                COUNT(*) as call_count,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                SUM(characters) as total_characters,
                SUM(duration_seconds) as total_duration,
                SUM(cost_usd) as total_cost
            FROM usage_logs
            {where_clauses}
            GROUP BY service
            ORDER BY total_cost DESC
        """),
        params
    )
    rows = result.fetchall()

    services = {}
    total_cost = 0.0
    total_calls = 0
    total_tokens_in = 0
    total_tokens_out = 0
    total_characters = 0
    total_duration = 0.0

    for row in rows:
        c_in = row.total_tokens_in or 0
        c_out = row.total_tokens_out or 0
        chars = row.total_characters or 0
        dur = float(row.total_duration or 0)
        c_cost = float(row.total_cost or 0)

        services[row.service] = {
            "call_count": row.call_count,
            "tokens_in": c_in,
            "tokens_out": c_out,
            "characters": chars,
            "duration_seconds": dur,
            "cost_usd": c_cost,
        }
        total_cost += c_cost
        total_calls += row.call_count
        total_tokens_in += c_in
        total_tokens_out += c_out
        total_characters += chars
        total_duration += dur

    return {
        "period_days": days,
        "total_cost_usd": round(total_cost, 6),
        "total_calls": total_calls,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_characters": total_characters,
        "total_duration_seconds": round(total_duration, 2),
        "by_service": services,
    }


async def get_daily_costs(
    db: AsyncSession,
    user_id: Optional[str] = None,
    days: int = 30,
) -> list[dict]:
    """Get daily cost breakdown for charting."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    where_clauses = "WHERE created_at >= :cutoff"
    params = {"cutoff": cutoff}

    if user_id:
        where_clauses += " AND user_id = CAST(:user_id AS uuid)"
        params["user_id"] = user_id

    result = await db.execute(
        text(f"""
            SELECT
                DATE(created_at) as day,
                service,
                SUM(cost_usd) as cost,
                COUNT(*) as calls
            FROM usage_logs
            {where_clauses}
            GROUP BY DATE(created_at), service
            ORDER BY day DESC
        """),
        params
    )
    rows = result.fetchall()

    daily = {}
    for row in rows:
        day_str = str(row.day)
        if day_str not in daily:
            daily[day_str] = {"date": day_str, "total": 0.0, "calls": 0, "breakdown": {}}
        daily[day_str]["breakdown"][row.service] = round(float(row.cost or 0), 6)
        daily[day_str]["total"] += float(row.cost or 0)
        daily[day_str]["calls"] += int(row.calls or 0)

    return list(daily.values())


async def get_usage_detail(
    db: AsyncSession,
    user_id: Optional[str] = None,
    days: int = 7,
    limit: int = 150,
) -> list[dict]:
    """Get detailed individual call log including full trace metadata."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    where_clauses = "WHERE created_at >= :cutoff"
    params = {"cutoff": cutoff, "limit": limit}

    if user_id:
        where_clauses += " AND user_id = CAST(:user_id AS uuid)"
        params["user_id"] = user_id

    result = await db.execute(
        text(f"""
            SELECT id, service, operation, tokens_in, tokens_out,
                   characters, duration_seconds, cost_usd, metadata_json, created_at
            FROM usage_logs
            {where_clauses}
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        params
    )
    rows = result.fetchall()

    output = []
    for row in rows:
        meta = {}
        if row.metadata_json:
            try:
                meta = json.loads(row.metadata_json)
            except Exception:
                meta = {"raw": row.metadata_json}

        output.append({
            "id": str(row.id),
            "service": row.service,
            "operation": row.operation,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "characters": row.characters,
            "duration_seconds": float(row.duration_seconds),
            "cost_usd": float(row.cost_usd),
            "metadata": meta,
            "created_at": row.created_at.isoformat() if hasattr(row.created_at, 'isoformat') else str(row.created_at),
        })

    return output
