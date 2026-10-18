from datetime import UTC, date, datetime, timedelta

import pytest

from app.nlp.quickadd import parse_quick_add
from training import evaluate_quickadd

SUNDAY = date(2026, 10, 18)


def parse(text: str):
    return parse_quick_add(text, SUNDAY)


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("swiggy 450", 450),
        ("₹2,499 amazon", 2499),
        ("rs.250 parking", 250),
        ("petrol 500 rs", 500),
        ("450/- chai", 450),
        ("INR 1,25,000 laptop", 125000),  # Indian digit grouping
        ("groceries 1,250.50", 1250.5),
        ("uber 1.5k", 1500),
        ("bonus 2 lakh", 200000),
        ("2 coffees 300", 300),  # no currency marker: the largest number
        ("2 coffees ₹30", 30),  # a currency marker beats size
        ("tata 1mg 430", 430),  # digits inside a word are not an amount
    ],
)
def test_amounts(text, amount):
    assert parse(text).amount == amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("lunch 250", SUNDAY),
        ("lunch 250 yesterday", date(2026, 10, 17)),
        ("lunch 250 kal", date(2026, 10, 17)),
        ("lunch 250 day before yesterday", date(2026, 10, 16)),
        ("lunch 250 3 days ago", date(2026, 10, 15)),
        ("lunch 250 a week ago", date(2026, 10, 11)),
        ("lunch 250 friday", date(2026, 10, 16)),  # the most recent Friday
        ("lunch 250 sunday", SUNDAY),  # today is a Sunday
        ("lunch 250 last sunday", date(2026, 10, 11)),
        ("lunch 250 on 3rd oct", date(2026, 10, 3)),
        ("lunch 250 oct 3", date(2026, 10, 3)),
        ("lunch 250 12/10", date(2026, 10, 12)),  # day first
        ("lunch 250 05/10/2026", date(2026, 10, 5)),
        ("lunch 250 2026-09-30", date(2026, 9, 30)),
        ("lunch 250 25 dec", date(2025, 12, 25)),  # no year: the most recent past one
        ("lunch 250 on the 20th", date(2026, 9, 20)),  # this month's 20th is still to come
    ],
)
def test_dates(text, expected):
    assert parse(text).date == expected


def test_a_date_number_is_never_the_amount():
    entry = parse("rent 18000 1st oct")
    assert (entry.amount, entry.date, entry.title) == (18000, date(2026, 10, 1), "Rent")


def test_an_implausible_year_is_left_for_the_amount():
    entry = parse("insurance 5 sep 2000")
    assert (entry.amount, entry.date) == (2000, date(2026, 9, 5))


@pytest.mark.parametrize(
    ("text", "tx_type"),
    [
        ("salary 85000", "INCOME"),
        ("received 1500 from rahul", "INCOME"),
        ("refund 499 amazon", "INCOME"),
        ("got 2000 from dad", "INCOME"),
        ("maid salary 3000", "EXPENSE"),  # paying someone's salary
        ("credit card bill 12000", "EXPENSE"),
        ("paid 500 to rahul", "EXPENSE"),
    ],
)
def test_types(text, tx_type):
    assert parse(text).type == tx_type


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("paid 1200 for groceries at dmart", "Groceries at dmart"),
        ("spent 1.5k on shopping", "Shopping"),
        ("uber 340 to office", "Uber to office"),  # inner words stay
        ("salary credited 92k", "Salary"),
        ("paid rent 20000 for october", "Rent for october"),
        ("iphone 15 79900", "Iphone 15"),  # other numbers stay in the title
    ],
)
def test_titles(text, title):
    assert parse(text).title == title


def test_reports_which_fields_came_from_the_text():
    assert parse("swiggy 450").found == {"amount": True, "date": False, "type": False}
    assert parse("salary yesterday").found == {"amount": False, "date": True, "type": True}


def test_text_without_numbers_still_gives_a_title():
    entry = parse("coffee with team")
    assert (entry.title, entry.amount, entry.date) == ("Coffee with team", None, SUNDAY)


# ---------- POST /v1/parse ----------

def test_requires_a_token(client):
    assert client.post("/v1/parse", json={"text": "swiggy 450"}).status_code == 401


def test_parse_endpoint_fills_the_draft_and_suggests_a_category(client, supabase, auth_headers):
    supabase.tables["categories"] = [{"id": 10, "name": "Dining Out", "user_id": "u"}]
    supabase.tables["transactions"] = [{"title": "Swiggy order", "category_id": 10}]
    today = datetime.now(UTC).date()
    response = client.post(
        "/v1/parse", json={"text": "swiggy 450 yesterday", "today": today.isoformat()}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["amount"], body["date"], body["type"]) == (
        "Swiggy", 450, (today - timedelta(days=1)).isoformat(), "EXPENSE"
    )
    assert body["suggestion"]["category_id"] == 10 and body["suggestion"]["source"] == "history"


def test_parse_endpoint_without_a_title_skips_the_suggestion(client, supabase, auth_headers):
    body = client.post("/v1/parse", json={"text": "450"}, headers=auth_headers).json()
    assert body["title"] == "" and body["amount"] == 450 and body["suggestion"] is None


def test_parse_endpoint_validates_input(client, auth_headers):
    assert client.post("/v1/parse", json={"text": ""}, headers=auth_headers).status_code == 422
    too_far = {"text": "lunch 250", "today": "2020-01-01"}
    assert client.post("/v1/parse", json=too_far, headers=auth_headers).status_code == 422


def test_evaluation_script_passes_its_gate(tmp_path, model_dir):
    arguments = ["--gate", "--report-dir", str(tmp_path), "--model-dir", str(model_dir)]
    assert evaluate_quickadd.main(arguments) == 0
    assert "Every test failure" in (tmp_path / "report.md").read_text(encoding="utf-8")
