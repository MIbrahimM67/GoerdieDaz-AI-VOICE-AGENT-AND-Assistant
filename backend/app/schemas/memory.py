"""Pydantic schemas for memory operations."""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    entity_key: Optional[str]
    content: str
    memory_type: Literal["semantic", "episodic"]
    importance_score: float
    confidence_score: float
    source_persona_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    # similarity score added during retrieval
    similarity_score: Optional[float] = None
    composite_score: Optional[float] = None

    model_config = {"from_attributes": True}


class MemoryWriteRequest(BaseModel):
    """Used by internal agent nodes — not exposed as public API."""
    user_id: str
    turn_text: str  # The conversation turn to extract facts from
    persona_id: str


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class MemoryDeleteResponse(BaseModel):
    success: bool
    memory_id: uuid.UUID
