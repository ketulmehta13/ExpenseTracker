"""BM25: the standard keyword-search baseline, written out to show how it works.

    score(query, doc) = sum over query terms t of
        idf(t) * tf(t, doc) * (k1 + 1) / (tf(t, doc) + k1 * (1 - b + b * len(doc) / avg_len))

- idf rewards rare words: "pdf" says more about a document than "my".
- tf saturates (k1): the tenth "category" in a section adds little over the third.
- Length normalisation (b): a long section doesn't win just by containing more words.
"""

from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "be", "to", "of", "and", "or", "in", "on", "for", "with", "my",
    "i", "me", "you", "your", "it", "this", "that", "do", "does", "did", "can", "how", "what", "why", "when",
    "where", "which", "will", "would", "should", "there", "at", "by", "from", "as", "so", "if", "not",
}
_TOKEN = re.compile(r"[a-z0-9₹]+")


def _stem(word: str) -> str:
    """A tiny suffix stripper: "categories" and "category" should match, as should "cancelling",
    "cancelled" and "cancel" (an undoubling rule borrowed from Porter's stemmer)."""
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: -len(suffix)] + replacement
            doubled = len(stem) > 4 and stem[-1] == stem[-2] and stem[-1] not in "aeiousz"
            if suffix in ("ing", "ed") and doubled:
                stem = stem[:-1]  # "cancell" -> "cancel", "stopp" -> "stop"; "bill" is left alone
            return stem
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(token) for token in _TOKEN.findall(text.lower()) if token not in STOPWORDS]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.term_counts = [Counter(tokenize(document)) for document in documents]
        self.lengths = [sum(counts.values()) for counts in self.term_counts]
        self.average_length = sum(self.lengths) / max(len(self.lengths), 1)
        document_frequency = Counter(term for counts in self.term_counts for term in counts)
        total = len(documents)
        self.idf = {
            term: math.log((total - frequency + 0.5) / (frequency + 0.5) + 1)
            for term, frequency in document_frequency.items()
        }

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        results = []
        for counts, length in zip(self.term_counts, self.lengths, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / self.average_length)
            results.append(sum(
                self.idf[term] * counts[term] * (self.k1 + 1) / (counts[term] + norm)
                for term in terms if term in counts
            ))
        return results
