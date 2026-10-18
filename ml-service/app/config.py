"""Service configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ORIGINS = "http://localhost:5173,https://ketul-expense-tracker.vercel.app"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    # The public (anon/publishable) key: identifies the project, grants nothing by itself
    supabase_anon_key: str = ""
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: _csv(DEFAULT_ORIGINS))
    model_dir: Path = DEFAULT_MODEL_DIR
    # A validated token is trusted for this long, so a burst of requests costs one auth round trip
    auth_cache_seconds: int = 60

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
            supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
            allowed_origins=_csv(os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS)),
            model_dir=Path(os.environ.get("MODEL_DIR", str(DEFAULT_MODEL_DIR))),
            auth_cache_seconds=int(os.environ.get("AUTH_CACHE_SECONDS", "60")),
        )
