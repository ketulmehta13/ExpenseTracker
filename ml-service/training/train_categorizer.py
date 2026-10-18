"""Train, evaluate and save the transaction categorizer.

Usage (from ml-service/):
    python -m training.train_categorizer                        # train, evaluate, save
    python -m training.train_categorizer --min-holdout-f1 0.8   # ...and fail below that score

Steps:
1. Generate synthetic titles and split them by template, so every test title comes from a
   phrase the model never saw. A random split puts near-duplicates on both sides and
   measures memorisation; the script reports that inflated number too, for comparison.
2. Choose the regularisation strength C by grouped cross-validation on the training split.
3. Compare models on the same split: majority class -> words only -> words + characters ->
   the full model with amount and type. Each addition has to earn its place.
4. Choose the confidence threshold from out-of-fold predictions: the lowest threshold at
   which suggestions are at least 90% correct. Below it the app shows no suggestion.
5. Refit on all synthetic data, score the hand-written holdout set (realistic titles and
   merchants the generator never uses), write the reports and save the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, cross_val_predict, train_test_split

from app.config import DEFAULT_MODEL_DIR
from app.ml.categorizer import CategorizerModel, build_pipeline, to_frame
from training.generate_data import generate_dataset
from training.runs import record_run

SEED = 42
HOLDOUT_PATH = Path(__file__).resolve().parent / "data" / "holdout_real.csv"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "categorizer"
C_GRID = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
TARGET_PRECISION = 0.90
CURVE_THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def features(frame: pd.DataFrame) -> pd.DataFrame:
    return to_frame(frame["title"], frame["amount"], frame["type"])


def grouped_split(data: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out about 20% of the templates, balanced across labels."""
    folds = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    train_idx, test_idx = next(folds.split(data, data["label"], groups=data["template_id"]))
    return data.iloc[train_idx].reset_index(drop=True), data.iloc[test_idx].reset_index(drop=True)


def confidence_and_correct(probabilities: np.ndarray, classes: np.ndarray, y: np.ndarray):
    return probabilities.max(axis=1), classes[probabilities.argmax(axis=1)] == y


def precision_coverage(confidence: np.ndarray, correct: np.ndarray, threshold: float) -> dict:
    """Coverage: share of inputs that get a suggestion. Precision: share of suggestions that are right."""
    shown = confidence >= threshold
    return {
        "coverage": round(float(shown.mean()), 4),
        "precision": round(float(correct[shown].mean()), 4) if shown.any() else None,
    }


def choose_threshold(confidence: np.ndarray, correct: np.ndarray, target_precision: float) -> float:
    """The lowest threshold meeting the precision target, which keeps coverage as high as possible."""
    for threshold in np.round(np.arange(0.20, 0.96, 0.05), 2):
        shown = confidence >= threshold
        if shown.any() and correct[shown].mean() >= target_precision:
            return float(threshold)
    return 0.95


