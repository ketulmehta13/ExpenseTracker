"""Understanding a message: which tool should answer it (the intent) and with what (the slots).

Intents are recognised by ordered rules, most specific first. Questions about using the app
("what does unusual spending mean?", "how is the forecast calculated?") are checked before
data intents, because they mention the same words. Slots are a period ("last month", "in
September", "pichle mahine"), one of the user's own categories (directly or through an alias:
"groceries" is Food) and a merchant from the user's own history ("swiggy").

Follow-ups use the conversation's memory: "and this month?" after a spending question keeps
the intent and the category and only changes the period.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.ml.recurring import merchant_key
from app.ml.taxonomy import CANONICAL_CATEGORIES, match_user_category
from app.nlp.quickadd import amounts_in

INTENTS = ("spending", "breakdown", "budget", "subscriptions", "unusual", "add", "help", "greeting")
DATA_INTENTS = {"spending", "breakdown"}  # the intents that take a period and filters

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

_GREETING = re.compile(r"^(hi+|hello|hey|namaste|thanks|thank you|thx|good (morning|afternoon|evening))\b")
_HELP = re.compile(
    r"\bhow (do|can|should) i\b|\bhow (is|are|does)\b|\bwhat (does|do) .*\bmean\b|\bwhat(?: is|'s) the\b"
    r"|\b(can|could) i\b|\bwhy (was|were|did|is|am|do|does|can't|cant|isn't)\b"
    r"|\bwhere (do|can) i\b|\bhow to\b"
)
_ADD = re.compile(r"^(add|log|record|note|track|save|enter)\b|^(i )?(spent|paid|bought|got|received)\b")
_SUBSCRIPTIONS = re.compile(r"subscription|recurring|\bbills?\b|\bemis?\b|repeat|autopay|\bdue\b")
_UNUSUAL = re.compile(r"unusual|strange|weird|suspicious|\bodd\b|abnormal|anomal|spike|fraud")
_BUDGET = re.compile(r"budget|on track|over budget|exceed|forecast|projected|projection|end of (the )?month"
                     r"|month[- ]end|\bpace\b")
_BREAKDOWN = re.compile(r"breakdown|by category|top categor|biggest (expense|categor|spend)"
                        r"|most (of )?my money|where did .*\bgo\b|where .*money")
_SPENDING = re.compile(r"how much|\btotal\b|\bspen[dt]|spending|expenses?\b|kharch|\bpaid\b|\bpay\b|cost me")
_FOLLOW_UP = re.compile(r"^(and|what about|how about)\b")


@dataclass(frozen=True)
class Period:
    key: str  # "this_month", "last_7_days", "month:9", ...
    start: date
    end: date
    label: str  # "this month", "in the last 7 days", "in September"


@dataclass(frozen=True)
class Understanding:
    intent: str
    period: Period | None = None
    category: dict | None = None  # the user's category: {"id", "name"}
    merchant: str | None = None  # a merchant key from the user's history
    follow_up: bool = False


def parse_period(text: str, today: date) -> Period | None:
    t = text.lower()
    month_start = today.replace(day=1)
    if re.search(r"\b(today|aaj)\b", t):
        return Period("today", today, today, "today")
    if re.search(r"\b(yesterday|kal)\b", t):
        return Period("yesterday", today - timedelta(days=1), today - timedelta(days=1), "yesterday")
    if match := re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+days?\b", t):
        days = int(match[1])
        start = today - timedelta(days=days - 1)
        return Period(f"last_{days}_days", start, today, f"in the last {days} days")
    if re.search(r"\bthis week\b", t):
        return Period("this_week", today - timedelta(days=today.weekday()), today, "this week")
    if re.search(r"\b(last|previous) week\b", t):
        end = today - timedelta(days=today.weekday() + 1)
        return Period("last_week", end - timedelta(days=6), end, "last week")
    if re.search(r"\b(this month|is mahine|this mahine)\b", t):
        return Period("this_month", month_start, today, "this month")
    if re.search(r"\b(last|previous) month\b|\bpichh?le mahine\b", t):
        end = month_start - timedelta(days=1)
        return Period("last_month", end.replace(day=1), end, "last month")
    if re.search(r"\bthis year\b", t):
        return Period("this_year", today.replace(month=1, day=1), today, "this year")
    if re.search(r"\b(last|previous) year\b", t):
        return Period("last_year", date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year")
    for name, month in _MONTHS.items():
        # "may" is a month only after "in" or "for" ("may I see..." is not)
        pattern = rf"\b(in|for|during|of) {name}\b" if name == "may" else rf"\b{name}\b"
        if re.search(pattern, t):
            year = today.year if month <= today.month else today.year - 1
            start = date(year, month, 1)
            end = min(date(year, month, calendar.monthrange(year, month)[1]), today)
            return Period(f"month:{month}", start, end, f"in {calendar.month_name[month]}")
    return None


def _words(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def match_category(text: str, categories: list[dict]) -> dict | None:
    """One of the user's categories named in the text, directly or through an alias."""
    words = _words(text)
    direct = [c for c in categories if f" {' '.join(re.findall(r'[a-z0-9]+', c['name'].lower()))} " in words]
    if direct:
        return max(direct, key=lambda c: len(c["name"]))
    for label, (_, aliases) in CANONICAL_CATEGORIES.items():
        named = any(f" {alias} " in words for alias in aliases)
        if named and (category := match_user_category(label, categories)):
            return category
    return None


def match_merchant(text: str, merchant_keys: set[str]) -> str | None:
    """A merchant from the user's history named in the text (the longest, if several)."""
    words = _words(text)
    found = [key for key in merchant_keys if key and f" {key} " in words]
    return max(found, key=len) if found else None


def classify(text: str) -> str | None:
    """The intent the rules recognise, or None."""
    t = " ".join(text.lower().split())
    if _GREETING.search(t) and len(t.split()) <= 4:
        return "greeting"
    if _HELP.search(t):
        return "help"
    if _ADD.search(t) and amounts_in(t):
        return "add"
    for intent, pattern in (("subscriptions", _SUBSCRIPTIONS), ("unusual", _UNUSUAL), ("budget", _BUDGET),
                            ("breakdown", _BREAKDOWN), ("spending", _SPENDING)):
        if pattern.search(t):
            return intent
    return None


def understand(
    text: str,
    today: date,
    categories: list[dict],
    merchant_keys: set[str],
    previous: Understanding | None = None,
) -> Understanding:
    intent = classify(text)
    period = parse_period(text, today)
    category = match_category(text, categories)
    merchant = None if category else match_merchant(text, merchant_keys)

    # A follow-up ("and this month?", "what about shopping?") reuses the last data question
    short = len(text.split()) <= 4 or _FOLLOW_UP.search(text.lower().strip())
    if previous and previous.intent in DATA_INTENTS and intent in (None, "spending") and short \
            and (period or category or merchant):
        update = {"period": period or previous.period, "follow_up": True}
        if category or merchant:  # a new filter replaces the old one
            update |= {"category": category, "merchant": merchant}
        return replace(previous, **update)

    intent = intent or "help"  # anything unrecognised goes to the help center, which can decline
    if intent in DATA_INTENTS and period is None:
        period = parse_period("this month", today)
    return Understanding(intent, period, category, merchant)


def merchant_keys_from(transactions: list[dict]) -> set[str]:
    return {merchant_key(tx.get("title")) for tx in transactions if tx.get("type") == "EXPENSE"}
