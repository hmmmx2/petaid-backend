"""Dashboard hierarchy — Template Method pattern (SRS 5.2.2).

``Dashboard`` defines the skeleton ``render()`` operation. Concrete
subclasses :class:`PetOwnerDashboard` and :class:`VeterinaryExpertDashboard`
override the abstract step methods to produce role-specific panels. The
shared assembly logic — header, navigation hints, error envelope — lives
in the base class so subclasses cannot accidentally diverge.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.events import EventBus
from app.models.account import Account, PetOwner, VeterinaryExpert
from app.models.chat import Chat, ChatStatus
from app.models.donation import Donation, DonationRecord, DonationStatus
from app.models.feedback import Feedback
from app.models.first_aid import FirstAidGuidance
from app.models.inquiry import Inquiry, InquiryStatus
from app.models.pet import Pet
from app.models.quiz import QuizAttempt
from app.models.resource import Resource, ResourceStatus


# --------------------------------------------------------------------------- #
# Abstract base                                                               #
# --------------------------------------------------------------------------- #
class Dashboard(ABC):
    """Skeleton of the role-specific dashboard.

    ``render()`` is the template method (non-virtual). Subclasses must
    provide :meth:`_panels` which returns the role-specific payload.
    """

    def __init__(
        self, *, account: Account, db: AsyncSession, event_bus: EventBus
    ) -> None:
        self._account = account
        self._db = db
        self._event_bus = event_bus

    async def render(self) -> dict[str, Any]:
        """Return the JSON-serialisable dashboard payload.

        The structure is intentionally common across roles:

            {
                "user": {...},
                "role": "pet_owner" | "veterinary_expert",
                "panels": {...},
            }
        """
        return {
            "user": self._user_summary(),
            "role": self._account.role,
            "panels": await self._panels(),
        }

    def _user_summary(self) -> dict[str, Any]:
        return {
            "id": str(self._account.id),
            "full_name": self._account.full_name,
            "initials": self._account.initials,
            "role": self._account.role,
            "display_name": self._account.display_name(),
        }

    @abstractmethod
    async def _panels(self) -> dict[str, Any]:
        """Return role-specific panels (see subclass docstrings)."""


# --------------------------------------------------------------------------- #
# Pet Owner Dashboard                                                         #
# --------------------------------------------------------------------------- #
class PetOwnerDashboard(Dashboard):
    """Renders the Pet Owner view (SRS 3.3.3 + Assignment 1 §8.1)."""

    async def _panels(self) -> dict[str, Any]:
        assert isinstance(self._account, PetOwner)
        owner_id = self._account.id

        pets = await self._load_pets(owner_id)
        attempts = await self._load_attempts(owner_id)
        chats = await self._load_chats(owner_id)
        guidance_count = await self._guidance_count_this_month(owner_id)
        recent_resources = await self._recent_published_resources(limit=5)

        avg_score = (
            round(sum(a.score_pct for a in attempts) / len(attempts)) if attempts else 0
        )
        preparedness = self._preparedness_pct(avg_score, len(pets), len(attempts))

        return {
            "pets": [self._pet_payload(p) for p in pets],
            "stats": {
                "quiz_avg_score": avg_score,
                "guidance_sessions_this_month": guidance_count,
                "preparedness_pct": preparedness,
            },
            "activity": self._activity_series(attempts, chats),
            "resources": [self._resource_payload(r) for r in recent_resources],
            "chats": [self._chat_payload(c) for c in chats[:4]],
            "readiness": self._readiness_from_attempts(attempts),
            "reminders": [],  # populated by a dedicated reminders module — out of A3 scope
        }

    # --- queries ----------------------------------------------------- #
    async def _load_pets(self, owner_id: uuid.UUID) -> list[Pet]:
        rows = await self._db.scalars(
            select(Pet).where(Pet.owner_id == owner_id).order_by(Pet.created_at)
        )
        return list(rows)

    async def _load_attempts(self, owner_id: uuid.UUID) -> list[QuizAttempt]:
        rows = await self._db.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.pet_owner_id == owner_id)
            .order_by(QuizAttempt.completed_at)
        )
        return list(rows)

    async def _load_chats(self, owner_id: uuid.UUID) -> list[Chat]:
        rows = await self._db.scalars(
            select(Chat)
            .where(Chat.pet_owner_id == owner_id)
            .order_by(Chat.started_at.desc())
        )
        return list(rows)

    async def _guidance_count_this_month(self, owner_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # A "guidance session" is approximated by inquiries + chats this month
        # so the figure is meaningful even without a dedicated session table.
        inquiries = await self._db.scalar(
            select(func.count())
            .select_from(Inquiry)
            .where(Inquiry.pet_owner_id == owner_id, Inquiry.submitted_at >= month_start)
        ) or 0
        chats = await self._db.scalar(
            select(func.count())
            .select_from(Chat)
            .where(Chat.pet_owner_id == owner_id, Chat.started_at >= month_start)
        ) or 0
        return int(inquiries) + int(chats)

    async def _recent_published_resources(self, *, limit: int) -> list[Resource]:
        rows = await self._db.scalars(
            select(Resource)
            .where(Resource.status == ResourceStatus.PUBLISHED)
            .order_by(Resource.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    # --- payload helpers --------------------------------------------- #
    @staticmethod
    def _pet_payload(p: Pet) -> dict[str, Any]:
        return {
            "id": str(p.id),
            "name": p.name,
            "breed": p.breed,
            "age_years": p.age_years,
            "pet_type": p.pet_type.name if p.pet_type else "",
            "icon_emoji": p.pet_type.icon_emoji if p.pet_type else "🐾",
            "icon_bg": p.pet_type.icon_bg if p.pet_type else "#F5F5F4",
        }

    @staticmethod
    def _resource_payload(r: Resource) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "title": r.title,
            "kind": r.content_type,
            "status": "new",  # client-facing label
            "pet_type": r.pet_type.name if r.pet_type else "",
        }

    @staticmethod
    def _chat_payload(c: Chat) -> dict[str, Any]:
        counterpart_name = c.vet.full_name if c.vet else "Unassigned vet"
        counterpart_initials = c.vet.initials if c.vet else "VT"
        return {
            "id": str(c.id),
            "counterpart_name": counterpart_name,
            "counterpart_initials": counterpart_initials,
            "counterpart_bg": "#E1F5EE",
            "counterpart_fg": "#085041",
            "last_message_at": c.started_at.isoformat(),
            "last_preview": c.subject or "(no subject)",
            "unread": c.status == ChatStatus.INITIATED,
        }

    def _activity_series(
        self, attempts: list[QuizAttempt], chats: list[Chat]
    ) -> dict[str, Any]:
        """Bucket the last 4 months and compute the trend."""
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        buckets: list[tuple[str, datetime, datetime]] = []
        cursor = month_start
        for _ in range(4):
            start = (cursor - timedelta(days=1)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            buckets.insert(0, (start.strftime("%b"), start, cursor))
            cursor = start

        points = []
        for label, start, end in buckets:
            attempts_in_range = [a for a in attempts if start <= a.completed_at < end]
            avg = (
                round(sum(a.score_pct for a in attempts_in_range) / len(attempts_in_range))
                if attempts_in_range
                else 0
            )
            sessions = sum(1 for c in chats if start <= c.started_at < end)
            points.append(
                {"label": label, "quiz_score": avg, "guidance_sessions": sessions}
            )

        first = next((p["quiz_score"] for p in points if p["quiz_score"]), 0)
        last = next((p["quiz_score"] for p in reversed(points) if p["quiz_score"]), 0)
        return {
            "points": points,
            "avg_score_trend_pct": max(0, last - first),
            "peak_label": "Week 3 · Peak score",
        }

    @staticmethod
    def _preparedness_pct(avg_score: int, pet_count: int, attempt_count: int) -> int:
        """Coarse, explainable readiness heuristic."""
        if pet_count == 0:
            return 0
        coverage = min(1.0, attempt_count / (pet_count * 3))
        return round((avg_score * 0.7 + 100 * coverage * 0.3))

    @staticmethod
    def _readiness_from_attempts(attempts: list[QuizAttempt]) -> list[dict[str, Any]]:
        """Group quiz attempts by their (resource-linked) topic and surface
        the best score per topic. Falls back to a static palette for empty
        data so the panel is never blank.
        """
        if not attempts:
            return [
                {"category": "Dog Emergency Care", "color": "#1D9E75", "score_pct": 0},
                {"category": "Cat First Aid", "color": "#EC6B52", "score_pct": 0},
                {"category": "Rabbit Safety", "color": "#EF9F27", "score_pct": 0},
                {"category": "Wound & Bleeding", "color": "#534AB7", "score_pct": 0},
                {"category": "Poisoning Response", "color": "#5DCAA5", "score_pct": 0},
            ]
        topics: dict[str, int] = {}
        for a in attempts:
            topic = a.quiz.title if a.quiz else "General"
            topics[topic] = max(topics.get(topic, 0), a.score_pct)
        palette = ["#1D9E75", "#EC6B52", "#EF9F27", "#534AB7", "#5DCAA5"]
        return [
            {"category": t, "color": palette[i % len(palette)], "score_pct": s}
            for i, (t, s) in enumerate(topics.items())
        ]


# --------------------------------------------------------------------------- #
# Veterinary Expert Dashboard                                                 #
# --------------------------------------------------------------------------- #
class VeterinaryExpertDashboard(Dashboard):
    """Renders the Veterinary Expert view (SRS 3.3.4)."""

    async def _panels(self) -> dict[str, Any]:
        assert isinstance(self._account, VeterinaryExpert)

        pending = await self._pending_inquiries()
        active_chats = await self._active_chats()
        draft_resources = await self._draft_resources()
        flagged_feedback = await self._flagged_feedback()
        recent_donations = await self._recent_donations()

        return {
            "pending_inquiries": pending,
            "active_chats": active_chats,
            "draft_resources": draft_resources,
            "flagged_feedback": flagged_feedback,
            "donations": recent_donations,
            "stats": {
                "pending_inquiries": len(pending),
                "active_chats": len(active_chats),
                "drafts_awaiting_approval": len(draft_resources),
            },
        }

    async def _pending_inquiries(self) -> list[dict[str, Any]]:
        rows = await self._db.scalars(
            select(Inquiry)
            .where(Inquiry.status == InquiryStatus.PENDING)
            .order_by(Inquiry.submitted_at.desc())
            .limit(20)
        )
        return [
            {
                "id": str(i.id),
                "subject": i.subject,
                "question": i.question,
                "submitted_at": i.submitted_at.isoformat(),
                "from": i.pet_owner.full_name if i.pet_owner else "Unknown",
            }
            for i in rows
        ]

    async def _active_chats(self) -> list[dict[str, Any]]:
        rows = await self._db.scalars(
            select(Chat)
            .where(Chat.status.in_([ChatStatus.INITIATED, ChatStatus.ACTIVE]))
            .order_by(Chat.started_at.desc())
            .limit(20)
        )
        return [
            {
                "id": str(c.id),
                "subject": c.subject,
                "status": c.status.value,
                "started_at": c.started_at.isoformat(),
                "owner": c.pet_owner.full_name if c.pet_owner else "Unknown",
            }
            for c in rows
        ]

    async def _draft_resources(self) -> list[dict[str, Any]]:
        rows = await self._db.scalars(
            select(Resource)
            .where(Resource.status == ResourceStatus.DRAFT)
            .order_by(Resource.created_at.desc())
            .limit(20)
        )
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "kind": r.content_type,
                "pet_type": r.pet_type.name if r.pet_type else "",
            }
            for r in rows
        ]

    async def _flagged_feedback(self) -> list[dict[str, Any]]:
        rows = await self._db.scalars(
            select(Feedback)
            .where(Feedback.flagged.is_(True))
            .options(selectinload(Feedback.entry))
            .order_by(Feedback.created_at.desc())
            .limit(20)
        )
        return [
            {
                "id": str(f.id),
                "target_type": f.target_type.value,
                "target_id": str(f.target_id),
                "rating": f.entry.rating if f.entry else None,
                "comment": f.entry.comment if f.entry else "",
                "from": f.submitter.full_name if f.submitter else "Unknown",
            }
            for f in rows
        ]

    async def _recent_donations(self) -> list[dict[str, Any]]:
        rows = await self._db.scalars(
            select(Donation)
            .where(Donation.status == DonationStatus.SUCCEEDED)
            .options(selectinload(Donation.record))
            .order_by(Donation.created_at.desc())
            .limit(20)
        )
        out = []
        for d in rows:
            record: DonationRecord | None = d.record
            out.append(
                {
                    "id": str(d.id),
                    "amount": d.amount_cents / 100,
                    "currency": d.currency,
                    "transaction_ref": record.transaction_ref if record else None,
                    "processed_at": record.processed_at.isoformat() if record else None,
                    "donor": d.pet_owner.full_name if d.pet_owner else "Unknown",
                }
            )
        return out


__all__ = ["Dashboard", "PetOwnerDashboard", "VeterinaryExpertDashboard"]
