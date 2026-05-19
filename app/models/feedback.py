"""Feedback and FeedbackEntry (SRS 3.3.19, 3.3.22).

``Feedback`` references the target entity (either a Resource or a
FirstAidGuidance — modelled with a discriminator column and a UUID
``target_id``, mirroring the UML where the association is polymorphic).
``FeedbackEntry`` is a composed data-holder containing the rating and
comment.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class FeedbackTargetType(str, enum.Enum):
    """Type of content the feedback targets."""

    RESOURCE = "resource"
    GUIDANCE = "guidance"


class Feedback(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    submitter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    target_type: Mapped[FeedbackTargetType] = mapped_column(
        Enum(FeedbackTargetType, native_enum=False), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    flagged: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)

    submitter = relationship("Account", lazy="joined")
    # Composition (SRS 4.1.7) — exactly one entry per feedback.
    entry = relationship(
        "FeedbackEntry",
        back_populates="feedback",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class FeedbackEntry(UUIDPkMixin, TimestampMixin, Base):
    """Composed data-holder with the rating and comment (SRS 3.3.22)."""

    __tablename__ = "feedback_entries"

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..5
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")

    feedback = relationship("Feedback", back_populates="entry")
