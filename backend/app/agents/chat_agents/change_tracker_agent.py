from __future__ import annotations

import json

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .llm import ChatAgentLLMProfile
from .registry import register_chat_agent


def _fallback_acknowledgement() -> str:
    return (
        "Предложение по изменению зарегистрировано и ожидает проверки аналитиком "
        "или администратором. После одобрения требование будет возвращено на доработку и повторную проверку."
    )


@register_chat_agent
class ChangeTrackerAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key="change-tracker",
        name="ChangeTrackerAgent",
        description="Преобразует запросы из чата в отслеживаемые предложения по изменению требований.",
        aliases=("change", "proposal", "changes"),
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
        llm_result = await self.invoke_llm(
            context,
            system_prompt=(
                "Ты нормализуешь запросы на изменение требований. "
                "Верни строгий JSON с ключами proposal_text и acknowledgement. "
                "proposal_text должен содержать чёткое, выполнимое изменение требования. "
                "acknowledgement должен быть одной короткой фразой для пользователя. "
                "Отвечай только на русском языке."
            ),
            user_prompt=(
                f"Название задачи: {context.task_title}\n"
                f"Статус задачи: {context.task_status}\n"
                f"Описание задачи:\n{context.task_content}\n\n"
                f"Запрошенное изменение:\n{context.message_content}\n"
            ),
        )

        proposal_text = context.message_content
        response = _fallback_acknowledgement()
        if llm_result is not None and llm_result.ok and llm_result.text:
            try:
                payload = json.loads(llm_result.text)
                proposal_text = str(payload.get("proposal_text") or proposal_text).strip()
                response = str(payload.get("acknowledgement") or response).strip()
            except json.JSONDecodeError:
                proposal_text = context.message_content
        elif llm_result is not None and llm_result.error_message:
            response = _fallback_acknowledgement()

        return ChatAgentResult(
            agent_name=self.metadata.name,
            message_type="agent_proposal",
            proposal_text=proposal_text,
            response=response,
            source_ref={
                "collection": "change_proposals",
                "provider_kind": llm_result.provider_kind if llm_result is not None and llm_result.ok else None,
                "model": llm_result.model if llm_result is not None and llm_result.ok else None,
                "fallback": llm_result is None or not llm_result.ok,
            },
        )
