"""Transaction categorizer: features, pipeline and inference.

Training (training/train_categorizer.py) and serving both build inputs with `to_frame`,
which applies the shared `normalize_title`, so production inputs always match the
format the model was trained on.

Model files are pickles: only load files this project produced.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, KBinsDiscretizer, OneHotEncoder

from app.ml.text import normalize_title

MODEL_FILENAME = "categorizer.joblib"


def to_frame(titles: Iterable, amounts: Iterable, types: Iterable) -> pd.DataFrame:
    return pd.DataFrame({
        "text": [normalize_title(title) for title in titles],
        "amount": [max(float(amount or 0), 0.0) for amount in amounts],
        "type": [str(tx_type or "EXPENSE").upper() for tx_type in types],
    })


def build_pipeline(c: float = 4.0, use_chars: bool = True, use_meta: bool = True) -> Pipeline:
    """TF-IDF over the title plus amount band and type, into logistic regression.

    Word n-grams (1-2) capture phrases like "house rent". Character n-grams (2-5, inside
    word boundaries) make the model robust to typos and to merchant-name fragments.
    The amount band separates e.g. rent from groceries; the type separates income.
    `use_chars` / `use_meta` switch parts off for ablation studies.
    """
    transformers: list = [("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True), "text")]
    if use_chars:
        chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
        transformers.append(("chars", chars, "text"))
    if use_meta:
        amount_bands = Pipeline([
            ("log", FunctionTransformer(np.log1p)),
            ("bands", KBinsDiscretizer(n_bins=8, encode="onehot", strategy="quantile",
                                       quantile_method="averaged_inverted_cdf")),
        ])
        transformers += [
            ("amount", amount_bands, ["amount"]),
            ("type", OneHotEncoder(handle_unknown="ignore"), ["type"]),
        ]
    return Pipeline([
        ("features", ColumnTransformer(transformers)),
        # class_weight="balanced" stops frequent categories from drowning out rare ones
        ("model", LogisticRegression(C=c, class_weight="balanced", max_iter=3000)),
    ])


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    # Top three (label, probability) pairs, best first
    alternatives: list[tuple[str, float]]


class CategorizerModel:
    def __init__(self, pipeline: Pipeline, version: str, threshold: float):
        self.pipeline = pipeline
        self.version = version
        # Minimum probability for a prediction to be shown as a suggestion
        self.threshold = threshold

    @classmethod
    def load(cls, model_dir: Path) -> CategorizerModel | None:
        path = Path(model_dir) / MODEL_FILENAME
        if not path.exists():
            return None
        bundle = joblib.load(path)
        return cls(bundle["pipeline"], bundle["version"], bundle["threshold"])

    def save(self, model_dir: Path) -> Path:
        path = Path(model_dir) / MODEL_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "version": self.version, "threshold": self.threshold}, path)
        return path

    def predict(self, title: str, amount: float | None = None, tx_type: str | None = None) -> Prediction:
        probabilities = self.pipeline.predict_proba(to_frame([title], [amount], [tx_type]))[0]
        labels = self.pipeline.classes_
        best = np.argsort(probabilities)[::-1][:3]
        alternatives = [(str(labels[i]), float(probabilities[i])) for i in best]
        return Prediction(label=alternatives[0][0], confidence=alternatives[0][1], alternatives=alternatives)
