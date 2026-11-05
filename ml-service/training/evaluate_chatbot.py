"""Evaluate the RAG chatbot.

Usage (from ml-service/):
    python -m training.evaluate_chatbot          # retrieval, routing, exact figures; writes reports/chatbot/
    python -m training.evaluate_chatbot --gate   # ...and fail if the test set misses a floor (what CI runs)
    python -m training.evaluate_chatbot --llm    # ...plus real Groq answers (needs GROQ_API_KEY)

1. Retrieval: hand-labelled questions, each with the article(s) that answer it. The dev questions
   choose chunk size, overlap and k; the test questions are only scored.
2. Routing: messages labelled with the calculator they need, or none
   (training/data/chatbot_routing_test.jsonl).
3. Figures: the calculators' answers for simulated users against an independent integer-paise sum.
4. With --llm: test questions answered end to end; how many were answered, how many off-topic
   ones were declined, and how many answers the number check rejected.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import UTC, date, datetime
from pathlib import Path

from app.chatbot import data_answers
from app.chatbot.chain import answer_chain, check_answer, format_docs, is_dont_know
from app.chatbot.index import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    build_vector_store,
    load_embeddings,
    load_source_documents,
    split_documents,
)
from app.config import DEFAULT_KNOWLEDGE_DIR, DEFAULT_MODEL_DIR, Settings
from training.runs import record_run
from training.simulate_history import CATEGORY_IDS, simulate_users

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "chatbot"
CHUNKINGS = [(500, 100), (500, 200), (1000, 100), (1000, 200), (1500, 200)]
KS = (3, 4, 6)
CHOSEN_K = 4
FLOORS = {"hit@k": 0.90, "hit@1": 0.70, "routing_accuracy": 0.85, "figures_correct": 1.0}
TODAY = date(2026, 10, 18)
CATEGORIES = [{"id": cid, "name": name.title()} for name, cid in CATEGORY_IDS.items()]


def load_questions(split: str) -> list[dict]:
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


def retrieval(store, rows: list[dict], k: int) -> dict:
    hits1, hitsk, reciprocal, misses, chars = [], [], [], [], []
    for row in rows:
        if not row["documents"]:
            continue
        docs = store.similarity_search(row["question"], k=k)
        chars.append(sum(len(doc.page_content) for doc in docs))
        ranked = list(dict.fromkeys(doc.metadata["document"] for doc in docs))
        rank = next((i for i, d in enumerate(ranked, start=1) if d in row["documents"]), None)
        hits1.append(rank == 1)
        hitsk.append(rank is not None)
        reciprocal.append(1 / rank if rank else 0.0)
        if rank is None:
            misses.append({"question": row["question"], "expected": row["documents"], "got": ranked[:3]})
    return {
        "hit@1": round(statistics.fmean(hits1), 4),
        "hit@k": round(statistics.fmean(hitsk), 4),
        "mrr": round(statistics.fmean(reciprocal), 4),
        "context_chars": round(statistics.fmean(chars)),
        "questions": len(hits1),
        "misses": misses,
    }


def routing() -> dict:
    with open(DATA_DIR / "chatbot_routing_test.jsonl", encoding="utf-8") as lines:
        rows = [json.loads(line) for line in lines if line.strip()]
    misses = []
    for row in rows:
        result = data_answers.classify(row["message"], TODAY)
        got = result.kind if result else None
        if got != row["kind"]:
            misses.append({"message": row["message"], "expected": row["kind"], "got": got})
    return {
        "routing_accuracy": round(1 - len(misses) / len(rows), 4),
        "questions": len(rows),
        "misses": misses,
    }


class _Rows:
    """SupabaseData for the calculators, over one simulated user's rows."""

    def __init__(self, rows: list[dict], budget: float):
        self.rows, self.budget = rows, budget

    async def select(self, table, params=None, limit=20_000):
        if table == "transactions":
            return self.rows
        if table == "categories":
            return CATEGORIES
        return [{"monthly_budget": self.budget}]


def _paise(rows, period, kind, category=None) -> int:
    return sum(
        round(float(r["amount"]) * 100)
        for r in rows
        if r["type"] == kind
        and period.start.isoformat() <= r["date"][:10] <= period.end.isoformat()
        and (category is None or r["category_id"] == category)
    )


