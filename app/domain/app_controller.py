"""``AppController`` — the singleton coordinator described in SRS 3.1.1.1.

It owns the :class:`AuthManager`, the :class:`EventBus`, and is responsible
for creating the role-specific :class:`Dashboard` after authentication
(Template Method pattern).

This class deliberately exposes only the operations the rest of the
application needs (minimal public interface heuristic, SRS 4.1.5). It does
not perform authentication, content management or rendering itself —
those responsibilities are delegated to the appropriate collaborator
(avoiding God-class anti-pattern, SRS 4.1.3).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.events import (
    CH_CHAT_MESSAGE,
    CH_DONATION_COMPLETED,
    CH_FEEDBACK_FLAGGED,
    CH_INQUIRY_SUBMITTED,
    DomainEvent,
    EventBus,
)

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.domain.auth_manager import AuthManager
    from app.domain.dashboards import Dashboard
    from app.models.account import Account

logger = logging.getLogger("petaid.controller")


class _SingletonMeta(type):
    """Metaclass implementing the Singleton pattern (SRS 5.1.2).

    Using a metaclass keeps the singleton invariant centralised so the same
    pattern can be reused (e.g. by :class:`AuthManager`) without copy-paste.
    """

    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):  # type: ignore[override]
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Test helper — clears the singleton cache."""
        mcs._instances.clear()


class AppController(metaclass=_SingletonMeta):
    """Single entry point that wires the support layer together at startup.

    Responsibilities (mirroring CRC table 4):
        * Construct :class:`AuthManager` on bootstrap.
        * Hold the :class:`EventBus` shared by all entity classes that emit
          events.
        * Decide which :class:`Dashboard` subclass to instantiate for a given
          authenticated :class:`Account`.
    """

    def __init__(self) -> None:
        # Late import to break the import cycle (auth_manager imports models
        # which import the bus indirectly through the seed helper).
        from app.domain.auth_manager import AuthManager

        self._event_bus = EventBus()
        self._auth_manager = AuthManager(event_bus=self._event_bus)
        self._wire_default_subscribers()
        logger.info("AppController bootstrapped")

    @property
    def auth_manager(self) -> "AuthManager":
        return self._auth_manager

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def create_dashboard(self, account: "Account", db: "AsyncSession") -> "Dashboard":
        """Factory entry point used by the dashboard router.

        Returns the concrete :class:`Dashboard` subclass appropriate for the
        authenticated actor's role. The decision is made here (Controller
        layer) rather than inside :class:`Account` so the entity layer stays
        free of UI concerns.
        """
        from app.domain.dashboards import PetOwnerDashboard, VeterinaryExpertDashboard

        if account.role == "pet_owner":
            return PetOwnerDashboard(account=account, db=db, event_bus=self._event_bus)
        if account.role == "veterinary_expert":
            return VeterinaryExpertDashboard(account=account, db=db, event_bus=self._event_bus)
        raise ValueError(f"Unknown account role: {account.role!r}")

    def shutdown(self) -> None:
        """Release coordinator state. Called from the FastAPI lifespan."""
        logger.info("AppController shutting down")
        _SingletonMeta.reset()

    # ------------------------------------------------------------------ #
    # Default observer wiring                                            #
    # ------------------------------------------------------------------ #
    def _wire_default_subscribers(self) -> None:
        """Subscribe the system-level observers.

        These are deliberately small — they log the event so it is visible in
        the server log during evaluation/screenshots. Real notification
        delivery (push, email) would be additional subscribers added here.
        """

        def _log(event: DomainEvent) -> None:
            logger.info("event[%s] payload=%s", event.channel, event.payload)

        for channel in (
            CH_INQUIRY_SUBMITTED,
            CH_CHAT_MESSAGE,
            CH_DONATION_COMPLETED,
            CH_FEEDBACK_FLAGGED,
        ):
            self._event_bus.subscribe(channel, _log)


def get_app_controller() -> AppController:
    """Convenience accessor — preferred over ``AppController()`` in routers."""
    return AppController()
