"""v1 API router aggregator.

Each area of operation lives in its own module — eight in total, matching
the eight verification scenarios in SRS Section 7.
"""
from fastapi import APIRouter

from app.api.v1 import (
    auth,
    chats,
    dashboard,
    donations,
    feedback,
    first_aid,
    inquiries,
    pet_types,
    pets,
    quizzes,
    resources,
    ws,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(pet_types.router)
api_router.include_router(pets.router)
api_router.include_router(resources.router)
api_router.include_router(first_aid.router)
api_router.include_router(quizzes.router)
api_router.include_router(inquiries.router)
api_router.include_router(chats.router)
api_router.include_router(donations.router)
api_router.include_router(feedback.router)
api_router.include_router(ws.router)
