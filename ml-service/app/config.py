"""Service configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ORIGINS = "http://localhost:5173,https://ketul-expense-tracker.vercel.app"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
SECRET_FILES_DIR = Path("/etc/secrets")  # where Render mounts "secret files"


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _model_name(value: str) -> str:
    """A model name, or "" when switched off with "none" or "off" (an explicit value, because
    some hosts drop environment variables whose value is empty)."""
    value = value.strip()
    return "" if value.lower() in {"", "none", "off"} else value


def _secret(name: str, secrets_dir: Path = SECRET_FILES_DIR) -> str:
    """An environment variable, or else a secret file of the same name (Render, Docker secrets).
    A file may hold just the value or a NAME=value line."""
    if value := os.environ.get(name, "").strip():
        return value
    try:
        text = (secrets_dir / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return text.splitlines()[0].strip() if text else ""


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    # The public (anon/publishable) key: identifies the project, grants nothing by itself
    supabase_anon_key: str = ""
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: _csv(DEFAULT_ORIGINS))
    model_dir: Path = DEFAULT_MODEL_DIR
    # A validated token is trusted for this long, so a burst of requests costs one auth round trip
    auth_cache_seconds: int = 60
    # How long a user's history and categories are reused before being re-read from Supabase
    user_context_cache_seconds: int = 60
    # Optional LLM: "none", "ollama" (local) or "openai" (any OpenAI-compatible endpoint, e.g. a free tier)
    llm_provider: str = "none"
    llm_model: str = "qwen2.5:3b"
    llm_base_url: str = ""
    llm_api_key: str = field(default="", repr=False)  # never printed in logs or tracebacks
    llm_timeout_seconds: float = 20.0
    # Help-center search: articles, and the embedding model ("" = keyword search only, which
    # EMBEDDING_MODEL=none selects)
    knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: Path = DEFAULT_MODEL_DIR / "embeddings"
    # Monitoring: GET /metrics requires this bearer token when set
    metrics_token: str = field(default="", repr=False)
    log_level: str = "INFO"
    # Bill scanning: CPU threads for OCR (1 suits a small shared server)
    ocr_threads: int = 1
    # Financial Copilot: knowledge-base embeddings ("" = keyword search only) and per-user limits
    copilot_embedding_model: str = "Supabase/gte-small"
    copilot_per_minute: int = 20
    copilot_per_day: int = 300

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
            supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
            allowed_origins=_csv(os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS)),
            model_dir=Path(os.environ.get("MODEL_DIR", str(DEFAULT_MODEL_DIR))),
            auth_cache_seconds=int(os.environ.get("AUTH_CACHE_SECONDS", "60")),
            user_context_cache_seconds=int(os.environ.get("USER_CONTEXT_CACHE_SECONDS", "60")),
            llm_provider=os.environ.get("LLM_PROVIDER", "none"),
            llm_model=os.environ.get("LLM_MODEL", "qwen2.5:3b"),
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            llm_api_key=_secret("LLM_API_KEY"),
            llm_timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
            knowledge_dir=Path(os.environ.get("KNOWLEDGE_DIR", str(DEFAULT_KNOWLEDGE_DIR))),
            embedding_model=_model_name(os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")),
            embedding_cache_dir=Path(
                os.environ.get("EMBEDDING_CACHE_DIR", str(DEFAULT_MODEL_DIR / "embeddings"))
            ),
            metrics_token=os.environ.get("METRICS_TOKEN", ""),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            ocr_threads=int(os.environ.get("OCR_THREADS", "1")),
            copilot_embedding_model=_model_name(
                os.environ.get("COPILOT_EMBEDDING_MODEL", "Supabase/gte-small")
            ),
            copilot_per_minute=int(os.environ.get("COPILOT_PER_MINUTE", "20")),
            copilot_per_day=int(os.environ.get("COPILOT_PER_DAY", "300")),
        )
