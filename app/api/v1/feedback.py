"""Feedback endpoints (SRS 7.7)."""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentPetOwnerDep, CurrentVetDep, DbDep
from app.core.rate_limit import enforce
from app.domain.app_controller import get_app_controller
from app.domain.events import CH_FEEDBACK_FLAGGED, CH_FEEDBACK_SUBMITTED, DomainEvent
from app.models.feedback import Feedback, FeedbackEntry, FeedbackTargetType
from app.schemas.common import FeedbackIn, FeedbackOut

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _to_out(f: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=f.id,
        target_type=f.target_type.value,
        target_id=f.target_id,
        flagged=f.flagged,
        rating=f.entry.rating if f.entry else 0,
        comment=f.entry.comment if f.entry else "",
        created_at=f.created_at,
    )


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    payload: FeedbackIn, owner: CurrentPetOwnerDep, db: DbDep
) -> FeedbackOut:
    # Anti-spam: cap feedback submissions per owner.
    enforce("feedback_create", str(owner.id), max_requests=20, window_seconds=3600)
    feedback = Feedback(
        submitter_id=owner.id,
        target_type=FeedbackTargetType(payload.target_type),
        target_id=payload.target_id,
        flagged=payload.flagged,
    )
    db.add(feedback)
    await db.flush()

    entry = FeedbackEntry(
        feedback_id=feedback.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(feedback, attribute_names=["entry"])

    bus = get_app_controller().event_bus
    bus.publish(
        DomainEvent(
            channel=CH_FEEDBACK_SUBMITTED,
            payload={"feedback_id": str(feedback.id)},
        )
    )
    if feedback.flagged:
        bus.publish(
            DomainEvent(
                channel=CH_FEEDBACK_FLAGGED,
                payload={"feedback_id": str(feedback.id)},
            )
        )
    return _to_out(feedback)


@router.get("", response_model=list[FeedbackOut])
async def list_feedback(_vet: CurrentVetDep, db: DbDep) -> list[FeedbackOut]:
    rows = await db.scalars(
        select(Feedback)
        .options(selectinload(Feedback.entry))
        .order_by(Feedback.created_at.desc())
        .limit(50)
    )
    return [_to_out(f) for f in rows]
