"""Month-end spending forecast with an uncertainty band.

    projected total = spent so far this month
                    + expected everyday spending for the rest of the month
                    + recurring payments still due this month

Everyday spending is estimated per weekday from the last 90 days (Saturdays differ from
Tuesdays). That estimate leaves out recurring payments, which are added on their due dates
instead, and detected anomalies, because one-offs are not a run-rate. Treating the remaining
days as independent, their variances add up. That gives an 80% interval of ±1.28 standard
deviations and, when the user has a budget, the probability of going over it.

Real days are not independent, and the weekday averages are themselves estimates, so that
textbook spread is too narrow. SD_INFLATION widens it by a factor calibrated on simulated
validation users, chosen so that 80% of actual totals fall inside the interval: split
conformal prediction (see training/evaluate_insights.py).
"""

from __future__ import annotations

import calendar
import math
import statistics
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist

from app.ml.recurring import RecurringSeries, find_recurring, merchant_key

LOOKBACK_DAYS = 90
MIN_HISTORY_DAYS = 28
Z_80 = 1.2816  # 80% of a normal distribution lies within ±1.2816 standard deviations
SD_INFLATION = 1.45  # calibrated widening of the textbook standard deviation
GRACE_DAYS = 5  # a recurring payment this many days late is still expected


@dataclass(frozen=True)
class Forecast:
    month: str  # "YYYY-MM"
    as_of: date
    spent_to_date: float
    expected_everyday: float
    expected_recurring: float
    sd: float  # calibrated standard deviation of the projection
    low: float
    high: float
    budget: float | None
    probability_over_budget: float | None

    @property
    def projected_total(self) -> float:
        return self.spent_to_date + self.expected_everyday + self.expected_recurring

    @property
    def status(self) -> str | None:
        if not self.budget:
            return None
        if self.spent_to_date > self.budget:
            return "over"
        return "at_risk" if self.projected_total > self.budget else "on_track"


def _to_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def payments_due(series: RecurringSeries, today: date, month_end: date) -> int:
    """How many payments of a series are still expected between tomorrow and the month's end."""
    if not series.is_active(today):
        return 0
    when = series.next_date
    if when <= today:
        if (today - when).days > GRACE_DAYS:
            return 0  # long overdue: probably cancelled
        when = today + timedelta(days=1)  # late, but still expected
    count = 0
    while when <= month_end:
        count += 1
        when = series.after(when)
    return count


def forecast_month(
    transactions: list[dict],
    today: date,
    recurring: list[RecurringSeries] | None = None,
    exclude_ids: Collection = (),
    budget: float | None = None,
) -> Forecast | None:
    """Forecast this month's total expenses as of the end of `today`; None without 4 weeks of history.

    `exclude_ids`: transactions to leave out of the everyday spending rate (detected anomalies).
    """
    expenses = [
        (_to_date(tx["date"]), float(tx["amount"]), tx)
        for tx in transactions
        if tx.get("type") == "EXPENSE" and _to_date(tx["date"]) <= today
    ]
    if not expenses:
        return None
    first_day = min(day for day, _, _ in expenses)
    if (today - first_day).days < MIN_HISTORY_DAYS:
        return None

    month_start = today.replace(day=1)
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    spent = sum(amount for day, amount, _ in expenses if day >= month_start)

    if recurring is None:
        recurring = find_recurring([tx for _, _, tx in expenses])
    recurring_keys = {series.key for series in recurring}
    excluded = set(exclude_ids)

    # Everyday spending per day over the lookback window (full days before today), zero when nothing was spent
    daily: dict[date, float] = defaultdict(float)
    for day, amount, tx in expenses:
        if tx.get("id") not in excluded and merchant_key(tx.get("title")) not in recurring_keys:
            daily[day] += amount
    window = [today - timedelta(days=n) for n in range(1, LOOKBACK_DAYS + 1)]
    by_weekday: dict[int, list[float]] = defaultdict(list)
    for day in window:
        if day >= first_day:
            by_weekday[day.weekday()].append(daily.get(day, 0.0))

    remaining_days = [today + timedelta(days=n) for n in range(1, (month_end - today).days + 1)]
    expected_everyday = sum(statistics.fmean(by_weekday[day.weekday()]) for day in remaining_days)
    variance = sum(statistics.pvariance(by_weekday[day.weekday()]) for day in remaining_days)
    expected_recurring = sum(series.amount * payments_due(series, today, month_end) for series in recurring)

    projected = spent + expected_everyday + expected_recurring
    sd = math.sqrt(variance) * SD_INFLATION
    probability_over = None
    if budget:
        probability_over = 1 - NormalDist(projected, sd).cdf(budget) if sd > 0 else float(projected > budget)
    return Forecast(
        month=f"{today:%Y-%m}",
        as_of=today,
        spent_to_date=round(spent, 2),
        expected_everyday=round(expected_everyday, 2),
        expected_recurring=round(expected_recurring, 2),
        sd=round(sd, 2),
        low=round(max(spent, projected - Z_80 * sd), 2),
        high=round(projected + Z_80 * sd, 2),
        budget=budget,
        probability_over_budget=None if probability_over is None else round(probability_over, 3),
    )
