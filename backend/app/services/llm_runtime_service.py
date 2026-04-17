from __future__ import annotations

import asyncio
import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any

import httpx
from cryptography.fernet import Fernet
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_agents.llm import (
    ChatAgentLLMProfile,
    build_chat_model,
    get_default_llm_profile,
    resolve_agent_llm_profile,
)
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.llm_agent_override import LLMAgentOverride
from app.models.llm_provider_config import LLMProviderConfig
from app.models.llm_request_log import LLMRequestLog
from app.models.llm_runtime_settings import LLMRuntimeSettings

DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434",
    "openrouter": "https://openrouter.ai/api/v1",
    "gigachat": "https://gigachat.devices.sberbank.ru/api/v1",
}
GIGACHAT_TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"


@dataclass(slots=True)
class ResolvedLLMProvider:
    config: LLMProviderConfig
    profile: ChatAgentLLMProfile


@dataclass(slots=True)
class LLMInvocationResult:
    ok: bool
    text: str | None
    provider_config_id: str | None
    provider_kind: str
    model: str
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: Decimal | None
    error_message: str | None = None


class LLMRuntimeService:
    _bootstrap_lock = asyncio.Lock()
    _gigachat_lock = asyncio.Lock()
    _gigachat_token_cache: dict[str, tuple[str, datetime]] = {}

    @staticmethod
    def normalize_base_url(provider_kind: str, base_url: str | None) -> str:
        normalized = provider_kind.casefold()
        if base_url:
            return base_url.rstrip("/")
        if normalized == "openai_compatible":
            raise ValueError("Для провайдера openai_compatible необходимо указать base_url")
        return DEFAULT_BASE_URLS.get(normalized, DEFAULT_BASE_URLS["openai"])

    @staticmethod
    def _fernet() -> Fernet:
        settings = get_settings()
        secret_seed = settings.LLM_SETTINGS_ENCRYPTION_KEY or settings.JWT_SECRET_KEY
        digest = hashlib.sha256(secret_seed.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @classmethod
    def mask_secret(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}********{value[-4:]}"

    @classmethod
    def encrypt_secret(cls, value: str | None) -> tuple[str | None, str | None]:
        if value is None or value == "":
            return None, None
        token = cls._fernet().encrypt(value.encode("utf-8")).decode("utf-8")
        return token, cls.mask_secret(value)

    @classmethod
    def decrypt_secret(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return cls._fernet().decrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    async def ensure_bootstrap(cls) -> None:
        async with cls._bootstrap_lock:
            async with AsyncSessionLocal() as db:
                provider_count = await db.scalar(select(func.count()).select_from(LLMProviderConfig))
                runtime_settings = await db.get(LLMRuntimeSettings, 1)
                if provider_count and runtime_settings is not None:
                    return

                if not provider_count:
                    await cls._bootstrap_provider_data(db)
                    provider_count = await db.scalar(select(func.count()).select_from(LLMProviderConfig))
                    runtime_settings = await db.get(LLMRuntimeSettings, 1)

                if runtime_settings is None:
                    default_provider_id = await db.scalar(
                        select(LLMProviderConfig.id)
                        .where(LLMProviderConfig.enabled.is_(True))
                        .order_by(LLMProviderConfig.created_at.asc())
                        .limit(1)
                    )
                    db.add(
                        LLMRuntimeSettings(
                            id=1,
                            default_provider_config_id=default_provider_id,
                            prompt_log_mode="metadata_only",
                        )
                    )

                await db.commit()

    @classmethod
    async def _bootstrap_provider_data(cls, db: AsyncSession) -> None:
        from app.agents.chat_agents.registry import get_chat_agents, reset_chat_agent_registry

        settings = get_settings()
        default_profile = get_default_llm_profile()
        default_provider = await cls._create_provider_config(
            db,
            name="Автоматически созданный профиль по умолчанию",
            provider_kind=default_profile.provider,
            base_url=default_profile.base_url,
            model=default_profile.model,
            temperature=default_profile.temperature,
            enabled=True,
            secret=default_profile.api_key,
            created_by=None,
        )
        db.add(
            LLMRuntimeSettings(
                id=1,
                default_provider_config_id=default_provider.id,
                prompt_log_mode="metadata_only",
            )
        )

        reset_chat_agent_registry()
        default_signature = cls._profile_signature(default_profile)
        for agent in get_chat_agents():
            if agent.llm_profile is None:
                continue
            effective_profile = resolve_agent_llm_profile(agent.metadata.key, agent.llm_profile)
            if cls._profile_signature(effective_profile) == default_signature:
                continue
            provider = await cls._create_provider_config(
                db,
                name=f"Автоматически созданный профиль для агента {agent.metadata.key}",
                provider_kind=effective_profile.provider,
                base_url=effective_profile.base_url,
                model=effective_profile.model,
                temperature=effective_profile.temperature,
                enabled=True,
                secret=effective_profile.api_key,
                created_by=None,
            )
            db.add(
                LLMAgentOverride(
                    agent_key=agent.metadata.key,
                    provider_config_id=provider.id,
                    enabled=True,
                )
            )

        # Preserve env overrides that target agents without a static llm_profile.
        for agent_key, override in settings.CHAT_AGENT_LLM_OVERRIDES.items():
            if override.provider is None and override.model is None and override.base_url is None:
                continue
            existing = await db.get(LLMAgentOverride, agent_key)
            if existing is not None:
                continue
            effective_profile = resolve_agent_llm_profile(agent_key, default_profile)
            if cls._profile_signature(effective_profile) == default_signature:
                continue
            provider = await cls._create_provider_config(
                db,
                name=f"Автоматически созданный профиль из переменных окружения для {agent_key}",
                provider_kind=effective_profile.provider,
                base_url=effective_profile.base_url,
                model=effective_profile.model,
                temperature=effective_profile.temperature,
                enabled=True,
                secret=effective_profile.api_key,
                created_by=None,
            )
            db.add(
                LLMAgentOverride(
                    agent_key=agent_key,
                    provider_config_id=provider.id,
                    enabled=True,
                )
            )

    @classmethod
    async def _create_provider_config(
        cls,
        db: AsyncSession,
        *,
        name: str,
        provider_kind: str,
        base_url: str | None,
        model: str,
        temperature: float,
        enabled: bool,
        secret: str | None,
        created_by: str | None,
    ) -> LLMProviderConfig:
        encrypted_secret, masked_secret = cls.encrypt_secret(secret)
        provider = LLMProviderConfig(
            name=name,
            provider_kind=provider_kind,
            base_url=cls.normalize_base_url(provider_kind, base_url),
            model=model,
            temperature=Decimal(str(temperature)),
            enabled=enabled,
            encrypted_secret=encrypted_secret,
            masked_secret=masked_secret,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(provider)
        await db.flush()
        return provider

    @staticmethod
    def _profile_signature(profile: ChatAgentLLMProfile) -> tuple[Any, ...]:
        return (
            profile.provider,
            profile.model,
            profile.temperature,
            profile.base_url or "",
            profile.api_key or "",
        )

    @classmethod
    async def resolve_provider(cls, db: AsyncSession, *, agent_key: str | None) -> ResolvedLLMProvider:
        await cls.ensure_bootstrap()

        selected: LLMProviderConfig | None = None
        if agent_key:
            override_stmt = (
                select(LLMAgentOverride, LLMProviderConfig)
                .join(LLMProviderConfig, LLMProviderConfig.id == LLMAgentOverride.provider_config_id)
                .where(
                    LLMAgentOverride.agent_key == agent_key,
                    LLMAgentOverride.enabled.is_(True),
                    LLMProviderConfig.enabled.is_(True),
                )
            )
            override_row = (await db.execute(override_stmt)).first()
            if override_row is not None:
                _, selected = override_row

        if selected is None:
            runtime_settings = await db.get(LLMRuntimeSettings, 1)
            if runtime_settings is not None and runtime_settings.default_provider_config_id is not None:
                selected = await db.get(LLMProviderConfig, runtime_settings.default_provider_config_id)
                if selected is not None and not selected.enabled:
                    selected = None

        if selected is None:
            fallback_stmt = (
                select(LLMProviderConfig)
                .where(LLMProviderConfig.enabled.is_(True))
                .order_by(LLMProviderConfig.created_at.asc())
                .limit(1)
            )
            selected = (await db.execute(fallback_stmt)).scalar_one_or_none()

        if selected is None:
            raise RuntimeError("Нет доступной включённой конфигурации LLM-провайдера")

        profile = await cls._build_profile(selected)
        return ResolvedLLMProvider(config=selected, profile=profile)

    @classmethod
    async def _build_profile(cls, config: LLMProviderConfig) -> ChatAgentLLMProfile:
        provider_kind = config.provider_kind
        api_key: str | None = None
        if provider_kind != "ollama":
            secret = cls.decrypt_secret(config.encrypted_secret)
            if provider_kind == "gigachat":
                if not secret:
                    raise ValueError("Для GigaChat не настроен ключ авторизации")
                api_key = await cls._get_gigachat_access_token(config.id, secret)
            else:
                api_key = secret

        return ChatAgentLLMProfile(
            provider=provider_kind,  # type: ignore[arg-type]
            model=config.model,
            temperature=float(config.temperature),
            api_key=api_key,
            base_url=config.base_url,
        )

    @classmethod
    async def _get_gigachat_access_token(cls, cache_key: str, authorization_key: str) -> str:
        now = datetime.now(timezone.utc)
        cached = cls._gigachat_token_cache.get(cache_key)
        if cached is not None and cached[1] > now + timedelta(minutes=2):
            return cached[0]

        async with cls._gigachat_lock:
            cached = cls._gigachat_token_cache.get(cache_key)
            if cached is not None and cached[1] > now + timedelta(minutes=2):
                return cached[0]

            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    GIGACHAT_TOKEN_URL,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Authorization": f"Basic {authorization_key}",
                        "RqUID": str(uuid.uuid4()),
                    },
                    data={"scope": "GIGACHAT_API_PERS"},
                )
                response.raise_for_status()
                payload = response.json()

            access_token = str(payload["access_token"])
            expires_at = now + timedelta(minutes=29)
            cls._gigachat_token_cache[cache_key] = (access_token, expires_at)
            return access_token

    @classmethod
    async def invoke_chat(
        cls,
        db: AsyncSession,
        *,
        agent_key: str | None,
        actor_user_id: str | None,
        task_id: str | None,
        project_id: str | None,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMInvocationResult:
        resolved = await cls.resolve_provider(db, agent_key=agent_key)
        return await cls._execute_prompt(
            db,
            config=resolved.config,
            profile=resolved.profile,
            actor_user_id=actor_user_id,
            task_id=task_id,
            project_id=project_id,
            agent_key=agent_key,
            request_kind="chat",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    @classmethod
    async def test_provider(
        cls,
        db: AsyncSession,
        *,
        config: LLMProviderConfig,
        actor_user_id: str | None,
    ) -> LLMInvocationResult:
        profile = await cls._build_profile(config)
        return await cls._execute_prompt(
            db,
            config=config,
            profile=profile,
            actor_user_id=actor_user_id,
            task_id=None,
            project_id=None,
            agent_key=None,
            request_kind="provider_test",
            system_prompt="Ты выполняешь проверку подключения к LLM-провайдеру.",
            user_prompt="Кратко подтверди на русском языке, что соединение работает.",
        )

    @classmethod
    async def _execute_prompt(
        cls,
        db: AsyncSession,
        *,
        config: LLMProviderConfig,
        profile: ChatAgentLLMProfile,
        actor_user_id: str | None,
        task_id: str | None,
        project_id: str | None,
        agent_key: str | None,
        request_kind: str,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMInvocationResult:
        started = perf_counter()
        try:
            model = build_chat_model(profile)
            response = await model.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )
            latency_ms = int((perf_counter() - started) * 1000)
            prompt_tokens, completion_tokens, total_tokens = cls._extract_usage(response)
            estimated_cost = cls._estimate_cost(
                config,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            text = cls._stringify_content(getattr(response, "content", ""))
            db.add(
                LLMRequestLog(
                    request_kind=request_kind,
                    actor_user_id=actor_user_id,
                    task_id=task_id,
                    project_id=project_id,
                    agent_key=agent_key,
                    provider_config_id=config.id,
                    provider_kind=config.provider_kind,
                    model=config.model,
                    status="success",
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost,
                )
            )
            return LLMInvocationResult(
                ok=True,
                text=text,
                provider_config_id=config.id,
                provider_kind=config.provider_kind,
                model=config.model,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost,
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((perf_counter() - started) * 1000)
            db.add(
                LLMRequestLog(
                    request_kind=request_kind,
                    actor_user_id=actor_user_id,
                    task_id=task_id,
                    project_id=project_id,
                    agent_key=agent_key,
                    provider_config_id=config.id,
                    provider_kind=config.provider_kind,
                    model=config.model,
                    status="error",
                    latency_ms=latency_ms,
                    error_message=str(exc)[:1000],
                )
            )
            return LLMInvocationResult(
                ok=False,
                text=None,
                provider_config_id=config.id,
                provider_kind=config.provider_kind,
                model=config.model,
                latency_ms=latency_ms,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                estimated_cost_usd=None,
                error_message=str(exc),
            )

    @staticmethod
    def _extract_usage(response: Any) -> tuple[int | None, int | None, int | None]:
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict):
            prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
            completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            return (
                int(prompt_tokens) if prompt_tokens is not None else None,
                int(completion_tokens) if completion_tokens is not None else None,
                int(total_tokens) if total_tokens is not None else None,
            )

        response_metadata = getattr(response, "response_metadata", None)
        token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
        if isinstance(token_usage, dict):
            prompt_tokens = token_usage.get("prompt_tokens")
            completion_tokens = token_usage.get("completion_tokens")
            total_tokens = token_usage.get("total_tokens")
            return (
                int(prompt_tokens) if prompt_tokens is not None else None,
                int(completion_tokens) if completion_tokens is not None else None,
                int(total_tokens) if total_tokens is not None else None,
            )

        return None, None, None

    @staticmethod
    def _estimate_cost(
        config: LLMProviderConfig,
        *,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> Decimal | None:
        if config.provider_kind == "ollama":
            return Decimal("0")
        if prompt_tokens is None and completion_tokens is None:
            return None

        cost = Decimal("0")
        if prompt_tokens is not None and config.input_cost_per_1k_tokens is not None:
            cost += (Decimal(prompt_tokens) / Decimal("1000")) * Decimal(config.input_cost_per_1k_tokens)
        if completion_tokens is not None and config.output_cost_per_1k_tokens is not None:
            cost += (Decimal(completion_tokens) / Decimal("1000")) * Decimal(config.output_cost_per_1k_tokens)
        return cost

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text_value = item.get("text") or item.get("content")
                    if isinstance(text_value, str):
                        parts.append(text_value)
            return "\n".join(part.strip() for part in parts if part.strip())
        return str(content).strip()
