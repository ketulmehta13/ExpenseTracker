"""End-to-end evaluation of bill scanning on rendered "phone photos": OpenCV -> OCR -> parsing.

Usage (from ml-service/):
    python -m training.evaluate_receipt_ocr             # the full pipeline, writes reports/receipt_ocr/
    python -m training.evaluate_receipt_ocr --ablation  # ...plus the pipeline with steps switched off
    python -m training.evaluate_receipt_ocr --gate      # fail if the full pipeline misses a floor

Bills from training/receipt_samples.py are drawn as paper receipts, then damaged the way a phone
photo is: a table behind the bill, a perspective tilt, rotation, blur, uneven light, sensor noise
and JPEG compression. A third are "scans": the bill fills the frame, with mild damage. The OCR
model is the real one (downloaded on first use), so this runs in CI only, not in the unit tests.

The ablation answers "what does each OpenCV step add?" by running the same photos with the
preprocessing steps switched on one at a time.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.receipts.ocr import load_engine, read_image
from app.receipts.preprocess import ALL_STEPS
from training.evaluate_receipts import CATEGORIES, TODAY, _match_items, _same_merchant
from training.receipt_samples import generate
from training.runs import record_run

DEFAULT_REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "receipt_ocr"
VARIANTS = {
    "no preprocessing": (),
    "size": ("size",),
    "+ perspective": ("size", "perspective"),
    "+ deskew": ("size", "perspective", "deskew"),
    "full (+ contrast)": ALL_STEPS,
}
FLOORS = {"total": 0.8, "date": 0.8, "merchant": 0.8}


def render(bill: dict, rng: random.Random) -> bytes:
    """A bill drawn on paper and photographed badly; returns JPEG bytes."""
    font = ImageFont.load_default(size=24)
    lines = [line.replace("₹", "Rs.") for line in bill["lines"]]  # the built-in font has no rupee sign
    width = max(560, 40 + max(int(font.getlength(line)) for line in lines))
    paper = Image.new("L", (width, 60 + 34 * len(lines)), rng.randint(238, 252))
    draw = ImageDraw.Draw(paper)
    for row, line in enumerate(lines):
        draw.text((20, 30 + 34 * row), line, fill=rng.randint(15, 70), font=font)
    sheet = np.asarray(paper, dtype=np.float32)

    scan = rng.random() < 1 / 3
    if scan:
        photo = sheet
        angle = rng.uniform(-2.5, 2.5)
    else:
        # A table behind the bill, then the camera's perspective
        height, width = sheet.shape
        pad_x, pad_y = int(width * rng.uniform(0.15, 0.3)), int(height * rng.uniform(0.08, 0.15))
        photo = np.full((height + 2 * pad_y, width + 2 * pad_x), rng.uniform(70, 160), np.float32)
        photo[pad_y : pad_y + height, pad_x : pad_x + width] = sheet
        h, w = photo.shape
        jitter = lambda: rng.uniform(-0.05, 0.05)  # noqa: E731
        source = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        target = np.float32(
            [
                [w * jitter(), h * jitter()],
                [w * (1 + jitter()), h * jitter()],
                [w * (1 + jitter()), h * (1 + jitter())],
                [w * jitter(), h * (1 + jitter())],
            ]
        )
        photo = cv2.warpPerspective(
            photo, cv2.getPerspectiveTransform(source, target), (w, h), borderMode=cv2.BORDER_REPLICATE
        )
        angle = rng.uniform(-7, 7)
    h, w = photo.shape
    photo = cv2.warpAffine(
        photo, cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0), (w, h), borderMode=cv2.BORDER_REPLICATE
    )
    photo = cv2.GaussianBlur(photo, (0, 0), rng.uniform(0.3, 1.0 if scan else 1.4))
    light = np.linspace(rng.uniform(0.7, 0.9), rng.uniform(0.95, 1.08), w)[None, :]
    photo = photo * (light if rng.random() < 0.5 else light[:, ::-1])
    photo = photo + np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(3, 9), photo.shape)
    image = Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=rng.randint(55, 85))
    return buffer.getvalue()


def evaluate(bills: list[dict], photos: list[bytes], engine, steps: tuple[str, ...]) -> dict:
    from app.receipts.items import group_items
    from app.receipts.parse import parse_receipt

    counts = {"merchant": 0, "date": 0, "total": 0}
    got_items = want_items = matched = 0
    seconds = []
    for bill, photo in zip(bills, photos, strict=True):
        started = time.perf_counter()
        read = read_image(photo, engine, steps)
        draft = parse_receipt(read.lines, TODAY)
        groups, _, _ = group_items(draft.items, draft.total, CATEGORIES, draft.merchant, read.lines)
        seconds.append(time.perf_counter() - started)
        counts["merchant"] += _same_merchant(draft.merchant, bill["merchant"])
        counts["date"] += draft.date is not None and draft.date.isoformat() == bill["date"]
        counts["total"] += draft.total is not None and abs(draft.total - bill["total"]) <= 0.01
        items = [{"name": i.name, "amount": i.amount, "group": i.group} for g in groups for i in g.items]
        got_items += len(items)
        want_items += len(bill["items"])
        matched += len(_match_items(items, bill["items"]))
    precision = matched / got_items if got_items else 1.0
    recall = matched / want_items if want_items else 1.0
    result = {key: round(value / len(bills), 4) for key, value in counts.items()}
    result["item_f1"] = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    result["seconds_per_bill"] = round(float(np.mean(seconds)), 2)
    return result


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def report(metrics: dict) -> str:
    rows = [
        [
            name,
            f"{m['merchant']:.0%}",
            f"{m['date']:.0%}",
            f"{m['total']:.0%}",
            f"{m['item_f1']:.2f}",
            f"{m['seconds_per_bill']:.1f} s",
        ]
        for name, m in metrics["variants"].items()
    ]
    gate = _table(
        ["Check (full pipeline)", "Result"],
        [[name, "pass" if ok else "**FAIL**"] for name, ok in metrics["gate"].items()],
    )
    return f"""# Bill scanning, end to end: evaluation report

