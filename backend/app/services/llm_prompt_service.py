from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_agent_prompt_config import LLMAgentPromptConfig
from app.models.llm_agent_prompt_version import LLMAgentPromptVersion
from app.models.user import User
from app.schemas.admin_llm import (
    AgentPromptConfigRead,
    AgentPromptUpdate,
    AgentPromptVersionRead,
)
from app.services.audit_service import AuditService
from app.services.llm_prompt_registry import (
    LLMPromptDefinition,
    get_llm_prompt_definition,
    list_llm_prompt_definitions,
)


class LLMPromptService:
    @staticmethod
    async def list_prompt_configs(db: AsyncSession) -> list[AgentPromptConfigRead]:
        definitions = list_llm_prompt_definitions()
        prompt_keys = [item.prompt_key for item in definitions]
        stmt: Select[tuple[LLMAgentPromptConfig]] = select(LLMAgentPromptConfig).where(
            LLMAgentPromptConfig.prompt_key.in_(prompt_keys)
        )
        configs = {
            item.prompt_key: item for item in (await db.execute(stmt)).scalars().all()
        }
        return [
            LLMPromptService._serialize_config(definition, configs.get(definition.prompt_key))
            for definition in definitions
        ]

    @staticmethod
    async def update_prompt_config(
        prompt_key: str,
        payload: AgentPromptUpdate,
        actor: User,
        db: AsyncSession,
    ) -> AgentPromptConfigRead:
        definition = LLMPromptService._definition_or_404(prompt_key)
        description = LLMPromptService._strip_required(payload.description, "description")
        system_prompt = LLMPromptService._strip_required(payload.system_prompt, "system_prompt")

        config = await db.get(LLMAgentPromptConfig, definition.prompt_key)
        revision = 1 if config is None else config.revision + 1
        if config is None:
            config = LLMAgentPromptConfig(
                prompt_key=definition.prompt_key,
                agent_key=definition.agent_key,
                description=description,
                system_prompt=system_prompt,
                enabled=payload.enabled,
                revision=revision,
                updated_by=actor.id,
            )
            db.add(config)
        else:
            config.agent_key = definition.agent_key
            config.description = description
            config.system_prompt = system_prompt
            config.enabled = payload.enabled
            config.revision = revision
            config.updated_by = actor.id

        db.add(
            LLMAgentPromptVersion(
                prompt_key=definition.prompt_key,
                agent_key=definition.agent_key,
                description=description,
                system_prompt=system_prompt,
                enabled=payload.enabled,
                revision=revision,
                created_by=actor.id,
            )
        )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_prompt.updated",
            entity_type="llm_prompt",
            entity_id=definition.prompt_key,
            metadata={"agent_key": definition.agent_key, "revision": revision},
        )
        await db.commit()
        await db.refresh(config)
        return LLMPromptService._serialize_config(definition, config)

    @staticmethod
    async def list_prompt_versions(
        prompt_key: str,
        db: AsyncSession,
    ) -> list[AgentPromptVersionRead]:
        definition = LLMPromptService._definition_or_404(prompt_key)
        stmt = (
            select(LLMAgentPromptVersion)
            .where(LLMAgentPromptVersion.prompt_key == definition.prompt_key)
            .order_by(LLMAgentPromptVersion.revision.desc())
        )
        versions = list((await db.execute(stmt)).scalars().all())
        return [LLMPromptService._serialize_version(version) for version in versions]

    @staticmethod
    async def restore_prompt_version(
        prompt_key: str,
        version_id: str,
        actor: User,
        db: AsyncSession,
    ) -> AgentPromptConfigRead:
        definition = LLMPromptService._definition_or_404(prompt_key)
        version = await db.get(LLMAgentPromptVersion, version_id)
        if version is None or version.prompt_key != definition.prompt_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Версия промпта не найдена",
            )

        config = await db.get(LLMAgentPromptConfig, definition.prompt_key)
        revision = 1 if config is None else config.revision + 1
        if config is None:
            config = LLMAgentPromptConfig(
                prompt_key=definition.prompt_key,
                agent_key=definition.agent_key,
                description=version.description,
                system_prompt=version.system_prompt,
                enabled=version.enabled,
                revision=revision,
                updated_by=actor.id,
            )
            db.add(config)
        else:
            config.agent_key = definition.agent_key
            config.description = version.description
            config.system_prompt = version.system_prompt
            config.enabled = version.enabled
            config.revision = revision
            config.updated_by = actor.id

        db.add(
            LLMAgentPromptVersion(
                prompt_key=definition.prompt_key,
                agent_key=definition.agent_key,
                description=version.description,
                system_prompt=version.system_prompt,
                enabled=version.enabled,
                revision=revision,
                created_by=actor.id,
            )
        )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.llm_prompt.restored",
            entity_type="llm_prompt",
            entity_id=definition.prompt_key,
            metadata={
                "agent_key": definition.agent_key,
                "restored_version_id": version.id,
                "revision": revision,
            },
        )
        await db.commit()
        await db.refresh(config)
        return LLMPromptService._serialize_config(definition, config)

    @staticmethod
    async def resolve_system_prompt(
        db: AsyncSession,
        *,
        prompt_key: str | None,
        default_system_prompt: str,
    ) -> str:
        if not prompt_key:
            return default_system_prompt
        config = await db.get(LLMAgentPromptConfig, prompt_key)
        if config is None or not config.enabled:
            return default_system_prompt
        return config.system_prompt

    @staticmethod
    async def resolve_description(
        db: AsyncSession,
        *,
        prompt_key: str | None,
        default_description: str,
    ) -> str:
        if not prompt_key:
            return default_description
        config = await db.get(LLMAgentPromptConfig, prompt_key)
        if config is None or not config.enabled:
            return default_description
        return config.description

    @staticmethod
    def _definition_or_404(prompt_key: str) -> LLMPromptDefinition:
        definition = get_llm_prompt_definition(prompt_key)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Промпт агента не найден",
            )
        return definition

    @staticmethod
    def _serialize_config(
        definition: LLMPromptDefinition,
        config: LLMAgentPromptConfig | None,
    ) -> AgentPromptConfigRead:
        override_enabled = bool(config.enabled) if config is not None else False
        override_description = config.description if config is not None else None
        override_system_prompt = config.system_prompt if config is not None else None
        return AgentPromptConfigRead(
            prompt_key=definition.prompt_key,
            agent_key=definition.agent_key,
            name=definition.name,
            aliases=list(definition.aliases),
            default_description=definition.description,
            default_system_prompt=definition.default_system_prompt,
            effective_description=(
                override_description
                if override_enabled and override_description is not None
                else definition.description
            ),
            effective_system_prompt=(
                override_system_prompt
                if override_enabled and override_system_prompt is not None
                else definition.default_system_prompt
            ),
            override_description=override_description,
            override_system_prompt=override_system_prompt,
            override_enabled=override_enabled,
            revision=config.revision if config is not None else None,
            updated_at=config.updated_at if config is not None else None,
        )

    @staticmethod
    def _serialize_version(version: LLMAgentPromptVersion) -> AgentPromptVersionRead:
        return AgentPromptVersionRead(
            id=version.id,
            prompt_key=version.prompt_key,
            agent_key=version.agent_key,
            description=version.description,
            system_prompt=version.system_prompt,
            enabled=version.enabled,
            revision=version.revision,
            created_at=version.created_at,
        )

    @staticmethod
    def _strip_required(value: str, field_name: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Поле {field_name} не может быть пустым",
            )
        return stripped
