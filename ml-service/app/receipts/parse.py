"""Bill text -> merchant, date, total and item lines. Rules, tuned for Indian bills.

- Numbers are cleaned of OCR's usual mix-ups first (O->0, l->1, S->5 next to digits) and read
  with Indian digit grouping ("1,24,500") or a decimal comma ("12,40").
- The total is found by its keyword, not by size: "Net payable" or "Grand total" beats
  "Total MRP", "Total savings", "Sub total", "Total qty", tax lines and "Cash tendered". Among
  the candidates the strongest keyword wins, then the later line. With no keyword at all, the
  largest amount is used and the result is flagged as a guess.
- The date is the printed date nearest a "date" label, never in the future.
- The merchant is matched against well-known chains (DMart, Reliance, BigBasket, Apollo…) and
  the user's own merchants, with fuzzy matching for OCR typos; otherwise the first name-like
  line at the top, skipping addresses, GSTINs and phone numbers.
- Items are lines with a name and a trailing amount (optionally quantity and rate), between the
  header and the first summary line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from rapidfuzz import fuzz

from app.nlp.quickadd import MONTHS

# ---------- numbers ----------

# A number-like token with OCR look-alikes inside it ("1O19.0O", "l2.40", "S00", "4B.23")
_NUMERIC_TOKEN = re.compile(r"(?<![A-Za-z])[0-9OolISB|]*\d[0-9OolISB|.,]*(?![A-Za-z])")
_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})

_AMOUNT = re.compile(
    r"(?<![\w.,/:-])(?:(?:₹|rs\.?|inr)\s*)?"
    r"(?P<int>\d{1,3}(?:,\d{2,3})*,\d{3}|\d+)"  # 1,24,500 / 1,019 / 1019
    r"(?:[.,](?P<frac>\d{1,2}))?"  # .50, or a decimal comma: 12,40
    r"(?![\w%/:]|[.,]\d)",
    re.IGNORECASE,
)
MAX_AMOUNT = 1e7  # one crore: anything bigger is an id, not a bill
_GLUED_LABEL = re.compile(r"(?i)\b(total|payable|amount|amt)(?=[₹\d])")


def fix_digits(line: str) -> str:
    return _NUMERIC_TOKEN.sub(lambda match: match[0].translate(_LOOKALIKES), line)


@dataclass(frozen=True)
class Amount:
    value: float
    start: int
    has_decimals: bool


def amounts_in(line: str) -> list[Amount]:
    found = []
    for match in _AMOUNT.finditer(line):
        digits = match["int"].replace(",", "")
        if len(digits) >= 7 and "," not in match["int"]:
            continue  # a long bare number is an id or a phone number
        value = float(f"{digits}.{match['frac'] or 0}")
        if 0 < value < MAX_AMOUNT:
            found.append(Amount(value, match.start(), match["frac"] is not None))
    return found


# ---------- keywords ----------

_TOTAL_KEYWORDS = [  # (pattern, strength): the strongest keyword on the bill wins
    (re.compile(r"grand\s*total"), 10),
    (re.compile(r"net\s*payable|amount\s*payable|total\s*payable|payable\s*amount|net\s*to\s*pay"), 9),
    (re.compile(r"net\s*(?:amount|amt|total|value)|invoice\s*(?:total|value|amount)"
                r"|bill\s*(?:amount|amt|total|value)"), 8),
    (re.compile(r"total\s*(?:amount|amt|value|rs|inr)|amount\s*due|total\s*due|order\s*total"), 7),
    (re.compile(r"\bto\s*pay\b|amount\s*paid|paid\s*amount|you\s*pay"), 6),
    (re.compile(r"\btotal\b"), 5),
    (re.compile(r"^\s*(?:sale\s*|txn\s*)?amount\b"), 4),  # a fuel slip's "Amount: Rs 500.00"
]
_NOT_TOTAL = re.compile(
    r"sub\s*-?\s*total|total\s*(?:qty|quantity|items?|no\b|mrp|savings?|discount|tax|gst)|no\.?\s*of\s*items"
    r"|\bsav(?:ed|ings?)\b|discount|\bdisc\b|round(?:ed)?\s*(?:off|ing)|\b[csiu]?gst\b|\btax(?:able)?\b|\bvat\b|\bcess\b"
    r"|tender|\bchange\b|\bmrp\b|cash\s*back|balance|points|loyalty|\bpaid\s*by\b"
)
# "Total (incl. GST)" is a total, not a tax line: the tax words are dropped before the check
_TAX_INCLUDED = re.compile(r"incl(?:\.|uding|usive)?\s*(?:of\s*)?(?:all\s*)?(?:taxes|tax|gst)")
_SUMMARY = re.compile(
    r"total|\b[csiu]?gst\b|\btax\b|\bvat\b|discount|round\s*off|payable|savings|\bnet\b|tender|\bchange\b"
    r"|\bgross\b"
)
_ITEM_HEADER = re.compile(r"\b(?:item|items|description|particulars|product|qty|quantity)\b")
_NOT_ITEM = re.compile(
    r"cashier|counter|\bbill\b|invoice|\btable\b|\btime\b|\bdate\b|\bph(?:one)?\b|\btel\b|gstin|\bgst\b|fssai|\bcin\b"
    r"|\bpos\b|\btxn\b|\bref\b|\bcard\b|\bupi\b|\bmode\b|terminal|token|\border\b|\bkot\b|mobile|customer|\bno\b\.?\s*:"
    r"|\bmob\b|\bmo\b\.?|whatsapp|contact|\bcell\b"
)
_ADDRESS = re.compile(
    r"road|\brd\b|street|\bst\b\.|nagar|marg|lane|sector|\bplot\b|floor|\bshop\b\s*no|building|complex|mall"
    r"|near|opp\.?|\bpin\b|\d{6}|highway|chowk|society|colony|gstin|\bph\b|phone|\btel\b|www\.|\.com|@|cin\b|fssai"
)
_DATE_LABEL = re.compile(r"\bdate\b|\bdt\b|dated|bill\s*date|invoice\s*date|order\s*date")
_DOCUMENT_WORDS = re.compile(r"tax\s*invoice|\binvoice\b|\breceipt\b|\bbill\b")

# ---------- dates ----------

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})\s?[/.-]\s?(\d{1,2})\s?[/.-]\s?(\d{4}|\d{2})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?!\d)")
_DAY_MONTH = re.compile(
    rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s/.,-]*({_MONTH})[a-z]*\.?[\s/.,'-]*(\d{{4}}|\d{{2}})?(?![a-z\d])"
)
_MONTH_DAY = re.compile(rf"\b({_MONTH})[a-z]*\.?[\s.-]*(\d{{1,2}})(?:st|nd|rd|th)?[\s,'-]+(\d{{4}})\b")
MAX_BILL_AGE_DAYS = 3 * 365


def _valid_date(year: int | None, month: int, day: int, today: date) -> date | None:
    if year is not None and year < 100:
        year += 2000
    try:
        if year is None:
            found = date(today.year, month, day)
            found = found if found <= today else date(today.year - 1, month, day)
        else:
            found = date(year, month, day)
    except ValueError:
        return None
    if found > today + timedelta(days=1) or found < today - timedelta(days=MAX_BILL_AGE_DAYS):
        return None
    return found


def dates_in(line: str, today: date) -> list[date]:
    text = line.lower()
    found = []
    for match in _ISO_DATE.finditer(text):
        found.append(_valid_date(int(match[1]), int(match[2]), int(match[3]), today))
    for match in _NUMERIC_DATE.finditer(text):
        # Day first, as written in India
        found.append(_valid_date(int(match[3]), int(match[2]), int(match[1]), today))
    for match in _DAY_MONTH.finditer(text):
        found.append(_valid_date(int(match[3]) if match[3] else None, MONTHS[match[2]], int(match[1]), today))
    for match in _MONTH_DAY.finditer(text):
        found.append(_valid_date(int(match[3]), MONTHS[match[1]], int(match[2]), today))
    return [value for value in found if value is not None]


# ---------- merchants ----------

# display name -> how it appears on bills (lower case)
KNOWN_MERCHANTS: dict[str, tuple[str, ...]] = {
    "DMart": ("dmart", "d-mart", "d mart", "avenue supermarts"),
    "Reliance Smart": ("reliance smart", "smart bazaar", "smart point", "reliance retail"),
    "Reliance Fresh": ("reliance fresh",),
    "JioMart": ("jiomart", "jio mart"),
    "More": ("more supermarket", "more megastore", "more retail", "more hypermarket"),
    "BigBasket": ("bigbasket", "big basket", "bbdaily", "innovative retail concepts"),
    "Blinkit": ("blinkit", "grofers", "blink commerce"),
    "Zepto": ("zepto", "kiranakart"),
    "Swiggy Instamart": ("instamart",),
    "Swiggy": ("swiggy", "bundl technologies"),
    "Zomato": ("zomato",),
    "Star Bazaar": ("star bazaar", "trent hypermarket"),
    "Spencer's": ("spencer's", "spencers"),
    "Nature's Basket": ("nature's basket", "natures basket"),
    "Vishal Mega Mart": ("vishal mega mart", "vishal megamart"),
    "Ratnadeep": ("ratnadeep",),
    "Spar": ("spar hypermarket", "spar india"),
    "Lulu": ("lulu hypermarket", "lulu mall"),
    "Metro Cash & Carry": ("metro cash", "metro wholesale"),
    "Apollo Pharmacy": ("apollo pharmacy", "apollo pharmacies"),
    "MedPlus": ("medplus", "med plus"),
    "Wellness Forever": ("wellness forever",),
    "Netmeds": ("netmeds",),
    "Tata 1mg": ("1mg",),
    "PharmEasy": ("pharmeasy",),
    "Indian Oil": ("indian oil", "iocl"),
    "Bharat Petroleum": ("bharat petroleum", "bpcl"),
    "HP Petrol": ("hindustan petroleum", "hpcl"),
    "Shell": ("shell india", "shell petrol"),
    "Amazon": ("amazon",),
    "Flipkart": ("flipkart",),
    "Myntra": ("myntra",),
    "Ajio": ("ajio",),
    "Nykaa": ("nykaa",),
    "Decathlon": ("decathlon",),
    "Croma": ("croma", "infiniti retail"),
    "Reliance Digital": ("reliance digital",),
    "Vijay Sales": ("vijay sales",),
    "IKEA": ("ikea",),
    "Westside": ("westside",),
    "Pantaloons": ("pantaloons",),
    "Max Fashion": ("max fashion",),
    "Lifestyle": ("lifestyle international",),
    "Shoppers Stop": ("shoppers stop",),
    "Domino's": ("domino's", "dominos", "jubilant foodworks"),
    "McDonald's": ("mcdonald", "hardcastle restaurants"),
    "KFC": ("kfc",),
    "Pizza Hut": ("pizza hut",),
    "Burger King": ("burger king",),
    "Subway": ("subway",),
    "Starbucks": ("starbucks", "tata starbucks"),
    "Cafe Coffee Day": ("cafe coffee day", "coffee day"),
    "Haldiram's": ("haldiram",),
    "Barbeque Nation": ("barbeque nation", "barbecue nation"),
}
_ALIASES = [(alias, name) for name, aliases in KNOWN_MERCHANTS.items() for alias in aliases]
_HEADER_LINES = 8


def _letters_share(text: str) -> float:
    stripped = text.replace(" ", "")
    return sum(char.isalpha() for char in stripped) / len(stripped) if stripped else 0.0


def find_merchant(lines: list[str], own_merchants: list[str] = ()) -> str | None:
    header = [line.lower() for line in lines[:_HEADER_LINES]]
    text = " \n ".join(line.lower() for line in lines)
    # 1. A well-known chain, anywhere on the bill (invoices print the brand in the footer too)
    for alias, name in sorted(_ALIASES, key=lambda pair: -len(pair[0])):
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text):
            return name
    # 2. The same, allowing OCR typos, in the header
    for line in header:
        for alias, name in _ALIASES:
            # One OCR typo in a 7-letter name scores 86: allow it for longer names, not short ones
            if len(alias) >= 6 and fuzz.partial_ratio(alias, line) >= 85:
                return name
    # 3. One of the user's own merchants, matched against the header
    for line in header:
        if len(line) >= 3 and own_merchants:
            best = max(own_merchants, key=lambda merchant: fuzz.token_set_ratio(merchant.lower(), line))
            if fuzz.token_set_ratio(best.lower(), line) >= 92 and len(best) >= 3:
                return best
    # 4. The first name-like line at the top
    for line in lines[:5]:
        clean = re.sub(r"[^A-Za-z0-9&'. -]", " ", line).strip(" .-")
        clean = " ".join(clean.split())
        lowered = clean.lower()
        if 3 <= len(clean) <= 40 and _letters_share(clean) >= 0.6 and not _ADDRESS.search(lowered) \
                and not _DATE_LABEL.search(lowered) and not _DOCUMENT_WORDS.search(lowered):
            return clean.title() if clean.isupper() else clean
    return None


# ---------- items ----------

@dataclass(frozen=True)
class ReceiptItem:
    name: str
    amount: float
    line: int


_LEADING_SERIAL = re.compile(r"^\s*(?:\d{1,3}[.)]?\s+)(?=[A-Za-z])")
_HSN = re.compile(r"(?<![\w.])\d{4,8}(?![\w.])")
_EXPIRY = re.compile(r"(?<![\w/])\d{1,2}/\d{2,4}(?![\w/])")  # a pharmacy's batch expiry, "08/27"
_QTY_UNIT = re.compile(r"^\d+(?:\.\d+)?\s*(?:x|nos?|pcs?|qty|kg|g|gm|ml|l|ltr|pc|pkt)?$", re.IGNORECASE)


def _parse_item(line: str, index: int, today: date) -> ReceiptItem | None:
    lowered = line.lower()
    if _NOT_ITEM.search(lowered) or _SUMMARY.search(lowered) or dates_in(lowered, today):
        return None
    tokens = line.split()
    numbers: list[str] = []
    while tokens and len(numbers) < 4 and (amounts_in(tokens[-1]) or _QTY_UNIT.match(tokens[-1])
                                            or tokens[-1] in {"x", "X", "@", "-", "="}):
        numbers.insert(0, tokens.pop())
    raw_name = " ".join(tokens)
    if ":" in raw_name:  # "Amount: Rs 500.00" is a labelled field, not an item
        return None
    name = _LEADING_SERIAL.sub("", raw_name)
    name = " ".join(_HSN.sub(" ", _EXPIRY.sub(" ", name)).split()).strip(" .-*=")
    if not numbers or _letters_share(name) < 0.3 or len(name) < 2:
        return None
    found = [amount for token in numbers for amount in amounts_in(token)]
    if not found:
        return None
    last = found[-1]
    if len(numbers) == 1 and not last.has_decimals and last.value < 10:
        return None  # "Banana 6" is a quantity, not a price
    if not last.has_decimals and last.value >= 100_000:
        return None  # a PIN code or an id, not a price
    return ReceiptItem(name, round(last.value, 2), index)


def find_items(lines: list[str], today: date) -> list[ReceiptItem]:
    lowered = [line.lower() for line in lines]
    # A table header has no amount on it ("Item Total ₹295" is a summary, not a header)
    headers = (i + 1 for i, line in enumerate(lowered[:15])
               if _ITEM_HEADER.search(line) and not amounts_in(line))
    start = next(headers, 0)
    summaries = (i for i in range(start, len(lowered))
                 if _SUMMARY.search(lowered[i]) and amounts_in(lines[i]))
    end = next(summaries, len(lines))
    items = []
    index = start
    while index < end:
        item = _parse_item(lines[index], index, today)
        # OCR can split a row: a name without its price, then a row of only numbers
        if item is None and index + 1 < end and _letters_share(lines[index]) > 0.5 \
                and _letters_share(lines[index + 1]) < 0.2 and amounts_in(lines[index + 1]):
            merged = _parse_item(f"{lines[index]} {lines[index + 1]}", index, today)
            if merged is not None:
                items.append(merged)
                index += 2
                continue
        if item is not None:
            items.append(item)
        index += 1
    return items


# ---------- the whole bill ----------

@dataclass
class ReceiptDraft:
    merchant: str | None
    date: date | None
    total: float | None
    items: list[ReceiptItem] = field(default_factory=list)
    subtotal: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def found(self) -> dict[str, bool]:
        return {"merchant": self.merchant is not None, "date": self.date is not None,
                "total": self.total is not None and "total_guessed" not in self.warnings}


def _line_amount(lines: list[str], index: int) -> Amount | None:
    """The amount for a keyword line: on the line itself, else on a following line that is only a number."""
    if found := amounts_in(lines[index]):
        return found[-1]
    for neighbour in (index + 1, index - 1):
        if 0 <= neighbour < len(lines) and _letters_share(lines[neighbour]) < 0.3 \
                and (found := amounts_in(lines[neighbour])):
            return found[-1]
    return None


def find_total(lines: list[str]) -> tuple[float | None, bool]:
    """(total, guessed): guessed when no total keyword was found and the largest amount was used."""
    best: tuple[int, int, float] | None = None
    for index, line in enumerate(lines):
        lowered = _TAX_INCLUDED.sub(" ", line.lower())
        if _NOT_TOTAL.search(lowered):
            continue
        strength = max((weight for pattern, weight in _TOTAL_KEYWORDS if pattern.search(lowered)), default=0)
        if strength and (amount := _line_amount(lines, index)) is not None:
            candidate = (strength, index, amount.value)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is not None:
        return round(best[2], 2), False
    plain = [line for line in lines
             if not _NOT_TOTAL.search(line.lower()) and not _NOT_ITEM.search(line.lower())]
    pool = [amount.value for line in plain for amount in amounts_in(line) if amount.has_decimals]
    return (round(max(pool), 2), True) if pool else (None, False)


def find_date(lines: list[str], today: date) -> date | None:
    scored = []
    for index, line in enumerate(lines):
        for found in dates_in(line, today):
            labelled = bool(_DATE_LABEL.search(line.lower()))
            scored.append((labelled, -index, found))
    return max(scored)[2] if scored else None


def find_subtotal(lines: list[str]) -> float | None:
    for index, line in enumerate(lines):
        if re.search(r"sub\s*-?\s*total", line.lower()) and (amount := _line_amount(lines, index)):
            return amount.value
    return None


def parse_receipt(raw_lines: list[str], today: date, own_merchants: list[str] = ()) -> ReceiptDraft:
    # OCR can drop the gap between a label and its number: "Total703" -> "Total 703"
    lines = [_GLUED_LABEL.sub(r"\1 ", fix_digits(" ".join(line.split())))
             for line in raw_lines if line and line.strip()]
    total, guessed = find_total(lines)
    draft = ReceiptDraft(
        merchant=find_merchant(lines, own_merchants),
        date=find_date(lines, today),
        total=total,
        items=find_items(lines, today),
        subtotal=find_subtotal(lines),
    )
    if total is None:
        draft.warnings.append("no_total")
    elif guessed:
        draft.warnings.append("total_guessed")
    if draft.date is None:
        draft.warnings.append("no_date")
    if draft.merchant is None:
        draft.warnings.append("no_merchant")
    if not draft.items:
        draft.warnings.append("no_items")
    return draft
