"""Retrieval for the copilot: hybrid search over the knowledge base, with a sufficiency check.

1. Dense: the query's gte-small embedding against pgvector (match_kb_chunks), top candidates.
2. Keywords: BM25 over the same chunks' text (cached in memory, refreshed every few minutes).
3. Reciprocal Rank Fusion of the two rankings (see app/rag/retriever.py for why ranks, not scores).
4. Sufficiency: if the best chunk isn't close enough in meaning (or, without embeddings, the
   question's words barely appear in the knowledge base), the evidence is "insufficient" and the
   copilot says it doesn't know instead of answering from weak matches.

The thresholds are calibrated on the dev questions by training/evaluate_copilot_retrieval.py.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

from app.rag.bm25 import BM25, tokenize
from app.rag.chunking import KbChunk
from app.rag.embeddings import Embedder
from app.rag.vectorstore import VectorStore, VectorStoreError

logger = logging.getLogger("ml_service.rag")

RRF_K = 60
DENSE_CANDIDATES = 20
# Calibrated for Supabase/gte-small on the dev questions (training/evaluate_copilot_retrieval.py)
MIN_SIMILARITY = 0.80
MIN_KEYWORD_COVERAGE = 0.3


@dataclass(frozen=True)
class Evidence:
    ref: str  # "finance/budgeting-methods#2"
    document_id: str
    title: str
    section: str
    content: str
    topic: str
    source: str
    source_url: str | None
    version: int
    similarity: float | None  # cosine to the query, when embeddings were used
    score: float  # fused rank score


@dataclass(frozen=True)
class Retrieval:
    evidence: list[Evidence]
    sufficient: bool
    top_similarity: float | None
    mode: str  # "hybrid", "keyword" (no embedder) or "unavailable" (store down)


def _key(chunk: KbChunk) -> str:
    return f"{chunk.document_id}#{chunk.index}"


class KnowledgeRetriever:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder | None,
        *,
        refresh_seconds: float = 600,
        min_similarity: float = MIN_SIMILARITY,
        min_keyword_coverage: float = MIN_KEYWORD_COVERAGE,
    ):
        self.store = store
        self.embedder = embedder
        self.refresh_seconds = refresh_seconds
        self.min_similarity = min_similarity
        self.min_keyword_coverage = min_keyword_coverage
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._corpus: list[tuple[KbChunk, str | None]] = []
        self._bm25: BM25 | None = None

    def _keyword_index(self) -> tuple[list[tuple[KbChunk, str | None]], BM25 | None]:
        with self._lock:
            if self._bm25 is None or time.monotonic() - self._loaded_at > self.refresh_seconds:
                corpus = self.store.chunks()
                self._corpus = corpus
                self._bm25 = BM25([_search_text(chunk) for chunk, _ in corpus]) if corpus else None
                self._loaded_at = time.monotonic()
            return self._corpus, self._bm25

    def keyword_coverage(self, query: str) -> float:
        _, bm25 = self._keyword_index()
        terms = tokenize(query)
        if not terms or bm25 is None or not bm25.idf:
            return 0.0
        rarest = max(bm25.idf.values())
        weights = [(term in bm25.idf, bm25.idf.get(term, rarest)) for term in terms]
        return sum(w for known, w in weights if known) / sum(w for _, w in weights)

    def retrieve(self, query: str, k: int = 4, topics: list[str] | None = None) -> Retrieval:
        k = max(1, min(k, 10))
        try:
            corpus, bm25 = self._keyword_index()
        except VectorStoreError as err:
            logger.warning("knowledge base unavailable: %s", err)
            return Retrieval([], False, None, "unavailable")
        if not corpus:
            return Retrieval([], False, None, "unavailable")

        allowed = [
            i
            for i, (chunk, _) in enumerate(corpus)
            if topics is None or chunk.metadata.get("topic") in topics
        ]
        keyword_scores = np.array(bm25.scores(query)) if bm25 else np.zeros(len(corpus))
        keyword_rank = sorted((i for i in allowed if keyword_scores[i] > 0), key=lambda i: -keyword_scores[i])

        similarity: dict[str, float] = {}
        dense_rank: list[str] = []
        urls = {_key(chunk): url for chunk, url in corpus}
        mode = "keyword"
        if self.embedder is not None:
            try:
                hits = self.store.search(self.embedder.embed_query(query), DENSE_CANDIDATES, topics)
                dense_rank = [_key(hit.chunk) for hit in hits]
                similarity = {_key(hit.chunk): hit.similarity for hit in hits}
                mode = "hybrid"
            except VectorStoreError as err:
                logger.warning("vector search failed, keywords only: %s", err)

        fused: dict[str, float] = {}
        for rank, i in enumerate(keyword_rank[:DENSE_CANDIDATES], start=1):
            fused[_key(corpus[i][0])] = fused.get(_key(corpus[i][0]), 0) + 1 / (RRF_K + rank)
        for rank, key in enumerate(dense_rank, start=1):
            fused[key] = fused.get(key, 0) + 1 / (RRF_K + rank)
        by_key = {_key(chunk): chunk for chunk, _ in corpus}
        best = sorted((key for key in fused if key in by_key), key=lambda key: -fused[key])[:k]

        top_similarity = max(similarity.values()) if similarity else None
        if top_similarity is not None:
            sufficient = top_similarity >= self.min_similarity
        else:
            sufficient = bool(best) and self.keyword_coverage(query) >= self.min_keyword_coverage
        evidence = [_evidence(by_key[key], urls.get(key), similarity.get(key), fused[key]) for key in best]
        return Retrieval(evidence, sufficient and bool(evidence), top_similarity, mode)


def _search_text(chunk: KbChunk) -> str:
    return chunk.search_text


def _evidence(chunk: KbChunk, url: str | None, similarity: float | None, score: float) -> Evidence:
    meta = chunk.metadata
    return Evidence(
        ref=_key(chunk),
        document_id=chunk.document_id,
        title=str(meta.get("title", chunk.document_id)),
        section=chunk.section,
        content=chunk.content,
        topic=str(meta.get("topic", "")),
        source=str(meta.get("source", "")),
        source_url=url,
        version=int(meta.get("version", 1)),
        similarity=None if similarity is None else round(similarity, 4),
        score=round(score, 6),
    )
