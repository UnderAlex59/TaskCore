from __future__ import annotations

from app.agents.change_tracker_agent_graph import (
    CHANGE_TRACKER_AGENT_ALIASES,
    CHANGE_TRACKER_AGENT_DESCRIPTION,
    CHANGE_TRACKER_AGENT_KEY,
    CHANGE_TRACKER_AGENT_NAME,
    run_change_tracker_agent_graph,
)

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .llm import ChatAgentLLMProfile
from .registry import register_chat_agent


@register_chat_agent
class ChangeTrackerAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key=CHANGE_TRACKER_AGENT_KEY,
        name=CHANGE_TRACKER_AGENT_NAME,
        description=CHANGE_TRACKER_AGENT_DESCRIPTION,
        aliases=CHANGE_TRACKER_AGENT_ALIASES,
        priority=30,
    )
    llm_profile = ChatAgentLLMProfile(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.0,
    )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return context.message_type == "change_proposal"

    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        state = await run_change_tracker_agent_graph(
            db=context.db,
            actor_user_id=context.actor_user_id,
            task_id=context.task_id,
            project_id=context.project_id,
            task_title=context.task_title,
            task_status=context.task_status,
            task_content=context.task_content,
            message_content=context.message_content,
            routing_mode="direct",
        )
        return ChatAgentResult(
            agent_name=str(state.get("agent_name", self.metadata.name)),
            message_type=str(state.get("message_type", "agent_proposal")),
            response=str(state.get("response", "")),
            source_ref=dict(state.get("source_ref", {})),
            proposal_text=(
                str(state.get("proposal_text"))
                if state.get("proposal_text") is not None
                else None
            ),
        )
