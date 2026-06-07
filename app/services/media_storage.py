"""Cloudflare R2 media storage service (S3-compatible API via aioboto3)."""
from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager

from typing_extensions import TypedDict

from app.core.config import get_settings
from app.domain.exceptions import NotFoundException

# NOTE: botocore and aioboto3 are imported lazily inside the methods that use
# them (not at module top). Importing this module must stay free of the R2
# stack so the FastAPI app can boot even when that stack is missing or broken
# in the deploy container. The health check only passes if app import never
# depends on an optional integration.

logger = logging.getLogger("petaid.r2")

_SLUG_RE = re.compile(r"[^\w.\-]")

# Origins permitted to PUT directly to the R2 bucket from the browser.
_CORS_ORIGINS = [
    "https://petaid-frontend.vercel.app",
]


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name.lower())[:100]


class UploadUrlResult(TypedDict):
    upload_url: str
    public_url: str
    key: str
    expires_in: int


class HeadResult(TypedDict):
    size: int
    content_type: str
    etag: str


class R2MediaStorage:
    """Async wrapper around Cloudflare R2 (S3-compatible endpoint)."""

    def __init__(self) -> None:
        self._session = None

    def _get_session(self):
        if self._session is None:
            import aioboto3
            self._session = aioboto3.Session()
        return self._session

    @asynccontextmanager
    async def _client(self):
        from botocore.config import Config

        settings = get_settings()
        async with self._get_session().client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            region_name="auto",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(signature_version="s3v4"),
        ) as client:
            yield client

    async def configure_cors(self) -> None:
        """Best-effort attempt to set the R2 bucket CORS policy at startup.

        IMPORTANT: this is very likely a no-op against Cloudflare R2. R2's
        bucket CORS is managed through the Cloudflare API (which needs a
        Cloudflare API token), not the S3 ``put_bucket_cors`` action with the
        S3 HMAC credentials we hold here — so this call typically does nothing
        even when it appears to succeed. Do NOT read the log line below as
        proof that browser CORS is configured.

        Browser CORS for the SPA is actually handled on the frontend by the
        Content-Security-Policy in ``next.config.js`` (which allow-lists the
        R2 upload/CDN domains). Presigned PUT uploads work regardless because
        they don't trigger a CORS preflight the bucket would need to answer.

        Kept as a harmless best-effort call (it still works on a real
        S3-compatible endpoint). Failures are swallowed and never block startup.
        """
        settings = get_settings()
        if not settings.r2_enabled:
            logger.info("R2 not configured — skipping CORS setup")
            return

        cors_config = {
            "CORSRules": [
                {
                    "AllowedOrigins": _CORS_ORIGINS,
                    "AllowedMethods": ["PUT", "GET", "HEAD"],
                    "AllowedHeaders": ["Content-Type", "*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        }
        try:
            async with self._client() as client:
                await client.put_bucket_cors(
                    Bucket=settings.r2_bucket_name,
                    CORSConfiguration=cors_config,
                )
            logger.info(
                "R2 put_bucket_cors attempted for bucket %s — note this is "
                "likely a no-op on R2 (browser CORS is enforced by the frontend "
                "CSP, not this call)",
                settings.r2_bucket_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("R2 CORS setup failed (%s): %s", type(exc).__name__, exc)

    async def generate_upload_url(
        self,
        filename: str,
        content_type: str,
        max_bytes: int,
    ) -> UploadUrlResult:
        settings = get_settings()
        key = f"resources/{uuid.uuid4().hex}/{_slugify(filename)}"
        async with self._client() as client:
            upload_url: str = await client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.r2_bucket_name,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=300,
            )
        base = (settings.r2_public_base_url or "").rstrip("/")
        return UploadUrlResult(
            upload_url=upload_url,
            public_url=f"{base}/{key}",
            key=key,
            expires_in=300,
        )

    async def head_object(self, key: str) -> HeadResult:
        from botocore.exceptions import ClientError

        settings = get_settings()
        async with self._client() as client:
            try:
                resp = await client.head_object(
                    Bucket=settings.r2_bucket_name,
                    Key=key,
                )
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("404", "NoSuchKey", "403"):
                    raise NotFoundException("Media object") from exc
                raise
        return HeadResult(
            size=resp["ContentLength"],
            content_type=resp.get("ContentType", ""),
            etag=resp.get("ETag", "").strip('"'),
        )

    async def delete_object(self, key: str) -> None:
        settings = get_settings()
        async with self._client() as client:
            await client.delete_object(
                Bucket=settings.r2_bucket_name,
                Key=key,
            )


r2_storage = R2MediaStorage()
