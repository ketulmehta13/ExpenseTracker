"""Synthetic training data for the transaction categorizer.

Real transaction titles are private, so the model is trained on generated titles that
mimic Indian bank statements and UPI apps: merchant names, payment-rail noise
("UPI/SWIGGY/40213/Payment"), card descriptors ("AMZN MKTP"), casing and typos.

Each row records the template it came from (`template_id`). Rows from one template are
near-duplicates, so train/test splits must keep a template on one side only; otherwise
the test score measures memorisation, not generalisation.

Usage (from ml-service/):  python -m training.generate_data  -> data/transactions_synthetic.csv
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

# label -> (transaction type, amount range in rupees, title templates)
TEMPLATES: dict[str, tuple[str, tuple[int, int], list[str]]] = {
    "food": ("EXPENSE", (40, 2500), [
        "zomato order", "swiggy dinner", "swiggy instamart", "dominos pizza", "starbucks coffee",
        "chai tapri", "restaurant bill", "mcdonalds burger", "bigbasket groceries", "zepto groceries",
        "lunch with friends", "cafe coffee day", "kfc chicken", "subway sandwich", "haldiram snacks",
        "dmart groceries", "milk and bread", "vegetables market", "fruit vendor", "biryani house",
        "pizza hut", "bakery cakes", "dosa corner", "office canteen",
    ]),
    "travel": ("EXPENSE", (30, 8000), [
        "uber ride", "ola cab", "rapido bike", "petrol pump", "indian oil fuel", "hp petrol",
        "metro card recharge", "bus pass", "fastag toll", "auto rickshaw", "irctc train ticket",
        "indigo flight", "makemytrip booking", "redbus ticket", "parking fee", "airport taxi",
        "shell diesel", "bike service", "car wash", "vistara flight",
    ]),
    "shopping": ("EXPENSE", (200, 15000), [
        "amazon order", "flipkart purchase", "myntra clothes", "ajio fashion", "zara shirt",
        "nike shoes", "ikea furniture", "croma headphones", "reliance digital", "decathlon gear",
        "nykaa beauty", "lifestyle store", "westside clothing", "meesho order", "tata cliq",
        "pantaloons", "boat earphones", "apple store", "lenskart glasses", "mall shopping",
    ]),
    "utilities": ("EXPENSE", (100, 6000), [
        "electricity bill", "bescom bill", "tata power bill", "jio recharge", "airtel postpaid",
        "vi prepaid recharge", "wifi broadband bill", "act fibernet", "water bill", "indane gas cylinder",
        "piped gas bill", "dth recharge", "tata play", "mobile recharge", "bsnl landline",
        "mahanagar gas", "electricity board", "internet bill",
    ]),
    "entertainment": ("EXPENSE", (99, 3000), [
        "netflix subscription", "spotify premium", "bookmyshow movie", "pvr tickets", "inox cinema",
        "steam game", "concert ticket", "prime video", "hotstar subscription", "youtube premium",
        "bowling night", "amusement park", "playstation store", "sonyliv", "zee5 subscription",
        "comedy show", "gaming cafe", "theme park tickets",
    ]),
    "health": ("EXPENSE", (100, 12000), [
        "apollo pharmacy", "doctor consultation", "medplus medicines", "pharmeasy order", "netmeds",
        "dental checkup", "gym membership", "cult fit", "lab test", "thyrocare", "eye checkup",
        "protein supplements", "physiotherapy", "hospital bill", "practo consult", "1mg medicines",
        "yoga classes", "health checkup",
    ]),
    "education": ("EXPENSE", (100, 25000), [
        "udemy course", "coursera fee", "college fees", "book purchase", "exam registration",
        "coaching class", "stationery", "online workshop", "library fine", "tuition payment",
        "byjus subscription", "unacademy plus", "school fees", "kindle books", "certification exam",
        "upgrad course", "language classes",
    ]),
    "rent": ("EXPENSE", (5000, 45000), [
        "house rent", "flat rent", "pg rent", "room rent", "rent to landlord", "nobroker rent",
        "society maintenance", "hostel fees", "monthly rent", "apartment rent", "rent deposit",
        "paying guest rent", "home rent",
    ]),
    "salary": ("INCOME", (15000, 250000), [
        "salary credit", "monthly salary", "salary acme corp", "payroll credit", "stipend",
        "performance bonus", "salary tcs", "salary infosys", "salary wipro", "internship stipend",
        "incentive payout", "salary hcl", "joining bonus", "salary accenture",
    ]),
    "other": ("EXPENSE", (50, 20000), [
        "atm cash withdrawal", "cash withdrawal", "gift for friend", "donation", "temple donation",
        "bank charges", "transfer to friend", "wedding gift", "misc expense", "loan emi",
        "credit card bill payment", "birthday gift", "charity", "late fee", "annual card fee",
        "money sent to mom",
    ]),
}

_TYPO_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def _typo(text: str, rng: random.Random) -> str:
    """Drop, duplicate or swap one character, like a hurried manual entry."""
    if len(text) < 5:
        return text
    i = rng.randrange(1, len(text) - 1)
    kind = rng.choice(["drop", "dup", "swap", "sub"])
    if kind == "drop":
        return text[:i] + text[i + 1 :]
    if kind == "dup":
        return text[:i] + text[i] + text[i:]
    if kind == "swap":
        return text[: i - 1] + text[i] + text[i - 1] + text[i + 1 :]
    return text[:i] + rng.choice(_TYPO_ALPHABET) + text[i + 1 :]


def _render(phrase: str, rng: random.Random) -> str:
    """Turn a template phrase into a title in one of the formats seen in real statements."""
    merchant = phrase.split()[0].upper()
    digits = str(rng.randrange(10_000, 99_999_999))
    style = rng.choices(
        ["plain", "title", "upi", "card", "pos", "ref", "paid", "upper"],
        weights=[30, 20, 15, 8, 5, 8, 7, 7],
    )[0]
    if style == "title":
        text = phrase.title()
    elif style == "upi":
        text = f"UPI/{merchant}/{digits}/{rng.choice(['Payment', 'Pay', 'Order', phrase.split()[-1]])}"
    elif style == "card":
        text = f"{merchant}*{rng.choice(['ORDER', 'PAY', 'ONLINE', 'IN'])} {digits[:6]}"
    elif style == "pos":
        text = f"POS {digits[:6]} {phrase.upper()}"
    elif style == "ref":
        text = f"{phrase} ref {digits}"
    elif style == "paid":
        text = f"paid to {phrase}"
    elif style == "upper":
        text = phrase.upper()
    else:
        text = phrase
    return _typo(text, rng) if rng.random() < 0.15 else text


def generate_dataset(rows_per_label: int = 600, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    records = []
    for label, (tx_type, (low, high), phrases) in TEMPLATES.items():
        for n in range(rows_per_label):
            index = n % len(phrases)
            # Amounts are log-uniform: many small payments, a few large ones
            amount = round(low * (high / low) ** rng.random(), 2)
            records.append({
                "title": _render(phrases[index], rng),
                "amount": amount,
                "type": tx_type,
                "label": label,
                "template_id": f"{label}:{index}",
            })
    return pd.DataFrame.from_records(records).sample(frac=1.0, random_state=seed).reset_index(drop=True)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "transactions_synthetic.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame = generate_dataset()
    frame.to_csv(out, index=False)
    print(f"wrote {len(frame)} rows ({frame['label'].nunique()} labels) to {out}")
