"""Read a bill into lines of text: a PDF's own text layer when it has one, otherwise OCR.

OCR is RapidOCR: PaddleOCR's PP-OCR models, a text detector (finds each piece of text as a
four-cornered box, tilted if the photo is) and a text recogniser, run by ONNX Runtime on the CPU.
The detector returns pieces, not lines: on a bill "TATA SALT 1KG" and "28.00" at the far right
are separate boxes, and on a tilted photo they aren't at the same height. `lines_from_boxes`
rebuilds the printed lines: it measures the tilt from the boxes themselves, levels their
centres, and joins boxes whose centres share a row.
"""

from __future__ import annotations

import logging
import math
import statistics
import threading
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from app.receipts.preprocess import ALL_STEPS, decode_image, prepare

logger = logging.getLogger("ml_service.receipts")

MAX_PDF_PAGES = 3
PDF_TEXT_MIN_CHARS = 40  # less than this and the PDF is a scan: OCR its pages instead
PDF_RENDER_SCALE = 200 / 72  # about 200 dpi

Kind = Literal["image", "pdf"]


class UnreadableFile(ValueError):
    """The file can't be read: not an image or PDF we support, damaged, or password-protected."""


@dataclass(frozen=True)
class ReadResult:
    lines: list[str]
    source: Literal["pdf_text", "ocr"]
    confidence: float | None  # mean OCR confidence, 0-1; None for a PDF's text layer
    pages: int = 1
    steps: list[str] = field(default_factory=list)  # preprocessing steps that changed the image


def detect_kind(data: bytes) -> Kind | None:
    """Trust the bytes, not the file name or the browser's content type."""
    if data.startswith(b"%PDF"):
        return "pdf"
    is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) or is_webp:
        return "image"
    return None


_engine_lock = threading.Lock()


def load_engine(threads: int = 1) -> Any:
    """The OCR engine. Its models are downloaded on first use (the Docker build does it once)."""
    from rapidocr import RapidOCR

    with _engine_lock:
        return RapidOCR(params={
            "Global.log_level": "critical",
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })


def lines_from_boxes(boxes: Any, texts: Any, scores: Any) -> tuple[list[str], float | None]:
    """Group OCR text boxes into printed lines, top to bottom, left to right, even on a tilted photo."""
    pieces = []
    for box, text, score in zip(boxes if boxes is not None else [], texts or [], scores or [], strict=False):
        points = np.asarray(box, dtype=float)  # top-left, top-right, bottom-right, bottom-left
        width = float(np.linalg.norm(points[1] - points[0]))
        height = float(np.linalg.norm(points[3] - points[0]) + np.linalg.norm(points[2] - points[1])) / 2
        angle = math.atan2(points[1][1] - points[0][1], points[1][0] - points[0][0]) if width else 0.0
        pieces.append((points.mean(axis=0), height, angle, width, str(text).strip(), float(score)))
    pieces = [piece for piece in pieces if piece[4]]
    if not pieces:
        return [], None

    # The page's tilt: the median angle of the wider boxes (short ones are too noisy to measure)
    wide = [angle for _, _, angle, width, _, _ in pieces if width >= 40] or [piece[2] for piece in pieces]
    tilt = statistics.median(wide)
    cos, sin = math.cos(tilt), math.sin(tilt)
    levelled = sorted(
        ((x * cos + y * sin, -x * sin + y * cos, height, text) for (x, y), height, _, _, text, _ in pieces),
        key=lambda piece: piece[1],
    )
    tolerance = 0.6 * statistics.median(piece[2] for piece in levelled)

    rows: list[list[tuple[float, float, float, str]]] = []
    for piece in levelled:
        if rows and abs(piece[1] - statistics.fmean(p[1] for p in rows[-1])) <= tolerance:
            rows[-1].append(piece)
        else:
            rows.append([piece])
    lines = [" ".join(text for _, _, _, text in sorted(row)) for row in rows]
    return lines, round(statistics.fmean(piece[5] for piece in pieces), 4)


def _ocr_image(image: np.ndarray, engine: Any) -> tuple[list[str], float | None]:
    result = engine(image)
    return lines_from_boxes(result.boxes, result.txts, result.scores)


def read_image(data: bytes, engine: Any, steps: tuple[str, ...] = ALL_STEPS) -> ReadResult:
    try:
        image = decode_image(data)
    except ValueError as err:
        raise UnreadableFile(str(err)) from err
    prepared, applied = prepare(image, steps)
    lines, confidence = _ocr_image(prepared, engine)
    return ReadResult(lines, "ocr", confidence, 1, applied)


def read_pdf(data: bytes, engine_factory: Any, steps: tuple[str, ...] = ALL_STEPS) -> ReadResult:
    """A PDF's text layer (e-bills and invoices have one); scanned PDFs are rendered and OCR'd."""
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as err:
        raise UnreadableFile(
            "That PDF can't be opened. If it has a password, remove it and try again."
        ) from err
    try:
        count = min(len(document), MAX_PDF_PAGES)
        text_lines: list[str] = []
        for index in range(count):
            page = document[index]
            text = page.get_textpage().get_text_range()
            text_lines += [line.strip() for line in text.splitlines() if line.strip()]
        if sum(len(line) for line in text_lines) >= PDF_TEXT_MIN_CHARS:
            return ReadResult(text_lines, "pdf_text", None, count, [])

        # A scan saved as PDF: OCR each page (already flat, so no perspective step)
        engine = engine_factory()
        lines: list[str] = []
        confidences: list[float] = []
        for index in range(count):
            rendered = document[index].render(scale=PDF_RENDER_SCALE).to_pil().convert("RGB")
            image = np.asarray(rendered)[:, :, ::-1].copy()
            prepared, _ = prepare(image, tuple(step for step in steps if step != "perspective"))
            page_lines, confidence = _ocr_image(prepared, engine)
            lines += page_lines
            if confidence is not None:
                confidences.append(confidence)
        confidence = round(statistics.fmean(confidences), 4) if confidences else None
        return ReadResult(lines, "ocr", confidence, count, [])
    finally:
        document.close()
