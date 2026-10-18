"""One switch for the chat model: a local Ollama model, any OpenAI-compatible endpoint, or none.

LangChain's chat-model interface hides the provider, so the rest of the service never imports
a vendor SDK and a different model is a configuration change. Free options:
- Ollama on your own machine (e.g. `ollama pull qwen2.5:3b`), with LLM_PROVIDER=ollama;
- a free hosted tier that speaks the OpenAI API (Groq, OpenRouter, Gemini), with
  LLM_PROVIDER=openai plus LLM_BASE_URL and LLM_API_KEY.

With LLM_PROVIDER=none every LLM feature falls back to rules or templates. Tests pass a fake.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.config import Settings

OLLAMA_URL = "http://localhost:11434"


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.llm_base_url or OLLAMA_URL,
            temperature=0,  # extraction and phrasing should be repeatable, not creative
            client_kwargs={"timeout": settings.llm_timeout_seconds},
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            base_url=settings.llm_base_url or None,
            api_key=settings.llm_api_key or None,
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
    if provider not in {"", "none"}:
        raise ValueError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}: use none, ollama or openai")
    return None
