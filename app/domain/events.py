"""Observer pattern infrastructure (SRS 5.2.1).

Inquiry, Chat, Donation and Feedback emit events whenever their state
changes. Interested classes (typically the opposite actor's dashboard or a
notification log) subscribe to the relevant channel. The bus is in-process
and synchronous; it is sufficient for the prototype scope of Assignment 3
and keeps the design free of external broker dependencies.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("petaid.events")


@dataclass(frozen=True)
class DomainEvent:
    """Immutable event published on the bus.

    Attributes:
        channel: A dotted channel name e.g. ``"inquiry.submitted"``.
        payload: A small dict describing the event. Keep it serialisable.
        occurred_at: UTC timestamp at construction time.
    """

    channel: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Subscriber = Callable[[DomainEvent], None]


class EventBus:
    """In-process pub/sub bus used to implement the Observer pattern.

    A single :class:`EventBus` instance is owned by :class:`AppController`.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, channel: str, handler: Subscriber) -> None:
        """Register ``handler`` to receive events published on ``channel``."""
        self._subscribers[channel].append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Deliver ``event`` to every subscriber of its channel.

        Exceptions raised by subscribers are logged but do not interrupt
        delivery to other subscribers, so a single faulty observer cannot
        break the publishing entity.
        """
        for handler in self._subscribers.get(event.channel, []):
            try:
                handler(event)
            except Exception:  # pragma: no cover  - defensive
                logger.exception("Subscriber for %s raised", event.channel)


# Channel name constants — referenced from the entities so we don't pass raw
# strings around the codebase.
CH_INQUIRY_SUBMITTED = "inquiry.submitted"
CH_INQUIRY_RESPONDED = "inquiry.responded"
CH_CHAT_INITIATED = "chat.initiated"
CH_CHAT_MESSAGE = "chat.message"
CH_CHAT_CLOSED = "chat.closed"
CH_DONATION_COMPLETED = "donation.completed"
CH_FEEDBACK_SUBMITTED = "feedback.submitted"
CH_FEEDBACK_FLAGGED = "feedback.flagged"
