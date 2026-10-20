# Step 10 — Bill scanning: a photo or PDF becomes transactions

**What it does:** take a photo of a bill, or upload a photo or PDF (a supermarket receipt, a Blinkit/Zepto/BigBasket invoice, a pharmacy, restaurant or fuel bill). The app reads the shop, date, total and items, then shows them for review. You save the bill as one transaction or **split it by category**, for example "DMart · Groceries" ₹611.20 and "DMart · Household & personal care" ₹407.80, and the bill is **kept privately** with its transactions. Nothing is saved before you press Save.

**Where it lives:**

| Piece | File |
|---|---|
| OpenCV clean-up | [`app/receipts/preprocess.py`](../../ml-service/app/receipts/preprocess.py) |
| Reading: PDF text layer or OCR, rows rebuilt | [`app/receipts/ocr.py`](../../ml-service/app/receipts/ocr.py) |
| Parsing: merchant, date, total, items | [`app/receipts/parse.py`](../../ml-service/app/receipts/parse.py) |
| Grouping items by category | [`app/receipts/items.py`](../../ml-service/app/receipts/items.py) |
| API endpoint | [`app/routers/receipts.py`](../../ml-service/app/routers/receipts.py) (`POST /v1/receipts/scan`) |
| Bills (dev: generated, test: hand-written) | [`training/receipt_samples.py`](../../ml-service/training/receipt_samples.py), [`training/data/receipts_test.jsonl`](../../ml-service/training/data/receipts_test.jsonl) |
| Evaluation and gates | [`training/evaluate_receipts.py`](../../ml-service/training/evaluate_receipts.py), [`training/evaluate_receipt_ocr.py`](../../ml-service/training/evaluate_receipt_ocr.py) |
| Storage (private bucket, policies) | [`supabase/migrations/20261019000000_receipts.sql`](../../supabase/migrations/20261019000000_receipts.sql) |
| Frontend | [`ReceiptScanModal.jsx`](../../frontend/src/components/ReceiptScanModal.jsx), [`lib/receiptFile.js`](../../frontend/src/lib/receiptFile.js) |

## Results at a glance

**Parsing**, on 16 bills written by hand before any evaluation and never used to tune the rules:

| Field | Naive baseline | Rules |
|---|---|---|
| Merchant | 50.0% | **100%** |
| Date | 100% | **100%** |
| Total | 31.2% | **93.8%** |
| Items, F1 | 57.6% | **93.0%** |
| Item groups (on found items) | 47.3% | **92.5%** |

