"""In-memory WebSocket connection registry + presence (real-time chat).

Single-instance only — connections and presence live in this process. For a
horizontally-scaled deployment, back the same interface with a shared broker
(e.g. Redis pub/sub) so broadcasts and presence span instances.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket


class ConnectionManager:
    """Tracks live sockets per account and fans messages out to participants."""

    def __init__(self) -> None:
        self._by_account: dict[uuid.UUID, set[WebSocket]] = {}
        self._role: dict[uuid.UUID, str] = {}
        self.last_seen: dict[uuid.UUID, datetime] = {}
        self._lock = asyncio.Lock()

    async def connect(self, account_id: uuid.UUID, ws: WebSocket, role: str = "") -> bool:
        """Register a socket. Returns True if this is the account's first one
        (i.e. it just came online)."""
        async with self._lock:
            sockets = self._by_account.setdefault(account_id, set())
            was_offline = len(sockets) == 0
            sockets.add(ws)
            if role:
                self._role[account_id] = role
            return was_offline

    async def disconnect(self, account_id: uuid.UUID, ws: WebSocket) -> bool:
        """Remove a socket. Returns True if the account is now fully offline."""
        async with self._lock:
            sockets = self._by_account.get(account_id)
            if sockets:
                sockets.discard(ws)
                if not sockets:
                    self._by_account.pop(account_id, None)
                    self.last_seen[account_id] = datetime.now(timezone.utc)
                    return True
            return False

    def is_online(self, account_id: uuid.UUID) -> bool:
        return bool(self._by_account.get(account_id))

    def accounts_with_role(self, role: str) -> set[uuid.UUID]:
        return {aid for aid in self._by_account if self._role.get(aid) == role}

    def last_seen_iso(self, account_id: uuid.UUID) -> str | None:
        ts = self.last_seen.get(account_id)
        return ts.isoformat() if ts else None

    async def send_to_role(self, role: str, message: dict) -> None:
        await self.send_to_accounts(self.accounts_with_role(role), message)

    async def send_to_accounts(self, account_ids, message: dict) -> None:
        """Best-effort JSON fan-out to every live socket of each account."""
        targets: list[tuple[uuid.UUID, WebSocket]] = []
        for aid in {a for a in account_ids if a is not None}:
            for ws in list(self._by_account.get(aid, set())):
                targets.append((aid, ws))
        for aid, ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                # Socket is dead/closing — drop it.
                await self.disconnect(aid, ws)


# Process-wide singleton.
manager = ConnectionManager()
