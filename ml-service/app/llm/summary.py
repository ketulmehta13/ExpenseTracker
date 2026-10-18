"""A short written summary of the month: numbers from code, words from a model.

The facts are computed in code: spending so far against the same point last month, the
month-end projection and budget, the biggest category, unusual payments and subscriptions.
An LLM may turn them into two or three friendly sentences, but it only ever sees and writes
[placeholders]; code substitutes the numbers (app/llm/verify.py). Text that writes a digit
itself or uses an unknown placeholder is discarded for the template sentence, which goes
through the same substitution. Without an LLM the template is used directly, so the feature
never depends on one.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm.verify import fill_placeholders

logger = logging.getLogger("ml_service.llm")
MAX_SUMMARY_CHARS = 600


def money(value: float) -> str:
    """₹12,345 in Indian digit grouping (₹1,25,000), whole rupees."""
    rupees = f"{round(abs(value)):d}"
    if len(rupees) > 3:
        head, tail = rupees[:-3], rupees[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        rupees = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return f"{'-' if value < 0 else ''}₹{rupees}"


@dataclass(frozen=True)
class MonthFacts:
    month_name: str
    day: int
    spent: float
    spent_last_month_same_day: float
    projected: float | None
    budget: float | None
    status: str | None
    top_category: tuple[str, float] | None
    unusual: tuple[str, float, float] | None  # title, amount, times the usual top payment
    subscriptions_monthly: float
    subscription_count: int

    @property
    def difference(self) -> float:
        return self.spent - self.spent_last_month_same_day

    def values(self) -> dict[str, str]:
        """Each placeholder and the text code puts in its place."""
        values = {"day": str(self.day), "spent": money(self.spent)}
        if self.spent_last_month_same_day:
            values["difference"] = money(abs(self.difference))
        if self.projected is not None:
            values["projected"] = money(self.projected)
        if self.budget:
            values["budget"] = money(self.budget)
        if self.top_category:
            values["top_category_amount"] = money(self.top_category[1])
        if self.unusual:
            values["unusual_amount"] = money(self.unusual[1])
            values["unusual_ratio"] = f"{self.unusual[2]:g}"
        if self.subscription_count:
            values["subscriptions"] = money(self.subscriptions_monthly)
        return values

    def names(self) -> list[str]:
        """Names the text may repeat even if they contain digits."""
        names = [self.month_name]
        if self.top_category:
            names.append(self.top_category[0])
        if self.unusual:
            names.append(self.unusual[0])
        return names

    def lines(self) -> list[str]:
        """The facts as the model sees them: meanings and placeholders, never the numbers."""
        lines = [f"Month: {self.month_name}, day [day]", "Spent so far this month: [spent]"]
        if self.spent_last_month_same_day:
            change = "more" if self.difference >= 0 else "less"
            lines.append(f"Compared with the same point last month: [difference] {change}")
        if self.projected is not None:
            lines.append("Projected total for the month at this pace: [projected]")
        if self.budget:
            verdict = "within" if self.status == "on_track" else "above"
            lines.append(f"Monthly budget: [budget]; the projected total is {verdict} it")
        if self.top_category:
            lines.append(f"Biggest category so far: {self.top_category[0]}, [top_category_amount]")
        if self.unusual:
            lines.append(
                f"Unusually large payment: {self.unusual[0]}, [unusual_amount], "
                "[unusual_ratio] times the usual top payment there"
            )
        if self.subscription_count:
            lines.append("Subscriptions and bills: [subscriptions] a month")
        return lines

    def fill(self, text: str) -> str | None:
        return fill_placeholders(text, self.values(), self.names())


def month_facts(transactions: list[dict], categories: list[dict], insights, today: date) -> MonthFacts:
    """Facts for the current month, from raw transactions plus the computed insights."""
    names = {str(category["id"]): category["name"] for category in categories}
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    same_day_last_month = last_month_start.replace(
        day=min(today.day, calendar.monthrange(last_month_start.year, last_month_start.month)[1])
    )

    spent = previous = 0.0
    by_category: dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") != "EXPENSE":
            continue
        day = date.fromisoformat(str(tx["date"])[:10])
        amount = float(tx["amount"])
        if month_start <= day <= today:
            spent += amount
            by_category[names.get(str(tx.get("category_id")), "Uncategorized")] += amount
        elif last_month_start <= day <= same_day_last_month:
            previous += amount

    forecast = insights.forecast
    this_month_unusual = [u for u in insights.unusual if u.date >= month_start]
    biggest = max(this_month_unusual, key=lambda u: u.amount, default=None)
    active = [p for p in insights.recurring if p.active]
    return MonthFacts(
        month_name=f"{today:%B}",
        day=today.day,
        spent=round(spent, 2),
        spent_last_month_same_day=round(previous, 2),
        projected=forecast.projected_total if forecast else None,
        budget=forecast.budget if forecast else None,
        status=forecast.status if forecast else None,
        top_category=max(by_category.items(), key=lambda item: item[1]) if by_category else None,
        unusual=(biggest.title, biggest.amount, biggest.ratio) if biggest else None,
        subscriptions_monthly=round(sum(p.monthly_cost for p in active), 2),
        subscription_count=len(active),
    )


def template_text(facts: MonthFacts) -> str:
    """The fallback summary, written with the same placeholders the model uses."""
    sentences = []
    opening = f"You've spent [spent] so far in {facts.month_name}"
    previous = facts.spent_last_month_same_day
    if previous and abs(facts.difference) < 0.05 * previous:
        opening += ", about the same as at this point last month"
    elif previous:
        change = "more" if facts.difference > 0 else "less"
        opening += f", [difference] {change} than at this point last month"
    sentences.append(opening + ".")
    if facts.projected is not None:
        projection = "At this pace you'll end the month near [projected]"
        if facts.budget:
            projection += f", {'within' if facts.status == 'on_track' else 'above'} your [budget] budget"
        sentences.append(projection + ".")
    if facts.top_category:
        sentences.append(f"{facts.top_category[0]} is your biggest category so far ([top_category_amount]).")
    if facts.unusual:
        sentences.append(
            f"{facts.unusual[0]} ([unusual_amount]) was unusually large, "
            "[unusual_ratio] times your usual top payment there."
        )
    return " ".join(sentences)


def template_summary(facts: MonthFacts) -> str:
    return facts.fill(template_text(facts))


_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You write a short, friendly summary of someone's month for their expense tracker app.\n"
        "Rules: two or three sentences, at most 60 words, plain text.\n"
        "Never write a digit. Refer to amounts only with the placeholders in square brackets, exactly "
        "as they appear in the facts (for example [spent]); the app replaces them with the real numbers.\n"
        "Use only the facts given. No advice, greetings or emojis.",
    ),
    ("human", "Facts:\n{facts}"),
])


async def summarize(model: BaseChatModel | None, facts: MonthFacts, timeout: float) -> tuple[str, str]:
    """(text, source): the model's summary if it passes the placeholder check, else the template."""
    template = template_summary(facts)
    if model is None:
        return template, "template"
    try:
        chain = _PROMPT | model | StrOutputParser()
        text = await asyncio.wait_for(chain.ainvoke({"facts": "\n".join(facts.lines())}), timeout)
    except Exception as err:
        logger.warning("llm summary failed: %s", type(err).__name__)
        return template, "template"
    filled = facts.fill(" ".join(text.split()))
    if not filled or len(filled) > MAX_SUMMARY_CHARS:
        logger.warning("llm summary rejected (digits, unknown placeholders or too long)")
        return template, "template"
    return filled, "llm"
