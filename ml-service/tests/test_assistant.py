import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.assistant import tools
from app.assistant.router import parse_period, understand
from app.config import Settings
from app.main import create_app
from app.routers.insights import build_insights
from tests.conftest import OTHER_TOKEN, SUPABASE_URL, TEST_USER
from training import evaluate_assistant
from training.simulate_history import CATEGORY_IDS, simulate_users

SUNDAY = date(2026, 10, 18)
CATEGORIES = [{"id": i, "name": name.title(), "user_id": None} for name, i in CATEGORY_IDS.items()]
MERCHANTS = {"swiggy", "uber", "amazon"}


def ask(*messages: str):
    previous = None
    for message in messages:
        previous = understand(message, SUNDAY, CATEGORIES, MERCHANTS, previous)
    return previous


# ---------- understanding ----------

@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("how much did I spend on food last month", "spending"),
        ("where did most of my money go", "breakdown"),
        ("am I on track with my budget", "budget"),
        ("what subscriptions do I have", "subscriptions"),
        ("anything unusual?", "unusual"),
        ("add 450 swiggy yesterday", "add"),
        ("what does unusual spending mean", "help"),  # a definition, despite the data words
        ("how is the forecast calculated", "help"),
        ("hello", "greeting"),
        ("what's the weather today", "about"),  # off-topic: declined without searching the help center
        ("who made you?", "about"),
        ("What is your name", "about"),
        ("what can you do", "about"),
        ("which mutual fund should i invest in", "about"),
        ("how do i save money", "help"),
    ],
)
def test_intents(message, intent):
    assert ask(message).intent == intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Who made you?", "Ketul Mehta"),
        ("What is your name", "Expense Tracker assistant"),
        ("what can you do", "how much you spent"),
        ("tell me a joke", "outside what I can help with"),
        ("which mutual fund should i invest in", "can't recommend investments"),
    ],
)
def test_about_replies(message, expected):
    assert expected in tools.about_reply(message)


def test_periods():
    assert parse_period("this week", SUNDAY).start == date(2026, 10, 12)  # weeks start on Monday
    last_week = parse_period("last week", SUNDAY)
    assert (last_week.start, last_week.end) == (date(2026, 10, 5), date(2026, 10, 11))
    assert parse_period("in december", SUNDAY).start == date(2025, 12, 1)  # the most recent December
    assert parse_period("pichle mahine", SUNDAY).key == "last_month"
    assert parse_period("may I see my totals", SUNDAY) is None  # "may" needs "in" or "for"
    assert parse_period("in may", SUNDAY).key == "month:5"


def test_slots_use_the_users_own_categories_and_merchants():
    assert ask("how much on groceries this week").category["name"] == "Food"  # an alias
    assert ask("how much on swiggy this month").merchant == "swiggy"
    assert ask("total spent").period.key == "this_month"  # the default period


def test_follow_ups_keep_what_wasnt_changed():
    follow_up = ask("how much did I spend on food last month", "and this month?")
    assert follow_up.intent == "spending" and follow_up.category["name"] == "Food"
    assert follow_up.period.key == "this_month"
    swapped = ask("how much on swiggy in september", "what about shopping?")
    assert (swapped.category["name"], swapped.merchant, swapped.period.key) == ("Shopping", None, "month:9")


# ---------- tools: exact numbers ----------

def test_spending_and_breakdown_match_a_direct_computation():
    user = simulate_users(1, SUNDAY, seed=3)[0]
    period = parse_period("last month", SUNDAY)
    food = next(c for c in CATEGORIES if c["name"] == "Food")
    expected = sum(t["amount"] for t in user.transactions if t["type"] == "EXPENSE"
                   and t["category_id"] == food["id"] and "2026-09-01" <= t["date"] <= "2026-09-30")
    assert tools.spending(user.transactions, period, food)["total"] == pytest.approx(expected, abs=0.01)
    rows = tools.breakdown(user.transactions, CATEGORIES, period)
    assert sum(share for _, _, share in rows) == pytest.approx(1.0)
    assert rows == sorted(rows, key=lambda row: -row[1])


def test_replies_read_naturally():
    period = parse_period("last month", SUNDAY)
    assert tools.spending_reply({"total": 4120.4, "count": 14}, period, {"name": "Food"}, None) == (
        "You spent ₹4,120 on Food last month (14 payments)."
    )
    assert tools.spending_reply({"total": 0, "count": 0}, period, None, "uber") == (
        "You haven't spent anything at Uber last month."
    )
    user = simulate_users(1, SUNDAY, seed=3)[0]
    insights = build_insights(user.transactions, CATEGORIES, user.monthly_budget, SUNDAY)
    assert tools.budget_reply(insights).startswith("At this pace you'll spend about ₹")
    assert "a month:" in tools.subscriptions_reply(insights)


# ---------- the graph, through the API ----------

TODAY = datetime.now(UTC).date()


def history() -> list[dict]:
    rows, next_id = [], 1
    for offset in range(1, 40):
        day = (TODAY - timedelta(days=offset)).isoformat()
        for row_id, title, amount, category_id in ((next_id, "Swiggy", 300, 1),
                                                   (next_id + 1, "Uber", 150, 2)):
            rows.append({"id": row_id, "title": title, "amount": amount, "type": "EXPENSE",
                         "category_id": category_id, "date": day})
        next_id += 2
    return rows


