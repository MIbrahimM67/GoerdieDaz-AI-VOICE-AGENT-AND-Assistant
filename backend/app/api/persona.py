"""
GeordieDaz — Persona API Routes
GET /personas — list all personas
POST /persona/switch — REST fallback for persona switch
"""
from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.persona import PersonaListItem, PersonaSwitchRequest, PersonaSwitchResponse
from app.services.persona_service import persona_manager
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/personas", tags=["personas"])


@router.get("", response_model=list[PersonaListItem])
async def list_personas(current_user: User = Depends(get_current_user)):
    """Return all available personas for the UI persona switcher."""
    return persona_manager.list_personas()


@router.post("/switch", response_model=PersonaSwitchResponse)
async def switch_persona(
    body: PersonaSwitchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    REST fallback for persona switch (WebSocket is the primary path).
    Updates persona in Redis and user record in DB.
    Memory is NEVER touched — preserved across all personas.
    """
    try:
        config = await persona_manager.hot_swap(
            user_id=str(current_user.id),
            new_persona_id=body.persona_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Persist persona preference to user record
    current_user.current_persona_id = body.persona_id
    await db.commit()

    return PersonaSwitchResponse(
        success=True,
        persona_id=config.id,
        persona_name=config.name,
        message=f"Switched to {config.name}. Your memories are fully preserved.",
    )
