from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel

from .llm import ChatAgentLLMProfile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.llm_runtime_service import LLMInvocationResult

@dataclass(frozen=True, slots=True)
class ChatAgentMetadata:
    key: str
    name: str
    description: str
    aliases: tuple[str, ...] = ()
    priority: int = 100


@dataclass(slots=True)
class ChatAgentContext:
    db: AsyncSession | None
    task_title: str
    task_status: str
    task_content: str
    message_type: str
    message_content: str
    validation_result: dict[str, Any] | None
    related_tasks: list[dict[str, object]]
    actor_user_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    requested_agent: str | None = None
    raw_message_content: str | None = None


@dataclass(slots=True)
class ChatAgentResult:
    agent_name: str
    message_type: str
    response: str
    source_ref: dict[str, Any] = field(default_factory=dict)
    proposal_text: str | None = None


class BaseChatAgent(ABC):
    metadata: ClassVar[ChatAgentMetadata]
    llm_profile: ClassVar[ChatAgentLLMProfile | None] = None

    @classmethod
    def supports_key(cls, key: str) -> bool:
        normalized_key = key.casefold()
        aliases = {alias.casefold() for alias in cls.metadata.aliases}
        return normalized_key == cls.metadata.key.casefold() or normalized_key in aliases

    async def invoke_llm(
        self,
        context: ChatAgentContext,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMInvocationResult | None:
        if context.db is None:
            return None

        from app.services.llm_runtime_service import LLMRuntimeService

        return await LLMRuntimeService.invoke_chat(
            context.db,
            agent_key=self.metadata.key,
            actor_user_id=context.actor_user_id,
            task_id=context.task_id,
            project_id=context.project_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return False

    @abstractmethod
    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        raise NotImplementedError
