import json

import numpy as np
import pytest

from app.ml.categorizer import CategorizerModel
from training import train_categorizer
from training.generate_data import generate_dataset
from training.train_categorizer import (
    choose_threshold,
    expected_calibration_error,
    grouped_split,
    precision_coverage,
)


def test_generated_data_is_reproducible_and_balanced():
    first, second = generate_dataset(rows_per_label=30, seed=1), generate_dataset(rows_per_label=30, seed=1)
    assert first.equals(second)
    assert first["label"].value_counts().eq(30).all()


def test_grouped_split_keeps_each_template_on_one_side():
    train, test = grouped_split(generate_dataset(rows_per_label=60), seed=42)
    assert not set(train["template_id"]) & set(test["template_id"])
    assert set(test["label"]) == set(train["label"])  # every label is still tested


def test_precision_and_coverage():
    confidence = np.array([0.9, 0.8, 0.6, 0.3])
    correct = np.array([True, True, False, True])
    assert precision_coverage(confidence, correct, 0.7) == {"coverage": 0.5, "precision": 1.0}
    assert precision_coverage(confidence, correct, 0.5) == {"coverage": 0.75, "precision": 0.6667}
    assert precision_coverage(confidence, correct, 0.95) == {"coverage": 0.0, "precision": None}


def test_threshold_is_the_lowest_that_meets_the_precision_target():
    confidence = np.array([0.95, 0.9, 0.85, 0.5, 0.45, 0.3])
    correct = np.array([True, True, True, False, True, False])
    assert choose_threshold(confidence, correct, target_precision=0.9) == 0.55
    assert choose_threshold(confidence, correct, target_precision=0.75) == 0.35


def test_expected_calibration_error():
    # Always 80% confident and right 80% of the time: perfectly calibrated
    assert expected_calibration_error(np.full(10, 0.8), np.array([True] * 8 + [False] * 2)) == 0.0
    # Always 90% confident but right half the time: off by 0.4
    assert expected_calibration_error(np.full(10, 0.9), np.array([True, False] * 5)) == pytest.approx(0.4)


def train(tmp_path, *extra_args: str) -> int:
    """Run the training script on a small dataset, writing into tmp_path."""
    return train_categorizer.main([
        "--rows-per-label", "60",
        "--model-dir", str(tmp_path / "models"),
        "--report-dir", str(tmp_path / "reports"),
        *extra_args,
    ])


def test_training_end_to_end_writes_reports_and_model(tmp_path, monkeypatch):
    monkeypatch.setattr(train_categorizer, "C_GRID", [1.0])
    exit_code = train(tmp_path)
    assert exit_code == 0
    metrics = json.loads((tmp_path / "reports" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["holdout"]["macro_f1"] > metrics["ablation"]["majority class"]["holdout"]["macro_f1"]
    assert "Model card" in (tmp_path / "reports" / "model_card.md").read_text(encoding="utf-8")
    model = CategorizerModel.load(tmp_path / "models")
    assert model.version == metrics["version"] and model.threshold == metrics["params"]["threshold"]


def test_evaluation_gate_blocks_a_weak_model(tmp_path, monkeypatch):
    monkeypatch.setattr(train_categorizer, "C_GRID", [1.0])
    exit_code = train(tmp_path, "--min-holdout-f1", "1.01")
    assert exit_code == 1
    assert CategorizerModel.load(tmp_path / "models") is None
    assert (tmp_path / "reports" / "metrics.json").exists()  # the failing run is still inspectable
