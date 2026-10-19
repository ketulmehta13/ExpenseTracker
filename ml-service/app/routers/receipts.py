"""POST /v1/receipts/scan: a photo or PDF of a bill -> merchant, date, total and category groups.

Nothing is saved here. The app shows the result for review, and on Save it stores the file in
the user's private storage folder and creates the transactions itself, through Supabase with
the user's own token.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.dates import resolve_today
from app.receipts.items import group_items
from app.receipts.ocr import ReadResult, UnreadableFile, detect_kind, load_engine, read_image, read_pdf
from app.receipts.parse import parse_receipt
from app.routers.categorize import Suggestion, load_user_context, suggest_category
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1/receipts", tags=["receipts"])
logger = logging.getLogger("ml_service.receipts")

MAX_UPLOAD_BYTES = 8 * 2**20
LOW_CONFIDENCE = 0.75  # mean OCR confidence below this: ask the user to check carefully
MAX_LINES_RETURNED = 200


class ScanItem(BaseModel):
    name: str
    amount: float
    group: str


class ScanGroup(BaseModel):
    key: str = Field(description="The item group(s) in it, e.g. 'household+personal_care'")
    name: str
    category_id: int | str | None
    category_name: str | None
    amount: float = Field(description="The items' sum plus their share of tax, discount and round-off")
    items: list[ScanItem]


class ScanResponse(BaseModel):
    source: Literal["pdf_text", "ocr"]
    ocr_confidence: float | None
    pages: int
    merchant: str | None
    date: date | None
    total: float | None
    found: dict[str, bool]
    items: list[ScanItem]
    groups: list[ScanGroup]
    items_total: float
    adjustment: float = Field(description="The total minus the item sum: tax, discounts and round-off")
    suggestion: Suggestion | None = Field(description="A category for the whole bill, as one transaction")
    model_version: str | None
    warnings: list[str]
    lines: list[str] = Field(description="The text read from the bill, top to bottom")


def _item(item) -> ScanItem:
    return ScanItem(name=item.name, amount=item.amount, group=item.group)


def get_ocr_engine(request: Request):
    """Loaded on the first scan, not at start-up: most servers never scan a bill."""
    state = request.app.state
    if state.ocr_engine is None:
        state.ocr_engine = load_engine(state.settings.ocr_threads)
    return state.ocr_engine


def _read(content: bytes, kind: str, request: Request) -> ReadResult:
    if kind == "pdf":
        return read_pdf(content, lambda: get_ocr_engine(request))
    return read_image(content, get_ocr_engine(request))


@router.post("/scan", response_model=ScanResponse)
async def scan(
    request: Request,
    file: UploadFile = File(..., description="A JPEG, PNG or WebP photo, or a PDF, up to 8 MB"),
    today: date | None = Form(None, description="The user's local date, so a bill isn't dated in the future"),
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> ScanResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "That file is too large: 8 MB at most.")
    kind = detect_kind(content)
    if kind is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a JPEG, PNG or WebP photo, or a PDF."
        )

    # One bill at a time: OCR is the heaviest thing this server does, and it runs off the event loop
    async with request.app.state.ocr_lock:
        try:
            read = await asyncio.to_thread(_read, content, kind, request)
        except UnreadableFile as err:
            request.app.state.metrics.event("receipt", "unreadable")
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
    if not read.lines:
        request.app.state.metrics.event("receipt", "no_text")
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "No text was found. Take the photo in good light, with the whole bill in the frame.",
        )

    context = await load_user_context(request, user, data)
    draft = parse_receipt(read.lines, resolve_today(today), context.history.titles[:500])
    groups, adjustment, group_warnings = group_items(
        draft.items, draft.total, context.categories, draft.merchant, read.lines
    )
    warnings = draft.warnings + group_warnings
    if read.confidence is not None and read.confidence < LOW_CONFIDENCE:
        warnings.append("low_confidence")

    suggestion, model_version = None, None
    title = draft.merchant or " ".join(item.name for item in draft.items[:3])
    if title:
        result = await suggest_category(request, user, data, title, draft.total, "EXPENSE")
        suggestion, model_version = result.suggestion, result.model_version

    found = draft.found
    outcome = "full" if all(found.values()) else ("partial" if any(found.values()) else "failed")
    request.app.state.metrics.event("receipt", outcome)
    logger.info(
        "receipt source=%s steps=%s lines=%d found=%s items=%d groups=%d warnings=%s",
        read.source, read.steps, len(read.lines), found, len(draft.items), len(groups), warnings,
    )
    return ScanResponse(
        source=read.source,
        ocr_confidence=read.confidence,
        pages=read.pages,
        merchant=draft.merchant,
        date=draft.date,
        total=draft.total,
        found=found,
        items=[_item(item) for group in groups for item in group.items],
        groups=[
            ScanGroup(
                key=group.key,
                name=group.name,
                category_id=group.category["id"] if group.category else None,
                category_name=group.category["name"] if group.category else None,
                amount=group.amount,
                items=[_item(item) for item in group.items],
            )
            for group in groups
        ],
        items_total=round(sum(item.amount for item in draft.items), 2),
        adjustment=adjustment,
        suggestion=suggestion,
        model_version=model_version,
        warnings=warnings,
        lines=read.lines[:MAX_LINES_RETURNED],
    )
