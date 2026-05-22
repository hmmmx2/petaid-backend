"""Chat endpoints (SRS 7.6).

Synchronous in the SRS sense (both actors present). At the HTTP layer we
poll — websockets would be a future enhancement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep
from app.domain.app_controller import get_app_controller
from app.domain.events import (
    CH_CHAT_CLOSED,
    CH_CHAT_INITIATED,
    CH_CHAT_MESSAGE,
    DomainEvent,
)
from app.domain.exceptions import InvalidInputException, NotAuthorisedException, NotFoundException
from app.models.account import PetOwner, VeterinaryExpert
from app.models.chat import Chat, ChatMessage, ChatStatus
from app.schemas.common import ChatIn, ChatMessageIn, ChatMessageOut, ChatOut

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def start_chat(
    payload: ChatIn, owner: CurrentPetOwnerDep, db: DbDep
) -> Chat:
    chat = Chat(
        pet_owner_id=owner.id,
        subject=payload.subject,
        status=ChatStatus.INITIATED,
        started_at=datetime.now(timezone.utc),
    )
    db.add(chat)
    await db.commit()
    # Eager-load `messages` inside the async session: ChatOut serializes the
    # relationship, and a lazy-load during Pydantic serialization runs outside
    # the greenlet → MissingGreenlet/500. A fresh chat just yields an empty list.
    await db.refresh(chat, attribute_names=["messages"])

    get_app_controller().event_bus.publish(
        DomainEvent(channel=CH_CHAT_INITIATED, payload={"chat_id": str(chat.id)})
    )
    return chat


@router.post("/{chat_id}/join", response_model=ChatOut)
async def join_chat(chat_id: uuid.UUID, vet: CurrentVetDep, db: DbDep) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise NotFoundException("Chat")
    try:
        chat.join(vet_id=vet.id)
    except ValueError as exc:
        raise InvalidInputException("status", str(exc)) from exc
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])
    return chat


@router.get("", response_model=list[ChatOut])
async def list_chats(account: CurrentAccountDep, db: DbDep) -> list[Chat]:
    if isinstance(account, PetOwner):
        stmt = select(Chat).where(Chat.pet_owner_id == account.id)
    elif isinstance(account, VeterinaryExpert):
        stmt = select(Chat).where(
            or_(Chat.vet_id == account.id, Chat.status == ChatStatus.INITIATED)
        )
    else:
        return []
    rows = await db.scalars(
        stmt.options(selectinload(Chat.messages)).order_by(Chat.started_at.desc())
    )
    return list(rows)


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(
    chat_id: uuid.UUID, account: CurrentAccountDep, db: DbDep
) -> Chat:
    chat = await db.scalar(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.messages))
    )
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    return chat


@router.post(
    "/{chat_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    chat_id: uuid.UUID,
    payload: ChatMessageIn,
    account: CurrentAccountDep,
    db: DbDep,
) -> ChatMessage:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    if chat.status == ChatStatus.CLOSED:
        raise InvalidInputException("status", "Chat is closed.")

    message = ChatMessage(
        chat_id=chat.id,
        sender_id=account.id,
        body=payload.body,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    get_app_controller().event_bus.publish(
        DomainEvent(
            channel=CH_CHAT_MESSAGE,
            payload={"chat_id": str(chat.id), "sender_id": str(account.id)},
        )
    )
    return message


@router.post("/{chat_id}/close", response_model=ChatOut)
async def close_chat(
    chat_id: uuid.UUID, account: CurrentAccountDep, db: DbDep
) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    chat.close()
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])

    get_app_controller().event_bus.publish(
        DomainEvent(channel=CH_CHAT_CLOSED, payload={"chat_id": str(chat.id)})
    )
    return chat


def _assert_participant(chat: Chat, account) -> None:
    """Pet owner or assigned vet only; pending vet may join via /join."""
    if isinstance(account, PetOwner) and chat.pet_owner_id == account.id:
        return
    if isinstance(account, VeterinaryExpert) and (
        chat.vet_id == account.id or chat.status == ChatStatus.INITIATED
    ):
        return
    raise NotAuthorisedException("You are not a participant in this chat.")
