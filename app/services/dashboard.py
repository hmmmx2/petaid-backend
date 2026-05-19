from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatThread
from app.models.pet import Pet
from app.models.quiz import QuizAttempt
from app.models.readiness import ReadinessCategory, UserReadiness
from app.models.reminder import Reminder
from app.models.resource import Resource, UserResource
from app.models.user import User
from app.schemas.dashboard import (
    ActivityPoint,
    ChatThreadOut,
    DashboardResponse,
    LearningActivity,
    PetOut,
    ReadinessOut,
    ReminderOut,
    ResourceOut,
    StatCards,
    UserSummary,
)


async def build_dashboard(db: AsyncSession, user: User) -> DashboardResponse:
    pets = list(
        await db.scalars(select(Pet).where(Pet.owner_id == user.id).order_by(Pet.created_at))
    )

    attempts = list(
        await db.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user.id)
            .order_by(QuizAttempt.completed_at)
        )
    )
    quizzes_count = len(attempts)
    quiz_avg = round(sum(a.score_pct for a in attempts) / quizzes_count) if attempts else 0

    threads = list(
        await db.scalars(
            select(ChatThread)
            .where(ChatThread.user_id == user.id)
            .order_by(ChatThread.last_message_at.desc())
        )
    )

    # Guidance sessions this month (using ChatThreads as a proxy; in real app would be its own table)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sessions_this_month = await db.scalar(
        select(func.count())
        .select_from(ChatThread)
        .where(ChatThread.user_id == user.id, ChatThread.last_message_at >= month_start)
    ) or 0

    readiness_rows = list(
        await db.scalars(
            select(UserReadiness)
            .where(UserReadiness.user_id == user.id)
            .options(selectinload(UserReadiness.category))
            .join(ReadinessCategory)
            .order_by(ReadinessCategory.sort_order)
        )
    )
    preparedness = (
        round(sum(r.score_pct for r in readiness_rows) / len(readiness_rows))
        if readiness_rows
        else 0
    )

    user_resources = list(
        await db.scalars(
            select(UserResource)
            .where(UserResource.user_id == user.id)
            .options(selectinload(UserResource.resource))
            .order_by(UserResource.created_at.desc())
            .limit(5)
        )
    )

    reminders = list(
        await db.scalars(
            select(Reminder)
            .where(Reminder.user_id == user.id, Reminder.due_at >= now - timedelta(days=1))
            .order_by(Reminder.due_at)
            .limit(5)
        )
    )

    # Build monthly activity buckets for the last 4 months
    months: list[tuple[str, datetime, datetime]] = []
    cursor = month_start
    for _ in range(4):
        start = (cursor - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        months.insert(0, (start.strftime("%b"), start, cursor))
        cursor = start

    points: list[ActivityPoint] = []
    for label, start, end in months:
        in_range = [a for a in attempts if start <= a.completed_at < end]
        avg = round(sum(a.score_pct for a in in_range) / len(in_range)) if in_range else 0
        sessions = sum(1 for t in threads if start <= t.last_message_at < end)
        points.append(ActivityPoint(label=label, quiz_score=avg, guidance_sessions=sessions))

    first_score = next((p.quiz_score for p in points if p.quiz_score), 0)
    last_score = next((p.quiz_score for p in reversed(points) if p.quiz_score), 0)
    trend = max(0, last_score - first_score)

    return DashboardResponse(
        user=UserSummary(
            id=user.id,
            full_name=user.full_name,
            initials=user.initials,
            role=user.role,
            pets_count=len(pets),
            quizzes_count=quizzes_count,
            chats_count=len(threads),
        ),
        pets=[PetOut.model_validate(p) for p in pets],
        stats=StatCards(
            quiz_avg_score=quiz_avg,
            guidance_sessions_this_month=int(sessions_this_month),
            preparedness_pct=preparedness,
        ),
        activity=LearningActivity(
            points=points,
            avg_score_trend_pct=trend,
            peak_label="Week 3 · Peak score",
        ),
        resources=[
            ResourceOut(
                id=ur.resource.id,
                title=ur.resource.title,
                kind=ur.resource.kind,
                status=ur.status,
            )
            for ur in user_resources
            if ur.resource is not None
        ],
        chats=[ChatThreadOut.model_validate(t) for t in threads[:4]],
        readiness=[
            ReadinessOut(
                category=r.category.name,
                color=r.category.color,
                score_pct=r.score_pct,
            )
            for r in readiness_rows
        ],
        reminders=[ReminderOut.model_validate(r) for r in reminders],
    )


__all__ = ["build_dashboard", "Resource"]
