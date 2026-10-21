from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.receipts.items import classify_item, group_items, resolve_category
from app.receipts.ocr import UnreadableFile, detect_kind, lines_from_boxes, load_engine, read_image, read_pdf
from app.receipts.parse import (
    ReceiptItem,
    amounts_in,
    dates_in,
    find_items,
    find_merchant,
    find_total,
    fix_digits,
    parse_receipt,
)
from app.receipts.preprocess import _profile_score, _rotate, estimate_skew, find_document, warp_document

TODAY = date(2026, 10, 19)
DMART = [
    "AVENUE SUPERMARTS LTD", "D-MART", "Plot 12, SG Highway, Ahmedabad", "GSTIN: 24AACCA8432H1Z9",
    "Ph: 079-26851234", "Bill No: 1027/4512 Date: 14/10/2026", "Cashier: 07 Time: 18:42", "Item Qty Rate Amt",
    "TATA SALT 1KG 1 28.00 28.00", "AASHIRVAAD ATTA 5KG 1 245.00 245.00", "AMUL BUTTER 500G 1 275.00 275.00",
    "SURF EXCEL 1KG 1 140.00 140.00", "COLGATE STRONG 200G 2 99.00 198.00", "BANANA ROBUSTA 1 48.50 48.50",
    "VIM BAR 300G 3 20.00 60.00", "Total Qty: 10 Sub Total 994.50", "CGST 2.5% 12.40", "SGST 2.5% 12.40",
    "Round Off -0.30", "NET PAYABLE Rs 1019.00", "You Saved Rs 86.00", "Thank you! Visit again",
]
CATEGORIES = [
    {"id": 1, "name": "Food", "user_id": None}, {"id": 2, "name": "Shopping", "user_id": None},
    {"id": 3, "name": "Travel", "user_id": None}, {"id": 4, "name": "Other", "user_id": None},
]


# ---------- numbers and dates ----------

@pytest.mark.parametrize("raw, fixed", [
    ("NET PAYABLE Rs 1O19.0O", "NET PAYABLE Rs 1019.00"),
    ("CGST l2.40", "CGST 12.40"),
    ("S00.00", "500.00"),
    ("SURF EXCEL SOLD OUT", "SURF EXCEL SOLD OUT"),  # words without digits are left alone
])
def test_ocr_lookalikes_are_fixed_only_inside_numbers(raw, fixed):
    assert fix_digits(raw) == fixed


@pytest.mark.parametrize("line, values", [
    ("Total ₹1,24,500.00", [124500.0]),
    ("Amount 1,019.50", [1019.5]),
    ("Total 12,40", [12.4]),  # a decimal comma
    ("Rs.1019.00", [1019.0]),
    ("Ph 9876543210", []),  # a phone number is not an amount
    ("CGST 2.5%", []),  # nor is a tax rate
    ("TATA SALT 1KG", []),  # nor a pack size
])
def test_amounts_are_read_the_indian_way(line, values):
    assert [amount.value for amount in amounts_in(line)] == values


@pytest.mark.parametrize("line, expected", [
    ("Date: 14/10/2026", date(2026, 10, 14)),
    ("Bill Dt 14-Oct-2026 18:42", date(2026, 10, 14)),
    ("Oct 14, 2026", date(2026, 10, 14)),
    ("2026-10-14", date(2026, 10, 14)),
    ("14.10.26", date(2026, 10, 14)),
    ("14 October 2026", date(2026, 10, 14)),
    ("Date: 05/10/2026", date(2026, 10, 5)),  # day first, as written in India
])
def test_printed_dates(line, expected):
    assert dates_in(line, TODAY) == [expected]


def test_future_and_ancient_dates_are_ignored():
    assert dates_in("Valid till 25/12/2026", TODAY) == []
    assert dates_in("Since 1998 01/01/1998", TODAY) == []


def test_the_labelled_date_wins():
    lines = ["Printed 01/10/2026 offer", "Bill Date: 14/10/2026"]
    assert parse_receipt(lines, TODAY).date == date(2026, 10, 14)


# ---------- totals ----------

def test_net_payable_beats_sub_total_savings_and_tax():
    draft = parse_receipt(DMART, TODAY)
    assert (draft.total, draft.subtotal, draft.warnings) == (1019.0, 994.5, [])


