"""LLM factory for the agent runtime."""

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from app.core.config import settings


def get_llm(model: str | None = None, temperature: float | None = None) -> ChatAnthropic:
    """Return a chat model configured from env (``LLM_MODEL``, ``LLM_TEMPERATURE``)."""
    model_name = model or settings.llm_model
    if not model_name:
        raise RuntimeError("LLM_MODEL is not set; provide it via env or .env")
    kwargs: dict = {
        "model": model_name,
        "temperature": settings.llm_temperature if temperature is None else temperature,
    }
    if settings.anthropic_api_key:
        kwargs["anthropic_api_key"] = SecretStr(settings.anthropic_api_key)
    return ChatAnthropic(**kwargs)
