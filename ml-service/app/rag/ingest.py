"""Incremental ingestion: bring the vector store in line with the knowledge files.

For each document, compare its sha256 with the stored one:
- unchanged: skipped (no embedding work, no writes), so re-running is cheap and safe;
- new or changed: chunked, embedded and written, replacing all of its old chunks, so a
  document never ends up with duplicate or stale chunks;
- in the store but no longer on disk: deleted (with `prune`), with its chunks.

Chunk size and overlap are part of the fingerprint too: changing them re-ingests everything.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from app.rag.chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, split_document
from app.rag.documents import Document
from app.rag.embeddings import Embedder
from app.rag.vectorstore import VectorStore

logger = logging.getLogger("ml_service.rag")


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    chunks_written: int = 0

    def summary(self) -> str:
        return (
            f"added {len(self.added)}, updated {len(self.updated)}, unchanged {len(self.unchanged)}, "
            f"deleted {len(self.deleted)}, chunks written {self.chunks_written}"
        )


def fingerprint(doc: Document, chunk_size: int, overlap: int) -> str:
    return hashlib.sha256(f"{doc.sha256}:{chunk_size}:{overlap}".encode()).hexdigest()


def ingest(
    documents: list[Document],
    store: VectorStore,
    embedder: Embedder,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    prune: bool = True,
    dry_run: bool = False,
) -> IngestReport:
    report = IngestReport()
    stored = store.documents()
    for doc in documents:
        current = stored.get(doc.id)
        sha = fingerprint(doc, chunk_size, overlap)
        if current is not None and current.sha256 == sha:
            report.unchanged.append(doc.id)
            continue
        chunks = split_document(doc, chunk_size, overlap)
        (report.updated if current is not None else report.added).append(doc.id)
        report.chunks_written += len(chunks)
        if dry_run:
            continue
        embeddings = embedder.embed_passages([chunk.search_text for chunk in chunks])
        # The stored sha is the fingerprint, so a chunking change also counts as a change
        store.replace_document(doc, chunks, embeddings, sha)
        logger.info("ingested %s: %d chunks", doc.id, len(chunks))
    if prune:
        on_disk = {doc.id for doc in documents}
        for doc_id in sorted(set(stored) - on_disk):
            report.deleted.append(doc_id)
            if not dry_run:
                store.delete_document(doc_id)
    return report
