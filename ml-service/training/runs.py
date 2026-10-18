"""A lightweight experiment log: every training or evaluation run appends one line.

Each reports/<kind>/runs.jsonl line records what ran, when, on which git commit, with which
parameters, and the headline metrics, so a regression can be traced to the commit that
caused it. `python -m training.runs` prints the recent history across all of them.

MLflow does this (and much more) for teams; for one service a JSON-lines file per kind is
enough and has no server to run. The logs are local and git-ignored; CI keeps its own copy
with the uploaded reports.

Usage (from ml-service/):  python -m training.runs [--kind rag] [--last 10]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                timeout=5, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def record_run(kind: str, report_dir: Path, params: dict, metrics: dict) -> dict:
    """Append one run to report_dir/runs.jsonl and return it."""
    run = {
        "id": uuid4().hex[:8],
        "kind": kind,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": git_commit(),
        "params": params,
        "metrics": metrics,
    }
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(report_dir) / "runs.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(run) + "\n")
    return run


def load_runs(reports_dir: Path = REPORTS_DIR) -> list[dict]:
    runs = []
    for path in Path(reports_dir).glob("*/runs.jsonl"):
        runs += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(runs, key=lambda run: run["at"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show recent training and evaluation runs.")
    parser.add_argument("--kind", help="only this kind, e.g. categorizer, insights, quickadd, rag, assistant")
    parser.add_argument("--last", type=int, default=10)
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)

    runs = [run for run in load_runs(args.reports_dir) if not args.kind or run["kind"] == args.kind]
    if not runs:
        print("No runs recorded yet.")
        return 0
    for run in runs[-args.last:]:
        metrics = "  ".join(f"{name} {value:.3f}" if isinstance(value, float) else f"{name} {value}"
                            for name, value in run["metrics"].items())
        print(f"{run['at']}  {run['commit'] or '-':<8} {run['kind']:<12} {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
