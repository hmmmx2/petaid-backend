"""Inquiry entity (SRS 3.3.16).

Asynchronous Pet Owner → Veterinary Expert written question. Owns its own
status lifecycle and publishes Observer events on transition.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class InquiryStatus(str, enum.Enum):
    """Lifecycle states (SRS 3.1.3.9)."""

    PENDING = "pending"
    RESPONDED = "responded"
    CLOSED = "closed"


class Inquiry(UUIDPkMixin, TimestampMixin, Base):
    """One written question + (eventually) one response.

    The behaviour is deliberately kept on the entity (SRS 4.1.4): the
    router calls ``inquiry.respond(...)`` instead of mutating columns
    directly.
    """

    __tablename__ = "inquiries"

    pet_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    assigned_vet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional photos the owner attaches (e.g. of the pet's condition). Stored
    # as inline data URLs / remote URLs so the vet can view them with the text.
    image_urls: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[InquiryStatus] = mapped_column(
        Enum(InquiryStatus, native_enum=False),
        nullable=False,
        default=InquiryStatus.PENDING,
        index=True,
    )

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pet_owner = relationship(
        "Account", foreign_keys=[pet_owner_id], lazy="joined"
    )
    assigned_vet = relationship(
        "Account", foreign_keys=[assigned_vet_id], lazy="joined"
    )

    # ------------------------------------------------------------------ #
    # Behaviour                                                          #
    # ------------------------------------------------------------------ #
    def respond(self, vet_id: uuid.UUID, response_text: str) -> None:
        """Mark the inquiry as responded by ``vet_id``.

        Raises :class:`ValueError` if the inquiry is already closed; the
        router converts this to ``InvalidInputException``.
        """
        if self.status == InquiryStatus.CLOSED:
            raise ValueError("Cannot respond to a closed inquiry.")
        self.assigned_vet_id = vet_id
        self.response = response_text
        self.status = InquiryStatus.RESPONDED
        self.responded_at = datetime.now(timezone.utc)

    def close(self) -> None:
        """Final state — no further responses accepted."""
        self.status = InquiryStatus.CLOSED
        self.closed_at = datetime.now(timezone.utc)
