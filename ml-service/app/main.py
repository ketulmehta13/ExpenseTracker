"""FastAPI application for the Expense Tracker ML service."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel

from app import __version__
from app.assistant.graph import build_graph
from app.auth import TokenCache
from app.cache import TTLCache
from app.config import Settings
from app.copilot.pipeline import build_copilot_graph
from app.copilot.ratelimit import RateLimiter
from app.llm.provider import build_chat_model
from app.ml.categorizer import CategorizerModel
from app.observability import Metrics, configure_logging
from app.rag.embeddings import Embedder
from app.routers import assistant, categorize, copilot, health, help, insights, parse, receipts

logger = logging.getLogger("ml_service")


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    llm: BaseChatModel | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings, an httpx transport that fakes Supabase,
    and optionally a fake chat model and embedder."""
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # One pooled HTTP client for the app's lifetime (Supabase Auth + REST calls)
        app.state.http = httpx.AsyncClient(timeout=10, transport=transport)
        app.state.categorizer = CategorizerModel.load(settings.model_dir)
        if app.state.categorizer is None:
            logger.warning(
                "No categorizer model in %s; /v1/categorize will use history only. "
                "Train one with: python -m training.train_categorizer",
                settings.model_dir,
            )
        try:
            app.state.llm = llm if llm is not None else build_chat_model(settings)
        except Exception as err:
            # A misconfigured LLM (e.g. a missing API key) must not take the whole service down:
            # every LLM feature has a rule-based or template fallback
            logger.error("LLM disabled, its configuration is invalid: %s", type(err).__name__)
            app.state.llm = None
        logger.info("LLM provider: %s", settings.llm_provider if app.state.llm is not None else "none")
        yield
        await app.state.http.aclose()

    app = FastAPI(title="Expense Tracker ML service", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.metrics = Metrics()
    app.state.token_cache = TokenCache(settings.auth_cache_seconds)
    app.state.user_context_cache = TTLCache(settings.user_context_cache_seconds)
    app.state.insights_cache = TTLCache(settings.user_context_cache_seconds)
    app.state.summary_cache = TTLCache(600)  # LLM summaries are slow; reused while their facts are unchanged
    app.state.embedder = embedder
    app.state.help_index = None  # built on the first help question
    app.state.assistant_graph = build_graph()
    app.state.ocr_engine = None  # loaded on the first bill scan
    app.state.copilot_graph = build_copilot_graph()
    app.state.kb_retriever = None  # built on the first copilot question
    app.state.copilot_limiter = RateLimiter(settings.copilot_per_minute, settings.copilot_per_day)
    app.state.ocr_lock = asyncio.Lock()

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
        elapsed = time.perf_counter() - started
        # The route template ("/v1/insights"), not the URL: query strings and ids would explode the labels
        route = getattr(request.scope.get("route"), "path", "unmatched")
        app.state.metrics.observe_request(route, response.status_code, elapsed)
        logger.info("%s %s -> %s in %.1f ms", request.method, route, response.status_code, elapsed * 1000)
        return response

    app.include_router(health.router)
    app.include_router(categorize.router)
    app.include_router(insights.router)
    app.include_router(parse.router)
    app.include_router(help.router)
    app.include_router(assistant.router)
    app.include_router(receipts.router)
    app.include_router(copilot.router)
    return app


app = create_app()
