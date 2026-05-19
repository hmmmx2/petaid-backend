"""Inquiry endpoints (SRS 7.2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from sqlalchemy import or_, select

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep
from app.domain.app_controller import get_app_controller
from app.domain.events import CH_INQUIRY_RESPONDED, CH_INQUIRY_SUBMITTED, DomainEvent
from app.domain.exceptions import InvalidInputException, NotFoundException
from app.models.account import PetOwner, VeterinaryExpert
from app.models.inquiry import Inquiry, InquiryStatus
from app.schemas.common import InquiryIn, InquiryOut, InquiryResponseIn

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED)
async def submit_inquiry(
    payload: InquiryIn, owner: CurrentPetOwnerDep, db: DbDep
) -> Inquiry:
    inquiry = Inquiry(
        pet_owner_id=owner.id,
        subject=payload.subject,
        question=payload.question,
        status=InquiryStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(inquiry)
    await db.commit()
    await db.refresh(inquiry)

    get_app_controller().event_bus.publish(
        DomainEvent(
            channel=CH_INQUIRY_SUBMITTED,
            payload={"inquiry_id": str(inquiry.id), "from": owner.full_name},
        )
    )
    return inquiry


@router.get("", response_model=list[InquiryOut])
async def list_inquiries(account: CurrentAccountDep, db: DbDep) -> list[Inquiry]:
    """Pet Owners see their own; Vets see pending + their answered."""
    if isinstance(account, PetOwner):
        stmt = select(Inquiry).where(Inquiry.pet_owner_id == account.id)
    elif isinstance(account, VeterinaryExpert):
        stmt = select(Inquiry).where(
            or_(
                Inquiry.status == InquiryStatus.PENDING,
                Inquiry.assigned_vet_id == account.id,
            )
        )
    else:
        return []
    rows = await db.scalars(stmt.order_by(Inquiry.submitted_at.desc()))
    return list(rows)


@router.post("/{inquiry_id}/respond", response_model=InquiryOut)
async def respond_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryResponseIn,
    vet: CurrentVetDep,
    db: DbDep,
) -> Inquiry:
    inquiry = await db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise NotFoundException("Inquiry")
    try:
        inquiry.respond(vet_id=vet.id, response_text=payload.response)
    except ValueError as exc:
        raise InvalidInputException("response", str(exc)) from exc
    await db.commit()
    await db.refresh(inquiry)

    get_app_controller().event_bus.publish(
        DomainEvent(
            channel=CH_INQUIRY_RESPONDED,
            payload={"inquiry_id": str(inquiry.id), "vet": vet.full_name},
        )
    )
    return inquiry


@router.post("/{inquiry_id}/close", response_model=InquiryOut)
async def close_inquiry(
    inquiry_id: uuid.UUID, _account: CurrentAccountDep, db: DbDep
) -> Inquiry:
    inquiry = await db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise NotFoundException("Inquiry")
    inquiry.close()
    await db.commit()
    await db.refresh(inquiry)
    return inquiry
