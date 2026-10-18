"""Evaluate the insight detectors on simulated histories with known ground truth.

Usage (from ml-service/):
    python -m training.evaluate_insights           # evaluate and write reports/insights/
    python -m training.evaluate_insights --gate    # ...and fail if a check does not pass

Two independent groups of simulated users: validation users choose every threshold and
calibration constant, and test users score them. This is the same discipline as a train/test
split: a number measured on the data that chose it is optimistic.

- Unusual spending: precision, recall and F1 on injected spikes. The shipped detector is
  built up one idea at a time (an ablation) and compared with textbook baselines, each with its
  own threshold tuned on the validation users.
- Recurring payments: precision, recall and F1 of the detected series, plus period accuracy.
- Month-end forecast: a backtest at days 5, 10, 15, 20 and 25 of past months, using only the
  data available that day. It reports mean absolute percentage error (MAPE) against two
  baselines, and how often the 80% interval contains the actual total. The interval's widening
  factor is calibrated on validation users (split conformal prediction).
"""

from __future__ import annotations

import argparse
import calendar
import json
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

from app.ml import anomaly, forecast
from app.ml.anomaly import MIN_AMOUNT, candidate_expenses, find_anomalies, peer_groups
from app.ml.forecast import Z_80, forecast_month
from app.ml.recurring import find_recurring, merchant_key
from training.simulate_history import SimulatedUser, simulate_users

VALIDATION_SEED, TEST_SEED = 1, 2
END = date(2026, 10, 18)
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "insights"
AS_OF_DAYS = [5, 10, 15, 20, 25]
BACKTEST_MONTHS = 6
SHIPPED = "percentile ratio instead of z-score (shipped)"

Scorer = Callable[[SimulatedUser], dict[int, float]]  # transaction id -> anomaly score, eligible rows only


# ---------- Unusual spending ----------

