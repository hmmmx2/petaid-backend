"""Feedback endpoints (SRS 7.7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentPetOwnerDep, CurrentVetDep, DbDep, require
from app.core.rate_limit import enforce
from app.domain.permissions import Permission
from app.domain.app_controller import get_app_controller
from app.domain.events import CH_FEEDBACK_FLAGGED, CH_FEEDBACK_SUBMITTED, DomainEvent
from app.models.feedback import Feedback, FeedbackEntry
from app.realtime.connection_manager import manager
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


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require(Permission.FEEDBACK_SUBMIT))])
async def submit_feedback(
    payload: FeedbackIn, owner: CurrentPetOwnerDep, db: DbDep
) -> FeedbackOut:
    # Anti-spam: cap feedback submissions per owner.
    enforce("feedback_create", str(owner.id), max_requests=20, window_seconds=3600)
    # UML: Feedback targets a Resource. The FK preserves referential integrity.
    feedback = Feedback(
        submitter_id=owner.id,
        resource_id=payload.target_id,
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
        # Real-time alert to every active veterinary expert. Mirrors the
        # pool-broadcast pattern that start_chat uses for undirected chats —
        # the diagram's pushReviewAlert step is now actually delivered.
        await manager.send_to_role(
            "veterinary_expert",
            {
                "type": "feedback_flagged",
                "feedback_id": str(feedback.id),
                "resource_id": str(feedback.resource_id) if feedback.resource_id else None,
                "rating": entry.rating,
            },
        )
    return _to_out(feedback)


@router.get("", response_model=list[FeedbackOut], dependencies=[Depends(require(Permission.FEEDBACK_REVIEW))])
async def list_feedback(_vet: CurrentVetDep, db: DbDep) -> list[FeedbackOut]:
    rows = await db.scalars(
        select(Feedback)
        .options(selectinload(Feedback.entry))
        .order_by(Feedback.created_at.desc())
        .limit(50)
    )
    return [_to_out(f) for f in rows]
