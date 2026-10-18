"""Title normalization shared by training and serving.

Running the same function in both places prevents train/serve skew: the model sees
exactly the kind of input in production that it learned from.
"""

from __future__ import annotations

import re

# Payment-rail and descriptor words that say nothing about what was bought
NOISE_WORDS = {
    "upi", "imps", "neft", "rtgs", "pos", "ecom", "txn", "ref", "via", "to",
    "pay", "payment", "paid", "order", "online", "in", "pvt", "ltd", "limited", "private",
}
# Abbreviations seen on bank statements
MERCHANT_ALIASES = {
    "amzn": "amazon",
    "mktp": "",
    "swgy": "swiggy",
    "zmt": "zomato",
    "bms": "bookmyshow",
    "sal": "salary",
}

_UPI_HANDLE = re.compile(r"([a-z0-9.\-_]+)@[a-z0-9]+")
_SEPARATORS = re.compile(r"[^a-z0-9]+")


def _is_noise(word: str) -> bool:
    # Numbers and long digit runs are reference numbers, card digits or amounts;
    # short alphanumerics such as "1mg", "zee5" or "d2h" are brand names
    digits = sum(ch.isdigit() for ch in word)
    return len(word) < 2 or word.isdigit() or digits >= 3 or word in NOISE_WORDS


def normalize_title(title: str | None) -> str:
    """Lowercase, keep only meaningful words: "UPI/SWIGGY/40213/Payment" -> "swiggy"."""
    text = _UPI_HANDLE.sub(r"\1", (title or "").lower())  # "swiggy@icici" -> "swiggy"
    words = (MERCHANT_ALIASES.get(word, word) for word in _SEPARATORS.split(text))
    # dict.fromkeys drops repeats ("BMS*BOOKMYSHOW" -> "bookmyshow") and keeps word order
    return " ".join(dict.fromkeys(word for word in words if not _is_noise(word)))
