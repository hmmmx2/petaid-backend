import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class ChatThread(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    counterpart_name: Mapped[str] = mapped_column(String(120), nullable=False)
    counterpart_initials: Mapped[str] = mapped_column(String(4), nullable=False)
    counterpart_bg: Mapped[str] = mapped_column(String(16), nullable=False, default="#F5F5F4")
    counterpart_fg: Mapped[str] = mapped_column(String(16), nullable=False, default="#515c67")
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="chat_threads")
    messages = relationship(
        "ChatMessage", back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.sent_at"
    )


class ChatMessage(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "vet"
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    thread = relationship("ChatThread", back_populates="messages")
