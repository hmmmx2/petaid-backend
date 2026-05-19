"""Pydantic request/response models for the auth router."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    role: str = Field(
        default="pet_owner",
        pattern=r"^(pet_owner|veterinary_expert)$",
        description="Account type to create.",
    )
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_token: str | None = Field(default=None, min_length=4, max_length=12)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str
