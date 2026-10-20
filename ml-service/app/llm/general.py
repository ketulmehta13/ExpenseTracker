"""General money questions the help center doesn't cover, answered by the LLM when one is configured.

"How do I build an emergency fund?" or "what is a SIP?" aren't about using the app, so help
search declines them. With an LLM, the assistant answers them briefly instead. The model gets
only the question: none of the user's data, so it can't state (or invent) their numbers.
Anything that isn't about money or the app is still declined, and an answer that fails the
checks (too long, empty, the off-topic marker) falls back to the rule-based reply.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger("ml_service.llm")

OFF_TOPIC = "OFF_TOPIC"
MAX_ANSWER_CHARS = 900

_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are the assistant inside Expense Tracker, a personal finance app for people in India, made by "
        "Ketul Mehta. Answer general questions about personal finance, budgeting, saving, spending habits, "
        "loans and money terms in two to four short, plain sentences, using ₹ for money.\n"
        "Never recommend a specific stock, fund, card or product. For investing or tax questions, explain "
        "the idea and say it isn't financial advice.\n"
        "You can't see the user's own transactions here: if they ask about their spending, tell them to ask "
        "something like \"how much did I spend this month?\".\n"
        f"If the question is not about money, personal finance or the app, reply exactly: {OFF_TOPIC}",
    ),
    ("human", "{question}"),
])


async def general_answer(model: BaseChatModel, question: str, timeout: float) -> str | None:
    """A short answer to a general money question, or None (off-topic, failed or unusable)."""
    try:
        chain = _PROMPT | model | StrOutputParser()
        text = await asyncio.wait_for(chain.ainvoke({"question": question[:500]}), timeout)
    except Exception as err:
        logger.warning("llm general answer failed: %s", type(err).__name__)
        return None
    text = " ".join(text.split())
    if not text or OFF_TOPIC in text or len(text) > MAX_ANSWER_CHARS:
        return None
    return text
