import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Resource(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "resources"

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # video, pdf, images
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class UserResource(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_resources"
    __table_args__ = (UniqueConstraint("user_id", "resource_id", name="uq_user_resource"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # watched, in_progress, new

    user = relationship("User", back_populates="resources")
    resource = relationship("Resource")
