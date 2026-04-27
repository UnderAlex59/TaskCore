from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderKind = Literal["openai", "ollama", "openrouter", "gigachat", "openai_compatible"]
PromptLogMode = Literal["disabled", "metadata_only", "full"]
VisionSystemPromptMode = Literal["system_role", "inline_user"]
VisionMessageOrder = Literal["text_first", "image_first"]
VisionDetail = Literal["default", "auto", "low", "high"]


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
    vision_enabled: bool = True
    vision_system_prompt_mode: VisionSystemPromptMode = "system_role"
    vision_message_order: VisionMessageOrder = "text_first"
    vision_detail: VisionDetail = "default"


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
    vision_enabled: bool | None = None
    vision_system_prompt_mode: VisionSystemPromptMode | None = None
    vision_message_order: VisionMessageOrder | None = None
    vision_detail: VisionDetail | None = None


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
    vision_enabled: bool
    vision_system_prompt_mode: VisionSystemPromptMode
    vision_message_order: VisionMessageOrder
    vision_detail: VisionDetail
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


class VisionTestResult(BaseModel):
    ok: bool
    provider_config_id: str | None
    provider_kind: str
    provider_name: str | None
    model: str
    latency_ms: int | None
    content_type: str
    prompt: str
    result_text: str | None
    message: str


class RuntimeDefaultProviderUpdate(BaseModel):
    provider_config_id: str


class RuntimeSettingsRead(BaseModel):
    prompt_log_mode: PromptLogMode


class RuntimeSettingsUpdate(BaseModel):
    prompt_log_mode: PromptLogMode


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
    prompt_log_mode: PromptLogMode
    providers: list[ProviderConfigRead]
    overrides: list[AgentOverrideRead]


class AgentDirectoryRead(BaseModel):
    key: str
    name: str
    description: str
    aliases: list[str]

    model_config = ConfigDict(from_attributes=True)


class AgentPromptConfigRead(BaseModel):
    prompt_key: str
    agent_key: str
    name: str
    aliases: list[str]
    default_description: str
    default_system_prompt: str
    effective_description: str
    effective_system_prompt: str
    override_description: str | None
    override_system_prompt: str | None
    override_enabled: bool
    revision: int | None
    updated_at: datetime | None


class AgentPromptUpdate(BaseModel):
    description: str = Field(min_length=3, max_length=4096)
    system_prompt: str = Field(min_length=20, max_length=20000)
    enabled: bool = True


class AgentPromptVersionRead(BaseModel):
    id: str
    prompt_key: str
    agent_key: str
    description: str
    system_prompt: str
    enabled: bool
    revision: int
    created_at: datetime


class AgentPromptRestorePayload(BaseModel):
    version_id: str
