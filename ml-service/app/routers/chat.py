"""The chatbot's API.

    POST   /chat                 one question -> the answer and its sources (JSON)
    POST   /chat/stream          the same as server-sent events: meta, delta..., final (or error)
    GET    /chat/threads         the user's saved conversations
    GET    /chat/threads/{id}    one conversation's messages
    DELETE /chat/threads/{id}    delete a conversation

Each question: follow-ups are rewritten to stand alone; questions about the user's own money go
to the calculators (read with their token, so row level security applies); everything else, and
the advice part of a mixed question, goes through the RAG chain. The Groq key stays on the server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
from app.chatbot.chain import FALLBACK, answer_chain, check_answer, format_docs, is_dont_know, sources_from
from app.chatbot.rewrite import standalone_question
from app.dates import resolve_today
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("ml_service.chatbot")

_THANKS = re.compile(r"^(thanks|thank you|thx|ty)\b[\s\w]{0,20}[.!]*$", re.IGNORECASE)
_GREETING = re.compile(
    r"^(hi+|hello+|hey+|namaste|good (morning|afternoon|evening))\b[\s\w]{0,12}[.!]*$", re.IGNORECASE
)
GREETING_REPLY = (
    "Hi! Ask me about your spending, budgeting and saving, or how to use the app. "
    'For example: "How much did I spend on food last month?"'
)
UNAVAILABLE = (
    "The chatbot can only answer questions about your own spending right now. Please try again later."
)
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
    answered_by: Literal["documents", "your_data", "both", "fixed"]
    history_saved: bool


class ThreadSummary(BaseModel):
    id: UUID
    title: str
    updated_at: str


class StoredMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    blocks: list[dict]
    created_at: str


@dataclass
class Result:
    reply: str
    answered_by: str
    sources: list[dict] = field(default_factory=list)


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


async def _answer(
    request: Request,
    data: SupabaseData,
    user: CurrentUser,
    message: str,
    messages: list[dict],
    today: date,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> Result:
    if _THANKS.match(message.strip()):
        return Result("You're welcome!", "fixed")
    if _GREETING.match(message.strip()):
        return Result(GREETING_REPLY, "fixed")

    state, settings = request.app.state, request.app.state.settings
    llm, retriever = state.chat_llm, state.chat_retriever
    question = await standalone_question(llm, message, messages) if llm is not None else message

    figures = ""
    data_question = data_answers.classify(question, today)
    if data_question is not None:
        computed = await data_answers.answer(data_question, data, user.id, today)
        figures = computed.text
        if not computed.wants_advice:
            return Result(figures, "your_data")
        if on_delta:
            await on_delta(figures + " ")

    if llm is None or retriever is None:
        if figures:
            return Result(figures, "your_data")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)

    parts: list[str] = []
    try:
        docs = await asyncio.wait_for(retriever.ainvoke(question), settings.chat_timeout_seconds)
        context = format_docs(docs)
        inputs = {"context": context, "question": question}

        async def generate() -> None:
            async for token in answer_chain(llm).astream(inputs):
                parts.append(token)
                if on_delta:
                    await on_delta(token)

        await asyncio.wait_for(generate(), settings.chat_timeout_seconds)
    except Exception as err:  # timeouts, rate limits, provider errors: never a raw error for the user
        logger.warning("chat answer failed: %s", type(err).__name__)
        state.metrics.event("chat", "ai_failed")
        return Result(f"{figures} {AI_FAILED}".strip(), "your_data" if figures else "fixed")

    answer = check_answer("".join(parts), context, question)
    if answer == FALLBACK or is_dont_know(answer):
        return Result(figures or FALLBACK, "your_data" if figures else "fixed")
    sources = sources_from(docs)
    return Result(f"{figures} {answer}".strip(), "both" if figures else "documents", sources)


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
    if history_ok and thread_id is not None:
        try:
            await history.save_turn(data, thread_id, body.message, result.reply, result.sources, user.id)
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
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def on_delta(text: str) -> None:
            await queue.put(text)

        async def run() -> Result:
            try:
                return await _answer(request, data, user, body.message, messages, today, on_delta)
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while (text := await queue.get()) is not None:
                yield _sse("delta", {"text": text})
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
