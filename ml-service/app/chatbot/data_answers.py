"""Questions about the user's own money, answered by code rather than by the model.

Transactions never go into the FAISS index, which every user shares. Instead, questions such as
"how much did I spend on food last month?" are recognised here by rules, and read-only
calculators work out the figure from the user's rows, fetched with their own token so row level
security applies. Sums use Decimal, so they are exact to the paisa.

A question that also asks for advice ("why did my spending go up, and what should I do?") gets
these figures first and then a normal RAG answer. "How do I see my spending?" is about the app,
so it goes to RAG alone.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.supabase import SupabaseData

Kind = Literal["spending", "income", "breakdown", "compare", "budget"]

_MONTHS = {
    name: number
    for number in range(1, 13)
    for name in (calendar.month_name[number].lower(), calendar.month_abbr[number].lower())
}
_ALIASES = {
    "food": ("food", "foods", "grocery", "groceries", "restaurant", "restaurants", "dining", "eating out"),
    "travel": ("travel", "transport", "commute", "commuting", "cab", "cabs", "fuel", "petrol"),
    "utilities": ("utilities", "utility", "electricity", "internet", "phone bill"),
    "shopping": ("shopping", "clothes", "clothing"),
    "entertainment": ("entertainment", "movies", "movie", "ott"),
}

# About using the app, or a general question: for RAG, not the calculators
_HOW_TO = re.compile(
    r"\b(how (do|can|to|does|is|are)|how should|where (do|can|is)|can i|what (does|do) .*\bmean\b"
    r"|what is an?\b|what are(?! my\b)|meaning of|should i|how much should)\b"
)
_ADVICE = re.compile(
    r"\b(why|explain|suggest|recommend|tips?|advice|what should i do"
    r"|how can i (reduce|cut|save|control|stop|lower))\b"
)
_PERSONAL = re.compile(r"\b(my|i|me|i've|i'm)\b")
_COMPARE = re.compile(
    r"\bcompare|\bvs\.?\b|\bversus\b|\bthan (last|usual|before)\b|\bincreas|\bdecreas|\bwent (up|down)\b"
    r"|\bgone (up|down)\b|\bgo(es)? (up|down)\b"
)
_BUDGET = re.compile(
    r"\b(on track|over budget|over my budget|budget (left|status|remaining)|left (of|in) my budget"
    r"|my budget)\b"
)
_BREAKDOWN = re.compile(
    r"\bwhere did\b.*\bmoney\b|\bbreak ?down\b|\bby category\b"
    r"|\b(top|biggest|largest|highest) (categor|expense|spend)|\bmost of my money\b"
)
_INCOME = re.compile(r"\b(earn(ed)?|income|salary|saved?|savings? rate)\b")
_SPENDING = re.compile(
    r"\bspen[dt]\b|\bspending\b|\bexpenses?\b|\bkharch\b|\bpaid\b|\bpay\b|\bcost me\b|\bhow much on\b"
)
_ASKS_AMOUNT = re.compile(r"\bhow much\b|\btotal\b|\bwhat (did|was|were|is|are) (i|my)\b|\bmy\b")
_SUBJECT = re.compile(
    r"\b(?:on|at|for|to)\s+(?:my\s+|the\s+)?([a-z0-9][a-z0-9&' -]*?)\s*(?:$|[?.!,]|\b(?:and|so|or)\b)"
)
_FILLER_SUBJECTS = {"me", "date", "track", "budget", "average", "now", "all", "everything", "it"}


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str


@dataclass(frozen=True)
class DataQuestion:
    kind: Kind
    period: Period
    subject: str | None  # what it was spent on, if named
    wants_advice: bool
    text: str = ""  # the question, lowercased, to spot the user's own category names in


@dataclass(frozen=True)
class DataAnswer:
    text: str
    wants_advice: bool


def _money(value: Decimal) -> str:
    """₹1,25,000 or ₹1,234.50: Indian digit grouping, paise only when there are any."""
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative, value = value < 0, abs(value)
    whole, paise = divmod(int(value * 100), 100)
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *groups, tail] if head else [*groups, tail])
    return f"{'-' if negative else ''}₹{digits}" + (f".{paise:02d}" if paise else "")


def parse_period(text: str, today: date) -> tuple[Period, str]:
    """The period named in the text (this month by default), and the text without it."""
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())

    def days(match: re.Match) -> Period:
        count = max(1, min(int(match[1]), 3660))
        return Period(today - timedelta(days=count - 1), today, f"in the last {count} days")

    named = [
        (r"\b(?:in |for |during )?(?:the )?(?:last|past) (\d{1,4}) days?\b", days),
        (r"\btoday\b", lambda _: Period(today, today, "today")),
        (r"\byesterday\b", lambda _: Period(today - timedelta(1), today - timedelta(1), "yesterday")),
        (r"\b(?:in |for |during )?this week\b", lambda _: Period(week_start, today, "this week")),
        (
            r"\b(?:in |for |during )?(?:last|previous) week\b",
            lambda _: Period(week_start - timedelta(7), week_start - timedelta(1), "last week"),
        ),
        (r"\b(?:in |for |during )?this month\b", lambda _: Period(month_start, today, "this month")),
        (
            r"\b(?:in |for |during )?(?:last|previous) month\b",
            lambda _: Period(last_month_end.replace(day=1), last_month_end, "last month"),
        ),
        (
            r"\b(?:in |for |during )?this year\b",
            lambda _: Period(today.replace(month=1, day=1), today, "this year"),
        ),
        (
            r"\b(?:in |for |during )?(?:last|previous) year\b",
            lambda _: Period(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year"),
        ),
    ]
    for pattern, build in named:
        if match := re.search(pattern, text):
            return build(match), (text[: match.start()] + " " + text[match.end() :]).strip()
    # "in may", "for march": "may" alone is usually the verb
    names = "|".join(sorted(_MONTHS, key=len, reverse=True))
    if match := re.search(rf"\b(?:in|for|during) ({names})\b", text):
        month = _MONTHS[match[1]]
        year = today.year if month <= today.month else today.year - 1
        last_day = calendar.monthrange(year, month)[1]
        end = min(date(year, month, last_day), today)
        period = Period(date(year, month, 1), end, f"in {calendar.month_name[month]}")
        return period, (text[: match.start()] + " " + text[match.end() :]).strip()
    return Period(month_start, today, "this month"), text


def classify(question: str, today: date) -> DataQuestion | None:
    """A question about the user's own money, or None if it's one for RAG."""
    t = " ".join(question.lower().split())
    wants_advice = bool(_ADVICE.search(t))
    if _HOW_TO.search(t) and not wants_advice:
        return None
    period, rest = parse_period(t, today)
    personal = bool(_PERSONAL.search(t))

    if _COMPARE.search(t) and (personal or _SPENDING.search(t) or rest != t):
        kind: Kind = "compare"
    elif _BUDGET.search(t) and personal:
        kind = "budget"
    elif _BREAKDOWN.search(t) and (personal or rest != t):
        kind = "breakdown"
    elif _INCOME.search(t) and personal:
        kind = "income"
    elif _SPENDING.search(t) and (_ASKS_AMOUNT.search(t) or personal):
        kind = "spending"
    else:
        return None
    if wants_advice and not personal:
        return None  # "explain how spending categories work" is a general question

    subject = None
    if kind in ("spending", "compare") and (match := _SUBJECT.search(rest)):
        candidate = match[1].strip()
        if candidate and candidate not in _FILLER_SUBJECTS:
            subject = candidate
    return DataQuestion(kind, period, subject, wants_advice, rest)


def _is_month(period: Period) -> bool:
    return period.label in ("this month", "last month") or (
        period.label.removeprefix("in ") in calendar.month_name
    )


def _previous(period: Period) -> Period:
    """What to compare with: the same days of the month before for a month, else the days before."""
    if _is_month(period):
        end_of_previous = period.start - timedelta(days=1)
        start = end_of_previous.replace(day=1)
        whole = period.end.day == calendar.monthrange(period.end.year, period.end.month)[1]
        end = end_of_previous if whole else min(start + (period.end - period.start), end_of_previous)
        label = f"in {calendar.month_name[start.month]}" + ("" if whole else f" (1–{end.day})")
        return Period(start, end, label)
    length = period.end - period.start
    end = period.start - timedelta(days=1)
    return Period(end - length, end, "the period before")


def _category_ids(subject: str, categories: list[dict]) -> set[str] | None:
    """The user's categories that a word refers to, directly or through a common alias."""
    direct = {str(c["id"]) for c in categories if c["name"].lower() == subject}
    if direct:
        return direct
    for name, aliases in _ALIASES.items():
        if subject in aliases:
            ids = {str(c["id"]) for c in categories if c["name"].lower() == name}
            if ids:
                return ids
    return None


