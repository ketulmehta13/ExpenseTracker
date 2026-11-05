"""The chatbot's API.

    POST   /chat                 one question -> the answer and its sources (JSON)
    POST   /chat/stream          the same as server-sent events: meta, delta..., final (or error)
    GET    /chat/threads         the user's saved conversations
    GET    /chat/threads/{id}    one conversation's messages
    DELETE /chat/threads/{id}    delete a conversation

    POST   /chat/feedback        a thumbs up or down on an answer

Each message: secrets and small talk are answered in code; the model then chooses a tool for the
rest, using the conversation to resolve follow-ups (app/chatbot/router.py). Calculators read with the
user's token, so row level security applies. Everything else, and the advice part of a mixed question,
goes through the RAG chain, then to a labelled general answer if the articles don't cover it. The
Groq key stays on the server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.chatbot import data_answers, history
from app.chatbot.chain import (
    FALLBACK,
    OFF_TOPIC,
    answer_chain,
    check_answer,
    format_docs,
    general_chain,
    is_dont_know,
    sources_from,
    used_documents,
)
from app.chatbot.guardrails import dont_know_reply, fixed_reply, off_topic_reply, profile_field
from app.chatbot.router import decide
from app.dates import resolve_today
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("ml_service.chatbot")

UNAVAILABLE = "I can only answer questions about your own spending right now. Please try again later."
HOLD_BACK_CHARS = 16
AI_FAILED = "I can't reach the AI service right now. Please try again in a moment."


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    thread_id: UUID | None = None
    today: date | None = None


class Source(BaseModel):
    title: str
    section: str
    source: str
    url: str | None
    excerpt: str


class ChatReply(BaseModel):
    thread_id: UUID | None
    reply: str
    sources: list[Source]
    answered_by: Literal["documents", "your_data", "both", "general", "fixed"]
    history_saved: bool
    blocks: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    message_id: int | None = None


class FeedbackRequest(BaseModel):
    message_id: int
    rating: Literal["up", "down"]


class ThreadSummary(BaseModel):
    id: UUID
    title: str
    updated_at: str


class StoredMessage(BaseModel):
    id: int | None = None
    role: Literal["user", "assistant"]
    content: str
    blocks: list[dict]
    created_at: str


@dataclass
class Result:
    reply: str
    answered_by: str
    sources: list[dict] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _limit(request: Request, user: CurrentUser) -> None:
    wait = request.app.state.chat_limiter.check(user.id)
    if wait is not None:
        request.app.state.metrics.event("chat", "rate_limited")
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many messages; please wait a moment",
            headers={"Retry-After": str(int(wait) + 1)},
        )


async def _open(data: SupabaseData, body: ChatRequest) -> tuple[UUID | None, list[dict], bool]:
    """The thread, its recent messages, and whether history is working."""
    try:
        thread_id = await history.open_thread(data, body.thread_id, body.message)
        return thread_id, await history.recent_messages(data, thread_id), True
    except history.ThreadNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found") from err
    except history.HistoryUnavailable as err:
        logger.warning("chat history unavailable: %s", err)
        return None, [], False


async def _profile_reply(field_name: str, data: SupabaseData, user: CurrentUser) -> str:
    if field_name == "email":
        return f"You're signed in as {user.email}." if user.email else "I can't see your email right now."
    params = {"select": "username,first_name,last_name", "id": f"eq.{user.id}"}
    rows = await data.select("profiles", params, limit=1)
    profile = rows[0] if rows else {}
    full = " ".join(p for p in (profile.get("first_name"), profile.get("last_name")) if p)
    name = full or profile.get("username")
    return f"You're signed in as {name}." if name else "I don't have your name. You can add it in Settings."


async def _stream_answer(
    chain,
    inputs: dict,
    on_delta: Callable[[str | None], Awaitable[None]] | None,
    timeout: float,
    hidden: tuple[str, ...],
) -> str:
    """The model's full text, streamed as it arrives. The first characters are held back until they
    can't become a signal to the code ("I don't know", OFF_TOPIC), so the user never sees those."""
    parts: list[str] = []
    held = True

    async def generate() -> None:
        nonlocal held
        async for token in chain.astream(inputs):
            parts.append(token)
            if on_delta is None:
                continue
            if held:
                so_far = "".join(parts)
                if len(so_far.strip()) < HOLD_BACK_CHARS:
                    continue
                held = False
                if not so_far.strip().strip('"').lower().startswith(hidden):
                    await on_delta(so_far)
                continue
            if not "".join(parts).strip().strip('"').lower().startswith(hidden):
                await on_delta(token)

    await asyncio.wait_for(generate(), timeout)
    return "".join(parts)


