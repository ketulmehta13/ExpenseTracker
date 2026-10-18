"""POST /v1/categorize: suggest a category while the user types a transaction.

A cascade, cheapest and most personal first:
1. The user's own history: a past transaction with the same (or nearly the same) title.
2. The model: shown only above the confidence threshold chosen at training time.
3. Nothing. A missing suggestion costs the user a click; a wrong one costs trust.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.ml.categorizer import CategorizerModel
from app.ml.history import UserHistory
from app.ml.taxonomy import display_name, match_user_category
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1", tags=["categorize"])
logger = logging.getLogger("ml_service.categorize")

HISTORY_LIMIT = 2000  # most recent categorized transactions to learn the user's habits from
HISTORY_MIN_CONFIDENCE = 0.6


class CategorizeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    amount: float | None = Field(default=None, ge=0)
    type: Literal["EXPENSE", "INCOME"] = "EXPENSE"


class Suggestion(BaseModel):
    category_id: int | str | None = Field(
        description="The user's category; null when they have no category for this label"
    )
    category_name: str
    label: str | None = Field(description="The model's canonical label; null for history matches")
    confidence: float
    source: Literal["history", "model"]


class CategorizeResponse(BaseModel):
    suggestion: Suggestion | None
    model_version: str | None


@dataclass(frozen=True)
class UserContext:
    history: UserHistory
    categories: list[dict]


async def load_user_context(request: Request, user: CurrentUser, data: SupabaseData) -> UserContext:
    """The user's history and categories, cached briefly: the form calls this on every pause in typing."""
    cache = request.app.state.user_context_cache
    context = cache.get(user.id)
    if context is None:
        transactions, categories = await asyncio.gather(
            data.select(
                "transactions",
                {"select": "title,category_id", "category_id": "not.is.null", "order": "date.desc,id.desc"},
                limit=HISTORY_LIMIT,
            ),
            data.select("categories", {"select": "id,name,user_id", "order": "id"}, limit=1000),
        )
        context = UserContext(UserHistory(transactions), categories)
        cache.put(user.id, context)
    return context


async def suggest_category(
    request: Request,
    user: CurrentUser,
    data: SupabaseData,
    title: str,
    amount: float | None,
    tx_type: str,
) -> CategorizeResponse:
    """The cascade itself, shared with POST /v1/parse."""
    model: CategorizerModel | None = request.app.state.categorizer
    model_version = model.version if model else None
    context = await load_user_context(request, user, data)
    categories_by_id = {str(category["id"]): category for category in context.categories}

    match = context.history.match(title)
    if match and match.confidence >= HISTORY_MIN_CONFIDENCE and str(match.category_id) in categories_by_id:
        category = categories_by_id[str(match.category_id)]
        logger.info("categorize source=history confidence=%.2f", match.confidence)
        request.app.state.metrics.event("categorize", "history")
        return CategorizeResponse(
            suggestion=Suggestion(
                category_id=category["id"], category_name=category["name"], label=None,
                confidence=match.confidence, source="history",
            ),
            model_version=model_version,
        )

    if model is not None:
        # A few milliseconds of CPU: fine inline. A heavier model would go to a thread pool.
        prediction = model.predict(title, amount, tx_type)
        if prediction.confidence >= model.threshold:
            category = match_user_category(prediction.label, context.categories)
            logger.info(
                "categorize source=model label=%s confidence=%.2f", prediction.label, prediction.confidence
            )
            request.app.state.metrics.event("categorize", "model")
            return CategorizeResponse(
                suggestion=Suggestion(
                    category_id=category["id"] if category else None,
                    category_name=category["name"] if category else display_name(prediction.label),
                    label=prediction.label,
                    confidence=round(prediction.confidence, 4),
                    source="model",
                ),
                model_version=model_version,
            )

    logger.info("categorize source=none")
    request.app.state.metrics.event("categorize", "none")
    return CategorizeResponse(suggestion=None, model_version=model_version)


@router.post("/categorize", response_model=CategorizeResponse)
async def categorize(
    body: CategorizeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> CategorizeResponse:
    return await suggest_category(request, user, data, body.title, body.amount, body.type)
