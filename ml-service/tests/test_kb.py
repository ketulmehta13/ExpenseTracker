"""The copilot's knowledge base: loading, chunking, incremental ingestion, stores and retrieval."""

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.config import DEFAULT_KNOWLEDGE_DIR
from app.rag.chunking import split_document
from app.rag.documents import DocumentError, load_document, load_documents
from app.rag.ingest import fingerprint, ingest
from app.rag.kb_retriever import KnowledgeRetriever
from app.rag.vectorstore import PENDING_SHA, InMemoryVectorStore, SupabaseVectorStore, VectorStoreError
from tests.test_rag import WordEmbedder

ARTICLE = """---
title: Budgeting methods
topic: budgeting
source: Test editorial
source_url: https://www.ncfe.org.in/
version: 2
---
# Budgeting methods

## The 50/30/20 rule
Needs 50%, wants 30%, savings 20% of take-home income.

## Zero-based budgeting
Give every rupee of income a job until nothing is left unplanned.
"""


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------- documents ----------


def test_markdown_front_matter_becomes_metadata(tmp_path):
    doc = load_document(write(tmp_path, "finance/Budgeting Methods.md", ARTICLE), tmp_path)
    assert (doc.id, doc.title, doc.topic, doc.version) == (
        "finance/budgeting-methods",
        "Budgeting methods",
        "budgeting",
        2,
    )
    assert doc.source_url == "https://www.ncfe.org.in/" and not doc.text.startswith("---")


def test_text_files_and_root_files_get_defaults(tmp_path):
    doc = load_document(write(tmp_path, "faq.txt", "How do I export? Use Export CSV."), tmp_path)
    assert (doc.id, doc.topic, doc.format, doc.title) == ("faq", "app-help", "txt", "faq")


def test_pdf_text_is_read(tmp_path):
    pdfium = pytest.importorskip("pypdfium2")
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(200, 200)
    pdf.save(str(tmp_path / "blank.pdf"))
    # A page without text: refused rather than ingested empty
    with pytest.raises(DocumentError, match="no text"):
        load_document(tmp_path / "blank.pdf", tmp_path)


@pytest.mark.parametrize(
    ("front_matter", "error"),
    [
        ("topic: Budgeting Tips", "topic"),
        ("topic: budgeting\nsource_url: http://insecure.example", "https"),
        ("topic: budgeting\nversion: 0", "version"),
        ("topic: budgeting\nreferences: [ftp://x]", "references"),
    ],
)
def test_bad_metadata_is_rejected(tmp_path, front_matter, error):
    with pytest.raises(DocumentError, match=error):
        load_document(
            write(tmp_path, "finance/x.md", f"---\n{front_matter}\n---\n# X\n\n## A\nText."), tmp_path
        )


def test_a_finance_file_must_set_its_topic(tmp_path):
    with pytest.raises(DocumentError, match="topic"):
        load_document(write(tmp_path, "finance/x.md", "# X\n\n## A\nText."), tmp_path)


def test_duplicate_ids_are_rejected(tmp_path):
    write(tmp_path, "faq.md", "# FAQ\n\n## A\nText.")
    write(tmp_path, "faq.txt", "Text.")
    with pytest.raises(DocumentError, match="duplicate"):
        load_documents(tmp_path)


def test_the_shipped_knowledge_base_loads():
    docs = load_documents(DEFAULT_KNOWLEDGE_DIR)
    topics = {doc.topic for doc in docs}
    assert {"app-help", "budgeting", "saving", "cash-flow", "debt", "investing"} <= topics
    assert all(split_document(doc) for doc in docs)


# ---------- chunking ----------


def test_markdown_is_chunked_by_section_with_its_context(tmp_path):
    chunks = split_document(load_document(write(tmp_path, "finance/b.md", ARTICLE), tmp_path))
    assert [c.section for c in chunks] == ["The 50/30/20 rule", "Zero-based budgeting"]
    assert chunks[0].search_text.startswith("Budgeting methods > The 50/30/20 rule\n")
    assert chunks[0].metadata["topic"] == "budgeting"


