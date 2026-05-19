"""FastAPI dependencies shared across all v1 routers.

Authentication uses the access JWT issued at login. The decoded ``sub`` is
mapped back to an :class:`Account`; SQLAlchemy single-table inheritance
will return the correct subclass (PetOwner or VeterinaryExpert).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.domain.exceptions import NotAuthorisedException
from app.models.account import Account, PetOwner, VeterinaryExpert

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str | None, Depends(oauth2_scheme)]


async def get_current_account(token: TokenDep, db: DbDep) -> Account:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        account_id = uuid.UUID(sub)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    account = await db.get(Account, account_id)
    if account is None or not account.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return account


CurrentAccountDep = Annotated[Account, Depends(get_current_account)]


async def get_current_pet_owner(account: CurrentAccountDep) -> PetOwner:
    if not isinstance(account, PetOwner):
        raise NotAuthorisedException("This action is only available to Pet Owners.")
    return account


async def get_current_vet(account: CurrentAccountDep) -> VeterinaryExpert:
    if not isinstance(account, VeterinaryExpert):
        raise NotAuthorisedException("This action is only available to Veterinary Experts.")
    return account


CurrentPetOwnerDep = Annotated[PetOwner, Depends(get_current_pet_owner)]
CurrentVetDep = Annotated[VeterinaryExpert, Depends(get_current_vet)]
