"""Seed demo data — Alwin (Pet Owner) and Dr. Kavitha (Vet Expert).

Idempotent: re-running is safe. The scenarios in SRS Section 7 can be
walked through end-to-end against the data this script lays down.

Usage:
    python -m app.seed
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.account import PetOwner, VeterinaryExpert
from app.models.chat import Chat, ChatStatus
from app.models.credentials import UserCredentials
from app.models.donation import Donation, DonationRecord, DonationStatus
from app.models.feedback import Feedback, FeedbackEntry, FeedbackTargetType
from app.models.first_aid import FirstAidGuidance
from app.models.inquiry import Inquiry, InquiryStatus
from app.models.pet import Pet
from app.models.pet_type import PetType
from app.models.quiz import Quiz, QuizAttempt
from app.models.resource import Resource, ResourceStatus

logger = logging.getLogger("petaid.seed")
logging.basicConfig(level=logging.INFO)

OWNER_EMAIL = "alwin@petaid.local"
OWNER_PASSWORD = "petaid-demo-2026"
VET_EMAIL = "vet@petaid.local"
VET_PASSWORD = "petaid-vet-2026"
VET_MFA_CODE = "123456"


async def create_schema() -> None:
    """Create tables for dev / first-run convenience.

    Production deployments should run ``alembic upgrade head`` instead.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed() -> None:
    await create_schema()

    async with SessionLocal() as db:
        existing = await db.scalar(
            select(UserCredentials).where(UserCredentials.email == OWNER_EMAIL)
        )
        if existing is not None:
            logger.info("Demo data already present — skipping seed.")
            return

        now = datetime.now(timezone.utc)

        # --- Actors ---------------------------------------------------- #
        owner = PetOwner(
            full_name="Alwin Tay", initials="AT", email_verified=True
        )
        vet = VeterinaryExpert(
            full_name="Dr. Kavitha Subramaniam", initials="KS", email_verified=True
        )
        db.add_all([owner, vet])
        await db.flush()

        db.add(
            UserCredentials(
                account_id=owner.id,
                email=OWNER_EMAIL,
                hashed_password=hash_password(OWNER_PASSWORD),
            )
        )
        db.add(
            UserCredentials(
                account_id=vet.id,
                email=VET_EMAIL,
                hashed_password=hash_password(VET_PASSWORD),
                mfa_enabled=True,
                mfa_secret=VET_MFA_CODE,
            )
        )

        # --- Pet Types ------------------------------------------------- #
        pt_dog = PetType(name="Dog", icon_emoji="🐕", icon_bg="#E1F5EE", sort_order=1)
        pt_cat = PetType(name="Cat", icon_emoji="🐈", icon_bg="#FDECEA", sort_order=2)
        pt_rabbit = PetType(name="Rabbit", icon_emoji="🐇", icon_bg="#FAEEDA", sort_order=3)
        db.add_all([pt_dog, pt_cat, pt_rabbit])
        await db.flush()

        # --- Pets (aggregated by Alwin) -------------------------------- #
        pets = [
            Pet(owner_id=owner.id, pet_type_id=pt_dog.id, name="Mochi", breed="Golden", age_years=3),
            Pet(owner_id=owner.id, pet_type_id=pt_cat.id, name="Luna", breed="Tabby", age_years=2),
            Pet(owner_id=owner.id, pet_type_id=pt_rabbit.id, name="Biscuit", breed="Holland Lop", age_years=1),
        ]
        db.add_all(pets)

        # --- Resources (published by the vet) -------------------------- #
        r_cpr = Resource(
            pet_type_id=pt_dog.id, author_id=vet.id,
            title="Dog CPR Step-by-Step Video", content_type="video",
            media_path="https://media.petaid.local/dog-cpr.mp4",
            status=ResourceStatus.PUBLISHED,
        )
        r_poison = Resource(
            pet_type_id=pt_cat.id, author_id=vet.id,
            title="Cat Poisoning Guide", content_type="pdf",
            media_path="https://media.petaid.local/cat-poisoning.pdf",
            status=ResourceStatus.PUBLISHED,
        )
        r_wound = Resource(
            pet_type_id=pt_rabbit.id, author_id=vet.id,
            title="Rabbit Wound Care Images", content_type="images",
            media_path="https://media.petaid.local/rabbit-wound.png",
            status=ResourceStatus.DRAFT,  # left in draft for the approval scenario
        )
        db.add_all([r_cpr, r_poison, r_wound])
        await db.flush()

        # --- First Aid Guidance ---------------------------------------- #
        guidance = [
            FirstAidGuidance(
                pet_type_id=pt_dog.id, author_id=vet.id,
                title="Dog Choking — Emergency Protocol",
                emergency_type="Choking",
                summary="Quick airway clearance for a choking dog.",
                steps=[
                    "Stay calm and keep the dog still.",
                    "Open the mouth gently and check for visible obstruction.",
                    "If visible, sweep with a finger — do not push the object deeper.",
                    "Perform back blows between shoulder blades up to five times.",
                    "If unconscious, begin CPR and call emergency vet immediately.",
                ],
            ),
            FirstAidGuidance(
                pet_type_id=pt_cat.id, author_id=vet.id,
                title="Cat Poisoning — First Response",
                emergency_type="Poisoning",
                summary="Stabilise the cat before transport to the clinic.",
                steps=[
                    "Identify and remove the toxic substance from reach.",
                    "Note packaging or remaining material to bring to the vet.",
                    "Do not induce vomiting unless instructed by a vet.",
                    "Keep the cat warm and quiet during transport.",
                    "Call the emergency vet line for product-specific guidance.",
                ],
            ),
        ]
        db.add_all(guidance)
        await db.flush()
        guidance[0].resources.append(r_cpr)
        guidance[1].resources.append(r_poison)

        # --- Quizzes --------------------------------------------------- #
        quiz_cpr = Quiz(
            resource_id=r_cpr.id,
            title="Dog CPR Basics",
            passing_score=60,
            questions=[
                {
                    "prompt": "How often should you perform compressions per minute?",
                    "options": ["30-50", "60-80", "100-120", "150-180"],
                    "answer_index": 2,
                },
                {
                    "prompt": "Where should you place your hands for a medium-sized dog?",
                    "options": [
                        "Over the abdomen",
                        "Highest point of the chest",
                        "On the neck",
                        "On the spine",
                    ],
                    "answer_index": 1,
                },
                {
                    "prompt": "When should you call the emergency vet?",
                    "options": [
                        "Only if compressions fail",
                        "Immediately, while administering CPR",
                        "After 30 minutes of CPR",
                        "Never — handle it yourself",
                    ],
                    "answer_index": 1,
                },
            ],
        )
        quiz_poison = Quiz(
            resource_id=r_poison.id,
            title="Cat Poisoning Response",
            passing_score=60,
            questions=[
                {
                    "prompt": "Should you induce vomiting if a cat ingested chocolate?",
                    "options": ["Always", "Only with vet instruction", "Never", "If under 5 minutes"],
                    "answer_index": 1,
                },
                {
                    "prompt": "What should you bring with you to the clinic?",
                    "options": ["Toys", "Packaging of the toxin", "Litter box", "Food bowl"],
                    "answer_index": 1,
                },
            ],
        )
        db.add_all([quiz_cpr, quiz_poison])
        await db.flush()

        # --- Quiz attempts (so the dashboard shows real numbers) ------- #
        rng_scores = [55, 68, 74, 78, 82, 88, 92]
        for i, score in enumerate(rng_scores):
            db.add(
                QuizAttempt(
                    pet_owner_id=owner.id,
                    quiz_id=quiz_cpr.id if i % 2 == 0 else quiz_poison.id,
                    score_pct=score,
                    passed=score >= 60,
                    answers=[1, 1, 1],
                    completed_at=now - timedelta(days=(7 - i) * 5),
                )
            )

        # --- Inquiry --------------------------------------------------- #
        db.add(
            Inquiry(
                pet_owner_id=owner.id,
                subject="Luna seems lethargic — non-urgent",
                question="Luna has been sleeping more than usual for the last 3 days. "
                "Eating fine. Should I be worried?",
                status=InquiryStatus.PENDING,
                submitted_at=now - timedelta(hours=6),
            )
        )

        # --- Chat ------------------------------------------------------ #
        chat = Chat(
            pet_owner_id=owner.id,
            vet_id=vet.id,
            subject="Quick follow-up on Mochi's paw",
            status=ChatStatus.ACTIVE,
            started_at=now - timedelta(hours=2),
        )
        db.add(chat)

        # --- Donation (with composed immutable record) ----------------- #
        donation = Donation(
            pet_owner_id=owner.id,
            amount_cents=2500,
            currency="USD",
            status=DonationStatus.SUCCEEDED,
        )
        db.add(donation)
        await db.flush()
        db.add(
            DonationRecord(
                donation_id=donation.id,
                transaction_ref="TXN-SEEDED0000001",
                provider="MockProvider",
                amount_cents=2500,
                currency="USD",
                final_status="succeeded",
                processed_at=now - timedelta(days=1),
            )
        )

        # --- Feedback (composed entry) --------------------------------- #
        feedback = Feedback(
            submitter_id=owner.id,
            target_type=FeedbackTargetType.RESOURCE,
            target_id=r_cpr.id,
            flagged=False,
        )
        db.add(feedback)
        await db.flush()
        db.add(
            FeedbackEntry(
                feedback_id=feedback.id,
                rating=5,
                comment="Saved Mochi's life — clear, calm steps.",
            )
        )

        await db.commit()
        logger.info("Seed complete.")
        logger.info("  Pet Owner login : %s / %s", OWNER_EMAIL, OWNER_PASSWORD)
        logger.info("  Vet Expert login: %s / %s  (MFA: %s)", VET_EMAIL, VET_PASSWORD, VET_MFA_CODE)


async def _main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