def test_long_sections_are_split_with_overlap(tmp_path):
    sentences = " ".join(f"Sentence number {i} explains a budgeting idea in plain words." for i in range(40))
    doc = load_document(
        write(tmp_path, "finance/long.md", f"---\ntopic: budgeting\n---\n# Long\n\n## Part\n{sentences}"),
        tmp_path,
    )
    chunks = split_document(doc, chunk_size=300, overlap=60)
    assert len(chunks) > 5 and all(len(c.content) <= 300 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # Neighbours share text, so a sentence cut in two is whole in one of them
    assert any(chunks[0].content[-30:].split()[-1] in chunks[1].content for _ in [0])


def test_chunk_settings_are_validated(tmp_path):
    doc = load_document(write(tmp_path, "finance/b.md", ARTICLE), tmp_path)
    with pytest.raises(ValueError):
        split_document(doc, chunk_size=50)
    with pytest.raises(ValueError):
        split_document(doc, chunk_size=400, overlap=300)


# ---------- ingestion ----------


class CountingEmbedder(WordEmbedder):
    def __init__(self):
        self.passages = 0

    def embed_passages(self, texts):
        self.passages += len(texts)
        return super().embed_passages(texts)


def test_ingestion_is_incremental_and_prunes_deleted_documents(tmp_path):
    write(tmp_path, "finance/b.md", ARTICLE)
    write(tmp_path, "faq.md", "# FAQ\n\n## Export\nUse Export CSV on the Transactions page.")
    store, embedder = InMemoryVectorStore(), CountingEmbedder()

    first = ingest(load_documents(tmp_path), store, embedder)
    assert (sorted(first.added), first.chunks_written) == (["faq", "finance/b"], 3)

    # Re-running changes nothing: no embedding work, no writes, no duplicate chunks
    writes, embedded = store.writes, embedder.passages
    again = ingest(load_documents(tmp_path), store, embedder)
    assert (again.unchanged, store.writes, embedder.passages) == (["faq", "finance/b"], writes, embedded)
    assert len(store.chunks()) == 3

    # An edit re-ingests only that document, replacing its chunks
    write(tmp_path, "faq.md", "# FAQ\n\n## Export\nUse Export PDF.\n\n## Import\nNot supported yet.")
    edited = ingest(load_documents(tmp_path), store, embedder)
    assert (edited.updated, edited.unchanged) == (["faq"], ["finance/b"])
    assert len(store.chunks()) == 4

    # A deleted file is removed from the store
    (tmp_path / "faq.md").unlink()
    pruned = ingest(load_documents(tmp_path), store, embedder)
    assert pruned.deleted == ["faq"] and {c.document_id for c, _ in store.chunks()} == {"finance/b"}


def test_changing_the_chunking_reingests(tmp_path):
    doc = load_document(write(tmp_path, "finance/b.md", ARTICLE), tmp_path)
    assert fingerprint(doc, 900, 150) != fingerprint(doc, 400, 80)


def test_dry_run_writes_nothing(tmp_path):
    write(tmp_path, "finance/b.md", ARTICLE)
    store = InMemoryVectorStore()
    result = ingest(load_documents(tmp_path), store, CountingEmbedder(), dry_run=True)
    assert result.added == ["finance/b"] and store.documents() == {}


# ---------- the Supabase (pgvector) store ----------


class FakePostgrest:
    """Records requests to PostgREST and answers like it."""

    def __init__(self, fail_status: int | None = None):
        self.requests: list[httpx.Request] = []
        self.fail_status = fail_status

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_status:
            return httpx.Response(self.fail_status, json={"message": "boom"})
        path = request.url.path
        if path.endswith("/rpc/match_kb_chunks"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "document_id": "finance/b",
                        "chunk_index": 0,
                        "section": "The 50/30/20 rule",
                        "content": "Needs 50%...",
                        "metadata": {},
                        "title": "Budgeting methods",
                        "source": "Test",
                        "source_url": "https://www.ncfe.org.in/",
                        "topic": "budgeting",
                        "version": 2,
                        "similarity": 0.91,
                    }
                ],
            )
        if path.endswith("/kb_documents") and request.method == "GET":
            return httpx.Response(200, json=[{"id": "finance/b", "content_sha256": "a" * 64, "version": 2}])
        return httpx.Response(201 if request.method == "POST" else 204)


def supabase_store(fake: FakePostgrest, key: str = "service-key") -> SupabaseVectorStore:
    return SupabaseVectorStore(
        "https://p.supabase.co", key, httpx.Client(transport=httpx.MockTransport(fake.handler))
    )


