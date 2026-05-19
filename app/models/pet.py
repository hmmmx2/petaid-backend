import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Pet(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "pets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    species: Mapped[str] = mapped_column(String(40), nullable=False)  # dog, cat, rabbit, ...
    breed: Mapped[str | None] = mapped_column(String(80), nullable=True)
    age_years: Mapped[int | None] = mapped_column(nullable=True)
    icon_emoji: Mapped[str] = mapped_column(String(8), nullable=False, default="🐾")
    icon_bg: Mapped[str] = mapped_column(String(16), nullable=False, default="#F5F5F4")

    owner = relationship("User", back_populates="pets")
