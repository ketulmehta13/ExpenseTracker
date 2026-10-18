"""Unusual-spending detection: payments far above the user's normal range.

A payment is unusual when it is at least MIN_RATIO times the user's usual top payment (the
90th percentile of their other payments) at the same merchant. When there's too little
history at that merchant, the payment is compared with the rest of its category instead.

    ratio = amount / P90(other payments in the group)       unusual if ratio >= MIN_RATIO

Why this rule (training/evaluate_insights.py has the numbers):
- Robust z-scores, (x - median) / MAD, are the textbook choice and were tried first. Their bar
  scales with the spread of past payments, so merchants with widely varying amounts (Amazon:
  a ₹300 cable or a ₹4,000 jacket) hid 20x spikes, while merchants with a few similar payments
  raised false alarms.
- The 90th percentile of the *other* payments is robust: one earlier outlier can't raise the
  bar for the next (masking), and the payment being judged is never part of its own baseline.
- It explains itself: "₹24,000 at Amazon, 5x more than your usual top payment there".
- Merchant first: categories mix price levels (a weekly cleaner and a monthly maid are both
  "Other"), so a category baseline flags ordinary payments to the pricier merchant.
- Recurring payments are left out: they have their own detector, and a fixed price says
  nothing about spending habits.

MIN_RATIO is tuned on simulated validation users and scored on separate test users.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.ml.recurring import find_recurring, merchant_key

MIN_RATIO = 6.0  # F1 is within 2 points of its best anywhere from 4x to 7x on validation users
QUANTILE = 0.9  # "usual top payment"
MIN_HISTORY = 8  # payments needed in a group before judging any of them
MIN_AMOUNT = 500.0  # never flag small payments, however unusual


@dataclass(frozen=True)
class Anomaly:
    transaction_id: int | str
    category_id: int | str | None
    amount: float
    usual_high: float  # the 90th percentile of the other payments in the group
    typical_amount: float  # their median
    compared_with: str  # "merchant" or "category"

    @property
    def ratio(self) -> float:
        return self.amount / self.usual_high


@dataclass(frozen=True)
class PeerGroup:
    compared_with: str  # "merchant" or "category"
    baseline: list[int]  # indexes of the payments that define "normal"
    judged: list[int]  # indexes of the payments judged against them


def candidate_expenses(transactions: list[dict], exclude_recurring: bool = True) -> list[dict]:
    """Expenses that can be judged at all: positive amounts, minus recurring payments."""
    expenses = [tx for tx in transactions if tx.get("type") == "EXPENSE" and float(tx["amount"]) > 0]
    if exclude_recurring:
        recurring_keys = {series.key for series in find_recurring(expenses)}
        expenses = [tx for tx in expenses if merchant_key(tx.get("title")) not in recurring_keys]
    return expenses


def peer_groups(
    expenses: list[dict], merchant_first: bool = True, min_history: int = MIN_HISTORY
) -> list[PeerGroup]:
    """Judge each payment once: against its merchant's history when there's enough, else its category's."""
    by_merchant: dict[str, list[int]] = defaultdict(list)
    by_category: dict[int | str, list[int]] = defaultdict(list)
    for index, tx in enumerate(expenses):
        by_merchant[merchant_key(tx.get("title"))].append(index)
        if tx.get("category_id") is not None:
            by_category[tx["category_id"]].append(index)

    groups: list[PeerGroup] = []
    judged_by_merchant: set[int] = set()
    if merchant_first:
        for members in by_merchant.values():
            if len(members) >= min_history:
                groups.append(PeerGroup("merchant", members, members))
                judged_by_merchant.update(members)
    for members in by_category.values():
        judged = [index for index in members if index not in judged_by_merchant]
        if judged and len(members) >= min_history:
            groups.append(PeerGroup("category", members, judged))
    return groups


def leave_one_out_quantile(values: np.ndarray, q: float) -> np.ndarray:
    """For each value, the q-quantile of all the *other* values (linear interpolation), in O(n log n).

    Removing the element of sorted rank k shifts every later element down by one place, so the
    quantile of the rest can be read straight from the sorted array.
    """
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=int)
    ranks[order] = np.arange(len(values))
    ordered = values[order]
    position = (len(values) - 2) * q  # quantile position among the n - 1 others
    low = int(np.floor(position))
    high = min(low + 1, len(values) - 2)
    fraction = position - low
    at_low = np.where(ranks > low, ordered[low], ordered[low + 1])
    at_high = np.where(ranks > high, ordered[high], ordered[high + 1])
    return at_low + fraction * (at_high - at_low)


def find_anomalies(
    transactions: list[dict],
    min_ratio: float = MIN_RATIO,
    merchant_first: bool = True,
    exclude_recurring: bool = True,
    min_history: int = MIN_HISTORY,
    min_amount: float = MIN_AMOUNT,
) -> list[Anomaly]:
    """Unusually large expenses, largest ratio first. Rows need id, title, amount, type, category_id.

    `merchant_first` and `exclude_recurring` exist to measure what each idea contributes.
    """
    expenses = candidate_expenses(transactions, exclude_recurring)
    amounts = np.array([float(tx["amount"]) for tx in expenses])
    found = []
    for group in peer_groups(expenses, merchant_first, min_history):
        baseline = amounts[group.baseline]
        # Each payment is compared with the others only, never with itself
        usual_highs = dict(zip(group.baseline, leave_one_out_quantile(baseline, QUANTILE), strict=True))
        typicals = dict(zip(group.baseline, leave_one_out_quantile(baseline, 0.5), strict=True))
        for index in group.judged:
            amount, usual_high = float(amounts[index]), float(usual_highs[index])
            if amount >= min_amount and amount >= min_ratio * usual_high:
                tx = expenses[index]
                found.append(Anomaly(
                    transaction_id=tx["id"],
                    category_id=tx.get("category_id"),
                    amount=amount,
                    usual_high=round(usual_high, 2),
                    typical_amount=round(float(typicals[index]), 2),
                    compared_with=group.compared_with,
                ))
    return sorted(found, key=lambda anomaly: anomaly.ratio, reverse=True)
