from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderKind = Literal["openai", "ollama", "openrouter", "gigachat", "openai_compatible"]


class ProviderConfigPayload(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    provider_kind: ProviderKind
    base_url: str | None = Field(default=None, max_length=512)
    model: str = Field(min_length=1, max_length=255)
    temperature: float = Field(default=0.2, ge=0, le=2)
    enabled: bool = True
    input_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    output_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)


class ProviderConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    provider_kind: ProviderKind | None = None
    base_url: str | None = Field(default=None, max_length=512)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    temperature: float | None = Field(default=None, ge=0, le=2)
    enabled: bool | None = None
    input_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    output_cost_per_1k_tokens: Decimal | None = Field(default=None, ge=0)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)


class ProviderConfigRead(BaseModel):
    id: str
    name: str
    provider_kind: ProviderKind
    base_url: str
    model: str
    temperature: float
    enabled: bool
    input_cost_per_1k_tokens: Decimal | None
    output_cost_per_1k_tokens: Decimal | None
    secret_configured: bool
    masked_secret: str | None
    is_default: bool
    used_by_agents: list[str]
    created_at: datetime
    updated_at: datetime


class ProviderTestResult(BaseModel):
    ok: bool
    provider_kind: ProviderKind
    model: str
    latency_ms: int | None
    message: str


class RuntimeDefaultProviderUpdate(BaseModel):
    provider_config_id: str


class AgentOverrideUpdate(BaseModel):
    provider_config_id: str
    enabled: bool = True


class AgentOverrideRead(BaseModel):
    agent_key: str
    provider_config_id: str
    provider_name: str
    provider_kind: ProviderKind
    model: str
    enabled: bool


class RuntimeOverviewRead(BaseModel):
    default_provider_config_id: str | None
    prompt_log_mode: str
    providers: list[ProviderConfigRead]
    overrides: list[AgentOverrideRead]


class AgentDirectoryRead(BaseModel):
    key: str
    name: str
    description: str
    aliases: list[str]

    model_config = ConfigDict(from_attributes=True)
