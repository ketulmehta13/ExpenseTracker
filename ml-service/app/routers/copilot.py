"""The Financial Copilot API.

    POST   /v1/copilot/chat               one message -> a reply with typed blocks (JSON)
    POST   /v1/copilot/chat/stream        the same as server-sent events: meta, delta..., final (or error)
    POST   /v1/copilot/actions/confirm    run a confirmed action once (idempotent)
    GET    /v1/copilot/threads            the user's conversations
    GET    /v1/copilot/threads/{id}       one conversation's messages
    DELETE /v1/copilot/threads/{id}       delete a conversation

Every route needs the user's Supabase access token. Their data and history are read and written
with that token, so row level security applies; the user id is never taken from the request
body or from a model. Each user is rate limited.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.assistant.router import merchant_keys_from
from app.auth import CurrentUser, get_current_user
from app.copilot import actions, history
from app.copilot.pipeline import CopilotContext, understanding_from_dict, understanding_to_dict
from app.copilot.schemas import (
    ChatRequest,
    ConfirmRequest,
    ConfirmResult,
    ContextBlock,
    CopilotReply,
    StoredMessage,
    ThreadSummary,
)
from app.copilot.tools import FinanceData
from app.dates import resolve_today
from app.rag.embeddings import load_embedder
from app.rag.kb_retriever import KnowledgeRetriever
from app.rag.vectorstore import FallbackVectorStore, InMemoryVectorStore, SupabaseVectorStore, load_snapshot
from app.routers.categorize import suggest_category
from app.routers.insights import load_insights
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])
logger = logging.getLogger("ml_service.copilot")


def get_retriever(request: Request) -> KnowledgeRetriever:
    """Built on first use: pgvector in Supabase, with the snapshot baked into the image as the
    fallback (so the copilot works before ingestion and while Supabase is unreachable)."""
    state, settings = request.app.state, request.app.state.settings
    if state.kb_retriever is None:
        snapshot = settings.model_dir / "kb_snapshot.npz"
        fallback = load_snapshot(snapshot) if snapshot.exists() else InMemoryVectorStore()
        if not snapshot.exists():
            logger.warning("no knowledge-base snapshot at %s", snapshot)
        store = (
            FallbackVectorStore(
                SupabaseVectorStore(settings.supabase_url, settings.supabase_anon_key), fallback
            )
            if settings.supabase_url
            else fallback
        )
        embedder = None
        if settings.copilot_embedding_model:
            embedder = load_embedder(settings.copilot_embedding_model, settings.embedding_cache_dir)
        state.kb_retriever = KnowledgeRetriever(store, embedder)
    return state.kb_retriever


def _limit(request: Request, user: CurrentUser) -> None:
    wait = request.app.state.copilot_limiter.check(user.id)
    if wait is not None:
        request.app.state.metrics.event("copilot", "rate_limited")
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many messages; please wait a moment",
            headers={"Retry-After": str(int(wait) + 1)},
        )


async def _prepare(request: Request, user: CurrentUser, data: SupabaseData, body: ChatRequest):
    """The user's data, their thread and the previous question (for follow-ups)."""
    today = resolve_today(body.today)
    inputs = await load_insights(request, user, data, today)
    finance = FinanceData(today, inputs.transactions, inputs.categories, inputs.budget, inputs.insights)

    thread_id, previous, history_ok = body.thread_id, None, True
    try:
        thread_id = await history.open_thread(data, body.thread_id, body.message)
        for message in reversed(await history.recent_messages(data, thread_id)):
            context = next((b for b in message.get("blocks") or [] if b.get("type") == "context"), None)
            if message["role"] == "assistant" and context:
                previous = understanding_from_dict(context.get("understanding"))
                break
    except history.ThreadNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from err
    except history.HistoryUnavailable as err:
        logger.warning("copilot history unavailable: %s", err)
        history_ok, thread_id = False, None

    async def suggest(title: str, amount: float | None, tx_type: str) -> dict | None:
        suggestion = (await suggest_category(request, user, data, title, amount, tx_type)).suggestion
        if suggestion is None or suggestion.category_id is None:
            return None
        return {"id": suggestion.category_id, "name": suggestion.category_name}

    settings = request.app.state.settings
    context = CopilotContext(
        data=finance,
        merchant_keys=merchant_keys_from(inputs.transactions),
        retriever=get_retriever(request),
        llm=request.app.state.llm,
        timeout=settings.llm_timeout_seconds,
        suggest_category=suggest,
    )
    return context, thread_id, previous, history_ok


