"""Evaluate the copilot's knowledge retrieval: keyword vs dense (gte-small) vs hybrid, two chunk sizes.

Usage (from ml-service/):
    python -m training.evaluate_copilot_retrieval          # evaluate, write reports/copilot_retrieval/
    python -m training.evaluate_copilot_retrieval --gate   # ...and fail if the test set misses a floor

The whole knowledge base (ml-service/knowledge/, app help and finance articles) is ingested into
an in-memory vector store with the same ranking as pgvector (cosine), using the production
embedding model. Questions:
- help_{dev,test}.jsonl: the app-help questions of the original help search (training/evaluate_rag.py);
- kb_finance_{dev,test}.jsonl: financial-education questions, plus off-topic ones to decline.
Dev chooses the design and the sufficiency threshold; test is reported and gated, never tuned on.

Metrics, at document level: hit@1, hit@3, MRR@5 for answerable questions; decline accuracy
(answerable ones judged sufficient, off-topic ones insufficient); retrieval latency per question.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import DEFAULT_KNOWLEDGE_DIR, DEFAULT_MODEL_DIR
from app.rag.documents import load_documents
from app.rag.embeddings import GTE_SMALL, load_embedder
from app.rag.ingest import ingest
from app.rag.kb_retriever import MIN_SIMILARITY, KnowledgeRetriever
from app.rag.vectorstore import InMemoryVectorStore
from training.runs import record_run

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "copilot_retrieval"
CHUNKINGS = {"sections (900/150)": (900, 150), "small (400/80)": (400, 80)}
CHOSEN = ("sections (900/150)", "hybrid")
FLOORS = {"hit@1": 0.80, "hit@3": 0.90, "decline_accuracy": 0.85}
THRESHOLDS = (0.74, 0.76, 0.78, 0.80, 0.82, 0.84)


def load(split: str) -> list[dict]:
    rows = []
    for name in (f"help_{split}.jsonl", f"kb_finance_{split}.jsonl"):
        with open(DATA_DIR / name, encoding="utf-8") as lines:
            for line in lines:
                if line.strip():
                    row = json.loads(line)
                    rows.append(
                        {
                            "question": row["question"],
                            "documents": row.get("documents", row.get("articles", [])),
                        }
                    )
    return rows


def ranked_documents(retriever: KnowledgeRetriever, store: InMemoryVectorStore, question: str, mode: str):
    """Documents in rank order, for one search mode, and the retrieval itself (None for dense-only)."""
    if mode == "dense":
        hits = store.search(retriever.embedder.embed_query(question), 15)
        return list(dict.fromkeys(hit.chunk.document_id for hit in hits)), hits[0].similarity if hits else 0.0
    result = retriever.retrieve(question, k=10)
    return list(dict.fromkeys(e.document_id for e in result.evidence)), result


def evaluate(retrievers: dict, store: InMemoryVectorStore, rows: list[dict], threshold: float) -> dict:
    results = {}
    for mode, retriever in retrievers.items():
        hits1, hits3, reciprocal, declines, seconds, misses = [], [], [], [], [], []
        retriever.min_similarity = threshold
        for row in rows:
            started = time.perf_counter()
            documents, result = ranked_documents(retriever, store, row["question"], mode)
            seconds.append(time.perf_counter() - started)
            sufficient = result >= threshold if mode == "dense" else result.sufficient
            declines.append(sufficient == bool(row["documents"]))
            if not row["documents"]:
                continue
            rank = next((i for i, d in enumerate(documents[:5], start=1) if d in row["documents"]), None)
            hits1.append(rank == 1)
            hits3.append(rank is not None and rank <= 3)
            reciprocal.append(1 / rank if rank else 0.0)
            if rank != 1:
                misses.append(
                    {"question": row["question"], "expected": row["documents"], "got": documents[:3]}
                )
        results[mode] = {
            "hit@1": round(statistics.fmean(hits1), 4),
            "hit@3": round(statistics.fmean(hits3), 4),
            "mrr@5": round(statistics.fmean(reciprocal), 4),
            "decline_accuracy": round(statistics.fmean(declines), 4),
            "ms_per_question": round(1000 * statistics.fmean(seconds), 1),
            "misses": misses,
        }
    return results


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def report(metrics: dict) -> str:
    rows = []
    for chunking, by_mode in metrics["test"].items():
        for mode, m in by_mode.items():
            bold = "**" if (chunking, mode) == CHOSEN else ""
            dev = metrics["dev"][chunking][mode]
            rows.append(
                [
                    f"{bold}{chunking}, {mode}{bold}",
                    f"{dev['hit@1']:.3f}",
                    f"{m['hit@1']:.3f}",
                    f"{m['hit@3']:.3f}",
                    f"{m['mrr@5']:.3f}",
                    f"{m['decline_accuracy']:.3f}",
                    f"{m['ms_per_question']:.0f} ms",
                ]
            )
    sweep = _table(
        ["Similarity threshold", "Dev decline accuracy (hybrid)"],
        [[str(t), f"{a:.3f}"] for t, a in metrics["threshold_sweep"].items()],
    )
    misses = metrics["test"][CHOSEN[0]][CHOSEN[1]]["misses"]
    miss_rows = [[m["question"], ", ".join(m["expected"]), ", ".join(m["got"]) or "-"] for m in misses]
    gate = _table(
        ["Check (test, chosen design)", "Result"],
        [[name, "pass" if ok else "**FAIL**"] for name, ok in metrics["gate"].items()],
    )
    header = ["Design", "Dev hit@1", "Test hit@1", "Test hit@3", "Test MRR@5", "Test decline acc.", "Latency"]
    results = _table(header, rows)
    generated, model = metrics["generated_at"], metrics["embedding_model"]
    docs, chunks = metrics["documents"], metrics["chunks"]
    n_dev, n_test = metrics["questions"]["dev"], metrics["questions"]["test"]
    return f"""# Copilot knowledge retrieval: evaluation report

