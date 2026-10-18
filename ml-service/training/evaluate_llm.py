"""Evaluate the LLM features against a real model. Needs one: CI tests the guardrails with fakes.

Usage (from ml-service/), for example with a local Ollama model:
    ollama pull qwen2.5:3b
    LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:3b python -m training.evaluate_llm

1. Quick add: the quick-add test sentences with the rules alone, then with the LLM fallback.
   The fallback is only asked when the rules look unsure, and only checked values are used.
2. Monthly summary: for simulated users' real months, how often the model's summary passes
   the placeholder check (no digits of its own, only known placeholders), and how long it takes.
   A rejected summary falls back to the template, so this measures quality, not safety.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.llm.extract import checked_fields, llm_draft, merge, needs_llm
from app.llm.provider import build_chat_model
from app.llm.summary import month_facts, summarize
from app.nlp.quickadd import parse_quick_add
from app.routers.insights import build_insights
from training.evaluate_quickadd import TODAY, load, score
from training.simulate_history import CATEGORY_IDS, simulate_users

DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "llm"


def hybrid_parser(model, timeout: float):
    """The /v1/parse logic as a plain function: rules, then the checked LLM fallback when unsure."""
    def parse(text, today):
        parsed = parse_quick_add(text, today)
        if needs_llm(parsed):
            draft = asyncio.run(llm_draft(model, text, today, timeout))
            if draft is not None:
                parsed, _ = merge(parsed, checked_fields(draft, text, today))
        return parsed
    return parse


def evaluate_summaries(model, timeout: float, users: int) -> dict:
    categories = [{"id": category_id, "name": name.title()} for name, category_id in CATEGORY_IDS.items()]
    sources, seconds, examples = Counter(), [], []
    for user in simulate_users(users, TODAY, seed=21):
        insights = build_insights(user.transactions, categories, user.monthly_budget, TODAY)
        facts = month_facts(user.transactions, categories, insights, TODAY)
        started = time.perf_counter()
        text, source = asyncio.run(summarize(model, facts, timeout))
        seconds.append(time.perf_counter() - started)
        sources[source] += 1
        if source == "llm" and len(examples) < 3:
            examples.append(text)
    return {
        "users": users,
        "accepted_rate": round(sources["llm"] / users, 4),
        "median_seconds": round(statistics.median(seconds), 2),
        "examples": examples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the LLM features with the configured model.")
    parser.add_argument("--users", type=int, default=20, help="simulated users for the summary test")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    model = build_chat_model(settings)
    if model is None:
        print("No LLM configured. Set LLM_PROVIDER (ollama or openai) and LLM_MODEL first.")
        return 2

    rows = load("test")
    rules, _ = score(rows, parse_quick_add, None)
    hybrid, failures = score(rows, hybrid_parser(model, settings.llm_timeout_seconds), None)
    metrics = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "quickadd": {"rules": rules, "rules_plus_llm": hybrid, "failures": failures},
        "summary": evaluate_summaries(model, settings.llm_timeout_seconds, args.users),
    }
    fields = ("amount", "date", "type", "title_f1", "all_fields")
    for name in ("rules", "rules_plus_llm"):
        print(f"quick add, {name:<15}" + "  ".join(f"{f} {metrics['quickadd'][name][f]:.3f}" for f in fields))
    summary = metrics["summary"]
    print(f"summaries accepted {summary['accepted_rate']:.0%}, median {summary['median_seconds']}s")

    args.report_dir.mkdir(parents=True, exist_ok=True)
    report = json.dumps(metrics, indent=2, default=str) + "\n"
    (args.report_dir / "metrics.json").write_text(report, encoding="utf-8")
    print(f"report: {args.report_dir / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
