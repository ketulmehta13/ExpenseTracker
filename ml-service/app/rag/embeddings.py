"""Text embeddings for semantic search: a small model that runs on the CPU.

BAAI/bge-small-en-v1.5 maps text to 384 numbers, so that texts with similar meaning land
close together: "download a PDF of my expenses" sits near "export to PDF" although they share
one word. It runs through ONNX Runtime via fastembed (about 70 MB, no PyTorch, no GPU, no API).
Queries and passages are embedded differently: bge models expect an instruction in front of
search queries, which fastembed's query_embed adds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np

logger = logging.getLogger("ml_service.rag")


class Embedder(Protocol):
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    """Unit length, so a dot product is the cosine similarity."""
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: Path, local_files_only: bool = False):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name, cache_dir=str(cache_dir), local_files_only=local_files_only)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return normalize(np.array(list(self.model.passage_embed(texts))))

    def embed_query(self, text: str) -> np.ndarray:
        return normalize(np.array(next(iter(self.model.query_embed(text)))))


def load_embedder(model_name: str, cache_dir: Path) -> FastEmbedder | None:
    """The embedding model from the local cache, downloading it if needed; None if unavailable.

    Without it, help search still works on keywords alone (BM25).
    """
    if not model_name:
        return None
    for local_only in (True, False):
        try:
            return FastEmbedder(model_name, cache_dir, local_files_only=local_only)
        except Exception as err:
            if not local_only:
                logger.warning("embedding model %s unavailable (%s): keyword search only", model_name, err)
    return None
