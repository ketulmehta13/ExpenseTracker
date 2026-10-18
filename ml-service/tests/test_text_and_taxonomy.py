import pytest

from app.ml.taxonomy import CANONICAL_CATEGORIES, display_name, match_user_category
from app.ml.text import normalize_title
from training.generate_data import TEMPLATES


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("UPI/SWIGGY/40213/Payment", "swiggy"),
        ("AMZN MKTP IN", "amazon"),
        ("swiggy@icici paid", "swiggy"),
        ("BMS*BOOKMYSHOW 2201", "bookmyshow"),
        ("paid to Zomato order ref 99812345", "zomato"),
        ("Tata 1mg", "tata 1mg"),
        ("ZEE5 annual", "zee5 annual"),
        ("Card XX1234 POS 88213 DMART", "card dmart"),  # masked card digits are dropped too
        ("UPI/SWIGGY/1234/Pay", "swiggy"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_title(title, expected):
    assert normalize_title(title) == expected


def test_normalization_is_idempotent():
    for title in ["UPI/SWIGGY/40213/Payment", "Disney+ Hotstar annual", "rent paid via cred"]:
        assert normalize_title(normalize_title(title)) == normalize_title(title)


def test_taxonomy_covers_every_training_label():
    assert set(TEMPLATES) == set(CANONICAL_CATEGORIES)


GLOBAL = [
    {"id": 1, "name": "Food", "user_id": None},
    {"id": 2, "name": "Travel", "user_id": None},
    {"id": 3, "name": "Rent & Housing", "user_id": None},
]


def test_matches_category_names_through_aliases():
    assert match_user_category("food", GLOBAL)["id"] == 1
    assert match_user_category("rent", GLOBAL)["id"] == 3  # "&" is read as "and"


def test_prefers_the_users_own_category_over_a_default():
    own = {"id": 9, "name": "Groceries", "user_id": "user-1"}
    assert match_user_category("food", [*GLOBAL, own])["id"] == 9


def test_no_match_when_the_user_has_no_such_category():
    assert match_user_category("health", GLOBAL) is None
    assert display_name("health") == "Health"
