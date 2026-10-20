"""Suggest a category from the user's own past transactions.

The best predictor of how someone files "Swiggy" is how they filed it last time, and it
captures personal habits a global model cannot (one user files Amazon under Shopping,
another under Household). This layer runs before the model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.ml.text import normalize_title

# rapidfuzz similarity (0-100) that still counts as the same title. token_sort_ratio ignores word
# order and tolerates a typo or two, but unlike partial or token-set matching it will not equate
# "uber" with "uber eats" or "rent" with "car rental".
MIN_SIMILARITY = 88


@dataclass(frozen=True)
class HistoryMatch:
    category_id: int | str
    matched_title: str
    similarity: float  # 0-1, how close the new title is to the past one
    share: float  # 0-1, share of the past title's transactions filed under this category
    count: int

    @property
    def confidence(self) -> float:
        return round(self.similarity * self.share, 4)


class UserHistory:
    def __init__(self, transactions: list[dict]):
        """`transactions` are rows with `title` and `category_id`."""
        by_title: dict[str, Counter] = defaultdict(Counter)
        for tx in transactions:
            title = normalize_title(tx.get("title"))
            if title and tx.get("category_id") is not None:
                by_title[title][tx["category_id"]] += 1
        self._by_title = dict(by_title)
        self._titles = list(by_title)

    @property
    def titles(self) -> list[str]:
        """The user's distinct titles, most recent first."""
        return self._titles

    def __len__(self) -> int:
        return len(self._titles)

    def match(self, title: str) -> HistoryMatch | None:
        query = normalize_title(title)
        if not query or not self._titles:
            return None
        if query in self._by_title:
            matched, score = query, 100.0
        else:
            best = process.extractOne(
                query, self._titles, scorer=fuzz.token_sort_ratio, score_cutoff=MIN_SIMILARITY
            )
            if best is None:
                return None
            matched, score = best[0], best[1]
        counts = self._by_title[matched]
        category_id, count = counts.most_common(1)[0]
        return HistoryMatch(
            category_id=category_id,
            matched_title=matched,
            similarity=score / 100,
            share=count / sum(counts.values()),
            count=count,
        )
