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
    def evaluate(self, answers: list[int]) -> tuple[int, bool, list[dict]]:
        """Return ``(score_pct, passed, per_question)`` for the answer indices.

        ``answers`` should be the same length as :attr:`questions` (the API
        layer validates this); out-of-range or missing answers are counted as
        wrong, never as an error, so the UI can always render a result.

        ``per_question`` is a list of ``{prompt, ok, given, correct}`` dicts
        (option *text*, not indices) so the client can render per-question
        feedback directly without re-deriving option labels.
        """
        if not self.questions:
            return 0, False, []

        def _opt(options: list, idx) -> str | None:
            if idx is None:
                return None
            try:
                i = int(idx)
            except (TypeError, ValueError):
                return None
            return options[i] if 0 <= i < len(options) else None

        correct = 0
        per_question: list[dict] = []
        for i, q in enumerate(self.questions):
            options = list(q.get("options", []))
            correct_index = q.get("answer_index")
            given_index = answers[i] if i < len(answers) else None
            try:
                ok = given_index is not None and int(given_index) == int(correct_index)
            except (TypeError, ValueError):
                ok = False
            if ok:
                correct += 1
            per_question.append(
                {
                    "prompt": q.get("prompt", ""),
                    "ok": ok,
                    "given": _opt(options, given_index),
                    "correct": _opt(options, correct_index),
                }
            )
        score = round(correct * 100 / len(self.questions))
        return score, score >= self.passing_score, per_question


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
