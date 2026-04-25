from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None

    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    CHAT_AGENT_MODULES: list[str] = Field(default_factory=list)

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_PROVIDER: Literal["openai", "ollama"] | None = None
    EMBEDDING_MODEL: str | None = None
    OLLAMA_EMBEDDING_MODEL: str | None = None
    EMBEDDING_DIMENSION: int | None = None
    LLM_SETTINGS_ENCRYPTION_KEY: str | None = None

    RAG_CHUNK_TARGET_TOKENS: int = 450
    RAG_CHUNK_OVERLAP_TOKENS: int = 50
    RAG_ATTACHMENT_MAX_TEXT_CHARS: int = 20000
    RAG_VISION_ENABLED: bool = True
    RAG_VISION_MAX_IMAGE_BYTES: int = 5242880

    UPLOAD_DIR: str = "/tmp/uploads"
    LANGGRAPH_IMAGES_DIR: str = str(PROJECT_ROOT / "langgraph_graphs")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "COOKIE_DOMAIN",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_MODEL",
        "OLLAMA_EMBEDDING_MODEL",
        "LLM_SETTINGS_ENCRYPTION_KEY",
        mode="before",
    )
    @classmethod
    def empty_optional_setting_to_none(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        return value

    @field_validator("ALLOWED_ORIGINS", "CHAT_AGENT_MODULES", mode="before")
    @classmethod
    def parse_list_settings(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return value

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
