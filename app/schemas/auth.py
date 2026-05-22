"""Pydantic request/response models for the auth router."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    role: str = Field(
        default="pet_owner",
        pattern=r"^(pet_owner|veterinary_expert)$",
        description="Account type to create.",
    )
    full_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=64)


class RegisterResponse(BaseModel):
    """Registration does not log the user in — it triggers email verification.

    ``verification_code`` is **only** populated outside production (there is
    no mail server in dev, so the code is surfaced for local testing). In
    production it is ``None`` and the real code is delivered by email — it
    must never reach the client, to avoid leaking a credential that would
    let anyone verify an address they don't control.
    """

    email: str
    verification_code: str | None = None
    message: str = "Account created. Check your email for a verification code."


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


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
