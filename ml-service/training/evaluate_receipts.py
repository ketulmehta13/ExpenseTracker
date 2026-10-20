"""Evaluate bill parsing (merchant, date, total, items, item groups) on bill text.

Usage (from ml-service/):
    python -m training.evaluate_receipts           # evaluate and write reports/receipts/
    python -m training.evaluate_receipts --gate    # ...and fail if the test set misses a floor

Two sets, relative to a fixed "today" (Monday 19 October 2026):
- dev: 60 bills from training/receipt_samples.py (six layouts, OCR-style noise). The rules were
  developed against these, so a high score here proves little.
- test: 16 bills written by hand before any evaluation, never used to change the rules: other
  stores and layouts, abbreviated item names, OCR look-alikes, and traps such as a product
  called "Lifebuoy Total", "Total (Incl. GST)" and a rounded amount below "Net Payable".
  Every test failure is listed in the report.

This measures the parsing step on text. `evaluate_receipt_ocr` measures the whole pipeline on
rendered photos. A naive baseline shows what the rules add: the first line as the merchant, the
first date, the largest number as the total, and every line ending in a number as an item.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from rapidfuzz import fuzz

from app.receipts.items import group_items
from app.receipts.parse import amounts_in, dates_in, fix_digits, parse_receipt
from training.runs import record_run

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "receipts"
TODAY = date(2026, 10, 19)
CATEGORIES = [  # the live defaults
    {"id": i, "name": name, "user_id": None}
    for i, name in enumerate(
        ["Entertainment", "Food", "Other", "Rent", "Salary", "Shopping", "Travel", "Utilities"], 1
    )
]
# Below what the test set reaches, so ordinary changes pass and real regressions fail
FLOORS = {"total": 0.85, "date": 0.9, "merchant": 0.85, "item_f1": 0.8, "group_accuracy": 0.8}
FIELDS = [
    ("merchant", "Merchant"),
    ("date", "Date"),
    ("total", "Total"),
    ("all_three", "Merchant + date + total"),
    ("item_precision", "Items, precision"),
    ("item_recall", "Items, recall"),
    ("item_f1", "Items, F1"),
    ("group_accuracy", "Item groups, accuracy"),
]


def load(split: str) -> list[dict]:
    with open(DATA_DIR / f"receipts_{split}.jsonl", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _same_merchant(got: str | None, want: str | None) -> bool:
    if not got or not want:
        return got == want
    clean = lambda text: re.sub(r"[^a-z0-9]", "", text.lower())  # noqa: E731
    return clean(got) == clean(want) or fuzz.ratio(clean(got), clean(want)) >= 90


def naive_parse(lines: list[str]) -> dict:
    fixed = [fix_digits(line) for line in lines]
    dates = [found for line in fixed for found in dates_in(line, TODAY)]
    amounts = [amount.value for line in fixed for amount in amounts_in(line)]
    items = []
    for line in fixed:
        found = amounts_in(line)
        if found and found[-1].start > 0 and any(char.isalpha() for char in line[: found[-1].start]):
            items.append(
                {"name": line[: found[-1].start].strip(), "amount": found[-1].value, "group": "groceries"}
            )
    return {
        "merchant": lines[0] if lines else None,
        "date": dates[0] if dates else None,
        "total": max(amounts) if amounts else None,
        "items": items,
    }


def rules_parse(lines: list[str]) -> dict:
    draft = parse_receipt(lines, TODAY)
    groups, _, _ = group_items(draft.items, draft.total, CATEGORIES, draft.merchant, lines)
    items = [
        {"name": item.name, "amount": item.amount, "group": item.group}
        for group in groups
        for item in group.items
    ]
    return {"merchant": draft.merchant, "date": draft.date, "total": draft.total, "items": items}


def _match_items(got: list[dict], want: list[dict]) -> list[tuple[dict, dict]]:
    """Pair predicted and gold items: the same amount and a similar name."""
    pairs, free = [], list(want)
    for item in got:
        candidates = [
            gold
            for gold in free
            if abs(gold["amount"] - item["amount"]) <= 0.01
            and fuzz.token_set_ratio(gold["name"].lower(), item["name"].lower()) >= 60
        ]
        if candidates:
            best = max(
                candidates, key=lambda gold: fuzz.token_set_ratio(gold["name"].lower(), item["name"].lower())
            )
            free.remove(best)
            pairs.append((item, best))
    return pairs


def score(rows: list[dict], parse) -> tuple[dict, list[dict]]:
    counts = {"merchant": 0, "date": 0, "total": 0, "all_three": 0}
    got_items = want_items = matched = grouped_right = 0
    failures = []
    for row in rows:
        result = parse(row["lines"])
        checks = {
            "merchant": _same_merchant(result["merchant"], row["merchant"]),
            "date": result["date"] is not None and result["date"].isoformat() == row["date"],
            "total": result["total"] is not None and abs(result["total"] - row["total"]) <= 0.01,
        }
        checks["all_three"] = all(checks.values())
        for key, ok in checks.items():
            counts[key] += ok
        pairs = _match_items(result["items"], row["items"])
        got_items += len(result["items"])
        want_items += len(row["items"])
        matched += len(pairs)
        wrong_groups = [
            (item["name"], item["group"], gold["group"])
            for item, gold in pairs
            if item["group"] != gold["group"]
        ]
        grouped_right += len(pairs) - len(wrong_groups)
        if (
            not checks["all_three"]
            or len(pairs) < max(len(row["items"]), len(result["items"]))
            or wrong_groups
        ):
            failures.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "wrong": [key for key in ("merchant", "date", "total") if not checks[key]],
                    "got": {
                        "merchant": result["merchant"],
                        "date": str(result["date"]),
                        "total": result["total"],
                    },
                    "want": {"merchant": row["merchant"], "date": row["date"], "total": row["total"]},
                    "items": f"{len(pairs)} matched of {len(row['items'])} expected, "
                    f"{len(result['items'])} found",
                    "wrong_groups": wrong_groups,
                }
            )
    n = len(rows)
    precision = matched / got_items if got_items else 1.0
    recall = matched / want_items if want_items else 1.0
    metrics = {key: round(value / n, 4) for key, value in counts.items()}
    metrics.update(
        {
            "item_precision": round(precision, 4),
            "item_recall": round(recall, 4),
            "item_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
            "group_accuracy": round(grouped_right / matched, 4) if matched else 0.0,
            "bills": n,
        }
    )
    return metrics, failures


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def report(metrics: dict) -> str:
    def cell(split, parser, key):
        return f"{metrics[split][parser][key]:.1%}"

    results = _table(
        ["Field", "Dev: naive", "Dev: rules", "Test: naive", "**Test: rules**"],
        [
            [
                label,
                cell("dev", "naive", key),
                cell("dev", "rules", key),
                cell("test", "naive", key),
                f"**{cell('test', 'rules', key)}**",
            ]
            for key, label in FIELDS
        ],
    )
    rows = []
    for failure in metrics["test_failures"]:
        fields = (
            "; ".join(
                f"{key}: got {failure['got'][key]!r}, want {failure['want'][key]!r}"
                for key in failure["wrong"]
            )
            or "–"
        )
        groups = (
            "; ".join(f"{name}: {got} (want {want})" for name, got, want in failure["wrong_groups"]) or "–"
        )
        rows.append([failure["id"], failure["kind"], fields, failure["items"], groups])
    failures = _table(["Bill", "Kind", "Wrong fields", "Items", "Wrong groups"], rows) if rows else "None."
    gate = _table(
        ["Check (test set)", "Result"],
        [[name, "pass" if ok else "**FAIL**"] for name, ok in metrics["gate"].items()],
    )
    return f"""# Bill parsing: evaluation report

