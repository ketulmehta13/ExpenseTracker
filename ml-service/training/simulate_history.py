"""Synthetic transaction histories with ground truth, for evaluating the insight detectors.

Each simulated user gets a year of transactions:
- a monthly salary;
- recurring payments on a fixed rhythm (rent, subscriptions, bills), written with the small
  title variations real entries have: the ground truth for recurring-payment detection;
- everyday spending at the same merchants with no rhythm, with lognormal amounts, so a
  legitimately large purchase now and then is normal. These are the hard negatives for both
  detectors: ordering from Swiggy three times a week is frequent, not recurring;
- a few injected payments far above what the user normally pays at that merchant: the
  ground truth for anomaly detection.

Usage (from ml-service/):  python -m training.simulate_history
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

CATEGORY_IDS = {
    "food": 1, "travel": 2, "shopping": 3, "utilities": 4, "entertainment": 5,
    "health": 6, "rent": 7, "salary": 8, "other": 9,
}

# title variants, category, period, amount range, relative jitter of the amount between payments.
# "{month}" becomes the payment's month and "{ref}" a reference number.
RECURRING = [
    (["House rent", "House rent for {month}", "UPI/HOUSE RENT/{ref}/Pay"], "rent", "monthly",
     (8000, 30000), 0.0),
    (["Netflix", "NETFLIX.COM", "Netflix subscription"], "entertainment", "monthly", (199, 649), 0.0),
    (["Spotify Premium", "SPOTIFY", "Spotify India"], "entertainment", "monthly", (119, 179), 0.0),
    (["Jio recharge", "JIO PREPAID", "Jio plan"], "utilities", "every 28 days", (239, 719), 0.0),
    (["Electricity bill", "Electricity bill {month}", "electricity"], "utilities", "monthly",
     (600, 3500), 0.2),
    (["Gym membership", "GYM MEMBERSHIP", "Gym membership {month}"], "health", "monthly", (1000, 3000), 0.0),
    (["Maid salary", "Maid salary {month}"], "other", "monthly", (2000, 5000), 0.0),
    (["Cleaning service", "cleaning service"], "other", "weekly", (300, 600), 0.0),
    (["Airtel broadband", "AIRTEL BROADBAND", "UPI/AIRTEL BROADBAND/{ref}/Pay"], "utilities", "monthly",
     (499, 1199), 0.0),
    (["Milk subscription", "milk subscription"], "food", "weekly", (280, 420), 0.1),
]
PERIOD_DAYS = {"weekly": 7, "every 28 days": 28, "monthly": 30}

# titles, category, purchases per week, amount range covering ~95% of purchases, weekend multiplier
EVERYDAY = [
    (["Swiggy", "Zomato", "Swiggy order"], "food", 3.0, (150, 900), 1.6),
    (["BigBasket", "Zepto groceries", "DMart"], "food", 1.2, (300, 3000), 1.4),
    (["Uber", "Ola cab", "Rapido"], "travel", 2.5, (60, 600), 0.8),
    (["Amazon", "Flipkart", "Myntra"], "shopping", 0.7, (300, 5000), 1.3),
    (["PVR movie", "BookMyShow"], "entertainment", 0.25, (200, 1200), 2.5),
    (["Apollo Pharmacy", "MedPlus"], "health", 0.3, (100, 1500), 1.0),
    (["Petrol", "HP petrol pump"], "travel", 0.6, (500, 2500), 1.0),
]


@dataclass
class SimulatedUser:
    transactions: list[dict]  # id, date (ISO string), title, amount, type, category_id
    recurring: dict[str, str]  # base title of each recurring payment -> its period
    anomaly_ids: set[int]
    monthly_budget: float


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    return low * (high / low) ** rng.random()


def _lognormal_in(rng: random.Random, low: float, high: float) -> float:
    """Lognormal amount with about 95% of draws inside [low, high], and a long right tail."""
    mu, sigma = (math.log(low) + math.log(high)) / 2, (math.log(high) - math.log(low)) / 4
    return math.exp(rng.gauss(mu, sigma))


def _poisson(rng: random.Random, rate: float) -> int:
    # Knuth's method: fine for the small daily rates used here
    threshold, count, product = math.exp(-rate), 0, rng.random()
    while product > threshold:
        count += 1
        product *= rng.random()
    return count


def _monthly_dates(rng: random.Random, start: date, end: date, day_of_month: int) -> list[date]:
    dates, year, month = [], start.year, start.month
    while True:
        jitter = rng.choice([0, 0, 0, 1, 2])  # usually on the day, sometimes a day or two late
        when = date(year, month, min(day_of_month + jitter, 28))
        if when > end:
            return dates
        if when >= start:
            dates.append(when)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _interval_dates(rng: random.Random, start: date, end: date, days: int) -> list[date]:
    dates, when = [], start
    while when <= end:
        dates.append(when + timedelta(days=rng.choice([0, 0, 0, 1]) if days == 7 else 0))
        when += timedelta(days=days)
    return [d for d in dates if d <= end]


def simulate_user(rng: random.Random, end: date, months: int = 12, anomalies: int = 3) -> SimulatedUser:
    start = end - timedelta(days=round(months * 30.44))
    rows: list[dict] = []

    def add(when: date, title: str, amount: float, category: str, tx_type: str = "EXPENSE") -> dict:
        row = {
            "date": when.isoformat(), "title": title, "amount": round(amount, 2),
            "type": tx_type, "category_id": CATEGORY_IDS[category],
        }
        rows.append(row)
        return row

    salary = round(_log_uniform(rng, 25000, 150000), -3)
    for when in _monthly_dates(rng, start, end, rng.randint(1, 3)):
        add(when, "Salary credit", salary, "salary", "INCOME")

    recurring: dict[str, str] = {}
    for variants, category, period, (low, high), jitter in rng.sample(RECURRING, k=rng.randint(3, 6)):
        amount = round(_log_uniform(rng, low, high), -1)
        # Some start late or get cancelled part-way through the year
        series_start = start + timedelta(days=rng.choice([0, 0, 0, rng.randint(30, 120)]))
        series_end = end - timedelta(days=rng.choice([0, 0, 0, 0, rng.randint(60, 150)]))
        if period == "monthly":
            dates = _monthly_dates(rng, series_start, series_end, rng.randint(1, 26))
        else:
            dates = _interval_dates(rng, series_start, series_end, PERIOD_DAYS[period])
        if len(dates) >= 3:
            recurring[variants[0]] = period
        raise_month = rng.choice([None, None, rng.randint(4, 10)])  # sometimes the price goes up once
        for index, when in enumerate(dates):
            title = rng.choice(variants).format(month=f"{when:%B}", ref=rng.randint(10_000, 99_999_999))
            price = amount * (1.08 if raise_month is not None and index >= raise_month else 1.0)
            add(when, title, price * (1 + rng.uniform(-jitter, jitter)), category)

    everyday: list[tuple[dict, float]] = []  # each row with the top of its habit's normal range
    habits = [(titles, category, rate * rng.uniform(0.5, 1.5), amounts, weekend)
              for titles, category, rate, amounts, weekend in EVERYDAY if rng.random() < 0.85]
    day = start
    while day <= end:
        weekend_day = day.weekday() >= 5
        for titles, category, rate, (low, high), weekend in habits:
            for _ in range(_poisson(rng, rate / 7 * (weekend if weekend_day else 1.0))):
                everyday.append((add(day, rng.choice(titles), _lognormal_in(rng, low, high), category), high))
        day += timedelta(days=1)

    # Unusually large payments: 5-15x the top of the user's normal range at that kind of merchant
    spikes = rng.sample(everyday, k=min(anomalies, len(everyday)))
    for row, high in spikes:
        row["amount"] = round(high * rng.uniform(5, 15), 2)

    rows.sort(key=lambda row: row["date"])
    for index, row in enumerate(rows, start=1):
        row["id"] = index
    monthly_spend = sum(r["amount"] for r in rows if r["type"] == "EXPENSE") / months
    return SimulatedUser(
        transactions=rows,
        recurring=recurring,
        anomaly_ids={row["id"] for row, _ in spikes},
        monthly_budget=round(monthly_spend * rng.uniform(0.9, 1.2), -3),
    )


def simulate_users(count: int, end: date, seed: int = 42) -> list[SimulatedUser]:
    rng = random.Random(seed)
    return [simulate_user(rng, end) for _ in range(count)]


if __name__ == "__main__":
    user = simulate_users(1, date(2026, 10, 18))[0]
    print(f"{len(user.transactions)} transactions, budget {user.monthly_budget:,.0f}")
    print("recurring:", user.recurring)
    print("anomalies:", [t for t in user.transactions if t["id"] in user.anomaly_ids])
