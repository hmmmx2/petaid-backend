"""Resource entity (SRS 3.3.14)."""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class ResourceStatus(str, enum.Enum):
    """Lifecycle of a :class:`Resource` (SRS 7.3).

    A new resource starts in :attr:`DRAFT` and only becomes visible to Pet
    Owners after the Veterinary Expert explicitly approves it.
    """

    DRAFT = "draft"
    PUBLISHED = "published"


class Resource(UUIDPkMixin, TimestampMixin, Base):
    """A content item (video, image, document) managed by a Veterinary
    Expert and grouped by :class:`PetType`.

    File handling is delegated to ``MediaStorage`` — the column on this
    table is only the relative ``media_path`` returned by the storage layer.
    """

    __tablename__ = "resources"

    pet_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pet_types.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)  # video, pdf, images
    media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(ResourceStatus, native_enum=False),
        nullable=False,
        default=ResourceStatus.DRAFT,
        index=True,
    )

    pet_type = relationship("PetType", lazy="joined")
    author = relationship("Account", lazy="joined")
