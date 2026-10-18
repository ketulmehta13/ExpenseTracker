"""The assistant's API: POST /v1/assistant/chat and POST /v1/assistant/confirm.

Each conversation is a LangGraph thread keyed by the signed-in user's id plus the client's
thread id, so one user can never read or resume another user's conversation.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.assistant.graph import AssistantContext
from app.assistant.router import merchant_keys_from
from app.auth import CurrentUser, get_current_user
from app.dates import resolve_today
from app.routers.categorize import suggest_category
from app.routers.help import CitationOut, get_help_index
from app.routers.insights import load_insights
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])
logger = logging.getLogger("ml_service.assistant")

_THREAD_ID = r"^[A-Za-z0-9_-]{1,64}$"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    thread_id: str = Field(default_factory=lambda: uuid4().hex, pattern=_THREAD_ID)
    today: date | None = None


class ConfirmRequest(BaseModel):
    thread_id: str = Field(pattern=_THREAD_ID)
    approve: bool
    today: date | None = None


class Draft(BaseModel):
    title: str
    amount: float
    date: date
    type: str
    category_id: int | str | None
    category_name: str | None


class AssistantReply(BaseModel):
    thread_id: str
    intent: str
    reply: str
    citations: list[CitationOut] = []
    pending: Draft | None = Field(None, description="A transaction waiting for the user to confirm")
    saved: dict | None = Field(None, description="The transaction that was just saved")


async def _run_config(request: Request, user: CurrentUser, data: SupabaseData, thread_id: str, today: date):
    inputs = await load_insights(request, user, data, today)
    settings = request.app.state.settings

    async def suggest(title: str, amount: float | None, tx_type: str):
        return (await suggest_category(request, user, data, title, amount, tx_type)).suggestion

    async def save(draft: dict) -> dict:
        row = {key: draft[key] for key in ("title", "amount", "date", "type", "category_id")}
        row |= {"user_id": user.id, "notes": "", "is_recurring": False}
        saved = await data.insert("transactions", row)
        # The new transaction must show up in the next answer
        request.app.state.insights_cache.pop(f"{user.id}:{today.isoformat()}")
        request.app.state.user_context_cache.pop(user.id)
        return saved

    context = AssistantContext(
        today=today,
        transactions=inputs.transactions,
        categories=inputs.categories,
        merchant_keys=merchant_keys_from(inputs.transactions),
        insights=inputs.insights,
        help_index=lambda: get_help_index(request),
        llm=request.app.state.llm,
        timeout=settings.llm_timeout_seconds,
        suggest_category=suggest,
        save_transaction=save,
    )
    return {"configurable": {"thread_id": f"{user.id}:{thread_id}", "context": context}}


def _reply(thread_id: str, result: dict) -> AssistantReply:
    pending = result.get("draft") if result.get("__interrupt__") else None
    return AssistantReply(
        thread_id=thread_id,
        intent=result.get("understanding", {}).get("intent", "help"),
        reply=result.get("reply") or ("Should I add this?" if pending else ""),
        citations=[CitationOut(**citation) for citation in result.get("citations") or []],
        pending=Draft(**pending) if pending else None,
        saved=result.get("saved"),
    )


@router.post("/chat", response_model=AssistantReply)
async def chat(
    body: ChatRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> AssistantReply:
    graph = request.app.state.assistant_graph
    config = await _run_config(request, user, data, body.thread_id, resolve_today(body.today))
    if (await graph.aget_state(config)).interrupts:
        # A new message instead of an answer to the pending confirmation counts as "no"
        await graph.ainvoke(Command(resume={"approve": False}), config)
    result = await graph.ainvoke({"message": body.message}, config)
    reply = _reply(body.thread_id, result)
    request.app.state.metrics.event("assistant", reply.intent)
    return reply


@router.post("/confirm", response_model=AssistantReply)
async def confirm(
    body: ConfirmRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> AssistantReply:
    graph = request.app.state.assistant_graph
    config = await _run_config(request, user, data, body.thread_id, resolve_today(body.today))
    if not (await graph.aget_state(config)).interrupts:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting for confirmation")
    result = await graph.ainvoke(Command(resume={"approve": body.approve}), config)
    logger.info("assistant confirm approve=%s saved=%s", body.approve, bool(result.get("saved")))
    request.app.state.metrics.event("assistant_confirm", "saved" if result.get("saved") else "cancelled")
    return _reply(body.thread_id, result)
