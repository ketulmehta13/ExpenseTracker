"""Authenticate requests with the caller's Supabase access token.

Tokens are checked by Supabase Auth itself (GET /auth/v1/user). That works for every
JWT signing method the project may use (legacy shared secret or asymmetric keys),
at the cost of a network round trip, so validated tokens are cached briefly.
The alternative, verifying signatures locally against the project's JWKS, avoids the
round trip but cannot notice a session that was revoked before the token expires.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings

bearer_scheme = HTTPBearer(auto_error=False)
MAX_CACHED_TOKENS = 10_000


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    # Forwarded to Supabase so row level security applies to every read
    token: str


class TokenCache:
    """Remembers validated tokens (keyed by hash, never stored raw) for `ttl_seconds`."""

    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, CurrentUser]] = {}

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def get(self, token: str) -> CurrentUser | None:
        entry = self._entries.get(self._key(token))
        if entry is None or entry[0] < time.monotonic():
            return None
        return entry[1]

    def put(self, user: CurrentUser) -> None:
        if len(self._entries) >= MAX_CACHED_TOKENS:
            self._entries.clear()
        self._entries[self._key(user.token)] = (time.monotonic() + self.ttl_seconds, user)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def verify_token(token: str, http: httpx.AsyncClient, settings: Settings) -> CurrentUser:
    try:
        response = await http.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_anon_key},
        )
    except httpx.HTTPError as err:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication service unavailable"
        ) from err
    if response.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    data = response.json()
    return CurrentUser(id=data["id"], email=data.get("email"), token=token)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    cache: TokenCache = request.app.state.token_cache
    user = cache.get(credentials.credentials)
    if user is None:
        user = await verify_token(credentials.credentials, request.app.state.http, settings)
        cache.put(user)
    return user
