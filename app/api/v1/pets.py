import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep
from app.models.pet import Pet
from app.schemas.dashboard import PetOut

router = APIRouter(prefix="/pets", tags=["pets"])


class PetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    species: str = Field(min_length=1, max_length=40)
    breed: str | None = None
    age_years: int | None = Field(default=None, ge=0, le=80)
    icon_emoji: str = "🐾"
    icon_bg: str = "#F5F5F4"


@router.get("", response_model=list[PetOut])
async def list_pets(user: CurrentUserDep, db: DbDep) -> list[Pet]:
    rows = await db.scalars(select(Pet).where(Pet.owner_id == user.id).order_by(Pet.created_at))
    return list(rows)


@router.post("", response_model=PetOut, status_code=status.HTTP_201_CREATED)
async def create_pet(payload: PetCreate, user: CurrentUserDep, db: DbDep) -> Pet:
    pet = Pet(owner_id=user.id, **payload.model_dump())
    db.add(pet)
    await db.commit()
    await db.refresh(pet)
    return pet


@router.delete("/{pet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pet(pet_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> None:
    pet = await db.get(Pet, pet_id)
    if pet is None or pet.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pet not found")
    await db.delete(pet)
    await db.commit()
