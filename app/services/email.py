"""Transactional email via SMTP.

Optional integration. Uses the Python standard library (``smtplib`` +
``email.message``) run off the event loop with ``asyncio.to_thread`` — so it
adds no third-party dependency and can never block app startup or the request
loop. When SMTP is not configured the senders are no-ops and the caller falls
back to the dev behaviour (surfacing the code in the API response outside
production).

All failures are logged and swallowed: a mail outage must never break the
register / password-reset flow, and we must never disclose whether an email
maps to an account (account-enumeration safety).
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("petaid.email")


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
    msg.set_content(body)

    if port == 465:
        # Implicit TLS.
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as server:
            if user:
                server.login(user, password or "")
            server.send_message(msg)
    else:
        # STARTTLS (port 587 and friends).
        with smtplib.SMTP(host, port, timeout=15) as server:
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


async def _send(to: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.email_enabled:
        logger.info("Email not configured — skipping message to %s (%s)", to, subject)
        return False
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
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email send failed (%s): %s", type(exc).__name__, exc)
        return False


async def send_verification_code(to: str, code: str) -> bool:
    """Email a 6-digit account-verification code (best effort)."""
    body = (
        "Welcome to PetAid!\n\n"
        f"Your email verification code is: {code}\n\n"
        "Enter it in the app to finish creating your account. "
        "The code expires in 15 minutes.\n\n"
        "If you didn't sign up for PetAid, you can safely ignore this email."
    )
    return await _send(to, "Your PetAid verification code", body)


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
    return await _send(to, "Your PetAid password reset code", body)
