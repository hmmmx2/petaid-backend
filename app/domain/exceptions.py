"""Domain exceptions for PetAid.

Each exception carries a stable ``code`` so the FastAPI exception handler in
``app.main`` can map it to the right HTTP status without leaking implementation
detail. The user-facing ``message`` is plain language as required by SRS 1.3.3
(generic "invalid login" wording to avoid revealing whether email or password
was wrong).
"""
from __future__ import annotations


class PetAidError(Exception):
    """Base class for all PetAid domain errors."""

    code: str = "petaid_error"
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputException(PetAidError):
    """Raised when a field fails domain validation (SRS 1.3.4).

    Includes the offending field name so the UI can highlight it.
    """

    code = "invalid_input"
    http_status = 422

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


class InvalidCredentialsException(PetAidError):
    """Raised on a failed login (SRS 1.3.3).

    The message is intentionally generic and does not disclose whether
    the email or the password was incorrect.
    """

    code = "invalid_credentials"
    http_status = 401

    def __init__(self, message: str = "The email or password you entered is incorrect.") -> None:
        super().__init__(message)


class AccountLockedException(PetAidError):
    """Raised when an account is in the 30-second lockout window after five
    consecutive failed login attempts (SRS 1.3.3).
    """

    code = "account_locked"
    http_status = 423  # Locked

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            f"Too many failed attempts. Try again in {retry_after_seconds} seconds."
        )
        self.retry_after_seconds = retry_after_seconds


class MfaRequiredException(PetAidError):
    """Raised when a Veterinary Expert must complete MFA before access
    (SRS 2.1 / Assumption A1).
    """

    code = "mfa_required"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("Multi-factor verification is required for this account.")


class PaymentFailedException(PetAidError):
    """Raised when ``PaymentProcessor`` returns a non-success outcome."""

    code = "payment_failed"
    http_status = 402  # Payment Required

    def __init__(self, message: str = "Payment could not be processed.") -> None:
        super().__init__(message)


class NotAuthorisedException(PetAidError):
    """Raised when an authenticated actor tries to access a function reserved
    for the other role (e.g. a Pet Owner attempting content management).
    """

    code = "not_authorised"
    http_status = 403

    def __init__(self, message: str = "You are not authorised to perform this action.") -> None:
        super().__init__(message)


class NotFoundException(PetAidError):
    """Raised when a requested entity does not exist or is not visible to the actor."""

    code = "not_found"
    http_status = 404

    def __init__(self, entity: str) -> None:
        super().__init__(f"{entity} not found.")
        self.entity = entity
