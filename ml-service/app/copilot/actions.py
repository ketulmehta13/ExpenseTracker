"""Writes the copilot can propose: add a transaction, change the monthly budget.

Nothing is written when the user asks. The copilot replies with an action block: the parsed
fields, an idempotency key and a one-line summary. The user can edit the fields and confirm.
Confirming (POST /v1/copilot/actions/confirm) then:
1. validates the fields again on the server (types, ranges, dates, and that the category is one
   of the user's own); the client's copy is never trusted;
2. claims the idempotency key in copilot_actions (unique per user), so a double click, a retry
   after a timeout or a replayed request runs the write at most once and returns the first result;
3. writes with the user's own token (RLS applies; user_id comes from the verified token);
4. records the result on the claim.
If the copilot_actions table doesn't exist yet (migration not applied), claims fall back to an
in-process cache: still safe against double clicks, but not across restarts or servers.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.cache import TTLCache
from app.copilot.facts import inr
from app.copilot.schemas import ActionBlock, BudgetFields, TransactionFields
from app.nlp.quickadd import amounts_in, parse_quick_add
from app.supabase import SupabaseData

logger = logging.getLogger("ml_service.copilot")

_COMMAND = re.compile(r"^(add|log|record|note|track|save|enter)\s+", re.IGNORECASE)
_local_claims: TTLCache[dict] = TTLCache(24 * 3600, max_entries=10_000)


def new_key() -> str:
    return secrets.token_urlsafe(18)  # 24 URL-safe characters


def propose_transaction(text: str, today: date, category: dict | None) -> ActionBlock | None:
    parsed = parse_quick_add(_COMMAND.sub("", text.strip()), today)
    if parsed.amount is None or not parsed.title:
        return None
    fields = TransactionFields(
        title=parsed.title[:100],
        amount=parsed.amount,
        date=parsed.date,
        type=parsed.type,
        category_id=category["id"] if category else None,
        category_name=category["name"] if category else None,
    )
    kind = "income" if fields.type == "INCOME" else "expense"
    where = f" in {fields.category_name}" if fields.category_name else ""
    summary = f"Add {kind}: {fields.title}, {inr(fields.amount)} on {fields.date:%d %b %Y}{where}."
    return ActionBlock(action="create_transaction", idempotency_key=new_key(), fields=fields, summary=summary)


_BUDGET_TO = re.compile(r"\bto\s*(?:rs\.?|₹|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lakh|lac)?\b", re.IGNORECASE)
_SCALE = {"k": 1_000, "lakh": 100_000, "lac": 100_000}


def propose_budget(text: str, current: float | None) -> ActionBlock | None:
    # The amount after "to" ("set my budget to 30k"); other numbers (an id, a year) are ignored
    match = _BUDGET_TO.search(text)
    if match:
        amount = float(match[1].replace(",", "")) * _SCALE.get((match[2] or "").lower(), 1)
    else:
        amounts = [a for a in amounts_in(text.lower()) if a > 0]
        if len(amounts) != 1:
            return None  # none, or several: ask instead of guessing
        amount = amounts[0]
    fields = BudgetFields(monthly_budget=amount, previous_budget=current)
    before = f" (now {inr(current)})" if current else ""
    summary = f"Set your monthly budget to {inr(fields.monthly_budget)}{before}."
    return ActionBlock(action="update_budget", idempotency_key=new_key(), fields=fields, summary=summary)


def validate_fields(action: str, raw: dict, categories: list[dict], today: date):
    """Server-side validation of what the user confirmed (they may have edited it)."""
    try:
        if action == "update_budget":
            return BudgetFields.model_validate(raw)
        fields = TransactionFields.model_validate(raw)
    except ValidationError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Those details aren't valid") from err
    if not today - timedelta(days=5 * 366) <= fields.date <= today + timedelta(days=366):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The date must be within five years")
    if fields.category_id is not None:
        owned = {str(c["id"]): c["name"] for c in categories}
        if str(fields.category_id) not in owned:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That category isn't one of yours")
        fields.category_name = owned[str(fields.category_id)]
    fields.title = " ".join(fields.title.split())
    return fields


@dataclass
class Claim:
    fresh: bool  # True: this request owns the key and must run the write
    result: dict | None = None
    stored: bool = True  # False: the in-process fallback was used


async def claim(data: SupabaseData, user_id: str, key: str, action: str) -> Claim:
    response = await data.request(
        "POST", "copilot_actions", json={"idempotency_key": key, "action": action}, prefer="return=minimal"
    )
    if response.status_code in (200, 201, 204):
        return Claim(True)
    if response.status_code == 409:  # the key was claimed before: return what happened then
        rows = await data.request(
            "GET", "copilot_actions", params={"select": "status,result", "idempotency_key": f"eq.{key}"}
        )
        row = (rows.json() or [{}])[0] if rows.status_code == 200 else {}
        return Claim(False, row.get("result") if row.get("status") == "done" else None)
    if response.status_code == 404:  # PostgREST: the table doesn't exist (migration not applied)
        local_key = f"{user_id}:{key}"
        if (seen := _local_claims.get(local_key)) is not None:
            return Claim(False, seen or None, stored=False)
        _local_claims.put(local_key, {})
        logger.warning("copilot_actions table missing: idempotency is per process until the migration runs")
        return Claim(True, stored=False)
    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not record the action")


async def finish(data: SupabaseData, user_id: str, key: str, result: dict, stored: bool) -> None:
    if not stored:
        _local_claims.put(f"{user_id}:{key}", result)
        return
    await data.request(
        "PATCH",
        "copilot_actions",
        params={"idempotency_key": f"eq.{key}"},
        json={"status": "done", "result": result},
        prefer="return=minimal",
    )


async def execute(action: str, fields, data: SupabaseData, user_id: str) -> tuple[dict, str]:
    """Run a validated write as the user. Returns the stored row and a one-line confirmation."""
    if action == "create_transaction":
        row = {
            "title": fields.title,
            "amount": fields.amount,
            "date": fields.date.isoformat(),
            "type": fields.type,
            "category_id": fields.category_id,
            "user_id": user_id,
            "notes": "",
            "is_recurring": False,
        }
        saved = await data.insert("transactions", row)
        kind = "income" if fields.type == "INCOME" else "expense"
        return saved, f"Saved {kind}: {fields.title}, {inr(fields.amount)} on {fields.date:%d %b}."
    response = await data.request(
        "PATCH",
        "profiles",
        params={"id": f"eq.{user_id}"},
        json={"monthly_budget": fields.monthly_budget},
        prefer="return=representation",
    )
    if response.status_code != 200 or not response.json():
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not update the budget")
    return response.json()[0], f"Your monthly budget is now {inr(fields.monthly_budget)}."
