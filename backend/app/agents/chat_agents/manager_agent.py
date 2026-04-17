from __future__ import annotations

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .registry import register_chat_agent


@register_chat_agent
class ManagerAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key="manager",
        name="ManagerAgent",
        description="Резервный агент, который оставляет сообщение в треде и объясняет маршрутизацию.",
        aliases=("router", "default"),
        priority=1000,
    )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return True

    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        response = (
            "Сообщение сохранено в обсуждении. Чтобы получить автоматический ответ, "
            "сформулируйте вопрос или явное предложение по изменению требования."
        )
        if context.requested_agent is None:
            response += (
                " При необходимости можно явно выбрать агента через префикс "
                "вида `@qa` или `@change-tracker`."
            )

        return ChatAgentResult(
            agent_name=self.metadata.name,
            message_type="agent_answer",
            response=response,
            source_ref={"collection": "messages"},
        )
