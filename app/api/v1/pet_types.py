"""PetType endpoints.

Pet types are read-only for Pet Owners and managed by Veterinary Experts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentVetDep, DbDep, require
from app.domain.permissions import Permission
from app.models.pet_type import PetType
from app.schemas.common import PetTypeOut

router = APIRouter(prefix="/pet-types", tags=["pet-types"])


class PetTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=240)
    icon_emoji: str = Field(default="🐾", max_length=8)
    icon_bg: str = Field(default="#F5F5F4", max_length=16)


@router.get("", response_model=list[PetTypeOut])
async def list_pet_types(db: DbDep) -> list[PetType]:
    rows = await db.scalars(select(PetType).order_by(PetType.sort_order, PetType.name))
    return list(rows)


@router.post("", response_model=PetTypeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require(Permission.PET_TYPE_MANAGE))])
async def create_pet_type(
    payload: PetTypeIn, _vet: CurrentVetDep, db: DbDep
) -> PetType:
    pt = PetType(**payload.model_dump())
    db.add(pt)
    await db.commit()
    await db.refresh(pt)
    return pt
