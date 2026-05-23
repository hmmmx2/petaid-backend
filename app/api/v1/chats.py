"""Chat endpoints (SRS 7.6).

Writes (start/join/message/close/read) are REST so RBAC, rate limits and
validation apply; after each write the handler broadcasts the resulting event
over WebSocket (app/api/v1/ws.py) to the chat's participants for real-time
delivery. Read cursors per participant drive unread counts + "Seen" receipts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentAccountDep, CurrentPetOwnerDep, CurrentVetDep, DbDep, require
from app.core.rate_limit import enforce
from app.core.storage import offload_data_url
from app.domain.app_controller import get_app_controller
from app.domain.events import (
    CH_CHAT_CLOSED,
    CH_CHAT_INITIATED,
    CH_CHAT_MESSAGE,
    DomainEvent,
)
from app.domain.exceptions import InvalidInputException, NotAuthorisedException, NotFoundException
from app.domain.permissions import Permission
from app.models.account import PetOwner, VeterinaryExpert
from app.models.chat import Chat, ChatMessage, ChatStatus
from app.realtime.connection_manager import manager
from app.schemas.common import ChatIn, ChatLastMessage, ChatMessageIn, ChatMessageOut, ChatOut

router = APIRouter(prefix="/chats", tags=["chats"])


# --------------------------------------------------------------------------- #
# Serialization helpers                                                       #
# --------------------------------------------------------------------------- #
def _chat_out(chat: Chat, account_id: uuid.UUID) -> ChatOut:
    """Build ChatOut from the requester's perspective (unread + last message)."""
    msgs = sorted(chat.messages, key=lambda m: m.sent_at)
    is_owner = chat.pet_owner_id == account_id
    my_last = chat.owner_last_read_at if is_owner else chat.vet_last_read_at
    unread = sum(
        1 for m in msgs
        if m.sender_id != account_id and (my_last is None or m.sent_at > my_last)
    )
    last_message = None
    if msgs:
        last = msgs[-1]
        preview = (last.body or "").strip() or ("📷 Photo" if last.image_url else "")
        last_message = ChatLastMessage(
            sender_id=last.sender_id, preview=preview[:120], sent_at=last.sent_at
        )
    return ChatOut(
        id=chat.id,
        subject=chat.subject,
        status=chat.status.value,
        started_at=chat.started_at,
        ended_at=chat.ended_at,
        pet_owner_id=chat.pet_owner_id,
        vet_id=chat.vet_id,
        owner_last_read_at=chat.owner_last_read_at,
        vet_last_read_at=chat.vet_last_read_at,
        unread=unread,
        last_message=last_message,
        messages=[
            ChatMessageOut(
                id=m.id, sender_id=m.sender_id, body=m.body,
                image_url=m.image_url, sent_at=m.sent_at,
            )
            for m in msgs
        ],
    )


def _participants(chat: Chat) -> list[uuid.UUID]:
    return [pid for pid in (chat.pet_owner_id, chat.vet_id) if pid is not None]


async def _broadcast_chat_update(chat: Chat) -> None:
    await manager.send_to_accounts(
        _participants(chat),
        {
            "type": "chat_update",
            "chat_id": str(chat.id),
            "status": chat.status.value,
            "vet_id": str(chat.vet_id) if chat.vet_id else None,
        },
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #
@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require(Permission.CHAT_INITIATE))])
async def start_chat(payload: ChatIn, owner: CurrentPetOwnerDep, db: DbDep) -> ChatOut:
    enforce("chat_create", str(owner.id), max_requests=10, window_seconds=3600)
    chat = Chat(
        pet_owner_id=owner.id,
        subject=payload.subject,
        status=ChatStatus.INITIATED,
        started_at=datetime.now(timezone.utc),
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])

    get_app_controller().event_bus.publish(
        DomainEvent(channel=CH_CHAT_INITIATED, payload={"chat_id": str(chat.id)})
    )
    # Surface the new (unassigned) chat to every online vet in real time.
    await manager.send_to_role(
        "veterinary_expert",
        {"type": "chat_new", "chat": _chat_out(chat, owner.id).model_dump(mode="json")},
    )
    return _chat_out(chat, owner.id)


