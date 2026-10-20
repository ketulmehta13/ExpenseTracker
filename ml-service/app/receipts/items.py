"""Bill items -> category groups, so one supermarket bill can become several transactions.

1. Each item is put in a group (groceries, household, personal care, health…) by a keyword
   lexicon of Indian products and brands. Multi-word phrases ("surf excel") count double, and
   OCR typos are tolerated by fuzzy matching single words ("detergnt").
2. Some bills are one kind of spend whatever the items say: a restaurant bill is dining, a fuel
   slip is fuel, a pharmacy bill defaults to health.
3. Items no rule recognises join the bill's main group.
4. Groups are mapped to the user's categories: a category named like the group first
   ("Groceries", "Household"), else the canonical label's category (groceries -> Food,
   household -> Shopping). Groups that land on the same category are merged.
5. Tax, discounts and round-off make the items not add up to the total; the difference is
   spread across the groups in proportion, so the transactions add up to the bill exactly.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.ml.taxonomy import match_user_category
from app.receipts.parse import ReceiptItem

# group -> (display name, canonical category label, names a user might give such a category)
GROUPS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "groceries": ("Groceries", "food", ("groceries", "grocery", "kirana", "provisions", "food")),
    "dining": ("Dining", "food", ("dining", "dining out", "restaurants", "eating out", "food")),
    "household": ("Household", "shopping", ("household", "home supplies", "home needs", "cleaning")),
    "personal_care": ("Personal care", "shopping", ("personal care", "toiletries", "self care", "grooming",
                                                     "beauty")),
    "health": ("Health", "health", ("health", "medical", "medicine", "medicines", "pharmacy", "healthcare")),
    "baby": ("Baby care", "shopping", ("baby", "baby care", "kids", "children")),
    "pet": ("Pet care", "other", ("pet", "pets", "pet care")),
    "stationery": ("Stationery", "education", ("stationery", "office supplies", "education")),
    "electronics": ("Electronics", "shopping", ("electronics", "gadgets")),
    "clothing": ("Clothing", "shopping", ("clothing", "clothes", "fashion", "apparel")),
    "fuel": ("Fuel", "travel", ("fuel", "petrol", "diesel", "travel", "transport")),
    "other": ("Other", "other", ("other", "misc", "miscellaneous")),
}

KEYWORDS: dict[str, set[str]] = {
    "groceries": {
        "atta", "aata", "flour", "maida", "rice", "basmati", "dal", "daal", "toor", "tur", "moong", "masoor",
        "urad", "chana", "rajma", "sugar", "salt", "jaggery", "gud", "oil", "ghee", "butter", "milk", "curd",
        "dahi", "paneer", "cheese", "bread", "pav", "bun", "eggs", "egg", "biscuit", "biscuits", "cookies",
        "namkeen", "bhujia", "chips", "maggi", "noodles", "pasta", "oats", "cornflakes", "muesli", "poha",
        "suji", "sooji", "rava", "besan", "tea", "coffee", "masala", "haldi", "turmeric", "chilli", "chili",
        "mirchi", "jeera", "cumin", "mustard", "rai", "pickle", "achar", "jam", "ketchup", "sauce", "honey",
        "almond", "almonds", "badam", "cashew", "kaju", "raisins", "kishmish", "peanut", "peanuts",
        "vegetable", "vegetables", "veg", "potato", "aloo", "onion", "pyaz", "tomato", "banana", "apple",
        "mango", "orange", "grapes", "papaya", "fruit", "fruits", "coriander", "dhania", "ginger", "garlic",
        "lemon", "chocolate", "juice", "frooti", "maaza", "cola", "pepsi", "coke", "sprite", "bisleri",
        "kinley", "water", "amul", "britannia", "parle", "haldiram", "lays", "kurkure", "fortune", "saffola",
        "aashirvaad", "ashirvad", "aashirvad", "patanjali", "everest", "mdh", "kissan", "knorr", "nescafe",
        "bru", "taj", "brooke", "cadbury", "kitkat", "dairy", "yogurt", "lassi", "chaas", "spinach", "palak",
        "cabbage", "cauliflower", "gobi", "carrot", "cucumber", "brinjal", "capsicum", "peas", "corn",
        "soya", "chicken", "mutton", "fish", "prawns", "idli", "dosa", "batter", "ragi", "jowar",
        "bajra", "millet", "vermicelli", "sewai", "custard", "icecream", "kulfi", "sweets", "mithai",
        "ladoo", "rusk", "toast", "khari", "cake", "muffin", "cereal", "fresh cream", "ice cream",
        "milk powder", "chocos", "horlicks", "bournvita",
        "boost", "complan", "nutella", "mayonnaise", "vinegar", "soda", "coconut", "nariyal", "tamarind",
        "imli", "cardamom", "elaichi", "clove", "pepper", "cinnamon", "hing", "methi", "ajwain",
    },
    "household": {
        "detergent", "surf", "ariel", "tide", "rin", "wheel", "nirma", "ghadi", "vim", "pril", "exo",
        "harpic", "lizol", "domex", "colin", "phenyl", "cleaner", "dishwash", "dishwasher", "scrubber",
        "scotch brite", "scotchbrite", "garbage bag", "garbage bags", "trash bag", "dustbin", "tissue",
        "tissues", "napkin", "napkins", "toilet paper", "toilet roll", "kitchen towel", "foil",
        "cling wrap", "mop", "broom", "jhadu", "bucket", "candle", "candles", "matchbox", "agarbatti",
        "incense", "dhoop", "mosquito", "good knight", "goodknight", "all out", "allout", "mortein",
        "odonil", "air freshener", "freshener", "comfort", "fabric conditioner", "ujala", "bleach",
        "naphthalene", "battery", "batteries", "bulb", "led bulb", "extension board", "hanger", "hangers",
        "container", "tiffin", "bottle", "lunch box", "sponge", "wiper", "duster", "wipes kitchen",
        "toilet brush", "cleaning brush", "detergent powder", "washing powder",
        "surf excel", "vim bar", "vim liquid", "pril liquid", "lizol floor", "harpic toilet",
    },
    "personal_care": {
        "soap", "lux", "dove", "lifebuoy", "santoor", "pears", "cinthol", "medimix", "hamam", "shampoo",
        "conditioner", "clinic plus", "sunsilk", "pantene", "head & shoulders", "head and shoulders",
        "toothpaste", "colgate", "pepsodent", "close up", "closeup", "sensodyne", "dabur red",
        "toothbrush", "brush", "facewash", "face wash", "himalaya", "cream", "lotion", "nivea", "vaseline",
        "ponds", "pond's", "glow & lovely", "fair & lovely", "deodorant", "deo", "perfume", "body spray",
        "razor", "gillette", "shaving", "shave", "aftershave", "sanitary", "whisper", "stayfree", "sofy",
        "hair oil", "parachute", "kesh king", "dabur amla", "kajal", "lipstick", "nail polish", "sunscreen",
        "handwash", "hand wash", "sanitizer", "sanitiser", "talc", "comb", "cotton buds",
        "mouthwash", "listerine", "floss", "lip balm", "talc powder", "face powder", "hair gel",
        "moisturiser", "moisturizer", "serum", "scrub",
        "bodywash", "body wash", "shower gel", "dettol soap", "lifebuoy handwash", "veet", "trimmer",
    },
    "health": {
        "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "syrup", "paracetamol", "crocin",
        "dolo", "calpol", "combiflam", "vicks", "strepsils", "ors", "electral", "bandage", "band-aid",
        "bandaid", "antiseptic", "dettol liquid", "savlon", "thermometer", "vitamin", "multivitamin",
        "zincovit", "becosules", "limcee", "digene", "eno", "pudin hara", "ointment", "cough", "cold",
        "mask", "masks", "gloves", "insulin", "medicine", "injection", "drops", "inhaler",
        "antacid", "pantoprazole", "pan 40", "azithromycin", "amoxicillin", "cetirizine", "allegra",
        "volini", "moov", "iodex", "glucon", "protein powder", "whey", "supplement", "bp monitor",
    },
    "baby": {
        "diaper", "diapers", "pampers", "huggies", "mamypoko", "baby wipes", "wipes", "cerelac",
        "lactogen", "nan pro", "baby oil", "baby lotion", "baby powder", "johnson's baby", "johnsons baby",
        "feeding bottle", "himalaya baby", "teether",
    },
    "pet": {"dog food", "cat food", "pedigree", "whiskas", "drools", "pet food", "cat litter", "dog treats"},
    "stationery": {
        "notebook", "notebooks", "pen", "pens", "pencil", "pencils", "eraser", "sharpener", "register",
        "a4", "paper", "stapler", "glue", "fevicol", "fevistick", "marker", "highlighter", "file", "folder",
        "envelope", "sellotape", "cello tape", "scale", "geometry box", "crayons", "sketch pens",
    },
    "electronics": {
        "charger", "cable", "usb", "earphones", "earbuds", "headphones", "mouse", "keyboard", "power bank",
        "pendrive", "memory card", "adapter", "speaker", "smartwatch", "hdmi",
    },
    "clothing": {
        "shirt", "t-shirt", "tshirt", "tee", "jeans", "trouser", "trousers", "kurta", "kurti", "saree",
        "socks", "innerwear", "vest", "brief", "briefs", "bra", "leggings", "shorts", "jacket", "sweater",
        "shoes", "slippers", "chappal", "sandals", "dupatta", "nightwear", "pyjama", "towel", "handkerchief",
    },
    "fuel": {"petrol", "diesel", "cng", "fuel", "speed", "power petrol", "xtrapremium", "xp95"},
}
_SINGLE_WORDS = {word: group for group, words in KEYWORDS.items() for word in words if " " not in word}
_PHRASES = [(phrase, group) for group, words in KEYWORDS.items() for phrase in words if " " in phrase]
_VOCABULARY = [word for word in _SINGLE_WORDS if len(word) >= 5]
_LONG_WORDS = [word for word in _SINGLE_WORDS if len(word) >= 4]

_RESTAURANT_CUES = re.compile(
    r"\btable\b|\bcovers?\b|\bkot\b|service\s*charge|dine[\s-]*in|restaurant|\bcafe\b|\bcaf[eé]\b|\bsteward\b"
    r"|\bpax\b|\bguests?\b|food\s*bill"
)
_FUEL_CUES = re.compile(
    r"\bpetrol\b|\bdiesel\b|\bcng\b|\bnozzle\b|\bpump\b|\bvolume\b.*\b(?:l|ltr)\b|\bfuel\b"
)
_PHARMACY_CUES = re.compile(
    r"pharma|chemist|druggist|medical\s*store|\brx\b|apollo|medplus|netmeds|1mg|pharmeasy"
)
_DINING_MERCHANTS = {"Domino's", "McDonald's", "KFC", "Pizza Hut", "Burger King", "Subway", "Starbucks",
                     "Cafe Coffee Day", "Barbeque Nation", "Swiggy", "Zomato", "Haldiram's"}
_FUEL_MERCHANTS = {"Indian Oil", "Bharat Petroleum", "HP Petrol", "Shell"}
_PHARMACY_MERCHANTS = {"Apollo Pharmacy", "MedPlus", "Wellness Forever", "Netmeds", "Tata 1mg", "PharmEasy"}


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9&' -]", " ", text.lower()).split())


def classify_item(name: str) -> str | None:
    """The group an item belongs to, or None when nothing recognises it."""
    text = _normalize(name)
    tokens = re.findall(r"[a-z0-9]+", text)  # "parle-g" -> "parle", "g"
    scores: Counter[str] = Counter()
    for phrase, group in _PHRASES:
        if phrase in text:
            scores[group] += 2
    for token in tokens:
        if token in _SINGLE_WORDS:
            scores[_SINGLE_WORDS[token]] += 1
        elif len(token) >= 5 and (match := process.extractOne(token, _VOCABULARY, scorer=fuzz.ratio,
                                                                score_cutoff=85)):
            scores[_SINGLE_WORDS[match[0]]] += 1  # an OCR typo of a known word
        elif len(token) >= 7 and (inside := [word for word in _LONG_WORDS if word in token]):
            scores[_SINGLE_WORDS[max(inside, key=len)]] += 1  # words OCR ran together: "tatasalt"
    if not scores:
        return None
    best = max(scores.values())
    # Ties go to the more specific group: a "Dettol soap" is personal care, not health
    for group in ("baby", "pet", "personal_care", "household", "health", "stationery", "electronics",
                  "clothing", "fuel", "groceries"):
        if scores.get(group) == best:
            return group
    return None


def bill_kind(merchant: str | None, lines: list[str]) -> str | None:
    """A whole-bill group when the kind of shop decides it: dining, fuel, or health for a pharmacy."""
    text = " ".join(lines).lower()
    if merchant in _DINING_MERCHANTS or _RESTAURANT_CUES.search(text):
        return "dining"
    if merchant in _FUEL_MERCHANTS or _FUEL_CUES.search(text):
        return "fuel"
    if merchant in _PHARMACY_MERCHANTS or _PHARMACY_CUES.search(text):
        return "health"
    return None


@dataclass
class GroupedItem:
    name: str
    amount: float
    group: str


@dataclass
class Group:
    key: str  # a group name, or several joined by "+" after merging
    name: str
    category: dict | None
    items: list[GroupedItem] = field(default_factory=list)
    amount: float = 0.0


def resolve_category(group: str, categories: list[dict]) -> dict | None:
    """The user's category for a group: one named like the group first, else the canonical label's."""
    aliases = set(GROUPS[group][2])
    named = [c for c in categories if _normalize(c["name"]) in aliases and _normalize(c["name"]) != "food"]
    if named:
        return min(named, key=lambda c: c.get("user_id") is None)  # their own category over a default
    return match_user_category(GROUPS[group][1], categories)


def group_items(
    items: list[ReceiptItem],
    total: float | None,
    categories: list[dict],
    merchant: str | None = None,
    lines: list[str] = (),
) -> tuple[list[Group], float, list[str]]:
    """(groups, adjustment, warnings): adjustment is the total minus the item sum, spread over the groups."""
    warnings: list[str] = []
    if not items:
        return [], 0.0, warnings
    whole_bill = bill_kind(merchant, list(lines))
    grouped = []
    for item in items:
        group = whole_bill if whole_bill in ("dining", "fuel") else classify_item(item.name)
        grouped.append(GroupedItem(item.name, item.amount, group or ""))
    known = Counter(item.group for item in grouped if item.group)
    fallback = whole_bill or (known.most_common(1)[0][0] if known else "other")
    for item in grouped:
        item.group = item.group or fallback

    # Groups landing on the same category become one transaction
    merged: dict[str, Group] = {}
    for item in grouped:
        category = resolve_category(item.group, categories)
        key = f"category:{category['id']}" if category else f"group:{item.group}"
        name = category["name"] if category else GROUPS[item.group][0]
        group = merged.setdefault(key, Group(item.group, name, category))
        if item.group not in group.key.split("+"):
            group.key = f"{group.key}+{item.group}"
        group.items.append(item)
        group.amount += item.amount
    groups = sorted(merged.values(), key=lambda g: -g.amount)

    items_total = round(sum(item.amount for item in grouped), 2)
    adjustment = round((total if total is not None else items_total) - items_total, 2)
    if items_total > 0 and abs(adjustment) <= 0.25 * items_total:
        # Spread tax, discount and round-off in proportion; the last paisa goes to the biggest group
        for group in groups:
            group.amount = round(group.amount + adjustment * group.amount / items_total, 2)
        residual = (items_total + adjustment) - sum(g.amount for g in groups)
        groups[0].amount = round(groups[0].amount + residual, 2)
    else:
        warnings.append("items_dont_add_up")
        for group in groups:
            group.amount = round(group.amount, 2)
    return groups, adjustment, warnings
