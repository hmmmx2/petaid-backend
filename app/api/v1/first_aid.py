"""FirstAidGuidance endpoints — emergency protocols (SRS 7.1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAccountDep, CurrentVetDep, DbDep
from app.domain.exceptions import NotFoundException
from app.models.first_aid import FirstAidGuidance
from app.schemas.common import FirstAidIn, FirstAidOut

router = APIRouter(prefix="/first-aid", tags=["first-aid"])


@router.get("", response_model=list[FirstAidOut])
async def list_guidance(
    _account: CurrentAccountDep,
    db: DbDep,
    pet_type_id: uuid.UUID | None = None,
    emergency_type: str | None = None,
) -> list[FirstAidGuidance]:
    stmt = select(FirstAidGuidance).options(
        selectinload(FirstAidGuidance.pet_type),
        selectinload(FirstAidGuidance.resources),
    )
    if pet_type_id is not None:
        stmt = stmt.where(FirstAidGuidance.pet_type_id == pet_type_id)
    if emergency_type:
        stmt = stmt.where(FirstAidGuidance.emergency_type == emergency_type)
    rows = await db.scalars(stmt.order_by(FirstAidGuidance.emergency_type))
    return list(rows)


@router.get("/{guidance_id}", response_model=FirstAidOut)
async def get_guidance(
    guidance_id: uuid.UUID, _account: CurrentAccountDep, db: DbDep
) -> FirstAidGuidance:
    g = await db.get(FirstAidGuidance, guidance_id)
    if g is None:
        raise NotFoundException("Guidance")
    return g


@router.post("", response_model=FirstAidOut, status_code=status.HTTP_201_CREATED)
async def create_guidance(
    payload: FirstAidIn, vet: CurrentVetDep, db: DbDep
) -> FirstAidGuidance:
    guidance = FirstAidGuidance(
        title=payload.title,
        emergency_type=payload.emergency_type,
        pet_type_id=payload.pet_type_id,
        author_id=vet.id,
        summary=payload.summary,
        steps=list(payload.steps),
    )
    db.add(guidance)
    await db.commit()
    await db.refresh(guidance, attribute_names=["pet_type", "resources"])
    return guidance
