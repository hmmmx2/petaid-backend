"""Object storage offload to Supabase Storage.

Uploaded images arrive from the client as base64 ``data:`` URLs (the frontend
downscales them first). When Supabase Storage is configured (``SUPABASE_URL`` +
``SUPABASE_SERVICE_KEY``) we upload those bytes to a **public** bucket and
persist the small public URL instead of the inline base64 — keeping DB rows
small and serving the images from Supabase's CDN.

Design goals:
* **Graceful fallback.** If storage is not configured, or the input is already a
  URL, or an upload fails for any reason, the original value is returned
  unchanged. The app therefore degrades to inline data-URL storage and never
  breaks because of a storage hiccup.
* **Server-only credential.** The ``service_role`` key lives only in the backend
  environment; it bypasses RLS so no anonymous-write policy is needed. It is
  never sent to the browser.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
import uuid

import httpx

from app.core.config import get_settings

logger = logging.getLogger("petaid.storage")

# data:<mime>;base64,<payload>
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+/-]+);base64,(?P<b64>.+)$", re.DOTALL)
_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
_ALLOWED_MIME = list(_EXT.keys())
_MAX_BYTES = 6 * 1024 * 1024  # 6 MB safety cap per object

# Create the bucket at most once per process.
_bucket_ready = False


def _settings():
    return get_settings()


def _base() -> str:
    return _settings().supabase_url.rstrip("/")


def _auth_headers() -> dict[str, str]:
    key = _settings().supabase_service_key
    return {"Authorization": f"Bearer {key}", "apikey": key}


async def _ensure_bucket(client: httpx.AsyncClient) -> None:
    """Create the public bucket if it doesn't exist yet (idempotent)."""
    global _bucket_ready
    if _bucket_ready:
        return
    bucket = _settings().supabase_storage_bucket
    resp = await client.post(
        f"{_base()}/storage/v1/bucket",
        headers={**_auth_headers(), "Content-Type": "application/json"},
        json={
            "id": bucket,
            "name": bucket,
            "public": True,
            "file_size_limit": _MAX_BYTES,
            "allowed_mime_types": _ALLOWED_MIME,
        },
    )
    # 200/201 = created; 409 = already exists. Anything else: log and carry on
    # (the upload below will surface a hard failure if the bucket is unusable).
    if resp.status_code not in (200, 201, 409):
        logger.warning("bucket ensure returned %s: %s", resp.status_code, resp.text[:200])
    _bucket_ready = True


async def offload_data_url(value: str | None, prefix: str) -> str | None:
    """Offload a base64 data-URL to Supabase Storage and return its public URL.

    Returns ``value`` unchanged when storage is disabled, the value is empty or
    already a URL, or the upload fails (graceful fallback to inline storage).
    """
    if not value or not _settings().storage_enabled:
        return value
    match = _DATA_URL_RE.match(value.strip())
    if not match:
        return value  # already a hosted URL, or not an image data-URL
    mime = match.group("mime").lower()
    try:
        raw = base64.b64decode(match.group("b64"), validate=False)
    except (binascii.Error, ValueError):
        return value
    if not raw or len(raw) > _MAX_BYTES:
        return value

    bucket = _settings().supabase_storage_bucket
    path = f"{prefix}/{uuid.uuid4().hex}.{_EXT.get(mime, 'bin')}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            await _ensure_bucket(client)
            resp = await client.post(
                f"{_base()}/storage/v1/object/{bucket}/{path}",
                headers={**_auth_headers(), "Content-Type": mime, "x-upsert": "true"},
                content=raw,
            )
            if resp.status_code not in (200, 201):
                logger.warning("storage upload failed %s: %s", resp.status_code, resp.text[:200])
                return value
    except httpx.HTTPError as exc:
        logger.warning("storage upload error: %s", type(exc).__name__)
        return value

    return f"{_base()}/storage/v1/object/public/{bucket}/{path}"


async def offload_many(values: list[str], prefix: str) -> list[str]:
    """Offload each data-URL in a list (used for inquiry attachments)."""
    result: list[str] = []
    for v in values:
        result.append(await offload_data_url(v, prefix) or v)
    return result
