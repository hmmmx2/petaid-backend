import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    initials: str
    role: str
    pets_count: int
    quizzes_count: int
    chats_count: int


class PetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    species: str
    breed: str | None
    age_years: int | None
    icon_emoji: str
    icon_bg: str


class StatCards(BaseModel):
    quiz_avg_score: int
    guidance_sessions_this_month: int
    preparedness_pct: int


class ActivityPoint(BaseModel):
    label: str  # e.g. "Aug"
    quiz_score: int
    guidance_sessions: int


class LearningActivity(BaseModel):
    points: list[ActivityPoint]
    avg_score_trend_pct: int
    peak_label: str  # e.g. "Week 3 · Peak score"


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: str
    status: str  # watched, in_progress, new


class ChatThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    counterpart_name: str
    counterpart_initials: str
    counterpart_bg: str
    counterpart_fg: str
    last_message_at: datetime
    last_preview: str
    unread: bool


class ReadinessOut(BaseModel):
    category: str
    color: str
    score_pct: int


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    kind: str
    due_at: datetime
    icon_color: str


class DashboardResponse(BaseModel):
    user: UserSummary
    pets: list[PetOut]
    stats: StatCards
    activity: LearningActivity
    resources: list[ResourceOut]
    chats: list[ChatThreadOut]
    readiness: list[ReadinessOut]
    reminders: list[ReminderOut]
