"""Where knowledge-base chunks and their embeddings live.

Two stores with one interface:
- InMemoryVectorStore: NumPy, for tests, evaluation and local development;
- SupabaseVectorStore: Postgres + pgvector (kb_documents, kb_chunks, match_kb_chunks()) through
  Supabase's REST API. Reads use the public anon key (the knowledge base is public); writes need
  the service-role key, which only the ingestion job has (never the web service).

Both rank by cosine similarity, so evaluation in memory measures what production does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
import numpy as np

from app.rag.chunking import KbChunk
from app.rag.documents import Document

PENDING_SHA = "0" * 64  # marks a document whose chunks are being replaced


class VectorStoreError(RuntimeError):
    """The vector store can't be reached or rejected a request."""


@dataclass(frozen=True)
class StoredDocument:
    id: str
    sha256: str
    version: int


@dataclass(frozen=True)
class ScoredChunk:
    chunk: KbChunk
    similarity: float
    source_url: str | None = None


class VectorStore(Protocol):
    def documents(self) -> dict[str, StoredDocument]: ...
    def replace_document(
        self, doc: Document, chunks: list[KbChunk], embeddings: np.ndarray, sha256: str
    ) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
    def search(self, query: np.ndarray, k: int, topics: list[str] | None = None) -> list[ScoredChunk]: ...
    def chunks(self) -> list[tuple[KbChunk, str | None]]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._docs: dict[str, tuple[Document, list[KbChunk], np.ndarray]] = {}
        self._shas: dict[str, str] = {}
        self.writes = 0  # how many documents were written, for tests

    def documents(self) -> dict[str, StoredDocument]:
        return {i: StoredDocument(i, self._shas[i], doc.version) for i, (doc, _, _) in self._docs.items()}

    def replace_document(
        self, doc: Document, chunks: list[KbChunk], embeddings: np.ndarray, sha256: str
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("one embedding per chunk")
        self._docs[doc.id] = (doc, list(chunks), np.asarray(embeddings, dtype=np.float32))
        self._shas[doc.id] = sha256
        self.writes += 1

    def delete_document(self, document_id: str) -> None:
        self._docs.pop(document_id, None)
        self._shas.pop(document_id, None)

    def search(self, query: np.ndarray, k: int, topics: list[str] | None = None) -> list[ScoredChunk]:
        scored = [
            ScoredChunk(chunk, float(vector @ query), doc.source_url)
            for doc, chunks, vectors in self._docs.values()
            if topics is None or doc.topic in topics
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        return sorted(scored, key=lambda hit: -hit.similarity)[: max(1, min(k, 50))]

    def chunks(self) -> list[tuple[KbChunk, str | None]]:
        return [(chunk, doc.source_url) for doc, chunks, _ in self._docs.values() for chunk in chunks]


def _vector_literal(vector: np.ndarray) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in np.asarray(vector, dtype=float)) + "]"


class SupabaseVectorStore:
    """pgvector through PostgREST. Pass the anon key to read, the service-role key to ingest."""

    def __init__(self, url: str, key: str, client: httpx.Client | None = None, timeout: float = 10.0):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        self.client = client or httpx.Client(timeout=timeout)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        try:
            response = self.client.request(method, f"{self.base}/{path}", headers=headers, **kwargs)
        except httpx.HTTPError as err:
            raise VectorStoreError(f"knowledge base unreachable: {type(err).__name__}") from err
        if response.status_code >= 400:
            # PostgREST errors name the table or constraint, never the key
            raise VectorStoreError(
                f"knowledge base request failed ({response.status_code}): {response.text[:300]}"
            )
        return response

    def documents(self) -> dict[str, StoredDocument]:
        rows = self._request("GET", "kb_documents", params={"select": "id,content_sha256,version"}).json()
        return {row["id"]: StoredDocument(row["id"], row["content_sha256"], row["version"]) for row in rows}

    def replace_document(
        self, doc: Document, chunks: list[KbChunk], embeddings: np.ndarray, sha256: str
    ) -> None:
        """Replace a document's chunks. The real sha is written last, so an interrupted run leaves
        the document marked pending and the next run redoes it."""
        if len(chunks) != len(embeddings):
            raise ValueError("one embedding per chunk")
        row = {
            "id": doc.id,
            "title": doc.title,
            "source": doc.source,
            "source_url": doc.source_url,
            "topic": doc.topic,
            "version": doc.version,
            "content_sha256": PENDING_SHA,
            "chunk_count": len(chunks),
        }
        self._request(
            "POST", "kb_documents", json=row, headers={"Prefer": "resolution=merge-duplicates,return=minimal"}
        )
        self._request("DELETE", "kb_chunks", params={"document_id": f"eq.{doc.id}"})
        if chunks:
            self._request(
                "POST",
                "kb_chunks",
                headers={"Prefer": "return=minimal"},
                json=[
                    {
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.index,
                        "section": chunk.section,
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "embedding": _vector_literal(vector),
                    }
                    for chunk, vector in zip(chunks, embeddings, strict=True)
                ],
            )
        self._request(
            "PATCH",
            "kb_documents",
            params={"id": f"eq.{doc.id}"},
            json={"content_sha256": sha256, "updated_at": "now"},
            headers={"Prefer": "return=minimal"},
        )

    def delete_document(self, document_id: str) -> None:
        self._request("DELETE", "kb_documents", params={"id": f"eq.{document_id}"})  # chunks cascade

    def search(self, query: np.ndarray, k: int, topics: list[str] | None = None) -> list[ScoredChunk]:
        body = {
            "query_embedding": _vector_literal(query),
            "match_count": max(1, min(k, 50)),
            "topics": topics,
        }
        rows = self._request("POST", "rpc/match_kb_chunks", json=body).json()
        return [
            ScoredChunk(
                KbChunk(
                    row["document_id"],
                    row["chunk_index"],
                    row["section"],
                    row["content"],
                    {
                        **(row.get("metadata") or {}),
                        "title": row["title"],
                        "topic": row["topic"],
                        "source": row["source"],
                        "version": row["version"],
                    },
                ),
                float(row["similarity"]),
                row.get("source_url"),
            )
            for row in rows
        ]

    def chunks(self) -> list[tuple[KbChunk, str | None]]:
        """Every chunk's text (no embeddings), for keyword search. A few hundred rows."""
        rows = self._request(
            "GET",
            "kb_chunks",
            params={
                "select": "document_id,chunk_index,section,content,metadata,"
                "kb_documents(title,topic,source,source_url,version)",
                "order": "document_id,chunk_index",
            },
        ).json()
        result = []
        for row in rows:
            doc = row.get("kb_documents") or {}
            meta = {
                **(row.get("metadata") or {}),
                **{k: doc[k] for k in ("title", "topic", "source", "version") if k in doc},
            }
            result.append(
                (
                    KbChunk(row["document_id"], row["chunk_index"], row["section"], row["content"], meta),
                    doc.get("source_url"),
                )
            )
        return result
