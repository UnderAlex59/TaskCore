from __future__ import annotations

from app.agents.qa_agent_graph import (
    QA_AGENT_ALIASES,
    QA_AGENT_DESCRIPTION,
    QA_AGENT_KEY,
    QA_AGENT_NAME,
    run_qa_agent_graph,
)

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .registry import register_chat_agent


@register_chat_agent
class QuestionAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key=QA_AGENT_KEY,
        name=QA_AGENT_NAME,
        description=QA_AGENT_DESCRIPTION,
        aliases=QA_AGENT_ALIASES,
        priority=20,
    )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return context.message_type == "question"

    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        state = await run_qa_agent_graph(
            db=context.db,
            actor_user_id=context.actor_user_id,
            task_id=context.task_id,
            project_id=context.project_id,
            task_title=context.task_title,
            task_status=context.task_status,
            task_content=context.task_content,
            message_content=context.message_content,
            validation_result=context.validation_result,
            related_tasks=context.related_tasks,
            routing_mode="direct",
        )
        return ChatAgentResult(
            agent_name=str(state.get("agent_name", self.metadata.name)),
            message_type=str(state.get("message_type", "agent_answer")),
            response=str(state.get("response", "")),
            source_ref=dict(state.get("source_ref", {})),
        )
