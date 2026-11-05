"""Saved conversations in Supabase (chat_threads, chat_messages), read and written with the
user's own token, so row level security keeps them private. History is a convenience: if the
tables are missing or Supabase fails, the chatbot still answers and reports history_saved=false.
"""

from __future__ import annotations

from uuid import UUID

import httpx

from app.supabase import SupabaseData

RECENT_MESSAGES = 6


class HistoryUnavailable(RuntimeError):
    pass


class ThreadNotFound(LookupError):
    pass


async def _call(data: SupabaseData, method: str, table: str, **kwargs):
    try:
        response = await data.request(method, table, **kwargs)
    except httpx.HTTPError as err:
        raise HistoryUnavailable(type(err).__name__) from err
    if response.status_code >= 400:
        raise HistoryUnavailable(f"{table}: {response.status_code}")
    return response


async def open_thread(data: SupabaseData, thread_id: UUID | None, first_message: str) -> UUID:
    """The given thread if this user owns it (RLS hides other users' threads), or a new one."""
    if thread_id is not None:
        params = {"select": "id", "id": f"eq.{thread_id}"}
        if not (await _call(data, "GET", "chat_threads", params=params)).json():
            raise ThreadNotFound(str(thread_id))
        return thread_id
    title = " ".join(first_message.split())
    title = f"{title[:57]}..." if len(title) > 60 else title
    response = await _call(
        data, "POST", "chat_threads", json={"title": title}, prefer="return=representation"
    )
    return UUID(response.json()[0]["id"])


async def recent_messages(data: SupabaseData, thread_id: UUID, limit: int = RECENT_MESSAGES) -> list[dict]:
    params = {
        "select": "role,content",
        "thread_id": f"eq.{thread_id}",
        "order": "created_at.desc,id.desc",
        "limit": str(limit),
    }
    return list(reversed((await _call(data, "GET", "chat_messages", params=params)).json()))


async def save_turn(
    data: SupabaseData, thread_id: UUID, question: str, answer: str, blocks: list[dict], user_id: str
) -> int | None:
    """Saves both messages and returns the answer's id, which feedback refers to."""
    rows = [
        {"thread_id": str(thread_id), "user_id": user_id, "role": "user", "content": question, "blocks": []},
        {
            "thread_id": str(thread_id),
            "user_id": user_id,
            "role": "assistant",
            "content": answer[:8000],
            "blocks": blocks,
        },
    ]
    saved = await _call(data, "POST", "chat_messages", json=rows, prefer="return=representation")
    params = {"id": f"eq.{thread_id}"}
    await _call(
        data, "PATCH", "chat_threads", params=params, json={"updated_at": "now"}, prefer="return=minimal"
    )
    return next((row.get("id") for row in saved.json() if row.get("role") == "assistant"), None)


async def list_threads(data: SupabaseData, limit: int = 30) -> list[dict]:
    params = {"select": "id,title,updated_at", "order": "updated_at.desc", "limit": str(limit)}
    return (await _call(data, "GET", "chat_threads", params=params)).json()


async def thread_messages(data: SupabaseData, thread_id: UUID, limit: int = 100) -> list[dict]:
    await open_thread(data, thread_id, "")
    params = {
        "select": "id,role,content,blocks,created_at",
        "thread_id": f"eq.{thread_id}",
        "order": "created_at.asc,id.asc",
        "limit": str(limit),
    }
    return (await _call(data, "GET", "chat_messages", params=params)).json()


async def delete_thread(data: SupabaseData, thread_id: UUID) -> None:
    await open_thread(data, thread_id, "")
    await _call(data, "DELETE", "chat_threads", params={"id": f"eq.{thread_id}"})


async def save_feedback(data: SupabaseData, message_id: int, rating: str, user_id: str) -> None:
    """A thumbs up or down on one of the user's own answers; a later one replaces the earlier one."""
    await _call(
        data,
        "POST",
        "chat_feedback",
        params={"on_conflict": "user_id,message_id"},
        json={"message_id": message_id, "rating": rating, "user_id": user_id},
        prefer="resolution=merge-duplicates,return=minimal",
    )
