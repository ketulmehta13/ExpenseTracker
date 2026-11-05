"""Build the chatbot's FAISS index from ml-service/knowledge/ and save it to disk.

Usage (from ml-service/):
    python -m training.build_index

The Docker build runs this, so the index ships inside the image. Run it locally after changing
a knowledge file (.md, .txt or .pdf); the API loads the saved index at startup without
re-embedding anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.chatbot.index import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    build_vector_store,
    load_embeddings,
    load_source_documents,
    save_index,
    split_documents,
)
from app.config import DEFAULT_KNOWLEDGE_DIR, DEFAULT_MODEL_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the chatbot's FAISS index.")
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_MODEL_DIR / "faiss")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=CHUNK_OVERLAP)
    args = parser.parse_args(argv)

    documents = load_source_documents(args.knowledge_dir)
    chunks = split_documents(documents, args.chunk_size, args.overlap)
    embeddings = load_embeddings(DEFAULT_MODEL_DIR / "embeddings")
    save_index(build_vector_store(chunks, embeddings), args.out)
    print(f"{len(documents)} documents, {len(chunks)} chunks -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
