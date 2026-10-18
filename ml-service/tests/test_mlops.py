import json
import logging
import random

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.observability import JsonFormatter
from tests.conftest import SUPABASE_URL
from training import retrain_categorizer, runs
from training.retrain_categorizer import export_feedback, feedback_examples, label_for, should_promote

# ---------- metrics ----------


def metric_value(text: str, name: str, **labels) -> float:
    wanted = ",".join(f'{key}="{value}"' for key, value in labels.items())
    line = next(line for line in text.splitlines() if line.startswith(f"{name}{{{wanted}}}"))
    return float(line.rsplit(" ", 1)[1])


def test_metrics_count_requests_and_feature_outcomes(client, supabase, auth_headers):
    supabase.tables.update({"categories": [], "transactions": []})
    client.post("/v1/categorize", json={"title": "zomato order"}, headers=auth_headers)
    client.post("/v1/categorize", json={"title": "qwxz"}, headers=auth_headers)
    text = client.get("/metrics").text
    assert metric_value(text, "ml_requests_total", route="/v1/categorize", status="200") == 2
    assert metric_value(text, "ml_feature_events_total", feature="categorize", outcome="model") == 1
    assert metric_value(text, "ml_feature_events_total", feature="categorize", outcome="none") == 1
    assert 'ml_request_seconds_bucket{le="0.005",route="/v1/categorize"}' in text


def test_metrics_label_routes_not_urls(client, auth_headers):
    client.get("/health?anything=1")
    assert 'route="/health"' in client.get("/metrics").text


def test_metrics_can_require_a_token(supabase, model_dir):
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", model_dir=model_dir,
                        metrics_token="scrape-me")
    with TestClient(create_app(settings, transport=httpx.MockTransport(supabase.handler))) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer scrape-me"}).status_code == 200


def test_logs_are_json_lines():
    record = logging.LogRecord(
        "ml_service.test", logging.INFO, __file__, 1, "categorize source=%s", ("model",), None
    )
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "categorize source=model" and entry["level"] == "INFO"


# ---------- experiment log ----------


def test_runs_are_appended_and_listed(tmp_path, capsys):
    runs.record_run("rag", tmp_path / "rag", {"k": 3}, {"hit@1": 0.83})
    runs.record_run("rag", tmp_path / "rag", {"k": 5}, {"hit@1": 0.87})
    history = runs.load_runs(tmp_path)
    assert [run["params"]["k"] for run in history] == [3, 5]
    assert runs.main(["--reports-dir", str(tmp_path), "--kind", "rag"]) == 0
    assert "hit@1 0.870" in capsys.readouterr().out


# ---------- retraining ----------


def test_feedback_maps_onto_canonical_labels():
    assert label_for("Food") == "food" and label_for("Rent & Housing") == "rent" and label_for("Pets") is None
    rows = [{"title": "lenskart", "amount": 900, "type": "EXPENSE", "chosen_category": "Health"},
            {"title": "puppy food", "amount": 500, "type": "EXPENSE", "chosen_category": "Pets"},
            {"title": "", "chosen_category": "Food"}]
    assert feedback_examples(rows).to_dict("records") == [
        {"title": "lenskart", "amount": 900.0, "type": "EXPENSE", "label": "health"},
    ]


@pytest.mark.parametrize(
    ("feedback_accuracy", "newly_wrong", "newly_right", "promote"),
    [
        (0.9, 1, 3, True),  # gains on both
        (0.9, 4, 2, True),  # 2 net examples worse: within the margin
        (0.99, 6, 1, False),  # breaks what worked
        (0.5, 0, 5, False),  # better on the holdout, but learnt nothing from users
    ],
)
def test_promotion_rule(feedback_accuracy, newly_wrong, newly_right, promote):
    champion = {"holdout_macro_f1": 0.88, "feedback_accuracy": 0.5}
    challenger = {"holdout_macro_f1": 0.87, "feedback_accuracy": feedback_accuracy}
    paired = {"newly_wrong": newly_wrong, "newly_right": newly_right}
    assert should_promote(champion, challenger, paired)[0] is promote


def write_feedback(path, habits, count=200):
    rng = random.Random(0)
    rows = [{"title": title, "amount": rng.randint(200, 3000), "type": "EXPENSE", "chosen_category": category}
            for title, category in (rng.choice(habits) for _ in range(count))]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def retrain(tmp_path, habits) -> dict:
    feedback = write_feedback(tmp_path / "feedback.jsonl", habits)
    out = tmp_path / "out"
    assert retrain_categorizer.main(["--feedback", str(feedback), "--model-dir", str(tmp_path / "none"),
                                     "--out-dir", str(out), "--rows-per-label", "300"]) == 0
    return json.loads((out / "retrain.json").read_text(encoding="utf-8"))


def test_retraining_learns_new_merchants_and_is_promoted(tmp_path):
    # Merchants the synthetic data never mentions, filed where anyone would file them
    report = retrain(tmp_path, [("dunzo", "Food"), ("cleartrip", "Travel"), ("wakefit", "Shopping"),
                                ("testbook", "Education")])
    assert report["promote"] is True, report
    assert report["challenger"]["feedback_accuracy"] > report["champion"]["feedback_accuracy"]
    assert (tmp_path / "out" / "categorizer.joblib").exists()


def test_feedback_that_breaks_known_cases_is_not_promoted(tmp_path):
    # Contradicts the hand-written holdout ("kindle unlimited" is Education, Amazon orders are Shopping)
    report = retrain(tmp_path, [("kindle", "Entertainment"), ("amazon prime", "Entertainment"),
                                ("amazon", "Entertainment")])
    assert report["promote"] is False and report["reason"].startswith("worse on the hand-written holdout")
    assert not (tmp_path / "out" / "categorizer.joblib").exists()


def test_too_little_feedback_changes_nothing(tmp_path):
    feedback = write_feedback(tmp_path / "feedback.jsonl", [("lenskart", "Health")], count=10)
    assert retrain_categorizer.main(["--feedback", str(feedback), "--out-dir", str(tmp_path / "out")]) == 0
    report = json.loads((tmp_path / "out" / "retrain.json").read_text(encoding="utf-8"))
    assert report["promote"] is False and "need 50" in report["reason"]


def test_export_reads_only_users_who_opted_in():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path + "?" + str(request.url.query, "utf-8"))
        if request.url.path.endswith("/profiles"):
            return httpx.Response(200, json=[{"id": "u1"}])
        return httpx.Response(200, json=[{"title": "lenskart", "chosen_category": "Health"}])

    rows = export_feedback("https://x.supabase.co", "service-key", transport=httpx.MockTransport(handler))
    assert rows == [{"title": "lenskart", "chosen_category": "Health"}]
    assert "ai_training_opt_in=eq.true" in seen[0] and "user_id=in.%28u1%29" in seen[1]
