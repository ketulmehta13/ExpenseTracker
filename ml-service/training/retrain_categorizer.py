"""Retrain the categorizer with users' feedback, and promote it only if it isn't worse.

Feedback rows (Supabase's ml_feedback, only for users who opted in) record which category a
user actually saved for a title. Mapped onto the canonical labels, they are real labelled
data: the thing the synthetic generator can only imitate.

Champion / challenger:
- champion: the current model (or one trained like it, on synthetic data only);
- challenger: the same pipeline retrained on synthetic data plus the feedback. Feedback rows
  are weighted up because they are real, but capped at a fifth of the total training weight:
  an early version used a fixed 5x weight, and with a small synthetic base a few merchants'
  feedback outweighed everything else and cost 7 points on the holdout (the gate caught it);
- both are scored on the same hand-written holdout and on a held-out fifth of the feedback;
- the challenger is promoted only if it is better on the held-out feedback and no worse on
  the holdout, so learning from users can't quietly break what worked. "No worse" is a paired
  comparison on the same 142 examples (as in McNemar's test): the examples it newly gets wrong,
  minus those it newly gets right, may be at most 2. A macro-F1 difference can't be used: on so
  few examples one example moves it by about a point, and the first version of this rule
  rejected a harmless challenger over a single net example.

The decision is written to the report. Deploying a promoted model is a deliberate human step:
the feedback set is small at first, and model files are pickles, i.e. code.

Usage (from ml-service/):
    python -m training.retrain_categorizer --feedback feedback.csv
    python -m training.retrain_categorizer --from-supabase   # SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from app.config import DEFAULT_MODEL_DIR
from app.ml.categorizer import CategorizerModel, build_pipeline
from app.ml.taxonomy import CANONICAL_CATEGORIES
from training.generate_data import generate_dataset
from training.runs import record_run
from training.train_categorizer import HOLDOUT_PATH, SEED, evaluate, features

DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "reports" / "retrain"
MIN_FEEDBACK = 50  # below this, a fifth held out is too small to judge anything
FEEDBACK_WEIGHT = 5.0  # per feedback row, at most...
MAX_FEEDBACK_SHARE = 0.2  # ...and feedback never more than a fifth of the training weight
MAX_NET_NEW_ERRORS = 2  # holdout examples the challenger may newly get wrong, net


def label_for(category_name: str | None) -> str | None:
    """The canonical label for a category name, through the same aliases the app uses."""
    if not category_name:
        return None
    name = re.sub(r"\s+", " ", category_name.lower().replace("&", " and ")).strip()
    return next((label for label, (_, aliases) in CANONICAL_CATEGORIES.items() if name in aliases), None)


def feedback_examples(rows: list[dict]) -> pd.DataFrame:
    """Labelled examples; rows saved under custom categories can't be mapped and are dropped."""
    examples = []
    for row in rows:
        label = label_for(row.get("chosen_category"))
        if row.get("title") and label:
            examples.append({"title": row["title"], "amount": float(row.get("amount") or 0),
                             "type": row.get("type") or "EXPENSE", "label": label})
    return pd.DataFrame(examples, columns=["title", "amount", "type", "label"])


