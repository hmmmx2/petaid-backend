"""Pydantic schemas shared across multiple routers."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PetTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    icon_emoji: str
    icon_bg: str


class PetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    pet_type_id: uuid.UUID
    breed: str | None = Field(default=None, max_length=80)
    age_years: int | None = Field(default=None, ge=0, le=80)
    health_notes: str = Field(default="", max_length=1000)


class PetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    breed: str | None
    age_years: int | None
    health_notes: str
    pet_type: PetTypeOut


class ResourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content_type: str = Field(pattern=r"^(video|pdf|images)$")
    pet_type_id: uuid.UUID
    media_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=1)


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content_type: str
    status: str
    media_path: str | None
    pet_type: PetTypeOut


class FirstAidIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    emergency_type: str = Field(min_length=1, max_length=60)
    pet_type_id: uuid.UUID
    summary: str = Field(default="", max_length=1000)
    steps: list[str] = Field(min_length=1)


class FirstAidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    emergency_type: str
    summary: str
    steps: list[str]
    pet_type: PetTypeOut
    resources: list[ResourceOut]


class QuizQuestion(BaseModel):
    prompt: str = Field(min_length=1, max_length=400)
    options: list[str] = Field(min_length=2, max_length=6)
    # ``-1`` is used as a sentinel on the *response* side to hide the correct
    # answer from clients; create-time validation is enforced separately in the
    # quizzes router via a stricter input model.
    answer_index: int = Field(ge=-1)


class QuizIn(BaseModel):
    resource_id: uuid.UUID
    title: str = Field(min_length=1, max_length=160)
    passing_score: int = Field(ge=0, le=100, default=60)
    questions: list[QuizQuestion] = Field(min_length=1)


class QuizOut(BaseModel):
    id: uuid.UUID
    title: str
    passing_score: int
    resource_id: uuid.UUID
    questions: list[QuizQuestion]


class QuizAttemptIn(BaseModel):
    answers: list[int]


class QuizPerQuestion(BaseModel):
    """Per-question feedback returned after grading (option *text*)."""

    prompt: str
    ok: bool
    given: str | None = None
    correct: str | None = None


class QuizAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quiz_id: uuid.UUID
    score_pct: int
    passed: bool
    completed_at: datetime
    per_question: list[QuizPerQuestion] = []


class InquiryIn(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=4000)
    # Optional photos (data URLs or http(s) URLs). Owners typically attach a
    # downscaled JPEG of their pet's condition.
    images: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("images")
    @classmethod
    def _validate_images(cls, v: list[str]) -> list[str]:
        MAX_EACH = 2_000_000  # ~2 MB per image (data-URL chars)
        MAX_TOTAL = 6_000_000
        total = 0
        for s in v:
            if not isinstance(s, str) or not s.strip():
                raise ValueError("Each image must be a non-empty string.")
            if not (s.startswith("data:image/") or s.startswith("http://") or s.startswith("https://")):
                raise ValueError("Images must be image data URLs or http(s) URLs.")
            if len(s) > MAX_EACH:
                raise ValueError("An attached image is too large (max ~2 MB each).")
            total += len(s)
        if total > MAX_TOTAL:
            raise ValueError("Attached images exceed the total size limit.")
        return v


class InquiryResponseIn(BaseModel):
    response: str = Field(min_length=1, max_length=4000)


class InquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    question: str
    response: str | None
    status: str
    image_urls: list[str] = []
    submitted_at: datetime
    responded_at: datetime | None
    closed_at: datetime | None


class ChatIn(BaseModel):
    subject: str = Field(min_length=1, max_length=160)


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    sent_at: datetime


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    messages: list[ChatMessageOut] = []


class DonationIn(BaseModel):
    amount_cents: int = Field(ge=100, le=1_000_000_00)
    currency: str = Field(default="MYR", pattern=r"^[A-Z]{3}$")
    recurring: bool = False


class DonationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_cents: int
    currency: str
    recurring: bool
    status: str
    transaction_ref: str | None
    processed_at: datetime | None


class FeedbackIn(BaseModel):
    target_type: str = Field(pattern=r"^(resource|guidance)$")
    target_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
    flagged: bool = False


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    flagged: bool
    rating: int
    comment: str
    created_at: datetime
