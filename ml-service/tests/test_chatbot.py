"""The RAG chatbot: index, chain, follow-ups, calculators, API, isolation and failures."""

import json
import zlib
from datetime import date, timedelta
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from app.chatbot import data_answers
from app.chatbot.chain import FALLBACK, build_chain, check_answer, format_docs, sources_from, used_documents
from app.chatbot.guardrails import fixed_reply, profile_field
from app.chatbot.index import (
    build_vector_store,
    load_index,
    load_source_documents,
    make_retriever,
    save_index,
    split_documents,
)
from app.chatbot.ratelimit import RateLimiter
from app.chatbot.router import decide, period_from_name, route_from_call
from app.config import DEFAULT_KNOWLEDGE_DIR, Settings
from app.main import create_app
from tests.conftest import OTHER_TOKEN, OTHER_USER, SUPABASE_URL, TEST_USER, USERS, VALID_TOKEN

TODAY = date.today()
MONTH_START = TODAY.replace(day=1)
LAST_MONTH = (MONTH_START - timedelta(days=1)).replace(day=1)
AUTH = {"Authorization": f"Bearer {VALID_TOKEN}"}
OTHER = {"Authorization": f"Bearer {OTHER_TOKEN}"}
CATEGORIES = [
    {"id": 1, "name": "Food", "user_id": None},
    {"id": 2, "name": "Shopping", "user_id": None},
    {"id": 3, "name": "Rent", "user_id": None},
]


class HashEmbeddings(Embeddings):
    """A stand-in for the real model: a hashed bag of words, unit length, no download."""

    def _vector(self, text: str) -> list[float]:
        vector = np.zeros(512)
        for word in text.lower().split():
            vector[zlib.crc32(word.strip(".,?!").encode()) % 512] += 1
        return (vector / max(np.linalg.norm(vector), 1)).tolist()

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture(scope="module")
def store():
    chunks = split_documents(load_source_documents(DEFAULT_KNOWLEDGE_DIR))
    return build_vector_store(chunks, HashEmbeddings())


# ---------- index ----------


def test_every_format_loads_with_its_metadata(tmp_path):
    (tmp_path / "finance").mkdir()
    (tmp_path / "finance" / "budget.md").write_text(
        "---\ntitle: Budgeting\nsource: Editorial\nsource_url: https://example.org/\n---\n# Budgeting\n\n"
        "## The rule\nNeeds 50%.\n",
        encoding="utf-8",
    )
    (tmp_path / "faq.txt").write_text("Use Export CSV.", encoding="utf-8")
    docs = {d.metadata["document"]: d for d in load_source_documents(tmp_path)}
    assert docs["finance/budget"].metadata["title"] == "Budgeting"
    assert docs["finance/budget"].metadata["url"] == "https://example.org/"
    assert not docs["finance/budget"].page_content.startswith("---")
    assert docs["faq"].metadata["source"] == "Expense Tracker help center"


