"""Grounding: an LLM may phrase a result, never produce its numbers.

Language models are good at wording and bad at arithmetic, and they will confidently write a
number that was never in their input. Checking each number the model writes against the
known facts is the usual guard, but it can't tell when a real number lands next to the wrong
words: this project's own evaluation planted wrong numbers and found two that passed, each
within 1% of a different fact.

So the model never writes numbers at all. It writes [placeholders] such as [spent], code
substitutes the values it computed, and any digit the model writes itself rejects the text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

PLACEHOLDER = re.compile(r"\[([a-z_]+)\]")
_DIGIT = re.compile(r"\d")
_NUMBER = re.compile(r"(?<![\w.,])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.,])\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[float]:
    """The numbers written in `text`, with Indian or Western digit grouping: "₹1,25,000" -> 125000."""
    return {float(match.replace(",", "")) for match in _NUMBER.findall(text)}


def fill_placeholders(text: str, values: dict[str, str], names: Iterable[str] = ()) -> str | None:
    """`text` with each [placeholder] replaced by its value, or None if the text can't be trusted:
    it uses a placeholder that has no value, or writes a digit itself. Digits inside the given
    names (a merchant called "Tata 1mg") are allowed."""
    if any(name not in values for name in PLACEHOLDER.findall(text)):
        return None
    own_words = PLACEHOLDER.sub(" ", text)
    for name in names:
        own_words = re.sub(re.escape(name), " ", own_words, flags=re.IGNORECASE)
    if _DIGIT.search(own_words):
        return None
    return PLACEHOLDER.sub(lambda match: values[match[1]], text)
