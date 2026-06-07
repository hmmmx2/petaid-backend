"""Transactional email via SMTP.

Optional integration. Uses the Python standard library (``smtplib`` +
``email.message``) run off the event loop with ``asyncio.to_thread`` — so it
adds no third-party dependency and can never block app startup or the request
loop. When SMTP is not configured the senders are no-ops and the caller falls
back to the dev behaviour (surfacing the code in the API response outside
production).

Reliability notes:
* Every message carries ``Date`` and ``Message-ID`` headers. Mail without them
  is widely treated as malformed — many relays reject it outright and spam
  filters silently drop it, which is a common cause of "the API says 201 but no
  email arrives".
* All failures are captured and returned to the caller (never raised through
  the request path) so a mail outage can't break register / password-reset and
  can't disclose whether an email maps to an account (enumeration safety).
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.core.config import get_settings

logger = logging.getLogger("petaid.email")


def _from_domain(sender: str) -> str:
    """Best-effort domain for the Message-ID, derived from the From address."""
    if "@" in sender:
        # Handles both "Name <a@b.com>" and "a@b.com".
        addr = sender.split("<")[-1].rstrip(">")
        if "@" in addr:
            return addr.split("@")[-1].strip()
    return "petaid.local"


def _send_sync(
    *,
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    sender: str,
    to: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    # Required, deliverability-critical headers (see module docstring).
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=_from_domain(sender))
    msg.set_content(body)

    if port == 465:
        # Implicit TLS.
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
            if user:
                server.login(user, password or "")
            server.send_message(msg)
    else:
        # STARTTLS (port 587 and friends).
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            try:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                # Relay without STARTTLS (e.g. a local test catcher) — proceed
                # in the clear rather than failing the send.
                pass
            if user:
                server.login(user, password or "")
            server.send_message(msg)


async def _send(to: str, subject: str, body: str) -> tuple[bool, str | None]:
    """Send one message. Returns ``(ok, error_detail)`` — never raises."""
    settings = get_settings()
    if not settings.email_enabled:
        msg = "SMTP not configured (set SMTP_HOST and SMTP_FROM/SMTP_USER)"
        logger.info("Email skipped — %s — to %s (%s)", msg, to, subject)
        return False, msg
    try:
        await asyncio.to_thread(
            _send_sync,
            host=settings.smtp_host or "",
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            sender=settings.smtp_from or settings.smtp_user or "",
            to=to,
            subject=subject,
            body=body,
        )
        logger.info("Sent email to %s (%s)", to, subject)
        return True, None
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        logger.warning("Email send failed to %s (%s)", to, detail)
        return False, detail


async def send_verification_code(to: str, code: str) -> bool:
    """Email a 6-digit account-verification code (best effort)."""
    body = (
        "Welcome to PetAid!\n\n"
        f"Your email verification code is: {code}\n\n"
        "Enter it in the app to finish creating your account. "
        "The code expires in 15 minutes.\n\n"
        "If you didn't sign up for PetAid, you can safely ignore this email."
    )
    ok, _ = await _send(to, "Your PetAid verification code", body)
    return ok


async def send_password_reset_code(to: str, code: str) -> bool:
    """Email a 6-digit password-reset code (best effort)."""
    body = (
        "We received a request to reset your PetAid password.\n\n"
        f"Your password reset code is: {code}\n\n"
        "Enter it in the app to choose a new password. "
        "The code expires in 15 minutes.\n\n"
        "If you didn't request this, you can safely ignore this email — "
        "your password will not change."
    )
    ok, _ = await _send(to, "Your PetAid password reset code", body)
    return ok


async def send_test_email(to: str) -> tuple[bool, str | None]:
    """Send a diagnostic test message. Returns ``(ok, error_detail)``.

    Used by the vet-only email diagnostics endpoint to surface the real SMTP
    error (which the register/reset paths intentionally swallow).
    """
    body = (
        "This is a PetAid email deliverability test.\n\n"
        "If you received this, transactional email is working correctly."
    )
    return await _send(to, "PetAid email test", body)