def test_supabase_replace_writes_the_real_sha_last(tmp_path):
    fake = FakePostgrest()
    doc = load_document(write(tmp_path, "finance/b.md", ARTICLE), tmp_path)
    chunks = split_document(doc)
    supabase_store(fake).replace_document(
        doc, chunks, WordEmbedder().embed_passages([c.search_text for c in chunks]), "f" * 64
    )
    steps = [(r.method, r.url.path.rsplit("/", 1)[-1]) for r in fake.requests]
    assert steps == [
        ("POST", "kb_documents"),
        ("DELETE", "kb_chunks"),
        ("POST", "kb_chunks"),
        ("PATCH", "kb_documents"),
    ]
    assert json.loads(fake.requests[0].content)["content_sha256"] == PENDING_SHA
    inserted = json.loads(fake.requests[2].content)
    assert (
        len(inserted) == 2
        and inserted[0]["embedding"].startswith("[")
        and inserted[0]["document_id"] == "finance/b"
    )
    assert json.loads(fake.requests[3].content)["content_sha256"] == "f" * 64
    assert all(r.headers["apikey"] == "service-key" for r in fake.requests)


def test_supabase_search_calls_the_rpc_with_limits():
    fake = FakePostgrest()
    hits = supabase_store(fake, "anon").search(np.ones(384) / np.sqrt(384), k=500, topics=["budgeting"])
    body = json.loads(fake.requests[0].content)
    assert (body["match_count"], body["topics"]) == (50, ["budgeting"])
    assert hits[0].similarity == 0.91 and hits[0].chunk.metadata["title"] == "Budgeting methods"


def test_supabase_errors_are_reported_without_the_key():
    with pytest.raises(VectorStoreError) as err:
        supabase_store(FakePostgrest(fail_status=401), "secret-key").documents()
    assert "secret-key" not in str(err.value)


# ---------- retrieval ----------


@pytest.fixture(scope="module")
def knowledge():
    store = InMemoryVectorStore()
    ingest(load_documents(DEFAULT_KNOWLEDGE_DIR), store, WordEmbedder())
    return store


def test_hybrid_retrieval_finds_the_right_document_with_its_source(knowledge):
    result = KnowledgeRetriever(knowledge, WordEmbedder(), min_similarity=0.3).retrieve(
        "explain the 50/30/20 rule"
    )
    top = result.evidence[0]
    assert result.sufficient and result.mode == "hybrid"
    assert top.document_id == "finance/budgeting-methods" and top.section == "The 50/30/20 rule"
    assert top.source_url == "https://www.ncfe.org.in/" and top.ref == "finance/budgeting-methods#1"


def test_topic_filters_restrict_the_evidence(knowledge):
    result = KnowledgeRetriever(knowledge, WordEmbedder(), min_similarity=0.3).retrieve(
        "how do I export my budget", topics=["app-help"]
    )
    assert result.evidence and all(e.topic == "app-help" for e in result.evidence)


def test_off_topic_questions_are_insufficient(knowledge):
    for retriever in (
        KnowledgeRetriever(knowledge, WordEmbedder(), min_similarity=0.5),
        KnowledgeRetriever(knowledge, None),
    ):
        assert not retriever.retrieve("what is the capital of australia").sufficient


def test_without_embeddings_retrieval_uses_keywords(knowledge):
    result = KnowledgeRetriever(knowledge, None).retrieve("what is zero based budgeting")
    assert result.mode == "keyword" and result.evidence[0].document_id == "finance/budgeting-methods"


class BrokenStore(InMemoryVectorStore):
    def __init__(self, inner, search_fails=True, read_fails=False):
        super().__init__()
        self.inner, self.search_fails, self.read_fails = inner, search_fails, read_fails

    def chunks(self):
        if self.read_fails:
            raise VectorStoreError("down")
        return self.inner.chunks()

    def search(self, query, k, topics=None):
        raise VectorStoreError("rpc failed")


def test_vector_search_failures_fall_back_to_keywords(knowledge):
    result = KnowledgeRetriever(BrokenStore(knowledge), WordEmbedder()).retrieve(
        "what is zero based budgeting"
    )
    assert result.mode == "keyword" and result.evidence


def test_an_unreachable_store_gives_no_evidence_instead_of_an_error(knowledge):
    result = KnowledgeRetriever(BrokenStore(knowledge, read_fails=True), WordEmbedder()).retrieve("budgeting")
    assert (result.mode, result.evidence, result.sufficient) == ("unavailable", [], False)


def test_the_evaluation_script_passes_its_gate(tmp_path):
    pytest.importorskip("fastembed")
    from training import evaluate_copilot_retrieval

    assert evaluate_copilot_retrieval.main(["--gate", "--report-dir", str(tmp_path)]) == 0
