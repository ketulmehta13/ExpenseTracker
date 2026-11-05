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
from langchain_core.retrievers import BaseRetriever

from app import __version__
from app.auth import TokenCache
from app.cache import TTLCache
from app.chatbot.chain import build_llm
from app.chatbot.ratelimit import RateLimiter
from app.config import Settings
from app.llm.provider import build_chat_model
from app.ml.categorizer import CategorizerModel
from app.observability import Metrics, configure_logging
from app.routers import categorize, chat, health, insights, parse, receipts

logger = logging.getLogger("ml_service")


def load_retriever(settings: Settings) -> BaseRetriever | None:
    """The saved FAISS index, loaded once at startup. Without it the chatbot still answers
    questions about the user's own money, so a bad index mustn't stop the service."""
    from app.chatbot.index import load_embeddings, load_index, make_retriever

    try:
        store = load_index(settings.faiss_dir, load_embeddings(settings.embedding_cache_dir))
    except Exception as err:
        logger.error("Chatbot index not loaded from %s: %s", settings.faiss_dir, type(err).__name__)
        return None
    logger.info("Chatbot index loaded: %d chunks", store.index.ntotal)
    return make_retriever(store, settings.chat_k)


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    llm: BaseChatModel | None = None,
    chat_llm: BaseChatModel | None = None,
    chat_retriever: BaseRetriever | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings, an httpx transport that fakes Supabase,
    and optionally fake chat models and a fake retriever."""
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
        app.state.chat_llm = chat_llm if chat_llm is not None else build_llm(settings)
        app.state.chat_retriever = chat_retriever
        if chat_retriever is None and app.state.chat_llm is not None:
            app.state.chat_retriever = load_retriever(settings)
        yield
        await app.state.http.aclose()

    app = FastAPI(title="Expense Tracker ML service", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.metrics = Metrics()
    app.state.token_cache = TokenCache(settings.auth_cache_seconds)
    app.state.user_context_cache = TTLCache(settings.user_context_cache_seconds)
    app.state.insights_cache = TTLCache(settings.user_context_cache_seconds)
    app.state.summary_cache = TTLCache(600)  # LLM summaries are slow; reused while their facts are unchanged
    app.state.ocr_engine = None  # loaded on the first bill scan
    app.state.ocr_lock = asyncio.Lock()
    app.state.chat_limiter = RateLimiter(settings.chat_per_minute, settings.chat_per_day)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "DELETE"],
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
    app.include_router(receipts.router)
    app.include_router(chat.router)
    return app


app = create_app()
