import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.supabase import SupabaseData, _total_from_content_range
from tests.conftest import SUPABASE_URL, VALID_TOKEN, FakeSupabase


def read(fake: FakeSupabase, table: str, token: str = VALID_TOKEN, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            return await SupabaseData(http, SUPABASE_URL, "anon-key", token).select(table, **kwargs)

    return asyncio.run(run())


@pytest.fixture
def fake():
    fake = FakeSupabase()
    fake.tables["transactions"] = [{"id": i} for i in range(2345)]
    return fake


def test_reads_every_row_across_pages(fake):
    rows = read(fake, "transactions")
    assert len({row["id"] for row in rows}) == 2345


def test_still_complete_when_the_server_cap_is_below_the_page_size(fake):
    fake.max_rows = 300
    rows = read(fake, "transactions")
    assert len({row["id"] for row in rows}) == 2345


def test_respects_the_limit(fake):
    assert len(read(fake, "transactions", limit=50)) == 50


def test_forwards_query_params(fake):
    read(fake, "transactions", params={"select": "id,amount", "order": "date.desc,id.desc"})
    assert fake.last_params == {"select": "id,amount", "order": "date.desc,id.desc"}


def test_empty_table(fake):
    assert read(fake, "categories") == []


def test_rejected_token_becomes_a_502(fake):
    with pytest.raises(HTTPException) as err:
        read(fake, "transactions", token="someone-else")
    assert err.value.status_code == 502


@pytest.mark.parametrize(
    ("header", "expected"),
    [("0-999/2345", 2345), ("*/0", 0), ("0-999/*", None), (None, None)],
)
def test_content_range_parsing(header, expected):
    assert _total_from_content_range(header) == expected
