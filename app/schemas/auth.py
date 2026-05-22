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

    ``verification_code`` is returned directly because A3 has no real mail
    server (the reference shows it in a banner). Remove this field once a
    real mail provider is wired in.
    """

    email: str
    verification_code: str
    message: str = "Account created. Enter the verification code to finish."


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


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
