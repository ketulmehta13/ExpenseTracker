"""Questions about the user's own money, answered by code rather than by the model.

Transactions never go into the FAISS index, which every user shares, and they never reach the
model. A calculator works out each figure from the user's rows, fetched with their own token so
row level security applies. Sums use Decimal, so they are exact to the paisa.

Normally the model picks the calculator (app/chatbot/router.py). classify() below is the backup
for when Groq is unavailable: rules that recognise the common phrasings.

Every answer can carry typed blocks for the panel (cards, bars, rows) and suggested next questions.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.supabase import SupabaseData

Kind = Literal[
    "spending", "income", "summary", "breakdown", "compare", "budget", "largest", "recent", "average"
]

ALL_TIME_START = date(2000, 1, 1)
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
    r"|what is an?\b|what are(?! my\b)|meaning of|should i|how much should"
    r"|can (other|others|anyone|someone)|is my .* (safe|private))\b"
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
    r"|my budget|budget do i have)\b"
)
_BREAKDOWN = re.compile(
    r"\bwhere did\b.*\bmoney\b|\bbreak ?down\b|\bby category\b"
    r"|\b(top|biggest|largest|highest) (categor|expenses\b|spend)|\bmost of my money\b"
)
_LARGEST = re.compile(r"\b(biggest|largest|highest|top|costliest) (payments?|transactions?|purchases?)\b")
_RECENT = re.compile(
    r"\b(recent|latest|last few)\b.{0,12}\b(payments?|transactions?|expenses?)\b|\bmy transactions\b"
)
_AVERAGE = re.compile(r"\baverage\b|\bper day\b|\bdaily spend")
_SUMMARY = re.compile(r"\b(da+ta|summary|overview|report|statement)\b")
_INCOME = re.compile(r"\b(earn(ed|ings?)?|income|salary|credits?|credited|saved?|savings? rate)\b")
_SPENDING = re.compile(
    r"\bspen[dt]\b|\bspending\b|\bexpenses?\b|\bkharch\b|\bpaid\b|\bpay\b|\bcost me\b|\bhow much on\b"
    r"|\bdebits?\b|\bdebited\b"
)
_ASKS_AMOUNT = re.compile(r"\bhow much\b|\btotal\b|\bwhat (did|was|were|is|are) (i|my)\b|\bmy\b|\bgive me\b")
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
    assumed_period: bool = False  # the user named no period, so this month was assumed
    advice_query: str | None = None  # what to search for when advice is wanted too


@dataclass(frozen=True)
class DataAnswer:
    text: str
    wants_advice: bool
    blocks: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def money(value: Decimal) -> str:
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


def all_time(today: date) -> Period:
    return Period(ALL_TIME_START, today, "in total")


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
        (r"\b(?:in )?(?:all[- ]time|overall|so far|ever|lifetime|in total)\b", lambda _: all_time(today)),
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
        return month_period(_MONTHS[match[1]], today), (
            text[: match.start()] + " " + text[match.end() :]
        ).strip()
    return Period(month_start, today, "this month"), text


def month_period(month: int, today: date) -> Period:
    """The most recent such month."""
    year = today.year if month <= today.month else today.year - 1
    last_day = calendar.monthrange(year, month)[1]
    return Period(
        date(year, month, 1), min(date(year, month, last_day), today), f"in {calendar.month_name[month]}"
    )


def wants_advice(question: str) -> bool:
    """Whether the question also asks why, or what to do about it."""
    return bool(_ADVICE.search(" ".join(question.lower().split())))


def classify(question: str, today: date) -> DataQuestion | None:
    """The backup router: a question about the user's own money, or None if it's one for RAG."""
    t = " ".join(question.lower().split())
    wants_advice = bool(_ADVICE.search(t))
    if _HOW_TO.search(t) and not wants_advice:
        return None
    period, rest = parse_period(t, today)
    named_period = rest != t
    personal = bool(_PERSONAL.search(t))

    if _COMPARE.search(t) and (personal or _SPENDING.search(t) or named_period):
        kind: Kind = "compare"
    elif _BUDGET.search(t) and personal:
        kind = "budget"
    elif _LARGEST.search(t) and personal:
        kind = "largest"
    elif _RECENT.search(t) and personal:
        kind = "recent"
    elif _AVERAGE.search(t) and (personal or _SPENDING.search(t)):
        kind = "average"
    elif _BREAKDOWN.search(t) and (personal or named_period):
        kind = "breakdown"
    elif _INCOME.search(t) and (personal or re.search(r"\btotal\b", t)):
        kind = "income"
    elif _SPENDING.search(t) and (_ASKS_AMOUNT.search(t) or personal):
        kind = "spending"
    elif _SUMMARY.search(t) and (personal or named_period):
        kind = "summary"
    else:
        return None
    if wants_advice and not personal:
        return None  # "explain how spending categories work" is a general question

    subject = None
    if kind in ("spending", "compare", "largest") and (match := _SUBJECT.search(rest)):
        candidate = match[1].strip()
        if candidate and candidate not in _FILLER_SUBJECTS:
            subject = candidate
    return DataQuestion(
        kind,
        period,
        subject,
        wants_advice,
        rest,
        assumed_period=not named_period,
        advice_query=question if wants_advice else None,
    )


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


async def _records_note(data: SupabaseData) -> str:
    """Tells "you spent nothing then" apart from "the records don't go back that far"."""
    first = await data.select("transactions", {"select": "date", "order": "date.asc,id.asc"}, limit=1)
    if not first:
        return " You don't have any transactions yet."
    day = date.fromisoformat(str(first[0]["date"])[:10])
    return f" Your records start on {day.day} {day:%b %Y}."


def _nice_date(value) -> str:
    day = date.fromisoformat(str(value)[:10])
    return f"{day.day} {day:%b %Y}"


def _cards(*items: tuple[str, str, str]) -> dict:
    return {"type": "cards", "items": [{"label": a, "value": b, "tone": c} for a, b, c in items]}


def _bars(title: str, points: list[tuple[str, Decimal]]) -> dict:
    return {
        "type": "bars",
        "title": title,
        "points": [
            {"label": label, "value": float(value), "display": money(value)} for label, value in points
        ],
    }


def _table(title: str, rows: list[tuple[str, str, str]]) -> dict:
    return {"type": "rows", "title": title, "rows": [{"a": a, "b": b, "c": c} for a, b, c in rows]}


def _period_choices(question: DataQuestion, template: str) -> list[str]:
    """When the user named no period: one tap away from the others they may have meant."""
    if not question.assumed_period:
        return []
    return [template.format(period=p) for p in ("this year", "in total")]


def _by_category(rows: list[dict], categories: list[dict]) -> list[tuple[str, Decimal]]:
    names = {str(c["id"]): c["name"] for c in categories}
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        totals[names.get(str(row.get("category_id")), "Uncategorized")] += Decimal(str(row["amount"]))
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


async def answer(question: DataQuestion, data: SupabaseData, user_id: str, today: date) -> DataAnswer:
    calculators = {
        "income": _income, "summary": _summary, "compare": _compare,
        "breakdown": _breakdown, "largest": _largest, "recent": _recent, "average": _average,
        "spending": _spending,
    }  # fmt: skip
    if question.kind == "budget":
        return await _budget(question, data, user_id, today)
    categories = await data.select("categories", {"select": "id,name", "order": "id"}, limit=1000)
    if not question.subject and question.kind in ("spending", "compare", "largest"):
        question = replace(question, subject=_named_category(question.text, categories))
    return await calculators[question.kind](question, data, categories, today)


async def _budget(question: DataQuestion, data: SupabaseData, user_id: str, today: date) -> DataAnswer:
    month = Period(today.replace(day=1), today, "this month")
    spent = _total(_within(await _rows(data, month.start, month.end), month))
    profiles = await data.select("profiles", {"select": "monthly_budget", "id": f"eq.{user_id}"}, limit=1)
    budget = Decimal(str(profiles[0].get("monthly_budget") or 0)) if profiles else Decimal(0)
    if not budget:
        text = (
            f"You've spent {money(spent)} so far this month, and you haven't set a monthly budget. "
            "You can set one in Settings."
        )
        return DataAnswer(text, question.wants_advice, suggestions=["Explain the 50/30/20 rule"])
    if spent > budget:
        text = (
            f"You've spent {money(spent)} this month, "
            f"{money(spent - budget)} over your {money(budget)} budget."
        )
        left = _cards(
            ("Spent", money(spent), "expense"),
            ("Budget", money(budget), ""),
            ("Over by", money(spent - budget), "expense"),
        )
    else:
        text = (
            f"You've spent {money(spent)} of your {money(budget)} budget this month, "
            f"so {money(budget - spent)} is left."
        )
        left = _cards(
            ("Spent", money(spent), "expense"),
            ("Budget", money(budget), ""),
            ("Left", money(budget - spent), "income"),
        )
    return DataAnswer(text, question.wants_advice, [left], ["Where did my money go this month?"])


async def _income(question: DataQuestion, data, categories, today) -> DataAnswer:
    period = question.period
    rows = await _rows(data, period.start, period.end)
    income, spent = _total(_within(rows, period, "INCOME")), _total(_within(rows, period))
    suggestions = _period_choices(question, "How much did I earn {period}?")
    if not income:
        note = await _records_note(data)
        return DataAnswer(
            f"You haven't recorded any income {period.label}.{note}",
            question.wants_advice,
            suggestions=suggestions,
        )
    rate = ((income - spent) / income * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = (
        f"You earned {money(income)} {period.label} and spent {money(spent)}, "
        f"leaving {money(income - spent)} (a savings rate of {rate}%)."
    )
    cards = _cards(
        ("Earned", money(income), "income"),
        ("Spent", money(spent), "expense"),
        ("Left", money(income - spent), ""),
        ("Savings rate", f"{rate}%", ""),
    )
    return DataAnswer(text, question.wants_advice, [cards], suggestions)


async def _summary(question: DataQuestion, data, categories, today) -> DataAnswer:
    period = question.period
    rows = await _rows(data, period.start, period.end)
    expenses = _within(rows, period)
    income, spent = _total(_within(rows, period, "INCOME")), _total(expenses)
    if not income and not spent:
        note = await _records_note(data)
        return DataAnswer(
            f"You have no transactions {period.label}.{note}",
            question.wants_advice,
            suggestions=["How much did I spend in total?"],
        )
    top = _by_category(expenses, categories)
    text = (
        f"{period.label.capitalize()}: you earned {money(income)} and spent {money(spent)}, "
        f"leaving {money(income - spent)}."
    )
    if top:
        text += f" Your biggest category was {top[0][0]} at {money(top[0][1])}."
    blocks = [
        _cards(
            ("Earned", money(income), "income"),
            ("Spent", money(spent), "expense"),
            ("Left", money(income - spent), ""),
        )
    ]
    if top:
        blocks.append(_bars("Spending by category", top[:5]))
    return DataAnswer(
        text,
        question.wants_advice,
        blocks,
        ["Compare this month with last month", "How much of my budget is left?"],
    )


async def _compare(question: DataQuestion, data, categories, today) -> DataAnswer:
    period, subject = question.period, question.subject
    about = f" on {subject}" if subject else ""
    before = _previous(period)
    rows = await _rows(data, before.start, period.end)
    now_rows = _filter(_within(rows, period), subject, categories)
    before_rows = _filter(_within(rows, before), subject, categories)
    now, then = _total(now_rows), _total(before_rows)
    text = f"You spent {money(now)}{about} {period.label}, against {money(then)} {before.label}"
    text += (
        ", the same." if now == then else f": {money(abs(now - then))} {'more' if now > then else 'less'}."
    )
    changes: dict[str, Decimal] = defaultdict(Decimal)
    for name, value in _by_category(now_rows, categories):
        changes[name] += value
    for name, value in _by_category(before_rows, categories):
        changes[name] -= value
    biggest = sorted((c for c in changes.items() if c[1]), key=lambda c: (-abs(c[1]), c[0]))[:3]
    if biggest and not subject:
        parts = [f"{name} {'up' if d > 0 else 'down'} {money(abs(d))}" for name, d in biggest]
        text += f" Biggest changes: {', '.join(parts)}."
    cards = _cards(
        (period.label.capitalize(), money(now), "expense"), (before.label.capitalize(), money(then), "")
    )
    return DataAnswer(text, question.wants_advice, [cards], ["Where did my money go this month?"])


async def _breakdown(question: DataQuestion, data, categories, today) -> DataAnswer:
    period = question.period
    expenses = _within(await _rows(data, period.start, period.end), period)
    if not expenses:
        note = await _records_note(data)
        return DataAnswer(f"You haven't spent anything {period.label}.{note}", question.wants_advice)
    top = _by_category(expenses, categories)
    overall = _total(expenses)
    parts = [f"{name} {money(v)} ({(v / overall * 100).quantize(Decimal('1'))}%)" for name, v in top[:5]]
    text = f"You spent {money(overall)} {period.label}: {', '.join(parts)}."
    return DataAnswer(
        text,
        question.wants_advice,
        [_bars("Spending by category", top[:8])],
        ["Show my biggest payments this month"],
    )


async def _largest(question: DataQuestion, data, categories, today) -> DataAnswer:
    period, subject = question.period, question.subject
    about = f" on {subject}" if subject else ""
    expenses = _filter(_within(await _rows(data, period.start, period.end), period), subject, categories)
    if not expenses:
        note = "" if subject else await _records_note(data)
        return DataAnswer(f"You haven't spent anything{about} {period.label}.{note}", question.wants_advice)
    top = sorted(expenses, key=lambda r: -Decimal(str(r["amount"])))[:5]
    first = top[0]
    amount = money(Decimal(str(first["amount"])))
    text = (
        f"Your biggest payment{about} {period.label} was {first['title']}, "
        f"{amount} on {_nice_date(first['date'])}."
    )
    rows = [(str(r["title"]), money(Decimal(str(r["amount"]))), _nice_date(r["date"])) for r in top]
    return DataAnswer(
        text, question.wants_advice, [_table("Biggest payments", rows)], ["Where did my money go this month?"]
    )


async def _recent(question: DataQuestion, data, categories, today) -> DataAnswer:
    rows = await data.select(
        "transactions",
        {"select": "id,title,amount,type,category_id,date", "order": "date.desc,id.desc"},
        limit=5,
    )
    if not rows:
        return DataAnswer("You don't have any transactions yet.", question.wants_advice)
    table = [
        (
            str(r["title"]),
            ("+" if r.get("type") == "INCOME" else "−") + money(Decimal(str(r["amount"]))),
            _nice_date(r["date"]),
        )
        for r in sorted(rows, key=lambda r: str(r["date"]), reverse=True)
    ]
    return DataAnswer(
        f"Here are your latest {len(table)} transactions.",
        question.wants_advice,
        [_table("Latest transactions", table)],
    )


async def _average(question: DataQuestion, data, categories, today) -> DataAnswer:
    period = question.period
    expenses = _within(await _rows(data, period.start, period.end), period)
    if not expenses:
        note = await _records_note(data)
        return DataAnswer(f"You haven't spent anything {period.label}.{note}", question.wants_advice)
    total = _total(expenses)
    first = min(str(r["date"])[:10] for r in expenses)
    start = date.fromisoformat(first) if period.start == ALL_TIME_START else period.start
    days = max(1, (min(period.end, today) - start).days + 1)
    per_day, per_payment = total / days, total / len(expenses)
    text = (
        f"You spent about {money(per_day)} a day {period.label}, "
        f"and about {money(per_payment)} per payment ({len(expenses)} payments)."
    )
    cards = _cards(
        ("Per day", money(per_day), ""),
        ("Per payment", money(per_payment), ""),
        ("Total", money(total), "expense"),
    )
    return DataAnswer(text, question.wants_advice, [cards])


async def _spending(question: DataQuestion, data, categories, today) -> DataAnswer:
    period, subject = question.period, question.subject
    about = f" on {subject}" if subject else ""
    expenses = _within(await _rows(data, period.start, period.end), period)
    matching = _filter(expenses, subject, categories)
    what = f"on {subject} " if subject else ""
    suggestions = _period_choices(question, f"How much did I spend {what}{{period}}?")
    if not matching:
        note = "" if subject else await _records_note(data)
        return DataAnswer(
            f"You haven't spent anything{about} {period.label}.{note}",
            question.wants_advice,
            suggestions=suggestions,
        )
    word = "payment" if len(matching) == 1 else "payments"
    total = _total(matching)
    text = f"You spent {money(total)}{about} {period.label} ({len(matching)} {word})."
    cards = _cards(("Spent", money(total), "expense"), ("Payments", str(len(matching)), ""))
    return DataAnswer(text, question.wants_advice, [cards], suggestions)