def test_grand_total_on_a_restaurant_bill():
    lines = ["THE GREEN LEAF", "Table 4 Covers 2", "Paneer Tikka 1 280.00", "Dal Makhani 1 260.00",
             "Butter Naan 4 60.00 240.00", "Sub Total 780.00", "Service Charge 5% 39.00", "CGST 2.5% 19.50",
             "SGST 2.5% 19.50", "Grand Total 858.00", "Cash Tendered 900.00", "Change 42.00"]
    assert find_total(lines) == (858.0, False)


def test_total_mrp_tendered_and_change_are_not_the_total():
    lines = ["Total MRP 1105.00", "Total Savings 86.00", "TOTAL 1019.00", "Cash Tendered 2000.00",
             "Change 981.00"]
    assert find_total(lines) == (1019.0, False)


def test_a_total_split_onto_the_next_line_is_found():
    assert find_total(["Grand Total", "1,245.50", "Thank you"]) == (1245.5, False)


def test_without_any_keyword_the_largest_amount_is_a_flagged_guess():
    draft = parse_receipt(["Sharma General Store", "Sugar 45.00", "Tea 120.00", "245.00"], TODAY)
    assert draft.total == 245.0 and "total_guessed" in draft.warnings and draft.found["total"] is False


# ---------- merchant ----------

def test_known_chain_found_by_its_company_name():
    assert find_merchant(["AVENUE SUPERMARTS LTD", "Plot 12"]) == "DMart"


def test_known_chain_with_an_ocr_typo():
    assert find_merchant(["B1inkit Commerce", "Order summary"]) == "Blinkit"


def test_the_users_own_merchant_is_reused():
    assert find_merchant(["SHREE KRISHNA PROVISION STORE", "Main Road"], ["Shree Krishna Provision Store"]) \
        == "Shree Krishna Provision Store"


def test_fallback_skips_addresses_gstin_and_document_words():
    lines = ["TAX INVOICE", "Sharma Kirana", "12 MG Road, Indore 452001", "GSTIN 23ABCDE1234F1Z5"]
    assert find_merchant(lines) == "Sharma Kirana"


# ---------- items ----------

def test_items_with_quantity_rate_and_amount():
    items = find_items(DMART, TODAY)
    assert [(item.name, item.amount) for item in items] == [
        ("TATA SALT", 28.0), ("AASHIRVAAD ATTA", 245.0), ("AMUL BUTTER", 275.0), ("SURF EXCEL", 140.0),
        ("COLGATE STRONG", 198.0), ("BANANA ROBUSTA", 48.5), ("VIM BAR", 60.0),
    ]


def test_a_row_split_by_ocr_is_joined():
    lines = ["Item Qty Amt", "AMUL BUTTER 500G", "1 275.00 275.00", "Sub Total 275.00"]
    assert [(item.name, item.amount) for item in find_items(lines, TODAY)] == [("AMUL BUTTER", 275.0)]


def test_header_and_footer_lines_are_not_items():
    lines = ["Cashier: 07", "Bill No: 1027 4512", "Table 4", "Item Qty Amt", "Tea 1 20.00", "Total 20.00"]
    assert [item.name for item in find_items(lines, TODAY)] == ["Tea"]


# ---------- grouping ----------

@pytest.mark.parametrize("name, group", [
    ("TATA SALT 1KG", "groceries"), ("SURF EXCEL MATIC", "household"), ("COLGATE STRONG", "personal_care"),
    ("DOLO 650 TAB", "health"), ("PAMPERS L 42", "baby"), ("CLASSMATE NOTEBOOK", "stationery"),
    ("DETERGNT POWDER", "household"),  # an OCR typo, matched fuzzily
    ("XQZ 123", None),
])
def test_items_are_classified(name, group):
    assert classify_item(name) == group


def _items(*pairs):
    return [ReceiptItem(name, amount, index) for index, (name, amount) in enumerate(pairs)]


def test_groups_add_up_to_the_total_exactly():
    items = _items(("TATA SALT", 28.0), ("AMUL BUTTER", 275.0), ("SURF EXCEL", 140.0), ("COLGATE", 198.0))
    groups, adjustment, warnings = group_items(items, 660.0, CATEGORIES)
    assert adjustment == 19.0 and warnings == []
    assert round(sum(group.amount for group in groups), 2) == 660.0
    assert [(group.name, group.key) for group in groups] == [("Shopping", "household+personal_care"),
                                                             ("Food", "groceries")]


