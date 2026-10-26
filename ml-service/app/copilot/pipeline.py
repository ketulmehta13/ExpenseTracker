"""The copilot as a LangGraph workflow.

    START -> route -> data       -> tools ----------------> compose -> END
                   -> combined   -> tools -> retrieve -----> compose -> END
                   -> knowledge  ---------> retrieve -----> compose -> END
                   -> action     -> propose (an action block to confirm)  -> END
                   -> small_talk / unsupported (fixed replies)            -> END

One message is routed once and each step runs at most once: a predictable workflow, not an agent
loop. The LLM is used in two bounded places: wording grounded answers (compose), and, only when
the rules find no tool for a personal question, choosing one allowlisted tool by tool calling.
The graph is stateless; conversation history lives in Supabase (app/copilot/history.py) and per-
request objects (the user's data, the retriever, the model) travel in the run's config.
Streaming: compose sends answer tokens through LangGraph's stream writer as "delta" events.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date
from typing import TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.assistant.router import Period, Understanding, classify
from app.assistant.tools import greeting_reply, small_talk_reply
from app.copilot import tools as t
from app.copilot.actions import propose_budget, propose_transaction
from app.copilot.compose import NO_EVIDENCE, Answer, combined_answer, data_answer, knowledge_answer
from app.copilot.facts import describe
from app.copilot.routing import Plan, plan
from app.rag.kb_retriever import KnowledgeRetriever, Retrieval

logger = logging.getLogger("ml_service.copilot")

UNSUPPORTED = (
    "That's outside what I can help with: I answer questions about your own spending and budget, explain "
    "money topics such as budgeting, saving, debt and investing basics, and help with using the app."
)
_PERSONAL = re.compile(r"\b(my|i|me|am i|did i)\b", re.IGNORECASE)


@dataclass
class CopilotContext:
    data: t.FinanceData
    merchant_keys: set[str]
    retriever: KnowledgeRetriever | None
    llm: BaseChatModel | None
    timeout: float
    suggest_category: Callable[[str, float | None, str], Awaitable[dict | None]]


class CopilotState(TypedDict, total=False):
    message: str
    previous: Understanding | None
    plan: Plan
    picked: tuple[str, dict] | None  # a tool the LLM chose
    results: list
    retrieval: Retrieval | None
    answer: Answer
    blocks: list


def _ctx(config: RunnableConfig) -> CopilotContext:
    return config["configurable"]["copilot"]


def _results(p: Plan, data: t.FinanceData) -> list:
    """Run the planned read tools with the slots the rules found (period, category, merchant)."""
    u = p.understanding
    period: Period = u.period or t.resolve_period(None, data.today)
    out = []
    for name in p.tools:
        if name == "get_expense_summary":
            out.append(t.get_expense_summary(data, period, u.category, u.merchant))
        elif name == "get_category_breakdown":
            out.append(t.get_category_breakdown(data, period))
        elif name == "compare_expense_periods":
            out.append(t.compare_expense_periods(data, period, category=u.category))
        elif name == "get_budget_status":
            out.append(t.get_budget_status(data))
        elif name == "detect_recurring_expenses":
            out.append(t.detect_recurring_expenses(data))
        elif name == "get_unusual_payments":
            out.append(t.get_unusual_payments(data))
    return out


async def llm_pick_tool(model: BaseChatModel, message: str, timeout: float) -> tuple[str, dict] | None:
    """LangChain tool calling over the allowlist; the arguments are validated before running."""
    specs = [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args.model_json_schema(),
            },
        }
        for tool in t.READ_TOOLS.values()
    ]
    system = SystemMessage(
        "You route questions in a personal finance app. If the user's question is about their own money and "
        "one of the tools answers it, call that tool. Otherwise reply with the single word NONE."
    )
    try:
        reply = await asyncio.wait_for(
            model.bind_tools(specs).ainvoke([system, HumanMessage(message)]), timeout
        )
    except Exception as err:
        logger.warning("copilot tool choice failed: %s", type(err).__name__)
        return None
    calls = getattr(reply, "tool_calls", None) or []
    if not calls or calls[0]["name"] not in t.READ_TOOLS:
        return None
    return calls[0]["name"], dict(calls[0].get("args") or {})


async def route_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    ctx = _ctx(config)
    p = plan(state["message"], ctx.data.today, ctx.data.categories, ctx.merchant_keys, state.get("previous"))
    picked = None
    # Only for personal questions the rules didn't recognise at all ("netflix and co, what am i paying for?")
    unrecognised = classify(state["message"]) is None
    if p.route == "knowledge" and ctx.llm is not None and unrecognised and _PERSONAL.search(state["message"]):
        picked = await llm_pick_tool(ctx.llm, state["message"], ctx.timeout)
        if picked:
            p = Plan("data", p.understanding, tools=[], reason=f"llm:{picked[0]}")
    logger.info("copilot route=%s tools=%s", p.route, p.tools or (picked and [picked[0]]))
    return {"plan": p, "picked": picked, "results": [], "retrieval": None, "blocks": []}


async def tools_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    data = _ctx(config).data
    results = _results(state["plan"], data)
    if state.get("picked"):
        name, args = state["picked"]
        try:
            results.append(t.run_tool(name, args, data))
        except (ValueError, TypeError) as err:
            logger.warning("copilot rejected tool arguments from the LLM: %s", err)
    return {"results": results}


async def retrieve_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    ctx = _ctx(config)
    if ctx.retriever is None:
        return {"retrieval": Retrieval([], False, None, "unavailable")}
    topics = state["plan"].topics if state["plan"].route == "combined" else None
    retrieval = await asyncio.to_thread(ctx.retriever.retrieve, state["message"], 4, topics)
    return {"retrieval": retrieval}


async def compose_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    ctx = _ctx(config)
    writer = get_stream_writer()

    async def on_delta(text: str) -> None:
        writer({"delta": text})

    route = state["plan"].route
    facts = describe(state.get("results") or [])
    if route == "knowledge":
        answer = await knowledge_answer(ctx.llm, state["message"], state["retrieval"], ctx.timeout, on_delta)
    elif route == "combined":
        answer = await combined_answer(
            ctx.llm, state["message"], facts, state["retrieval"], ctx.timeout, on_delta
        )
    elif facts.sentences:
        answer = data_answer(facts)
    else:  # an LLM-picked tool whose arguments were rejected
        answer = Answer(NO_EVIDENCE, "fixed", True)
    return {"answer": answer, "blocks": [*facts.blocks, *answer.blocks()]}


async def action_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    ctx, p = _ctx(config), state["plan"]
    if p.action == "update_budget":
        block = propose_budget(state["message"], ctx.data.budget)
        if block is None:
            return {
                "answer": Answer(
                    'What should your monthly budget be? For example: "set my budget to 30000".',
                    "fixed",
                    True,
                )
            }
    else:
        parsed_category = p.understanding.category
        block = propose_transaction(state["message"], ctx.data.today, parsed_category)
        if block is None:
            return {
                "answer": Answer(
                    'I couldn\'t find an amount and a title in that. Try "add 450 swiggy yesterday".',
                    "fixed",
                    True,
                )
            }
        if block.fields.category_id is None:
            suggestion = await ctx.suggest_category(
                block.fields.title, block.fields.amount, block.fields.type
            )
            if suggestion:
                block.fields.category_id, block.fields.category_name = suggestion["id"], suggestion["name"]
                block.summary = block.summary.rstrip(".") + f" in {suggestion['name']}."
    return {
        "answer": Answer(f"{block.summary} Check the details and confirm to save.", "fixed", True),
        "blocks": [block],
    }


async def small_talk_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    message = state["message"]
    reply = small_talk_reply(message) or greeting_reply(message)
    return {"answer": Answer(reply, "fixed", True)}


async def unsupported_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    return {"answer": Answer(UNSUPPORTED, "fixed", True)}


def build_copilot_graph():
    builder = StateGraph(CopilotState)
    for name, node in (
        ("route", route_node),
        ("tools", tools_node),
        ("retrieve", retrieve_node),
        ("compose", compose_node),
        ("action", action_node),
        ("small_talk", small_talk_node),
        ("unsupported", unsupported_node),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        lambda s: s["plan"].route,
        {
            "data": "tools",
            "combined": "tools",
            "knowledge": "retrieve",
            "action": "action",
            "small_talk": "small_talk",
            "unsupported": "unsupported",
        },
    )
    builder.add_conditional_edges(
        "tools",
        lambda s: "retrieve" if s["plan"].route == "combined" else "compose",
        {"retrieve": "retrieve", "compose": "compose"},
    )
    builder.add_edge("retrieve", "compose")
    for name in ("compose", "action", "small_talk", "unsupported"):
        builder.add_edge(name, END)
    return builder.compile()


def understanding_to_dict(u: Understanding) -> dict:
    data = asdict(u)
    if u.period:
        data["period"] = {
            **data["period"],
            "start": u.period.start.isoformat(),
            "end": u.period.end.isoformat(),
        }
    return data


def understanding_from_dict(data: dict | None) -> Understanding | None:
    if not data:
        return None
    period = data.get("period")
    if period:
        period = Period(
            period["key"],
            date.fromisoformat(period["start"]),
            date.fromisoformat(period["end"]),
            period["label"],
        )
    return Understanding(
        data["intent"], period, data.get("category"), data.get("merchant"), bool(data.get("follow_up"))
    )
