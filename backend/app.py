"""FastAPI application factory for ITARS (Phase 2).

The heavy `RoutingPipeline` is imported and constructed lazily inside the lifespan
handler, so importing this module (and injecting a fake pipeline in tests) does not
require the full ML stack. Run with:

    uvicorn backend.app:app --reload
"""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .api.deps import Metrics
from .api.routes import router
from .core.config import SETTINGS

API_DESCRIPTION = (
    "Intelligent Ticket Auto-Routing System API. Exposes the deterministic ML "
    "pipeline (duplicate detection, multi-label tags, priority, hybrid department "
    "routing, confidence gate) over REST, plus grounded LLM/RAG assistance."
)

# Endpoints reachable without the API token (liveness + API docs).
_PUBLIC_PATHS = {"/health", "/openapi.json", "/docs", "/redoc"}


def _parse_origins(raw: str) -> list[str]:
    """Turn the ITARS_CORS_ORIGINS string into a CORS allow-list. '*' / empty
    means allow all (dev); otherwise a comma-separated origin list."""
    cleaned = (raw or "").strip()
    if cleaned in ("", "*"):
        return ["*"]
    return [origin.strip() for origin in cleaned.split(",") if origin.strip()]


def _make_auth(token: str):
    """Shared-token gate. Preflight (OPTIONS) and the public paths pass through;
    everything else needs a matching X-API-Key or Bearer token. Constant-time
    compare avoids leaking the token via timing."""

    async def _auth(request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or path in _PUBLIC_PATHS
            or path.startswith("/docs")
            or path.startswith("/redoc")
        ):
            return await call_next(request)
        supplied = request.headers.get("x-api-key") or ""
        if not supplied:
            authz = request.headers.get("authorization", "")
            if authz[:7].lower() == "bearer ":
                supplied = authz[7:].strip()
        if not secrets.compare_digest(supplied, token):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "detail": "Provide a valid API token via X-API-Key or Authorization: Bearer.",
                },
            )
        return await call_next(request)

    return _auth


def create_app(
    pipeline=None,
    translation=None,
    *,
    session_factory=None,
    database_url=None,
    rag=None,
    llm=None,
    api_token: str | None = None,
    cors_origins: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from .core.config import SETTINGS

        # Persistence first — cheap, and the analyze path will use it.
        if app.state.session_factory is None:
            from .repositories.database import (
                init_db,
                make_engine,
                make_session_factory,
            )

            engine = make_engine(database_url or SETTINGS.database_url)
            init_db(engine)
            app.state.session_factory = make_session_factory(engine)
        # Lazy heavy imports so module import stays light / test-injectable.
        if app.state.translation is None:
            from .services.translation import TranslationService

            app.state.translation = TranslationService()
        if app.state.pipeline is None:
            from .services.pipeline import RoutingPipeline

            app.state.pipeline = RoutingPipeline(
                translation_service=app.state.translation
            )
        # RAG is optional — start without it if Qdrant/embedder are unavailable.
        if app.state.rag is None and SETTINGS.rag_enabled:
            try:
                from .rag.service import RagService

                app.state.rag = RagService()
            except Exception as exc:  # pragma: no cover - environment dependent
                print(f"[WARN] RAG unavailable, continuing without it: {exc}")
        # LLM gateway always available (echo provider works offline).
        if app.state.llm is None:
            from .core.llm import LLMGateway

            app.state.llm = LLMGateway()
        yield

    app = FastAPI(
        title="ITARS API",
        version=__version__,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "routing", "description": "Ticket analysis and routing."},
            {"name": "duplicates", "description": "Duplicate detection."},
            {"name": "translation", "description": "Multilingual translation (Phase 3)."},
            {"name": "tickets", "description": "Persisted decision log (Phase 6)."},
            {"name": "review", "description": "Human review queue and feedback."},
            {"name": "rag", "description": "Similar-ticket retrieval (Phase 7)."},
            {"name": "llm", "description": "LLM gateway (Phase 8)."},
            {"name": "ai", "description": "Grounded AI assistance (Phase 9)."},
            {"name": "system", "description": "Health and metrics."},
        ],
    )
    app.state.pipeline = pipeline
    app.state.translation = translation
    app.state.session_factory = session_factory
    app.state.rag = rag
    app.state.llm = llm
    app.state.metrics = Metrics()

    app.include_router(router)

    # --- Security & CORS (Phase 14) ---
    token = api_token if api_token is not None else SETTINGS.api_token
    origins = _parse_origins(
        cors_origins if cors_origins is not None else SETTINGS.cors_allow_origins
    )
    # Optional shared-token auth, added BEFORE CORS so CORS remains the outermost
    # layer (it then decorates 401s and handles preflight even when auth is on).
    if token:
        app.add_middleware(BaseHTTPMiddleware, dispatch=_make_auth(token))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Credentialed requests can't use a wildcard origin (CORS spec); the
        # browser client doesn't send credentials, so only enable it when the
        # origins are explicitly pinned.
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": str(exc)},
        )

    return app


app = create_app()
