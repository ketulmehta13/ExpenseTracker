"""Writing the answer, and checking it before anyone sees it as final.

- Data (B): template sentences over the tool facts. No model involved, so the figures are exact.
- Knowledge (A): the LLM answers from numbered passages. The answer must cite at least one
  passage, only passages it was given, and every number must appear in a passage it cites.
- Combined (C): the same, plus the user's figures, which the model writes as [placeholders]
  that code fills in; any digit it writes itself must come from a cited passage.
Anything that fails a check, a timeout, a rate limit or a missing LLM falls back to a
deterministic answer: the facts' template sentences and/or the best passage, quoted and cited.
When the evidence is insufficient the copilot says so instead of guessing.

Streaming: tokens are sent as they arrive, with [placeholders] filled in on the fly; the final
event carries the checked text, which replaces the streamed text if the check failed.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from app.copilot.facts import Facts
from app.copilot.prompts import (
    COMBINED_PROMPT,
    INSUFFICIENT,
    KNOWLEDGE_PROMPT,
    format_facts,
    format_sources,
)
from app.copilot.schemas import Citation, CitationsBlock
from app.llm.verify import numbers_in
from app.rag.kb_retriever import Evidence, Retrieval

logger = logging.getLogger("ml_service.copilot")

MAX_ANSWER_CHARS = 1200
_SOURCE_REF = re.compile(r"\[S(\d+)\]")
_PLACEHOLDER = re.compile(r"\[([a-z][a-z0-9_]*)\]")
_MARKUP = re.compile(r"<[a-zA-Z/!?]|```|^#{1,6} ", re.MULTILINE)

NO_EVIDENCE = (
    "I couldn't find that in my knowledge base, so I'd rather not guess. I can explain budgeting, saving, "
    "debt and investing basics, help with using the app, or look at your own spending."
)
UNAVAILABLE = (
    "My knowledge base isn't reachable right now, so I can't answer that reliably. Questions about your "
    "own spending still work."
)

Delta = Callable[[str], Awaitable[None]]


@dataclass
class Answer:
    text: str
    answered_by: str  # "template", "llm", "extractive", "fixed"
    grounded: bool
    citations: list[Citation] = field(default_factory=list)

    def blocks(self) -> list:
        return [CitationsBlock(items=self.citations)] if self.citations else []


def _citation(n: int, e: Evidence) -> Citation:
    return Citation(
        n=n,
        ref=e.ref,
        title=e.title,
        section=e.section,
        source=e.source,
        source_url=e.source_url,
        topic=e.topic,
        version=e.version,
        excerpt=e.content[:400],
    )


def check_answer(text: str, evidence: list[Evidence], facts: Facts | None = None) -> Answer | None:
    """The model's answer with placeholders filled, or None if it breaks a rule."""
    text = " ".join(text.split())
    if not text or INSUFFICIENT in text or len(text) > MAX_ANSWER_CHARS or _MARKUP.search(text):
        return None
    cited = sorted({int(n) for n in _SOURCE_REF.findall(text)})
    if not cited or any(n < 1 or n > len(evidence) for n in cited):
        return None
    names = _PLACEHOLDER.findall(text)
    values = facts.values if facts else {}
    if any(name not in values for name in names):
        return None
    # Digits the model wrote itself must come from the passages it cites
    own = _PLACEHOLDER.sub(" ", _SOURCE_REF.sub(" ", text))
    allowed = numbers_in(
        " ".join(
            f"{evidence[n - 1].title} {evidence[n - 1].section} {evidence[n - 1].content}" for n in cited
        )
    )
    if not numbers_in(own) <= allowed:
        return None
    filled = _PLACEHOLDER.sub(lambda m: values[m[1]], text)
    return Answer(filled, "llm", True, [_citation(n, evidence[n - 1]) for n in cited])


def extractive(evidence: list[Evidence], sentences: int = 2) -> Answer:
    best = evidence[0]
    parts = re.split(r"(?<=[.!?])\s+", best.content.strip())
    return Answer(" ".join(parts[:sentences]) + " [S1]", "extractive", True, [_citation(1, best)])


def data_answer(facts: Facts) -> Answer:
    return Answer(" ".join(facts.sentences), "template", True)


