import asyncio
import json
import random
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.config import Settings
from app.llm.extract import LLMDraft, checked_fields, llm_draft, merge, needs_llm
from app.llm.provider import build_chat_model
from app.llm.summary import MonthFacts, money, month_facts, summarize, template_summary, template_text
from app.llm.verify import fill_placeholders
from app.main import create_app
from app.nlp.quickadd import parse_quick_add
from app.routers.insights import build_insights
from tests.conftest import SUPABASE_URL
from training.simulate_history import CATEGORY_IDS, simulate_users

SUNDAY = date(2026, 10, 18)


def fake(*responses: str) -> FakeListChatModel:
    return FakeListChatModel(responses=list(responses))


def draft_json(**fields) -> str:
    return json.dumps({"title": "", "amount": None, "date": None, "type": "EXPENSE", **fields})


# ---------- grounding: the model writes placeholders, code writes numbers ----------

VALUES = {"spent": "₹10,422", "budget": "₹40,000"}


def test_placeholders_are_filled_with_values_computed_in_code():
    text = "You've spent [spent] of your [budget] budget."
    assert fill_placeholders(text, VALUES) == "You've spent ₹10,422 of your ₹40,000 budget."


@pytest.mark.parametrize(
    "text",
    [
        "You've spent ₹10,422 so far.",  # copied a number instead of using the placeholder
        "You've spent [spent], 13% more than last month.",  # computed a new one
        "You're saving [savings] a month.",  # a placeholder with no value
    ],
)
def test_text_that_writes_its_own_numbers_is_rejected(text):
    assert fill_placeholders(text, VALUES) is None


def test_digits_inside_known_names_are_allowed():
    assert fill_placeholders("Tata 1mg cost [spent].", VALUES, names=["Tata 1mg"]) == "Tata 1mg cost ₹10,422."


def test_money_uses_indian_digit_grouping():
    assert [money(v) for v in (999, 12345.4, 125000, 1234567, -500)] == [
        "₹999",
        "₹12,345",
        "₹1,25,000",
        "₹12,34,567",
        "-₹500",
    ]


# ---------- provider switch ----------


def test_provider_switch():
    assert build_chat_model(Settings()) is None
    assert type(build_chat_model(Settings(llm_provider="ollama"))).__name__ == "ChatOllama"
    hosted = Settings(llm_provider="openai", llm_base_url="https://example.com/v1", llm_api_key="k")
    assert type(build_chat_model(hosted)).__name__ == "ChatOpenAI"
    with pytest.raises(ValueError):
        build_chat_model(Settings(llm_provider="gpt-magic"))


def test_api_key_is_not_printed():
    assert "secret" not in repr(Settings(llm_api_key="secret"))


# ---------- quick-add fallback ----------


def test_the_llm_is_only_asked_when_the_rules_look_unsure():
    assert not needs_llm(parse_quick_add("swiggy 450 yesterday", SUNDAY))
    assert needs_llm(parse_quick_add("ola 250 3 days back", SUNDAY))  # time words left in the title
    assert needs_llm(parse_quick_add("coffee with the team", SUNDAY))  # no amount


def test_llm_draft_parses_structured_output():
    model = fake(draft_json(title="Ola", amount=250, date="2026-10-15"))
    draft = asyncio.run(llm_draft(model, "ola 250 3 days back", SUNDAY, timeout=5))
    assert draft == LLMDraft(title="Ola", amount=250, date=date(2026, 10, 15), type="EXPENSE")


@pytest.mark.parametrize("reply", ["Sure! It was Ola for 250.", '{"title": "Ola"}', ""])
def test_unusable_llm_replies_are_ignored(reply):
    assert asyncio.run(llm_draft(fake(reply), "ola 250 3 days back", SUNDAY, timeout=5)) is None


