"""Quiz endpoints (SRS 7.4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep
from app.domain.exceptions import InvalidInputException, NotFoundException
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


@router.get("/attempts", response_model=list[QuizAttemptOut])
async def list_my_attempts(owner: CurrentPetOwnerDep, db: DbDep) -> list[QuizAttemptOut]:
    """The signed-in Pet Owner's own quiz attempts (newest first).

    Declared before ``/{quiz_id}`` so the literal path isn't parsed as a UUID.
    Used by the dashboard to show a per-quiz best score.
    """
    rows = await db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.pet_owner_id == owner.id)
        .order_by(QuizAttempt.completed_at.desc())
    )
    return [
        QuizAttemptOut(
            id=a.id,
            quiz_id=a.quiz_id,
            score_pct=a.score_pct,
            passed=a.passed,
            completed_at=a.completed_at,
        )
        for a in rows
    ]


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
) -> QuizAttemptOut:
    """Score the attempt via :meth:`Quiz.evaluate` (SRS 4.1.4).

    The submission must answer every question exactly once — a partial answer
    list is rejected rather than silently scored as wrong, so a truncated or
    malformed request never produces a misleading score.
    """
    quiz = await db.get(Quiz, quiz_id)
    if quiz is None:
        raise NotFoundException("Quiz")
    expected = len(quiz.questions)
    if len(payload.answers) != expected:
        raise InvalidInputException(
            "answers",
            f"Expected {expected} answer(s) but received {len(payload.answers)}.",
        )
    score, passed, per_question = quiz.evaluate(payload.answers)
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
    return QuizAttemptOut(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        score_pct=attempt.score_pct,
        passed=attempt.passed,
        completed_at=attempt.completed_at,
        per_question=per_question,
    )
