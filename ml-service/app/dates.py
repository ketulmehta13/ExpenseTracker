"""The user's "today", which can differ from the server's."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import HTTPException, status


def resolve_today(requested: date | None) -> date:
    """The user's local date. Clients send it, because the server's UTC date can be a day off."""
    server_today = datetime.now(UTC).date()
    if requested is None:
        return server_today
    if abs((requested - server_today).days) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be within a day of the current date"
        )
    return requested
