"""UserCredentials data-holder (SRS 3.3.20).

Stored in its own table and joined 1:1 with :class:`Account` so the column
is physically separable from the rest of the account profile. Access is
enforced by :class:`app.domain.auth_manager.AuthManager` — no other class
should import or query this model directly. The encapsulation is enforced
by convention (Python lacks ``friend`` declarations) and reinforced in the
code review checklist in ``DESIGN.md``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class UserCredentials(UUIDPkMixin, TimestampMixin, Base):
    """Hashed password, email and MFA state for one :class:`Account`.

    The relationship to ``Account`` is composition (SRS 4.1.7): credentials
    cannot exist without their owner and are cascade-deleted if the account
    is removed.
    """

    __tablename__ = "user_credentials"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # MFA state — applies only to Veterinary Experts (SRS A1).
    mfa_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Lockout state — five-failure / 30-second rule (SRS 1.3.3).
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account = relationship("Account", back_populates="credentials")