Generated by `python -m training.evaluate_copilot_retrieval` on {generated}. Do not edit by hand.

Knowledge base: {docs} documents ({chunks} chunks with the chosen chunking), embedded
with `{model}`. Questions: {n_dev} dev and {n_test} test,
app help and financial education, including off-topic questions that should be declined.

## Results

Hit@1 and hit@3 count a question as answered when a labelled document is ranked first / in the top three.
Decline accuracy counts answerable questions judged sufficient and off-topic ones judged insufficient.

{results}

Chosen: **{CHOSEN[0]}, {CHOSEN[1]}**. On the original app-help test questions alone it scores
{metrics["help_only_test_hit@1"]:.3f} hit@1 (the previous help search: 0.900 hybrid with bge-small, 0.733
keyword-only, which is what production ran on the free server).

## Sufficiency threshold (chosen on dev)

{sweep}

Chosen: {metrics["threshold"]} (the code default in `app/rag/kb_retriever.py` is {MIN_SIMILARITY}).

## Test questions not answered first (chosen design)

{_table(["Question", "Expected", "Got (top 3)"], miss_rows) if miss_rows else "None."}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the copilot's knowledge retrieval.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)

    embedder = load_embedder(GTE_SMALL, DEFAULT_MODEL_DIR / "embeddings")
    if embedder is None:
        raise SystemExit(f"{GTE_SMALL} could not be loaded")
    documents = load_documents(DEFAULT_KNOWLEDGE_DIR)
    dev, test = load("dev"), load("test")

    metrics: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "embedding_model": GTE_SMALL,
        "documents": len(documents),
        "questions": {"dev": len(dev), "test": len(test)},
        "dev": {},
        "test": {},
    }
    stores = {}
    for name, (size, overlap) in CHUNKINGS.items():
        store = InMemoryVectorStore()
        report_ = ingest(documents, store, embedder, chunk_size=size, overlap=overlap)
        stores[name] = (store, report_.chunks_written)

    # Choose the threshold on dev, with the chosen chunking and hybrid search
    chosen_store = stores[CHOSEN[0]][0]
    hybrid = KnowledgeRetriever(chosen_store, embedder)
    sweep = {
        t: evaluate({"hybrid": hybrid}, chosen_store, dev, t)["hybrid"]["decline_accuracy"]
        for t in THRESHOLDS
    }
    threshold = max(sweep, key=lambda t: (sweep[t], -abs(t - MIN_SIMILARITY)))
    metrics["threshold_sweep"] = sweep
    metrics["threshold"] = threshold

    for name, (store, chunks) in stores.items():
        retrievers = {
            "keyword": KnowledgeRetriever(store, None),
            "dense": KnowledgeRetriever(store, embedder),
            "hybrid": KnowledgeRetriever(store, embedder),
        }
        metrics["dev"][name] = evaluate(retrievers, store, dev, threshold)
        metrics["test"][name] = evaluate(retrievers, store, test, threshold)
        if name == CHOSEN[0]:
            metrics["chunks"] = chunks
            help_test = [
                row for row in test if all("/" not in d for d in row["documents"]) and row["documents"]
            ]
            metrics["help_only_test_hit@1"] = evaluate(
                {"hybrid": retrievers["hybrid"]}, store, help_test, threshold
            )["hybrid"]["hit@1"]
        for split in ("dev", "test"):
            for mode, m in metrics[split][name].items():
                print(
                    f"{split:<4} {name:<20} {mode:<7} hit@1 {m['hit@1']:.3f}  hit@3 {m['hit@3']:.3f}  "
                    f"mrr@5 {m['mrr@5']:.3f}  decline {m['decline_accuracy']:.3f}  {m['ms_per_question']} ms"
                )

    chosen = metrics["test"][CHOSEN[0]][CHOSEN[1]]
    metrics["gate"] = {f"{k} >= {v} (got {chosen[k]:.3f})": chosen[k] >= v for k, v in FLOORS.items()}
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    record_run(
        "copilot_retrieval",
        args.report_dir,
        {"chunking": CHOSEN[0], "threshold": threshold},
        {k: chosen[k] for k in ("hit@1", "hit@3", "mrr@5", "decline_accuracy")},
    )
    print(f"threshold {threshold}; reports: {args.report_dir}")
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
