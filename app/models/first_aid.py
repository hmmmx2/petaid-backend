"""FirstAidGuidance entity (SRS 3.3.13).

Represents one emergency protocol filtered by :class:`PetType` and
supported by zero or more :class:`Resource` records. Authored exclusively
by a :class:`VeterinaryExpert`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin

# M2M link between FirstAidGuidance and supporting Resources.
first_aid_resource_link = Table(
    "first_aid_resource_link",
    Base.metadata,
    Column(
        "guidance_id",
        UUID(as_uuid=True),
        ForeignKey("first_aid_guidance.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "resource_id",
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class FirstAidGuidance(UUIDPkMixin, TimestampMixin, Base):
    """Sequential numbered steps for one emergency protocol."""

    __tablename__ = "first_aid_guidance"

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
    emergency_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Sequential ordered steps stored as a JSON list of strings. Keeping
    # them in one column avoids a child table whose sole purpose would be
    # to hold an ordered ``position`` column.
    steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    pet_type = relationship("PetType", lazy="joined")
    resources = relationship(
        "Resource",
        secondary=first_aid_resource_link,
        lazy="selectin",
    )
