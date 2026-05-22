"""Auth endpoints — login, register, refresh, MFA.

All logic is delegated to :class:`AuthManager` so this router is a thin
HTTP adapter. SRS scenario 7.8 (account registration with email
verification) is implemented as the register → /auth/verify-email flow;
the email send step is stubbed for Assignment 3 scope.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep
from app.core.config import get_settings
from app.core.security import create_token, decode_token
from app.domain.app_controller import get_app_controller
from app.models.account import Account
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(account: Account) -> TokenPair:
    sub = str(account.id)
    return TokenPair(
        access_token=create_token(sub, "access"),
        refresh_token=create_token(sub, "refresh"),
        role=account.role,
    )


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: RegisterRequest, db: DbDep) -> RegisterResponse:
    """Create a new account via :class:`AuthManager` (Factory Method).

    Returns a verification code rather than tokens — the account must
    confirm its email (SRS §7.8) before it can log in.
    """
    controller = get_app_controller()
    _account, code = await controller.auth_manager.register(
        db,
        role=payload.role,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
    )
    # SECURITY: never return the verification code in production — it would
    # let a client verify an email they don't control. In production the code
    # is delivered out-of-band (email). Dev surfaces it because there's no
    # mail server locally.
    exposed_code = None if get_settings().is_production else code
    return RegisterResponse(email=payload.email.lower(), verification_code=exposed_code)


@router.post("/verify-email", response_model=TokenPair)
async def verify_email(payload: VerifyEmailRequest, db: DbDep) -> TokenPair:
    """Confirm the email code and log the user in (returns tokens)."""
    controller = get_app_controller()
    account = await controller.auth_manager.confirm_email_verification(
        db, email=payload.email, code=payload.code
    )
    return _issue_tokens(account)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: DbDep) -> TokenPair:
    """Authenticate the actor and return an access/refresh token pair."""
    controller = get_app_controller()
    account = await controller.auth_manager.authenticate(
        db,
        email=payload.email,
        password=payload.password,
        mfa_token=payload.mfa_token,
    )
    return _issue_tokens(account)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: DbDep) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    sub = claims.get("sub")
    try:
        account_id = uuid.UUID(sub) if sub else None
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    account = await db.get(Account, account_id) if account_id else None
    if account is None or not account.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return _issue_tokens(account)
