"""Feedback and FeedbackEntry (SRS 3.3.19, 3.3.22).

Per the UML, ``Feedback`` targets a single ``Resource`` (0..1), realised as a
nullable ``resource_id`` foreign key with ``ON DELETE CASCADE`` — so the target
is guaranteed to exist and feedback is removed with the resource it rates
(unlike a bare polymorphic ``target_id`` UUID). ``target_type`` / ``target_id``
are kept as derived, read-only properties so the API, dashboards and UI keep a
single, simple shape. ``FeedbackEntry`` is the composed data-holder holding the
rating and comment.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class FeedbackTargetType(str, enum.Enum):
    """Type of content the feedback targets (currently always RESOURCE)."""

    RESOURCE = "resource"


class Feedback(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    submitter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Target (UML: Feedback -> Resource, 0..1). A real FK preserves integrity.
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

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

    # --- derived view: keep a stable (target_type, target_id) shape -------- #
    @property
    def target_type(self) -> FeedbackTargetType:
        return FeedbackTargetType.RESOURCE

    @property
    def target_id(self) -> uuid.UUID | None:
        return self.resource_id


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