def _named_category(text: str, categories: list[dict]) -> str | None:
    """A category mentioned anywhere in the question: "my food spending went up"."""
    words = f" {' '.join(re.findall(r'[a-z0-9]+', text))} "
    names = [c["name"].lower() for c in categories]
    names += [alias for name, aliases in _ALIASES.items() if name in names for alias in aliases]
    return next((name for name in sorted(names, key=len, reverse=True) if f" {name} " in words), None)


def _total(rows: list[dict]) -> Decimal:
    return sum((Decimal(str(row["amount"])) for row in rows), Decimal(0))


def _within(rows: list[dict], period: Period, kind: str = "EXPENSE") -> list[dict]:
    start, end = period.start.isoformat(), period.end.isoformat()
    return [r for r in rows if r.get("type") == kind and start <= str(r["date"])[:10] <= end]


def _filter(rows: list[dict], subject: str | None, categories: list[dict]) -> list[dict]:
    if not subject:
        return rows
    ids = _category_ids(subject, categories)
    if ids is not None:
        return [r for r in rows if str(r.get("category_id")) in ids]
    return [r for r in rows if subject in str(r.get("title", "")).lower()]


async def _rows(data: SupabaseData, start: date, end: date) -> list[dict]:
    return await data.select(
        "transactions",
        {
            "select": "id,title,amount,type,category_id,date",
            "and": f"(date.gte.{start.isoformat()},date.lte.{end.isoformat()})",
            "order": "date.desc,id.desc",
        },
    )