async def _ask(question: str, data: _Rows) -> str:
    parsed = data_answers.classify(question, TODAY)
    return (await data_answers.answer(parsed, data, "user", TODAY)).text


def figures(users: int = 25) -> dict:
    checks = wrong = 0
    questions = ["this month", "last month", "this week", "the last 7 days", "this year"]

    def expect(reply: str, paise: int) -> None:
        nonlocal checks, wrong
        checks += 1
        wrong += data_answers._money(data_answers.Decimal(paise) / 100) not in reply

    async def run() -> None:
        for user in simulate_users(users, TODAY, seed=101):
            rows, data = user.transactions, _Rows(user.transactions, user.monthly_budget)
            for words in questions:
                period = data_answers.parse_period(words, TODAY)[0]
                spent = _paise(rows, period, "EXPENSE")
                if spent:
                    expect(await _ask(f"how much did I spend {words}", data), spent)
                food = _paise(rows, period, "EXPENSE", CATEGORY_IDS["food"])
                if food:
                    expect(await _ask(f"how much did I spend on food {words}", data), food)
                income = _paise(rows, period, "INCOME")
                if income:
                    reply = await _ask(f"how much did I earn {words}", data)
                    expect(reply, income)
                    expect(reply, income - spent)

    asyncio.run(run())
    return {"checks": checks, "wrong": wrong, "figures_correct": round(1 - wrong / checks, 6)}


