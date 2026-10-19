"""OpenCV clean-up before OCR: turn a phone photo of a bill into a straight, evenly lit page.

Each step can be switched off, so the evaluation can measure what it adds
(`python -m training.evaluate_receipt_ocr --ablation`):

- size: the long side is brought to about 1,800 px. Bigger photos only cost time on a small
  server; small ones are scaled up so thin thermal-printer text survives.
- perspective: if the bill stands out from the table behind it, its four corners are found
  (edges -> the largest four-sided contour) and it is warped to a flat, top-down rectangle.
- deskew: the tilt of the text lines is measured with a projection profile (rows of text give
  the sharpest row-sum peaks when they are level) and undone.
- contrast: CLAHE evens out shadows and faded print. There is no hard black-and-white
  threshold: the OCR model reads grey levels better than a binarised page.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

ALL_STEPS = ("size", "perspective", "deskew", "contrast")
TARGET_LONG_SIDE = 1800
MIN_DOCUMENT_SHARE = 0.25  # the bill must cover a quarter of the photo to count as found
MAX_SKEW_DEGREES = 15.0


class UnreadableImage(ValueError):
    pass


def decode_image(data: bytes) -> np.ndarray:
    """Bytes -> a BGR array, turned as the camera's EXIF tag says (phones save portrait photos sideways)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        raise UnreadableImage("That file isn't an image we can read.") from err
    return cv2.cvtColor(np.asarray(upright), cv2.COLOR_RGB2BGR)


def resize(image: np.ndarray, long_side: int = TARGET_LONG_SIDE) -> np.ndarray:
    height, width = image.shape[:2]
    scale = long_side / max(height, width)
    if 0.9 <= scale <= 1.1:
        return image
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=interpolation)


def _order_corners(points: np.ndarray) -> np.ndarray:
    """Top-left, top-right, bottom-right, bottom-left."""
    sums, diffs = points.sum(axis=1), np.diff(points, axis=1).ravel()
    return np.array([points[np.argmin(sums)], points[np.argmin(diffs)],
                     points[np.argmax(sums)], points[np.argmax(diffs)]], dtype=np.float32)


def find_document(image: np.ndarray) -> np.ndarray | None:
    """The bill's four corners when it stands out from its background; None when it fills the photo."""
    height, width = image.shape[:2]
    scale = 500 / max(height, width)
    small = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))),
                       interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(contour) < MIN_DOCUMENT_SHARE * area:
            break
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order_corners(approx.reshape(4, 2).astype(np.float32) / scale)
    return None


def warp_document(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = corners
    width = int(max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left)))
    height = int(max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (width, height), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def _rotate(image: np.ndarray, degrees: float, border: int | tuple = cv2.BORDER_REPLICATE) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=border)


def _profile_score(ink: np.ndarray, degrees: float) -> float:
    rows = _rotate(ink, degrees, border=cv2.BORDER_CONSTANT).sum(axis=1, dtype=np.float64)
    return float(np.square(np.diff(rows)).sum())


def estimate_skew(image: np.ndarray) -> float:
    """The rotation, in degrees, that makes the text lines level (0 when unsure)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape
    scale = 600 / max(height, width)
    if scale < 1:
        gray = cv2.resize(gray, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if ink.mean() < 1:  # a blank page: nothing to level
        return 0.0
    # Coarse search in whole degrees, then refine around the best in fifths of a degree
    angles = np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + 1, 1.0)
    coarse = max(angles, key=lambda a: _profile_score(ink, a))
    fine = max(np.arange(coarse - 1, coarse + 1.01, 0.2), key=lambda a: _profile_score(ink, a))
    level = _profile_score(ink, 0.0)
    # Rotate only when it clearly helps: a straight page shouldn't be nudged by noise
    return float(round(fine, 1)) if _profile_score(ink, fine) > level * 1.05 else 0.0


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    even = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(even, cv2.COLOR_GRAY2BGR)


def prepare(image: np.ndarray, steps: tuple[str, ...] = ALL_STEPS) -> tuple[np.ndarray, list[str]]:
    """Apply the enabled steps; returns the image and the steps that actually changed something."""
    applied: list[str] = []
    if "size" in steps:
        resized = resize(image)
        if resized is not image:
            applied.append("size")
        image = resized
    if "perspective" in steps and (corners := find_document(image)) is not None:
        image = warp_document(image, corners)
        applied.append("perspective")
    if "deskew" in steps and (angle := estimate_skew(image)):
        image = _rotate(image, angle)
        applied.append("deskew")
    if "contrast" in steps:
        image = enhance_contrast(image)
        applied.append("contrast")
    return image, applied
