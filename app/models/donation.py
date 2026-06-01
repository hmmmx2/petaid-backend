"""Donation and DonationRecord (SRS 3.3.18, 3.3.21).

``Donation`` delegates all transaction execution to
:class:`PaymentProcessor` (Adapter pattern, SRS 5.3.1). On success it
creates one composed :class:`DonationRecord` whose fields are write-once
to preserve financial integrity (SRS A4).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.exceptions import InvalidInputException
from app.models.mixins import TimestampMixin, UUIDPkMixin


class DonationStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Donation(UUIDPkMixin, TimestampMixin, Base):
    """One voluntary contribution initiated by a Pet Owner."""

    __tablename__ = "donations"

    pet_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MYR")
    status: Mapped[DonationStatus] = mapped_column(
        Enum(DonationStatus, native_enum=False),
        nullable=False,
        default=DonationStatus.PENDING,
        index=True,
    )
    recurring: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Demo-mode payment method label (card_on_file / ewallet / online_banking).
    # Stored for traceability on the vet review screen, not for PCI handling.
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)

    pet_owner = relationship("Account", lazy="joined")
    # Composition (SRS 4.1.7) — record cannot exist without its donation.
    record = relationship(
        "DonationRecord",
        back_populates="donation",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # --- Status transitions (encapsulation) ---------------------------- #
    def mark_succeeded(self, record: "DonationRecord") -> None:
        """Mark this donation as succeeded once its immutable record exists.

        Enforces the invariant "SUCCEEDED implies a record exists" here rather
        than scattering raw status assignments across the router (SRS A4).
        """
        if record.donation_id != self.id:
            raise InvalidInputException(
                "record", "Donation record does not belong to this donation."
            )
        self.status = DonationStatus.SUCCEEDED

    def mark_failed(self) -> None:
        """Mark this donation as failed. No record is created."""
        self.status = DonationStatus.FAILED


class DonationRecord(UUIDPkMixin, TimestampMixin, Base):
    """Immutable transaction outcome (SRS 4.1.2 + A4).

    Once persisted, no method on this class mutates its columns. Any
    application code attempting to overwrite a record is a bug; the
    invariant is reinforced in code review per ``DESIGN.md``.
    """

    __tablename__ = "donation_records"

    donation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("donations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    transaction_ref: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    final_status: Mapped[str] = mapped_column(String(20), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    donation = relationship("Donation", back_populates="record")


# --- DonationRecord immutability (SRS A4, <<immutable>> stereotype) -------- #
# A donation record is write-once. Any attempt to UPDATE it after insert is a
# bug; we refuse at the data layer so the invariant is enforced regardless of
# which caller forgets it.
@event.listens_for(DonationRecord, "before_update", propagate=True)
def _block_donation_record_update(mapper, connection, target):  # noqa: ARG001
    raise InvalidInputException(
        "donation_record",
        "DonationRecord is immutable, no updates allowed after creation.",
    )