class _Filler:
    """Fills [placeholders] in a token stream as soon as the closing bracket arrives."""

    def __init__(self, values: dict[str, str]):
        self.values, self.pending = values, ""

    def feed(self, token: str) -> str:
        self.pending += token
        out = []
        while self.pending:
            start = self.pending.find("[")
            if start == -1:
                out.append(self.pending)
                self.pending = ""
                break
            out.append(self.pending[:start])
            end = self.pending.find("]", start)
            if end == -1:
                self.pending = self.pending[start:]
                if len(self.pending) > 40:  # not a placeholder after all
                    out.append(self.pending)
                    self.pending = ""
                break
            name = self.pending[start + 1 : end]
            out.append(self.values.get(name, self.pending[start : end + 1]))
            self.pending = self.pending[end + 1 :]
        return "".join(out)

    def flush(self) -> str:
        rest, self.pending = self.pending, ""
        return rest


async def _generate(
    model: BaseChatModel, prompt, inputs: dict, timeout: float, on_delta: Delta | None, values: dict[str, str]
) -> str:
    chain = prompt | model | StrOutputParser()
    if on_delta is None:
        return await asyncio.wait_for(chain.ainvoke(inputs), timeout)
    filler, parts = _Filler(values), []

    async def emit(text: str) -> None:
        if text:
            await on_delta(text)

    async def run() -> None:
        # Hold the first characters back until they can't be the start of "INSUFFICIENT",
        # which is a signal to the code, not something to show
        held = True
        async for token in chain.astream(inputs):
            parts.append(token)
            if held:
                so_far = "".join(parts)
                if len(so_far.strip()) <= len(INSUFFICIENT):
                    continue
                held = False
                if not so_far.strip().startswith(INSUFFICIENT):
                    await emit(filler.feed(so_far))
                continue
            if not "".join(parts).strip().startswith(INSUFFICIENT):
                await emit(filler.feed(token))
        so_far = "".join(parts)
        if held and so_far.strip() and not so_far.strip().startswith(INSUFFICIENT):
            await emit(filler.feed(so_far))  # a very short answer
        await emit(filler.flush())

    await asyncio.wait_for(run(), timeout)
    return "".join(parts)


async def knowledge_answer(
    model: BaseChatModel | None,
    question: str,
    retrieval: Retrieval,
    timeout: float,
    on_delta: Delta | None = None,
) -> Answer:
    if retrieval.mode == "unavailable":
        return Answer(UNAVAILABLE, "fixed", False)
    if not retrieval.sufficient:
        return Answer(NO_EVIDENCE, "fixed", True)
    if model is None:
        return extractive(retrieval.evidence)
    try:
        text = await _generate(
            model,
            KNOWLEDGE_PROMPT,
            {"sources": format_sources(retrieval.evidence), "question": question},
            timeout,
            on_delta,
            {},
        )
    except Exception as err:  # timeouts, rate limits (429), provider errors
        logger.warning("copilot knowledge answer failed: %s", type(err).__name__)
        return extractive(retrieval.evidence)
    if INSUFFICIENT in text:
        return Answer(NO_EVIDENCE, "fixed", True)
    checked = check_answer(text, retrieval.evidence)
    if checked is None:
        logger.warning("copilot knowledge answer rejected by the grounding check")
    return checked or extractive(retrieval.evidence)


async def combined_answer(
    model: BaseChatModel | None,
    question: str,
    facts: Facts,
    retrieval: Retrieval,
    timeout: float,
    on_delta: Delta | None = None,
) -> Answer:
    data = data_answer(facts)
    if not retrieval.sufficient or not retrieval.evidence:
        return Answer(data.text, "template", True)  # the user's numbers, without advice we can't ground
    if model is None:
        tip = extractive(retrieval.evidence)
        return Answer(f"{data.text} {tip.text}", "extractive", True, tip.citations)
    inputs = {
        "facts": format_facts(facts),
        "sources": format_sources(retrieval.evidence),
        "question": question,
    }
    try:
        text = await _generate(model, COMBINED_PROMPT, inputs, timeout, on_delta, facts.values)
    except Exception as err:
        logger.warning("copilot combined answer failed: %s", type(err).__name__)
        text = ""
    checked = check_answer(text, retrieval.evidence, facts) if text else None
    if checked is None:
        if text:
            logger.warning("copilot combined answer rejected by the grounding check")
        tip = extractive(retrieval.evidence)
        return Answer(f"{data.text} {tip.text}", "extractive", True, tip.citations)
    return checked
