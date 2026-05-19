"""Seed the database with Alwin's demo data matching the dashboard mockup.

Usage:
    python -m app.seed
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models.chat import ChatThread
from app.models.pet import Pet
from app.models.quiz import Quiz, QuizAttempt
from app.models.readiness import ReadinessCategory, UserReadiness
from app.models.reminder import Reminder
from app.models.resource import Resource, UserResource
from app.models.user import User

DEMO_EMAIL = "alwin@petaid.local"
DEMO_PASSWORD = "petaid-demo-2026"


async def seed() -> None:
    async with SessionLocal() as db:
        # idempotent: skip if Alwin exists
        existing = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing is not None:
            print(f"User {DEMO_EMAIL} already exists, skipping seed.")
            return

        now = datetime.now(timezone.utc)

        alwin = User(
            email=DEMO_EMAIL,
            full_name="Alwin Tay",
            initials="AT",
            role="Pet Owner",
            hashed_password=hash_password(DEMO_PASSWORD),
        )
        db.add(alwin)
        await db.flush()

        pets = [
            Pet(owner_id=alwin.id, name="Mochi", species="dog", breed="Golden",
                age_years=3, icon_emoji="🐕", icon_bg="#E1F5EE"),
            Pet(owner_id=alwin.id, name="Luna", species="cat", breed="Tabby",
                age_years=2, icon_emoji="🐈", icon_bg="#FDECEA"),
            Pet(owner_id=alwin.id, name="Biscuit", species="rabbit", breed="Rabbit",
                age_years=1, icon_emoji="🐇", icon_bg="#FAEEDA"),
        ]
        db.add_all(pets)

        quiz_definitions = [
            ("Dog Emergency Basics", "Dog Emergency Care"),
            ("Cat First Aid Essentials", "Cat First Aid"),
            ("Rabbit Safety 101", "Rabbit Safety"),
            ("Wound & Bleeding Response", "Wound & Bleeding"),
            ("Poisoning Response", "Poisoning Response"),
        ]
        quizzes = [Quiz(title=t, category=c, question_count=10) for t, c in quiz_definitions]
        db.add_all(quizzes)
        await db.flush()

        # 12 quiz attempts across the last 4 months → avg ~78%
        rng = random.Random(42)
        target_scores = [55, 62, 68, 71, 74, 78, 80, 82, 84, 86, 88, 91]
        for i, score in enumerate(target_scores):
            month_offset = 3 - (i // 3)  # spread across 4 months, recent first
            completed = now - timedelta(days=month_offset * 28 + rng.randint(0, 25))
            db.add(QuizAttempt(
                user_id=alwin.id,
                quiz_id=rng.choice(quizzes).id,
                score_pct=score,
                completed_at=completed,
            ))

        # 9 guidance sessions this month: encoded as 4 chat threads + 5 historical ones we track via creation.
        # The dashboard surfaces threads as chats and counts month-anchored threads as "guidance sessions".
        threads = [
            ChatThread(user_id=alwin.id, counterpart_name="Dr. Kavitha",
                       counterpart_initials="DK", counterpart_bg="#E1F5EE", counterpart_fg="#085041",
                       last_message_at=now.replace(hour=10, minute=30, second=0, microsecond=0),
                       last_preview="Mochi's paw looks fine, apply ointment tonight…",
                       unread=True),
            ChatThread(user_id=alwin.id, counterpart_name="VetTeam Support",
                       counterpart_initials="VT", counterpart_bg="#FDECEA", counterpart_fg="#b84c36",
                       last_message_at=now - timedelta(days=2),
                       last_preview="Your inquiry about Luna has been reviewed…",
                       unread=False),
            ChatThread(user_id=alwin.id, counterpart_name="Dr. Rania",
                       counterpart_initials="DR", counterpart_bg="#EEEDFE", counterpart_fg="#3C3489",
                       last_message_at=now - timedelta(days=3),
                       last_preview="Follow-up on Biscuit — diet improving well",
                       unread=False),
            ChatThread(user_id=alwin.id, counterpart_name="PetAid Alerts",
                       counterpart_initials="PA", counterpart_bg="#F5F5F4", counterpart_fg="#515c67",
                       last_message_at=now - timedelta(days=20),
                       last_preview="New resource: Rabbit emergency handling guide",
                       unread=False),
        ]
        # add 5 extra "guidance session" threads dated this month for the stat card
        for n in range(5):
            threads.append(ChatThread(
                user_id=alwin.id,
                counterpart_name=f"VetCare Session {n+1}",
                counterpart_initials="VC",
                counterpart_bg="#F5F5F4",
                counterpart_fg="#515c67",
                last_message_at=now - timedelta(days=rng.randint(1, 25)),
                last_preview="Session summary uploaded.",
                unread=False,
            ))
        db.add_all(threads)

        resources = [
            Resource(title="Dog CPR Step-by-Step Video", kind="video", category="Dog Emergency Care"),
            Resource(title="Cat Poisoning Guide (PDF)", kind="pdf", category="Poisoning Response"),
            Resource(title="Rabbit Wound Care Images", kind="images", category="Rabbit Safety"),
        ]
        db.add_all(resources)
        await db.flush()

        statuses = ["watched", "in_progress", "new"]
        for r, status in zip(resources, statuses):
            db.add(UserResource(user_id=alwin.id, resource_id=r.id, status=status))

        categories = [
            ReadinessCategory(name="Dog Emergency Care", color="#1D9E75", sort_order=1),
            ReadinessCategory(name="Cat First Aid", color="#EC6B52", sort_order=2),
            ReadinessCategory(name="Rabbit Safety", color="#EF9F27", sort_order=3),
            ReadinessCategory(name="Wound & Bleeding", color="#534AB7", sort_order=4),
            ReadinessCategory(name="Poisoning Response", color="#5DCAA5", sort_order=5),
        ]
        db.add_all(categories)
        await db.flush()

        readiness_scores = [82, 61, 38, 74, 55]
        for cat, score in zip(categories, readiness_scores):
            db.add(UserReadiness(user_id=alwin.id, category_id=cat.id, score_pct=score))

        db.add_all([
            Reminder(
                user_id=alwin.id,
                title="Retake Cat Quiz",
                body="Improve your 61% cat first aid score",
                kind="quiz",
                due_at=now + timedelta(days=1),
                icon_color="#EC6B52",
            ),
            Reminder(
                user_id=alwin.id,
                title="New Resource Ready",
                body="Rabbit wound care — approved by vet expert",
                kind="resource",
                due_at=now + timedelta(days=30),
                icon_color="#1D9E75",
            ),
        ])

        await db.commit()
        print(f"Seeded user {DEMO_EMAIL} / password {DEMO_PASSWORD}")


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
