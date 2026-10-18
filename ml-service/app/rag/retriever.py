"""Hybrid search over the help center: keywords (BM25) and meaning (embeddings), fused.

Keyword search is exact and transparent but misses paraphrases ("stop paying" vs "cancel").
Embedding search finds paraphrases but can blur specifics ("PDF" vs "CSV"). Hybrid search runs
both and merges the two rankings with Reciprocal Rank Fusion:

    fused(doc) = sum over rankings of 1 / (60 + rank of doc in that ranking)

RRF uses ranks, not raw scores, so a BM25 score of 12.3 and a cosine of 0.81 never need to be
put on one scale. At this size (dozens of chunks) the vectors live in a NumPy array; a vector
database (pgvector, FAISS) only pays off at thousands of documents or more.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.rag.bm25 import BM25
from app.rag.embeddings import Embedder
from app.rag.knowledge import Chunk

RRF_K = 60
# Below this cosine similarity to every section, a question is off-topic. Calibrated for
# bge-small-en-v1.5 on the dev questions (training/evaluate_rag.py): in-scope ones scored 0.63
# or more, off-topic ones 0.57 or less. A different embedding model needs its own value.
DECLINE_BELOW = 0.60


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # fused (or single-method) score: higher is better
    similarity: float | None  # cosine similarity to the query, when embeddings are available


class HelpIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder | None, decline_below: float = DECLINE_BELOW):
        self.chunks = chunks
        self.embedder = embedder
        self.decline_below = decline_below
        self.bm25 = BM25([chunk.text for chunk in chunks])
        self.vectors = embedder.embed_passages([chunk.text for chunk in chunks]) if embedder else None

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[Hit]:
        """Top-k chunks. `mode` is "hybrid", "bm25" or "dense" (the last two for comparison)."""
        keyword = np.array(self.bm25.scores(query))
        similarity = self.vectors @ self.embedder.embed_query(query) if self.vectors is not None else None
        if mode == "dense" and similarity is not None:
            fused = similarity
        elif mode == "bm25" or similarity is None:
            fused = keyword
        else:
            fused = np.zeros(len(self.chunks))
            for scores in (keyword, similarity):
                ranks = np.empty(len(scores), dtype=int)
                ranks[np.argsort(-scores, kind="stable")] = np.arange(1, len(scores) + 1)
                fused += 1.0 / (RRF_K + ranks)
        best = np.argsort(-fused, kind="stable")[:k]
        return [
            Hit(self.chunks[i], float(fused[i]), None if similarity is None else float(similarity[i]))
            for i in best
        ]

    def top_similarity(self, query: str) -> float | None:
        """How close the query is to anything in the help center (None without embeddings)."""
        if self.vectors is None:
            return None
        return float(np.max(self.vectors @ self.embedder.embed_query(query)))

    def in_scope(self, query: str) -> bool:
        """Whether the help center is likely to answer it. Without embeddings, assume so."""
        similarity = self.top_similarity(query)
        return similarity is None or similarity >= self.decline_below


def ranked_articles(hits: list[Hit]) -> list[str]:
    """Articles in order of their best chunk, without repeats."""
    return list(dict.fromkeys(hit.chunk.article for hit in hits))
