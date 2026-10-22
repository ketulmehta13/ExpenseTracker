"""Ingest ml-service/knowledge/ into the copilot's knowledge base (Supabase pgvector).

Usage (from ml-service/):
    python -m training.ingest_kb --dry-run     # show what would change, write nothing
    python -m training.ingest_kb               # add new and changed documents, delete removed ones
    python -m training.ingest_kb --no-prune    # ...but keep documents whose files are gone

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment: only this job writes the
knowledge base (the web service reads it with the public anon key). In CI the key is a GitHub
Actions secret (.github/workflows/ingest-kb.yml); never put it in a file.

Ingestion is incremental: unchanged documents are skipped, so running it again is safe.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from app.config import DEFAULT_KNOWLEDGE_DIR, DEFAULT_MODEL_DIR
from app.rag.chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from app.rag.documents import DocumentError, load_documents
from app.rag.embeddings import GTE_SMALL, load_embedder
from app.rag.ingest import ingest
from app.rag.vectorstore import SupabaseVectorStore, VectorStoreError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the knowledge files into Supabase pgvector.")
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    parser.add_argument("--no-prune", action="store_true", help="keep documents whose files were deleted")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.", file=sys.stderr)
        return 2
    try:
        documents = load_documents(args.knowledge_dir)
    except DocumentError as err:
        print(f"Invalid knowledge file: {err}", file=sys.stderr)
        return 1
    embedder = load_embedder(GTE_SMALL, DEFAULT_MODEL_DIR / "embeddings")
    if embedder is None:
        print(f"Could not load {GTE_SMALL}.", file=sys.stderr)
        return 1
    try:
        report = ingest(
            documents,
            SupabaseVectorStore(url, key, timeout=30),
            embedder,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            prune=not args.no_prune,
            dry_run=args.dry_run,
        )
    except VectorStoreError as err:
        print(f"Ingestion failed: {err}", file=sys.stderr)
        return 1
    print(("Dry run: " if args.dry_run else "") + report.summary())
    for label, ids in (("added", report.added), ("updated", report.updated), ("deleted", report.deleted)):
        for doc_id in ids:
            print(f"  {label}: {doc_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