def test_pdfs_are_loaded(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(200, 200)
    with open(tmp_path / "blank.pdf", "wb") as out:
        writer.write(out)
    assert load_source_documents(tmp_path) == []  # a page without text isn't indexed


def test_chunks_keep_their_title_and_section():
    chunks = split_documents(load_source_documents(DEFAULT_KNOWLEDGE_DIR))
    assert all(len(c.page_content) <= 1000 + 100 for c in chunks)
    rule = next(c for c in chunks if "50/30/20 rule splits" in c.page_content)
    assert rule.page_content.startswith("Budgeting methods\n") and rule.metadata["section"]


def test_long_text_overlaps_between_chunks():
    text = " ".join(f"Sentence {i} explains a budgeting idea." for i in range(200))
    doc = Document(page_content=text, metadata={"document": "x", "title": "T", "source": "s", "url": None})
    chunks = split_documents([doc], chunk_size=300, overlap=100)
    first, second = chunks[0].page_content, chunks[1].page_content
    assert first[-40:].split(". ")[-1] in second


def test_the_index_reloads_without_re_embedding(tmp_path, store):
    class NoEmbedding(HashEmbeddings):
        def embed_documents(self, texts):
            raise AssertionError("reloading must not embed the documents again")

    save_index(store, tmp_path / "faiss")
    loaded = load_index(tmp_path / "faiss", NoEmbedding())
    assert loaded.index.ntotal == store.index.ntotal
    docs = make_retriever(loaded, 4).invoke("what is the 50/30/20 rule")
    assert len(docs) == 4


def test_user_data_is_never_in_the_index(store):
    documents = {doc.metadata["document"] for doc in store.docstore._dict.values()}
    assert "about-the-chatbot" in documents and not any("transaction" in d and "/" in d for d in documents)


# ---------- chain ----------


def test_the_chain_answers_from_the_retrieved_context(store):
    chain = build_chain(make_retriever(store), FakeListChatModel(responses=["Save about 20%."]))
    assert chain.invoke("what is the 50/30/20 rule") == "Save about 20%."


def test_format_docs_and_sources():
    docs = [
        Document(page_content="A", metadata={"document": "a", "section": "s", "title": "T", "source": "x"}),
        Document(page_content="B", metadata={"document": "a", "section": "s", "title": "T", "source": "x"}),
    ]
    assert format_docs(docs) == "A\n\n---\n\nB"
    assert len(sources_from(docs)) == 1  # the same section isn't listed twice
    passage = Document(page_content="Title\n## Heading\nThe text.", metadata={"title": "Title"})
    assert sources_from([passage])[0]["excerpt"] == "The text."  # no title line or heading marks


@pytest.mark.parametrize(
    ("answer", "shown"),
    [
        ("Save about 20% of your income.", "Save about 20% of your income."),
        ("Save about 35% of your income.", FALLBACK),  # a number from nowhere
        ("I don't know", FALLBACK),
        ('"I don\'t know."', FALLBACK),
        ("   ", FALLBACK),
    ],
)
def test_answers_are_checked_against_the_context(answer, shown):
    assert check_answer(answer, "Needs 50%, wants 30%, savings 20%.", "how much?") == shown


# ---------- the model's tool choice ----------


def run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


class ToolModel(FakeListChatModel):
    """Plays back scripted tool calls, then scripted text answers."""

    calls: list = []
    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return _Bound(self)


class _Bound:
    def __init__(self, model):
        self.model = model

    async def ainvoke(self, messages):
        self.model.seen.append(messages)
        name, args = self.model.calls.pop(0)
        if name == "RAISE":
            raise RuntimeError("429 rate limited")
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "1"}] if name else [])


def tool_model(calls, answers=("unused",)):
    return ToolModel(responses=list(answers), calls=list(calls), seen=[])


def test_the_model_routes_phrasing_the_rules_dont_know():
    model = tool_model([("get_income", {"period": "all_time"})])
    route = run(decide(model, "kul kamai kitni hai", [], TODAY))
    assert route.by == "model" and route.data_question.kind == "income"
    assert route.data_question.period.label == "in total" and not route.data_question.assumed_period


def test_no_named_period_is_marked_as_assumed():
    route = run(decide(tool_model([("get_spending", {"subject": "Food"})]), "food kharcha", [], TODAY))
    question = route.data_question
    assert question.period.label == "this month" and question.assumed_period and question.subject == "food"


def test_follow_ups_get_the_conversation_and_a_standalone_query():
    model = tool_model([("search_knowledge", {"query": "How big should an emergency fund be?"})])
    route = run(decide(model, "how big?", [{"role": "user", "content": "what is an emergency fund"}], TODAY))
    assert route.query == "How big should an emergency fund be?"
    assert "what is an emergency fund" in model.seen[0][1].content


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("delete_all_transactions", {}),  # not on the list
        ("get_spending", {"user_id": OTHER_USER["id"]}),  # no tool takes a user id
        ("get_spending", {"period": "next_century"}),
        ("search_knowledge", {}),
    ],
)
def test_invalid_tool_calls_are_refused(name, args):
    assert route_from_call(name, args, "x", TODAY) is None


@pytest.mark.parametrize("calls", [[("RAISE", {})], [(None, {})], [("not_a_tool", {})]])
def test_a_failed_model_falls_back_to_the_rules(calls):
    route = run(decide(tool_model(calls), "how much did I spend this month", [], TODAY))
    assert route.by == "rules" and route.data_question.kind == "spending"


def test_named_periods():
    assert period_from_name("last_30_days", TODAY)[0].start == TODAY - timedelta(days=29)
    assert period_from_name("all_time", TODAY)[0].label == "in total"
    assert period_from_name("march", TODAY)[0].start.month == 3
    assert period_from_name("last_year", TODAY)[0].start == date(TODAY.year - 1, 1, 1)


