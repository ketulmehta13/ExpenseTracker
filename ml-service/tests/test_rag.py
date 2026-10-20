import asyncio
import zlib

import numpy as np
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.config import Settings
from app.llm.verify import numbers_in
from app.rag.answer import NOT_FOUND, answer_question, checked_llm_answer
from app.rag.bm25 import BM25, tokenize
from app.rag.embeddings import load_embedder, normalize
from app.rag.knowledge import Chunk, fixed_size_chunks, load_chunks
from app.rag.retriever import HelpIndex, ranked_articles
from training.evaluate_rag import decline_accuracy, retrieval_metrics


class WordEmbedder:
    """A deterministic stand-in for the real model: a hashed bag of words, unit length."""

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(512)
        for token in tokenize(text):
            vector[zlib.crc32(token.encode()) % 512] += 1
        return normalize(vector)

    def embed_passages(self, texts):
        return np.array([self._vector(text) for text in texts])

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture(scope="module")
def chunks():
    return load_chunks()


@pytest.fixture(scope="module")
def index(chunks):
    # Hash collisions give unrelated text a similarity up to ~0.25 with this fake; real matches score 0.6+
    return HelpIndex(chunks, WordEmbedder(), decline_below=0.3)


# ---------- chunking ----------

def test_every_article_is_split_into_cited_sections(chunks):
    exporting = [chunk for chunk in chunks if chunk.article == "exporting"]
    assert [chunk.section for chunk in exporting][:2] == ["CSV and PDF export", "Opening the CSV in Excel"]
    assert exporting[1].id == "exporting#opening-the-csv-in-excel"
    assert exporting[1].text.startswith("Exporting your data > Opening the CSV in Excel\n")
    assert all(chunk.body and "##" not in chunk.body for chunk in chunks)


def test_fixed_windows_ignore_sections(chunks):
    windows = fixed_size_chunks(chunks, size=200)
    assert all(window.section == "" for window in windows)
    assert {window.article for window in windows} == {chunk.article for chunk in chunks}


# ---------- BM25 ----------

def test_bm25_prefers_rare_matching_words():
    bm25 = BM25(["export your data to pdf", "your data is your data", "set a monthly budget"])
    scores = bm25.scores("pdf export")
    assert scores[0] > 0 and scores[1] == 0 and scores[2] == 0


def test_tokenizer_drops_stopwords_and_normalizes_word_forms():
    assert tokenize("How do I delete my categories?") == ["delete", "category"]
    expected = ["cancel", "cancel", "cancel", "bill", "stop"]
    assert tokenize("cancelling cancelled cancel billing stopped") == expected


# ---------- hybrid search ----------

def test_search_modes_find_the_right_article(index):
    for mode in ("bm25", "dense", "hybrid"):
        assert ranked_articles(index.search("export transactions as pdf", mode=mode))[0] == "exporting"


def test_reciprocal_rank_fusion_rewards_agreement():
    docs = [Chunk(f"d{i}", f"a{i}", "", "", text) for i, text in enumerate(
        ["pdf export guide", "export pdf csv data", "budget"]
    )]
    hybrid = HelpIndex(docs, WordEmbedder()).search("export pdf", k=3)
    assert hybrid[0].score >= hybrid[1].score >= hybrid[2].score
    assert hybrid[-1].chunk.article == "a2"


def test_without_embeddings_search_falls_back_to_keywords(chunks):
    keyword_only = HelpIndex(chunks, embedder=None)
    hits = keyword_only.search("cancel pro subscription", k=3)
    assert all(hit.similarity is None for hit in hits)
    assert "plans-and-billing" in ranked_articles(hits)
    # Without embeddings, questions whose words the help center never uses are declined
    assert keyword_only.in_scope("how do i export a pdf")
    assert keyword_only.in_scope("export kaise kare")
    assert not keyword_only.in_scope("what is the capital of australia")
    assert not keyword_only.in_scope("explain inflation")


