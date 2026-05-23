"""Pet entity (SRS 3.3.11)."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Pet(UUIDPkMixin, TimestampMixin, Base):
    """A single pet aggregated under one :class:`PetOwner`.

    Drives which :class:`FirstAidGuidance` and :class:`Resource` records are
    surfaced to the owner (filtered by :class:`PetType`).
    """

    __tablename__ = "pets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    pet_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pet_types.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    breed: Mapped[str | None] = mapped_column(String(80), nullable=True)
    age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Avatar: a photo wins, else a custom chosen icon, else the pet-type emoji.
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)

    owner = relationship("PetOwner", back_populates="pets")
    pet_type = relationship("PetType", lazy="joined")
