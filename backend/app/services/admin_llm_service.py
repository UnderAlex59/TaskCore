from __future__ import annotations

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.provider_test_graph import run_provider_test_graph
from app.models.llm_agent_override import LLMAgentOverride
from app.models.llm_provider_config import LLMProviderConfig
from app.models.llm_runtime_settings import LLMRuntimeSettings
from app.models.user import User
from app.schemas.admin_llm import (
    AgentDirectoryRead,
    AgentOverrideRead,
    AgentOverrideUpdate,
    ProviderConfigPayload,
    ProviderConfigRead,
    ProviderConfigUpdate,
    ProviderTestResult,
)
from app.services.audit_service import AuditService
from app.services.llm_agent_registry import list_llm_agents
from app.services.llm_runtime_service import LLMRuntimeService


class AdminLLMService:
    @staticmethod
    async def list_provider_configs(db: AsyncSession) -> list[ProviderConfigRead]:
        await LLMRuntimeService.ensure_bootstrap()
        stmt: Select[tuple[LLMProviderConfig]] = select(LLMProviderConfig).order_by(
            LLMProviderConfig.created_at.desc()
        )
        providers = list((await db.execute(stmt)).scalars().all())
        return await AdminLLMService._serialize_provider_list(db, providers)

    @staticmethod
    async def create_provider_config(
        payload: ProviderConfigPayload,
        actor: User,
        db: AsyncSession,
    ) -> ProviderConfigRead:
        encrypted_secret, masked_secret = LLMRuntimeService.encrypt_secret(payload.secret)
        provider = LLMProviderConfig(
            name=payload.name,
            provider_kind=payload.provider_kind,
            base_url=LLMRuntimeService.normalize_base_url(payload.provider_kind, payload.base_url),
            model=payload.model,
            temperature=payload.temperature,
            enabled=payload.enabled,
            encrypted_secret=encrypted_secret,
            masked_secret=masked_secret,
            input_cost_per_1k_tokens=payload.input_cost_per_1k_tokens,
            output_cost_per_1k_tokens=payload.output_cost_per_1k_tokens,
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(provider)
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_provider.created",
            entity_type="llm_provider",
            metadata={"name": payload.name, "provider_kind": payload.provider_kind},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Название профиля провайдера должно быть уникальным",
            ) from exc

        await db.refresh(provider)
        return await AdminLLMService.get_provider_config(provider.id, db)

    @staticmethod
    async def get_provider_config(provider_id: str, db: AsyncSession) -> ProviderConfigRead:
        await LLMRuntimeService.ensure_bootstrap()
        provider = await db.get(LLMProviderConfig, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль провайдера не найден",
            )
        await db.refresh(provider)
        return (await AdminLLMService._serialize_provider_list(db, [provider]))[0]

    @staticmethod
    async def update_provider_config(
        provider_id: str,
        payload: ProviderConfigUpdate,
        actor: User,
        db: AsyncSession,
    ) -> ProviderConfigRead:
        provider = await db.get(LLMProviderConfig, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль провайдера не найден",
            )

        updates = payload.model_dump(exclude_unset=True)
        secret = updates.pop("secret", None)
        provider_kind = str(updates.get("provider_kind", provider.provider_kind))
        if "base_url" in updates or "provider_kind" in updates:
            provider.base_url = LLMRuntimeService.normalize_base_url(
                provider_kind,
                updates.get("base_url", provider.base_url),
            )
        for field_name, value in updates.items():
            if field_name == "base_url":
                continue
            setattr(provider, field_name, value)

        if secret is not None:
            (
                provider.encrypted_secret,
                provider.masked_secret,
            ) = LLMRuntimeService.encrypt_secret(secret)

        provider.updated_by = actor.id
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_provider.updated",
            entity_type="llm_provider",
            entity_id=provider.id,
            metadata={"provider_kind": provider.provider_kind, "enabled": provider.enabled},
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Название профиля провайдера должно быть уникальным",
            ) from exc

        await db.refresh(provider)
        return await AdminLLMService.get_provider_config(provider.id, db)

    @staticmethod
    async def test_provider_config(
        provider_id: str,
        actor: User,
        db: AsyncSession,
    ) -> ProviderTestResult:
        result = await run_provider_test_graph(
            db=db,
            provider_id=provider_id,
            actor_user_id=actor.id,
        )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_provider.tested",
            entity_type="llm_provider",
            entity_id=provider_id,
            metadata={"ok": result["ok"], "provider_kind": result["provider_kind"]},
        )
        await db.commit()
        return ProviderTestResult(
            ok=bool(result["ok"]),
            provider_kind=result["provider_kind"],  # type: ignore[arg-type]
            model=result["model"],
            latency_ms=result["latency_ms"],
            message=result["message"],
        )

    @staticmethod
    async def set_default_provider(
        provider_id: str,
        actor: User,
        db: AsyncSession,
    ) -> ProviderConfigRead:
        provider = await db.get(LLMProviderConfig, provider_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль провайдера не найден",
            )

        provider.enabled = True
        runtime = await db.get(LLMRuntimeSettings, 1)
        if runtime is None:
            runtime = LLMRuntimeSettings(
                id=1,
                default_provider_config_id=provider.id,
                prompt_log_mode="metadata_only",
                updated_by=actor.id,
            )
            db.add(runtime)
        else:
            runtime.default_provider_config_id = provider.id
            runtime.updated_by = actor.id

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_provider.default_set",
            entity_type="llm_provider",
            entity_id=provider.id,
            metadata={"provider_kind": provider.provider_kind},
        )
        await db.commit()
        await db.refresh(provider)
        return await AdminLLMService.get_provider_config(provider.id, db)

    @staticmethod
    async def list_agent_overrides(db: AsyncSession) -> list[AgentOverrideRead]:
        await LLMRuntimeService.ensure_bootstrap()
        stmt = (
            select(LLMAgentOverride, LLMProviderConfig)
            .join(LLMProviderConfig, LLMProviderConfig.id == LLMAgentOverride.provider_config_id)
            .order_by(LLMAgentOverride.agent_key.asc())
        )
        rows = list((await db.execute(stmt)).all())
        return [
            AgentOverrideRead(
                agent_key=override.agent_key,
                provider_config_id=provider.id,
                provider_name=provider.name,
                provider_kind=provider.provider_kind,  # type: ignore[arg-type]
                model=provider.model,
                enabled=override.enabled,
            )
            for override, provider in rows
        ]

    @staticmethod
    async def upsert_agent_override(
        agent_key: str,
        payload: AgentOverrideUpdate,
        actor: User,
        db: AsyncSession,
    ) -> AgentOverrideRead:
        available_agent_keys = {item.key for item in list_llm_agents()}
        if agent_key not in available_agent_keys:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Агент не найден",
            )

        provider = await db.get(LLMProviderConfig, payload.provider_config_id)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Профиль провайдера не найден",
            )

        override = await db.get(LLMAgentOverride, agent_key)
        if override is None:
            override = LLMAgentOverride(
                agent_key=agent_key,
                provider_config_id=provider.id,
                enabled=payload.enabled,
                updated_by=actor.id,
            )
            db.add(override)
        else:
            override.provider_config_id = provider.id
            override.enabled = payload.enabled
            override.updated_by = actor.id

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_override.updated",
            entity_type="llm_override",
            entity_id=agent_key,
            metadata={"provider_id": provider.id, "enabled": payload.enabled},
        )
        await db.commit()
        return AgentOverrideRead(
            agent_key=agent_key,
            provider_config_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.provider_kind,  # type: ignore[arg-type]
            model=provider.model,
            enabled=payload.enabled,
        )

    @staticmethod
    async def list_available_agents() -> list[AgentDirectoryRead]:
        return [
            AgentDirectoryRead(
                key=item.key,
                name=item.name,
                description=item.description,
                aliases=list(item.aliases),
            )
            for item in list_llm_agents()
        ]

    @staticmethod
    async def _serialize_provider_list(
        db: AsyncSession,
        providers: list[LLMProviderConfig],
    ) -> list[ProviderConfigRead]:
        runtime = await db.get(LLMRuntimeSettings, 1)
        override_stmt = (
            select(LLMAgentOverride.agent_key, LLMAgentOverride.provider_config_id)
            .where(LLMAgentOverride.enabled.is_(True))
        )
        override_rows = list((await db.execute(override_stmt)).all())
        used_by: dict[str, list[str]] = defaultdict(list)
        for agent_key, provider_id in override_rows:
            used_by[str(provider_id)].append(agent_key)

        return [
            ProviderConfigRead(
                id=provider.id,
                name=provider.name,
                provider_kind=provider.provider_kind,  # type: ignore[arg-type]
                base_url=provider.base_url,
                model=provider.model,
                temperature=float(provider.temperature),
                enabled=provider.enabled,
                input_cost_per_1k_tokens=provider.input_cost_per_1k_tokens,
                output_cost_per_1k_tokens=provider.output_cost_per_1k_tokens,
                secret_configured=provider.encrypted_secret is not None,
                masked_secret=provider.masked_secret,
                is_default=(
                    runtime is not None
                    and runtime.default_provider_config_id == provider.id
                ),
                used_by_agents=sorted(used_by.get(provider.id, [])),
                created_at=provider.created_at,
                updated_at=provider.updated_at,
            )
            for provider in providers
        ]
