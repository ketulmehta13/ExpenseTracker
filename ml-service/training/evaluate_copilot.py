"""Evaluate the Financial Copilot.

Usage (from ml-service/):
    python -m training.evaluate_copilot           # routing, financial correctness, grounding checks, latency
    python -m training.evaluate_copilot --gate    # ...and fail if a floor is missed (what CI runs)
    python -m training.evaluate_copilot --llm     # ...plus end-to-end answers from the configured LLM
                                                  #    (LLM_PROVIDER etc. in the environment; not in CI)

1. Routing: hand-labelled messages (training/data/copilot_{dev,test}.jsonl) covering knowledge,
   personal data, combined, actions, small talk, unsupported and adversarial requests. Dev was
   used while writing the rules; test was written separately and is the reported number.
2. Financial correctness: every figure the tools produce for simulated users (a year of
   transactions each), checked against an independent calculation in integer paise.
3. Grounding checks: for knowledge-base passages, a correct cited answer and four planted
   failures (no citation, a source it wasn't given, an invented number, a copied user figure).
4. Latency of the deterministic path (routing + tools + template answer) and of retrieval.
5. With --llm: each knowledge and combined test question answered end to end; how often the
   model's answer passed the grounding check (else a quoted passage was shown), latency, tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.assistant.router import Period, merchant_keys_from
from app.config import DEFAULT_KNOWLEDGE_DIR, DEFAULT_MODEL_DIR, Settings
from app.copilot import tools as t
from app.copilot.compose import check_answer
from app.copilot.facts import describe
from app.copilot.pipeline import CopilotContext, build_copilot_graph
from app.copilot.routing import plan
from app.rag.documents import load_documents
from app.rag.embeddings import GTE_SMALL, load_embedder
from app.rag.ingest import ingest
from app.rag.kb_retriever import KnowledgeRetriever
from app.rag.vectorstore import InMemoryVectorStore
from app.routers.insights import build_insights
from training.runs import record_run
from training.simulate_history import CATEGORY_IDS, simulate_users

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "copilot"
TODAY = date(2026, 10, 18)
FLOORS = {
    "route_accuracy": 0.85,
    "tools_accuracy": 0.85,
    "financial_correctness": 1.0,
    "grounding_catch_rate": 1.0,
    "grounding_good_pass_rate": 0.9,
}
CATEGORIES = [{"id": cid, "name": name.title()} for name, cid in CATEGORY_IDS.items()]


def load(split: str) -> list[dict]:
    with open(DATA_DIR / f"copilot_{split}.jsonl", encoding="utf-8") as lines:
        return [json.loads(line) for line in lines if line.strip()]


# ---------- 1. routing ----------


def routing(rows: list[dict]) -> dict:
    route_ok, tools_ok, misses, by_route = [], [], [], defaultdict(list)
    for row in rows:
        p = plan(row["message"], TODAY, CATEGORIES, {"swiggy", "uber", "amazon", "zomato"})
        r_ok, t_ok = p.route == row["route"], p.tools == row["tools"]
        route_ok.append(r_ok)
        tools_ok.append(r_ok and t_ok)
        by_route[row["route"]].append(r_ok)
        if not (r_ok and t_ok):
            misses.append(
                {
                    "message": row["message"],
                    "expected": f"{row['route']} {row['tools']}",
                    "got": f"{p.route} {p.tools}",
                }
            )
    return {
        "route_accuracy": round(statistics.fmean(route_ok), 4),
        "tools_accuracy": round(statistics.fmean(tools_ok), 4),
        "by_route": {k: round(statistics.fmean(v), 3) for k, v in sorted(by_route.items())},
        "questions": len(rows),
        "misses": misses,
    }


# ---------- 2. financial correctness ----------


def _paise(rows, start: date, end: date, kind: str, category=None) -> int:
    return sum(
        round(float(r["amount"]) * 100)
        for r in rows
        if r["type"] == kind
        and start.isoformat() <= r["date"][:10] <= end.isoformat()
        and (category is None or r["category_id"] == category)
    )


def financial_correctness(users: int = 25) -> dict:
    checks = failures = 0
    periods = [
        Period("this_month", TODAY.replace(day=1), TODAY, "this month"),
        Period(
            "last_month",
            (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1),
            TODAY.replace(day=1) - timedelta(days=1),
            "last month",
        ),
        Period("last_7_days", TODAY - timedelta(days=6), TODAY, "in the last 7 days"),
        Period("this_year", TODAY.replace(month=1, day=1), TODAY, "this year"),
    ]
    examples = []
    for user in simulate_users(users, TODAY, seed=101):
        rows = user.transactions
        data = t.FinanceData(
            TODAY,
            rows,
            CATEGORIES,
            user.monthly_budget,
            SimpleNamespace(forecast=None, recurring=[], unusual=[]),
        )
        for period in periods:
            summary = t.get_expense_summary(data, period)
            expected = {
                "expenses": _paise(rows, period.start, period.end, "EXPENSE"),
                "income": _paise(rows, period.start, period.end, "INCOME"),
            }
            expected["net"] = expected["income"] - expected["expenses"]
            for name, value in expected.items():
                checks += 1
                if round(getattr(summary, name) * 100) != value:
                    failures += 1
                    examples.append(f"{period.key} {name}: {getattr(summary, name)} vs {value / 100}")
            breakdown = t.get_category_breakdown(data, period, top=50)
            for row in breakdown.rows:
                cid = next(c["id"] for c in CATEGORIES if c["name"] == row.category)
                checks += 1
                if round(row.amount * 100) != _paise(rows, period.start, period.end, "EXPENSE", cid):
                    failures += 1
            comparison = t.compare_expense_periods(data, period)
            prev = comparison.previous
            checks += 2
            failures += round(comparison.current_total * 100) != expected["expenses"]
            failures += round(comparison.previous_total * 100) != _paise(
                rows, prev.start, prev.end, "EXPENSE"
            )
    return {
        "checks": checks,
        "failures": failures,
        "financial_correctness": round(1 - failures / checks, 6) if checks else 0.0,
        "examples": examples[:5],
    }


# ---------- 3. grounding checks ----------


def grounding(retriever: KnowledgeRetriever, questions: list[str]) -> dict:
    good = caught = planted = 0
    data = t.FinanceData(
        TODAY,
        [
            {
                "id": 1,
                "title": "Swiggy",
                "amount": 4321.5,
                "date": TODAY.isoformat(),
                "type": "EXPENSE",
                "category_id": CATEGORY_IDS["food"],
            }
        ],
        CATEGORIES,
        None,
        SimpleNamespace(forecast=None, recurring=[], unusual=[]),
    )
    facts = describe(
        [t.get_expense_summary(data, Period("this_month", TODAY.replace(day=1), TODAY, "this month"))]
    )
    for question in questions:
        evidence = retriever.retrieve(question, k=3).evidence
        if not evidence:
            continue
        sentence = evidence[0].content.split(". ")[0].rstrip(".") + "."
        good += check_answer(f"{sentence} [S1]", evidence) is not None
        bad = [
            sentence,  # no citation
            f"{sentence} [S9]",  # a source it wasn't given
            f"{sentence} Most people save 37.5% of their income [S1].",  # an invented number
        ]
        bad_with_facts = ["You spent ₹4,321.50 this month [S1]."]  # copied a figure instead of [spent]
        planted += len(bad) + len(bad_with_facts)
        caught += sum(check_answer(text, evidence) is None for text in bad)
        caught += sum(check_answer(text, evidence, facts) is None for text in bad_with_facts)
    return {
        "good_answers": len(questions),
        "grounding_good_pass_rate": round(good / len(questions), 4),
        "planted_failures": planted,
        "grounding_catch_rate": round(caught / planted, 4) if planted else 0.0,
    }


# ---------- 4./5. end to end ----------


def _context(user, retriever, llm) -> CopilotContext:
    insights = build_insights(user.transactions, CATEGORIES, user.monthly_budget, TODAY)
    data = t.FinanceData(TODAY, user.transactions, CATEGORIES, user.monthly_budget, insights)

    async def no_suggestion(*_):
        return None

    return CopilotContext(data, merchant_keys_from(user.transactions), retriever, llm, 20.0, no_suggestion)


async def end_to_end(rows: list[dict], retriever, llm) -> dict:
    graph = build_copilot_graph()
    user = simulate_users(1, TODAY, seed=7)[0]
    context = _context(user, retriever, llm)
    timings: dict[str, list[float]] = defaultdict(list)
    answered_by: dict[str, int] = defaultdict(int)
    tokens = 0
    samples = []
    for row in rows:
        if row["route"] not in ("knowledge", "data", "combined"):
            continue
        started = time.perf_counter()
        state = await graph.ainvoke(
            {"message": row["message"], "previous": None}, {"configurable": {"copilot": context}}
        )
        timings[state["plan"].route].append(time.perf_counter() - started)
        answered_by[f"{state['plan'].route}:{state['answer'].answered_by}"] += 1
        if llm is not None and len(samples) < 6 and state["plan"].route != "data":
            samples.append({"question": row["message"], "answer": state["answer"].text})
    if llm is not None and hasattr(llm, "get_num_tokens"):
        tokens = None  # providers report usage per call; see the provider's dashboard for exact counts
    return {
        "latency_ms": {
            route: {"p50": round(1000 * statistics.median(v)), "max": round(1000 * max(v))}
            for route, v in sorted(timings.items())
        },
        "answered_by": dict(sorted(answered_by.items())),
        "samples": samples,
        "tokens": tokens,
    }


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def report(m: dict) -> str:
    test, dev = m["routing"]["test"], m["routing"]["dev"]
    misses = (
        _table(
            ["Message", "Expected", "Got"], [[x["message"], x["expected"], x["got"]] for x in test["misses"]]
        )
        if test["misses"]
        else "None."
    )
    latency = _table(
        ["Route", "p50", "max"],
        [[r, f"{v['p50']} ms", f"{v['max']} ms"] for r, v in m["deterministic"]["latency_ms"].items()],
    )
    llm = "Not run (no LLM configured). Run with `--llm` and LLM_PROVIDER set to measure it."
    if m.get("llm"):
        e = m["llm"]
        llm = (
            f"Model: `{e['model']}`.\n\n"
            + _table(["Route: answered by", "Questions"], [[k, str(v)] for k, v in e["answered_by"].items()])
            + "\n\n"
            + _table(
                ["Route", "p50", "max"],
                [[r, f"{v['p50']} ms", f"{v['max']} ms"] for r, v in e["latency_ms"].items()],
            )
            + '\n\n"llm" means the model\'s answer passed the grounding check; "extractive" means it was '
            'rejected (or failed) and a cited passage was shown instead; "fixed" means the evidence was '
            "insufficient and the copilot said so. Cost: ₹0 on Groq's free tier (rate-limited).\n\n"
            + "\n\n".join(f"> **{s['question']}**\n>\n> {s['answer']}" for s in e["samples"])
        )
    gate = _table(["Check", "Result"], [[k, "pass" if ok else "**FAIL**"] for k, ok in m["gate"].items()])
    f, g = m["financial"], m["grounding"]
    return f"""# Financial Copilot: evaluation report

