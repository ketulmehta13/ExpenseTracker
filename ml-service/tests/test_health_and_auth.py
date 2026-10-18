import httpx
from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app
from tests.conftest import SUPABASE_URL, TEST_USER


def test_health_needs_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "models": {"categorizer": "test-model"},
        "llm": False,
    }


def test_missing_token_is_rejected(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_invalid_token_is_rejected(client):
    response = client.get("/v1/me", headers={"Authorization": "Bearer forged"})
    assert response.status_code == 401


def test_valid_token_returns_the_user(client, auth_headers):
    response = client.get("/v1/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == TEST_USER


def test_validated_tokens_are_cached(client, supabase, auth_headers):
    for _ in range(3):
        assert client.get("/v1/me", headers=auth_headers).status_code == 200
    assert supabase.auth_calls == 1


def test_expired_cache_entries_are_rechecked(supabase, auth_headers):
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon-key", auth_cache_seconds=0)
    app = create_app(settings, transport=httpx.MockTransport(supabase.handler))
    with TestClient(app) as client:
        client.get("/v1/me", headers=auth_headers)
        client.get("/v1/me", headers=auth_headers)
    assert supabase.auth_calls == 2


def test_auth_outage_is_a_503_not_a_crash(client, supabase, auth_headers):
    supabase.auth_down = True
    response = client.get("/v1/me", headers=auth_headers)
    assert response.status_code == 503


def test_cors_allows_the_frontend_origin(client):
    response = client.options(
        "/v1/me",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
