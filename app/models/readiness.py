import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class ReadinessCategory(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "readiness_categories"

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#1D9E75")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserReadiness(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_readiness"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_user_category"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("readiness_categories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    score_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="readiness")
    category = relationship("ReadinessCategory")