@router.post("/{chat_id}/join", response_model=ChatOut, dependencies=[Depends(require(Permission.CHAT_JOIN))])
async def join_chat(chat_id: uuid.UUID, vet: CurrentVetDep, db: DbDep) -> ChatOut:
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
    )
    if chat is None:
        raise NotFoundException("Chat")
    try:
        chat.join(vet_id=vet.id)
    except ValueError as exc:
        raise InvalidInputException("status", str(exc)) from exc
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])
    await _broadcast_chat_update(chat)
    return _chat_out(chat, vet.id)


@router.get("", response_model=list[ChatOut], dependencies=[Depends(require(Permission.CHAT_VIEW))])
async def list_chats(account: CurrentAccountDep, db: DbDep) -> list[ChatOut]:
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
    return [_chat_out(c, account.id) for c in rows]


@router.get("/{chat_id}", response_model=ChatOut, dependencies=[Depends(require(Permission.CHAT_VIEW))])
async def get_chat(chat_id: uuid.UUID, account: CurrentAccountDep, db: DbDep) -> ChatOut:
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
    )
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    return _chat_out(chat, account.id)


@router.post(
    "/{chat_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.CHAT_PARTICIPATE))],
)
async def post_message(
    chat_id: uuid.UUID, payload: ChatMessageIn, account: CurrentAccountDep, db: DbDep
) -> ChatMessage:
    enforce("chat_message", str(account.id), max_requests=20, window_seconds=60)
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    if chat.status == ChatStatus.CLOSED:
        raise InvalidInputException("status", "Chat is closed.")

    message = ChatMessage(
        chat_id=chat.id,
        sender_id=account.id,
        body=payload.body or "",
        image_url=await offload_data_url(payload.image_url, "chats"),
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
    # Real-time push to both participants.
    await manager.send_to_accounts(
        _participants(chat),
        {
            "type": "message",
            "chat_id": str(chat.id),
            "message": ChatMessageOut.model_validate(message).model_dump(mode="json"),
        },
    )
    return message


@router.post("/{chat_id}/read", response_model=ChatOut, dependencies=[Depends(require(Permission.CHAT_VIEW))])
async def mark_read(chat_id: uuid.UUID, account: CurrentAccountDep, db: DbDep) -> ChatOut:
    """Advance the caller's read cursor and notify the peer (Seen receipt)."""
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
    )
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    now = datetime.now(timezone.utc)
    if chat.pet_owner_id == account.id:
        chat.owner_last_read_at = now
    elif chat.vet_id == account.id:
        chat.vet_last_read_at = now
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])

    peer = chat.vet_id if chat.pet_owner_id == account.id else chat.pet_owner_id
    if peer is not None:
        await manager.send_to_accounts(
            [peer],
            {
                "type": "read",
                "chat_id": str(chat.id),
                "account_id": str(account.id),
                "last_read_at": now.isoformat(),
            },
        )
    return _chat_out(chat, account.id)


@router.post("/{chat_id}/close", response_model=ChatOut, dependencies=[Depends(require(Permission.CHAT_PARTICIPATE))])
async def close_chat(chat_id: uuid.UUID, account: CurrentAccountDep, db: DbDep) -> ChatOut:
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.messages))
    )
    if chat is None:
        raise NotFoundException("Chat")
    _assert_participant(chat, account)
    chat.close()
    await db.commit()
    await db.refresh(chat, attribute_names=["messages"])

    get_app_controller().event_bus.publish(
        DomainEvent(channel=CH_CHAT_CLOSED, payload={"chat_id": str(chat.id)})
    )
    await _broadcast_chat_update(chat)
    return _chat_out(chat, account.id)


def _assert_participant(chat: Chat, account) -> None:
    """Pet owner or assigned vet only; pending vet may join via /join."""
    if isinstance(account, PetOwner) and chat.pet_owner_id == account.id:
        return
    if isinstance(account, VeterinaryExpert) and (
        chat.vet_id == account.id or chat.status == ChatStatus.INITIATED
    ):
        return
    raise NotAuthorisedException("You are not a participant in this chat.")