Generated by `python -m training.evaluate_receipt_ocr` on {metrics["generated_at"]}. Do not edit by hand.

{metrics["bills"]} bills from `training/receipt_samples.py`, drawn on paper and "photographed": two thirds
on a table with a perspective tilt and rotation up to 7°, a third as scans; all with blur, uneven light,
noise and JPEG compression. OCR: RapidOCR (PP-OCR models on ONNX Runtime), {metrics["threads"]} thread(s)
on the machine that generated this report.

{_table(["Pipeline", "Merchant", "Date", "Total", "Items F1", "Time"], rows)}

## Evaluation gate

{gate}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate bill scanning end to end on rendered photos.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--bills", type=int, default=24)
    parser.add_argument("--threads", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--ablation", action="store_true", help="also run with preprocessing steps switched off"
    )
    parser.add_argument("--gate", action="store_true", help="fail if the full pipeline misses a floor")
    args = parser.parse_args(argv)

    rng = random.Random(23)
    bills = generate(args.bills, seed=23, noise=False)
    photos = [render(bill, rng) for bill in bills]
    engine = load_engine(args.threads)
    names = list(VARIANTS) if args.ablation else ["full (+ contrast)"]
    metrics: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "bills": len(bills),
        "threads": args.threads,
        "variants": {},
    }
    for name in names:
        metrics["variants"][name] = evaluate(bills, photos, engine, VARIANTS[name])
        print(f"{name:<20} {metrics['variants'][name]}")
    full = metrics["variants"]["full (+ contrast)"]
    metrics["gate"] = {
        f"{name} >= {floor} (got {full[name]:.3f})": full[name] >= floor for name, floor in FLOORS.items()
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (args.report_dir / "report.md").write_text(report(metrics), encoding="utf-8")
    print(f"reports: {args.report_dir}")
    record_run(
        "receipt_ocr",
        args.report_dir,
        {"bills": len(bills), "ablation": args.ablation},
        {key: full[key] for key in ("merchant", "date", "total", "item_f1", "seconds_per_bill")},
    )
    failed = [name for name, ok in metrics["gate"].items() if not ok]
    for name in failed:
        print(f"FAILED evaluation gate: {name}")
    return 1 if args.gate and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