def test_a_category_named_like_the_group_is_preferred():
    own = CATEGORIES + [{"id": 9, "name": "Groceries", "user_id": "u1"},
                        {"id": 10, "name": "Household", "user_id": "u1"}]
    assert resolve_category("groceries", own)["id"] == 9
    assert resolve_category("household", own)["id"] == 10
    assert resolve_category("groceries", CATEGORIES)["name"] == "Food"


def test_a_restaurant_bill_is_one_dining_group():
    items = _items(("Paneer Tikka", 280.0), ("Lime Soda", 90.0))
    groups, _, _ = group_items(items, 370.0, CATEGORIES, "The Green Leaf", ["Table 4 Covers 2"])
    assert [(group.name, group.amount) for group in groups] == [("Food", 370.0)]


def test_items_that_dont_add_up_are_flagged():
    _, _, warnings = group_items(_items(("Sugar", 45.0)), 900.0, CATEGORIES)
    assert warnings == ["items_dont_add_up"]


# ---------- reading ----------

def test_detect_kind_trusts_the_bytes():
    assert detect_kind(b"%PDF-1.4 ...") == "pdf"
    assert detect_kind(b"\xff\xd8\xff\xe0 jpeg") == "image"
    assert detect_kind(b"\x89PNG\r\n\x1a\n...") == "image"
    assert detect_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image"
    assert detect_kind(b"MZ executable") is None


def _box(x, y, width, height, degrees):
    """A text box at (x, y) on a page tilted by `degrees`: its corners rotated about the page's origin."""
    angle = np.radians(degrees)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    corners = np.array([[x, y], [x + width, y], [x + width, y + height], [x, y + height]], dtype=float)
    return corners @ rotation.T


def test_lines_are_rebuilt_from_boxes_on_a_tilted_photo():
    # On a 5° tilt the price at the far right sits about 26 px lower than its item name
    boxes = [_box(10, 100, 200, 20, 5), _box(300, 100, 80, 20, 5), _box(10, 140, 150, 20, 5),
             _box(300, 140, 80, 20, 5)]
    lines, confidence = lines_from_boxes(boxes, ["TATA SALT", "28.00", "AMUL BUTTER", "275.00"], [0.9] * 4)
    assert lines == ["TATA SALT 28.00", "AMUL BUTTER 275.00"] and confidence == 0.9


