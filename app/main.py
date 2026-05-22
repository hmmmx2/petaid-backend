"""FastAPI entry point.

Bootstrap order (per SRS Section 6):

1. ``create_app()`` builds the FastAPI application object.
2. The lifespan callback instantiates :class:`AppController`, which is the
   single coordinator (Singleton, SRS 5.1.2). The controller in turn
   creates :class:`AuthManager` and wires the :class:`EventBus`.
3. Domain exceptions raised inside any router are translated into HTTP
   responses by the handlers registered below — the routers themselves
   never see HTTPException for domain errors.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.v1 import api_router
from app.core.config import get_settings
from app.domain.app_controller import AppController, get_app_controller
from app.domain.exceptions import PetAidError

logger = logging.getLogger("petaid")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info("PetAid backend starting (env=%s)", settings.environment)
    # Eagerly bootstrap the singleton so the EventBus is shared with the
    # very first request rather than being created on demand.
    get_app_controller()
    try:
        yield
    finally:
        AppController().shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PetAid API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        # Explicit allow-list only — never reflect arbitrary origins while
        # credentials are allowed (that would defeat the same-origin policy).
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    # Security headers on every response. The API serves JSON only, so a strict
    # CSP plus anti-sniff / anti-framing / referrer controls cost nothing and
    # shrink the attack surface (clickjacking, MIME sniffing, referrer leakage).
    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # Don't let intermediaries cache authenticated API payloads.
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

    @app.exception_handler(PetAidError)
    async def _domain_error_handler(_: Request, exc: PetAidError) -> JSONResponse:
        """Translate domain exceptions to HTTP responses.

        Keeping this central means routers never need ``try/except`` around
        domain calls — they raise, we shape the response.
        """
        body: dict[str, object] = {"code": exc.code, "detail": exc.message}
        headers: dict[str, str] = {}
        # Surface the offending field on validation errors so the UI can
        # highlight it without parsing prose.
        if (field := getattr(exc, "field", None)) is not None:
            body["field"] = field
        if (retry := getattr(exc, "retry_after_seconds", None)) is not None:
            body["retry_after_seconds"] = retry
            # Standards-compliant signal for 429/423 so clients/proxies back off.
            headers["Retry-After"] = str(retry)
        return JSONResponse(status_code=exc.http_status, content=body, headers=headers)

    async def _db_unavailable_handler(_: Request, exc: Exception) -> JSONResponse:
        """Return a clean 503 when the database is unreachable.

        Without this, a connection failure (DB down, network blip, pool
        exhaustion) bubbles up as an opaque 500 ``Internal Server Error``.
        A 503 lets the client show a "temporarily unavailable, retry" message
        instead of a generic crash.
        """
        # Log only the exception *type* — the message/args of a connection
        # error can embed the DSN (host/user/password), which must never reach
        # the logs.
        logger.error("Database unavailable (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "code": "service_unavailable",
                "detail": "The service is temporarily unavailable. Please try again in a moment.",
            },
        )

    app.add_exception_handler(OperationalError, _db_unavailable_handler)
    app.add_exception_handler(InterfaceError, _db_unavailable_handler)

    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
