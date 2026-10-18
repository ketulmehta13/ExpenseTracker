"""The categorizer's canonical labels and how they map onto each user's own categories.

The model predicts a fixed set of labels; users name categories however they like
("Food", "Groceries", "Dining Out"). A prediction is mapped to the user's category
through these aliases, and suggested as a new category when nothing matches.
"""

from __future__ import annotations

import re

# label -> (name to suggest when the user has no such category, names that mean the same)
CANONICAL_CATEGORIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "food": ("Food", ("food", "groceries", "grocery", "dining", "dining out", "restaurants",
                      "food and dining", "eating out", "food and drinks")),
    "travel": ("Travel", ("travel", "transport", "transportation", "commute", "fuel", "cab", "taxi")),
    "shopping": ("Shopping", ("shopping", "clothes", "clothing", "electronics", "fashion")),
    "utilities": ("Utilities", ("utilities", "bills", "bills and utilities", "recharge", "internet",
                                "electricity", "phone")),
    "entertainment": ("Entertainment", ("entertainment", "subscriptions", "movies", "fun", "leisure",
                                        "streaming")),
    "health": ("Health", ("health", "health and medical", "medical", "healthcare", "fitness", "pharmacy",
                          "medicine")),
    "education": ("Education", ("education", "learning", "courses", "books", "school")),
    "rent": ("Rent", ("rent", "rent and housing", "housing", "home", "accommodation")),
    "salary": ("Salary", ("salary", "income", "wages", "paycheck")),
    "other": ("Other", ("other", "others", "misc", "miscellaneous", "general")),
}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().replace("&", " and ")).strip()


def display_name(label: str) -> str:
    return CANONICAL_CATEGORIES[label][0]


def match_user_category(label: str, categories: list[dict]) -> dict | None:
    """The user's category for a label, preferring one they created over a shared default."""
    aliases = set(CANONICAL_CATEGORIES[label][1])
    matches = [c for c in categories if _normalize_name(c["name"]) in aliases]
    if not matches:
        return None
    return min(matches, key=lambda c: c.get("user_id") is None)
