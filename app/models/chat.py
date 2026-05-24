"""Chat and ChatMessage entities (SRS 3.3.17).

Real-time follow-up channel between a :class:`PetOwner` (initiator) and a
:class:`VeterinaryExpert` (joiner). Manages its own status lifecycle
(Initiated → Active → Closed) and emits Observer events on transition.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class ChatStatus(str, enum.Enum):
    INITIATED = "initiated"
    ACTIVE = "active"
    CLOSED = "closed"


class Chat(UUIDPkMixin, TimestampMixin, Base):
    """A chat session between one Pet Owner and one Veterinary Expert."""

    __tablename__ = "chats"

    pet_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    vet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    subject: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    status: Mapped[ChatStatus] = mapped_column(
        Enum(ChatStatus, native_enum=False),
        nullable=False,
        default=ChatStatus.INITIATED,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-participant read cursors → unread counts + "Seen" receipts. Exactly two
    # participants, so two columns are simpler than a ChatParticipant table.
    owner_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vet_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pet_owner = relationship(
        "Account", foreign_keys=[pet_owner_id], lazy="joined"
    )
    vet = relationship("Account", foreign_keys=[vet_id], lazy="joined")
    messages = relationship(
        "ChatMessage",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="ChatMessage.sent_at",
    )

    # ------------------------------------------------------------------ #
    # Behaviour                                                          #
    # ------------------------------------------------------------------ #
    def join(self, vet_id: uuid.UUID) -> None:
        """Veterinary expert joins; status transitions to Active."""
        if self.status == ChatStatus.CLOSED:
            raise ValueError("Cannot join a closed chat.")
        self.vet_id = vet_id
        self.status = ChatStatus.ACTIVE

    def close(self) -> None:
        """Either actor closes the session."""
        self.status = ChatStatus.CLOSED
        self.ended_at = datetime.now(timezone.utc)


class ChatMessage(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    chat = relationship("Chat", back_populates="messages")
    sender = relationship("Account", lazy="joined")

    @property
    def edited(self) -> bool:
        """True once the message has been edited after sending.

        Derived from the timestamp mixin (no extra column): ``updated_at`` is
        bumped on every write, so a gap beyond a couple of seconds from
        ``created_at`` means the body was changed after the initial insert.
        """
        if not self.created_at or not self.updated_at:
            return False
        return (self.updated_at - self.created_at).total_seconds() > 2