Generated by `python -m training.evaluate_copilot` on {m["generated_at"]}. Do not edit by hand.

## 1. Routing (knowledge / data / combined / action / small talk / unsupported)

| Set | Questions | Route accuracy | Route + tools accuracy |
|---|---|---|---|
| dev | {dev["questions"]} | {dev["route_accuracy"]:.3f} | {dev["tools_accuracy"]:.3f} |
| **test** | {test["questions"]} | **{test["route_accuracy"]:.3f}** | **{test["tools_accuracy"]:.3f}** |

Test accuracy by expected route: {", ".join(f"{k} {v:.2f}" for k, v in test["by_route"].items())}.

Test misses:

{misses}

## 2. Financial correctness

{f["checks"]} figures (totals, income, net, every category, both sides of each comparison) for
{m["financial_users"]} simulated users over four periods, against an independent integer-paise
calculation: **{f["failures"]} wrong** (correctness {f["financial_correctness"]:.6f}).

## 3. Grounding checks

On {g["good_answers"]} knowledge questions, a correct cited answer passed
{g["grounding_good_pass_rate"]:.1%} of the time, and **{g["grounding_catch_rate"]:.1%}** of
{g["planted_failures"]} planted failures were rejected (no citation, an unknown source, an invented
number, a copied user figure).

