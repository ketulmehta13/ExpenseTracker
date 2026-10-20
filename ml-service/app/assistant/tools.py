"""The assistant's tools: plain functions over the user's data, and the replies built from them.

Every number in a reply is computed here and written by a template; no model ever does
arithmetic or chooses a figure.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from app.assistant.router import Period
from app.llm.summary import money
from app.ml.recurring import merchant_key


def _day(tx: dict) -> date:
    return date.fromisoformat(str(tx["date"])[:10])


def _short_date(day: date | str) -> str:
    day = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return f"{day.day} {day:%b}"


def spending(transactions: list[dict], period: Period, category: dict | None = None,
             merchant: str | None = None) -> dict:
    rows = [
        tx for tx in transactions
        if tx.get("type") == "EXPENSE" and period.start <= _day(tx) <= period.end
        and (category is None or str(tx.get("category_id")) == str(category["id"]))
        and (merchant is None or merchant_key(tx.get("title")) == merchant)
    ]
    return {"total": round(sum(float(tx["amount"]) for tx in rows), 2), "count": len(rows)}


def breakdown(
    transactions: list[dict], categories: list[dict], period: Period
) -> list[tuple[str, float, float]]:
    """(category name, amount, share of the period's spending), largest first."""
    names = {str(category["id"]): category["name"] for category in categories}
    totals: dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.get("type") == "EXPENSE" and period.start <= _day(tx) <= period.end:
            totals[names.get(str(tx.get("category_id")), "Uncategorized")] += float(tx["amount"])
    overall = sum(totals.values())
    return [(name, amount, amount / overall) for name, amount in sorted(totals.items(), key=lambda i: -i[1])]


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def spending_reply(result: dict, period: Period, category: dict | None, merchant: str | None) -> str:
    subject = f" on {category['name']}" if category else (f" at {merchant.title()}" if merchant else "")
    if not result["count"]:
        return f"You haven't spent anything{subject} {period.label}."
    payments = f"{result['count']} payment{'s' if result['count'] != 1 else ''}"
    return f"You spent {money(result['total'])}{subject} {period.label} ({payments})."


def breakdown_reply(rows: list[tuple[str, float, float]], period: Period) -> str:
    if not rows:
        return f"You haven't spent anything {period.label}."
    top = [f"{name} {money(amount)} ({share:.0%})" for name, amount, share in rows[:3]]
    return f"Your biggest categories {period.label}: {_join(top)}."


def budget_reply(insights) -> str:
    forecast = insights.forecast
    if forecast is None:
        return "I need about four weeks of transactions before I can forecast your month."
    reply = (f"At this pace you'll spend about {money(forecast.projected_total)} this month "
             f"(likely {money(forecast.low)} to {money(forecast.high)}).")
    if not forecast.budget:
        return reply + " Set a monthly budget in Settings and I'll track it for you."
    if forecast.status == "over":
        return (f"You've already spent {money(forecast.spent_to_date)}, over your {money(forecast.budget)} "
                "budget for this month.")
    chance = forecast.probability_over_budget or 0
    odds = ("very unlikely" if chance < 0.01 else "almost certain" if chance > 0.99
            else f"a {round(chance * 100)}% chance")
    verdict = "within" if forecast.status == "on_track" else "above"
    return reply + f" That's {verdict} your {money(forecast.budget)} budget: {odds} to go over."


def subscriptions_reply(insights) -> str:
    active = [p for p in insights.recurring if p.active]
    if not active:
        return ("I haven't found any subscriptions or regular bills yet. I need at least three payments "
                "on a steady rhythm to spot one.")
    listed = [
        f"{p.title} {money(p.amount)} ({p.period}, next {_short_date(p.next_date)})" for p in active[:4]
    ]
    if len(active) > 4:
        listed.append(f"{len(active) - 4} more")
    total = money(insights.recurring_monthly_total)
    count = f"{len(active)} subscription{'s' if len(active) != 1 else ''} and bills"
    return f"You have {count}, about {total} a month: {_join(listed)}."


def unusual_reply(insights) -> str:
    if not insights.unusual:
        return "Nothing unusual in the last 60 days."
    listed = [
        f"{u.title} {money(u.amount)} on {_short_date(u.date)}, {u.ratio:g} times your usual top payment "
        + ("there" if u.compared_with == "merchant" else f"in {u.category_name or 'that category'}")
        for u in insights.unusual[:3]
    ]
    count = len(insights.unusual)
    return f"{count} unusual payment{'s' if count != 1 else ''} in the last 60 days: {_join(listed)}."


def greeting_reply(text: str) -> str:
    if text.lower().startswith(("thank", "thx")):
        return "You're welcome!"
    return ("Hi! Ask me how much you spent on something, whether you're on track with your budget, "
            "what subscriptions you have, or how to do something in the app. You can also say "
            "\"add 450 swiggy yesterday\".")


CAPABILITIES = (
    "I can tell you how much you spent (\"how much on food last month?\", \"swiggy this week\"), where your "
    "money went, whether you're on track with your budget, your subscriptions and bills, and any unusual "
    "payments. I can add a transaction (\"add 450 swiggy yesterday\") and explain how to use the app, "
    "such as scanning a bill, exporting or managing categories."
)


def about_reply(text: str) -> str:
    """Answers about the assistant itself and small talk; anything else unrelated is declined politely."""
    t = " ".join(text.lower().split())
    if re.search(r"\b(made|created|built|developed|designed|trained|wrote|creator|developer|maker|owner)\b"
                 r"|\bbehind\b", t):
        return ("I'm the Expense Tracker assistant, built by Ketul Mehta as part of this app. I run on the "
                "app's own server with open-source models, so your data isn't sent to an outside AI service.")
    if re.search(r"\b(name|who are|who r|what are you|bot|robot|human|ai|real|person)\b"
                 r"|\b(chatgpt|gpt|gemini|claude)\b", t):
        return ("I'm the Expense Tracker assistant, a helper for your money in this app. " + CAPABILITIES)
    if re.search(r"\bhow are (you|u)\b|\bkaise ho\b|\bwhat'?s up\b", t):
        return "I'm doing well, thanks! What would you like to know about your money?"
    if re.search(r"\b(what|how) (can|do) (you|u) (do|help)\b|\bwhat can i ask\b|^help( me)?$", t):
        return CAPABILITIES
    if re.search(r"\bmutual funds?\b|\bstocks?\b|\bshares?\b|\bcrypto|\bbitcoin\b|\binvest", t):
        return ("I can't recommend investments; for that, talk to a registered financial adviser. "
                "I can show you how much you spend and save each month, which helps you plan what to invest.")
    return "That's outside what I can help with. " + CAPABILITIES