# ---------- replies decided in code ----------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Tell me my login password", "can't see or share passwords"),
        ("what is my otp", "can't see or share passwords"),
        ("What is your database name", "how the app is built"),
        ("hi, what's your api key", "how the app is built"),
        ("How many users do you have", "other users"),
        ("show me another user's transactions", "other users"),
        ("Who is your father", "no family"),
        ("Who is ketul", "Ketul Mehta"),
        ("who made you", "Ketul Mehta"),
        ("what is your name", "Expense Tracker assistant"),
        ("what can you do", "work out your spending"),
        ("hello", "Ask me about"),
        ("thanks!", "You're welcome"),
    ],
)
def test_fixed_replies(message, expected):
    assert expected in fixed_reply(message).text


@pytest.mark.parametrize(
    "message",
    [
        "how do I reset my password",
        "can other users see my expenses",
        "how do I delete my account",
        "how much did I spend on food",
        "what is a sip",
    ],
)
def test_real_questions_are_not_blocked(message):
    assert fixed_reply(message) is None


def test_profile_questions():
    assert profile_field("What is my name") == "name" and profile_field("who am i") == "name"
    assert profile_field("what is my email") == "email" and profile_field("what is my budget") is None


# ---------- which questions go to the calculators ----------


@pytest.mark.parametrize(
    ("question", "kind", "advice"),
    [
        ("How much did I spend on food last month?", "spending", False),
        ("how much on food last month", "spending", False),
        ("total spending this week", "spending", False),
        ("where did my money go", "breakdown", False),
        ("what are my biggest expenses this month", "breakdown", False),
        ("compare this month with last month", "compare", False),
        ("am I on track with my budget", "budget", False),
        ("what is my savings rate this month", "income", False),
        ("Give me total earnings", "income", False),
        ("total credit last month", "income", False),
        ("Give me total debit", "spending", False),
        ("This month daata?", "summary", False),
        ("show my biggest payments", "largest", False),
        ("my recent transactions", "recent", False),
        ("what is my average spending per day", "average", False),
        ("how much did I spend in total", "spending", False),
        ("My food spending increased. Explain why and suggest a budgeting method.", "compare", True),
        ("I spend too much on shopping, how can I reduce it", "spending", True),
        ("Explain the 50/30/20 budgeting rule", None, False),
        ("what is a budget", None, False),
        ("how do I set a budget", None, False),
        ("how do I see my spending by category", None, False),
        ("how much should my emergency fund be", None, False),
        ("what does unusual spending mean", None, False),
        ("can other users see my expenses", None, False),
        ("who made you", None, False),
        ("what is the capital of australia", None, False),
    ],
)
def test_routing(question, kind, advice):
    result = data_answers.classify(question, TODAY)
    assert (result.kind if result else None) == kind
    if result:
        assert result.wants_advice is advice


def test_periods():
    today = date(2026, 3, 18)  # a Wednesday
    parse = lambda text: data_answers.parse_period(text, today)[0]  # noqa: E731
    assert (parse("this week").start, parse("this week").end) == (date(2026, 3, 16), today)
    assert parse("last week").end == date(2026, 3, 15)
    assert (parse("last month").start, parse("last month").end) == (date(2026, 2, 1), date(2026, 2, 28))
    assert parse("last year").start == date(2025, 1, 1)
    assert parse("in december").start == date(2025, 12, 1)  # the most recent December
    assert parse("may I see it").label == "this month"  # "may" alone is a verb
    assert parse("the last 7 days").start == date(2026, 3, 12)


# ---------- a Supabase stand-in with row level security ----------


def tx(i, title, amount, day, category_id=1, kind="EXPENSE", user=TEST_USER["id"]):
    return {
        "id": i, "title": title, "amount": amount, "date": day.isoformat(), "type": kind,
        "category_id": category_id, "user_id": user,
    }  # fmt: skip


