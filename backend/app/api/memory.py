from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.memory import Memory
from app.services.embedding_service import embed_text
from app.services.memory_service import get_core_memories

from sqlalchemy import select, text

router = APIRouter(prefix="/api/memory", tags=["memory"])


class BrainMemoryItem(BaseModel):
    entity_key: str
    content: str
    importance_score: float
    confidence_score: float
    memory_type: str
    source_persona_id: str | None = None
    updated_at: datetime | None = None


class BrainResponse(BaseModel):
    memories: List[BrainMemoryItem]
    total: int


@router.get("/brain", response_model=BrainResponse)
async def get_brain(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Return all stored memories for the current user (for the Brain sidebar)."""
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(Memory)
        .where(Memory.user_id == str(current_user.id))
        .order_by(Memory.importance_score.desc(), Memory.updated_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    items = [
        BrainMemoryItem(
            entity_key=r.entity_key,
            content=r.content,
            importance_score=float(r.importance_score or 0),
            confidence_score=float(r.confidence_score or 0),
            memory_type=r.memory_type or "personal",
            source_persona_id=r.source_persona_id,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
    return BrainResponse(memories=items, total=len(items))



class CoreFactCreate(BaseModel):
    content: str


class CoreFactResponse(BaseModel):
    content: str
    importance_score: float


@router.get("/core", response_model=List[CoreFactResponse])
async def get_core_facts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch the user's core facts."""
    return await get_core_memories(user_id=str(current_user.id), db=db, limit=20)


@router.post("/core")
async def add_core_fact(
    fact: CoreFactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually add a core fact about the user."""
    content = fact.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        embedding = await embed_text(content)
        
        # Use a generic entity_key for manual facts to avoid conflict resolution overwriting different facts
        # Or generate a unique one
        entity_key = f"manual.fact.{uuid.uuid4().hex[:8]}"
        
        stmt = pg_insert(Memory).values(
            id=uuid.uuid4(),
            user_id=str(current_user.id),
            entity_key=entity_key,
            content=content,
            memory_type="semantic",
            importance_score=1.0,  # Manual facts are highly important
            confidence_score=1.0,
            source_persona_id="system",
            embedding=embedding,
            updated_at=datetime.now(timezone.utc),
        )
        
        # In case of unlikely conflict, do nothing
        stmt = stmt.on_conflict_do_nothing()
        
        await db.execute(stmt)
        await db.commit()
        
        return {"status": "success", "message": "Fact added"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