Generated by `python -m training.evaluate_receipts` on {metrics["generated_at"]}. Do not edit by hand.

{metrics["dev"]["rules"]["bills"]} dev bills (generated, used while writing the rules) and
{metrics["test"]["rules"]["bills"]} test bills (written by hand before any evaluation, never used to tune the
rules), relative to {TODAY:%A %d %B %Y}. Items count as found when the amount matches and the name is similar;
groups are scored on found items. The naive baseline takes the first line as the merchant, the first date, the
largest number as the total, and every line ending in a number as an item.

{results}

## Every test failure

{failures}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate bill parsing on bill text.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gate", action="store_true", help="fail if the test set misses a floor")
    args = parser.parse_args(argv)

    metrics: dict = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    for split in ("dev", "test"):
        rows = load(split)
        metrics[split] = {"naive": score(rows, naive_parse)[0]}
        metrics[split]["rules"], failures = score(rows, rules_parse)
        if split == "test":
            metrics["test_failures"] = failures
        summary = "  ".join(f"{key} {metrics[split]['rules'][key]:.3f}" for key, _ in FIELDS)
        print(f"{split:<5} {summary}")
    test = metrics["test"]["rules"]
    metrics["gate"] = {
        f"{name} >= {floor} (got {test[name]:.3f})": test[name] >= floor for name, floor in FLOORS.items()
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    print(f"reports: {args.report_dir}")
    record_run(
        "receipts",
        args.report_dir,
        {"floors": FLOORS},
        {key: test[key] for key in ("merchant", "date", "total", "item_f1", "group_accuracy")},
    )
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
