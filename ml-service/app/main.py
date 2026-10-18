"""FastAPI application for the Expense Tracker ML service."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.auth import TokenCache
from app.config import Settings
from app.routers import health

logger = logging.getLogger("ml_service")


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings and an httpx transport that fakes Supabase."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # One pooled HTTP client for the app's lifetime (Supabase Auth + REST calls)
        app.state.http = httpx.AsyncClient(timeout=10, transport=transport)
        yield
        await app.state.http.aclose()

    app = FastAPI(title="Expense Tracker ML service", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.token_cache = TokenCache(settings.auth_cache_seconds)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %s in %.1f ms", request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response

    app.include_router(health.router)
    return app


app = create_app()
