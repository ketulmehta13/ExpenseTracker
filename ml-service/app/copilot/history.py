"""Conversation history in Supabase (chat_threads, chat_messages), read and written as the user.

Row level security keeps each user's conversations private, and deleting the account deletes
them. History is a convenience, not a dependency: if the tables are missing (the migration
hasn't been applied) or Supabase fails, the copilot still answers and reports history_saved=false.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.supabase import SupabaseData

logger = logging.getLogger("ml_service.copilot")

CONTEXT_MESSAGES = 6  # recent messages read for follow-ups


class HistoryUnavailable(RuntimeError):
    pass


class ThreadNotFound(LookupError):
    pass


def _ok(response, what: str):
    if response.status_code >= 400:
        raise HistoryUnavailable(f"{what}: {response.status_code}")
    return response


def _title(message: str) -> str:
    title = " ".join(message.split())
    return (title[:57] + "...") if len(title) > 60 else title or "New conversation"


async def open_thread(data: SupabaseData, thread_id: UUID | None, first_message: str) -> UUID:
    """The given thread if the user owns it (RLS hides others'), or a new one."""
    if thread_id is not None:
        rows = _ok(
            await data.request("GET", "chat_threads", params={"select": "id", "id": f"eq.{thread_id}"}),
            "read thread",
        ).json()
        if not rows:
            raise ThreadNotFound(str(thread_id))
        return thread_id
    rows = _ok(
        await data.request(
            "POST", "chat_threads", json={"title": _title(first_message)}, prefer="return=representation"
        ),
        "create thread",
    ).json()
    return UUID(rows[0]["id"])


async def recent_messages(data: SupabaseData, thread_id: UUID, limit: int = CONTEXT_MESSAGES) -> list[dict]:
    rows = _ok(
        await data.request(
            "GET",
            "chat_messages",
            params={
                "select": "role,content,blocks,created_at",
                "thread_id": f"eq.{thread_id}",
                "order": "created_at.desc,id.desc",
                "limit": str(limit),
            },
        ),
        "read messages",
    ).json()
    return list(reversed(rows))


async def append(data: SupabaseData, thread_id: UUID, role: str, content: str, blocks: list[dict]) -> None:
    _ok(
        await data.request(
            "POST",
            "chat_messages",
            json={"thread_id": str(thread_id), "role": role, "content": content[:8000], "blocks": blocks},
            prefer="return=minimal",
        ),
        "save message",
    )
    await data.request(
        "PATCH",
        "chat_threads",
        params={"id": f"eq.{thread_id}"},
        json={"updated_at": "now"},
        prefer="return=minimal",
    )


async def list_threads(data: SupabaseData, limit: int = 30) -> list[dict]:
    return _ok(
        await data.request(
            "GET",
            "chat_threads",
            params={"select": "id,title,updated_at", "order": "updated_at.desc", "limit": str(limit)},
        ),
        "list threads",
    ).json()


async def thread_messages(data: SupabaseData, thread_id: UUID, limit: int = 100) -> list[dict]:
    await open_thread(data, thread_id, "")
    return _ok(
        await data.request(
            "GET",
            "chat_messages",
            params={
                "select": "role,content,blocks,created_at",
                "thread_id": f"eq.{thread_id}",
                "order": "created_at.asc,id.asc",
                "limit": str(limit),
            },
        ),
        "read messages",
    ).json()


async def delete_thread(data: SupabaseData, thread_id: UUID) -> None:
    await open_thread(data, thread_id, "")
    _ok(await data.request("DELETE", "chat_threads", params={"id": f"eq.{thread_id}"}), "delete thread")
