from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import get_settings

LLMProvider = Literal["openai", "ollama", "openrouter", "gigachat", "openai_compatible"]


@dataclass(frozen=True, slots=True)
class ChatAgentLLMProfile:
    provider: LLMProvider
    model: str
    temperature: float = 0.2
    api_key: str | None = None
    base_url: str | None = None


def _normalize_provider(value: str) -> LLMProvider:
    normalized = value.casefold()
    if normalized == "openai":
        return "openai"
    if normalized == "ollama":
        return "ollama"
    if normalized == "openrouter":
        return "openrouter"
    if normalized == "gigachat":
        return "gigachat"
    if normalized == "openai_compatible":
        return "openai_compatible"
    raise ValueError(f"Неподдерживаемый LLM-провайдер: '{value}'")


def _provider_defaults(provider: LLMProvider) -> ChatAgentLLMProfile:
    settings = get_settings()
    if provider in {"openai", "openrouter", "gigachat", "openai_compatible"}:
        return ChatAgentLLMProfile(
            provider=provider,
            model=settings.OPENAI_MODEL or settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

    return ChatAgentLLMProfile(
        provider="ollama",
        model=settings.OLLAMA_MODEL or settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        api_key=None,
        base_url=settings.OLLAMA_BASE_URL,
    )


def get_default_llm_profile() -> ChatAgentLLMProfile:
    settings = get_settings()
    return _provider_defaults(_normalize_provider(settings.LLM_PROVIDER))


def resolve_agent_llm_profile(
    agent_key: str,
    default_profile: ChatAgentLLMProfile | None = None,
) -> ChatAgentLLMProfile:
    settings = get_settings()
    profile = default_profile or get_default_llm_profile()
    override = settings.CHAT_AGENT_LLM_OVERRIDES.get(agent_key)
    if override is None:
        return profile

    provider = (
        _normalize_provider(override.provider)
        if override.provider is not None
        else profile.provider
    )
    provider_profile = _provider_defaults(provider)
    active_profile = provider_profile if provider != profile.provider else profile

    return ChatAgentLLMProfile(
        provider=provider,
        model=override.model or active_profile.model,
        temperature=(
            override.temperature
            if override.temperature is not None
            else profile.temperature
        ),
        api_key=(
            override.api_key
            if override.api_key is not None
            else active_profile.api_key or provider_profile.api_key
        ),
        base_url=(
            override.base_url
            if override.base_url is not None
            else active_profile.base_url or provider_profile.base_url
        ),
    )


def build_chat_model(profile: ChatAgentLLMProfile) -> BaseChatModel:
    if profile.provider in {"openai", "openrouter", "gigachat", "openai_compatible"}:
        if not profile.api_key:
            raise ValueError("Для выбранного провайдера требуется API-ключ или токен доступа")
        return ChatOpenAI(
            model=profile.model,
            api_key=SecretStr(profile.api_key),
            base_url=profile.base_url,
            temperature=profile.temperature,
        )

    return ChatOllama(
        model=profile.model,
        base_url=profile.base_url or get_settings().OLLAMA_BASE_URL,
        temperature=profile.temperature,
    )
