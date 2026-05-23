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

import re
import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import totp
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
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 64
MAX_NAME_LENGTH = 80
RESEND_COOLDOWN_SECONDS = 30  # min gap between verification-code re-sends
VERIFICATION_TTL_SECONDS = 900  # email verification codes expire after 15 minutes
RESET_TTL_SECONDS = 900  # password-reset codes expire after 15 minutes

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

    # email (lower) -> (6-digit code, expiry). In-memory for the prototype
    # (the reference stores it the same way — SRS A3 allows this simplification).
    # Single-instance only; a horizontally-scaled deployment would move these to
    # a shared store (Redis), behind the same AuthManager interface.
    _pending_verifications: dict[str, tuple[str, datetime]] = {}
    # email (lower) -> last time a verification code was issued (rate-limiting).
    _last_verification_sent: dict[str, datetime] = {}
    # email (lower) -> (6-digit reset code, expiry) for password recovery.
    _pending_resets: dict[str, tuple[str, datetime]] = {}

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
        """Create a new (unverified) Pet Owner account and return
        ``(account, code)``.

        Only ``"pet_owner"`` may self-register. Veterinary Expert accounts are
        provisioned by the Veterinary Association (SRS §3.1.3.3) and seeded —
        allowing self-registration would also let a caller obtain a vet token
        through the email-verification path without ever completing MFA.

        A 6-digit email-verification code is generated; the account cannot log
        in until the code is confirmed (SRS §7.8).
        """
        if role != "pet_owner":
            raise InvalidInputException(
                "role",
                "Veterinary Expert accounts are provisioned by the Veterinary "
                "Association and cannot be self-registered.",
            )
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

        is_vet = isinstance(account, VeterinaryExpert)
        creds = UserCredentials(
            account_id=account.id,
            email=email,
            hashed_password=_pwd_context.hash(password),
            mfa_enabled=is_vet,
            # Real per-account TOTP secret (RFC 6238) for vets — no shared/static
            # code. Enrol by scanning the provisioning URI in an authenticator app.
            mfa_secret=totp.generate_secret() if is_vet else None,
        )
        db.add(creds)
        await db.commit()
        await db.refresh(account)

        now = datetime.now(timezone.utc)
        code = f"{secrets.randbelow(900000) + 100000}"
        self._pending_verifications[email] = (code, now + timedelta(seconds=VERIFICATION_TTL_SECONDS))
        self._last_verification_sent[email] = now
        return account, code

    async def resend_verification(
        self, db: AsyncSession, *, email: str
    ) -> str | None:
        """Re-issue a verification code for an unverified account.

        Returns the new 6-digit code, or ``None`` when there is nothing to
        resend (no such account, or it's already verified). Returning ``None``
        rather than raising lets the endpoint respond identically in every case
        and avoids leaking which emails are registered (account enumeration).

        Rate-limited per email via :data:`RESEND_COOLDOWN_SECONDS`.
        """
        email = email.strip().lower()
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email)
        )
        if creds is None:
            return None
        account = await db.get(Account, creds.account_id)
        if account is None or account.email_verified:
            return None

        now = datetime.now(timezone.utc)
        last = self._last_verification_sent.get(email)
        if last is not None and (now - last).total_seconds() < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - (now - last).total_seconds())
            raise InvalidInputException(
                "email", f"Please wait {max(remaining, 1)}s before requesting another code."
            )

        code = f"{secrets.randbelow(900000) + 100000}"
        self._pending_verifications[email] = (code, now + timedelta(seconds=VERIFICATION_TTL_SECONDS))
        self._last_verification_sent[email] = now
        return code

    async def confirm_email_verification(
        self, db: AsyncSession, *, email: str, code: str
    ) -> Account:
        """Mark an account's email verified once the right code is supplied."""
        email = email.strip().lower()
        entry = self._pending_verifications.get(email)
        if not entry:
            raise InvalidInputException("code", "Verification code is invalid or has expired.")
        expected, expires_at = entry
        if datetime.now(timezone.utc) > expires_at:
            self._pending_verifications.pop(email, None)
            raise InvalidInputException("code", "Verification code has expired. Request a new one.")
        if expected != code.strip():
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

        if creds.mfa_enabled:
            if not mfa_token:
                # First factor passed; prompt for the TOTP code. Not an attempt
                # against the code itself, so the lockout counter is untouched.
                raise MfaRequiredException()
            if not totp.verify(creds.mfa_secret or "", mfa_token):
                # A wrong code IS a guess at the second factor — count it toward
                # the lockout so the 6-digit space can't be brute-forced.
                await self._record_failed_attempt(db, creds)
                raise MfaRequiredException()

        # Successful login — clear any failure counter / expired-lock marker
        # so the cleared state is persisted (not just held in memory).
        if creds.failed_attempts or creds.locked_until is not None:
            creds.failed_attempts = 0
            creds.locked_until = None
            await db.commit()

        return account

    async def get_mfa_provisioning_uri(
        self, db: AsyncSession, account: Account
    ) -> str | None:
        """Return the ``otpauth://`` enrolment URI for the account's TOTP secret.

        Used by an already-authenticated vet to (re-)enrol a device. Returns
        ``None`` if MFA isn't enabled. Reading credentials stays inside
        AuthManager (data-hiding heuristic 4.1.2).
        """
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.account_id == account.id)
        )
        if creds is None or not creds.mfa_enabled or not creds.mfa_secret:
            return None
        return totp.provisioning_uri(creds.mfa_secret, account_name=creds.email)

    async def verify_mfa(
        self, db: AsyncSession, *, account: Account, code: str
    ) -> bool:
        """Check a TOTP ``code`` against the account's enrolled secret.

        Used by the Settings "verify your authenticator works" step. Reading
        credentials stays inside AuthManager (data-hiding heuristic 4.1.2).
        """
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.account_id == account.id)
        )
        if creds is None or not creds.mfa_enabled or not creds.mfa_secret:
            return False
        return totp.verify(creds.mfa_secret, code)

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
    # Password recovery / change                                         #
    # ------------------------------------------------------------------ #
    async def request_password_reset(
        self, db: AsyncSession, *, email: str
    ) -> str | None:
        """Issue a password-reset code for a verified account.

        Returns the 6-digit code, or ``None`` when there is nothing to reset
        (unknown email, or an account that never verified). Returning ``None``
        rather than raising lets the endpoint respond identically every time —
        no account enumeration.
        """
        email = email.strip().lower()
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email)
        )
        if creds is None:
            return None
        account = await db.get(Account, creds.account_id)
        if account is None or not account.email_verified:
            return None
        code = f"{secrets.randbelow(900000) + 100000}"
        self._pending_resets[email] = (
            code,
            datetime.now(timezone.utc) + timedelta(seconds=RESET_TTL_SECONDS),
        )
        return code

    async def reset_password(
        self, db: AsyncSession, *, email: str, code: str, new_password: str
    ) -> None:
        """Set a new password after validating the reset code and its expiry."""
        email = email.strip().lower()
        entry = self._pending_resets.get(email)
        if not entry:
            raise InvalidInputException("code", "This reset code is invalid or has expired.")
        expected, expires_at = entry
        if datetime.now(timezone.utc) > expires_at:
            self._pending_resets.pop(email, None)
            raise InvalidInputException("code", "This reset code has expired. Request a new one.")
        if expected != code.strip():
            raise InvalidInputException("code", "Reset code is incorrect.")
        self.validate_password_strength(new_password)
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == email)
        )
        if creds is None:
            raise InvalidInputException("email", "Account not found.")
        creds.hashed_password = _pwd_context.hash(new_password)
        # A successful reset also clears any lockout so the user can sign in.
        creds.failed_attempts = 0
        creds.locked_until = None
        await db.commit()
        self._pending_resets.pop(email, None)

    async def change_password(
        self,
        db: AsyncSession,
        *,
        account: Account,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change the password of an already-authenticated account."""
        creds = await db.scalar(
            select(UserCredentials).where(UserCredentials.account_id == account.id)
        )
        if creds is None:
            raise InvalidInputException("current_password", "Account not found.")
        if not _pwd_context.verify(current_password, creds.hashed_password):
            raise InvalidInputException("current_password", "Current password is incorrect.")
        self.validate_password_strength(new_password)
        if _pwd_context.verify(new_password, creds.hashed_password):
            raise InvalidInputException(
                "new_password", "New password must be different from your current one."
            )
        creds.hashed_password = _pwd_context.hash(new_password)
        await db.commit()

    # ------------------------------------------------------------------ #
    # Input validation                                                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def validate_password_strength(password: str) -> None:
        """Enforce the password policy (shared by register / reset / change).

        Policy: 8–64 characters, with at least one lowercase letter, one
        uppercase letter and one digit. Raises :class:`InvalidInputException`
        on the offending field so the UI can highlight it.
        """
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidInputException(
                "password", f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )
        if len(password) > MAX_PASSWORD_LENGTH:
            raise InvalidInputException(
                "password", f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
            )
        if not re.search(r"[a-z]", password):
            raise InvalidInputException("password", "Password must include a lowercase letter.")
        if not re.search(r"[A-Z]", password):
            raise InvalidInputException("password", "Password must include an uppercase letter.")
        if not re.search(r"\d", password):
            raise InvalidInputException("password", "Password must include a number.")

    @classmethod
    def _validate_input(cls, *, full_name: str, email: str, password: str) -> None:
        if not full_name or not full_name.strip():
            raise InvalidInputException("full_name", "Full name is required.")
        if len(full_name) > MAX_NAME_LENGTH:
            raise InvalidInputException(
                "full_name", f"Full name must be at most {MAX_NAME_LENGTH} characters."
            )
        if "@" not in email or "." not in email.split("@")[-1]:
            raise InvalidInputException("email", "Email format is invalid.")
        cls.validate_password_strength(password)