class RLSSupabase:
    OWNED = {
        "transactions": "user_id",
        "chat_threads": "user_id",
        "chat_messages": "user_id",
        "chat_feedback": "user_id",
        "profiles": "id",
    }

    def __init__(self):
        self.tables = {
            "transactions": [
                tx(1, "Swiggy", 33.33, MONTH_START),
                tx(2, "Swiggy", 33.33, MONTH_START),
                tx(3, "Zomato", 33.33, MONTH_START),
                tx(4, "Amazon", 500.10, MONTH_START, category_id=2),
                tx(5, "Salary", 50000, MONTH_START, category_id=None, kind="INCOME"),
                tx(6, "Swiggy", 40.00, LAST_MONTH),
                tx(8, "Hidden Jewellery", 99999, MONTH_START, category_id=2, user=OTHER_USER["id"]),
            ],
            "categories": CATEGORIES,
            "profiles": [
                {"id": TEST_USER["id"], "monthly_budget": 2000},
                {"id": OTHER_USER["id"], "monthly_budget": 1},
            ],
            "chat_threads": [],
            "chat_messages": [],
            "chat_feedback": [],
        }
        self.missing: set[str] = set()
        self.next_id = 100

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, user = request.url.path, USERS.get(request.headers.get("authorization", ""))
        if path == "/auth/v1/user":
            return httpx.Response(200, json=user) if user else httpx.Response(401, json={})
        if user is None:
            return httpx.Response(401, json={})
        table, uid = path.removeprefix("/rest/v1/"), user["id"]
        if table in self.missing:
            return httpx.Response(404, json={"code": "PGRST205"})
        column = self.OWNED.get(table)
        visible = [r for r in self.tables.get(table, []) if column is None or r.get(column) == uid]
        query = parse_qs(request.url.query.decode())
        for key, values in query.items():
            if values[0].startswith("eq."):
                visible = [r for r in visible if str(r.get(key)) == values[0][3:]]
        if request.method == "GET":
            order = query.get("order", [""])[0]
            if order.startswith("date."):
                visible = sorted(visible, key=lambda r: r["date"], reverse=order.startswith("date.desc"))
            if "limit" in query:
                visible = (visible[::-1] if ".desc" in query.get("order", [""])[0] else visible)[
                    : int(query["limit"][0])
                ]
            return httpx.Response(200, json=visible, headers={"Content-Range": f"0-0/{len(visible)}"})
        if request.method == "POST":
            body = json.loads(request.content)
            rows = body if isinstance(body, list) else [body]
            for row in rows:
                row.setdefault("user_id", uid)
                if row["user_id"] != uid:
                    return httpx.Response(403, json={"message": "row-level security"})
                if table == "chat_threads":
                    row.setdefault("id", str(uuid4()))
                    row.setdefault("updated_at", "2026-11-05T00:00:00")
                self.next_id += 1
                if table == "chat_messages":
                    row.setdefault("id", self.next_id)
                if table == "chat_feedback":
                    owned = [m for m in self.tables["chat_messages"] if m["id"] == row["message_id"]]
                    if not owned or owned[0]["user_id"] != uid:
                        return httpx.Response(403, json={"message": "row-level security"})
                    self.tables[table] = [
                        f
                        for f in self.tables[table]
                        if not (f["message_id"] == row["message_id"] and f["user_id"] == uid)
                    ]
                row.setdefault("created_at", f"2026-11-05T00:00:{self.next_id % 60:02d}")
                self.tables[table].append(row)
            return httpx.Response(201, json=rows)
        if request.method == "PATCH":
            for row in visible:
                row.update(json.loads(request.content))
            return httpx.Response(200, json=visible)
        if request.method == "DELETE":
            ids = {id(r) for r in visible}
            self.tables[table] = [r for r in self.tables[table] if id(r) not in ids]
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture
def rls():
    return RLSSupabase()


def make_client(rls, model_dir, store=None, answers=None, model=None, **settings):
    config = Settings(
        supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir, **settings
    )
    app = create_app(
        config,
        transport=httpx.MockTransport(rls.handler),
        chat_llm=model or (FakeListChatModel(responses=answers) if answers else None),
        chat_retriever=make_retriever(store) if store else None,
    )
    client = TestClient(app)
    client.__enter__()
    return client


def ask(client, message, headers=AUTH, **extra):
    body = {"message": message, "today": TODAY.isoformat(), **extra}
    return client.post("/chat", json=body, headers=headers)


# ---------- the API ----------


def test_every_route_needs_a_token(rls, model_dir):
    client = make_client(rls, model_dir)
    assert client.post("/chat", json={"message": "hi"}).status_code == 401
    assert client.post("/chat/stream", json={"message": "hi"}).status_code == 401
    assert client.get("/chat/threads").status_code == 401
    assert client.delete(f"/chat/threads/{uuid4()}").status_code == 401


