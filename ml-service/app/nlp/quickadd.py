"""Natural-language quick add: "swiggy 450 yesterday" -> title, amount, date and type.

Rule-based slot filling. Each slot has its own patterns, applied in a fixed order to the raw
text, and every match is blanked out before the next slot looks, so a number used in a date
can never also become the amount:

1. Date: relative words (today, yesterday, kal, 2 days ago, last friday) and explicit dates
   (3rd oct, oct 3, 12/10, 2026-10-01). Numeric dates are day first, as written in India,
   and a date without a year is the most recent one in the past: expenses have happened.
2. Amount: Indian digit grouping (1,25,000), decimals, k / lakh / crore, and currency markers
   (₹, rs, inr, /-). With several numbers, a currency marker wins, then the largest
   ("2 coffees 300" -> 300).
3. Type: income cue words (received, salary, refund, cashback...), except when they describe
   paying someone ("maid salary").
4. Title: whatever is left, minus filler words at its edges ("paid ... for", "spent ... on").

Why rules rather than a model: there is no labelled data yet, the slots have rigid formats,
and every decision can be explained and unit-tested. Step 6 adds an LLM fallback for what the
rules miss.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
SCALES = {"k": 1e3, "thousand": 1e3, "l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
          "cr": 1e7, "crore": 1e7, "crores": 1e7}

INCOME_WORDS = {
    "received", "receive", "credited", "salary", "stipend", "bonus", "refund", "refunded", "cashback",
    "income", "earned", "interest", "dividend", "sold", "reimbursement", "incentive",
}
# "maid salary" or "driver bonus" is money paid out, not earned
PAYEE_ROLES = {"maid", "driver", "cook", "nanny", "watchman", "staff", "servant", "bai", "helper", "gardener"}
# Dropped from the edges of the title: "paid 500 for groceries at dmart" -> "groceries at dmart"
EDGE_FILLERS = {
    "paid", "pay", "spent", "spend", "bought", "buy", "got", "received", "receive", "credited", "sold",
    "sent", "for", "on", "at", "to", "from", "of", "the", "a", "an", "and", "via", "by", "rs", "rs.", "inr",
}

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_WEEKDAY = "|".join(sorted(WEEKDAYS, key=len, reverse=True))
_ON = r"(?:on\s+)?(?:the\s+)?"
_ORDINAL = r"(?:st|nd|rd|th)"

_ISO_DATE = re.compile(rf"\b{_ON}(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})\b")
# 12/10, 12-10-2026, 12.10.26 (dots need the year, so "10.10" stays an amount)
_NUMERIC_DATE = re.compile(
    rf"\b{_ON}(\d{{1,2}})"
    r"(?:([/-])(\d{1,2})(?:\2(\d{2}|\d{4}))?"  # 12/10 or 12-10-2026
    r"|\.(\d{1,2})\.(\d{2}|\d{4}))\b"  # 12.10.26
)
_DAY_MONTH = re.compile(
    rf"\b{_ON}(\d{{1,2}}){_ORDINAL}?\s*(?:of\s+)?({_MONTH})\b(?:,?\s*(\d{{4}}|\d{{2}})\b)?"
)
_MONTH_DAY = re.compile(rf"\b{_ON}({_MONTH})\s+(\d{{1,2}}){_ORDINAL}?\b(?:,?\s*(\d{{4}}))?")
_ORDINAL_DAY = re.compile(rf"\b{_ON}(\d{{1,2}}){_ORDINAL}\b")
_DAYS_AGO = re.compile(r"\b(\d+|a|one|two|three|four|five|six|seven)\s+(day|days|week|weeks)\s+ago\b")
_WEEKDAY_DATE = re.compile(rf"\b(?:(last|this|past|on)\s+)?({_WEEKDAY})\b")
_RELATIVE = [
    (re.compile(r"\bday before yesterday\b"), 2),
    (re.compile(r"\b(?:yesterday|yday|yest|ystrdy|kal)\b"), 1),
    (re.compile(r"\bparso\b"), 2),
    (re.compile(r"\b(?:today|tdy|aaj)\b"), 0),
    (re.compile(r"\blast\s+week\b"), 7),
]
_WORD_NUMBERS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

_AMOUNT = re.compile(
    r"(?<![\w.,/])(?P<prefix>(?:₹|rs\.?|inr)\s*)?"
    r"(?P<number>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    rf"(?:\s?(?P<scale>{'|'.join(sorted(SCALES, key=len, reverse=True))})(?![a-z]))?"
    r"(?P<suffix>\s*(?:/-|rs\b\.?|inr\b|rupees?\b))?"
    r"(?![a-z0-9])"
)


@dataclass(frozen=True)
class ParsedEntry:
    title: str
    amount: float | None
    date: date
    type: str  # "EXPENSE" or "INCOME"
    # Which slots came from the text rather than a default (today, expense)
    found: dict[str, bool] = field(default_factory=dict)


class _Text:
    """The input with a removal mask: matched spans are blanked out for later slots."""

    def __init__(self, text: str):
        self.original = text
        self.working = text.lower()
        self.removed = [False] * len(text)

    def remove(self, start: int, end: int) -> None:
        self.working = self.working[:start] + " " * (end - start) + self.working[end:]
        for index in range(start, end):
            self.removed[index] = True

    def remainder(self) -> str:
        return "".join(" " if gone else char for char, gone in zip(self.original, self.removed, strict=True))


def _past_date(year: int | None, month: int, day: int, today: date) -> date | None:
    """A valid date; without a year, the most recent one that isn't in the future."""
    try:
        if year is not None:
            return date(year, month, day)
        candidate = date(today.year, month, day)
        return candidate if candidate <= today else date(today.year - 1, month, day)
    except ValueError:
        return None