async def answer(question: DataQuestion, data: SupabaseData, user_id: str, today: date) -> DataAnswer:
    period, subject = question.period, question.subject

    if question.kind == "budget":
        month = Period(today.replace(day=1), today, "this month")
        rows = await _rows(data, month.start, month.end)
        spent = _total(_within(rows, month))
        profiles = await data.select("profiles", {"select": "monthly_budget", "id": f"eq.{user_id}"}, limit=1)
        budget = Decimal(str(profiles[0].get("monthly_budget") or 0)) if profiles else Decimal(0)
        if not budget:
            text = (
                f"You've spent {_money(spent)} so far this month, and you haven't set a monthly budget. "
                "You can set one in Settings."
            )
        elif spent > budget:
            text = (
                f"You've spent {_money(spent)} this month, "
                f"{_money(spent - budget)} over your {_money(budget)} budget."
            )
        else:
            text = (
                f"You've spent {_money(spent)} of your {_money(budget)} budget this month, "
                f"so {_money(budget - spent)} is left."
            )
        return DataAnswer(text, question.wants_advice)

    categories = await data.select("categories", {"select": "id,name", "order": "id"}, limit=1000)
    if not subject and question.kind in ("spending", "compare"):
        subject = _named_category(question.text, categories)
    about = f" on {subject}" if subject else ""

    if question.kind == "compare":
        before = _previous(period)
        rows = await _rows(data, before.start, period.end)
        now_rows = _filter(_within(rows, period), subject, categories)
        before_rows = _filter(_within(rows, before), subject, categories)
        now, then = _total(now_rows), _total(before_rows)
        text = f"You spent {_money(now)}{about} {period.label}, against {_money(then)} {before.label}"
        if now == then:
            text += ", the same."
        else:
            text += f": {_money(abs(now - then))} {'more' if now > then else 'less'}."
        names = {str(c["id"]): c["name"] for c in categories}
        changes: dict[str, Decimal] = defaultdict(Decimal)
        for row in now_rows:
            changes[names.get(str(row.get("category_id")), "Uncategorized")] += Decimal(str(row["amount"]))
        for row in before_rows:
            changes[names.get(str(row.get("category_id")), "Uncategorized")] -= Decimal(str(row["amount"]))
        biggest = sorted((c for c in changes.items() if c[1]), key=lambda c: (-abs(c[1]), c[0]))[:3]
        if biggest and not subject:
            parts = [f"{name} {'up' if d > 0 else 'down'} {_money(abs(d))}" for name, d in biggest]
            text += f" Biggest changes: {', '.join(parts)}."
        return DataAnswer(text, question.wants_advice)

    rows = await _rows(data, period.start, period.end)
    if question.kind == "income":
        income = _total(_within(rows, period, "INCOME"))
        spent = _total(_within(rows, period))
        if not income:
            return DataAnswer(f"You haven't recorded any income {period.label}.", question.wants_advice)
        rate = ((income - spent) / income * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        text = (
            f"You earned {_money(income)} {period.label} and spent {_money(spent)}, "
            f"leaving {_money(income - spent)} (a savings rate of {rate}%)."
        )
        return DataAnswer(text, question.wants_advice)

    expenses = _within(rows, period)
    if question.kind == "breakdown":
        names = {str(c["id"]): c["name"] for c in categories}
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for row in expenses:
            totals[names.get(str(row.get("category_id")), "Uncategorized")] += Decimal(str(row["amount"]))
        if not totals:
            return DataAnswer(f"You haven't spent anything {period.label}.", question.wants_advice)
        overall = sum(totals.values(), Decimal(0))
        top = sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:5]
        parts = [f"{name} {_money(v)} ({(v / overall * 100).quantize(Decimal('1'))}%)" for name, v in top]
        return DataAnswer(
            f"You spent {_money(overall)} {period.label}: {', '.join(parts)}.", question.wants_advice
        )

    matching = _filter(expenses, subject, categories)
    if not matching:
        return DataAnswer(f"You haven't spent anything{about} {period.label}.", question.wants_advice)
    word = "payment" if len(matching) == 1 else "payments"
    return DataAnswer(
        f"You spent {_money(_total(matching))}{about} {period.label} ({len(matching)} {word}).",
        question.wants_advice,
    )