async def _answer(
    request: Request,
    data: SupabaseData,
    user: CurrentUser,
    message: str,
    messages: list[dict],
    today: date,
    on_delta: Callable[[str | None], Awaitable[None]] | None = None,
) -> Result:
    fixed = fixed_reply(message)
    if fixed is not None:
        return Result(fixed.text, "fixed", suggestions=fixed.suggestions)
    if field_name := profile_field(message):
        return Result(await _profile_reply(field_name, data, user), "fixed")

    state, settings = request.app.state, request.app.state.settings
    llm, retriever = state.chat_llm, state.chat_retriever
    route = await decide(llm, message, messages, today)
    state.metrics.event("chat_route", route.by)
    if route.kind == "off_topic":
        reply = off_topic_reply(message)
        return Result(reply.text, "fixed", suggestions=reply.suggestions)

    figures, blocks, suggestions, query = "", [], [], route.query or message
    if route.kind == "data":
        computed = await data_answers.answer(route.data_question, data, user.id, today)
        figures, blocks, suggestions = computed.text, computed.blocks, computed.suggestions
        if not computed.wants_advice:
            return Result(figures, "your_data", blocks=blocks, suggestions=suggestions)
        query = route.data_question.advice_query or message
        if on_delta:
            await on_delta(figures + " ")

    def only_figures(reply: str = "") -> Result:
        text = f"{figures} {reply}".strip()
        return Result(text, "your_data", blocks=blocks, suggestions=suggestions)

    if llm is None or retriever is None:
        if figures:
            return only_figures()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)

    timeout = settings.chat_timeout_seconds
    try:
        docs = await asyncio.wait_for(retriever.ainvoke(query), timeout)
        context = format_docs(docs)
        raw = await _stream_answer(
            answer_chain(llm), {"context": context, "question": query}, on_delta, timeout, ("i don't know",)
        )
    except Exception as err:  # timeouts, rate limits, provider errors: never a raw error for the user
        logger.warning("chat answer failed: %s", type(err).__name__)
        state.metrics.event("chat", "ai_failed")
        return only_figures(AI_FAILED) if figures else Result(AI_FAILED, "fixed")

    answer = check_answer(raw, context, query)
    if answer != FALLBACK and not is_dont_know(answer):
        embeddings = getattr(getattr(retriever, "vectorstore", None), "embeddings", None)
        used = await asyncio.to_thread(used_documents, answer, docs, embeddings) if embeddings else docs[:1]
        return Result(
            f"{figures} {answer}".strip(),
            "both" if figures else "documents",
            sources_from(used),
            blocks,
            suggestions,
        )

    # The articles don't cover it (or the answer failed the number check): a labelled general answer
    if on_delta:
        await on_delta(None)
        if figures:
            await on_delta(figures + " ")
    try:
        general = await _stream_answer(
            general_chain(llm), {"question": query}, on_delta, timeout, ("off_topic",)
        )
    except Exception as err:
        logger.warning("general answer failed: %s", type(err).__name__)
        general = ""
    general = " ".join(general.split())
    if general and OFF_TOPIC not in general:
        return Result(f"{figures} {general}".strip(), "general", blocks=blocks, suggestions=suggestions)
    state.metrics.event("chat", "dont_know")
    if figures:
        return only_figures()
    reply = dont_know_reply(message)
    return Result(reply.text, "fixed", suggestions=reply.suggestions)


