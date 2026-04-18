from __future__ import annotations

from app.agents.manager_agent_graph import (
    MANAGER_AGENT_ALIASES,
    MANAGER_AGENT_DESCRIPTION,
    MANAGER_AGENT_KEY,
    MANAGER_AGENT_NAME,
    run_manager_agent_graph,
)

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .registry import register_chat_agent


@register_chat_agent
class ManagerAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key=MANAGER_AGENT_KEY,
        name=MANAGER_AGENT_NAME,
        description=MANAGER_AGENT_DESCRIPTION,
        aliases=MANAGER_AGENT_ALIASES,
        priority=1000,
    )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return True

    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        state = await run_manager_agent_graph(
            requested_agent=context.requested_agent,
            routing_mode="direct",
        )
        return ChatAgentResult(
            agent_name=str(state.get("agent_name", self.metadata.name)),
            message_type=str(state.get("message_type", "agent_answer")),
            response=str(state.get("response", "")),
            source_ref=dict(state.get("source_ref", {})),
        )
