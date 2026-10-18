from datetime import date, timedelta

import numpy as np
import pytest

from app.ml.anomaly import find_anomalies, leave_one_out_quantile
from app.ml.forecast import forecast_month, payments_due
from app.ml.recurring import find_recurring, merchant_key

START = date(2026, 1, 1)


def tx(tx_id: int, day: date, title: str, amount: float, category_id: int = 1, tx_type: str = "EXPENSE"):
    return {"id": tx_id, "date": day.isoformat(), "title": title, "amount": amount,
            "type": tx_type, "category_id": category_id}


def monthly(title: str, amount: float, months: int, day_of_month: int = 5, start_id: int = 1000, **kwargs):
    return [tx(start_id + m, date(2026, m + 1, day_of_month), title, amount, **kwargs) for m in range(months)]


def irregular(title: str, amounts: list[float], start_id: int = 1, category_id: int = 1, seed: int = 0):
    """Payments on random, uneven days: frequent but not recurring."""
    rng = np.random.default_rng(seed)
    days = np.sort(rng.choice(np.arange(0, 270), size=len(amounts), replace=False))
    return [tx(start_id + i, START + timedelta(days=int(d)), title, a, category_id)
            for i, (d, a) in enumerate(zip(days, amounts, strict=True))]


# ---------- unusual spending ----------

def test_leave_one_out_quantile_matches_brute_force():
    rng = np.random.default_rng(3)
    for n in (2, 3, 9, 40):
        values = rng.lognormal(5, 1, n).round()
        expected = [np.quantile(np.delete(values, i), 0.9) for i in range(n)]
        assert np.allclose(leave_one_out_quantile(values, 0.9), expected)


def test_flags_a_payment_far_above_the_merchants_usual_top():
    rows = irregular("Swiggy", [300 + 10 * i for i in range(20)] + [4800])
    [found] = find_anomalies(rows)
    assert found.amount == 4800 and found.compared_with == "merchant"
    assert found.ratio > 6 and found.usual_high < 500


def test_ordinary_variation_is_not_flagged():
    rows = irregular("Amazon", [300, 450, 800, 1200, 2000, 3500, 600, 900, 1500, 2500, 700, 4000])
    assert find_anomalies(rows) == []


def test_small_payments_are_never_flagged():
    rows = irregular("Chai", [20] * 15 + [450])  # 22x the usual, but under ₹500
    assert find_anomalies(rows) == []


def test_needs_enough_history():
    rows = irregular("Uber", [200, 210, 190, 205, 3000])
    assert find_anomalies(rows) == []


def test_falls_back_to_the_category_for_rare_merchants():
    rows = irregular("Uber", [200 + 5 * i for i in range(15)], category_id=2)
    rows.append(tx(99, date(2026, 6, 3), "Fancy limo", 6000, category_id=2))
    [found] = find_anomalies(rows)
    assert found.transaction_id == 99 and found.compared_with == "category"


def test_one_earlier_spike_does_not_hide_the_next():
    amounts = [300 + 5 * i for i in range(30)]
    amounts[10], amounts[25] = 5000, 5200
    found = {a.amount for a in find_anomalies(irregular("Swiggy", amounts))}
    assert found == {5000, 5200}


# ---------- recurring payments ----------

def test_merchant_key_ignores_months_formats_and_filler():
    assert merchant_key("Rent for October") == merchant_key("rent nov") == "rent"
    assert merchant_key("NETFLIX.COM") == merchant_key("Netflix subscription") == "netflix"
    assert merchant_key("UPI/HOUSE RENT/88213/Pay") == "house rent"


def test_finds_monthly_subscriptions_despite_title_variations():
    titles = ["Netflix", "NETFLIX.COM", "Netflix subscription"] * 3
    rows = [tx(i, date(2026, i + 1, 7), title, 649) for i, title in enumerate(titles)]
    [series] = find_recurring(rows)
    assert (series.key, series.period, series.count, series.amount) == ("netflix", "monthly", 9, 649)
    assert series.next_date == date(2026, 10, 7)