def test_the_groq_key_never_appears_in_settings_output():
    assert "gsk_secret" not in repr(Settings(groq_api_key="gsk_secret"))


def test_figures_are_exact_and_saved_to_history(rls, model_dir):
    client = make_client(rls, model_dir)
    body = ask(client, "How much did I spend on food this month?").json()
    assert body["answered_by"] == "your_data" and "₹99.99" in body["reply"] and "3 payments" in body["reply"]
    assert body["history_saved"] and [m["role"] for m in rls.tables["chat_messages"]] == ["user", "assistant"]


def test_calculators_cover_the_other_questions(rls, model_dir):
    client = make_client(rls, model_dir)
    assert "₹600.09" in ask(client, "where did my money go this month").json()["reply"]
    budget = ask(client, "how much of my budget is left").json()["reply"]
    assert "₹600.09" in budget and "₹1,399.91" in budget
    income = ask(client, "how much did I earn this month").json()["reply"]
    assert "₹50,000" in income and "₹49,399.91" in income
    assert "₹40" in ask(client, "how much did I spend on food last month").json()["reply"]


def test_a_merchant_with_no_payments_says_so_instead_of_the_whole_total(rls, model_dir):
    client = make_client(rls, model_dir)
    reply = ask(client, "how much did I spend on gold this month").json()["reply"]
    assert reply == "You haven't spent anything on gold this month."


def test_users_never_see_each_others_data_or_conversations(rls, model_dir):
    client = make_client(rls, model_dir)
    mine = ask(client, "where did my money go this month").json()
    assert "Jewellery" not in json.dumps(mine) and "99,999" not in json.dumps(mine)
    thread = mine["thread_id"]
    assert ask(client, "and last month?", headers=OTHER, thread_id=thread).status_code == 404
    assert client.get(f"/chat/threads/{thread}", headers=OTHER).status_code == 404
    assert client.delete(f"/chat/threads/{thread}", headers=OTHER).status_code == 404
    assert client.get("/chat/threads", headers=OTHER).json() == []
    assert "₹99,999" in ask(client, "how much did I spend this month", headers=OTHER).json()["reply"]


def test_document_questions_come_with_sources(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["Keep needs to about 50% and save 20%."])
    body = ask(client, "Explain the 50/30/20 budgeting rule").json()
    assert body["answered_by"] == "documents" and body["reply"].startswith("Keep needs")
    assert body["sources"] and body["sources"][0]["title"]


def test_i_dont_know_shows_no_sources(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["I don't know", "OFF_TOPIC"])
    body = ask(client, "what is the capital of australia").json()
    assert (
        "don't have an answer" in body["reply"]
        or "couldn't find" in body["reply"]
        or "not sure" in body["reply"]
    )
    assert body["sources"] == [] and body["suggestions"]


def test_invented_numbers_are_not_shown(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["Most people save 37.123% of their income.", "OFF_TOPIC"])
    reply = ask(client, "how much do people save").json()["reply"]
    assert "37.123" not in reply


def test_mixed_questions_give_figures_then_advice(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["Try setting a limit for each category."])
    body = ask(client, "My food spending increased. Explain why and suggest a method.").json()
    assert body["answered_by"] == "both"
    assert body["reply"].startswith("You spent ₹99.99 on food") and "Try setting a limit" in body["reply"]


def test_follow_ups_use_the_conversation(rls, model_dir, store):
    model = tool_model(
        [
            ("search_knowledge", {"query": "what is an emergency fund"}),
            ("search_knowledge", {"query": "How big should an emergency fund be?"}),
        ],
        ["An emergency fund is money set aside.", "Three months."],
    )
    client = make_client(rls, model_dir, store, model=model)
    first = ask(client, "what is an emergency fund").json()
    second = ask(client, "how big?", thread_id=first["thread_id"]).json()
    assert second["reply"] == "Three months." and second["thread_id"] == first["thread_id"]


def test_greetings_need_no_ai(rls, model_dir):
    client = make_client(rls, model_dir)
    assert ask(client, "hello").json()["answered_by"] == "fixed"
    assert ask(client, "thanks!").json()["reply"] == "You're welcome!"


