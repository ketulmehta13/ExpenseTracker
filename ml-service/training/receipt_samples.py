"""Synthetic Indian bills with known answers, for developing and testing bill scanning.

Six layouts, each with its own quirks:
- supermarket: company name above the store name, item table with qty and rate, Total Qty,
  Sub Total, CGST/SGST, Round Off, "Net Payable", "You Saved", cash tendered and change;
- quick commerce: a tax-invoice PDF with "qty x price" lines, fees and a discount;
- pharmacy: batch numbers and expiry dates inside the item lines;
- restaurant: table and covers, service charge, GST, "Grand Total";
- fuel slip: one product, rate, volume and amount;
- kirana: a few hand-totalled lines without decimals.

`noisy()` adds OCR-style damage to the text: look-alike characters inside numbers, a row split
in two, a missing space. The hand-written test set (data/receipts_test.jsonl) is separate:
different stores, abbreviated item names, layouts this generator doesn't produce.

Usage (from ml-service/):
    python -m training.receipt_samples --write-dev   # writes data/receipts_dev.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
TODAY = date(2026, 10, 19)

# (name on the bill, price range, group)
CATALOG: dict[str, list[tuple[str, tuple[float, float]]]] = {
    "groceries": [
        ("TATA SALT 1KG", (28, 30)),
        ("AASHIRVAAD ATTA 5KG", (230, 260)),
        ("FORTUNE SUNFLOWER OIL 1L", (150, 180)),
        ("AMUL BUTTER 500G", (265, 285)),
        ("AMUL TAAZA MILK 1L", (54, 56)),
        ("BRITANNIA BREAD 400G", (40, 50)),
        ("PARLE-G 250G", (25, 30)),
        ("MAGGI NOODLES 280G", (52, 60)),
        ("TATA TEA GOLD 500G", (280, 320)),
        ("BRU INSTANT COFFEE 100G", (230, 260)),
        ("INDIA GATE BASMATI 1KG", (140, 180)),
        ("TOOR DAL 1KG", (150, 180)),
        ("SUGAR 1KG", (44, 50)),
        ("EVEREST GARAM MASALA 100G", (70, 85)),
        ("HALDIRAM BHUJIA 400G", (95, 110)),
        ("KISSAN KETCHUP 950G", (125, 140)),
        ("AMUL PANEER 200G", (85, 95)),
        ("EGGS 12 PCS", (80, 95)),
        ("ONION 1KG", (35, 60)),
        ("POTATO 1KG", (30, 45)),
        ("TOMATO 1KG", (30, 70)),
        ("BANANA ROBUSTA", (40, 60)),
        ("APPLE SHIMLA 1KG", (140, 200)),
        ("CADBURY DAIRY MILK 50G", (40, 50)),
        ("SAFFOLA OATS 1KG", (190, 210)),
        ("BESAN 500G", (55, 65)),
        ("POHA 1KG", (60, 75)),
        ("AMUL MASTI DAHI 400G", (35, 45)),
        ("COCA COLA 750ML", (40, 45)),
    ],
    "household": [
        ("SURF EXCEL MATIC 1KG", (210, 240)),
        ("ARIEL MATIC 1KG", (280, 300)),
        ("VIM BAR 300G", (20, 30)),
        ("VIM LIQUID 500ML", (105, 115)),
        ("HARPIC 500ML", (95, 110)),
        ("LIZOL FLOOR CLEANER 975ML", (190, 215)),
        ("SCOTCH BRITE SCRUBBER", (30, 40)),
        ("GARBAGE BAGS MEDIUM", (90, 120)),
        ("GOOD KNIGHT REFILL", (75, 85)),
        ("ODONIL 50G", (55, 60)),
        ("RIN BAR 250G", (22, 28)),
        ("COLIN GLASS CLEANER 500ML", (99, 110)),
        ("TISSUE ROLL 4 PCS", (120, 160)),
        ("ALUMINIUM FOIL 9M", (90, 110)),
        ("EXO DISHWASH BAR", (30, 40)),
    ],
    "personal_care": [
        ("COLGATE STRONG TEETH 200G", (95, 110)),
        ("PEPSODENT 150G", (75, 90)),
        ("DOVE SOAP 3X100G", (165, 190)),
        ("LIFEBUOY SOAP 4X125G", (140, 160)),
        ("CLINIC PLUS SHAMPOO 340ML", (180, 210)),
        ("PARACHUTE HAIR OIL 200ML", (95, 120)),
        ("NIVEA CREME 100ML", (180, 210)),
        ("GILLETTE GUARD RAZOR", (30, 40)),
        ("WHISPER ULTRA XL", (180, 210)),
        ("HIMALAYA FACE WASH 100ML", (140, 170)),
        ("DETTOL HANDWASH 200ML", (90, 105)),
        ("PONDS TALC 100G", (90, 110)),
    ],
    "health": [
        ("DOLO 650 TAB 15S", (30, 35)),
        ("CROCIN ADVANCE TAB 15S", (25, 35)),
        ("VICKS VAPORUB 50ML", (140, 160)),
        ("ELECTRAL ORS SACHET", (20, 25)),
        ("BAND-AID 10S", (40, 50)),
        ("DIGENE SYRUP 200ML", (120, 140)),
        ("ZINCOVIT TAB 15S", (105, 115)),
        ("STREPSILS 8S", (40, 45)),
        ("BECOSULES CAP 20S", (50, 60)),
        ("SAVLON ANTISEPTIC 100ML", (70, 85)),
    ],
    "baby": [
        ("PAMPERS DIAPER M 20", (380, 450)),
        ("HUGGIES WIPES 72", (150, 180)),
        ("CERELAC WHEAT 300G", (220, 260)),
    ],
    "stationery": [
        ("CLASSMATE NOTEBOOK 172P", (50, 70)),
        ("REYNOLDS PEN 5 PCS", (40, 55)),
        ("FEVISTICK 15G", (25, 35)),
    ],
    "dining": [
        ("PANEER BUTTER MASALA", (260, 340)),
        ("DAL MAKHANI", (220, 280)),
        ("BUTTER NAAN", (50, 70)),
        ("JEERA RICE", (160, 200)),
        ("VEG BIRYANI", (240, 300)),
        ("MASALA DOSA", (110, 150)),
        ("COLD COFFEE", (120, 160)),
        ("FRESH LIME SODA", (80, 110)),
        ("GULAB JAMUN 2 PCS", (80, 110)),
        ("CHICKEN TIKKA", (300, 380)),
    ],
}

SUPERMARKETS = [
    ("DMart", ["AVENUE SUPERMARTS LTD", "D-MART"]),
    ("Reliance Smart", ["RELIANCE RETAIL LTD", "SMART BAZAAR"]),
    ("More", ["MORE RETAIL PVT LTD", "MORE SUPERMARKET"]),
    ("Star Bazaar", ["TRENT HYPERMARKET PVT LTD", "STAR BAZAAR"]),
    ("Spencer's", ["SPENCER'S RETAIL LTD", "SPENCER'S"]),
    ("Vishal Mega Mart", ["VISHAL MEGA MART PVT LTD", "VISHAL MEGA MART"]),
]
QUICK_COMMERCE = [
    ("Blinkit", "Blinkit (Blink Commerce Pvt Ltd)"),
    ("Zepto", "Zepto (Kiranakart Technologies Pvt Ltd)"),
    ("Swiggy Instamart", "Swiggy Instamart"),
    ("BigBasket", "bigbasket - Innovative Retail Concepts"),
]
PHARMACIES = [
    ("Apollo Pharmacy", "APOLLO PHARMACY"),
    ("MedPlus", "MEDPLUS MART"),
    ("Shree Balaji Medical Store", "SHREE BALAJI MEDICAL STORE"),
]
RESTAURANTS = [
    "The Green Leaf Restaurant",
    "Sagar Ratna",
    "Hotel Shivam",
    "Cafe Mocha House",
    "Punjabi Tadka",
]
FUEL = [
    ("Indian Oil", "INDIAN OIL"),
    ("Bharat Petroleum", "BHARAT PETROLEUM"),
    ("HP Petrol", "HINDUSTAN PETROLEUM"),
]
KIRANAS = ["Shree Ganesh Kirana Stores", "Patel Provision Store", "Jai Ambe General Store"]
CITIES = ["Ahmedabad", "Pune", "Indore", "Surat", "Jaipur", "Nagpur", "Vadodara", "Bhopal"]
ROADS = ["SG Highway", "MG Road", "Station Road", "Ring Road", "CG Road", "FC Road", "Link Road"]


def _date_text(rng: random.Random, when: date, style: str) -> str:
    formats = {
        "numeric": ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y"],
        "words": ["%d-%b-%Y", "%d %b %Y", "%b %d, %Y"],
    }
    return when.strftime(rng.choice(formats[style]))


def _address(rng: random.Random) -> str:
    return (
        f"Plot {rng.randint(2, 180)}, {rng.choice(ROADS)}, {rng.choice(CITIES)} {rng.randint(380001, 495999)}"
    )


def _gstin(rng: random.Random) -> str:
    state, middle, check = rng.randint(10, 35), rng.randint(1000, 9999), rng.randint(1, 9)
    return f"GSTIN: {state}AAB{rng.choice('CDEFGH')}{middle}{rng.choice('KLMN')}1Z{check}"


def _pick_items(rng: random.Random, groups: list[str], count: int) -> list[dict]:
    chosen, seen = [], set()
    while len(chosen) < count:
        group = rng.choice(groups)
        name, (low, high) = rng.choice(CATALOG[group])
        if name in seen:
            continue
        seen.add(name)
        qty = rng.choice([1, 1, 1, 2, 3]) if group != "dining" else rng.choice([1, 1, 2])
        rate = round(rng.uniform(low, high) * 2) / 2
        chosen.append(
            {"name": name, "qty": qty, "rate": rate, "amount": round(qty * rate, 2), "group": group}
        )
    return chosen


def _bill_date(rng: random.Random) -> date:
    return TODAY - timedelta(days=rng.randint(0, 40))


def supermarket(rng: random.Random) -> dict:
    merchant, header = rng.choice(SUPERMARKETS)
    when = _bill_date(rng)
    items = _pick_items(rng, ["groceries"] * 3 + ["household", "personal_care", "baby"], rng.randint(4, 9))
    subtotal = round(sum(item["amount"] for item in items), 2)
    inclusive = rng.random() < 0.5  # tax already inside the prices, shown for information
    tax = round(subtotal * 0.025, 2)
    raw_total = subtotal if inclusive else subtotal + 2 * tax
    total = float(round(raw_total))
    lines = header + [
        _address(rng),
        _gstin(rng),
        f"Ph: 0{rng.randint(20, 99)}-{rng.randint(20000000, 29999999)}",
        f"Bill No: {rng.randint(1000, 9999)}/{rng.randint(1000, 9999)} "
        f"Date: {_date_text(rng, when, 'numeric')}",
        f"Cashier: {rng.randint(1, 30):02d} Time: {rng.randint(9, 21):02d}:{rng.randint(0, 59):02d}",
        rng.choice(["Item Qty Rate Amt", "Particulars Qty Rate Value", "Description Qty MRP Amount"]),
    ]
    lines += [f"{item['name']} {item['qty']} {item['rate']:.2f} {item['amount']:.2f}" for item in items]
    lines.append(f"Total Qty: {sum(item['qty'] for item in items)} Sub Total {subtotal:.2f}")
    lines += [f"CGST 2.5% {tax:.2f}", f"SGST 2.5% {tax:.2f}"]
    if round(total - raw_total, 2):
        lines.append(f"Round Off {total - raw_total:.2f}")
    lines.append(
        rng.choice(
            [
                f"NET PAYABLE Rs {total:.2f}",
                f"GRAND TOTAL {total:.2f}",
                f"TOTAL AMOUNT {total:.2f}",
                f"TOTAL (INCL. GST) {total:.2f}",
            ]
        )
    )
    lines.append(f"You Saved Rs {rng.randint(10, 150)}.00")
    if rng.random() < 0.5:
        tendered = float((int(total) // 100 + 1) * 100)
        lines += [f"Cash Tendered {tendered:.2f}", f"Change {tendered - total:.2f}"]
    else:
        lines.append(f"Paid by UPI {total:.2f}")
    lines.append("Thank you! Visit again")
    return {
        "kind": "supermarket",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": total,
        "items": items,
    }


def quick_commerce(rng: random.Random) -> dict:
    merchant, header = rng.choice(QUICK_COMMERCE)
    when = _bill_date(rng)
    items = _pick_items(rng, ["groceries"] * 4 + ["household", "personal_care"], rng.randint(3, 7))
    item_total = round(sum(item["amount"] for item in items), 2)
    fee, handling, discount = rng.choice([0, 25, 30]), rng.choice([2, 4, 6]), rng.choice([0, 0, 20, 50])
    total = round(item_total + fee + handling - discount, 2)
    lines = [
        "Tax Invoice",
        header,
        f"Order ID: {rng.randint(10**11, 10**12 - 1)}",
        f"Invoice Date: {_date_text(rng, when, 'words')}",
        _address(rng),
        "Item Qty Price",
    ]
    connector = rng.choice([" ", " = "])
    lines += [
        f"{item['name']} {item['qty']} x {item['rate']:.2f}{connector}{item['amount']:.2f}" for item in items
    ]
    lines += [f"Item Total ₹{item_total:.2f}", f"Delivery Fee ₹{fee:.2f}", f"Handling Charge ₹{handling:.2f}"]
    if discount:
        lines.append(f"Coupon Discount -₹{discount:.2f}")
    lines += [
        rng.choice([f"Grand Total ₹{total:.2f}", f"Bill Total ₹{total:.2f}", f"Order Total ₹{total:.2f}"]),
        "This is a computer generated invoice",
    ]
    return {
        "kind": "quick_commerce",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": total,
        "items": items,
    }


def pharmacy(rng: random.Random) -> dict:
    merchant, header = rng.choice(PHARMACIES)
    when = _bill_date(rng)
    items = _pick_items(rng, ["health"] * 4 + ["personal_care"], rng.randint(2, 5))
    for number, item in enumerate(items, 1):
        item["line"] = (
            f"{number} {item['name']} B{rng.randint(1000, 9999)} {rng.randint(1, 12):02d}/"
            f"{rng.randint(27, 29)} {item['qty']} {item['amount']:.2f}"
        )
    subtotal = round(sum(item["amount"] for item in items), 2)
    discount = round(subtotal * rng.choice([0, 0.1, 0.15]), 2)
    total = round(subtotal - discount, 2)
    lines = [
        header,
        _address(rng),
        f"D.L. No: 20B-{rng.randint(100, 999)}/{rng.randint(10, 99)}",
        _gstin(rng),
        f"Invoice No: {rng.randint(10000, 99999)} Date: {_date_text(rng, when, 'numeric')}",
        "Product Batch Exp Qty Amount",
    ]
    lines += [item.pop("line") for item in items]
    lines.append(f"Gross Amount {subtotal:.2f}")
    if discount:
        lines.append(f"Discount {discount:.2f}")
    lines += [rng.choice([f"Net Amount {total:.2f}", f"Amount Payable {total:.2f}"]), "Get well soon"]
    return {
        "kind": "pharmacy",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": total,
        "items": items,
    }


def restaurant(rng: random.Random) -> dict:
    merchant = rng.choice(RESTAURANTS)
    when = _bill_date(rng)
    items = _pick_items(rng, ["dining"], rng.randint(2, 6))
    subtotal = round(sum(item["amount"] for item in items), 2)
    service = round(subtotal * rng.choice([0, 0.05, 0.1]), 2)
    tax = round((subtotal + service) * 0.025, 2)
    total = round(subtotal + service + 2 * tax)
    lines = [
        merchant.upper(),
        _address(rng),
        _gstin(rng),
        f"Table: {rng.randint(1, 20)} Covers: {rng.randint(1, 6)}",
        f"Bill No: {rng.randint(100, 999)} Date: {_date_text(rng, when, 'numeric')} "
        f"Time: 21:{rng.randint(10, 59)}",
        "Item Qty Price Amount",
    ]
    lines += [f"{item['name']} {item['qty']} {item['rate']:.2f} {item['amount']:.2f}" for item in items]
    lines.append(f"Sub Total {subtotal:.2f}")
    if service:
        lines.append(f"Service Charge {service:.2f}")
    lines += [
        f"CGST 2.5% {tax:.2f}",
        f"SGST 2.5% {tax:.2f}",
        f"Grand Total {total:.2f}",
        "Thank you, visit again",
    ]
    for item in items:
        item["group"] = "dining"
    return {
        "kind": "restaurant",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": float(total),
        "items": items,
    }


def fuel(rng: random.Random) -> dict:
    merchant, brand = rng.choice(FUEL)
    when = _bill_date(rng)
    amount = float(rng.choice([300, 500, 750, 1000, 1500, 2000]))
    rate = round(rng.uniform(94, 107), 2)
    lines = [
        brand,
        f"M/S {rng.choice(['SHIV SHAKTI', 'JAI HIND', 'OM SAI'])} FUELS",
        _address(rng),
        f"Receipt No: {rng.randint(1000, 9999)}",
        f"Date: {_date_text(rng, when, 'numeric')} Time: 08:{rng.randint(10, 59)}",
        f"Nozzle No: {rng.randint(1, 8)}",
        "Product: PETROL",
        f"Rate: Rs {rate:.2f}/L",
        f"Volume: {amount / rate:.2f} L",
        f"Amount: Rs {amount:.2f}",
        "Mode: UPI",
        "Save fuel, save money",
    ]
    return {
        "kind": "fuel",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": amount,
        "items": [],
    }


def kirana(rng: random.Random) -> dict:
    merchant = rng.choice(KIRANAS)
    when = _bill_date(rng)
    items = _pick_items(rng, ["groceries"] * 5 + ["household"], rng.randint(3, 6))
    for item in items:
        item["amount"] = float(round(item["amount"]))
    total = sum(item["amount"] for item in items)
    mobile = str(rng.randint(9000000000, 9999999999))
    lines = [
        merchant.upper(),
        f"{rng.choice(ROADS)}, {rng.choice(CITIES)} {rng.randint(380001, 495999)}",
        rng.choice([f"Mob {mobile}", f"Mo. {mobile[:5]} {mobile[5:]}"]),
        f"Date {_date_text(rng, when, 'numeric')}",
    ]
    lines += [f"{item['name'].title()} {int(item['amount'])}" for item in items]
    lines.append(f"Total {int(total)}")
    return {
        "kind": "kirana",
        "lines": lines,
        "merchant": merchant,
        "date": when.isoformat(),
        "total": float(total),
        "items": items,
    }


LAYOUTS = [supermarket, supermarket, quick_commerce, pharmacy, restaurant, fuel, kirana]

_LOOKALIKE = {"0": "O", "1": "l", "5": "S", "8": "B"}


def noisy(bill: dict, rng: random.Random) -> dict:
    """OCR-style damage to the text, leaving the answers unchanged."""
    item_names = {item["name"] for item in bill["items"]}
    lines = []
    for line in bill["lines"]:
        name = next(
            (name for name in item_names if line.startswith(name) or line.split(" ", 1)[-1].startswith(name)),
            None,
        )
        if name and rng.random() < 0.12:  # OCR split a row: the name, then its numbers on the next line
            head, numbers = line.split(name, 1)
            lines += [f"{head}{name}".strip(), numbers.strip()]
            continue
        if rng.random() < 0.15:  # a look-alike letter inside a number
            chars = list(line)
            spots = [i for i, ch in enumerate(chars) if ch in _LOOKALIKE and i and chars[i - 1].isdigit()]
            if spots:
                spot = rng.choice(spots)
                chars[spot] = _LOOKALIKE[chars[spot]]
                line = "".join(chars)
        if rng.random() < 0.05 and " " in line:  # a lost space
            spaces = [i for i, ch in enumerate(line) if ch == " "]
            spot = rng.choice(spaces)
            line = line[:spot] + line[spot + 1 :]
        lines.append(line)
    return {**bill, "lines": lines}


def generate(count: int, seed: int, noise: bool = True) -> list[dict]:
    rng = random.Random(seed)
    bills = []
    for index in range(count):
        bill = rng.choice(LAYOUTS)(rng)
        bill = noisy(bill, rng) if noise else bill
        bills.append(
            {
                "id": f"gen-{seed}-{index:03d}",
                **bill,
                "items": [
                    {"name": i["name"], "amount": i["amount"], "group": i["group"]} for i in bill["items"]
                ],
            }
        )
    return bills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic bills.")
    parser.add_argument("--write-dev", action="store_true", help="write data/receipts_dev.jsonl")
    parser.add_argument("--count", type=int, default=60)
    args = parser.parse_args(argv)
    bills = generate(args.count, seed=11)
    if args.write_dev:
        path = DATA_DIR / "receipts_dev.jsonl"
        path.write_text(
            "".join(json.dumps(bill, ensure_ascii=False) + "\n" for bill in bills), encoding="utf-8"
        )
        print(f"wrote {len(bills)} bills to {path}")
    else:
        print(json.dumps(bills[0], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