async def _finish(
    request: Request,
    data: SupabaseData,
    user: CurrentUser,
    body: ChatRequest,
    result: Result,
    thread_id: UUID | None,
    history_ok: bool,
    started: float,
) -> ChatReply:
    message_id = None
    if history_ok and thread_id is not None:
        blocks = [*result.blocks, *([{"type": "sources", "items": result.sources}] if result.sources else [])]
        try:
            message_id = await history.save_turn(data, thread_id, body.message, result.reply, blocks, user.id)
        except history.HistoryUnavailable as err:
            logger.warning("chat history not saved: %s", err)
            history_ok = False
    request.app.state.metrics.event("chat", result.answered_by)
    # No message text and no figures in the logs
    logger.info("chat answered_by=%s ms=%d", result.answered_by, (time.perf_counter() - started) * 1000)
    return ChatReply(
        thread_id=thread_id if history_ok else None,
        reply=result.reply,
        sources=[Source(**source) for source in result.sources],
        answered_by=result.answered_by,
        history_saved=history_ok,
        blocks=result.blocks,
        suggestions=result.suggestions,
        message_id=message_id,
    )


@router.post("", response_model=ChatReply)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> ChatReply:
    _limit(request, user)
    started = time.perf_counter()
    today = resolve_today(body.today)
    thread_id, messages, history_ok = await _open(data, body)
    result = await _answer(request, data, user, body.message, messages, today)
    return await _finish(request, data, user, body, result, thread_id, history_ok, started)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> StreamingResponse:
    _limit(request, user)
    started = time.perf_counter()
    today = resolve_today(body.today)
    # Errors before the stream starts (auth, rate limit, unknown thread) are normal HTTP errors
    thread_id, messages, history_ok = await _open(data, body)

    async def events() -> AsyncIterator[str]:
        yield _sse("meta", {"thread_id": str(thread_id) if thread_id else None})
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        async def on_delta(text: str | None) -> None:
            await queue.put(("reset", "") if text is None else ("delta", text))

        async def run() -> Result:
            try:
                return await _answer(request, data, user, body.message, messages, today, on_delta)
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while (item := await queue.get()) is not None:
                yield _sse(item[0], {"text": item[1]})
            result = await task
            reply = await _finish(request, data, user, body, result, thread_id, history_ok, started)
            # The final text is the checked one: it replaces whatever was streamed
            yield _sse("final", reply.model_dump(mode="json"))
        except HTTPException as err:
            yield _sse("error", {"message": str(err.detail)})
        except Exception as err:
            logger.warning("chat stream failed: %s", type(err).__name__)
            yield _sse("error", {"message": "Something went wrong while answering. Please try again."})
        finally:
            task.cancel()  # the user pressed Stop or left: don't keep spending the Groq quota

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def feedback(
    body: FeedbackRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> None:
    try:
        await history.save_feedback(data, body.message_id, body.rating, user.id)
    except history.HistoryUnavailable as err:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Feedback is unavailable") from err
    request.app.state.metrics.event("chat_feedback", body.rating)


def _history_error(err: Exception) -> HTTPException:
    if isinstance(err, history.ThreadNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Saved conversations are unavailable")


@router.get("/threads", response_model=list[ThreadSummary])
async def threads(user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)):
    try:
        return await history.list_threads(data)
    except history.HistoryUnavailable as err:
        raise _history_error(err) from err


@router.get("/threads/{thread_id}", response_model=list[StoredMessage])
async def thread(
    thread_id: UUID, user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)
):
    try:
        return await history.thread_messages(data, thread_id)
    except (history.HistoryUnavailable, history.ThreadNotFound) as err:
        raise _history_error(err) from err


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID, user: CurrentUser = Depends(get_current_user), data: SupabaseData = Depends(get_data)
) -> None:
    try:
        await history.delete_thread(data, thread_id)
    except (history.HistoryUnavailable, history.ThreadNotFound) as err:
        raise _history_error(err) from err
