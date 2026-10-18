"""GET /v1/insights: unusual spending, recurring payments and the month-end forecast.
GET /v1/insights/summary: the same month in two or three sentences.

Computed on request from the user's last ~13 months, read with their own token (RLS), and
cached briefly. Nothing is stored, so there are no extra tables and no admin key.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.dates import resolve_today
from app.llm.summary import month_facts, summarize
from app.ml.anomaly import find_anomalies
from app.ml.forecast import forecast_month
from app.ml.recurring import find_recurring
from app.supabase import SupabaseData, get_data

router = APIRouter(prefix="/v1", tags=["insights"])
logger = logging.getLogger("ml_service.insights")

HISTORY_DAYS = 400  # a little over a year
RECENT_ANOMALY_DAYS = 60  # older unusual payments are no longer worth a card


class UnusualPayment(BaseModel):
    transaction_id: int | str
    title: str
    date: date
    amount: float
    category_id: int | str | None
    category_name: str | None
    usual_high: float  # the user's usual top payment (90th percentile) there
    typical_amount: float
    ratio: float
    compared_with: Literal["merchant", "category"]


class RecurringPayment(BaseModel):
    title: str
    category_id: int | str | None
    category_name: str | None
    period: str
    amount: float
    monthly_cost: float
    count: int
    last_date: date
    next_date: date
    active: bool


class MonthForecast(BaseModel):
    month: str
    spent_to_date: float
    projected_total: float
    low: float
    high: float
    expected_everyday: float
    expected_recurring: float
    budget: float | None
    probability_over_budget: float | None
    status: Literal["on_track", "at_risk", "over"] | None


class InsightsResponse(BaseModel):
    as_of: date
    unusual: list[UnusualPayment]
    recurring: list[RecurringPayment]
    recurring_monthly_total: float
    forecast: MonthForecast | None


def build_insights(transactions: list[dict], categories: list[dict], budget: float | None, today: date):
    names = {str(category["id"]): category["name"] for category in categories}

    def category_name(category_id) -> str | None:
        return names.get(str(category_id)) if category_id is not None else None

    rows = [
        {**tx, "amount": float(tx["amount"]), "date": str(tx["date"])[:10]}
        for tx in transactions if tx.get("amount") is not None and tx.get("date")
    ]
    by_id = {tx["id"]: tx for tx in rows}
    recurring = find_recurring(rows)
    anomalies = find_anomalies(rows)
    forecast = forecast_month(
        rows, today, recurring, exclude_ids={a.transaction_id for a in anomalies}, budget=budget
    )

    recent_since = (today - timedelta(days=RECENT_ANOMALY_DAYS)).isoformat()
    unusual = [
        UnusualPayment(
            transaction_id=a.transaction_id,
            title=by_id[a.transaction_id]["title"],
            date=by_id[a.transaction_id]["date"],
            amount=round(a.amount, 2),
            category_id=a.category_id,
            category_name=category_name(a.category_id),
            usual_high=a.usual_high,
            typical_amount=a.typical_amount,
            ratio=round(a.ratio, 1),
            compared_with=a.compared_with,
        )
        for a in anomalies if by_id[a.transaction_id]["date"] >= recent_since
    ]
    payments = [
        RecurringPayment(
            title=s.title,
            category_id=s.category_id,
            category_name=category_name(s.category_id),
            period=s.period,
            amount=s.amount,
            monthly_cost=round(s.monthly_cost, 2),
            count=s.count,
            last_date=s.last_date,
            next_date=s.next_date,
            active=s.is_active(today),
        )
        for s in recurring
    ]
    payments.sort(key=lambda p: (not p.active, -p.monthly_cost))
    month = None
    if forecast is not None:
        month = MonthForecast(
            month=forecast.month,
            spent_to_date=forecast.spent_to_date,
            projected_total=round(forecast.projected_total, 2),
            low=forecast.low,
            high=forecast.high,
            expected_everyday=forecast.expected_everyday,
            expected_recurring=forecast.expected_recurring,
            budget=forecast.budget,
            probability_over_budget=forecast.probability_over_budget,
            status=forecast.status,
        )
    return InsightsResponse(
        as_of=today,
        unusual=unusual,
        recurring=payments,
        recurring_monthly_total=round(sum(p.monthly_cost for p in payments if p.active), 2),
        forecast=month,
    )


@dataclass(frozen=True)
class InsightInputs:
    transactions: list[dict]
    categories: list[dict]
    budget: float | None
    insights: InsightsResponse


async def load_insights(
    request: Request, user: CurrentUser, data: SupabaseData, today: date
) -> InsightInputs:
    """The user's last ~13 months and the insights computed from them, cached per user and day."""
    cache = request.app.state.insights_cache
    cache_key = f"{user.id}:{today.isoformat()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    since = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    transactions, categories, profiles = await asyncio.gather(
        data.select(
            "transactions",
            {
                "select": "id,title,amount,type,category_id,date",
                "date": f"gte.{since}",
                "order": "date.desc,id.desc",
            },
            limit=10_000,
        ),
        data.select("categories", {"select": "id,name", "order": "id"}, limit=1000),
        data.select("profiles", {"select": "monthly_budget", "id": f"eq.{user.id}"}, limit=1),
    )
    budget = float(profiles[0]["monthly_budget"] or 0) if profiles else 0.0
    result = build_insights(transactions, categories, budget or None, today)
    logger.info(
        "insights unusual=%d recurring=%d forecast=%s",
        len(result.unusual), len(result.recurring), result.forecast is not None,
    )
    request.app.state.metrics.event("insights", "computed")
    inputs = InsightInputs(transactions, categories, budget or None, result)
    cache.put(cache_key, inputs)
    return inputs


@router.get("/insights", response_model=InsightsResponse)
async def insights(
    request: Request,
    today: date | None = Query(None, description="The user's local date (YYYY-MM-DD)"),
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> InsightsResponse:
    return (await load_insights(request, user, data, resolve_today(today))).insights


class SummaryResponse(BaseModel):
    text: str
    source: Literal["llm", "template"] = Field(description="llm only if every number in it was verified")


@router.get("/insights/summary", response_model=SummaryResponse)
async def insights_summary(
    request: Request,
    today: date | None = Query(None, description="The user's local date (YYYY-MM-DD)"),
    user: CurrentUser = Depends(get_current_user),
    data: SupabaseData = Depends(get_data),
) -> SummaryResponse:
    """Two or three sentences about the month: numbers from code, wording from an LLM if one is set."""
    today = resolve_today(today)
    inputs = await load_insights(request, user, data, today)
    facts = month_facts(inputs.transactions, inputs.categories, inputs.insights, today)
    # LLM calls take seconds, so a summary is reused for as long as its facts are unchanged
    cache_key = f"{user.id}:{hash(facts)}"
    cached = request.app.state.summary_cache.get(cache_key)
    if cached is None:
        timeout = request.app.state.settings.llm_timeout_seconds
        text, source = await summarize(request.app.state.llm, facts, timeout)
        cached = SummaryResponse(text=text, source=source)
        request.app.state.metrics.event("summary", source)
        request.app.state.summary_cache.put(cache_key, cached)
    return cached