def test_a_slow_llm_is_abandoned():
    async def slow(_):
        await asyncio.sleep(1)
        return draft_json(title="Ola")

    assert asyncio.run(llm_draft(RunnableLambda(slow), "ola 250", SUNDAY, timeout=0.05)) is None


def test_checks_reject_invented_values():
    draft = LLMDraft(title="Uber ride home", amount=999, date=date(2027, 1, 1), type="EXPENSE")
    assert checked_fields(draft, "ola 250 3 days back", SUNDAY) == {"type": "EXPENSE"}


def test_checked_values_fill_only_the_gaps():
    parsed = parse_quick_add("ola 250 3 days back", SUNDAY)
    draft = LLMDraft(title="Ola", amount=999, date=date(2026, 10, 15), type="EXPENSE")
    merged, filled = merge(parsed, checked_fields(draft, "ola 250 3 days back", SUNDAY))
    assert (merged.title, merged.amount, merged.date) == ("Ola", 250, date(2026, 10, 15))
    assert filled == ["date", "title"]
    assert merged.found["date"] is True


# ---------- grounded summary ----------

FACTS = MonthFacts(
    month_name="October",
    day=18,
    spent=10421.7,
    spent_last_month_same_day=9200,
    projected=30418.29,
    budget=40000,
    status="on_track",
    top_category=("Food", 4100),
    unusual=("Ola cab", 3141, 11.0),
    subscriptions_monthly=13904.92,
    subscription_count=4,
)


def test_template_summary_states_the_facts():
    text = template_summary(FACTS)
    assert text.startswith(
        "You've spent ₹10,422 so far in October, ₹1,222 more than at this point last month."
    )
    assert "within your ₹40,000 budget" in text and "Food is your biggest category so far (₹4,100)" in text
    assert "[" not in text


def test_the_model_sees_placeholders_not_numbers():
    facts_text = "\n".join(FACTS.lines())
    assert "[spent]" in facts_text and "10,422" not in facts_text and "10422" not in facts_text


def test_a_faithful_llm_summary_is_filled_and_used():
    reply = "October so far: [spent] spent, [difference] more than last month. On course for [projected]."
    text, source = asyncio.run(summarize(fake(reply), FACTS, timeout=5))
    assert source == "llm"
    assert text == "October so far: ₹10,422 spent, ₹1,222 more than last month. On course for ₹30,418."


@pytest.mark.parametrize(
    "reply",
    ["You've spent [spent] so far, 13% more than last month.", "You've saved [savings].", "x" * 700],
)
def test_untrustworthy_llm_summaries_are_replaced_by_the_template(reply):
    assert asyncio.run(summarize(fake(reply), FACTS, timeout=5)) == (template_summary(FACTS), "template")


def test_no_llm_or_a_failing_llm_gives_the_template():
    def broken(_):
        raise ConnectionError("model server down")

    assert asyncio.run(summarize(None, FACTS, timeout=5))[1] == "template"
    assert asyncio.run(summarize(RunnableLambda(broken), FACTS, timeout=5))[1] == "template"


def test_the_check_accepts_every_honest_summary_and_rejects_every_planted_number():
    """An evaluation of the guardrail itself, on simulated users' real months."""
    rng = random.Random(0)
    categories = [{"id": category_id, "name": name.title()} for name, category_id in CATEGORY_IDS.items()]
    for user in simulate_users(30, SUNDAY, seed=11):
        insights = build_insights(user.transactions, categories, user.monthly_budget, SUNDAY)
        facts = month_facts(user.transactions, categories, insights, SUNDAY)
        honest = template_text(facts)
        assert facts.fill(honest) is not None
        sentences = honest.split(". ")
        at = rng.randrange(len(sentences))
        for planted in (f"{rng.randint(1, 99)}% more", f"₹{rng.randint(100, 99999)}", "[savings]"):
            tampered = ". ".join([*sentences[:at], f"{sentences[at]}, {planted}", *sentences[at + 1 :]])
            assert facts.fill(tampered) is None, tampered


