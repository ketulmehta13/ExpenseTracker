"""Tool results as named facts, template sentences and UI blocks.

Facts are the only way the user's figures reach a reply. Each fact has a name ("spent",
"previous_total") and an exact, formatted value. A data answer (route B) is built from template
sentences over these facts. In a combined answer (route C) the LLM sees the facts and writes
[placeholders] instead of the figures, which code fills in afterwards (app/copilot/compose.py),
so the model can't misstate or mix up a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.copilot import tools as t
from app.copilot.schemas import ChartBlock, ChartPoint, DataBlock


def inr(value: float) -> str:
    """₹1,25,000 or ₹1,234.50: Indian digit grouping, paise only when there are any."""
    negative, value = value < 0, abs(round(value, 2))
    rupees, paise = divmod(round(value * 100), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *groups, tail] if head else [*groups, tail])
    return f"{'-' if negative else ''}₹{digits}" + (f".{paise:02d}" if paise else "")


def pct(share: float) -> str:
    return f"{share * 100:.0f}%" if abs(share * 100 - round(share * 100)) < 0.05 else f"{share * 100:.1f}%"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


@dataclass
class Facts:
    values: dict[str, str] = field(default_factory=dict)  # name -> formatted value
    labels: dict[str, str] = field(default_factory=dict)  # name -> what it is, for the prompt
    sentences: list[str] = field(default_factory=list)  # the template answer
    blocks: list = field(default_factory=list)

    def add(self, name: str, value: str, label: str) -> str:
        self.values[name], self.labels[name] = value, label
        return value

    def merge(self, other: Facts) -> Facts:
        self.values |= other.values
        self.labels |= other.labels
        self.sentences += other.sentences
        self.blocks += other.blocks
        return self


def _summary(r: t.ExpenseSummary) -> Facts:
    f = Facts()
    subject = f" on {r.category}" if r.category else (f" at {r.merchant.title()}" if r.merchant else "")
    period = r.period.label
    f.add("period", period, "the period asked about")
    spent = f.add("spent", inr(r.expenses), f"total spent{subject} {period}")
    payments = f.add("payments", str(r.expense_count), "number of expense payments")
    if not r.expense_count:
        f.sentences.append(f"You haven't spent anything{subject} {period}.")
    else:
        word = "payment" if r.expense_count == 1 else "payments"
        f.sentences.append(f"You spent {spent}{subject} {period} ({payments} {word}).")
    if not subject and r.income:
        income = f.add("income", inr(r.income), f"total income {period}")
        net = f.add("net", inr(r.net), "income minus expenses")
        sentence = f"You earned {income}, so your net cash flow was {net}"
        if r.savings_rate is not None:
            rate = f.add("savings_rate", pct(r.savings_rate), "share of income not spent")
            sentence += f" (a savings rate of {rate})"
        f.sentences.append(sentence + ".")
    f.blocks.append(DataBlock(tool="get_expense_summary", result=r.model_dump(mode="json")))
    return f


def _breakdown(r: t.CategoryBreakdown) -> Facts:
    f = Facts()
    if not r.rows:
        f.sentences.append(f"You haven't spent anything {r.period.label}.")
        return f
    f.add("breakdown_total", inr(r.total), f"total spent {r.period.label}")
    parts = []
    for i, row in enumerate(r.rows[:3], start=1):
        f.add(f"top_{i}_category", row.category, f"number {i} category by spending")
        amount = f.add(f"top_{i}_amount", inr(row.amount), f"spent on {row.category}")
        share = f.add(f"top_{i}_share", pct(row.share), f"{row.category}'s share of spending")
        parts.append(f"{row.category} {amount} ({share})")
    f.sentences.append(
        f"Your biggest categories {r.period.label}: {_join(parts)}, out of {inr(r.total)} in total."
    )
    f.blocks.append(
        ChartBlock(
            chart="bar",
            title=f"Spending by category, {r.period.label}",
            points=[ChartPoint(label=row.category, value=row.amount) for row in r.rows],
        )
    )
    return f


def _comparison(r: t.PeriodComparison) -> Facts:
    f = Facts()
    subject = f" on {r.category}" if r.category else ""
    now = f.add("current_total", inr(r.current_total), f"spent{subject} {r.current.label}")
    before = f.add("previous_total", inr(r.previous_total), f"spent{subject} {r.previous.label}")
    f.add("current_period", r.current.label, "the period asked about")
    f.add("previous_period", r.previous.label, "the period compared with")
    if r.change == 0:
        f.sentences.append(f"You spent {now}{subject} {r.current.label}, the same as {r.previous.label}.")
    else:
        direction = "more" if r.change > 0 else "less"
        change = f.add("change", inr(abs(r.change)), f"how much {direction} was spent")
        detail = ""
        if r.change_pct is not None:
            detail = (
                f", {f.add('change_pct', f'{abs(r.change_pct):g}%', 'the change in percent')} {direction}"
            )
        f.sentences.append(
            f"You spent {now}{subject} {r.current.label} against {before} {r.previous.label}: "
            f"{change} {direction}{detail}."
        )
    movers = []
    for i, c in enumerate(r.biggest_changes[:3], start=1):
        f.add(f"mover_{i}_category", c.category, f"category with change number {i}")
        amount = f.add(f"mover_{i}_change", inr(abs(c.change)), f"change in {c.category}")
        f.add(
            f"mover_{i}_direction", "up" if c.change > 0 else "down", f"direction of change in {c.category}"
        )
        movers.append(f"{c.category} {'up' if c.change > 0 else 'down'} {amount}")
    if movers and not r.category:
        f.sentences.append(f"Biggest changes: {_join(movers)}.")
    f.blocks.append(
        ChartBlock(
            chart="comparison",
            title=f"{r.current.label.capitalize()} vs {r.previous.label}",
            points=[
                ChartPoint(label=c.category, value=c.current, previous=c.previous) for c in r.biggest_changes
            ],
        )
    )
    return f


def _budget(r: t.BudgetStatus) -> Facts:
    f = Facts()
    spent = f.add("spent_to_date", inr(r.spent_to_date), "spent so far this month")
    if r.budget is None:
        f.sentences.append(
            f"You've spent {spent} so far this month. You haven't set a monthly budget yet; "
            'set one in Settings, or tell me "set my budget to 30000".'
        )
    else:
        budget = f.add("budget", inr(r.budget), "the monthly budget")
        remaining = f.add("remaining", inr(abs(r.remaining or 0)), "budget left (or over by)")
        if (r.remaining or 0) < 0:
            f.sentences.append(f"You've spent {spent} this month, {remaining} over your {budget} budget.")
        else:
            f.sentences.append(
                f"You've spent {spent} of your {budget} budget this month; {remaining} is left."
            )
    if r.projected_total is not None:
        projected = f.add("projected", inr(r.projected_total), "forecast spending for the whole month")
        low = f.add("projected_low", inr(r.projected_low or 0), "low end of the forecast")
        high = f.add("projected_high", inr(r.projected_high or 0), "high end of the forecast")
        sentence = f"At this pace you'll spend about {projected} this month (likely {low} to {high})"
        if r.budget is not None and r.probability_over_budget is not None:
            chance = r.probability_over_budget
            odds = (
                "very unlikely"
                if chance < 0.01
                else "almost certain"
                if chance > 0.99
                else f"a {round(chance * 100)}% chance"
            )
            f.add("chance_over", odds, "chance of going over the budget")
            sentence += f", with {odds} of going over"
        f.sentences.append(sentence + ".")
    f.blocks.append(DataBlock(tool="get_budget_status", result=r.model_dump(mode="json")))
    return f


def _recurring(r: t.RecurringExpenses) -> Facts:
    f = Facts()
    if not r.items:
        f.sentences.append(
            "I haven't found any subscriptions or regular bills yet: I need at least three "
            "payments on a steady rhythm to spot one."
        )
        return f
    total = f.add("recurring_total", inr(r.monthly_total), "monthly cost of subscriptions and bills")
    listed = [f"{i.title} {inr(i.amount)} ({i.period})" for i in r.items[:4]]
    f.sentences.append(
        f"You have {len(r.items)} subscriptions and regular bills costing about {total} a month: "
        f"{_join(listed)}."
    )
    f.blocks.append(DataBlock(tool="detect_recurring_expenses", result=r.model_dump(mode="json")))
    return f


def _unusual(r: t.UnusualPayments) -> Facts:
    f = Facts()
    if not r.items:
        f.sentences.append(f"Nothing unusual in the last {r.days} days.")
        return f
    listed = []
    for i, u in enumerate(r.items[:3], start=1):
        f.add(f"unusual_{i}_title", u.title, f"unusual payment number {i}")
        amount = f.add(f"unusual_{i}_amount", inr(u.amount), f"amount of {u.title}")
        usual = f.add(f"unusual_{i}_usual", inr(u.usual_high), f"usual top payment for {u.title}")
        listed.append(
            f"{u.title} {amount} on {u.date.day} {u.date:%b} (your usual top payment there is {usual})"
        )
    f.sentences.append(f"Unusual payments in the last {r.days} days: {_join(listed)}.")
    f.blocks.append(DataBlock(tool="get_unusual_payments", result=r.model_dump(mode="json")))
    return f


_DESCRIBE = {
    "expense_summary": _summary,
    "category_breakdown": _breakdown,
    "period_comparison": _comparison,
    "budget_status": _budget,
    "recurring_expenses": _recurring,
    "unusual_payments": _unusual,
}


def describe(results: list[BaseModel]) -> Facts:
    facts = Facts()
    for result in results:
        facts.merge(_DESCRIBE[result.kind](result))
    return facts