def robust_zscores(values: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
    """0.6745 * (x - median) / MAD (Iglewicz and Hoaglin), with the median and MAD from `reference`."""
    reference = values if reference is None else reference
    median = np.median(reference)
    deviations = np.abs(reference - median)
    mad = np.median(deviations)
    if mad > 0:
        return 0.6745 * (values - median) / mad
    mean_deviation = deviations.mean()  # over half the values identical: use the mean deviation
    return (values - median) / (1.253314 * mean_deviation) if mean_deviation > 0 else np.zeros(len(values))


def _expenses_by_category(user: SimulatedUser) -> list[list[dict]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    for tx in user.transactions:
        if tx["type"] == "EXPENSE":
            groups[tx["category_id"]].append(tx)
    return [rows for rows in groups.values() if len(rows) >= 8]


def _eligible(rows: list[dict], scores) -> dict[int, float]:
    pairs = zip(rows, scores, strict=True)
    return {row["id"]: float(score) for row, score in pairs if row["amount"] >= MIN_AMOUNT}


def classic_z(user: SimulatedUser) -> dict[int, float]:
    scores = {}
    for rows in _expenses_by_category(user):
        amounts = np.array([row["amount"] for row in rows])
        if amounts.std() > 0:
            scores.update(_eligible(rows, (amounts - amounts.mean()) / amounts.std()))
    return scores


def robust_z_raw(user: SimulatedUser) -> dict[int, float]:
    scores = {}
    for rows in _expenses_by_category(user):
        scores.update(_eligible(rows, robust_zscores(np.array([row["amount"] for row in rows]))))
    return scores


def isolation_forest(user: SimulatedUser) -> dict[int, float]:
    scores = {}
    for rows in _expenses_by_category(user):
        log_amounts = np.log([[row["amount"]] for row in rows])
        model = IsolationForest(n_estimators=50, random_state=0).fit(log_amounts)
        # score_samples is lower for outliers; negate it so higher means more anomalous
        outlier_scores = -model.score_samples(log_amounts)
        above_median = log_amounts[:, 0] > np.median(log_amounts)  # only unusually high payments
        high_rows = [row for row, high in zip(rows, above_median, strict=True) if high]
        scores.update(_eligible(high_rows, outlier_scores[above_median]))
    return scores


def robust_z_groups(merchant_first: bool, exclude_recurring: bool) -> Scorer:
    """Robust z of log amounts over the shipped detector's peer groups, for the ablation."""
    def score(user: SimulatedUser) -> dict[int, float]:
        expenses = candidate_expenses(user.transactions, exclude_recurring)
        log_amounts = np.log([tx["amount"] for tx in expenses])
        scores = {}
        for group in peer_groups(expenses, merchant_first):
            z = robust_zscores(log_amounts[group.judged], log_amounts[group.baseline])
            scores.update(_eligible([expenses[i] for i in group.judged], z))
        return scores
    return score


def percentile_ratio(user: SimulatedUser) -> dict[int, float]:
    return {a.transaction_id: a.ratio for a in find_anomalies(user.transactions, min_ratio=0)}


Z_GRID = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
ANOMALY_METHODS: dict[str, tuple[Scorer, list[float]]] = {
    "z-score on amounts, per category": (classic_z, [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
    "robust z on amounts, per category": (robust_z_raw, [3.5, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0]),
    "Isolation Forest on log amounts, per category": (
        isolation_forest, [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]),
    "robust z on log amounts, per category": (robust_z_groups(False, False), Z_GRID),
    "+ merchant's own history first": (robust_z_groups(True, False), Z_GRID),
    "+ recurring payments left out": (robust_z_groups(True, True), Z_GRID),
    SHIPPED: (percentile_ratio, [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]),
}


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "true_positives": tp, "false_positives": fp, "false_negatives": fn}


def _anomaly_metrics(scored: list[tuple[dict[int, float], set[int]]], threshold: float) -> dict:
    tp = fp = fn = 0
    for scores, truth in scored:
        flagged = {tx_id for tx_id, score in scores.items() if score >= threshold}
        tp, fp, fn = tp + len(flagged & truth), fp + len(flagged - truth), fn + len(truth - flagged)
    return _prf(tp, fp, fn)


def evaluate_anomalies(validation: list[SimulatedUser], test: list[SimulatedUser]) -> dict:
    results = {}
    for name, (scorer, grid) in ANOMALY_METHODS.items():
        validation_scored = [(scorer(user), user.anomaly_ids) for user in validation]
        best = max(grid, key=lambda t: _anomaly_metrics(validation_scored, t)["f1"])
        test_scored = [(scorer(user), user.anomaly_ids) for user in test]
        results[name] = {"threshold": best, **_anomaly_metrics(test_scored, best)}
        if name == SHIPPED:
            results[name]["shipped_threshold"] = anomaly.MIN_RATIO
            results[name]["at_shipped_threshold"] = _anomaly_metrics(test_scored, anomaly.MIN_RATIO)
            results[name]["validation_curve"] = {str(t): _anomaly_metrics(validation_scored, t) for t in grid}
        print(f"  anomalies  {name:<48} threshold {best:<5} test F1 {results[name]['f1']:.3f}")
    return results


# ---------- Recurring payments ----------

def evaluate_recurring(test: list[SimulatedUser]) -> dict:
    tp = fp = fn = period_correct = 0
    for user in test:
        truth = {merchant_key(title): period for title, period in user.recurring.items()}
        found = {series.key: series.period for series in find_recurring(user.transactions)}
        matched = truth.keys() & found.keys()
        tp += len(matched)
        fp += len(found.keys() - truth.keys())
        fn += len(truth.keys() - found.keys())
        period_correct += sum(truth[key] == found[key] for key in matched)
    result = _prf(tp, fp, fn)
    result["period_accuracy"] = round(period_correct / tp, 4) if tp else 0.0
    print(f"  recurring  test F1 {result['f1']:.3f}  period accuracy {result['period_accuracy']:.3f}")
    return result


# ---------- Month-end forecast ----------

def _month_total(transactions: list[dict], year: int, month: int) -> float:
    prefix = f"{year:04d}-{month:02d}"
    return sum(
        tx["amount"] for tx in transactions if tx["type"] == "EXPENSE" and tx["date"].startswith(prefix)
    )


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def backtest(users: list[SimulatedUser]) -> list[dict]:
    """One row per (user, month, as-of day): the actual total and every method's prediction."""
    months, (year, month) = [], _previous_month(END.year, END.month)
    for _ in range(BACKTEST_MONTHS):
        months.append((year, month))
        year, month = _previous_month(year, month)

    rows = []
    for user in users:
        for year, month in months:
            actual = _month_total(user.transactions, year, month)
            last_month = _month_total(user.transactions, *_previous_month(year, month))
            days_in_month = calendar.monthrange(year, month)[1]
            for day in AS_OF_DAYS:
                today = date(year, month, day)
                known = [tx for tx in user.transactions if tx["date"] <= today.isoformat()]
                anomalies = {a.transaction_id for a in find_anomalies(known)}
                result = forecast_month(known, today, exclude_ids=anomalies, budget=user.monthly_budget)
                if result is None:
                    continue
                rows.append({
                    "day": day, "actual": actual, "forecast": result,
                    "predictions": {
                        "last month's total": last_month,
                        "run-rate (spent / days so far)": result.spent_to_date / day * days_in_month,
                        "shipped": result.projected_total,
                    },
                })
    return rows


def evaluate_forecast(validation: list[SimulatedUser], test: list[SimulatedUser]) -> dict:
    # Split conformal calibration: how many textbook standard deviations cover 80% of validation errors
    textbook_errors = []
    for row in backtest(validation):
        textbook_sd = max(row["forecast"].sd / forecast.SD_INFLATION, 1.0)
        textbook_errors.append(abs(row["actual"] - row["forecast"].projected_total) / textbook_sd)
    calibrated_inflation = float(np.quantile(textbook_errors, 0.8)) / Z_80

    rows = backtest(test)
    result: dict = {"mape": {}, "mape_by_day": {}}
    for name in rows[0]["predictions"]:
        errors_by_day: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            errors_by_day[row["day"]].append(abs(row["predictions"][name] - row["actual"]) / row["actual"])
        every = [error for errors in errors_by_day.values() for error in errors]
        result["mape"][name] = round(statistics.fmean(every), 4)
        result["mape_by_day"][name] = {
            str(day): round(statistics.fmean(errors_by_day[day]), 4) for day in AS_OF_DAYS
        }
        print(f"  forecast   {name:<32} test MAPE {result['mape'][name]:.3f}")
    inside = [row["forecast"].low <= row["actual"] <= row["forecast"].high for row in rows]
    result["interval_coverage"] = round(statistics.fmean(inside), 4)
    result["sd_inflation"] = {"calibrated_on_validation": round(calibrated_inflation, 3),
                              "shipped": forecast.SD_INFLATION}
    result["cases"] = len(rows)
    print(f"  forecast   80% interval coverage {result['interval_coverage']:.1%}"
          f" (SD inflation: calibrated {calibrated_inflation:.2f}, shipped {forecast.SD_INFLATION})")
    return result


# ---------- Report ----------

def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def report(metrics: dict) -> str:
    anomalies, recurring, fc = metrics["anomalies"], metrics["recurring"], metrics["forecast"]
    shipped = anomalies[SHIPPED]
    anomaly_table = _table(
        ["Method", "Threshold", "Precision", "Recall", "F1"],
        [[name, str(s["threshold"]), f"{s['precision']:.3f}", f"{s['recall']:.3f}", f"**{s['f1']:.3f}**"]
         for name, s in anomalies.items()],
    )
    curve_table = _table(
        ["At least ... the usual top payment", "Precision", "Recall", "F1"],
        [[f"{t}x", f"{c['precision']:.3f}", f"{c['recall']:.3f}", f"{c['f1']:.3f}"]
         for t, c in shipped["validation_curve"].items()],
    )
    recurring_table = _table(
        ["Precision", "Recall", "F1", "Period accuracy"],
        [[f"{recurring[k]:.3f}" for k in ("precision", "recall", "f1", "period_accuracy")]],
    )
    forecast_table = _table(
        ["Method", "Overall", *[f"Day {day}" for day in AS_OF_DAYS]],
        [[name, f"**{fc['mape'][name]:.1%}**", *[f"{v:.1%}" for v in fc["mape_by_day"][name].values()]]
         for name in fc["mape"]],
    )
    gate_table = _table(
        ["Check (test users)", "Result"],
        [[name, "pass" if ok else "**FAIL**"] for name, ok in metrics["gate"].items()],
    )
    true_series = recurring["true_positives"] + recurring["false_negatives"]
    users, days = metrics["users_per_group"], ", ".join(map(str, AS_OF_DAYS))
    return f"""# Insight detectors: evaluation report

Generated by `python -m training.evaluate_insights` on {metrics['generated_at']}. Do not edit by hand.

{users} simulated validation users choose every threshold and constant; {users} different
simulated test users score them. Each user has a year of transactions.

## Unusual spending

{metrics['test_anomalies']} injected spikes among the test users' payments, each 5-15x the top of the user's
normal range at that merchant. Every method's threshold was tuned on the validation users. The last four
rows build the shipped detector one idea at a time.

{anomaly_table}

How the shipped threshold was chosen, on the validation users (it ships at {shipped['shipped_threshold']}x):

{curve_table}

Caveat: the simulator defines a spike relative to the top of the normal range, which is close to what
the percentile ratio measures, so its near-perfect score is an upper bound. The comparison between
methods is the informative part. On real data, the rate at which users dismiss alerts is the metric
to watch.

## Recurring payments

{true_series} true series (weekly, every 28 days, monthly) with varying titles, among everyday spending
at the same merchants.

{recurring_table}

## Month-end forecast

A backtest over the last {BACKTEST_MONTHS} complete months: forecasts on days {days},
using only the data available that day ({fc['cases']} forecasts). Mean absolute percentage error, lower
is better:

{forecast_table}

The 80% interval contained the actual month total in **{fc['interval_coverage']:.1%}** of test forecasts.
Its standard deviation is widened {fc['sd_inflation']['shipped']}x; calibration on the validation users
suggested {fc['sd_inflation']['calibrated_on_validation']}x.

## Evaluation gate

{gate_table}
"""


def gate_checks(metrics: dict) -> dict[str, bool]:
    anomaly_f1 = metrics["anomalies"][SHIPPED]["at_shipped_threshold"]["f1"]
    recurring_f1 = metrics["recurring"]["f1"]
    mape = metrics["forecast"]["mape"]
    gain = min(value for name, value in mape.items() if name != "shipped") - mape["shipped"]
    coverage = metrics["forecast"]["interval_coverage"]
    return {
        f"unusual-spending F1 >= 0.95 (got {anomaly_f1:.3f})": anomaly_f1 >= 0.95,
        f"recurring-payment F1 >= 0.95 (got {recurring_f1:.3f})": recurring_f1 >= 0.95,
        f"forecast MAPE >= 10 points below the better baseline (got {gain:.3f})": gain >= 0.10,
        f"80% interval covers 75-85% of actual totals (got {coverage:.3f})": 0.75 <= coverage <= 0.85,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the insight detectors on simulated users.")
    parser.add_argument("--users", type=int, default=100, help="simulated users in each group")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gate", action="store_true", help="exit with an error if a check does not pass")
    args = parser.parse_args(argv)

    validation = simulate_users(args.users, END, seed=VALIDATION_SEED)
    test = simulate_users(args.users, END, seed=TEST_SEED)
    print(f"{args.users} validation and {args.users} test users")
    metrics = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "users_per_group": args.users,
        "test_anomalies": sum(len(user.anomaly_ids) for user in test),
        "anomalies": evaluate_anomalies(validation, test),
        "recurring": evaluate_recurring(test),
        "forecast": evaluate_forecast(validation, test),
    }
    metrics["gate"] = gate_checks(metrics)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    print(f"reports: {args.report_dir}")

    failures = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failures:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
