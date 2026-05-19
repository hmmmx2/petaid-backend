"""PetType classifier (SRS 3.3.12)."""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class PetType(UUIDPkMixin, TimestampMixin, Base):
    """Animal classification used to filter Pets, Resources and FirstAidGuidance.

    Read-only during normal software use; only a :class:`VeterinaryExpert`
    creates new pet types (enforced in the router).
    """

    __tablename__ = "pet_types"

    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    icon_emoji: Mapped[str] = mapped_column(String(8), nullable=False, default="🐾")
    icon_bg: Mapped[str] = mapped_column(String(16), nullable=False, default="#F5F5F4")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