@pytest.mark.parametrize("value", ["", "none", "None", " off "])
def test_embeddings_can_be_switched_off(monkeypatch, value):
    # Small servers can't hold the 370 MB model (Render's free plan has 512 MB in all)
    monkeypatch.setenv("EMBEDDING_MODEL", value)
    settings = Settings.from_env()
    assert settings.embedding_model == ""
    assert load_embedder(settings.embedding_model, settings.embedding_cache_dir) is None


def test_an_embedding_model_name_is_kept(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", " BAAI/bge-small-en-v1.5 ")
    assert Settings.from_env().embedding_model == "BAAI/bge-small-en-v1.5"


# ---------- answers ----------

def ask(index, question, model=None):
    return asyncio.run(answer_question(index, question, model, timeout=5))


def test_extractive_answer_without_an_llm(index):
    answer = ask(index, "how do I export to pdf")
    assert answer.source == "extractive"
    assert answer.citations[0].article == "exporting"
    assert answer.text.startswith("On the Transactions page")


def test_off_topic_questions_are_declined(index):
    answer = ask(index, "astronaut volcano pyramid")
    assert (answer.text, answer.source, answer.citations) == (NOT_FOUND, "not_found", [])


def test_a_cited_llm_answer_is_used(index):
    reply = "Use Export CSV or Export PDF on the Transactions page; exports are a Pro feature [1]."
    answer = ask(index, "how do I export to pdf", FakeListChatModel(responses=[reply]))
    assert (answer.text, answer.source) == (reply, "llm")
    assert answer.citations[0].article == "exporting"


@pytest.mark.parametrize(
    "reply",
    [
        "Exports are a Pro feature.",  # no citation
        "Exports are a Pro feature [7].",  # cites a source it wasn't given
        "Exports cost ₹49 extra [1].",  # a number its source doesn't contain
        "I don't know.",
    ],
)
def test_unchecked_llm_answers_fall_back_to_the_extractive_answer(index, reply):
    answer = ask(index, "how do I export to pdf", FakeListChatModel(responses=[reply]))
    assert answer.source == "extractive"


def test_a_failing_llm_falls_back(index):
    def broken(_):
        raise TimeoutError

    assert ask(index, "how do I export to pdf", RunnableLambda(broken)).source == "extractive"


def test_numbers_must_come_from_the_cited_sources(index):
    hits = index.search("what is the 50/30/20 rule for saving", k=3)
    rule = next(n for n, hit in enumerate(hits, 1) if hit.chunk.section == "A simple rule of thumb: 50/30/20")
    assert numbers_in("Pro is ₹2,499 a year") == {2499.0}
    assert checked_llm_answer(f"Spend about 50% on needs and save about 20% [{rule}].", hits) is not None
    assert checked_llm_answer(f"Save about 25% of your income [{rule}].", hits) is None


# ---------- evaluation helpers ----------

def test_retrieval_metrics_and_decline_accuracy(index):
    rows = [
        {"question": "export transactions as pdf", "articles": ["exporting"]},
        {"question": "set monthly budget", "articles": ["budget-and-forecast"]},
        {"question": "astronaut volcano pyramid", "articles": []},
    ]
    metrics, misses = retrieval_metrics(index, rows, "hybrid")
    assert metrics["questions"] == 2 and metrics["hit@3"] == 1.0
    assert decline_accuracy(index, rows, threshold=0.3) == 1.0


# ---------- POST /v1/help ----------

def test_help_endpoint_requires_a_token(client):
    assert client.post("/v1/help", json={"question": "how do I export"}).status_code == 401


def test_help_endpoint_answers_with_citations(client, auth_headers, index):
    client.app.state.help_index = index  # instead of loading the real embedding model
    body = client.post("/v1/help", json={"question": "how do I export to pdf"}, headers=auth_headers).json()
    assert body["source"] == "extractive"
    assert body["citations"][0] == {"article": "exporting", "title": "Exporting your data",
                                    "section": "CSV and PDF export"}
