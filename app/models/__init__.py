"""SQLAlchemy ORM models.

The class hierarchy mirrors the UML in SRS Figure 1:

* :class:`Account` (abstract via single-table inheritance) with subclasses
  :class:`PetOwner` and :class:`VeterinaryExpert`.
* :class:`UserCredentials`, :class:`DonationRecord` and
  :class:`FeedbackEntry` are data-holders composed inside their parent
  (SRS 4.1.7).
* All other classes are entities with behaviour (SRS 4.1.4).

Importing this package registers every model on ``Base.metadata`` so Alembic
auto-generation picks them up.
"""
from app.models.account import Account, PetOwner, VeterinaryExpert
from app.models.chat import Chat, ChatMessage, ChatStatus
from app.models.credentials import UserCredentials
from app.models.donation import Donation, DonationRecord, DonationStatus
from app.models.feedback import Feedback, FeedbackEntry, FeedbackTargetType
from app.models.first_aid import FirstAidGuidance
from app.models.inquiry import Inquiry, InquiryStatus
from app.models.pet import Pet
from app.models.pet_type import PetType
from app.models.quiz import Quiz, QuizAttempt
from app.models.resource import Resource, ResourceStatus

__all__ = [
    "Account",
    "Chat",
    "ChatMessage",
    "ChatStatus",
    "Donation",
    "DonationRecord",
    "DonationStatus",
    "Feedback",
    "FeedbackEntry",
    "FeedbackTargetType",
    "FirstAidGuidance",
    "Inquiry",
    "InquiryStatus",
    "Pet",
    "PetOwner",
    "PetType",
    "Quiz",
    "QuizAttempt",
    "Resource",
    "ResourceStatus",
    "UserCredentials",
    "VeterinaryExpert",
]