def _text_pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF with a real text layer."""
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 11 Tf 50 800 Td 14 TL " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> "
        "/Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out.encode("latin-1")))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


class FakeEngine:
    """Stands in for RapidOCR: returns the given lines as level boxes."""

    def __init__(self, lines):
        self.lines, self.calls = lines, 0

    def __call__(self, image):
        self.calls += 1
        boxes = np.array([[[10, 30 * i], [400, 30 * i], [400, 30 * i + 20], [10, 30 * i + 20]]
                          for i in range(len(self.lines))], dtype=float)
        return SimpleNamespace(boxes=boxes, txts=tuple(self.lines), scores=tuple([0.95] * len(self.lines)))


def test_a_pdf_text_layer_is_read_without_ocr():
    def no_ocr():
        raise AssertionError("a PDF with text must not be OCR'd")

    read = read_pdf(_text_pdf(DMART), no_ocr)
    assert read.source == "pdf_text" and read.confidence is None
    assert parse_receipt(read.lines, TODAY).total == 1019.0


def test_a_scanned_pdf_falls_back_to_ocr():
    engine = FakeEngine(["SOME SHOP", "TOTAL 99.00"])
    read = read_pdf(_text_pdf([]), lambda: engine)
    assert (read.source, read.lines, engine.calls) == ("ocr", ["SOME SHOP", "TOTAL 99.00"], 1)


def test_a_damaged_file_is_reported_as_unreadable():
    with pytest.raises(UnreadableFile):
        read_pdf(b"%PDF-1.4 not really", lambda: None)
    with pytest.raises(UnreadableFile):
        read_image(b"\xff\xd8\xff\xe0 not really a jpeg", FakeEngine([]))


# ---------- preprocessing ----------

def test_a_bill_on_a_table_is_found_and_flattened():
    photo = np.full((800, 600, 3), 90, np.uint8)  # a dark table
    corners = np.array([[150, 120], [470, 160], [440, 700], [120, 660]], np.int32)
    cv2.fillPoly(photo, [corners], (245, 245, 245))  # a white bill, slightly rotated
    found = find_document(photo)
    assert found is not None and np.abs(found - corners).max() < 12
    flat = warp_document(photo, found)
    assert flat.mean() > 230  # only the bill is left


def _text_like_page(degrees):
    page = np.full((600, 450), 255, np.uint8)
    for y in range(60, 560, 28):  # rows of "text"
        for x in range(40, 400, 26):
            cv2.rectangle(page, (x, y), (x + 18, y + 10), 0, -1)
    return _rotate(page, degrees, border=cv2.BORDER_CONSTANT) if degrees else page


def test_skew_is_measured_and_undone():
    page = _text_like_page(6)
    angle = estimate_skew(page)
    assert abs(angle + 6) <= 1  # rotating by -6° levels it
    ink = 255 - page
    assert _profile_score(ink, angle) > _profile_score(ink, 0)


def test_a_straight_page_is_left_alone():
    assert estimate_skew(_text_like_page(0)) == 0.0


# ---------- the endpoint ----------

def _png():
    ok, encoded = cv2.imencode(".png", np.full((60, 60, 3), 255, np.uint8))
    return encoded.tobytes()


# The endpoint accepts "today" only within a day of the server's date
SERVER_TODAY = datetime.now(UTC).date().isoformat()


def test_scan_requires_a_token(client):
    response = client.post("/v1/receipts/scan", files={"file": ("bill.png", _png(), "image/png")})
    assert response.status_code == 401


def test_scan_rejects_unsupported_and_oversized_files(client, auth_headers):
    exe = client.post("/v1/receipts/scan", files={"file": ("x.exe", b"MZ" * 10, "application/octet-stream")},
                      headers=auth_headers)
    too_big = b"%PDF" + b"0" * (8 * 2**20)
    huge = client.post("/v1/receipts/scan", files={"file": ("big.pdf", too_big, "application/pdf")},
                       headers=auth_headers)
    assert (exe.status_code, huge.status_code) == (415, 413)


def test_scan_returns_the_bill_and_its_groups(client, auth_headers, supabase):
    supabase.tables["categories"] = CATEGORIES
    client.app.state.ocr_engine = FakeEngine(DMART)
    response = client.post("/v1/receipts/scan", files={"file": ("bill.png", _png(), "image/png")},
                           data={"today": SERVER_TODAY}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    fields = (body["merchant"], body["date"], body["total"], body["source"])
    assert fields == ("DMart", "2026-10-14", 1019.0, "ocr")
    assert body["found"] == {"merchant": True, "date": True, "total": True}
    assert [group["category_name"] for group in body["groups"]] == ["Food", "Shopping"]
    assert round(sum(group["amount"] for group in body["groups"]), 2) == 1019.0
    assert len(body["items"]) == 7 and body["adjustment"] == 24.5


def test_scan_reads_a_pdf_invoice(client, auth_headers, supabase):
    supabase.tables["categories"] = CATEGORIES
    upload = {"file": ("invoice.pdf", _text_pdf(DMART), "application/pdf")}
    response = client.post("/v1/receipts/scan", files=upload, data={"today": SERVER_TODAY},
                           headers=auth_headers)
    assert response.status_code == 200 and response.json()["source"] == "pdf_text"


def test_a_photo_without_text_gets_a_helpful_error(client, auth_headers):
    client.app.state.ocr_engine = FakeEngine([])
    response = client.post("/v1/receipts/scan", files={"file": ("blank.png", _png(), "image/png")},
                           headers=auth_headers)
    assert response.status_code == 422 and "whole bill" in response.json()["detail"]


# ---------- the real OCR model (downloads ~32 MB of models on first use) ----------

def test_real_ocr_reads_a_rendered_bill():
    font = ImageFont.load_default(size=26)
    image = Image.new("L", (700, 40 * len(DMART) + 60), 255)
    draw = ImageDraw.Draw(image)
    for row, line in enumerate(DMART):
        draw.text((20, 30 + 40 * row), line, fill=20, font=font)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(np.asarray(image), cv2.COLOR_GRAY2BGR))
    read = read_image(encoded.tobytes(), load_engine(threads=2))
    draft = parse_receipt(read.lines, TODAY)
    assert (draft.merchant, draft.date, draft.total) == ("DMart", date(2026, 10, 14), 1019.0)
    assert read.confidence > 0.9
