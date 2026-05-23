"""Pet endpoints — managed by the owning Pet Owner."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentPetOwnerDep, DbDep, require
from app.domain.exceptions import NotFoundException
from app.domain.permissions import Permission
from app.models.pet import Pet
from app.schemas.common import PetIn, PetOut, PetUpdate

router = APIRouter(prefix="/pets", tags=["pets"])
_pet_manage = [Depends(require(Permission.PET_MANAGE))]


@router.get("", response_model=list[PetOut], dependencies=_pet_manage)
async def list_pets(owner: CurrentPetOwnerDep, db: DbDep) -> list[Pet]:
    rows = await db.scalars(
        select(Pet)
        .where(Pet.owner_id == owner.id)
        .options(selectinload(Pet.pet_type))
        .order_by(Pet.created_at)
    )
    return list(rows)


@router.post("", response_model=PetOut, status_code=status.HTTP_201_CREATED, dependencies=_pet_manage)
async def create_pet(
    payload: PetIn, owner: CurrentPetOwnerDep, db: DbDep
) -> Pet:
    pet = Pet(owner_id=owner.id, **payload.model_dump())
    db.add(pet)
    await db.commit()
    await db.refresh(pet, attribute_names=["pet_type"])
    return pet


@router.patch("/{pet_id}", response_model=PetOut, dependencies=_pet_manage)
async def update_pet(
    pet_id: uuid.UUID, payload: PetUpdate, owner: CurrentPetOwnerDep, db: DbDep
) -> Pet:
    """Update an owned pet's profile (partial — only supplied fields change)."""
    pet = await db.get(Pet, pet_id)
    if pet is None or pet.owner_id != owner.id:
        raise NotFoundException("Pet")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pet, field, value)
    await db.commit()
    await db.refresh(pet, attribute_names=["pet_type"])
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_pet_manage)
async def delete_pet(
    pet_id: uuid.UUID, owner: CurrentPetOwnerDep, db: DbDep
) -> None:
    pet = await db.get(Pet, pet_id)
    if pet is None or pet.owner_id != owner.id:
        raise NotFoundException("Pet")
    await db.delete(pet)
    await db.commit()