**End to end** (OpenCV → OCR → parsing) on rendered "phone photos": see [§6](#6-the-whole-pipeline-on-photos-and-what-opencv-adds).

## 1. The pipeline

```
photo / PDF ──► browser: turned upright, shrunk to 2,000 px, JPEG ──► POST /v1/receipts/scan (user's JWT)
                                                                         │
     PDF with a text layer ──► its text (exact, no OCR) ◄────────────────┤
     photo or scanned PDF  ──► OpenCV clean-up ──► OCR ──► rows rebuilt ◄┘
                                                                         ▼
                     parse: merchant · date · total · item lines ──► group items by category
                                                                         ▼
                   review screen (edit, split or one) ──► Save: file → private storage,
                                                          transactions → Supabase (RLS)
```

The server only reads. The browser stores the file and creates the transactions, with the user's own token, after the user confirms.

## 2. Reading: PDF first, then OCR

- **PDF text layer.** E-bills and app invoices are PDFs with real text. `pypdfium2` extracts it exactly, so no OCR is needed. Only when a PDF has almost no text (a scan saved as PDF) are its pages rendered at about 200 dpi and OCR'd.
- **OCR engine: RapidOCR**, PaddleOCR's PP-OCR models run by ONNX Runtime on the CPU:
  - a **text detector** (DB, "differentiable binarization") finds every piece of text as a four-cornered box, tilted if the photo is;
  - a **recogniser** reads each box.
- **Why not Tesseract,** which was the first plan:
  - Tesseract needs a system binary, so it couldn't run on the development machine. Every experiment would have meant a CI round trip.
  - RapidOCR installs with pip on every OS, uses the ONNX Runtime the service already has for embeddings, and is built for photos of real-world text.
  - The deciding experiment: on a rendered bill rotated 4°, blurred, noisy, unevenly lit and JPEG-compressed, it read **34 of 34 lines exactly**, with 0.99 mean confidence.
- **Rebuilding rows.** The detector returns pieces, not lines. "TATA SALT 1KG" and its price "28.00" at the far right are separate boxes, and on a tilted photo they aren't at the same height. `lines_from_boxes`:
  1. measures the tilt from the boxes' own top edges (the median of the wide ones);
  2. rotates the box centres level;
  3. joins boxes whose centres share a row.

## 3. OpenCV clean-up

Each step can be switched off, to measure what it adds:

| Step | What it does | Why |
|---|---|---|
| size | Long side to about 1,800 px | Bigger photos only cost time; small ones are upscaled so thin thermal print survives |
| perspective | Edges → largest four-sided contour → `warpPerspective` | A bill on a table becomes a flat, top-down page with the table cut away |
| deskew | Projection profile: the rotation that makes row sums peak sharpest | Level text lines read better and rebuild into rows reliably |
| contrast | CLAHE on grayscale | Evens out shadows and faded print. There is no hard black/white threshold, because the OCR model reads grey levels better than a binarised page |

## 4. Parsing: rules tuned for Indian bills

- **Numbers.**
  - OCR look-alikes are fixed only inside numbers: O→0, l/I→1, S→5, B→8, so "1O19.0O" becomes 1019.00 while "SOLD" stays a word.
  - Indian digit grouping (1,24,500) and a decimal comma (12,40) are both read.
  - Phone numbers, GSTINs, tax rates and pack sizes are not amounts.
- **Total: by keyword strength, never by size.**
  - Grand total > net payable > net amount / bill amount > total amount > total > a fuel slip's "Amount:".
  - Never totals: sub total, total qty/items, total MRP, savings, discount, round off, tax lines, cash tendered, change. "Total (incl. GST)" counts as a total, not as a tax line.
  - Among candidates, the strongest keyword wins, then the later line.
  - With no keyword at all, the largest amount is used and flagged as a guess, so the review screen warns about it.
- **Date:** the printed date nearest a "date / dt" label (day first, as in India), never in the future.
- **Merchant**, tried in this order:
  1. a known chain, found by its legal name too ("AVENUE SUPERMARTS" is DMart);
  2. a fuzzy match that tolerates one OCR typo ("B1inkit");
  3. the user's own merchants;
  4. else the first name-like header line, skipping addresses, GSTINs and "TAX INVOICE".
- **Items.**
  - Lines with a name and a trailing amount (and optionally qty × rate) between the table header and the first summary line.
  - A row OCR split in two is joined back.
  - Serial numbers, HSN codes and a pharmacy's batch and expiry are stripped from names.
  - "Amount: Rs 500" fields, mobile numbers and PIN codes are not items.

## 5. Grouping items by category

1. **Item → group.** A lexicon of about 300 Indian product words and brands decides the group (atta, dal, Amul, Surf, Vim, Colgate, Dolo…):
   - multi-word phrases count double ("surf excel", "hair oil");
   - OCR typos are matched fuzzily ("detergnt" → detergent);
   - words OCR ran together are split by substring ("tatasalt" → salt).
2. **Whole-bill kinds.** A restaurant bill is all dining and a fuel slip is fuel. A pharmacy's unrecognised items default to health.
3. **Group → the user's category.** A category named like the group comes first ("Groceries", "Household"); otherwise the canonical label's category (groceries → Food, household → Shopping). Groups landing on the same category are merged into one transaction.
4. **Tax, discount and round-off** make the items not add up to the bill. The difference is spread across groups in proportion, and the last paisa goes to the largest group, so the transactions add up **exactly** to the total.

## 6. The whole pipeline on photos, and what OpenCV adds

`evaluate_receipt_ocr` draws generated bills on paper and "photographs" them badly:
- two thirds on a table, with a perspective tilt and rotation up to 7°;
- a third as scans;
- all with blur, uneven light, sensor noise and JPEG compression.

It then runs the real models through the whole pipeline.

On 24 rendered photos (4 threads on a laptop):

| Pipeline | Merchant | Date | Total | Items F1 | Time per bill |
|---|---|---|---|---|---|
| No preprocessing | 100% | 100% | 100% | 1.00 | 2.2 s |
| + size | 100% | 100% | 100% | 1.00 | 2.3 s |
| + perspective | 100% | 100% | 100% | 1.00 | (timing noise) |
| + deskew | 100% | 100% | 100% | 1.00 | 2.2 s |
| Full (+ contrast) | 100% | 100% | 100% | 1.00 | 2.3 s |

**The honest reading.**
- On these synthetic photos the OCR model is robust enough that the OpenCV steps make **no measurable difference**. The detector handles 7° tilts and mild perspective on its own, and rows are rebuilt from the tilted boxes anyway.
- The steps are kept because real photos are harsher (steep angles, shadows, crumpled paper) and they cost almost nothing.
- The ablation stays in the evaluation, so the claim can be re-checked when real photos with consent are added to the test set.

**Speed decisions, measured single-threaded** (like the free server's CPU):
- By default the detector runs on the full-size photo.
- Capping detection at 960 px and skipping the per-box rotation classifier brought a bill to **about 2 s on one laptop thread**, with the same accuracy.
- On Render's free plan (a tenth of a CPU) that's roughly 20 s.
- One bug the photos exposed: OCR dropping the gap in "Total 703" ("Total703"). Labels glued to their numbers are now split before parsing.

## 7. Evaluation done honestly

- **Two sets.**
  - **Dev:** 60 bills generated in six layouts, with OCR-style noise including split rows and lost spaces. The rules were developed against them.
  - **Test:** 16 bills **written by hand before the first evaluation**, never used to tune the rules. They use other stores and layouts, abbreviated names ("CLGT MAXFRSH", "SURF EXL EASY WSH") and traps:
    - a product called "Lifebuoy **Total**";
    - "Rounded Net Amt" below "Net Payable";
    - an Amazon invoice whose item line carries IGST;
    - Hindi item names on a kirana bill;
    - an electricity bill.
- **What the dev failures taught.** Each led to a general fix, never a test-specific one:
  - "Total (incl. GST)" was being excluded as a tax line;
  - pharmacy lines failed the "mostly letters" check because of batch codes;
  - "Amount: Rs 500" on a fuel slip became an item;
  - "Item Total ₹295" was taken for the item table's header.
- **Every remaining test failure is listed** in [the report](../../ml-service/reports/receipts/report.md). Highlights:
  - a product named "Total" ends the item list early;
  - the pharmacy's rounded amount loses to "Net Payable";
  - Hindi words (sabun, chini) and heavy abbreviations aren't in the lexicon.
- **Gates in CI** fail the build if, on the test set, total accuracy falls below 0.85, date below 0.9, merchant below 0.85, item F1 below 0.8 or grouping below 0.8. The end-to-end run has its own floor.

## 8. Serving

`POST /v1/receipts/scan`:
- takes a JPEG/PNG/WebP photo or a PDF, up to 8 MB, checked by its bytes rather than its name;
- needs the user's token;
- returns the fields, items, groups, warnings and the text that was read.

How it runs:
- **One scan at a time** (an `asyncio` lock), in a worker thread, so a long OCR never blocks other requests.
- **The OCR engine loads on the first scan**, not at start-up; the Docker build downloads its models once.
- **Nothing is stored, and no bill text is logged**: only counts and which fields were found.
- **On Render's free plan** (one tenth of a CPU) a scan takes noticeably longer than on a laptop. The browser wakes the server when the scanner opens, sends a shrunken JPEG, and allows up to two minutes.

## 9. Storage and privacy

- A private `receipts` bucket (10 MB; JPEG, PNG, WebP, PDF).
- Storage policies let users add, read and delete files **only in their own `receipts/<user id>/` folder**.
- `transactions.receipt_path` links the transactions made from a bill; a split bill shares one file.
- Bills are shown through **signed links that expire after a minute**.
- Deleting the last transaction of a bill deletes the file, and deleting the account empties the folder.
- The migration is tested on a fresh database and on a replica of the production schema.

## Reproduce

```bash
cd ml-service
pytest tests/test_receipts.py                        # unit, endpoint and real-OCR tests
python -m training.evaluate_receipts --gate          # parsing on dev and test bills
python -m training.evaluate_receipt_ocr --ablation   # the whole pipeline on rendered photos
python -m training.receipt_samples --write-dev       # regenerate the dev bills (seeded)
```

## Interview questions this step answers

- *How do you build OCR for receipts without paid APIs?* Read a PDF's text layer when there is one. Otherwise use OpenCV clean-up, then a small deep-learning OCR (PP-OCR detection + recognition on ONNX Runtime), then rules that understand bills, and always a human review before saving.
- *Why did you switch from Tesseract?* It needed a system binary I couldn't run in development. The alternative was pip-installable, faster to iterate on, and read a damaged test photo perfectly. I decided with an experiment, not by reputation.
- *How do you find the total on a receipt?* By keyword strength and position, with explicit exclusions (sub total, savings, tax, tendered, change), not by "the largest number". The largest number scores 31% on the test set; the keyword rules score 94%.
- *How do you split a bill by category?* A product lexicon with fuzzy matching groups the items, groups map onto the user's own categories, and tax and discount are spread in proportion so the parts add up to the total.
- *How do you evaluate a pipeline like this?* At two levels: parsing on bill text (dev generated, test hand-written first) and the whole pipeline on rendered photos with an ablation per OpenCV step. Both are gates in CI.
- *What about privacy?* The server never stores bills. Files go to a private bucket with per-user folder policies, are shown through expiring links, and are deleted with the transaction or the account.