def test_detects_weekly_and_28_day_rhythms():
    weekly = [tx(i, START + timedelta(days=7 * i), "Cleaning service", 400) for i in range(10)]
    plan = [tx(100 + i, START + timedelta(days=28 * i), "Jio recharge", 299) for i in range(6)]
    periods = {s.key: s.period for s in find_recurring(weekly + plan)}
    assert periods == {"cleaning service": "weekly", "jio": "every 28 days"}


def test_bills_may_vary_a_little_in_amount():
    rows = monthly("Electricity bill", 0, 8)
    for row, amount in zip(rows, [1800, 2100, 1650, 1900, 2300, 2000, 1750, 2200], strict=True):
        row["amount"] = amount
    assert [s.period for s in find_recurring(rows)] == ["monthly"]


def test_frequent_irregular_spending_is_not_recurring():
    rows = irregular("Swiggy", [250 + 30 * (i % 7) for i in range(40)])
    rows += irregular("BigBasket", [400, 2500, 900, 3000, 650, 1800, 300, 2200], start_id=500, seed=1)
    assert find_recurring(rows) == []


def test_a_skipped_month_does_not_break_a_series():
    rows = [r for r in monthly("Gym membership", 1500, 9) if r["date"] != "2026-05-05"]
    assert [s.period for s in find_recurring(rows)] == ["monthly"]


def test_cancelled_series_becomes_inactive():
    [series] = find_recurring(monthly("Spotify", 119, 4))  # last payment 5 April
    assert series.is_active(date(2026, 5, 20))
    assert not series.is_active(date(2026, 8, 1))


# ---------- forecast ----------

def history(days: int, today: date, daily: float = 100.0, rent: float = 10000.0) -> list[dict]:
    rows = [tx(i, today - timedelta(days=i), "Groceries", daily) for i in range(days)]
    first = today - timedelta(days=days)
    months = sorted({(d.year, d.month) for d in (first + timedelta(days=n) for n in range(days + 1))})
    rows += [tx(10_000 + i, date(y, m, 3), "House rent", rent, category_id=7)
             for i, (y, m) in enumerate(months) if first < date(y, m, 3) <= today]
    return rows


def test_forecast_adds_everyday_spending_for_the_rest_of_the_month():
    today = date(2026, 7, 15)
    result = forecast_month(history(120, today), today)
    assert result.spent_to_date == pytest.approx(10000 + 15 * 100)
    assert result.expected_everyday == pytest.approx(16 * 100)  # 16 more days in July
    assert result.expected_recurring == 0  # this month's rent is already paid
    assert result.projected_total == pytest.approx(13100)


def test_forecast_counts_recurring_payments_still_due():
    today = date(2026, 7, 2)  # rent comes on the 3rd
    result = forecast_month(history(120, today), today)
    assert result.expected_recurring == pytest.approx(10000)
    assert result.low <= result.projected_total <= result.high


def test_forecast_reports_budget_risk():
    today = date(2026, 7, 15)
    rows = history(120, today)
    rows += [tx(50_000 + i, today - timedelta(days=i), "Swiggy", 300 + 200 * (i % 3))
             for i in range(0, 60, 2)]
    tight = forecast_month(rows, today, budget=12_000)
    assert tight.status == "over" and tight.probability_over_budget == 1.0
    loose = forecast_month(rows, today, budget=100_000)
    assert loose.status == "on_track" and loose.probability_over_budget < 0.01
    assert tight.low < tight.projected_total < tight.high  # everyday spending varies, so there is a band


def test_forecast_needs_four_weeks_of_history():
    today = date(2026, 7, 15)
    assert forecast_month(history(20, today), today) is None
    assert forecast_month([], today) is None


def test_payments_due_counts_weekly_occurrences_and_drops_long_overdue():
    weekly = find_recurring([tx(i, date(2026, 6, 1) + timedelta(days=7 * i), "Cleaning service", 400)
                             for i in range(5)])[0]  # last payment 29 June
    assert payments_due(weekly, date(2026, 7, 1), date(2026, 7, 31)) == 4  # 6, 13, 20, 27 July
    assert payments_due(weekly, date(2026, 7, 20), date(2026, 7, 31)) == 0  # 3 weeks overdue: stopped
