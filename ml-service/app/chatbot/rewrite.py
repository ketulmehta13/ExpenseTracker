"""Follow-ups become standalone questions before retrieval.

"how much should it be?" means nothing to a vector search; "how much should an emergency fund
be?" does. With no history, or if the rewrite fails, the question is used as it was asked.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger("ml_service.chatbot")

MAX_TURN_CHARS = 400

REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the user's latest message as one standalone question, using the conversation to "
            'resolve words like "it" or "that". Don\'t answer it. If it already stands alone, or is not '
            "related to the conversation, return it unchanged. Reply with the question only.",
        ),
        ("human", "Conversation:\n{history}\n\nLatest message: {question}"),
    ]
)


def format_history(messages: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {str(m['content'])[:MAX_TURN_CHARS]}" for m in messages)


async def standalone_question(
    llm: BaseChatModel, question: str, messages: list[dict], timeout: float = 10.0
) -> str:
    if not messages:
        return question
    chain = REWRITE_PROMPT | llm | StrOutputParser()
    try:
        inputs = {"history": format_history(messages), "question": question}
        rewritten = " ".join((await asyncio.wait_for(chain.ainvoke(inputs), timeout)).split())
    except Exception as err:  # timeouts, rate limits: the original question still works
        logger.warning("question rewrite failed: %s", type(err).__name__)
        return question
    return rewritten[:1000] or question
