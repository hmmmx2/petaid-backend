"""Quiz endpoints (SRS 7.4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep
from app.domain.exceptions import NotFoundException
from app.models.quiz import Quiz, QuizAttempt
from app.schemas.common import (
    QuizAttemptIn,
    QuizAttemptOut,
    QuizIn,
    QuizOut,
    QuizQuestion,
)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def _to_out(q: Quiz) -> QuizOut:
    """Hide the correct ``answer_index`` from Pet Owners — only the prompt
    and options should leave the server until a submission is graded.
    """
    return QuizOut(
        id=q.id,
        title=q.title,
        passing_score=q.passing_score,
        resource_id=q.resource_id,
        questions=[
            QuizQuestion(
                prompt=qq["prompt"],
                options=list(qq["options"]),
                answer_index=-1,
            )
            for qq in q.questions
        ],
    )


@router.get("", response_model=list[QuizOut])
async def list_quizzes(
    _account: CurrentAccountDep,
    db: DbDep,
    resource_id: uuid.UUID | None = None,
) -> list[QuizOut]:
    stmt = select(Quiz)
    if resource_id is not None:
        stmt = stmt.where(Quiz.resource_id == resource_id)
    rows = await db.scalars(stmt.order_by(Quiz.created_at))
    return [_to_out(q) for q in rows]


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: uuid.UUID, _account: CurrentAccountDep, db: DbDep
) -> QuizOut:
    q = await db.get(Quiz, quiz_id)
    if q is None:
        raise NotFoundException("Quiz")
    return _to_out(q)


@router.post("", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
async def create_quiz(payload: QuizIn, _vet: CurrentVetDep, db: DbDep) -> QuizOut:
    q = Quiz(
        title=payload.title,
        resource_id=payload.resource_id,
        passing_score=payload.passing_score,
        questions=[qq.model_dump() for qq in payload.questions],
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return _to_out(q)


@router.post(
    "/{quiz_id}/attempts",
    response_model=QuizAttemptOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_attempt(
    quiz_id: uuid.UUID,
    payload: QuizAttemptIn,
    owner: CurrentPetOwnerDep,
    db: DbDep,
) -> QuizAttempt:
    """Score the attempt via :meth:`Quiz.evaluate` (SRS 4.1.4)."""
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFoundException("Quiz")
    score, passed = quiz.evaluate(payload.answers)
    attempt = QuizAttempt(
        pet_owner_id=owner.id,
        quiz_id=quiz.id,
        score_pct=score,
        passed=passed,
        answers=list(payload.answers),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt
