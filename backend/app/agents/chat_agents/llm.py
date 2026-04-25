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
