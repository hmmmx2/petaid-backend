"""RFC 6238 TOTP (time-based one-time passwords) — pure standard library.

Used for Veterinary Expert multi-factor authentication. Implemented directly
(HMAC-SHA1 over a time counter, per RFC 4226/6238) to avoid an extra runtime
dependency. Codes are compatible with Google Authenticator, Authy, 1Password,
etc., so an expert enrols by scanning the ``otpauth://`` provisioning URI.

Security notes:
* Secrets are random 160-bit values, base32-encoded (the authenticator-app
  standard).
* Verification compares with :func:`hmac.compare_digest` (constant time) and
  accepts a ±1 step (±30s) drift window to tolerate clock skew — no more, to
  keep the live brute-force window small.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

_STEP_SECONDS = 30
_DIGITS = 6


def generate_secret(num_bytes: int = 20) -> str:
    """Return a fresh base32 secret (no padding), suitable for an authenticator."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = _DIGITS) -> str:
    # Restore base32 padding before decoding.
    padded = secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def verify(
    secret_b32: str,
    code: str,
    *,
    window: int = 1,
    at: float | None = None,
    digits: int = _DIGITS,
) -> bool:
    """True if ``code`` is valid for ``secret_b32`` now (within ±``window`` steps)."""
    if not secret_b32 or not code:
        return False
    code = code.strip()
    if not code.isdigit():
        return False
    code = code.zfill(digits)
    counter = int((at if at is not None else time.time()) // _STEP_SECONDS)
    try:
        for drift in range(-window, window + 1):
            candidate = _hotp(secret_b32, counter + drift, digits)
            if hmac.compare_digest(candidate, code):
                return True
    except (ValueError, TypeError, struct.error):
        # Malformed/non-base32 secret (e.g. a legacy placeholder) — fail closed
        # rather than raising, so a bad stored secret can't 500 the login path.
        return False
    return False


def now_code(secret_b32: str, *, at: float | None = None, digits: int = _DIGITS) -> str:
    """The current valid code — for tests / dev tooling, never sent to clients."""
    counter = int((at if at is not None else time.time()) // _STEP_SECONDS)
    return _hotp(secret_b32, counter, digits)


def provisioning_uri(secret_b32: str, account_name: str, issuer: str = "PetAid") -> str:
    """Build the ``otpauth://totp/...`` URI an authenticator app scans."""
    label = quote(f"{issuer}:{account_name}")
    params = urlencode(
        {
            "secret": secret_b32,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": _DIGITS,
            "period": _STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{params}"