def expected_calibration_error(confidence: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    """How far confidence is from accuracy, averaged over confidence bins (0 = perfectly calibrated).

    A calibrated model that says "80%" is right 80% of the time, which is what makes a
    probability threshold meaningful.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        in_bin = (confidence > low) & (confidence <= high)
        if in_bin.any():
            error += in_bin.mean() * abs(correct[in_bin].mean() - confidence[in_bin].mean())
    return round(float(error), 4)


def evaluate(model, frame: pd.DataFrame, threshold: float | None = None) -> dict:
    X, y = features(frame), frame["label"].to_numpy()
    predicted = model.predict(X)
    result = {
        "rows": len(frame),
        "accuracy": round(float(accuracy_score(y, predicted)), 4),
        "macro_f1": round(float(f1_score(y, predicted, average="macro", zero_division=0)), 4),
    }
    if threshold is not None:
        confidence, correct = confidence_and_correct(model.predict_proba(X), model.classes_, y)
        result["ece"] = expected_calibration_error(confidence, correct)
        result["mean_confidence"] = round(float(confidence.mean()), 4)
        result["at_threshold"] = precision_coverage(confidence, correct, threshold)
        result["curve"] = {str(t): precision_coverage(confidence, correct, t) for t in CURVE_THRESHOLDS}
    return result


def confusion_table(model, frame: pd.DataFrame) -> str:
    """Markdown confusion matrix: rows are the true label, columns the prediction."""
    labels = list(model.classes_)
    matrix = confusion_matrix(frame["label"], model.predict(features(frame)), labels=labels)
    lines = ["| true \\ predicted | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"]
    for label, row in zip(labels, matrix, strict=True):
        cells = [
            f"**{n}**" if label == other else (str(n) if n else "·")
            for other, n in zip(labels, row, strict=True)
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def worst_mistakes(model, frame: pd.DataFrame, limit: int = 12) -> list[dict]:
    """Holdout rows the model got wrong, most confident first: the errors worth reading."""
    probabilities = model.predict_proba(features(frame))
    wrong = frame.assign(
        predicted=model.classes_[probabilities.argmax(axis=1)], confidence=probabilities.max(axis=1)
    )
    wrong = wrong[wrong["predicted"] != wrong["label"]].sort_values("confidence", ascending=False)
    return [
        {"title": row.title, "amount": row.amount, "label": row.label, "predicted": row.predicted,
         "confidence": round(float(row.confidence), 3)}
        for row in wrong.head(limit).itertuples()
    ]


def _pct(value: float | None) -> str:
    return "–" if value is None else f"{value:.1%}"


def _results_row(name: str, split: dict) -> str:
    at = split["at_threshold"]
    return (
        f"| {name} | {split['accuracy']:.3f} | {split['macro_f1']:.3f} | {split['ece']:.3f}"
        f" | {split['mean_confidence']:.3f} | {_pct(at['coverage'])} | {_pct(at['precision'])} |"
    )


def model_card(metrics: dict, confusion: str) -> str:
    holdout, test, params, data = metrics["holdout"], metrics["test"], metrics["params"], metrics["data"]
    c_grid = ", ".join(params["cv_macro_f1_by_C"])
    ablation_rows = "\n".join(
        f"| {name} | {scores['test']['macro_f1']:.3f} | {scores['holdout']['macro_f1']:.3f} |"
        for name, scores in metrics["ablation"].items()
    )
    out_of_fold = metrics["out_of_fold_curve"]
    curve_rows = "\n".join(
        f"| {t} | {_pct(out_of_fold[t]['precision'])} | {_pct(out_of_fold[t]['coverage'])}"
        f" | {_pct(holdout['curve'][t]['precision'])} | {_pct(holdout['curve'][t]['coverage'])} |"
        for t in holdout["curve"]
    )
    per_class_rows = "\n".join(
        f"| {label} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1-score']:.2f} | {s['support']:.0f} |"
        for label, s in metrics["holdout_per_class"].items()
    )
    mistakes = "\n".join(
        f"| {m['title']} | {m['amount']:g} | {m['label']} | {m['predicted']} | {m['confidence']:.2f} |"
        for m in metrics["holdout_mistakes"]
    )
    return f"""# Model card: transaction categorizer

Generated by `python -m training.train_categorizer`. Do not edit by hand.

| | |
|---|---|
| Version | `{metrics['version']}` |
| Trained | {metrics['trained_at']} |
| Model | TF-IDF (word 1-2 grams + character 2-5 grams) + amount band + type → logistic regression |
| Regularisation | C = {params['C']}, chosen by grouped 5-fold cross-validation over {c_grid} |
| Threshold | {params['threshold']}: lowest with ≥{params['target_precision']:.0%} out-of-fold precision |
| scikit-learn | {metrics['sklearn_version']} |

## Intended use
Suggests one of ten canonical categories for a personal expense or income entry from its title,
amount and type. The app checks the user's own history first, shows a model suggestion only above
the threshold, and the user always confirms.

## Data
- **Training:** {data['synthetic_rows']} synthetic titles from {data['templates']} templates
  (Indian merchants, UPI and card descriptors, casing and typos). No real user data.
- **Test:** {test['rows']} synthetic rows from templates the model never saw: the merchant itself is new.
- **Holdout:** {holdout['rows']} hand-written titles, including merchants the generator never uses.
  Never used for training, tuning or choosing the threshold.

## Results

| Split | Accuracy | Macro-F1 | ECE | Mean confidence | Coverage at threshold | Precision at threshold |
|---|---|---|---|---|---|---|
{_results_row("Synthetic test, unseen merchants", test)}
{_results_row("Hand-written holdout", holdout)}

A random split, where renderings of the same phrase land on both sides, reports macro-F1
**{metrics['leaky_random_split_macro_f1']:.3f}** on the same data. That number measures memorisation,
which is why the test split is grouped by template.

### Ablation (macro-F1, C = {params['C']})

| Model | Synthetic test | Holdout |
|---|---|---|
{ablation_rows}

### Precision–coverage trade-off

| Threshold | Out-of-fold precision | Out-of-fold coverage | Holdout precision | Holdout coverage |
|---|---|---|---|---|
{curve_rows}

The threshold is chosen on the out-of-fold columns only; the holdout columns show what it means
on realistic input.

### Holdout per class

| Label | Precision | Recall | F1 | Rows |
|---|---|---|---|---|
{per_class_rows}

### Holdout confusion matrix

{confusion}

### Most confident holdout mistakes

| Title | Amount | True | Predicted | Confidence |
|---|---|---|---|---|
{mistakes}

## Limitations
- Trained on synthetic data: real titles are messier. The live acceptance rate of suggestions is
  the metric that matters.
- The holdout is small ({holdout['rows']} rows), so its scores move by a few points between versions.
- Indian merchants and English or Hinglish titles only.
- The amount band helps on average but misleads on large one-off purchases (they look like rent).
- Ambiguous merchants (Amazon sells goods and Prime Video) need the user's own history,
  which the service checks before the model.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate the transaction categorizer.")
    parser.add_argument("--rows-per-label", type=int, default=600)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--min-holdout-f1", type=float, default=0.0,
        help="Evaluation gate: below this holdout macro-F1, exit with an error and save no model",
    )
    args = parser.parse_args(argv)

    data = generate_dataset(rows_per_label=args.rows_per_label, seed=SEED)
    holdout = pd.read_csv(HOLDOUT_PATH)
    train, test = grouped_split(data, SEED)
    X_train, y_train, groups = features(train), train["label"], train["template_id"]
    print(f"data: {len(train)} train / {len(test)} test (unseen templates) / {len(holdout)} holdout rows")

    # 1. Regularisation strength by grouped cross-validation
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    search = GridSearchCV(build_pipeline(), {"model__C": C_GRID}, cv=cv, scoring="f1_macro", n_jobs=-1)
    search.fit(X_train, y_train, groups=groups)
    best_c = float(search.best_params_["model__C"])
    cv_scores = {
        str(c): round(float(score), 4)
        for c, score in zip(C_GRID, search.cv_results_["mean_test_score"], strict=True)
    }
    print(f"C by grouped CV: {best_c}  {cv_scores}")

    # 2. Baselines and ablation on the same split
    candidates = {
        "majority class": DummyClassifier(strategy="most_frequent"),
        "words only": build_pipeline(c=best_c, use_chars=False, use_meta=False),
        "words + characters": build_pipeline(c=best_c, use_meta=False),
        "full (+ amount band + type)": build_pipeline(c=best_c),
    }
    ablation = {}
    for name, candidate in candidates.items():
        candidate.fit(X_train, y_train)
        ablation[name] = {"test": evaluate(candidate, test), "holdout": evaluate(candidate, holdout)}
        print(f"  {name:<28} test macro-F1 {ablation[name]['test']['macro_f1']:.3f}"
              f"   holdout macro-F1 {ablation[name]['holdout']['macro_f1']:.3f}")

    # The leaky alternative, for comparison: a random split shares templates between train and test
    leaky_train, leaky_test = train_test_split(data, test_size=0.2, stratify=data["label"], random_state=SEED)
    leaky_model = build_pipeline(c=best_c).fit(features(leaky_train), leaky_train["label"])
    leaky_f1 = evaluate(leaky_model, leaky_test)["macro_f1"]
    print(f"  random split (leaky)         test macro-F1 {leaky_f1:.3f}")

    # 3. Threshold from out-of-fold predictions: each row is scored by a model that never saw its template
    out_of_fold = cross_val_predict(
        build_pipeline(c=best_c), X_train, y_train, groups=groups, cv=cv, method="predict_proba", n_jobs=-1
    )
    confidence, correct = confidence_and_correct(out_of_fold, np.unique(y_train), y_train.to_numpy())
    threshold = choose_threshold(confidence, correct, TARGET_PRECISION)
    print(f"threshold: {threshold}  out-of-fold {precision_coverage(confidence, correct, threshold)}")
    test_metrics = evaluate(candidates["full (+ amount band + type)"], test, threshold)

    # 4. Final model on all synthetic data, scored on the hand-written holdout
    final = build_pipeline(c=best_c).fit(features(data), data["label"])
    holdout_metrics = evaluate(final, holdout, threshold)
    per_class = classification_report(
        holdout["label"], final.predict(features(holdout)), output_dict=True, zero_division=0
    )
    fingerprint = hashlib.sha256(
        f"{data.to_csv(index=False)}|{best_c}|{threshold}|{sklearn.__version__}".encode()
    ).hexdigest()[:8]
    metrics = {
        "version": f"{datetime.now(UTC):%Y%m%d}-{fingerprint}",
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "data": {
            "synthetic_rows": len(data), "templates": int(data["template_id"].nunique()),
            "train_rows": len(train), "test_rows": len(test), "holdout_rows": len(holdout),
        },
        "params": {"C": best_c, "cv_macro_f1_by_C": cv_scores, "threshold": threshold,
                   "target_precision": TARGET_PRECISION},
        "ablation": ablation,
        "leaky_random_split_macro_f1": leaky_f1,
        "out_of_fold_curve": {str(t): precision_coverage(confidence, correct, t) for t in CURVE_THRESHOLDS},
        "test": test_metrics,
        "holdout": holdout_metrics,
        "holdout_per_class": {label: per_class[label] for label in final.classes_},
        "holdout_mistakes": worst_mistakes(final, holdout),
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    card = model_card(metrics, confusion_table(final, holdout))
    (args.report_dir / "model_card.md").write_text(card, encoding="utf-8")
    for name, split in (("test", test_metrics), ("holdout", holdout_metrics)):
        print(f"{name + ':':<9}macro-F1 {split['macro_f1']:.3f}  at threshold {split['at_threshold']}")
    print(f"reports: {args.report_dir}")
    record_run("categorizer", args.report_dir, {"rows_per_label": args.rows_per_label, "C": best_c,
                                                 "threshold": threshold}, {
        "holdout_macro_f1": holdout_metrics["macro_f1"],
        "test_macro_f1": test_metrics["macro_f1"],
        "holdout_precision": holdout_metrics["at_threshold"]["precision"],
        "holdout_coverage": holdout_metrics["at_threshold"]["coverage"],
    })

    if holdout_metrics["macro_f1"] < args.min_holdout_f1:
        print(f"FAILED evaluation gate: holdout macro-F1 {holdout_metrics['macro_f1']:.3f}"
              f" < {args.min_holdout_f1:.3f}. Model not saved.")
        return 1
    path = CategorizerModel(final, metrics["version"], threshold).save(args.model_dir)
    print(f"saved {path} (version {metrics['version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
