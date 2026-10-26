"""The copilot's analytics tools: typed, read-only functions over the signed-in user's own data.

Security model:
- The data (`FinanceData`) is loaded by the server with the user's own access token, so Postgres
  row level security decides what it contains. No tool takes a user id, and none runs SQL: a
  model choosing a tool can only choose *which* allowlisted calculation runs and with which
  validated arguments (a period, one of the user's own categories, a merchant name).
- Money is summed with Decimal and rounded to paise once, so totals are exact. The LLM never
  computes or chooses a figure: tool results are passed to it as numbered facts, and any number
  in its answer must come from them (app/copilot/compose.py).

Each tool returns a Pydantic model, which is also what the chat UI renders (a table or chart).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.assistant.router import Period, match_category, match_merchant, parse_period
from app.ml.recurring import merchant_key

PAISE = Decimal("0.01")


def money(value: Decimal) -> float:
    return float(value.quantize(PAISE, rounding=ROUND_HALF_UP))


def _amount(tx: dict) -> Decimal:
    return Decimal(str(tx["amount"]))


def _day(tx: dict) -> date:
    return date.fromisoformat(str(tx["date"])[:10])


@dataclass(frozen=True)
class FinanceData:
    """One user's data for one request; loaded with that user's token (RLS applies)."""

    today: date
    transactions: list[dict]
    categories: list[dict]
    budget: float | None
    insights: object  # app.routers.insights.InsightsResponse

    def category_name(self, category_id) -> str:
        names = {str(c["id"]): c["name"] for c in self.categories}
        return names.get(str(category_id), "Uncategorized")

    def category_by_name(self, name: str | None) -> dict | None:
        return match_category(name, self.categories) if name else None


# ---------- periods ----------


class PeriodOut(BaseModel):
    key: str
    label: str
    start: date
    end: date


def period_out(period: Period) -> PeriodOut:
    return PeriodOut(key=period.key, label=period.label, start=period.start, end=period.end)


def resolve_period(text: str | None, today: date) -> Period:
    """A period from words ("last month", "this week", "in september"); this month by default."""
    return parse_period(text or "", today) or parse_period("this month", today)


def previous_period(period: Period) -> Period:
    """The period to compare with: the previous calendar month for months (up to the same day
    for the current month, so month-to-date is compared with the same days last month), otherwise
    the same number of days just before."""
    if period.key == "this_month" or period.key.startswith("month:") or period.key == "last_month":
        start = (period.start - timedelta(days=1)).replace(day=1)
        last_day = calendar.monthrange(start.year, start.month)[1]
        span = (period.end - period.start).days
        full_month = period.end.day == calendar.monthrange(period.end.year, period.end.month)[1]
        end = start.replace(day=last_day) if full_month else start.replace(day=min(1 + span, last_day))
        return Period(
            f"prev:{period.key}",
            start,
            end,
            f"in {calendar.month_name[start.month]}" + ("" if full_month else f" (1–{end.day})"),
        )
    days = (period.end - period.start).days + 1
    end = period.start - timedelta(days=1)
    return Period(f"prev:{period.key}", end - timedelta(days=days - 1), end, f"the {days} days before")


# ---------- tool results ----------


class ExpenseSummary(BaseModel):
    kind: Literal["expense_summary"] = "expense_summary"
    period: PeriodOut
    category: str | None
    merchant: str | None
    expenses: float
    income: float
    net: float
    savings_rate: float | None  # net / income, 0-1; None without income or with a filter
    expense_count: int


class CategoryRow(BaseModel):
    category: str
    amount: float
    share: float  # of the period's expenses, 0-1
    count: int


class CategoryBreakdown(BaseModel):
    kind: Literal["category_breakdown"] = "category_breakdown"
    period: PeriodOut
    total: float
    rows: list[CategoryRow]


class CategoryChange(BaseModel):
    category: str
    current: float
    previous: float
    change: float


class PeriodComparison(BaseModel):
    kind: Literal["period_comparison"] = "period_comparison"
    current: PeriodOut
    previous: PeriodOut
    category: str | None
    current_total: float
    previous_total: float
    change: float
    change_pct: float | None  # None when there was nothing to compare with
    biggest_changes: list[CategoryChange]


class BudgetStatus(BaseModel):
    kind: Literal["budget_status"] = "budget_status"
    month: str
    budget: float | None
    spent_to_date: float
    remaining: float | None
    projected_total: float | None
    projected_low: float | None
    projected_high: float | None
    status: Literal["on_track", "at_risk", "over"] | None
    probability_over_budget: float | None


class RecurringItem(BaseModel):
    title: str
    category: str | None
    period: str
    amount: float
    monthly_cost: float
    next_date: date


class RecurringExpenses(BaseModel):
    kind: Literal["recurring_expenses"] = "recurring_expenses"
    monthly_total: float
    items: list[RecurringItem]


# ---------- tools ----------


def _expenses(data: FinanceData, period: Period, category: dict | None = None, merchant: str | None = None):
    return [
        tx
        for tx in data.transactions
        if tx.get("type") == "EXPENSE"
        and period.start <= _day(tx) <= period.end
        and (category is None or str(tx.get("category_id")) == str(category["id"]))
        and (merchant is None or merchant_key(tx.get("title")) == merchant)
    ]


def get_expense_summary(
    data: FinanceData, period: Period, category: dict | None = None, merchant: str | None = None
) -> ExpenseSummary:
    expenses = _expenses(data, period, category, merchant)
    spent = sum((_amount(tx) for tx in expenses), Decimal(0))
    income = (
        sum(
            (
                _amount(tx)
                for tx in data.transactions
                if tx.get("type") == "INCOME" and period.start <= _day(tx) <= period.end
            ),
            Decimal(0),
        )
        if category is None and merchant is None
        else Decimal(0)
    )
    return ExpenseSummary(
        period=period_out(period),
        category=category["name"] if category else None,
        merchant=merchant,
        expenses=money(spent),
        income=money(income),
        net=money(income - spent),
        savings_rate=float(((income - spent) / income).quantize(Decimal("0.0001"))) if income else None,
        expense_count=len(expenses),
    )


def get_category_breakdown(data: FinanceData, period: Period, top: int = 8) -> CategoryBreakdown:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for tx in _expenses(data, period):
        name = data.category_name(tx.get("category_id"))
        totals[name] += _amount(tx)
        counts[name] += 1
    overall = sum(totals.values(), Decimal(0))
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    rows = [
        CategoryRow(
            category=name,
            amount=money(amount),
            share=float((amount / overall).quantize(Decimal("0.0001"))) if overall else 0.0,
            count=counts[name],
        )
        for name, amount in ordered[:top]
    ]
    if len(ordered) > top:
        rest = sum((amount for _, amount in ordered[top:]), Decimal(0))
        rows.append(
            CategoryRow(
                category="Other categories",
                amount=money(rest),
                share=float((rest / overall).quantize(Decimal("0.0001"))),
                count=sum(counts[name] for name, _ in ordered[top:]),
            )
        )
    return CategoryBreakdown(period=period_out(period), total=money(overall), rows=rows)


def compare_expense_periods(
    data: FinanceData, current: Period, previous: Period | None = None, category: dict | None = None
) -> PeriodComparison:
    previous = previous or previous_period(current)
    by_category: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for index, period in enumerate((current, previous)):
        for tx in _expenses(data, period, category):
            by_category[data.category_name(tx.get("category_id"))][index] += _amount(tx)
    now = sum((v[0] for v in by_category.values()), Decimal(0))
    before = sum((v[1] for v in by_category.values()), Decimal(0))
    changes = sorted(
        (
            CategoryChange(
                category=name, current=money(v[0]), previous=money(v[1]), change=money(v[0] - v[1])
            )
            for name, v in by_category.items()
            if v[0] != v[1]
        ),
        key=lambda c: (-abs(c.change), c.category),
    )
    return PeriodComparison(
        current=period_out(current),
        previous=period_out(previous),
        category=category["name"] if category else None,
        current_total=money(now),
        previous_total=money(before),
        change=money(now - before),
        change_pct=float(((now - before) / before * 100).quantize(Decimal("0.1"))) if before else None,
        biggest_changes=changes[:5],
    )


def get_budget_status(data: FinanceData) -> BudgetStatus:
    month = data.today.replace(day=1)
    this_month = Period("this_month", month, data.today, "this month")
    spent = sum((_amount(tx) for tx in _expenses(data, this_month)), Decimal(0))
    forecast = getattr(data.insights, "forecast", None)
    budget = Decimal(str(data.budget)) if data.budget else None
    return BudgetStatus(
        month=f"{month:%Y-%m}",
        budget=money(budget) if budget else None,
        spent_to_date=money(spent),
        remaining=money(budget - spent) if budget else None,
        projected_total=forecast.projected_total if forecast else None,
        projected_low=forecast.low if forecast else None,
        projected_high=forecast.high if forecast else None,
        status=(forecast.status if forecast else ("over" if budget and spent > budget else None)),
        probability_over_budget=forecast.probability_over_budget if forecast else None,
    )


def detect_recurring_expenses(data: FinanceData, top: int = 8) -> RecurringExpenses:
    active = [p for p in getattr(data.insights, "recurring", []) if p.active]
    total = sum((Decimal(str(p.monthly_cost)) for p in active), Decimal(0))
    return RecurringExpenses(
        monthly_total=money(total),
        items=[
            RecurringItem(
                title=p.title,
                category=p.category_name,
                period=p.period,
                amount=p.amount,
                monthly_cost=p.monthly_cost,
                next_date=p.next_date,
            )
            for p in active[:top]
        ],
    )


class UnusualItem(BaseModel):
    title: str
    date: date
    amount: float
    category: str | None
    usual_high: float
    ratio: float
    compared_with: Literal["merchant", "category"]


class UnusualPayments(BaseModel):
    kind: Literal["unusual_payments"] = "unusual_payments"
    days: int
    items: list[UnusualItem]


def get_unusual_payments(data: FinanceData, top: int = 5) -> UnusualPayments:
    unusual = list(getattr(data.insights, "unusual", []))
    return UnusualPayments(
        days=60,
        items=[
            UnusualItem(
                title=u.title,
                date=u.date,
                amount=u.amount,
                category=u.category_name,
                usual_high=u.usual_high,
                ratio=u.ratio,
                compared_with=u.compared_with,
            )
            for u in unusual[:top]
        ],
    )


# ---------- the allowlist, for LLM tool calling ----------


class SummaryArgs(BaseModel):
    period: str = Field(
        "this month", max_length=40, description='e.g. "this month", "last week", "in september"'
    )
    category: str | None = Field(None, max_length=60, description="One of the user's category names")
    merchant: str | None = Field(None, max_length=60, description="A merchant name from the user's history")


class PeriodArgs(BaseModel):
    period: str = Field("this month", max_length=40)


class CompareArgs(BaseModel):
    period: str = Field(
        "this month", max_length=40, description="The period to compare with the one before it"
    )
    category: str | None = Field(None, max_length=60)


class NoArgs(BaseModel):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[FinanceData, BaseModel], BaseModel]


def _summary(data: FinanceData, args: SummaryArgs) -> ExpenseSummary:
    merchant = None
    if args.merchant:
        keys = {merchant_key(tx.get("title")) for tx in data.transactions}
        merchant = match_merchant(args.merchant, keys)
    return get_expense_summary(
        data, resolve_period(args.period, data.today), data.category_by_name(args.category), merchant
    )


READ_TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            "get_expense_summary",
            "Total spent (and earned) in a period, optionally for one category or merchant.",
            SummaryArgs,
            _summary,
        ),
        Tool(
            "get_category_breakdown",
            "Spending by category in a period, largest first.",
            PeriodArgs,
            lambda data, a: get_category_breakdown(data, resolve_period(a.period, data.today)),
        ),
        Tool(
            "compare_expense_periods",
            "Spending in a period compared with the period before, by category.",
            CompareArgs,
            lambda data, a: compare_expense_periods(
                data, resolve_period(a.period, data.today), category=data.category_by_name(a.category)
            ),
        ),
        Tool(
            "get_budget_status",
            "This month's spending against the monthly budget, with the forecast.",
            NoArgs,
            lambda data, a: get_budget_status(data),
        ),
        Tool(
            "detect_recurring_expenses",
            "Subscriptions and regular bills, with their monthly cost.",
            NoArgs,
            lambda data, a: detect_recurring_expenses(data),
        ),
        Tool(
            "get_unusual_payments",
            "Payments in the last 60 days that were unusually large for that merchant or category.",
            NoArgs,
            lambda data, a: get_unusual_payments(data),
        ),
    )
}


def run_tool(name: str, raw_args: dict, data: FinanceData) -> BaseModel:
    """Run an allowlisted read tool with validated arguments. Unknown names are refused."""
    tool = READ_TOOLS.get(name)
    if tool is None:
        raise ValueError(f"unknown tool {name!r}")
    # Extra keys (a user_id the model invented, say) are rejected, not ignored
    args = tool.args.model_validate({k: v for k, v in (raw_args or {}).items()}, strict=False)
    extra = set(raw_args or {}) - set(tool.args.model_fields)
    if extra:
        raise ValueError(f"unexpected arguments for {name}: {sorted(extra)}")
    return tool.run(data, args)
