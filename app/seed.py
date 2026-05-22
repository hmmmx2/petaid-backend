"""Seed demo data — mirrors the reference prototype's core/90-seed.js.

Idempotent: re-running is safe. All eight SRS §7 scenarios can be walked
through end-to-end against the data this lays down.

Demo accounts (pre-verified):
    Pet Owner    alwin@petaid.com   / pet123
    Vet Expert   kavitha@petaid.com / vet123   (MFA 123456)

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

OWNER_EMAIL = "alwin@petaid.com"
OWNER_PASSWORD = "pet123"
VET_EMAIL = "kavitha@petaid.com"
VET_PASSWORD = "vet123"
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
            full_name="Alwin Jing Xue Tay", initials="AT", email_verified=True
        )
        vet = VeterinaryExpert(
            full_name="Kavitha Subramaniam", initials="KS", email_verified=True
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
        pt_dog = PetType(name="Dog", description="Canine companions",
                         icon_emoji="🐕", icon_bg="#FEE3D8", sort_order=1)
        pt_cat = PetType(name="Cat", description="Feline companions",
                         icon_emoji="🐈", icon_bg="#F8EDCF", sort_order=2)
        pt_rabbit = PetType(name="Rabbit", description="Domestic rabbits",
                            icon_emoji="🐇", icon_bg="#ECECEC", sort_order=3)
        db.add_all([pt_dog, pt_cat, pt_rabbit])
        await db.flush()

        # --- Pets ------------------------------------------------------ #
        pets = [
            Pet(owner_id=owner.id, pet_type_id=pt_dog.id, name="Mochi",
                breed="Golden Retriever", age_years=3,
                health_notes="Friendly; mild hip sensitivity."),
            Pet(owner_id=owner.id, pet_type_id=pt_cat.id, name="Luna",
                breed="Tabby", age_years=2, health_notes="Indoor only."),
            Pet(owner_id=owner.id, pet_type_id=pt_rabbit.id, name="Biscuit",
                breed="Holland Lop", age_years=1, health_notes=""),
        ]
        db.add_all(pets)

        # --- Resources (4 published, 1 draft) -------------------------- #
        r_cpr = Resource(pet_type_id=pt_dog.id, author_id=vet.id,
                         title="Dog CPR Step-by-Step (Video)", content_type="video",
                         media_path="https://media.petaid.app/dog-cpr.mp4",
                         status=ResourceStatus.PUBLISHED)
        r_poison = Resource(pet_type_id=pt_cat.id, author_id=vet.id,
                            title="Cat Poisoning Reference Guide", content_type="pdf",
                            media_path="https://media.petaid.app/cat-poisoning.pdf",
                            status=ResourceStatus.PUBLISHED)
        r_wound = Resource(pet_type_id=pt_rabbit.id, author_id=vet.id,
                           title="Rabbit Wound Care Photo Set", content_type="images",
                           media_path="https://media.petaid.app/rabbit-wound.png",
                           status=ResourceStatus.PUBLISHED)
        r_heat = Resource(pet_type_id=pt_dog.id, author_id=vet.id,
                          title="Heat-Stroke Triage Reference", content_type="pdf",
                          media_path="https://media.petaid.app/heatstroke.pdf",
                          status=ResourceStatus.PUBLISHED)
        r_bee = Resource(pet_type_id=pt_dog.id, author_id=vet.id,
                         title="Bee-Sting Response Draft", content_type="pdf",
                         media_path="https://media.petaid.app/bee-sting.pdf",
                         status=ResourceStatus.DRAFT)
        db.add_all([r_cpr, r_poison, r_wound, r_heat, r_bee])
        await db.flush()

        # --- First Aid Guidance (5 protocols) -------------------------- #
        guidance = [
            FirstAidGuidance(
                pet_type_id=pt_dog.id, author_id=vet.id,
                title="Dog CPR — Basic Compression", emergency_type="cardiac",
                summary="Restart circulation for a dog in cardiac arrest.",
                steps=[
                    "Place dog on a firm flat surface, right side down.",
                    "Locate the heart just behind the elbow on the left side.",
                    "Compress the chest one-third its width at 100–120 compressions per minute.",
                    "After 30 compressions, give 2 rescue breaths through the nose.",
                    "Continue cycles until a vet takes over or breathing resumes.",
                ],
                resources=[r_cpr],
            ),
            FirstAidGuidance(
                pet_type_id=pt_cat.id, author_id=vet.id,
                title="Suspected Poisoning — Cat", emergency_type="poisoning",
                summary="Stabilise a cat that may have ingested a toxin.",
                steps=[
                    "Identify the substance if possible. Save the packaging.",
                    "Do NOT induce vomiting unless explicitly advised by a vet.",
                    "Call the ASPCA poison line: 1-888-426-4435.",
                    "Keep the cat warm, calm, and contained.",
                    "Take the substance label with you to the clinic.",
                ],
                resources=[r_poison],
            ),
            FirstAidGuidance(
                pet_type_id=pt_dog.id, author_id=vet.id,
                title="Bleeding Wound — Pressure & Bandage", emergency_type="bleeding",
                summary="Control external bleeding before transport.",
                steps=[
                    "Apply direct firm pressure with a clean cloth.",
                    "Elevate the limb above heart level if no fracture is suspected.",
                    "Maintain pressure for at least 3 minutes without lifting.",
                    "Wrap with gauze and self-adhering bandage; do not over-tighten.",
                    "Transport to a vet if bleeding persists beyond 5 minutes.",
                ],
                resources=[r_wound],
            ),
            FirstAidGuidance(
                pet_type_id=pt_dog.id, author_id=vet.id,
                title="Heat Stroke Cooling Protocol", emergency_type="heatstroke",
                summary="Cool an overheated dog safely.",
                steps=[
                    "Move to a cool, shaded area immediately.",
                    "Wet fur with cool (not cold) water.",
                    "Direct a fan at the wet body.",
                    "Offer small amounts of cool water — do not force.",
                    "Transport to a vet even if recovery appears complete.",
                ],
                resources=[r_heat],
            ),
            FirstAidGuidance(
                pet_type_id=pt_dog.id, author_id=vet.id,
                title="Choking — Heimlich for Dogs", emergency_type="choking",
                summary="Clear an airway obstruction in a choking dog.",
                steps=[
                    "Open the mouth and look for a visible obstruction.",
                    "Sweep finger only if object is clearly reachable.",
                    "For small dogs: hold upside down, sharp pats between shoulder blades.",
                    "For large dogs: stand behind, squeeze just below the rib cage upward.",
                    "Re-check airway after each attempt.",
                ],
            ),
        ]
        db.add_all(guidance)
        await db.flush()

        # --- Quizzes --------------------------------------------------- #
        quiz_cpr = Quiz(
            resource_id=r_cpr.id, title="Dog CPR Basics", passing_score=70,
            questions=[
                {"prompt": "How many compressions per minute?",
                 "options": ["60–80", "100–120", "160–180"], "answer_index": 1},
                {"prompt": "When can you stop CPR?",
                 "options": ["After 1 minute", "Vet takes over or breathing returns", "Never"],
                 "answer_index": 1},
                {"prompt": "Where do you compress?",
                 "options": ["Centre of belly", "Behind elbow, left side", "Right hip"],
                 "answer_index": 1},
            ],
        )
        quiz_poison = Quiz(
            resource_id=r_poison.id, title="Cat Poisoning Triage", passing_score=70,
            questions=[
                {"prompt": "Should you induce vomiting first?",
                 "options": ["Always", "Only if vet directs", "Never if alkaline"],
                 "answer_index": 1},
                {"prompt": "What should you bring to the clinic?",
                 "options": ["Just the cat", "Cat + substance packaging", "Nothing"],
                 "answer_index": 1},
            ],
        )
        quiz_heat = Quiz(
            resource_id=r_heat.id, title="Heat-Stroke Response", passing_score=70,
            questions=[
                {"prompt": "What temperature water do you use?",
                 "options": ["Ice cold", "Cool", "Warm"], "answer_index": 1},
                {"prompt": "Can you skip the vet if your dog seems fine?",
                 "options": ["Yes", "No — always go in"], "answer_index": 1},
            ],
        )
        db.add_all([quiz_cpr, quiz_poison, quiz_heat])
        await db.flush()

        # --- Quiz attempts --------------------------------------------- #
        db.add(QuizAttempt(pet_owner_id=owner.id, quiz_id=quiz_cpr.id,
                           score_pct=100, passed=True, answers=[1, 1, 1],
                           completed_at=now - timedelta(days=7)))
        db.add(QuizAttempt(pet_owner_id=owner.id, quiz_id=quiz_poison.id,
                           score_pct=80, passed=True, answers=[1, 1],
                           completed_at=now - timedelta(days=2)))

        # --- Inquiries: one responded, one pending --------------------- #
        responded = Inquiry(
            pet_owner_id=owner.id, assigned_vet_id=vet.id,
            subject="Mochi licking paw pad",
            question="Mochi has been licking his paw pad. Should I bandage it?",
            response="Apply a thin layer of pet-safe antiseptic ointment twice daily. "
            "If swelling appears within 48h, bring him in for a check.",
            status=InquiryStatus.RESPONDED,
            submitted_at=now - timedelta(days=3),
            responded_at=now - timedelta(days=2),
        )
        pending = Inquiry(
            pet_owner_id=owner.id,
            subject="Luna refused dinner",
            question="Luna refused dinner tonight, is this serious?",
            status=InquiryStatus.PENDING,
            submitted_at=now - timedelta(hours=5),
        )
        db.add_all([responded, pending])

        # --- Chat ------------------------------------------------------ #
        db.add(Chat(
            pet_owner_id=owner.id, vet_id=vet.id,
            subject="Quick follow-up on Mochi's paw",
            status=ChatStatus.ACTIVE, started_at=now - timedelta(hours=2),
        ))

        # --- Donation (composed immutable record) ---------------------- #
        donation = Donation(pet_owner_id=owner.id, amount_cents=2500,
                            currency="USD", status=DonationStatus.SUCCEEDED)
        db.add(donation)
        await db.flush()
        db.add(DonationRecord(
            donation_id=donation.id, transaction_ref="TXN-SEEDED0000001",
            provider="MockProvider", amount_cents=2500, currency="USD",
            final_status="succeeded", processed_at=now - timedelta(days=1),
        ))

        # --- Feedback (composed entry) --------------------------------- #
        feedback = Feedback(submitter_id=owner.id,
                            target_type=FeedbackTargetType.RESOURCE,
                            target_id=r_cpr.id, flagged=False)
        db.add(feedback)
        await db.flush()
        db.add(FeedbackEntry(feedback_id=feedback.id, rating=5,
                             comment="Saved Mochi's life — clear, calm steps."))

        await db.commit()
        logger.info("Seed complete.")
        logger.info("  Pet Owner login : %s / %s", OWNER_EMAIL, OWNER_PASSWORD)
        logger.info("  Vet Expert login: %s / %s  (MFA: %s)", VET_EMAIL, VET_PASSWORD, VET_MFA_CODE)


async def _main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
