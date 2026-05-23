"""WebSocket endpoint for real-time chat (delivery + transient signals).

Persistence/RBAC/rate-limits stay on the REST chat endpoints; this socket
carries live delivery (message/chat_update/read are broadcast from the REST
handlers) plus transient typing + presence signals.

Auth: a short-lived access JWT is passed as the ``token`` query param (browsers
can't set Authorization headers on WebSocket handshakes). The client reconnects
with a refreshed token via the normal refresh flow.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.account import Account
from app.models.chat import Chat, ChatStatus
from app.realtime.connection_manager import manager

router = APIRouter(tags=["ws"])


async def _account_from_token(token: str) -> Account | None:
    if not token:
        return None
    try:
        claims = decode_token(token)
    except ValueError:
        return None
    if claims.get("type") != "access":
        return None
    sub = claims.get("sub")
    try:
        account_id = uuid.UUID(sub) if sub else None
    except (ValueError, TypeError):
        return None
    if account_id is None:
        return None
    async with SessionLocal() as db:
        account = await db.get(Account, account_id)
        if account is None or not account.is_active:
            return None
        return account


async def _peer_ids(account_id: uuid.UUID) -> set[uuid.UUID]:
    """Other participants of this account's non-closed chats."""
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(Chat).where(
                or_(Chat.pet_owner_id == account_id, Chat.vet_id == account_id),
                Chat.status != ChatStatus.CLOSED,
            )
        )
        peers: set[uuid.UUID] = set()
        for c in rows:
            other = c.vet_id if c.pet_owner_id == account_id else c.pet_owner_id
            if other:
                peers.add(other)
        return peers


async def _chat_peer(chat_id_raw, account_id: uuid.UUID) -> uuid.UUID | None:
    """Return the other participant if `account_id` belongs to the chat."""
    try:
        chat_id = uuid.UUID(str(chat_id_raw))
    except (ValueError, TypeError):
        return None
    async with SessionLocal() as db:
        chat = await db.get(Chat, chat_id)
    if chat is None:
        return None
    if chat.pet_owner_id == account_id:
        return chat.vet_id
    if chat.vet_id == account_id:
        return chat.pet_owner_id
    return None


@router.websocket("/ws/chat")
async def chat_ws(ws: WebSocket, token: str = Query(default="")) -> None:
    account = await _account_from_token(token)
    if account is None:
        await ws.close(code=4401)  # unauthorized
        return
    me = account.id
    await ws.accept()

    became_online = await manager.connect(me, ws, role=account.role)
    peers = await _peer_ids(me)

    # Tell the new client which peers are currently online…
    await ws.send_json({
        "type": "presence_snapshot",
        "online": [str(p) for p in peers if manager.is_online(p)],
    })
    # …and tell those peers that I just came online.
    if became_online and peers:
        await manager.send_to_accounts(
            peers, {"type": "presence", "account_id": str(me), "online": True}
        )

    try:
        while True:
            data = await ws.receive_json()
            kind = data.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "typing":
                peer = await _chat_peer(data.get("chat_id"), me)
                if peer is not None:
                    await manager.send_to_accounts(
                        [peer],
                        {
                            "type": "typing",
                            "chat_id": str(data.get("chat_id")),
                            "account_id": str(me),
                            "is_typing": bool(data.get("is_typing")),
                        },
                    )
            # other client→server kinds are ignored (writes go via REST)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        went_offline = await manager.disconnect(me, ws)
        if went_offline:
            offline_peers = await _peer_ids(me)
            if offline_peers:
                await manager.send_to_accounts(
                    offline_peers,
                    {
                        "type": "presence",
                        "account_id": str(me),
                        "online": False,
                        "last_seen": manager.last_seen_iso(me),
                    },
                )
