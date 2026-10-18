import pytest

from app.cache import TTLCache
from app.ml.categorizer import CategorizerModel
from app.ml.history import UserHistory


@pytest.fixture(scope="module")
def model(model_dir) -> CategorizerModel:
    return CategorizerModel.load(model_dir)


@pytest.mark.parametrize(
    ("title", "amount", "tx_type", "label"),
    [
        ("Swiggy dinner", 450, "EXPENSE", "food"),
        ("UPI/UBER/55123/Pay", 212, "EXPENSE", "travel"),
        ("Netflix subscription", 649, "EXPENSE", "entertainment"),
        ("monthly salary", 85000, "INCOME", "salary"),
        ("house rent", 18000, "EXPENSE", "rent"),
    ],
)
def test_predicts_clear_cases(model, title, amount, tx_type, label):
    prediction = model.predict(title, amount, tx_type)
    assert prediction.label == label
    assert prediction.alternatives[0] == (prediction.label, prediction.confidence)
    assert len(prediction.alternatives) == 3


def test_amount_and_type_are_optional(model):
    assert model.predict("swiggy").label == "food"


def test_save_and_load_round_trip(model, tmp_path):
    model.save(tmp_path)
    loaded = CategorizerModel.load(tmp_path)
    assert (loaded.version, loaded.threshold) == (model.version, model.threshold)
    assert loaded.predict("zomato order").label == model.predict("zomato order").label


def test_load_returns_none_without_a_model(tmp_path):
    assert CategorizerModel.load(tmp_path) is None


HISTORY = [
    {"title": "Swiggy order 8812", "category_id": 7},
    {"title": "UPI/SWIGGY/1234/Pay", "category_id": 7},
    {"title": "swiggy", "category_id": 4},
    {"title": "Uber Eats", "category_id": 7},
    {"title": "Uber trip", "category_id": 2},
    {"title": "no category", "category_id": None},
]


def test_history_exact_match_uses_the_majority_category():
    match = UserHistory(HISTORY).match("SWIGGY")
    assert (match.category_id, match.count, match.similarity) == (7, 2, 1.0)
    assert match.share == pytest.approx(2 / 3)


def test_history_tolerates_typos():
    match = UserHistory(HISTORY).match("swigy")
    assert match is not None and match.category_id == 7 and match.similarity < 1


def test_history_does_not_confuse_merchants_that_share_a_word():
    history = UserHistory([{"title": "Uber Eats", "category_id": 7}])
    assert history.match("uber") is None


def test_history_ignores_uncategorized_rows_and_empty_titles():
    history = UserHistory(HISTORY)
    assert history.match("no category") is None
    assert history.match("12345") is None
    assert len(history) == 3  # swiggy, uber eats, uber trip


def test_ttl_cache_expires_and_evicts_oldest():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (None, 2, 3)

    expired = TTLCache(ttl_seconds=0)
    expired.put("a", 1)
    assert expired.get("a") is None