# ---------- endpoints with a fake LLM ----------


@pytest.fixture
def llm_client(supabase, model_dir):
    def make(model):
        settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir)
        return TestClient(create_app(settings, transport=httpx.MockTransport(supabase.handler), llm=model))

    return make


def test_parse_endpoint_uses_the_llm_for_what_the_rules_missed(llm_client, supabase, auth_headers):
    supabase.tables.update({"categories": [], "transactions": []})
    today = datetime.now(UTC).date()
    three_days_ago = (today - timedelta(days=3)).isoformat()
    model = fake(draft_json(title="Ola", amount=250, date=three_days_ago))
    request = {"text": "ola 250 3 days back", "today": today.isoformat()}
    with llm_client(model) as client:
        body = client.post("/v1/parse", json=request, headers=auth_headers).json()
    assert (body["title"], body["amount"], body["date"]) == ("Ola", 250, three_days_ago)
    assert body["llm_filled"] == ["date", "title"]


def test_parse_endpoint_skips_the_llm_when_the_rules_are_sure(llm_client, supabase, auth_headers):
    supabase.tables.update({"categories": [], "transactions": []})

    def must_not_run(_):
        raise AssertionError("the LLM should not be called")

    with llm_client(RunnableLambda(must_not_run)) as client:
        body = client.post("/v1/parse", json={"text": "swiggy 450"}, headers=auth_headers).json()
    assert body["llm_filled"] == [] and body["amount"] == 450


def test_parse_endpoint_never_takes_an_invented_amount(llm_client, supabase, auth_headers):
    supabase.tables.update({"categories": [], "transactions": []})
    with llm_client(fake(draft_json(title="Coffee", amount=500))) as client:
        body = client.post("/v1/parse", json={"text": "coffee with the team"}, headers=auth_headers).json()
    assert body["amount"] is None and "amount" not in body["llm_filled"]


def test_summary_endpoint_without_an_llm_returns_the_template(client, supabase, auth_headers):
    supabase.tables.update({"transactions": [], "categories": [], "profiles": []})
    body = client.get("/v1/insights/summary", headers=auth_headers).json()
    assert body["source"] == "template" and body["text"].startswith("You've spent ₹0 so far")


def test_summary_endpoint_caches_llm_text_while_the_facts_are_unchanged(llm_client, supabase, auth_headers):
    supabase.tables.update({"transactions": [], "categories": [], "profiles": []})
    # FakeListChatModel cycles through its replies; .i is the index of the next one
    model = fake("You've spent [spent] so far this month.", "A second call would say this.")
    with llm_client(model) as client:
        first = client.get("/v1/insights/summary", headers=auth_headers).json()
        second = client.get("/v1/insights/summary", headers=auth_headers).json()
    assert first == second == {"text": "You've spent ₹0 so far this month.", "source": "llm"}
    assert model.i == 1  # called once


@pytest.mark.parametrize(
    "content", ["gsk_test", "gsk_test\n", "LLM_API_KEY=gsk_test", 'LLM_API_KEY="gsk_test"\n']
)
def test_the_api_key_can_come_from_a_secret_file(monkeypatch, tmp_path, content):
    from app.config import _secret

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert _secret("LLM_API_KEY", tmp_path) == ""
    (tmp_path / "LLM_API_KEY").write_text(content, encoding="utf-8")
    assert _secret("LLM_API_KEY", tmp_path) == "gsk_test"
    monkeypatch.setenv("LLM_API_KEY", "from-env")  # an environment variable wins
    assert _secret("LLM_API_KEY", tmp_path) == "from-env"


def test_a_misconfigured_llm_does_not_stop_the_service(monkeypatch, model_dir):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(
        supabase_url=SUPABASE_URL,
        supabase_anon_key="anon-key",
        model_dir=model_dir,
        llm_provider="openai",
        llm_api_key="",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.app.state.llm is None
