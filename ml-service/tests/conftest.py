from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SUPABASE_URL = "https://test-project.supabase.co"
VALID_TOKEN = "valid-token"
TEST_USER = {"id": "11111111-1111-1111-1111-111111111111", "email": "test@example.com"}


class FakeSupabase:
    """Stands in for Supabase Auth and PostgREST behind an httpx MockTransport."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.max_rows = 1000  # PostgREST's per-response cap
        self.auth_calls = 0
        self.auth_down = False
        self.last_params: dict[str, str] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/auth/v1/user":
            self.auth_calls += 1
            if self.auth_down:
                raise httpx.ConnectError("auth unreachable", request=request)
            if request.headers.get("authorization") == f"Bearer {VALID_TOKEN}":
                return httpx.Response(200, json=TEST_USER)
            return httpx.Response(401, json={"msg": "invalid JWT"})

        if path.startswith("/rest/v1/"):
            if request.headers.get("authorization") != f"Bearer {VALID_TOKEN}":
                return httpx.Response(401, json={"message": "JWT invalid"})
            self.last_params = dict(request.url.params)
            rows = self.tables.get(path.removeprefix("/rest/v1/"), [])
            start, end = (int(n) for n in request.headers.get("range", f"0-{len(rows) - 1}").split("-"))
            end = min(end, start + self.max_rows - 1)
            page = rows[start : end + 1]
            total = str(len(rows)) if "count=exact" in request.headers.get("prefer", "") else "*"
            content_range = f"{start}-{start + len(page) - 1}/{total}" if page else f"*/{total}"
            return httpx.Response(200, json=page, headers={"Content-Range": content_range})

        return httpx.Response(404)


@pytest.fixture
def supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def settings() -> Settings:
    return Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key")


@pytest.fixture
def client(supabase, settings):
    app = create_app(settings, transport=httpx.MockTransport(supabase.handler))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN}"}
