"""Auth endpoints — login, register, refresh, MFA.

All logic is delegated to :class:`AuthManager` so this router is a thin
HTTP adapter. SRS scenario 7.8 (account registration with email
verification) is implemented as the register → /auth/verify-email flow;
the email send step is stubbed for Assignment 3 scope.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentAccountDep, CurrentVetDep, DbDep, require
from app.core.config import get_settings
from app.core.rate_limit import rate_limit_ip
from app.core.security import create_token, decode_token
from app.domain.permissions import Permission, permissions_for
from app.domain.app_controller import get_app_controller
from app.models.account import Account
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
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
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_ip("auth_register", max_requests=5, window_seconds=900))],
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


@router.post(
    "/resend-verification",
    response_model=RegisterResponse,
    dependencies=[Depends(rate_limit_ip("auth_resend", max_requests=5, window_seconds=900))],
)
async def resend_verification(
    payload: ResendVerificationRequest, db: DbDep
) -> RegisterResponse:
    """Re-issue an email verification code (rate-limited).

    Always responds 200 with the same shape whether or not the email maps to
    an unverified account — this avoids account enumeration. As with register,
    the code is surfaced only outside production.
    """
    controller = get_app_controller()
    code = await controller.auth_manager.resend_verification(db, email=payload.email)
    exposed_code = None if get_settings().is_production else code
    return RegisterResponse(
        email=payload.email.lower(),
        verification_code=exposed_code,
        message="If the email matches an unverified account, a new code was sent.",
    )


@router.post(
    "/verify-email",
    response_model=TokenPair,
    dependencies=[Depends(rate_limit_ip("auth_verify", max_requests=15, window_seconds=600))],
)
async def verify_email(payload: VerifyEmailRequest, db: DbDep) -> TokenPair:
    """Confirm the email code and log the user in (returns tokens)."""
    controller = get_app_controller()
    account = await controller.auth_manager.confirm_email_verification(
        db, email=payload.email, code=payload.code
    )
    return _issue_tokens(account)


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(rate_limit_ip("auth_login", max_requests=30, window_seconds=300))],
)
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


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_ip("auth_forgot", max_requests=5, window_seconds=900))],
)
async def forgot_password(payload: ForgotPasswordRequest, db: DbDep) -> MessageResponse:
    """Request a password-reset code.

    Always responds 200 with the same shape whether or not the email maps to a
    verified account (no account enumeration). As with register, the code is
    surfaced only outside production (no mail server in dev).
    """
    controller = get_app_controller()
    code = await controller.auth_manager.request_password_reset(db, email=payload.email)
    exposed_code = None if get_settings().is_production else code
    return MessageResponse(
        message="If the email matches a verified account, a reset code was sent.",
        reset_code=exposed_code,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit_ip("auth_reset", max_requests=10, window_seconds=900))],
)
async def reset_password(payload: ResetPasswordRequest, db: DbDep) -> MessageResponse:
    """Set a new password using a valid (unexpired) reset code."""
    controller = get_app_controller()
    await controller.auth_manager.reset_password(
        db, email=payload.email, code=payload.code, new_password=payload.new_password
    )
    return MessageResponse(message="Your password has been reset. You can now sign in.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest, account: CurrentAccountDep, db: DbDep
) -> MessageResponse:
    """Change the password of the signed-in account (requires the current one)."""
    controller = get_app_controller()
    await controller.auth_manager.change_password(
        db,
        account=account,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return MessageResponse(message="Password updated.")


@router.get("/me")
async def me(account: CurrentAccountDep) -> dict:
    """Return the signed-in actor's identity + RBAC capabilities.

    Canonical source of "what may I do" for the client and any middleware.
    """
    return {
        "id": str(account.id),
        "role": account.role,
        "full_name": account.full_name,
        "permissions": [p.value for p in permissions_for(account.role)],
    }


@router.get(
    "/mfa/provisioning",
    dependencies=[Depends(require(Permission.MFA_ENROLL))],
)
async def mfa_provisioning(vet: CurrentVetDep, db: DbDep) -> dict[str, str | None]:
    """Return the current vet's TOTP enrolment URI (for adding to an
    authenticator app). Only the account's own secret is exposed, and only to
    an already-authenticated session."""
    controller = get_app_controller()
    uri = await controller.auth_manager.get_mfa_provisioning_uri(db, vet)
    return {"otpauth_uri": uri}


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
