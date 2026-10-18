"""Evaluate the quick-add parser on hand-labelled sentences.

Usage (from ml-service/):
    python -m training.evaluate_quickadd           # evaluate and write reports/quickadd/
    python -m training.evaluate_quickadd --gate    # ...and fail if the test set misses a floor

Two hand-written sets, relative to a fixed "today" (Sunday 18 October 2026):
- dev: the sentences the rules were developed against. A high score here is expected and
  proves little.
- test: written before the parser and never used to change it. This is the honest number,
  and every test failure is listed in the report.

Each slot is scored separately (entity-level evaluation): amount, date and type by exact
match, the title by token-level F1 (as in SQuAD), so "Groceries dmart" against "Groceries at
dmart" earns partial credit. A naive baseline (first number = amount, today, expense) shows
what the rules add. When a trained categorizer is present, the category it picks from the
parsed title is scored too.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import DEFAULT_MODEL_DIR
from app.ml.categorizer import CategorizerModel
from app.nlp.quickadd import ParsedEntry, parse_quick_add

TODAY = date(2026, 10, 18)
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "quickadd"
FLOORS = {"amount": 0.95, "date": 0.90, "type": 0.90, "title_f1": 0.85}  # on the test set


def load(name: str) -> list[dict]:
    with open(DATA_DIR / f"quickadd_{name}.jsonl", encoding="utf-8") as lines:
        return [json.loads(line) for line in lines if line.strip()]


def naive_parse(text: str, today: date) -> ParsedEntry:
    """Baseline: the first number is the amount, the rest is the title; today; an expense."""
    match = re.search(r"\d+(?:\.\d+)?", text)
    title = f"{text[:match.start()]} {text[match.end():]}" if match else text
    return ParsedEntry(" ".join(title.split()), float(match[0]) if match else None, today, "EXPENSE")


def token_f1(predicted: str, gold: str) -> float:
    predicted_tokens, gold_tokens = predicted.lower().split(), gold.lower().split()
    common = sum((Counter(predicted_tokens) & Counter(gold_tokens)).values())
    if not predicted_tokens or not gold_tokens or not common:
        return float(predicted_tokens == gold_tokens)
    precision, recall = common / len(predicted_tokens), common / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def score(rows: list[dict], parser, model: CategorizerModel | None) -> tuple[dict, list[dict]]:
    names = ("amount", "date", "type", "title_exact", "title_f1", "all_fields", "category")
    checks: dict[str, list[float]] = {name: [] for name in names}
    failures = []
    for row in rows:
        parsed = parser(row["text"], TODAY)
        result = {
            "amount": parsed.amount is not None and abs(parsed.amount - row["amount"]) < 0.005,
            "date": parsed.date.isoformat() == row["date"],
            "type": parsed.type == row["type"],
            "title_exact": parsed.title.lower() == row["title"].lower(),
        }
        result["all_fields"] = all(result.values())
        for name, ok in result.items():
            checks[name].append(float(ok))
        checks["title_f1"].append(token_f1(parsed.title, row["title"]))
        predicted_label = None
        if model is not None and row.get("label"):
            predicted_label = model.predict(parsed.title, parsed.amount, parsed.type).label
            checks["category"].append(float(predicted_label == row["label"]))
        if not result["all_fields"]:
            failures.append({
                "text": row["text"],
                "wrong": [name for name in ("amount", "date", "type", "title_exact") if not result[name]],
                "got": {"title": parsed.title, "amount": parsed.amount, "date": parsed.date.isoformat(),
                        "type": parsed.type},
                "want": {key: row[key] for key in ("title", "amount", "date", "type")},
            })
    metrics = {name: round(statistics.fmean(values), 4) for name, values in checks.items() if values}
    metrics["rows"] = len(rows)
    return metrics, failures


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


FIELDS = [("amount", "Amount"), ("date", "Date"), ("type", "Type"), ("title_exact", "Title, exact"),
          ("title_f1", "Title, token F1"), ("all_fields", "Whole entry right"), ("category", "Category")]


def report(metrics: dict) -> str:
    def cell(split: str, parser: str, field: str) -> str:
        value = metrics[split][parser].get(field)
        return "–" if value is None else f"{value:.1%}"

    results = _table(
        ["Field", "Dev: naive", "Dev: rules", "Test: naive", "**Test: rules**"],
        [[label, cell("dev", "naive", key), cell("dev", "rules", key), cell("test", "naive", key),
          f"**{cell('test', 'rules', key)}**"] for key, label in FIELDS],
    )
    failure_rows = [
        [f"`{f['text']}`", ", ".join(f["wrong"]),
         "; ".join(f"{k} {f['got'][k]!r}" for k in ("title", "amount", "date", "type")
                   if f["got"][k] != f["want"][k] and k + ("_exact" if k == "title" else "") in f["wrong"]),
         "; ".join(f"{k} {f['want'][k]!r}" for k in ("title", "amount", "date", "type")
                   if k + ("_exact" if k == "title" else "") in f["wrong"])]
        for f in metrics["test_failures"]
    ]
    failures = _table(["Input", "Wrong", "Got", "Expected"], failure_rows) if failure_rows else "None."
    gate = _table(["Check (test set)", "Result"],
                  [[name, "pass" if ok else "**FAIL**"] for name, ok in metrics["gate"].items()])
    dev_rows, test_rows = metrics["dev"]["rules"]["rows"], metrics["test"]["rules"]["rows"]
    return f"""# Quick-add parser: evaluation report

Generated by `python -m training.evaluate_quickadd` on {metrics['generated_at']}. Do not edit by hand.

{dev_rows} dev sentences (used while writing the rules) and {test_rows} test sentences (written first,
never used to change the rules), relative to {TODAY:%A %d %B %Y}. The naive baseline takes the first number
as the amount, today as the date and every entry as an expense. "Category" is the trained categorizer's
label for the parsed title, on sentences that have a gold label.

{results}

## Every test failure

{failures}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the quick-add parser.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--gate", action="store_true", help="fail if the test set misses a floor")
    args = parser.parse_args(argv)

    model = CategorizerModel.load(args.model_dir)
    metrics: dict = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    for split in ("dev", "test"):
        rows = load(split)
        metrics[split] = {"naive": score(rows, naive_parse, model)[0]}
        metrics[split]["rules"], failures = score(rows, parse_quick_add, model)
        if split == "test":
            metrics["test_failures"] = failures
        summary = "  ".join(f"{key} {metrics[split]['rules'].get(key, 0):.3f}" for key, _ in FIELDS)
        print(f"{split:<5} {summary}")
    test = metrics["test"]["rules"]
    metrics["gate"] = {
        f"{name} >= {floor} (got {test[name]:.3f})": test[name] >= floor for name, floor in FLOORS.items()
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    print(f"reports: {args.report_dir}")
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