def _year(text: str | None, today: date) -> int | None:
    if not text:
        return None
    year = int(text) + (2000 if len(text) == 2 else 0)
    return year if abs(year - today.year) <= 1 else -1  # -1: not a plausible year here


def _find_date(text: _Text, today: date) -> date | None:
    for pattern, days_back in _RELATIVE:
        if match := pattern.search(text.working):
            text.remove(*match.span())
            return today - timedelta(days=days_back)

    if match := _DAYS_AGO.search(text.working):
        count = _WORD_NUMBERS.get(match[1]) or int(match[1])
        text.remove(*match.span())
        return today - timedelta(days=count * (7 if match[2].startswith("week") else 1))

    match = _ISO_DATE.search(text.working)
    if match and (found := _past_date(int(match[1]), int(match[2]), int(match[3]), today)):
        text.remove(*match.span())
        return found

    for match in _NUMERIC_DATE.finditer(text.working):
        day = int(match[1])
        month = int(match[3] or match[5])
        year = _year(match[4] or match[6], today)
        if year != -1 and (found := _past_date(year, month, day, today)):
            text.remove(*match.span())
            return found

    for pattern, day_group, month_group in ((_DAY_MONTH, 1, 2), (_MONTH_DAY, 2, 1)):
        for match in pattern.finditer(text.working):
            year = _year(match[3], today)
            span_end = match.end() if year != -1 else match.end(2)  # an implausible "year" is the amount
            month, day = MONTHS[match[month_group]], int(match[day_group])
            found = _past_date(year if year != -1 else None, month, day, today)
            if found:
                text.remove(match.start(), span_end)
                return found

    if match := _ORDINAL_DAY.search(text.working):
        # "on the 20th": this month's 20th, or last month's if this month's hasn't come yet
        day = int(match[1])
        last_month = today.replace(day=1) - timedelta(days=1)
        found = None
        if 1 <= day <= today.day:
            found = today.replace(day=day)
        elif day <= calendar.monthrange(last_month.year, last_month.month)[1]:
            found = last_month.replace(day=day)
        if found:
            text.remove(*match.span())
            return found

    for match in _WEEKDAY_DATE.finditer(text.working):
        prefix, name = match[1], match[2]
        if name == "sun" and not prefix:
            continue  # "sun" alone is too often not a day (sun pharma, sunscreen)
        days_back = (today.weekday() - WEEKDAYS[name]) % 7
        if days_back == 0 and prefix == "last":
            days_back = 7
        text.remove(*match.span())
        return today - timedelta(days=days_back)
    return None


def amounts_in(text: str) -> list[float]:
    """Every amount-like number written in `text`, e.g. to check an LLM didn't invent one."""
    return [
        float(match["number"].replace(",", "")) * SCALES.get(match["scale"] or "", 1.0)
        for match in _AMOUNT.finditer(" ".join(text.split()).lower())
    ]


def _find_amount(text: _Text) -> float | None:
    candidates = []
    for match in _AMOUNT.finditer(text.working):
        value = float(match["number"].replace(",", "")) * SCALES.get(match["scale"] or "", 1.0)
        if value > 0:
            marked = bool(match["prefix"] or match["suffix"])
            candidates.append((marked, value, match.span()))
    if not candidates:
        return None
    # A currency marker wins; otherwise the largest number ("2 coffees 300" -> 300)
    _, value, span = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    text.remove(*span)
    return round(value, 2)


def _find_type(words: list[str]) -> str | None:
    for index, word in enumerate(words):
        if word in INCOME_WORDS:
            if word in {"salary", "bonus"} and index > 0 and words[index - 1] in PAYEE_ROLES:
                continue
            return "INCOME"
    if "got" in words and "from" in words:  # "got 2000 from dad"
        return "INCOME"
    return None


def _clean_title(remainder: str) -> str:
    words = [word.strip(",:;-–") for word in remainder.split()]
    words = [word for word in words if word]
    while words and words[0].lower() in EDGE_FILLERS:
        words.pop(0)
    while words and words[-1].lower() in EDGE_FILLERS:
        words.pop()
    title = " ".join(words)
    return title[:1].upper() + title[1:]


def parse_quick_add(text: str, today: date) -> ParsedEntry:
    """Fill the transaction slots from one line of free text."""
    working = _Text(" ".join(text.split()))
    parsed_date = _find_date(working, today)
    amount = _find_amount(working)
    tx_type = _find_type(working.working.split())
    return ParsedEntry(
        title=_clean_title(working.remainder()),
        amount=amount,
        date=parsed_date or today,
        type=tx_type or "EXPENSE",
        found={"amount": amount is not None, "date": parsed_date is not None, "type": tx_type is not None},
    )
