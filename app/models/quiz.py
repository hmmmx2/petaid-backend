"""Quiz and QuizAttempt entities (SRS 3.3.15).

A :class:`Quiz` is linked to exactly one :class:`Resource` (its learning
material). The questions are stored as a JSON list to keep the data model
compact; the SRS 2.2.3 simplification justified collapsing
``QuizQuestion`` into a Quiz attribute.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Quiz(UUIDPkMixin, TimestampMixin, Base):
    """An interactive assessment linked to one Resource."""

    __tablename__ = "quizzes"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    passing_score: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # ``questions`` is a list of dicts of the form
    #     {"prompt": str, "options": [str, ...], "answer_index": int}
    questions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    resource = relationship("Resource", lazy="joined")
    attempts = relationship(
        "QuizAttempt", back_populates="quiz", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------ #
    # Behaviour — Quiz scores its own attempts (SRS 4.1.4)               #
    # ------------------------------------------------------------------ #
    def evaluate(self, answers: list[int]) -> tuple[int, bool]:
        """Return ``(score_pct, passed)`` for the supplied answer indices.

        ``answers`` must be the same length as :attr:`questions`. Out-of-
        range or missing answers are counted as wrong, never as an error,
        so the UI can always render a score.
        """
        if not self.questions:
            return 0, False
        correct = 0
        for q, a in zip(self.questions, answers):
            try:
                if int(a) == int(q["answer_index"]):
                    correct += 1
            except (KeyError, TypeError, ValueError):
                continue
        score = round(correct * 100 / len(self.questions))
        return score, score >= self.passing_score


class QuizAttempt(UUIDPkMixin, TimestampMixin, Base):
    """One Pet Owner's attempt at a :class:`Quiz`.

    The score is computed by ``Quiz.evaluate`` at submission time and
    persisted alongside the answer list for traceability.
    """

    __tablename__ = "quiz_attempts"

    pet_owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    score_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    answers: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    quiz = relationship("Quiz", back_populates="attempts")
    pet_owner = relationship("PetOwner", lazy="joined")
