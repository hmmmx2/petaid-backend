"""Donation endpoints (SRS 7.5).

The router delegates the actual charge to :class:`PaymentProcessor`
(Adapter, SRS 5.3.1). On success it creates the immutable
:class:`DonationRecord` via composition (SRS A4).
"""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, DbDep
from app.core.rate_limit import enforce
from app.domain.app_controller import get_app_controller
from app.domain.events import CH_DONATION_COMPLETED, DomainEvent
from app.domain.exceptions import PaymentFailedException
from app.domain.payment_processor import MockPaymentProcessor
from app.models.donation import Donation, DonationRecord, DonationStatus
from app.schemas.common import DonationIn, DonationOut

router = APIRouter(prefix="/donations", tags=["donations"])

# Single concrete adapter for now. Swap for FailingPaymentProcessor in tests
# to verify the failure path from SRS Figure 6.
_processor = MockPaymentProcessor()


@router.post("", response_model=DonationOut, status_code=status.HTTP_201_CREATED)
async def create_donation(
    payload: DonationIn, owner: CurrentPetOwnerDep, db: DbDep
) -> DonationOut:
    # Anti-spam: cap donation attempts per account (also limits card-testing
    # abuse against the payment processor).
    enforce("donation_create", str(owner.id), max_requests=10, window_seconds=3600)
    donation = Donation(
        pet_owner_id=owner.id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        recurring=payload.recurring,
        status=DonationStatus.PENDING,
    )
    db.add(donation)
    await db.flush()  # need donation.id for the FK on the record

    try:
        result = _processor.charge(
            amount_cents=payload.amount_cents,
            currency=payload.currency,
            donor_label=owner.full_name,
        )
    except PaymentFailedException:
        donation.status = DonationStatus.FAILED
        await db.commit()
        raise

    record = DonationRecord(
        donation_id=donation.id,
        transaction_ref=result.transaction_ref,
        provider=result.provider,
        amount_cents=result.amount_cents,
        currency=result.currency,
        final_status=result.final_status,
        processed_at=result.processed_at,
    )
    donation.status = DonationStatus.SUCCEEDED
    db.add(record)
    await db.commit()
    await db.refresh(donation)
    await db.refresh(record)

    get_app_controller().event_bus.publish(
        DomainEvent(
            channel=CH_DONATION_COMPLETED,
            payload={
                "donation_id": str(donation.id),
                "amount": donation.amount_cents,
                "ref": record.transaction_ref,
            },
        )
    )

    return DonationOut(
        id=donation.id,
        amount_cents=donation.amount_cents,
        currency=donation.currency,
        recurring=donation.recurring,
        status=donation.status.value,
        transaction_ref=record.transaction_ref,
        processed_at=record.processed_at,
    )


@router.get("", response_model=list[DonationOut])
async def list_donations(account: CurrentAccountDep, db: DbDep) -> list[DonationOut]:
    """Pet Owners see their own donations; Veterinary Experts see every
    succeeded donation for verification (SRS §7.5)."""
    from sqlalchemy.orm import selectinload

    from app.models.account import PetOwner

    stmt = select(Donation).options(selectinload(Donation.record))
    if isinstance(account, PetOwner):
        stmt = stmt.where(Donation.pet_owner_id == account.id)
    else:
        stmt = stmt.where(Donation.status == DonationStatus.SUCCEEDED)
    rows = await db.scalars(stmt.order_by(Donation.created_at.desc()))
    out = []
    for d in rows:
        out.append(
            DonationOut(
                id=d.id,
                amount_cents=d.amount_cents,
                currency=d.currency,
                recurring=d.recurring,
                status=d.status.value,
                transaction_ref=d.record.transaction_ref if d.record else None,
                processed_at=d.record.processed_at if d.record else None,
            )
        )
    return out