@pytest.fixture
def chat(client, supabase, auth_headers):
    supabase.tables.update({"transactions": history(), "categories": CATEGORIES, "profiles": []})

    def send(message: str, thread: str = "t1", headers=None):
        body = {"message": message, "thread_id": thread, "today": TODAY.isoformat()}
        response = client.post("/v1/assistant/chat", json=body, headers=headers or auth_headers)
        assert response.status_code == 200, response.text
        return response.json()

    return send


def confirm(client, headers, approve: bool, thread: str = "t1"):
    return client.post("/v1/assistant/confirm", json={"thread_id": thread, "approve": approve,
                                                      "today": TODAY.isoformat()}, headers=headers)


def expected_spend(category_id: int, start: date, end: date) -> float:
    return sum(r["amount"] for r in history() if r["category_id"] == category_id
               and start.isoformat() <= r["date"] <= end.isoformat())


def test_chat_requires_a_token(client):
    assert client.post("/v1/assistant/chat", json={"message": "hi"}).status_code == 401


def test_spending_question_gets_the_exact_total_and_remembers_it(chat):
    first = chat("how much did I spend on food in the last 7 days")
    total = expected_spend(1, TODAY - timedelta(days=6), TODAY)
    assert first["intent"] == "spending"
    assert first["reply"].startswith(f"You spent ₹{total:,.0f} on Food in the last 7 days")
    follow_up = chat("what about travel?")
    travel = expected_spend(2, TODAY - timedelta(days=6), TODAY)
    assert f"₹{travel:,.0f} on Travel in the last 7 days" in follow_up["reply"]


def test_adding_waits_for_confirmation_then_saves(client, chat, supabase, auth_headers):
    before = len(supabase.tables["transactions"])
    draft = chat("add 450 swiggy yesterday")
    assert draft["intent"] == "add" and draft["reply"] == "Should I add this?"
    assert draft["pending"] | {} == {
        "title": "Swiggy", "amount": 450, "date": (TODAY - timedelta(days=1)).isoformat(), "type": "EXPENSE",
        "category_id": 1, "category_name": "Food",  # from the user's own history
    }
    assert len(supabase.tables["transactions"]) == before  # nothing saved yet

    saved = confirm(client, auth_headers, approve=True).json()
    assert saved["reply"].startswith("Saved expense: Swiggy, ₹450 on")
    stored = supabase.tables["transactions"][-1]
    assert (stored["title"], stored["amount"], stored["user_id"]) == ("Swiggy", 450, TEST_USER["id"])


def test_cancelling_saves_nothing(client, chat, supabase, auth_headers):
    before = len(supabase.tables["transactions"])
    chat("add 120 chai")
    assert confirm(client, auth_headers, approve=False).json()["reply"] == "Okay, I didn't save it."
    assert len(supabase.tables["transactions"]) == before


def test_a_new_message_cancels_a_pending_confirmation(client, chat, supabase, auth_headers):
    before = len(supabase.tables["transactions"])
    chat("add 120 chai")
    reply = chat("hello")
    assert reply["intent"] == "greeting" and reply["pending"] is None
    assert len(supabase.tables["transactions"]) == before
    assert confirm(client, auth_headers, approve=True).status_code == 409  # nothing is pending any more


def test_threads_are_private_to_each_user(client, chat):
    chat("add 120 chai", thread="shared-id")
    other = {"Authorization": f"Bearer {OTHER_TOKEN}"}
    assert confirm(client, other, approve=True, thread="shared-id").status_code == 409


def test_help_questions_use_the_help_center(client, chat):
    from app.rag.knowledge import load_chunks
    from app.rag.retriever import HelpIndex
    from tests.test_rag import WordEmbedder

    client.app.state.help_index = HelpIndex(load_chunks(), WordEmbedder(), decline_below=0.3)
    reply = chat("how do I export to pdf")
    assert reply["intent"] == "help" and reply["citations"][0]["article"] == "exporting"


def test_an_llm_routes_what_the_rules_dont_recognise(supabase, auth_headers, model_dir):
    supabase.tables.update({"transactions": history(), "categories": CATEGORIES, "profiles": []})
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir)
    model = FakeListChatModel(responses=[json.dumps({"intent": "subscriptions"})])
    app = create_app(settings, transport=httpx.MockTransport(supabase.handler), llm=model)
    with TestClient(app) as client:
        body = client.post("/v1/assistant/chat", json={"message": "netflix and co, what am i paying for?"},
                           headers=auth_headers).json()
    assert body["intent"] == "subscriptions"


@pytest.mark.parametrize(
    ("message", "llm_reply", "expected"),
    [
        # Off-topic for the rules, but a money question: the LLM answers it
        ("which mutual fund should i invest in", "A mutual fund pools money; this isn't financial advice.",
         "pools money"),
        # The LLM says it's off-topic: the rule-based decline is kept
        ("tell me a joke", "OFF_TOPIC", "outside what I can help with"),
        # Questions about the assistant never reach the LLM
        ("who made you", "should not be used", "Ketul Mehta"),
    ],
)
def test_an_llm_answers_general_money_questions(
    supabase, auth_headers, model_dir, message, llm_reply, expected
):
    supabase.tables.update({"transactions": history(), "categories": CATEGORIES, "profiles": []})
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir)
    model = FakeListChatModel(responses=[llm_reply])
    app = create_app(settings, transport=httpx.MockTransport(supabase.handler), llm=model)
    with TestClient(app) as client:
        body = client.post("/v1/assistant/chat", json={"message": message}, headers=auth_headers).json()
    assert body["intent"] == "about" and expected in body["reply"]


def test_evaluation_script_passes_its_gate(tmp_path):
    assert evaluate_assistant.main(["--gate", "--report-dir", str(tmp_path)]) == 0
