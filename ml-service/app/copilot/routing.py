"""Deciding how to answer a message: knowledge (RAG), the user's data (tools), both, or an action.

    A  knowledge   "Explain the 50/30/20 budgeting rule"           -> retrieve, grounded answer
    B  data        "How much did I spend on food last month?"       -> analytics tool, exact figures
    C  combined    "My food spending went up. Why, and what budget method helps?"
                                                                    -> tools first, then retrieval
    D  unsupported anything the knowledge base and the user's data can't answer -> say so
       action      "add 450 swiggy yesterday", "set my budget to 30000" -> a proposal to confirm
       small_talk  "hi", "who made you?"

Rules first: they are predictable, fast and testable (training/data/copilot_*.jsonl), and they
reuse the assistant's slot filling (periods, the user's categories and merchants, follow-ups).
Only when the rules find nothing does an LLM, if configured, pick a tool through LangChain tool
calling; it can choose only from the allowlist (app/copilot/tools.py), with validated arguments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.assistant.router import Understanding, classify, parse_period, understand
from app.assistant.tools import small_talk_reply
from app.nlp.quickadd import amounts_in

Route = Literal["knowledge", "data", "combined", "action", "small_talk", "unsupported"]

_COMPARE = re.compile(
    r"\bcompare|\bvs\.?\b|\bversus\b|\bthan (last|usual|before|previous)|\bincreas|\bdecreas|\bwent (up|down)"
    r"|\bgone (up|down)|\bgo(es)? (up|down)|\bhigher\b|\blower\b|\bjump(ed)?\b|\bdropp?(ed)?\b|\bdifference\b"
)
# Asking for an explanation, advice or a method, rather than (only) a number
_KNOWLEDGE_CUE = re.compile(
    r"\bwhy\b|\bexplain|\bsuggest|\brecommend|\btips?\b|\badvice\b|\bmethod|\bstrateg|\brule\b|\bidea"
    r"|\bhow (can|do|should|could) i (reduce|cut|save|control|stop|lower|manage|plan|budget|fix)"
    r"|\bwhat should i do\b|\bhelp me (save|budget|plan|reduce|cut)|\bhow much should\b|\bshould i\b"
)
_DEFINITION = re.compile(r"^(what|what's|whats) (is|are)\b|\bmeaning\b|\bdefin|\bwhat does .* mean\b")
_PERSONAL = re.compile(r"\b(my|i|me|mine|i'm|i've|am i|did i)\b")
_SPENDING_WORDS = re.compile(
    r"\bspen[dt]|\bspending\b|\bexpens|\bkharch|\bbudget\b|\bpaying\b|\bpaid\b|\bfund\b"
)
_UNUSUAL_WORDS = re.compile(r"\bflag|\bunusual|\bstrange|\bsuspicious|\bweird\b|\banomal")
_SUMMARY_WORDS = re.compile(
    r"\bsavings? rate\b|\bsaved\b|\bincome\b|\bearn(ed|ing)?\b|\bnet\b|\bcash ?flow\b"
)
_BUDGET_UPDATE = re.compile(
    r"\b(set|change|update|make|increase|decrease|raise|lower)\b.{0,30}\bbudget\b.{0,20}?\bto\b"
    r"|\bbudget\b.{0,20}\bto\s*(rs\.?|₹|inr)?\s*\d"
)
_DATA_TOOL = {
    "spending": "get_expense_summary",
    "breakdown": "get_category_breakdown",
    "budget": "get_budget_status",
    "subscriptions": "detect_recurring_expenses",
    "unusual": "get_unusual_payments",
}
# Knowledge topics worth searching for each kind of personal question in a combined answer
_TOPICS_FOR = {
    "get_expense_summary": ["budgeting", "saving", "cash-flow"],
    "get_category_breakdown": ["budgeting", "saving", "cash-flow"],
    "compare_expense_periods": ["cash-flow", "budgeting", "saving"],
    "get_budget_status": ["budgeting", "saving", "app-help"],
    "detect_recurring_expenses": ["saving", "debt", "app-help"],
    "get_unusual_payments": ["app-help", "cash-flow"],
}


@dataclass(frozen=True)
class Plan:
    route: Route
    understanding: Understanding
    tools: list[str] = field(default_factory=list)  # read tools to run, in order
    topics: list[str] | None = None  # knowledge topics to search (None: all)
    action: Literal["create_transaction", "update_budget"] | None = None
    reason: str = ""


def plan(
    text: str,
    today: date,
    categories: list[dict],
    merchant_keys: set[str],
    previous: Understanding | None = None,
) -> Plan:
    t = " ".join(text.lower().split())
    u = understand(text, today, categories, merchant_keys, previous)
    rule_intent = classify(text)

    if _BUDGET_UPDATE.search(t) and amounts_in(t):
        return Plan("action", u, action="update_budget", reason="budget update")
    if rule_intent == "add":
        return Plan("action", u, action="create_transaction", reason="add a transaction")
    if rule_intent == "greeting" or (rule_intent == "about" and small_talk_reply(text)):
        return Plan("small_talk", u, reason=rule_intent)
    if rule_intent == "about":  # weather, jokes, stock tips...: outside what the copilot can answer
        return Plan("unsupported", u, reason="off-topic")

    wants_knowledge = bool(_KNOWLEDGE_CUE.search(t))
    personal = bool(_PERSONAL.search(t)) or u.follow_up
    has_period = parse_period(text, today) is not None
    compare = bool(_COMPARE.search(t)) and (
        u.intent in ("spending", "breakdown", "budget") or personal or has_period
    )
    data_intent = u.intent if u.intent in _DATA_TOOL and (rule_intent is not None or u.follow_up) else None

    tools: list[str] = []
    if compare and (data_intent or personal or has_period):
        tools = ["compare_expense_periods"]
    elif personal and _UNUSUAL_WORDS.search(t):
        tools = ["get_unusual_payments"]
    elif personal and _SUMMARY_WORDS.search(t):
        tools = ["get_expense_summary"]
    elif personal and wants_knowledge and (u.category or u.merchant or _SPENDING_WORDS.search(t)):
        # "I spend too much on shopping, how can I cut it?": their numbers first, then advice
        tools = ["get_expense_summary", "compare_expense_periods"]
    elif data_intent:
        tools = [_DATA_TOOL[data_intent]]
        if data_intent == "spending" and wants_knowledge:
            tools.append("get_category_breakdown")  # explaining spending needs its parts

    if tools and not personal and (wants_knowledge or _DEFINITION.search(t)):
        tools = []  # "explain the 50/30/20 budget rule" is about budgeting, not about my budget
    if tools and wants_knowledge and personal:
        return Plan("combined", u, tools=tools, topics=_TOPICS_FOR[tools[0]], reason="data + knowledge")
    if tools:
        return Plan("data", u, tools=tools, reason=data_intent or "compare")
    # Questions about how the app works keep their help-center articles in the running
    return Plan("knowledge", u, reason="knowledge")