async def _finish(
    data: SupabaseData, body: ChatRequest, state: dict, thread_id: UUID | None, history_ok: bool
) -> CopilotReply:
    answer, plan = state["answer"], state["plan"]
    blocks = list(state.get("blocks") or [])
    stored = [b.model_dump(mode="json") for b in blocks]
    stored.append(
        ContextBlock(understanding=understanding_to_dict(plan.understanding)).model_dump(mode="json")
    )
    if history_ok and thread_id is not None:
        try:
            await history.append(data, thread_id, "user", body.message, [])
            await history.append(data, thread_id, "assistant", answer.text, stored)
        except history.HistoryUnavailable as err:
            logger.warning("copilot history not saved: %s", err)
            history_ok = False
    return CopilotReply(
        thread_id=thread_id if history_ok else None,
        route=plan.route,
        reply=answer.text,
        blocks=blocks,
        grounded=answer.grounded,
        answered_by=answer.answered_by,
        history_saved=history_ok,
    )


def _record(request: Request, reply: CopilotReply, started: float) -> None:
    request.app.state.metrics.event("copilot", reply.route)
    request.app.state.metrics.event("copilot_answer", reply.answered_by)
    # No message text and no figures in the logs: just what happened and how long it took
    logger.info(
        "copilot route=%s answered_by=%s blocks=%d ms=%d",
        reply.route,
        reply.answered_by,
        len(reply.blocks),
        (time.perf_counter() - started) * 1000,
    )


@router.post("/chat", response_model=CopilotReply)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> CopilotReply:
    _limit(request, user)
    started = time.perf_counter()
    context, thread_id, previous, history_ok = await _prepare(request, user, data, body)
    state = await request.app.state.copilot_graph.ainvoke(
        {"message": body.message, "previous": previous}, {"configurable": {"copilot": context}}
    )
    reply = await _finish(data, body, state, thread_id, history_ok)
    _record(request, reply, started)
    return reply


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> StreamingResponse:
    _limit(request, user)
    started = time.perf_counter()
    # Errors before the stream starts (auth, rate limit, unknown thread) are normal HTTP errors
    context, thread_id, previous, history_ok = await _prepare(request, user, data, body)

    async def events() -> AsyncIterator[str]:
        yield _sse("meta", {"thread_id": str(thread_id) if thread_id else None})
        final: dict = {}
        try:
            async for mode, chunk in request.app.state.copilot_graph.astream(
                {"message": body.message, "previous": previous},
                {"configurable": {"copilot": context}},
                stream_mode=["custom", "values"],
            ):
                if mode == "custom" and "delta" in chunk:
                    yield _sse("delta", {"text": chunk["delta"]})
                elif mode == "values":
                    final = chunk
            reply = await _finish(data, body, final, thread_id, history_ok)
            _record(request, reply, started)
            yield _sse("final", reply.model_dump(mode="json"))
        except Exception as err:  # the stream has started: report the failure as an event
            logger.exception("copilot stream failed: %s", type(err).__name__)
            yield _sse("error", {"message": "Something went wrong while answering. Please try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/confirm", response_model=ConfirmResult)
async def confirm_action(
    body: ConfirmRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> ConfirmResult:
    _limit(request, user)
    today = resolve_today(body.today)
    inputs = await load_insights(request, user, data, today)
    fields = actions.validate_fields(body.action, body.fields, inputs.categories, today)
    claim = await actions.claim(data, user.id, body.idempotency_key, body.action)
    if not claim.fresh:
        request.app.state.metrics.event("copilot_action", "duplicate")
        reply = "Already done: this was saved the first time you confirmed it."
        return ConfirmResult(status="duplicate", reply=reply, result=claim.result or {})
    saved, reply = await actions.execute(body.action, fields, data, user.id)
    result = (
        {"id": saved.get("id")}
        if body.action == "create_transaction"
        else {"monthly_budget": saved.get("monthly_budget")}
    )
    await actions.finish(data, user.id, body.idempotency_key, result, claim.stored)
    # The change must show in the next answer
    request.app.state.insights_cache.pop(f"{user.id}:{today.isoformat()}")
    request.app.state.user_context_cache.pop(user.id)
    request.app.state.metrics.event("copilot_action", body.action)
    logger.info("copilot action=%s done", body.action)
    return ConfirmResult(status="done", reply=reply, result=result)


def _history_errors(err: Exception) -> HTTPException:
    if isinstance(err, history.ThreadNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Conversation history is unavailable")


@router.get("/threads", response_model=list[ThreadSummary])
async def threads(user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)):
    try:
        return await history.list_threads(data)
    except history.HistoryUnavailable as err:
        raise _history_errors(err) from err


@router.get("/threads/{thread_id}", response_model=list[StoredMessage])
async def thread(
    thread_id: UUID, user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)
):
    try:
        messages = await history.thread_messages(data, thread_id)
    except (history.HistoryUnavailable, history.ThreadNotFound) as err:
        raise _history_errors(err) from err
    # The hidden context block is for the server's follow-ups, not for display
    return [
        {**m, "blocks": [b for b in m.get("blocks") or [] if b.get("type") != "context"]} for m in messages
    ]


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID, user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)
) -> None:
    try:
        await history.delete_thread(data, thread_id)
    except (history.HistoryUnavailable, history.ThreadNotFound) as err:
        raise _history_errors(err) from err
