"""AuthManager — authentication service (SRS 3.3.5).

Applies the **Factory Method** pattern (SRS 5.1.1) when creating accounts:
the caller asks for an account of a given role and ``AuthManager`` returns
the correct :class:`Account` subclass with composed
:class:`UserCredentials`.

Also enforces the lockout boundary case (SRS 1.3.3): five consecutive
failed login attempts trigger a 30-second lockout window during which no
further attempts are accepted.

This class is the **only** place in the codebase that should read or
mutate :class:`UserCredentials` (heuristic 4.1.2, data hiding).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import EventBus
from app.domain.exceptions import (
    AccountLockedException,
    InvalidCredentialsException,
    InvalidInputException,
    MfaRequiredException,
)
from app.models.account import Account, PetOwner, VeterinaryExpert
from app.models.credentials import UserCredentials

# Tuning constants per SRS 1.3.3 (mirrors the reference core/20-auth-manager.js)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 64
MAX_NAME_LENGTH = 80
DEMO_MFA_SECRET = "123456"

# Single password context shared by all credential operations.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _initials(full_name: str) -> str:
    parts = [p for p in full_name.split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class AuthManager:
    """Singleton-by-convention (owned by :class:`AppController`).

    All authentication state mutations go through here. The class purposely
    has a tiny public surface (heuristic 4.1.5):

        register, authenticate, verify_email, enable_mfa,
        consume_mfa_token, reset_failed_attempts
    """

    # email (lower) -> 6-digit verification code. In-memory for the prototype
    # (the reference stores it the same way — SRS A3 allows this simplification).
    _pending_verifications: dict[str, str] = {}

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    # ------------------------------------------------------------------ #
    # Factory Method                                                     #
    # ------------------------------------------------------------------ #
    async def register(
        self,
        db: AsyncSession,
        *,
        role: str,
        full_name: str,
        email: str,
        password: str,
    ) -> tuple[Account, str]:
        """Create a new (unverified) account and return ``(account, code)``.

        ``role`` must be one of ``"pet_owner"`` or ``"veterinary_expert"``.
        Vet accounts have MFA enabled at creation time (SRS A1). A 6-digit
        email-verification code is generated and returned so the SRS §7.8
        flow can complete; the account stays inactive for login until the
        code is confirmed.
        """
        self._validate_input(full_name=full_name, email=email, password=password)
        email = email.strip().lower()

        existing = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email)
        )
        if existing is not None:
            raise InvalidInputException("email", "An account with this email already exists.")

        account = self._make_account(role=role, full_name=full_name)
        account.email_verified = False
        db.add(account)
        await db.flush()  # need account.id for FK

        creds = UserCredentials(
            account_id=account.id,
            email=email,
            hashed_password=_pwd_context.hash(password),
            mfa_enabled=isinstance(account, VeterinaryExpert),
            mfa_secret=DEMO_MFA_SECRET if isinstance(account, VeterinaryExpert) else None,
        )
        db.add(creds)
        await db.commit()
        await db.refresh(account)

        code = f"{secrets.randbelow(900000) + 100000}"
        self._pending_verifications[email] = code
        return account, code

    async def confirm_email_verification(
        self, db: AsyncSession, *, email: str, code: str
    ) -> Account:
        """Mark an account's email verified once the right code is supplied."""
        email = email.strip().lower()
        expected = self._pending_verifications.get(email)
        if not expected or expected != code.strip():
            raise InvalidInputException("code", "Verification code is incorrect.")
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email)
        )
        if creds is None:
            raise InvalidInputException("email", "Account not found.")
        account = await db.get(Account, creds.account_id)
        if account is None:
            raise InvalidInputException("email", "Account not found.")
        account.email_verified = True
        await db.commit()
        await db.refresh(account)
        self._pending_verifications.pop(email, None)
        return account

    @staticmethod
    def _make_account(*, role: str, full_name: str) -> Account:
        """Concrete factory method for the Account hierarchy."""
        if role == "pet_owner":
            return PetOwner(full_name=full_name, initials=_initials(full_name))
        if role == "veterinary_expert":
            return VeterinaryExpert(full_name=full_name, initials=_initials(full_name))
        raise InvalidInputException("role", "Role must be pet_owner or veterinary_expert.")

    # ------------------------------------------------------------------ #
    # Login flow                                                         #
    # ------------------------------------------------------------------ #
    async def authenticate(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        mfa_token: str | None = None,
    ) -> Account:
        """Validate credentials and return the matching :class:`Account`.

        Raises one of :class:`InvalidCredentialsException`,
        :class:`AccountLockedException`, or :class:`MfaRequiredException`.
        """
        if not email or not password:
            raise InvalidCredentialsException()

        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email.strip().lower())
        )
        if creds is None:
            # Generic message — never disclose whether the email exists.
            raise InvalidCredentialsException()

        self._enforce_lockout(creds)

        if not _pwd_context.verify(password, creds.hashed_password):
            await self._record_failed_attempt(db, creds)
            raise InvalidCredentialsException()

        account = await db.get(Account, creds.account_id)
        if account is None or not account.is_active:
            raise InvalidCredentialsException()

        if not account.email_verified:
            raise InvalidCredentialsException(
                "Please verify your email before signing in."
            )

        if creds.mfa_enabled and not self._mfa_ok(creds, mfa_token):
            raise MfaRequiredException()

        # Successful login — clear failure counter.
        if creds.failed_attempts:
            creds.failed_attempts = 0
            creds.locked_until = None
            await db.commit()

        return account

    @staticmethod
    def _mfa_ok(creds: UserCredentials, mfa_token: str | None) -> bool:
        """Verify the supplied MFA token.

        Assignment 3 scope does not require a real TOTP. We accept a static
        per-account ``mfa_secret`` value so the scenario is testable.
        """
        if not creds.mfa_enabled:
            return True
        if not mfa_token:
            return False
        return mfa_token == (creds.mfa_secret or "123456")

    @staticmethod
    def _enforce_lockout(creds: UserCredentials) -> None:
        if creds.locked_until is None:
            return
        now = datetime.now(timezone.utc)
        if creds.locked_until > now:
            remaining = int((creds.locked_until - now).total_seconds())
            raise AccountLockedException(retry_after_seconds=max(remaining, 1))
        # Lock has expired — reset for a fresh window.
        creds.failed_attempts = 0
        creds.locked_until = None

    async def _record_failed_attempt(
        self, db: AsyncSession, creds: UserCredentials
    ) -> None:
        creds.failed_attempts += 1
        if creds.failed_attempts >= MAX_FAILED_ATTEMPTS:
            creds.locked_until = datetime.now(timezone.utc) + timedelta(
                seconds=LOCKOUT_SECONDS
            )
        await db.commit()

    # ------------------------------------------------------------------ #
    # Input validation                                                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_input(*, full_name: str, email: str, password: str) -> None:
        if not full_name or not full_name.strip():
            raise InvalidInputException("full_name", "Full name is required.")
        if len(full_name) > MAX_NAME_LENGTH:
            raise InvalidInputException(
                "full_name", f"Full name must be at most {MAX_NAME_LENGTH} characters."
            )
        if "@" not in email or "." not in email.split("@")[-1]:
            raise InvalidInputException("email", "Email format is invalid.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidInputException(
                "password",
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            )
        if len(password) > MAX_PASSWORD_LENGTH:
            raise InvalidInputException(
                "password",
                f"Password must be at most {MAX_PASSWORD_LENGTH} characters.",
            )
