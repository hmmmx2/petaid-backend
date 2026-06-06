"""Media upload endpoints — presigned URL generation for direct browser-to-R2 upload."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import CurrentVetDep, require
from app.core.rate_limit import enforce
from app.domain.exceptions import InvalidInputException
from app.domain.permissions import Permission
from app.services.media_storage import UploadUrlResult, r2_storage

router = APIRouter(prefix="/media", tags=["media"])

# MIME-type allow-list. Keep in sync with R2 CORS policy.
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_VIDEO_TYPES = frozenset({"video/mp4"})
_PDF_TYPES = frozenset({"application/pdf"})
ALLOWED_CONTENT_TYPES = _IMAGE_TYPES | _VIDEO_TYPES | _PDF_TYPES

# Per-type size caps (bytes).
_SIZE_CAPS: list[tuple[frozenset[str], int]] = [
    (_VIDEO_TYPES, 100 * 1024 * 1024),            # 100 MB for video
    (_IMAGE_TYPES | _PDF_TYPES, 10 * 1024 * 1024), # 10 MB for images / PDF
]


def _size_cap_for(content_type: str) -> int:
    for types, cap in _SIZE_CAPS:
        if content_type in types:
            return cap
    return 10 * 1024 * 1024


class MediaUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(min_length=1, max_length=80)
    expected_bytes: int = Field(ge=1)


@router.post(
    "/upload-url",
    response_model=UploadUrlResult,
    dependencies=[Depends(require(Permission.RESOURCE_MANAGE))],
    summary="Request a presigned PUT URL for direct browser-to-R2 upload",
)
async def request_upload_url(
    payload: MediaUploadRequest,
    vet: CurrentVetDep,
) -> UploadUrlResult:
    """Generate a short-lived (5 min) presigned PUT URL.

    The browser PUTs the file directly to Cloudflare R2 — the backend never
    proxies the binary.  After a successful PUT, submit the ``key`` returned
    here to ``POST /api/v1/resources`` as ``media_key``.

    Permissions: Veterinary Experts only (RESOURCE_MANAGE).
    Rate limit: 20 requests per hour per vet.
    """
    enforce("media_upload", str(vet.id), max_requests=20, window_seconds=3600)

    ct = payload.content_type.lower().strip()
    if ct not in ALLOWED_CONTENT_TYPES:
        raise InvalidInputException(
            "content_type",
            f"Unsupported type {ct!r}. Allowed: "
            + ", ".join(sorted(ALLOWED_CONTENT_TYPES)),
        )

    cap = _size_cap_for(ct)
    if payload.expected_bytes > cap:
        raise InvalidInputException(
            "expected_bytes",
            f"File size {payload.expected_bytes:,} B exceeds the "
            f"{cap // (1024 * 1024)} MB limit for {ct}.",
        )

    return await r2_storage.generate_upload_url(
        filename=payload.filename,
        content_type=ct,
        max_bytes=cap,
    )
