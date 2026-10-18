"""Recurring payments (subscriptions, rent, bills) found in transaction history.

Expenses are grouped by merchant, and a group counts as recurring when:
- it has at least 3 payments;
- the median gap between payments is close to a known period (weekly ... yearly);
- most gaps (75%) are within that period's tolerance, so one skipped month doesn't break
  a series, while irregular habits (Swiggy three times a week) never qualify;
- the amount is stable: coefficient of variation (std / mean) at most 0.35, which allows a
  varying electricity bill but not a basket of random purchases.
"""

from __future__ import annotations

import calendar
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.ml.text import normalize_title

# name, typical gap in days, tolerance in days; checked closest-first
PERIODS = [
    ("weekly", 7.0, 1.5),
    ("fortnightly", 14.0, 2.5),
    ("every 28 days", 28.0, 1.0),  # prepaid mobile plans
    ("monthly", 30.4, 4.0),
    ("quarterly", 91.0, 10.0),
    ("yearly", 365.0, 20.0),
]
CALENDAR_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}  # these follow the calendar, not a day count
MIN_PAYMENTS = 3
MIN_REGULAR_SHARE = 0.75
MAX_AMOUNT_CV = 0.35
DAYS_PER_MONTH = 30.44

_MONTHS = {
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "january", "february", "march", "april", "june", "july", "august", "september", "october",
    "november", "december",
}
# Words that vary between entries for the same merchant ("NETFLIX.COM", "Jio prepaid plan")
_KEY_STOPWORDS = {
    "for", "the", "of", "and", "my", "monthly", "bill", "subscription", "premium", "recharge",
    "prepaid", "postpaid", "plan", "com", "www", "india",
}


def merchant_key(title: str | None) -> str:
    """Group key for a merchant: "Rent for October" and "rent nov" both become "rent"."""
    words = normalize_title(title).split()
    kept = [w for w in words if w not in _MONTHS and w not in _KEY_STOPWORDS]
    return " ".join(kept[:2]) or " ".join(words[:2])


@dataclass(frozen=True)
class RecurringSeries:
    key: str
    title: str  # the user's most common way of writing it, for display
    category_id: int | str | None
    period: str
    period_days: float  # median gap actually observed
    amount: float  # typical recent amount
    count: int
    first_date: date
    last_date: date

    def after(self, payment: date) -> date:
        """The payment expected after one made on `payment`: same day next month for monthly bills."""
        months = CALENDAR_MONTHS.get(self.period)
        if months is None:
            return payment + timedelta(days=round(self.period_days))
        year, month = divmod(payment.month - 1 + months, 12)
        year, month = payment.year + year, month + 1
        return date(year, month, min(payment.day, calendar.monthrange(year, month)[1]))

    @property
    def next_date(self) -> date:
        return self.after(self.last_date)

    @property
    def monthly_cost(self) -> float:
        return self.amount * DAYS_PER_MONTH / self.period_days

    def is_active(self, today: date) -> bool:
        """Still running: the next payment is at most one period overdue."""
        return (today - self.next_date).days <= self.period_days


def _match_period(gap: float) -> tuple[str, float, float] | None:
    candidates = [period for period in PERIODS if abs(gap - period[1]) <= period[2]]
    return min(candidates, key=lambda period: abs(gap - period[1]) / period[1]) if candidates else None


def _to_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def find_recurring(transactions: list[dict]) -> list[RecurringSeries]:
    """Recurring expense series, largest monthly cost first. Rows need date, title, amount, type."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        key = merchant_key(tx.get("title"))
        if tx.get("type") == "EXPENSE" and key:
            groups[key].append(tx)

    series = []
    for key, rows in groups.items():
        if len(rows) < MIN_PAYMENTS:
            continue
        rows = sorted(rows, key=lambda row: _to_date(row["date"]))
        dates = [_to_date(row["date"]) for row in rows]
        gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:], strict=False)]
        median_gap = statistics.median(gaps)
        period = _match_period(median_gap)
        if period is None:
            continue
        name, days, tolerance = period
        regular_share = sum(abs(gap - days) <= tolerance for gap in gaps) / len(gaps)
        amounts = [float(row["amount"]) for row in rows]
        amount_cv = statistics.pstdev(amounts) / statistics.mean(amounts)
        if regular_share < MIN_REGULAR_SHARE or amount_cv > MAX_AMOUNT_CV:
            continue
        categories = [row.get("category_id") for row in rows if row.get("category_id") is not None]
        titles = Counter(row["title"] for row in rows)
        latest = {row["title"]: index for index, row in enumerate(rows)}
        series.append(RecurringSeries(
            key=key,
            title=max(titles, key=lambda title: (titles[title], latest[title])),  # ties: the most recent
            category_id=statistics.mode(categories) if categories else None,
            period=name,
            period_days=float(median_gap),
            amount=round(statistics.median(amounts[-3:]), 2),
            count=len(rows),
            first_date=dates[0],
            last_date=dates[-1],
        ))
    return sorted(series, key=lambda s: s.monthly_cost, reverse=True)
