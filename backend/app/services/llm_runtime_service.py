from __future__ import annotations

import asyncio
import base64
import hashlib
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_agents.llm import (
    ChatAgentLLMProfile,
    build_chat_model,
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
PROMPT_LOG_MODE_DISABLED = "disabled"
PROMPT_LOG_MODE_FULL = "full"
MAX_LOG_TEXT_CHARS = 50_000
TRUNCATED_SUFFIX = "\n...[truncated]"


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
            raise ValueError("Р”Р»СЏ РїСЂРѕРІР°Р№РґРµСЂР° openai_compatible РЅРµРѕР±С…РѕРґРёРјРѕ СѓРєР°Р·Р°С‚СЊ base_url")
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
        try:
            return cls._fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "Не удалось расшифровать секрет LLM-провайдера. Обновите секрет в админ-панели."
            ) from exc

    @staticmethod
    def _build_unavailable_result(
        *,
        provider_kind: str = "unknown",
        model: str = "",
        error_message: str,
    ) -> LLMInvocationResult:
        return LLMInvocationResult(
            ok=False,
            text=None,
            provider_config_id=None,
            provider_kind=provider_kind,
            model=model,
            latency_ms=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            estimated_cost_usd=None,
            error_message=error_message,
        )

    @classmethod
    def _get_gigachat_ssl_verify(cls) -> bool | ssl.SSLContext:
        settings = get_settings()
        if not settings.GIGACHAT_VERIFY_SSL:
            return False
        if not settings.GIGACHAT_CA_BUNDLE_FILE and not settings.GIGACHAT_CA_BUNDLE_PEM:
            return True

        context = ssl.create_default_context()
        if settings.GIGACHAT_CA_BUNDLE_FILE:
            ca_bundle_path = Path(settings.GIGACHAT_CA_BUNDLE_FILE).expanduser()
            if not ca_bundle_path.is_file():
                raise ValueError(
                    f"Файл GIGACHAT_CA_BUNDLE_FILE не найден: {ca_bundle_path}"
                )
            context.load_verify_locations(cafile=str(ca_bundle_path))
        if settings.GIGACHAT_CA_BUNDLE_PEM:
            context.load_verify_locations(cadata=settings.GIGACHAT_CA_BUNDLE_PEM)
        return context

    @classmethod
    def _build_gigachat_http_clients(
        cls,
        verify: bool | ssl.SSLContext,
    ) -> tuple[httpx.Client, httpx.AsyncClient]:
        timeout = httpx.Timeout(60.0, connect=20.0)
        return (
            httpx.Client(verify=verify, timeout=timeout),
            httpx.AsyncClient(verify=verify, timeout=timeout),
        )

    @classmethod
    async def ensure_bootstrap(cls) -> None:
        async with cls._bootstrap_lock, AsyncSessionLocal() as db:
            runtime_settings = await db.get(LLMRuntimeSettings, 1)
            if runtime_settings is not None:
                return

            db.add(
                LLMRuntimeSettings(
                    id=1,
                    default_provider_config_id=None,
                    prompt_log_mode=PROMPT_LOG_MODE_FULL,
                )
            )

            await db.commit()

    @classmethod
    async def resolve_provider(
        cls,
        db: AsyncSession,
        *,
        agent_key: str | None,
    ) -> ResolvedLLMProvider:
        await cls.ensure_bootstrap()

        selected: LLMProviderConfig | None = None
        if agent_key:
            override_stmt = (
                select(LLMAgentOverride, LLMProviderConfig)
                .join(
                    LLMProviderConfig,
                    LLMProviderConfig.id == LLMAgentOverride.provider_config_id,
                )
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
            if (
                runtime_settings is not None
                and runtime_settings.default_provider_config_id is not None
            ):
                selected = await db.get(
                    LLMProviderConfig,
                    runtime_settings.default_provider_config_id,
                )
                if selected is not None and not selected.enabled:
                    selected = None

        if selected is None:
            raise RuntimeError(
                "РќРµ РЅР°СЃС‚СЂРѕРµРЅ LLM-РїСЂРѕРІР°Р№РґРµСЂ. Р”РѕР±Р°РІСЊС‚Рµ РїСЂРѕС„РёР»СЊ Рё РІС‹Р±РµСЂРёС‚Рµ РїСЂРѕС„РёР»СЊ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ РІ Р°РґРјРёРЅ-РїР°РЅРµР»Рё."
            )

        profile = await cls._build_profile(selected)
        return ResolvedLLMProvider(config=selected, profile=profile)

    @classmethod
    async def _build_profile(cls, config: LLMProviderConfig) -> ChatAgentLLMProfile:
        provider_kind = config.provider_kind
        api_key: str | None = None
        http_client: httpx.Client | None = None
        http_async_client: httpx.AsyncClient | None = None
        if provider_kind != "ollama":
            secret = cls.decrypt_secret(config.encrypted_secret)
            if provider_kind == "gigachat":
                if not secret:
                    raise ValueError("Р”Р»СЏ GigaChat РЅРµ РЅР°СЃС‚СЂРѕРµРЅ РєР»СЋС‡ Р°РІС‚РѕСЂРёР·Р°С†РёРё")
                ssl_verify = cls._get_gigachat_ssl_verify()
                api_key = await cls._get_gigachat_access_token(
                    config.id,
                    secret,
                    verify=ssl_verify,
                )
                http_client, http_async_client = cls._build_gigachat_http_clients(ssl_verify)
            else:
                api_key = secret

        return ChatAgentLLMProfile(
            provider=provider_kind,  # type: ignore[arg-type]
            model=config.model,
            temperature=float(config.temperature),
            api_key=api_key,
            base_url=config.base_url,
            http_client=http_client,
            http_async_client=http_async_client,
        )

    @classmethod
    async def _get_gigachat_access_token(
        cls,
        cache_key: str,
        authorization_key: str,
        *,
        verify: bool | ssl.SSLContext | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        cached = cls._gigachat_token_cache.get(cache_key)
        if cached is not None and cached[1] > now + timedelta(minutes=2):
            return cached[0]

        async with cls._gigachat_lock:
            cached = cls._gigachat_token_cache.get(cache_key)
            if cached is not None and cached[1] > now + timedelta(minutes=2):
                return cached[0]

            ssl_verify = cls._get_gigachat_ssl_verify() if verify is None else verify
            async with httpx.AsyncClient(timeout=20.0, verify=ssl_verify) as client:
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
        prompt_key: str | None = None,
    ) -> LLMInvocationResult:
        try:
            resolved = await cls.resolve_provider(db, agent_key=agent_key)
        except Exception as exc:  # noqa: BLE001
            return cls._build_unavailable_result(error_message=str(exc))
        from app.services.llm_prompt_service import LLMPromptService

        effective_system_prompt = await LLMPromptService.resolve_system_prompt(
            db,
            prompt_key=prompt_key or agent_key,
            default_system_prompt=system_prompt,
        )
        return await cls._execute_prompt(
            db,
            config=resolved.config,
            profile=resolved.profile,
            actor_user_id=actor_user_id,
            task_id=task_id,
            project_id=project_id,
            agent_key=agent_key,
            request_kind="chat",
            system_prompt=effective_system_prompt,
            user_prompt=user_prompt,
        )

    @classmethod
    async def invoke_vision(
        cls,
        db: AsyncSession,
        *,
        agent_key: str | None,
        actor_user_id: str | None,
        task_id: str | None,
        project_id: str | None,
        image_bytes: bytes,
        content_type: str,
        prompt: str,
    ) -> LLMInvocationResult:
        try:
            resolved = await cls.resolve_provider(db, agent_key=agent_key)
        except Exception as exc:  # noqa: BLE001
            return cls._build_unavailable_result(error_message=str(exc))
        if not resolved.config.vision_enabled:
            return cls._build_unavailable_result(
                provider_kind=resolved.config.provider_kind,
                model=resolved.config.model,
                error_message="Для выбранного профиля поддержка Vision отключена в настройках.",
            )
        data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        system_prompt = (
            "Ты преобразуешь изображение из требований в текст, "
            "пригодный для семантического поиска."
        )
        return await cls._execute_messages(
            db,
            config=resolved.config,
            profile=resolved.profile,
            actor_user_id=actor_user_id,
            task_id=task_id,
            project_id=project_id,
            agent_key=agent_key,
            request_kind="vision_alt_text",
            messages=cls._build_vision_messages(
                data_url=data_url,
                prompt=prompt,
                system_prompt=system_prompt,
                vision_system_prompt_mode=resolved.config.vision_system_prompt_mode,
                vision_message_order=resolved.config.vision_message_order,
                vision_detail=resolved.config.vision_detail,
            ),
        )

    @classmethod
    async def test_provider(
        cls,
        db: AsyncSession,
        *,
        config: LLMProviderConfig,
        actor_user_id: str | None,
    ) -> LLMInvocationResult:
        try:
            profile = await cls._build_profile(config)
        except Exception as exc:  # noqa: BLE001
            return cls._build_unavailable_result(
                provider_kind=config.provider_kind,
                model=config.model,
                error_message=str(exc),
            )
        return await cls._execute_prompt(
            db,
            config=config,
            profile=profile,
            actor_user_id=actor_user_id,
            task_id=None,
            project_id=None,
            agent_key=None,
            request_kind="provider_test",
            system_prompt="РўС‹ РІС‹РїРѕР»РЅСЏРµС€СЊ РїСЂРѕРІРµСЂРєСѓ РїРѕРґРєР»СЋС‡РµРЅРёСЏ Рє LLM-РїСЂРѕРІР°Р№РґРµСЂСѓ.",
            user_prompt="РљСЂР°С‚РєРѕ РїРѕРґС‚РІРµСЂРґРё РЅР° СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµ, С‡С‚Рѕ СЃРѕРµРґРёРЅРµРЅРёРµ СЂР°Р±РѕС‚Р°РµС‚.",
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
        return await cls._execute_messages(
            db,
            config=config,
            profile=profile,
            actor_user_id=actor_user_id,
            task_id=task_id,
            project_id=project_id,
            agent_key=agent_key,
            request_kind=request_kind,
            messages=[SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        )

    @staticmethod
    async def _get_prompt_log_mode(db: AsyncSession) -> str:
        runtime = await db.get(LLMRuntimeSettings, 1)
        return runtime.prompt_log_mode if runtime is not None else PROMPT_LOG_MODE_FULL

    @staticmethod
    def _add_request_log(
        db: AsyncSession,
        *,
        prompt_log_mode: str,
        request_kind: str,
        actor_user_id: str | None,
        task_id: str | None,
        project_id: str | None,
        agent_key: str | None,
        config: LLMProviderConfig,
        status: str,
        latency_ms: int | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        estimated_cost_usd: Decimal | None,
        request_messages: list[dict[str, Any]] | None,
        response_text: str | None,
        error_message: str | None,
    ) -> None:
        if prompt_log_mode == PROMPT_LOG_MODE_DISABLED:
            return

        should_store_payload = prompt_log_mode == PROMPT_LOG_MODE_FULL
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
                status=status,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                request_messages=request_messages if should_store_payload else None,
                response_text=(
                    LLMRuntimeService._limit_log_text(response_text)
                    if should_store_payload
                    else None
                ),
                error_message=error_message,
            )
        )

    @classmethod
    async def _close_profile_clients(cls, profile: ChatAgentLLMProfile) -> None:
        if isinstance(profile.http_async_client, httpx.AsyncClient):
            try:
                await profile.http_async_client.aclose()
            except Exception:  # noqa: BLE001
                pass
        if isinstance(profile.http_client, httpx.Client):
            try:
                profile.http_client.close()
            except Exception:  # noqa: BLE001
                pass

    @classmethod
    async def _execute_messages(
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
        messages: list[Any],
    ) -> LLMInvocationResult:
        started = perf_counter()
        prompt_log_mode = await cls._get_prompt_log_mode(db)
        normalized_messages = cls._normalize_messages_for_model(profile, messages)
        request_messages = (
            cls._serialize_messages(normalized_messages)
            if prompt_log_mode == PROMPT_LOG_MODE_FULL
            else None
        )
        try:
            model = build_chat_model(profile)
            response = await model.ainvoke(normalized_messages)
            latency_ms = int((perf_counter() - started) * 1000)
            prompt_tokens, completion_tokens, total_tokens = cls._extract_usage(response)
            estimated_cost = cls._estimate_cost(
                config,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            text = cls._stringify_content(getattr(response, "content", ""))
            cls._add_request_log(
                db,
                prompt_log_mode=prompt_log_mode,
                request_kind=request_kind,
                actor_user_id=actor_user_id,
                task_id=task_id,
                project_id=project_id,
                agent_key=agent_key,
                config=config,
                status="success",
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost,
                request_messages=request_messages,
                response_text=text,
                error_message=None,
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
            cls._add_request_log(
                db,
                prompt_log_mode=prompt_log_mode,
                request_kind=request_kind,
                actor_user_id=actor_user_id,
                task_id=task_id,
                project_id=project_id,
                agent_key=agent_key,
                config=config,
                status="error",
                latency_ms=latency_ms,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                estimated_cost_usd=None,
                request_messages=request_messages,
                response_text=None,
                error_message=str(exc)[:1000],
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
        finally:
            await cls._close_profile_clients(profile)

    @classmethod
    def _normalize_messages_for_model(
        cls,
        profile: ChatAgentLLMProfile,
        messages: list[Any],
    ) -> list[Any]:
        if "gemma" not in profile.model.casefold():
            return messages

        pending_system: list[str] = []
        normalized: list[Any] = []
        for message in messages:
            if cls._message_role(message) == "system":
                content = cls._stringify_content(getattr(message, "content", ""))
                if content.strip():
                    pending_system.append(content.strip())
                continue

            if pending_system and cls._message_role(message) == "human":
                normalized.append(
                    cls._merge_system_prompt_into_human_message(
                        message,
                        "\n\n".join(pending_system),
                    )
                )
                pending_system.clear()
                continue

            if pending_system:
                normalized.append(HumanMessage(content="\n\n".join(pending_system)))
                pending_system.clear()
            normalized.append(message)

        if pending_system:
            normalized.append(HumanMessage(content="\n\n".join(pending_system)))
        return normalized

    @staticmethod
    def _build_vision_messages(
        *,
        data_url: str,
        prompt: str,
        system_prompt: str,
        vision_system_prompt_mode: str,
        vision_message_order: str,
        vision_detail: str,
    ) -> list[Any]:
        image_url: dict[str, Any] = {"url": data_url}
        if vision_detail != "default":
            image_url["detail"] = vision_detail

        image_part = {"type": "image_url", "image_url": image_url}
        text_value = prompt.strip()
        if vision_system_prompt_mode == "inline_user":
            text_value = f"{system_prompt}\n\n{text_value}".strip()
        text_part = {"type": "text", "text": text_value}

        content_parts = (
            [image_part, text_part]
            if vision_message_order == "image_first"
            else [text_part, image_part]
        )
        messages: list[Any] = []
        if vision_system_prompt_mode == "system_role":
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=content_parts))
        return messages

    @staticmethod
    def _merge_system_prompt_into_human_message(message: Any, system_prompt: str) -> HumanMessage:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            merged = f"{system_prompt}\n\n{content}".strip()
            return HumanMessage(content=merged)

        if isinstance(content, list):
            parts = list(content)
            for index, part in enumerate(parts):
                if (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                ):
                    parts[index] = {
                        **part,
                        "text": f"{system_prompt}\n\n{part['text']}".strip(),
                    }
                    return HumanMessage(content=parts)

            parts.insert(0, {"type": "text", "text": system_prompt})
            return HumanMessage(content=parts)

        return HumanMessage(content=system_prompt)

    @classmethod
    def _serialize_messages(cls, messages: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "role": cls._message_role(message),
                "content": cls._serialize_log_content(
                    getattr(message, "content", message)
                ),
            }
            for message in messages
        ]

    @staticmethod
    def _message_role(message: Any) -> str:
        message_type = getattr(message, "type", None)
        if isinstance(message_type, str) and message_type:
            return message_type
        return message.__class__.__name__.removesuffix("Message").lower()

    @classmethod
    def _serialize_log_content(cls, content: Any) -> Any:
        if isinstance(content, str):
            return cls._limit_log_text(content)
        if isinstance(content, list):
            return [cls._serialize_log_content(item) for item in content]
        if isinstance(content, dict):
            if content.get("type") == "image_url":
                return cls._serialize_image_part(content)
            return {
                str(key): cls._serialize_log_content(value)
                for key, value in content.items()
            }
        return content

    @classmethod
    def _serialize_image_part(cls, content: dict[Any, Any]) -> dict[str, Any]:
        image_url = content.get("image_url")
        if isinstance(image_url, dict):
            url = image_url.get("url")
            media_type = cls._data_url_media_type(url) if isinstance(url, str) else None
            return {
                "type": "image_url",
                "image_url": {
                    **{
                        str(key): value
                        for key, value in image_url.items()
                        if key != "url"
                    },
                    "url": "[image data omitted]",
                    "media_type": media_type,
                },
            }
        return {"type": "image_url", "image_url": "[image data omitted]"}

    @staticmethod
    def _data_url_media_type(value: str) -> str | None:
        if not value.startswith("data:") or ";base64," not in value:
            return None
        return value.removeprefix("data:").split(";base64,", maxsplit=1)[0] or None

    @staticmethod
    def _limit_log_text(value: str | None) -> str | None:
        if value is None or len(value) <= MAX_LOG_TEXT_CHARS:
            return value
        return f"{value[:MAX_LOG_TEXT_CHARS]}{TRUNCATED_SUFFIX}"

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
        token_usage = (
            response_metadata.get("token_usage") if isinstance(response_metadata, dict) else None
        )
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
            cost += (Decimal(prompt_tokens) / Decimal("1000")) * Decimal(
                config.input_cost_per_1k_tokens
            )
        if completion_tokens is not None and config.output_cost_per_1k_tokens is not None:
            cost += (Decimal(completion_tokens) / Decimal("1000")) * Decimal(
                config.output_cost_per_1k_tokens
            )
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
