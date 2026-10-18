"""Read (and, after the user confirms, write) the signed-in user's rows through Supabase's
REST API (PostgREST).

Every request carries the user's own access token, so Postgres row level security
decides what is visible and writable: the service never holds the service-role key.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status

from app.auth import CurrentUser, get_current_user

# PostgREST caps each response at the project's "max rows" setting (1000 by default)
PAGE_SIZE = 1000


def _total_from_content_range(header: str | None) -> int | None:
    """Parse the total from a Content-Range header such as "0-999/2345" or "*/0"."""
    if not header or "/" not in header:
        return None
    total = header.rsplit("/", 1)[1]
    return int(total) if total.isdigit() else None


class SupabaseData:
    def __init__(self, http: httpx.AsyncClient, base_url: str, anon_key: str, token: str):
        self._http = http
        self._rest_url = f"{base_url}/rest/v1"
        self._headers = {"apikey": anon_key, "Authorization": f"Bearer {token}"}

    async def select(
        self,
        table: str,
        params: dict[str, str] | None = None,
        limit: int = 20_000,
    ) -> list[dict[str, Any]]:
        """Fetch up to `limit` rows, page by page.

        Pass an `order` that ends in a unique column (e.g. "date.desc,id.desc"), otherwise
        rows sharing a sort value can be skipped or repeated between pages.
        """
        rows: list[dict[str, Any]] = []
        total: int | None = None
        while len(rows) < limit and (total is None or len(rows) < total):
            start = len(rows)
            end = min(start + PAGE_SIZE, limit) - 1
            headers = {**self._headers, "Range-Unit": "items", "Range": f"{start}-{end}"}
            if total is None:
                headers["Prefer"] = "count=exact"
            response = await self._http.get(f"{self._rest_url}/{table}", params=params or {}, headers=headers)
            if response.status_code not in (200, 206):
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not read {table} from Supabase")
            if total is None:
                total = _total_from_content_range(response.headers.get("content-range"))
            page = response.json()
            if not page:
                break
            rows.extend(page)
        return rows[:limit]


    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        """Insert one row as the user (row level security applies) and return it as stored."""
        headers = {**self._headers, "Prefer": "return=representation"}
        response = await self._http.post(f"{self._rest_url}/{table}", json=row, headers=headers)
        if response.status_code not in (200, 201):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not save to {table}")
        stored = response.json()
        return stored[0] if isinstance(stored, list) else stored


def get_data(request: Request, user: CurrentUser = Depends(get_current_user)) -> SupabaseData:
    settings = request.app.state.settings
    return SupabaseData(request.app.state.http, settings.supabase_url, settings.supabase_anon_key, user.token)
