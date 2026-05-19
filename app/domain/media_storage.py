"""MediaStorage — file validation + retrieval (SRS 3.3.7).

This implementation does not persist real binary files; instead, the
Veterinary Expert supplies a logical media reference (URL, S3 key, etc.)
along with its declared size and content type. :class:`MediaStorage`
validates the format and size before a :class:`Resource` can transition
from ``draft`` to ``published``, fulfilling the boundary case in SRS 1.3.2.

The class is intentionally narrow (heuristic 4.1.5). No other class should
parse file extensions or peek at content types directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.domain.exceptions import InvalidInputException

# Limits (SRS 1.3.2)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_VIDEO = {".mp4", ".mov", ".webm"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_PDF = {".pdf"}
ALLOWED_BY_TYPE: dict[str, set[str]] = {
    "video": ALLOWED_VIDEO,
    "images": ALLOWED_IMAGE,
    "image": ALLOWED_IMAGE,
    "pdf": ALLOWED_PDF,
}


@dataclass(frozen=True)
class MediaDescriptor:
    """Returned by :meth:`MediaStorage.accept` once validation passes."""

    media_path: str
    content_type: str
    size_bytes: int


class MediaStorage:
    """Stateless validator / retriever for Resource media files."""

    def accept(
        self, *, content_type: str, media_path: str, size_bytes: int
    ) -> MediaDescriptor:
        """Validate the inputs and return a :class:`MediaDescriptor`.

        Raises :class:`InvalidInputException` on bad input. The method is
        named ``accept`` to communicate that on success the file is now
        owned by the storage layer for the lifetime of the Resource.
        """
        content_type = content_type.lower()
        if content_type not in ALLOWED_BY_TYPE:
            raise InvalidInputException(
                "content_type",
                f"Unsupported content type: {content_type!r}",
            )
        if size_bytes <= 0:
            raise InvalidInputException("size_bytes", "File size must be positive.")
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise InvalidInputException(
                "size_bytes",
                f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit.",
            )
        if not media_path:
            raise InvalidInputException("media_path", "Media path is required.")

        ext = os.path.splitext(media_path)[1].lower()
        if ext and ext not in ALLOWED_BY_TYPE[content_type]:
            raise InvalidInputException(
                "media_path",
                f"Extension {ext!r} is not permitted for {content_type!r}.",
            )
        return MediaDescriptor(
            media_path=media_path, content_type=content_type, size_bytes=size_bytes
        )

    def retrieve(self, media_path: str) -> str:
        """Return a URL the dashboard can use to serve ``media_path``.

        In Assignment 3 scope, the stored path *is* the URL. A real
        implementation would sign an S3 URL here.
        """
        return media_path
