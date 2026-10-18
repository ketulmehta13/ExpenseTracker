"""POST /v1/parse: one line of text ("swiggy 450 yesterday") -> a transaction draft.

The rule-based parser fills title, amount, date and type, and the categorizer's cascade (the
user's history, then the model) suggests a category for the parsed title. Nothing is saved:
the app opens the transaction form pre-filled, and the user confirms.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.dates import resolve_today
from app.nlp.quickadd import parse_quick_add
from app.routers.categorize import Suggestion, suggest_category
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1", tags=["parse"])
logger = logging.getLogger("ml_service.parse")


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    today: date | None = Field(None, description="The user's local date, for words like 'yesterday'")


class ParseResponse(BaseModel):
    title: str
    amount: float | None
    date: date
    type: Literal["EXPENSE", "INCOME"]
    found: dict[str, bool] = Field(description="Which fields came from the text rather than a default")
    suggestion: Suggestion | None
    model_version: str | None


@router.post("/parse", response_model=ParseResponse)
async def parse(
    body: ParseRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> ParseResponse:
    parsed = parse_quick_add(body.text, resolve_today(body.today))
    suggestion, model_version = None, None
    if parsed.title:
        result = await suggest_category(request, user, data, parsed.title, parsed.amount, parsed.type)
        suggestion, model_version = result.suggestion, result.model_version
    logger.info("parse found=%s suggestion=%s", parsed.found, suggestion.source if suggestion else None)
    return ParseResponse(
        title=parsed.title,
        amount=parsed.amount,
        date=parsed.date,
        type=parsed.type,
        found=parsed.found,
        suggestion=suggestion,
        model_version=model_version,
    )