def load_feedback_file(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        return pd.read_csv(path).to_dict("records")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def export_feedback(
    base_url: str, service_key: str, transport: httpx.BaseTransport | None = None
) -> list[dict]:
    """Feedback from users who opted in, read with the service role (this job runs outside the app)."""
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    rest_url = f"{base_url.rstrip('/')}/rest/v1"
    with httpx.Client(base_url=rest_url, headers=headers, timeout=30, transport=transport) as http:
        opted_in = http.get("/profiles", params={"select": "id", "ai_training_opt_in": "eq.true"}).json()
        if not opted_in:
            return []
        params = {
            "select": "title,amount,type,chosen_category,accepted,source",
            "kind": "eq.category_suggestion",
            "user_id": f"in.({','.join(row['id'] for row in opted_in)})",
            "order": "id",
        }
        rows: list[dict] = []
        while True:  # PostgREST returns at most 1000 rows per request
            page_range = {"Range-Unit": "items", "Range": f"{len(rows)}-{len(rows) + 999}"}
            page = http.get("/ml_feedback", params=params, headers=page_range).json()
            rows += page
            if len(page) < 1000:
                return rows


def paired_holdout(champion, challenger, holdout: pd.DataFrame) -> dict:
    """Where the two models disagree on the holdout: what the challenger loses and gains."""
    truth = holdout["label"].to_numpy()
    champion_right = champion.predict(features(holdout)) == truth
    challenger_right = challenger.predict(features(holdout)) == truth
    return {
        "newly_wrong": int((champion_right & ~challenger_right).sum()),
        "newly_right": int((~champion_right & challenger_right).sum()),
    }


def should_promote(champion: dict, challenger: dict, paired: dict) -> tuple[bool, str]:
    net_new_errors = paired["newly_wrong"] - paired["newly_right"]
    if net_new_errors > MAX_NET_NEW_ERRORS:
        return False, f"worse on the hand-written holdout ({net_new_errors} more examples wrong)"
    if challenger["feedback_accuracy"] <= champion["feedback_accuracy"]:
        return False, "no better on held-out feedback"
    return True, "better on held-out feedback and no worse on the hand-written holdout"


def score(pipeline, holdout: pd.DataFrame, feedback_test: pd.DataFrame) -> dict:
    predicted = pipeline.predict(features(feedback_test))
    return {
        "holdout_macro_f1": evaluate(pipeline, holdout)["macro_f1"],
        "feedback_accuracy": round(float(np.mean(predicted == feedback_test["label"].to_numpy())), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrain the categorizer with feedback.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--feedback", type=Path, help="exported feedback, .csv or .jsonl")
    source.add_argument("--from-supabase", action="store_true", help="export it now (service-role key)")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR, help="where the champion is")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="report and challenger")
    parser.add_argument("--rows-per-label", type=int, default=600)
    args = parser.parse_args(argv)

    if args.from_supabase:
        rows = export_feedback(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    else:
        rows = load_feedback_file(args.feedback)
    examples = feedback_examples(rows)
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "feedback_rows": len(rows),
        "usable_examples": len(examples),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "retrain.json"
    if len(examples) < MIN_FEEDBACK:
        reason = f"only {len(examples)} usable feedback examples (need {MIN_FEEDBACK})"
        report |= {"promote": False, "reason": reason}
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(reason)
        return 0

    feedback_train, feedback_test = train_test_split(examples, test_size=0.2, random_state=SEED)
    synthetic = generate_dataset(rows_per_label=args.rows_per_label, seed=SEED)
    holdout = pd.read_csv(HOLDOUT_PATH)

    current = CategorizerModel.load(args.model_dir)
    c = float(current.pipeline.get_params()["model__C"]) if current else 1.0
    if current:
        champion = current.pipeline
    else:  # no model yet: a champion trained exactly like the challenger, minus the feedback
        champion = build_pipeline(c=c).fit(features(synthetic), synthetic["label"])
    combined = pd.concat([synthetic, feedback_train], ignore_index=True)
    weight = min(FEEDBACK_WEIGHT,
                 MAX_FEEDBACK_SHARE / (1 - MAX_FEEDBACK_SHARE) * len(synthetic) / len(feedback_train))
    weights = np.r_[np.ones(len(synthetic)), np.full(len(feedback_train), weight)]
    challenger = build_pipeline(c=c).fit(features(combined), combined["label"], model__sample_weight=weights)

    report["champion"] = score(champion, holdout, feedback_test)
    report["challenger"] = score(challenger, holdout, feedback_test)
    report["holdout_disagreements"] = paired_holdout(champion, challenger, holdout)
    report["promote"], report["reason"] = should_promote(
        report["champion"], report["challenger"], report["holdout_disagreements"]
    )
    if report["promote"]:
        version = f"{datetime.now(UTC):%Y%m%d}-feedback{len(examples)}"
        threshold = current.threshold if current else 0.7
        report["model"] = str(CategorizerModel(challenger, version, threshold).save(args.out_dir))
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["feedback_weight"] = round(weight, 3)
    record_run("retrain", args.out_dir, {"feedback_examples": len(examples), "C": c, "weight": weight}, {
        "champion_holdout_f1": report["champion"]["holdout_macro_f1"],
        "challenger_holdout_f1": report["challenger"]["holdout_macro_f1"],
        "champion_feedback_acc": report["champion"]["feedback_accuracy"],
        "challenger_feedback_acc": report["challenger"]["feedback_accuracy"],
        "promoted": report["promote"],
    })
    print(f"champion {report['champion']}  challenger {report['challenger']}")
    print(f"{'PROMOTE' if report['promote'] else 'keep the champion'}: {report['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