def test_without_groq_figures_still_work_and_documents_say_so(rls, model_dir):
    client = make_client(rls, model_dir)
    assert ask(client, "how much did I spend this month").status_code == 200
    assert ask(client, "what is a sip").status_code == 503


def test_ai_failures_are_reported_plainly(rls, model_dir, store):
    class Broken(FakeListChatModel):
        def _call(self, *args, **kwargs):
            raise RuntimeError("429 rate limited")

        async def _astream(self, *args, **kwargs):
            raise RuntimeError("429 rate limited")
            yield

    config = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir)
    app = create_app(
        config,
        transport=httpx.MockTransport(rls.handler),
        chat_llm=Broken(responses=["x"]),
        chat_retriever=make_retriever(store),
    )
    with TestClient(app) as client:
        body = ask(client, "what is a sip").json()
        assert "can't reach the AI service" in body["reply"] and "429" not in body["reply"]


def test_streaming_sends_meta_deltas_and_a_final_reply(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["Save about 20% of income."])
    response = client.post(
        "/chat/stream",
        headers=AUTH,
        json={"message": "what is the 50/30/20 rule", "today": TODAY.isoformat()},
    )
    events = [block.split("\n", 1) for block in response.text.strip().split("\n\n")]
    names = [event[0].removeprefix("event: ") for event in events]
    assert names[0] == "meta" and names[-1] == "final" and "delta" in names
    streamed = "".join(json.loads(e[1][6:])["text"] for e in events if e[0] == "event: delta")
    assert streamed == json.loads(events[-1][1][6:])["reply"] == "Save about 20% of income."


def test_streaming_reports_failures_as_an_event(rls, model_dir):
    client = make_client(rls, model_dir)
    response = client.post("/chat/stream", headers=AUTH, json={"message": "what is a sip"})
    assert "event: error" in response.text and "own spending" in response.text


def test_without_the_history_tables_the_chatbot_still_answers(rls, model_dir):
    rls.missing |= {"chat_threads", "chat_messages"}
    client = make_client(rls, model_dir)
    body = ask(client, "how much did I spend this month").json()
    assert body["history_saved"] is False and body["thread_id"] is None and "₹600.09" in body["reply"]
    assert client.get("/chat/threads", headers=AUTH).status_code == 503


def test_threads_can_be_listed_read_and_deleted(rls, model_dir):
    client = make_client(rls, model_dir)
    thread = ask(client, "how much did I spend this month").json()["thread_id"]
    assert [t["id"] for t in client.get("/chat/threads", headers=AUTH).json()] == [thread]
    messages = client.get(f"/chat/threads/{thread}", headers=AUTH).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert client.delete(f"/chat/threads/{thread}", headers=AUTH).status_code == 204
    assert client.get("/chat/threads", headers=AUTH).json() == []


def test_browsers_may_delete_conversations(rls, model_dir):
    client = make_client(rls, model_dir)
    response = client.options(
        f"/chat/threads/{uuid4()}",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"},
    )
    assert response.status_code == 200 and "DELETE" in response.headers["access-control-allow-methods"]


def test_rate_limits(rls, model_dir):
    client = make_client(rls, model_dir, chat_per_minute=2)
    assert ask(client, "hi").status_code == 200 and ask(client, "hi").status_code == 200
    blocked = ask(client, "hi")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    limiter = RateLimiter(per_minute=2, per_day=3)
    assert limiter.check("u", 0) is None and limiter.check("u", 1) is None
    assert limiter.check("u", 2) is not None and limiter.check("other", 2) is None


# ---------- the new answers ----------


def test_earnings_and_debit_get_real_answers_with_cards_and_choices(rls, model_dir):
    client = make_client(rls, model_dir)
    body = ask(client, "Give me total earnings").json()
    assert "₹50,000" in body["reply"] and "this month" in body["reply"]
    assert any(b["type"] == "cards" for b in body["blocks"])
    assert "How much did I earn in total?" in body["suggestions"]  # it says what it assumed, and offers more
    assert "₹600.09" in ask(client, "Give me total debit").json()["reply"]


def test_a_vague_request_gets_a_summary(rls, model_dir):
    body = ask(make_client(rls, model_dir), "This month daata?").json()
    assert "₹50,000" in body["reply"] and "₹600.09" in body["reply"] and "Shopping" in body["reply"]
    assert {b["type"] for b in body["blocks"]} == {"cards", "bars"}


