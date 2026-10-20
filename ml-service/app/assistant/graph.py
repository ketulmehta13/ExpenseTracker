"""The assistant as a LangGraph state machine.

    START -> understand -> one of: spending | breakdown | budget | subscriptions | unusual |
                                   help | greeting | about | draft -> confirm (pauses for the user) -> END

A finance assistant should be predictable, so this is a workflow with explicit routing rather
than a free-running agent loop: each message is understood once (rules first, an LLM only for
phrasing the rules don't recognise), exactly one tool answers it, and anything that changes
data goes through a human-in-the-loop step. `interrupt()` pauses the graph with the draft
transaction; nothing is saved until the user confirms and the graph is resumed.

State is checkpointed per conversation thread. That gives the assistant memory ("and last
month?" reuses the previous question) and lets a paused confirmation resume on a later
request. Per-request objects (the user's data, today's date, the models) travel in the run's
config, never in the checkpoint.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from app.assistant import tools
from app.assistant.router import INTENTS, Period, Understanding, classify, understand
from app.llm.extract import checked_fields, llm_draft, merge, needs_llm
from app.llm.general import general_answer
from app.llm.summary import money
from app.nlp.quickadd import parse_quick_add
from app.rag.answer import answer_question
from app.rag.retriever import HelpIndex

logger = logging.getLogger("ml_service.assistant")
_COMMAND = re.compile(r"^(add|log|record|note|track|save|enter)\s+", re.IGNORECASE)


class AssistantState(TypedDict, total=False):
    message: str
    understanding: dict  # the latest Understanding, as plain data, for follow-ups
    reply: str
    citations: list[dict]
    draft: dict | None  # a transaction waiting for the user's confirmation
    saved: dict | None


@dataclass
class AssistantContext:
    """Everything a run needs that must not be checkpointed."""

    today: date
    transactions: list[dict]
    categories: list[dict]
    merchant_keys: set[str]
    insights: object  # app.routers.insights.InsightsResponse
    help_index: Callable[[], HelpIndex]
    llm: BaseChatModel | None
    timeout: float
    suggest_category: Callable[[str, float | None, str], Awaitable[object | None]]
    save_transaction: Callable[[dict], Awaitable[dict]]


def _context(config: RunnableConfig) -> AssistantContext:
    return config["configurable"]["context"]


def _to_state(understanding: Understanding) -> dict:
    data = asdict(understanding)
    if understanding.period:
        data["period"] = {**data["period"], "start": understanding.period.start.isoformat(),
                          "end": understanding.period.end.isoformat()}
    return data


def _from_state(data: dict | None) -> Understanding | None:
    if not data:
        return None
    period = data.get("period")
    if period:
        period = Period(period["key"], date.fromisoformat(period["start"]), date.fromisoformat(period["end"]),
                        period["label"])
    return Understanding(
        data["intent"], period, data.get("category"), data.get("merchant"), bool(data.get("follow_up"))
    )


class _LLMIntent(BaseModel):
    intent: Literal[
        "spending", "breakdown", "budget", "subscriptions", "unusual", "add", "help", "greeting", "about"
    ]


_INTENT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Classify a message sent to a personal finance app's assistant into one intent:\n"
        "spending (how much was spent, for a period, category or merchant); breakdown (the biggest "
        "categories); budget (budget status or the month-end forecast); subscriptions (recurring payments "
        "and bills); unusual (unusual payments); add (record a new transaction); help (how to use the "
        "app); greeting; about (questions about the assistant itself, small talk, or anything unrelated to "
        "personal finance or the app). Reply with JSON only.\n{format_instructions}",
    ),
    ("human", "{message}"),
])


async def llm_intent(model: BaseChatModel, message: str, timeout: float) -> str | None:
    parser = PydanticOutputParser(pydantic_object=_LLMIntent)
    chain = _INTENT_PROMPT.partial(format_instructions=parser.get_format_instructions()) | model | parser
    try:
        return (await asyncio.wait_for(chain.ainvoke({"message": message}), timeout)).intent
    except Exception as err:
        logger.warning("llm intent failed: %s", type(err).__name__)
        return None


async def understand_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx = _context(config)
    message = state["message"]
    previous = _from_state(state.get("understanding"))
    result = understand(message, ctx.today, ctx.categories, ctx.merchant_keys, previous)
    if classify(message) is None and not result.follow_up and ctx.llm is not None:
        # Rules didn't recognise the phrasing: let the LLM pick the intent; the slots still come from rules
        intent = await llm_intent(ctx.llm, message, ctx.timeout)
        if intent in INTENTS and intent != "help":
            period = result.period
            if intent in ("spending", "breakdown") and period is None:
                period = understand("this month", ctx.today, [], set()).period
            result = Understanding(intent, period, result.category, result.merchant)
    logger.info("assistant intent=%s follow_up=%s", result.intent, result.follow_up)
    return {"understanding": _to_state(result), "reply": "", "citations": [], "draft": None, "saved": None}


async def spending_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx, u = _context(config), _from_state(state["understanding"])
    result = tools.spending(ctx.transactions, u.period, u.category, u.merchant)
    return {"reply": tools.spending_reply(result, u.period, u.category, u.merchant)}


async def breakdown_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx, u = _context(config), _from_state(state["understanding"])
    rows = tools.breakdown(ctx.transactions, ctx.categories, u.period)
    return {"reply": tools.breakdown_reply(rows, u.period)}


async def budget_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    return {"reply": tools.budget_reply(_context(config).insights)}


async def subscriptions_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    return {"reply": tools.subscriptions_reply(_context(config).insights)}


async def unusual_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    return {"reply": tools.unusual_reply(_context(config).insights)}


async def greeting_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    return {"reply": tools.greeting_reply(state["message"])}


async def about_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx, message = _context(config), state["message"]
    if reply := tools.small_talk_reply(message):
        return {"reply": reply}
    # Not about the assistant: with an LLM, a general money question still gets an answer
    general = await general_answer(ctx.llm, message, ctx.timeout) if ctx.llm is not None else None
    return {"reply": general or tools.about_reply(message)}


async def help_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx = _context(config)
    answer = await answer_question(ctx.help_index(), state["message"], ctx.llm, ctx.timeout)
    # Not in the help center: a general money question ("what is a SIP?") can still be answered
    general = None
    if answer.source == "not_found" and ctx.llm is not None:
        general = await general_answer(ctx.llm, state["message"], ctx.timeout)
    if general:
        return {"reply": general, "citations": []}
    return {"reply": answer.text, "citations": [asdict(citation) for citation in answer.citations]}


async def draft_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    ctx = _context(config)
    # "add 450 swiggy yesterday": the command word is not part of the transaction
    text = _COMMAND.sub("", state["message"].strip())
    parsed = parse_quick_add(text, ctx.today)
    if ctx.llm is not None and needs_llm(parsed):
        draft = await llm_draft(ctx.llm, text, ctx.today, ctx.timeout)
        if draft is not None:
            parsed, _ = merge(parsed, checked_fields(draft, text, ctx.today))
    if parsed.amount is None or not parsed.title:
        return {"reply": "I couldn't find an amount and a title in that. Try \"add 450 swiggy yesterday\"."}
    suggestion = await ctx.suggest_category(parsed.title, parsed.amount, parsed.type)
    has_category = suggestion is not None and suggestion.category_id is not None
    return {"draft": {
        "title": parsed.title,
        "amount": parsed.amount,
        "date": parsed.date.isoformat(),
        "type": parsed.type,
        "category_id": suggestion.category_id if has_category else None,
        "category_name": suggestion.category_name if has_category else None,
    }}


async def confirm_node(state: AssistantState, config: RunnableConfig) -> AssistantState:
    draft = state["draft"]
    # Pause here until the user answers; on resume, interrupt() returns their decision
    decision = interrupt({"draft": draft})
    if not decision.get("approve"):
        return {"reply": "Okay, I didn't save it.", "draft": None}
    saved = await _context(config).save_transaction(draft)
    kind = "income" if draft["type"] == "INCOME" else "expense"
    reply = f"Saved {kind}: {draft['title']}, {money(draft['amount'])} on {tools._short_date(draft['date'])}."
    return {"reply": reply, "saved": saved, "draft": None}


def build_graph():
    builder = StateGraph(AssistantState)
    builder.add_node("understand", understand_node)
    handlers = {
        "spending": spending_node, "breakdown": breakdown_node, "budget": budget_node,
        "subscriptions": subscriptions_node, "unusual": unusual_node, "help": help_node,
        "greeting": greeting_node, "about": about_node, "add": draft_node,
    }
    for intent, node in handlers.items():
        builder.add_node(intent, node)
    builder.add_node("confirm", confirm_node)

    builder.add_edge(START, "understand")
    builder.add_conditional_edges("understand", lambda state: state["understanding"]["intent"],
                                  {intent: intent for intent in handlers})
    for intent in handlers:
        if intent != "add":
            builder.add_edge(intent, END)
    builder.add_conditional_edges("add", lambda state: "confirm" if state.get("draft") else END,
                                  {"confirm": "confirm", END: END})
    builder.add_edge("confirm", END)
    # In-process memory: enough for one server. More instances would share a Postgres or Redis checkpointer.
    return builder.compile(checkpointer=InMemorySaver())
