"""LLM fallback for quick add: called only when the rules look unsure, and never trusted blindly.

The rules (app/nlp/quickadd.py) handle common formats perfectly and in microseconds, so the LLM
is a fallback, called only when they look unsure: no amount found, or time words left over in
the title ("ola 250 3 days back" -> title "Ola 3 days back"). Its answer must fit a Pydantic
schema, and is then checked against the input before any of it is used:
- the amount must be one of the numbers actually written in the text;
- the date must fall within the past year;
- the title may only use words from the text.
The rules keep every slot they found; checked LLM values only fill the gaps.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from dataclasses import replace
from datetime import date, timedelta
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.nlp.quickadd import ParsedEntry, amounts_in

logger = logging.getLogger("ml_service.llm")

# Left in a title, these suggest the rules missed a date phrase
TIME_WORDS = {
    "ago", "back", "last", "night", "morning", "evening", "afternoon", "tonight", "earlier", "day", "days",
    "week", "weeks", "month", "months",
    "raat", "subah", "shaam", "sham", "dopahar", "pichle", "pichhle", "pehle", "kal", "parso",  # Hinglish
}
_WORD = re.compile(r"[a-z0-9]+")


class LLMDraft(BaseModel):
    title: str = Field(description="What the money was for (merchant or item), using the note's own words")
    amount: float | None = Field(description="The amount in rupees exactly as written in the note, or null")
    # dt.date, not date: inside the class body "date" is this field, not the type
    date: dt.date | None = Field(description="The date the note refers to, YYYY-MM-DD, or null if none")
    type: Literal["EXPENSE", "INCOME"] = Field(description="INCOME only when money was received")


_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You turn a short note from an Indian user into one transaction.\n"
        "Today is {today} ({weekday}). The transaction already happened, so its date is today or earlier.\n"
        "Hindi words: kal = yesterday, parso = the day before yesterday, raat = night, subah = morning.\n"
        "Use only words and numbers that appear in the note. Reply with JSON only.\n"
        "{format_instructions}",
    ),
    ("human", "{text}"),
])


def needs_llm(parsed: ParsedEntry) -> bool:
    return parsed.amount is None or any(word in TIME_WORDS for word in _WORD.findall(parsed.title.lower()))


async def llm_draft(model: BaseChatModel, text: str, today: date, timeout: float) -> LLMDraft | None:
    """The model's reading of the note, or None if it fails, times out or returns invalid JSON."""
    parser = PydanticOutputParser(pydantic_object=LLMDraft)
    chain = _PROMPT.partial(format_instructions=parser.get_format_instructions()) | model | parser
    try:
        return await asyncio.wait_for(
            chain.ainvoke({"text": text, "today": today.isoformat(), "weekday": f"{today:%A}"}), timeout
        )
    except Exception as err:  # a failed fallback must never break quick add: the rules' answer stands
        logger.warning("llm extraction failed: %s", type(err).__name__)
        return None


def checked_fields(draft: LLMDraft, text: str, today: date) -> dict:
    """The parts of an LLM draft that check out against the note itself."""
    checked: dict = {"type": draft.type}
    if draft.amount is not None and any(abs(draft.amount - value) < 0.005 for value in amounts_in(text)):
        checked["amount"] = draft.amount
    if draft.date is not None and today - timedelta(days=366) <= draft.date <= today:
        checked["date"] = draft.date
    note_words = set(_WORD.findall(text.lower()))
    title_words = _WORD.findall(draft.title.lower())
    if title_words and all(word in note_words for word in title_words):
        title = " ".join(draft.title.split())
        checked["title"] = title[:1].upper() + title[1:]
    return checked


def merge(parsed: ParsedEntry, checked: dict) -> tuple[ParsedEntry, list[str]]:
    """Rules keep what they found; checked LLM values fill only the gaps. Returns the fields filled."""
    updates: dict = {}
    if parsed.amount is None and "amount" in checked:
        updates["amount"] = checked["amount"]
    if not parsed.found.get("date") and checked.get("date") not in (None, parsed.date):
        updates["date"] = checked["date"]
    if not parsed.found.get("type") and checked["type"] != parsed.type:
        updates["type"] = checked["type"]
    leftover_time_words = any(word in TIME_WORDS for word in _WORD.findall(parsed.title.lower()))
    if "title" in checked and leftover_time_words and checked["title"] != parsed.title:
        updates["title"] = checked["title"]
    if not updates:
        return parsed, []
    found = {**parsed.found, **{name: True for name in updates if name in parsed.found}}
    return replace(parsed, **updates, found=found), sorted(updates)
