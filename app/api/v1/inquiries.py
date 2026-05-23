"""Inquiry endpoints (SRS 7.2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep, require
from app.core.rate_limit import enforce
from app.domain.permissions import Permission
from app.domain.app_controller import get_app_controller
from app.domain.events import CH_INQUIRY_RESPONDED, CH_INQUIRY_SUBMITTED, DomainEvent
from app.domain.exceptions import (
    InvalidInputException,
    NotAuthorisedException,
    NotFoundException,
)
from app.models.account import PetOwner, VeterinaryExpert
from app.models.inquiry import Inquiry, InquiryStatus
from app.schemas.common import InquiryIn, InquiryOut, InquiryResponseIn

router = APIRouter(prefix="/inquiries", tags=["inquiries"])


@router.post("", response_model=InquiryOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require(Permission.INQUIRY_CREATE))])
async def submit_inquiry(
    payload: InquiryIn, owner: CurrentPetOwnerDep, db: DbDep
) -> Inquiry:
    # Anti-spam: cap inquiry submissions per owner.
    enforce("inquiry_create", str(owner.id), max_requests=10, window_seconds=3600)
    inquiry = Inquiry(
        pet_owner_id=owner.id,
        subject=payload.subject,
        question=payload.question,
        image_urls=list(payload.images),
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


@router.get("", response_model=list[InquiryOut], dependencies=[Depends(require(Permission.INQUIRY_VIEW))])
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


@router.post("/{inquiry_id}/respond", response_model=InquiryOut, dependencies=[Depends(require(Permission.INQUIRY_RESPOND))])
async def respond_inquiry(
    inquiry_id: uuid.UUID,
    payload: InquiryResponseIn,
    vet: CurrentVetDep,
    db: DbDep,
) -> Inquiry:
    inquiry = await db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise NotFoundException("Inquiry")
    # Claim-and-lock: any vet may pick up a still-unassigned inquiry, but once a
    # vet is assigned only that vet may respond again — closes the IDOR where any
    # vet could overwrite another's assignment/response.
    if inquiry.assigned_vet_id is not None and inquiry.assigned_vet_id != vet.id:
        raise NotAuthorisedException("This inquiry is assigned to another vet.")
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


@router.post("/{inquiry_id}/close", response_model=InquiryOut, dependencies=[Depends(require(Permission.INQUIRY_CLOSE))])
async def close_inquiry(
    inquiry_id: uuid.UUID, account: CurrentAccountDep, db: DbDep
) -> Inquiry:
    inquiry = await db.get(Inquiry, inquiry_id)
    if inquiry is None:
        raise NotFoundException("Inquiry")
    # Only a participant may close: the pet owner who raised it, or the vet who
    # was assigned to answer it. Prevents an IDOR where any authenticated
    # account closes an arbitrary inquiry by guessing its id.
    is_owner = isinstance(account, PetOwner) and inquiry.pet_owner_id == account.id
    is_assigned_vet = (
        isinstance(account, VeterinaryExpert)
        and inquiry.assigned_vet_id == account.id
    )
    if not (is_owner or is_assigned_vet):
        raise NotAuthorisedException("You cannot close this inquiry.")
    inquiry.close()
    await db.commit()
    await db.refresh(inquiry)
    return inquiry
