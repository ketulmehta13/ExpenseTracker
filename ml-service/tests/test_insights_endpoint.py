import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from training import evaluate_insights
from training.simulate_history import CATEGORY_IDS, EVERYDAY, simulate_users

TODAY = datetime.now(UTC).date()
CATEGORIES = [{"id": category_id, "name": name.title()} for name, category_id in CATEGORY_IDS.items()]


def shifted(transactions: list[dict], to: date) -> list[dict]:
    """Move a simulated history so it ends on `to`."""
    offset = to - max(date.fromisoformat(tx["date"]) for tx in transactions)
    return [{**tx, "date": (date.fromisoformat(tx["date"]) + offset).isoformat()} for tx in transactions]


@pytest.fixture
def simulated(supabase):
    user = simulate_users(1, date(2026, 10, 18), seed=5)[0]
    supabase.tables["transactions"] = shifted(user.transactions, TODAY)
    supabase.tables["categories"] = CATEGORIES
    supabase.tables["profiles"] = [{"monthly_budget": 40000}]
    return user


def test_requires_a_token(client):
    assert client.get("/v1/insights").status_code == 401


def test_returns_all_three_insights(client, auth_headers, simulated):
    response = client.get("/v1/insights", params={"today": TODAY.isoformat()}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["as_of"] == TODAY.isoformat()

    active = [p for p in body["recurring"] if p["active"]]
    true_merchants = {title.split()[0].lower() for title in simulated.recurring}
    assert {p["title"].split()[0].lower() for p in active} <= true_merchants
    assert body["recurring_monthly_total"] == pytest.approx(sum(p["monthly_cost"] for p in active), abs=0.05)

    forecast = body["forecast"]
    assert forecast["budget"] == 40000
    assert forecast["low"] <= forecast["projected_total"] <= forecast["high"]
    assert forecast["status"] in {"on_track", "at_risk", "over"}

    for payment in body["unusual"]:
        assert payment["ratio"] >= 6 and payment["category_name"]
        assert date.fromisoformat(payment["date"]) >= TODAY - timedelta(days=60)


def test_flags_a_recent_spike(client, auth_headers, simulated, supabase):
    rows = supabase.tables["transactions"]
    everyday_titles = {title for titles, *_ in EVERYDAY for title in titles}
    merchant, _ = Counter(tx["title"] for tx in rows if tx["title"] in everyday_titles).most_common(1)[0]
    past = [tx for tx in rows if tx["title"] == merchant]
    usual_top = sorted(tx["amount"] for tx in past)[int(len(past) * 0.9)]
    spike = round(usual_top * 9 + 500, 2)
    rows.append({**past[0], "id": 999_999, "date": TODAY.isoformat(), "amount": spike})
    body = client.get("/v1/insights", headers=auth_headers).json()
    assert 999_999 in {payment["transaction_id"] for payment in body["unusual"]}


def test_new_users_get_empty_insights(client, auth_headers, supabase):
    supabase.tables.update({"transactions": [], "categories": CATEGORIES, "profiles": []})
    body = client.get("/v1/insights", headers=auth_headers).json()
    assert body["unusual"] == [] and body["recurring"] == [] and body["forecast"] is None


def test_results_are_cached_per_user_and_day(client, auth_headers, simulated, supabase):
    client.get("/v1/insights", headers=auth_headers)
    calls = supabase.rest_calls
    client.get("/v1/insights", headers=auth_headers)
    assert supabase.rest_calls == calls


def test_rejects_a_date_far_from_today(client, auth_headers, simulated):
    response = client.get("/v1/insights", params={"today": "2020-01-01"}, headers=auth_headers)
    assert response.status_code == 422


def test_evaluation_script_writes_reports(tmp_path):
    exit_code = evaluate_insights.main(["--users", "4", "--report-dir", str(tmp_path)])
    assert exit_code == 0  # without --gate, a small run never fails
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) >= {"anomalies", "recurring", "forecast", "gate"}
    assert "Evaluation gate" in (tmp_path / "report.md").read_text(encoding="utf-8")