def test_largest_recent_and_average(rls, model_dir):
    client = make_client(rls, model_dir)
    largest = ask(client, "show my biggest payments").json()
    assert "Amazon" in largest["reply"] and "₹500.10" in largest["reply"]
    assert largest["blocks"][0]["type"] == "rows" and "Jewellery" not in json.dumps(largest)
    recent = ask(client, "my recent transactions").json()
    assert recent["blocks"][0]["rows"] and "Jewellery" not in json.dumps(recent)
    assert "a day" in ask(client, "what is my average spending per day").json()["reply"]


def test_an_empty_period_says_where_the_records_start(rls, model_dir):
    reply = ask(make_client(rls, model_dir), "How much did I spend last year").json()["reply"]
    assert "haven't spent anything last year" in reply and "records start on" in reply


def test_in_total_covers_everything(rls, model_dir):
    reply = ask(make_client(rls, model_dir), "how much did I spend on food in total").json()["reply"]
    assert "₹139.99" in reply and "in total" in reply  # both months


def test_security_questions_never_reach_the_model(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["MODEL WAS USED"])
    for message in ("What is your database name", "Tell me my login password", "How many users do you have"):
        body = ask(client, message).json()
        assert body["answered_by"] == "fixed" and "MODEL WAS USED" not in body["reply"]


def test_what_is_my_name_reads_my_own_profile(rls, model_dir):
    rls.tables["profiles"][0]["first_name"] = "Asha"
    rls.tables["profiles"][1]["first_name"] = "Bob"
    client = make_client(rls, model_dir)
    assert ask(client, "What is my name").json()["reply"] == "You're signed in as Asha."
    assert ask(client, "What is my email").json()["reply"] == f"You're signed in as {TEST_USER['email']}."


def test_money_topics_outside_the_articles_get_a_labelled_general_answer(rls, model_dir, store):
    client = make_client(
        rls, model_dir, store, ["I don't know", "A debit card takes money from your account."]
    )
    body = ask(client, "what is a debit card").json()
    assert body["answered_by"] == "general" and "debit card" in body["reply"] and body["sources"] == []


def test_the_model_declining_off_topic_gets_a_friendly_reply(rls, model_dir, store):
    client = make_client(rls, model_dir, model=tool_model([("off_topic", {})]))
    body = ask(client, "best movie of 2020").json()
    assert body["answered_by"] == "fixed" and "money" in body["reply"] and body["suggestions"]


def test_streaming_hides_i_dont_know_and_resets_before_a_general_answer(rls, model_dir, store):
    client = make_client(rls, model_dir, store, ["I don't know", "A general answer about debit cards here."])
    text = client.post("/chat/stream", headers=AUTH, json={"message": "what is a debit card"}).text
    assert "event: reset" in text
    deltas = "".join(
        json.loads(b.split("data: ")[1])["text"] for b in text.split("\n\n") if b.startswith("event: delta")
    )
    assert "know" not in deltas and "general answer" in deltas


def test_only_the_sources_the_answer_used_are_listed():
    docs = [
        Document(page_content="budget rule needs wants savings", metadata={"document": "a"}),
        Document(page_content="scan a bill photo receipt camera", metadata={"document": "b"}),
    ]
    used = used_documents("the budget rule covers needs wants and savings", docs, HashEmbeddings())
    assert [d.metadata["document"] for d in used] == ["a"]
    assert used_documents("x", docs, None) == docs[:1]  # no embeddings: the closest match only


def test_feedback_on_my_own_answer_only(rls, model_dir):
    client = make_client(rls, model_dir)
    message_id = ask(client, "how much did I spend this month").json()["message_id"]
    assert (
        client.post(
            "/chat/feedback", headers=AUTH, json={"message_id": message_id, "rating": "up"}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/chat/feedback", headers=AUTH, json={"message_id": message_id, "rating": "down"}
        ).status_code
        == 204
    )
    assert [f["rating"] for f in rls.tables["chat_feedback"]] == ["down"]  # replaced, not duplicated
    denied = client.post("/chat/feedback", headers=OTHER, json={"message_id": message_id, "rating": "up"})
    assert denied.status_code == 503 and len(rls.tables["chat_feedback"]) == 1
    assert client.post("/chat/feedback", json={"message_id": 1, "rating": "up"}).status_code == 401
