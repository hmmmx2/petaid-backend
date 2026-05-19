"""Account class hierarchy.

Implements UML "abstract Account ← PetOwner / VeterinaryExpert" using
SQLAlchemy single-table inheritance with a ``role`` discriminator column.
Both Python class structure *and* row-level discrimination match the UML
(SRS 3.3.8 - 3.3.10).
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Account(UUIDPkMixin, TimestampMixin, Base):
    """Abstract base — never instantiated directly (SRS 4.1.6)."""

    __tablename__ = "accounts"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    initials: Mapped[str] = mapped_column(String(4), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Single-table inheritance discriminator. ``pet_owner`` and
    # ``veterinary_expert`` are the only legal values.
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    __mapper_args__ = {
        "polymorphic_identity": "account",
        "polymorphic_on": "role",
    }

    # Composition (1:1) — every Account always owns one UserCredentials.
    credentials = relationship(
        "UserCredentials",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def display_name(self) -> str:
        """Return the first name of the account holder for headers etc."""
        return self.full_name.split()[0] if self.full_name else "User"


class PetOwner(Account):
    """A registered pet owner (SRS 3.3.9).

    Aggregates ``Pet`` records and acts as the primary actor for emergency
    guidance, learning, donations, feedback, inquiries and chat.
    """

    __mapper_args__ = {"polymorphic_identity": "pet_owner"}

    # Pet aggregation (weak ownership — a Pet can in theory be transferred).
    pets = relationship(
        "Pet",
        back_populates="owner",
        cascade="all, delete-orphan",
        primaryjoin="PetOwner.id == Pet.owner_id",
    )


class VeterinaryExpert(Account):
    """A licensed veterinary expert (SRS 3.3.10).

    Created via the registration flow with a vet-association code; in
    Assignment 3 scope, simply provisioned by the seed script. MFA is
    required at login (enforced in :class:`AuthManager`).
    """

    __mapper_args__ = {"polymorphic_identity": "veterinary_expert"}