## 4. Latency without an LLM (routing, tools, retrieval, template or quoted answer)

{latency}

## 5. End to end with the LLM

{llm}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Financial Copilot.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--llm", action="store_true", help="also answer end to end with the configured LLM")
    args = parser.parse_args(argv)

    embedder = load_embedder(GTE_SMALL, DEFAULT_MODEL_DIR / "embeddings")
    store = InMemoryVectorStore()
    ingest(load_documents(DEFAULT_KNOWLEDGE_DIR), store, embedder)
    retriever = KnowledgeRetriever(store, embedder)
    dev, test = load("dev"), load("test")
    with open(DATA_DIR / "kb_finance_test.jsonl", encoding="utf-8") as lines:
        kb_questions = [
            json.loads(line)["question"] for line in lines if line.strip() and json.loads(line)["documents"]
        ]

    metrics: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "routing": {"dev": routing(dev), "test": routing(test)},
        "financial_users": 25,
        "financial": financial_correctness(25),
        "grounding": grounding(retriever, kb_questions),
        "deterministic": asyncio.run(end_to_end(test, retriever, None)),
    }
    if args.llm:
        from app.llm.provider import build_chat_model

        settings = Settings.from_env()
        llm = build_chat_model(settings)
        if llm is None:
            raise SystemExit("--llm needs LLM_PROVIDER (and its settings) in the environment")
        metrics["llm"] = {"model": settings.llm_model, **asyncio.run(end_to_end(test, retriever, llm))}

    test_routing = metrics["routing"]["test"]
    values = {
        "route_accuracy": test_routing["route_accuracy"],
        "tools_accuracy": test_routing["tools_accuracy"],
        "financial_correctness": metrics["financial"]["financial_correctness"],
        "grounding_catch_rate": metrics["grounding"]["grounding_catch_rate"],
        "grounding_good_pass_rate": metrics["grounding"]["grounding_good_pass_rate"],
    }
    metrics["gate"] = {
        f"{k} >= {floor} (got {values[k]:.4f})": values[k] >= floor for k, floor in FLOORS.items()
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    record_run(
        "copilot", args.report_dir, {"llm": bool(args.llm), "model": os.environ.get("LLM_MODEL")}, values
    )
    for name, value in values.items():
        print(f"{name:<26} {value}")
    print(f"reports: {args.report_dir}")
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