async def with_groq(store, k: int) -> dict:
    from app.chatbot.chain import build_llm

    settings = Settings.from_env()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("--llm needs GROQ_API_KEY in the environment")
    chain = answer_chain(llm)
    rows = load_questions("test")
    counts = {
        "answered": 0,
        "said_dont_know": 0,
        "off_topic_declined": 0,
        "off_topic_answered": 0,
        "number_check_rejected": 0,
        "failed": 0,
    }
    seconds, samples = [], []
    for row in rows:
        await asyncio.sleep(2.2)  # stay inside the free tier's per-minute limit
        docs = store.similarity_search(row["question"], k=k)
        context = format_docs(docs)
        started = time.perf_counter()
        try:
            raw = await chain.ainvoke({"context": context, "question": row["question"]})
        except Exception as err:
            counts["failed"] += 1
            print(f"failed: {type(err).__name__}")
            continue
        seconds.append(time.perf_counter() - started)
        declined = is_dont_know(raw)
        if not row["documents"]:
            counts["off_topic_declined" if declined else "off_topic_answered"] += 1
            if not declined:
                samples.append({"question": row["question"], "answer": raw, "note": "off-topic but answered"})
            continue
        if declined:
            counts["said_dont_know"] += 1
            samples.append({"question": row["question"], "answer": raw, "note": "answerable but declined"})
            continue
        if check_answer(raw, context, row["question"]) != " ".join(raw.split()):
            counts["number_check_rejected"] += 1
            samples.append({"question": row["question"], "answer": raw, "note": "number check rejected"})
            continue
        counts["answered"] += 1
    return {
        "model": settings.groq_model,
        **counts,
        "median_seconds": round(statistics.median(seconds), 2) if seconds else None,
        "problems": samples,
    }


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def report(m: dict) -> str:
    sweep = _table(
        ["Chunk size / overlap", "k", "Chunks", "Dev hit@1", "Dev hit@k", "Dev MRR", "Context chars"],
        [
            [
                r["chunking"], str(r["k"]), str(r["chunks"]), f"{r['hit@1']:.3f}", f"{r['hit@k']:.3f}",
                f"{r['mrr']:.3f}", str(r["context_chars"]),
            ]
            for r in m["sweep"]
        ],
    )  # fmt: skip
    test, route, fig = m["test"], m["routing"], m["figures"]
    test_misses = (
        _table(
            ["Question", "Expected", "Got"],
            [[x["question"], ", ".join(x["expected"]), ", ".join(x["got"])] for x in test["misses"]],
        )
        if test["misses"]
        else "None."
    )
    route_misses = (
        _table(
            ["Message", "Expected", "Got"],
            [[x["message"], str(x["expected"]), str(x["got"])] for x in route["misses"]],
        )
        if route["misses"]
        else "None."
    )
    llm = "Not run in this report (`--llm` needs `GROQ_API_KEY`)."
    if m.get("llm"):
        e = m["llm"]
        counted = [k for k in e if k not in ("model", "median_seconds", "problems")]
        llm = f"Model `{e['model']}`, median {e['median_seconds']} s per answer.\n\n" + _table(
            ["Outcome", "Questions"], [[k.replace("_", " "), str(e[k])] for k in counted]
        )
        if e["problems"]:
            llm += "\n\n" + _table(
                ["Question", "Note", "Model's answer"],
                [[p["question"], p["note"], " ".join(p["answer"].split())[:160]] for p in e["problems"]],
            )
    gate = _table(["Check", "Result"], [[k, "pass" if ok else "**FAIL**"] for k, ok in m["gate"].items()])
    return f"""# RAG chatbot: evaluation report

Generated by `python -m training.evaluate_chatbot` on {m["generated_at"]}. Do not edit by hand.

Index: {m["documents"]} documents, `sentence-transformers/all-MiniLM-L6-v2`, FAISS. A question counts as
a hit when a labelled article is among the retrieved chunks' documents.

## Tuning chunk size, overlap and k (dev questions only)

{sweep}

Using: chunk size {m["chosen"]["chunk_size"]}, overlap {m["chosen"]["overlap"]}, k = {m["chosen"]["k"]}.

## Retrieval on the test questions

{test["questions"]} questions: hit@1 **{test["hit@1"]:.3f}**, hit@{m["chosen"]["k"]} **{test["hit@k"]:.3f}**,
MRR {test["mrr"]:.3f}.

Not retrieved:

{test_misses}

## Routing to the calculators

{route["questions"]} messages: accuracy **{route["routing_accuracy"]:.3f}**.

{route_misses}

## Exact figures

{fig["checks"]} figures for simulated users against an independent integer-paise sum:
**{fig["wrong"]} wrong**.

## End to end with Groq

{llm}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the RAG chatbot.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--llm", action="store_true", help="also answer the test questions with Groq")
    args = parser.parse_args(argv)

    documents = load_source_documents(DEFAULT_KNOWLEDGE_DIR)
    embeddings = load_embeddings(DEFAULT_MODEL_DIR / "embeddings")
    dev, test = load_questions("dev"), load_questions("test")

    sweep, chosen_store = [], None
    for size, overlap in CHUNKINGS:
        chunks = split_documents(documents, size, overlap)
        store = build_vector_store(chunks, embeddings)
        if (size, overlap) == (CHUNK_SIZE, CHUNK_OVERLAP):
            chosen_store = store
        for k in KS:
            result = retrieval(store, dev, k)
            sweep.append({"chunking": f"{size} / {overlap}", "k": k, "chunks": len(chunks), **result})
            print(f"{size:>5}/{overlap:<4} k={k} hit@1 {result['hit@1']:.3f} hit@k {result['hit@k']:.3f} "
                  f"mrr {result['mrr']:.3f} chars {result['context_chars']}")  # fmt: skip

    metrics: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "documents": len(documents),
        "chosen": {"chunk_size": CHUNK_SIZE, "overlap": CHUNK_OVERLAP, "k": CHOSEN_K},
        "sweep": sweep,
        "test": retrieval(chosen_store, test, CHOSEN_K),
        "routing": routing(),
        "figures": figures(),
    }
    if args.llm:
        metrics["llm"] = asyncio.run(with_groq(chosen_store, CHOSEN_K))
        print({k: v for k, v in metrics["llm"].items() if k != "problems"})
    values = {
        "hit@k": metrics["test"]["hit@k"],
        "hit@1": metrics["test"]["hit@1"],
        "routing_accuracy": metrics["routing"]["routing_accuracy"],
        "figures_correct": metrics["figures"]["figures_correct"],
    }
    metrics["gate"] = {
        f"{k} >= {floor} (got {values[k]:.3f})": values[k] >= floor for k, floor in FLOORS.items()
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    record_run("chatbot", args.report_dir, metrics["chosen"], values)
    print(values, metrics["routing"]["misses"], metrics["test"]["misses"], metrics["figures"])
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
