"""Answer a help question from retrieved help-center sections, with citations.

1. Out of scope? If the question isn't close to anything in the help center (embedding
   similarity below a threshold chosen on the dev questions, app/rag/retriever.py), say so
   instead of guessing.
2. Retrieve the best sections (hybrid search).
3. Without an LLM, answer extractively: the opening of the best section, cited.
4. With an LLM, ask for one to three sentences that cite the numbered sources, then check
   the answer before showing it: it must cite at least one source, only sources it was given,
   and every number in it must appear in the sources it cites. Otherwise the extractive
   answer is used. This is retrieval-augmented generation (RAG) with a grounding check.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.verify import numbers_in
from app.rag.retriever import HelpIndex, Hit

logger = logging.getLogger("ml_service.rag")

SOURCES = 3
MAX_ANSWER_CHARS = 700
NOT_FOUND = "I couldn't find that in the help center. Try rephrasing, or ask about using the app."
_CITATION = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Citation:
    article: str
    title: str
    section: str


@dataclass(frozen=True)
class HelpAnswer:
    text: str
    source: Literal["llm", "extractive", "not_found"]
    citations: list[Citation] = field(default_factory=list)


def _cite(hit: Hit) -> Citation:
    return Citation(hit.chunk.article, hit.chunk.title, hit.chunk.section)


def extractive_answer(hit: Hit, sentences: int = 2) -> str:
    """The opening sentences of the best section."""
    parts = re.split(r"(?<=[.!?])\s+", hit.chunk.body)
    return " ".join(parts[:sentences])


_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You answer questions about the Expense Tracker app using only the numbered help-center sources.\n"
        "Answer in one to three sentences and cite the sources you used, like [1] or [2].\n"
        "Every number in your answer must appear in a source you cite. If the sources don't answer "
        "the question, reply exactly: I don't know.",
    ),
    ("human", "Sources:\n{sources}\n\nQuestion: {question}"),
])


def checked_llm_answer(text: str, hits: list[Hit]) -> HelpAnswer | None:
    """The model's answer if it cites real sources and only their numbers, else None."""
    text = " ".join(text.split())
    cited = sorted({int(number) for number in _CITATION.findall(text)})
    if not cited or any(number < 1 or number > len(hits) for number in cited) or len(text) > MAX_ANSWER_CHARS:
        return None
    source_numbers = numbers_in(" ".join(hits[number - 1].chunk.body for number in cited))
    if not numbers_in(_CITATION.sub(" ", text)) <= source_numbers:
        return None
    return HelpAnswer(text, "llm", [_cite(hits[number - 1]) for number in cited])


async def answer_question(
    index: HelpIndex, question: str, model: BaseChatModel | None, timeout: float
) -> HelpAnswer:
    hits = index.search(question, k=SOURCES)
    if not index.in_scope(question) or not hits or hits[0].score <= 0:
        return HelpAnswer(NOT_FOUND, "not_found")

    fallback = HelpAnswer(extractive_answer(hits[0]), "extractive", [_cite(hits[0])])
    if model is None:
        return fallback
    sources = "\n".join(
        f"[{number}] {hit.chunk.title} > {hit.chunk.section}: {hit.chunk.body}"
        for number, hit in enumerate(hits, start=1)
    )
    try:
        chain = _PROMPT | model | StrOutputParser()
        text = await asyncio.wait_for(chain.ainvoke({"sources": sources, "question": question}), timeout)
    except Exception as err:
        logger.warning("llm help answer failed: %s", type(err).__name__)
        return fallback
    checked = checked_llm_answer(text, hits)
    if checked is None:
        logger.warning("llm help answer rejected (no or invalid citations, or unsupported numbers)")
    return checked or fallback
