from __future__ import annotations

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult
from .llm import ChatAgentLLMProfile
from .registry import register_chat_agent


@register_chat_agent
class QuestionAgent(BaseChatAgent):
    metadata = ChatAgentMetadata(
        key="qa",
        name="QAAgent",
        description="Отвечает на вопросы по требованиям с учётом контекста задачи и последней проверки.",
        aliases=("question", "analyst"),
        priority=20,
    )
    llm_profile = ChatAgentLLMProfile(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.2,
    )

    async def can_handle(self, context: ChatAgentContext) -> bool:
        return context.message_type == "question"

    async def handle(self, context: ChatAgentContext) -> ChatAgentResult:
        related_titles = ", ".join(
            str(item["title"]) for item in context.related_tasks[:3] if "title" in item
        )
        validation_result = context.validation_result or {}
        issues = validation_result.get("issues", [])
        questions = validation_result.get("questions", [])
        llm_result = await self.invoke_llm(
            context,
            system_prompt=(
                "Ты опытный продуктовый аналитик. Отвечай на вопрос пользователя "
                "только на русском языке, используя контекст задачи, результаты "
                "последней проверки и связанные задачи. Пиши конкретно, коротко и "
                "с учётом реализации. Если данных недостаточно, прямо укажи, чего не хватает."
            ),
            user_prompt=(
                f"Название задачи: {context.task_title}\n"
                f"Статус задачи: {context.task_status}\n"
                f"Описание задачи:\n{context.task_content}\n\n"
                f"Вопрос пользователя:\n{context.message_content}\n\n"
                f"Вердикт проверки: {validation_result.get('verdict', 'нет')}\n"
                f"Замечания проверки: {issues}\n"
                f"Открытые вопросы проверки: {questions}\n"
                f"Связанные задачи: {related_titles or 'нет'}"
            ),
        )
        if llm_result is not None and llm_result.ok and llm_result.text:
            return ChatAgentResult(
                agent_name=self.metadata.name,
                message_type="agent_answer",
                response=llm_result.text,
                source_ref={
                    "collection": "tasks",
                    "provider_kind": llm_result.provider_kind,
                    "model": llm_result.model,
                    "related_task_ids": [
                        item["task_id"] for item in context.related_tasks if "task_id" in item
                    ],
                },
            )

        fallback_parts = [
            f"Контекст задачи: «{context.task_title}», текущий статус `{context.task_status}`.",
            "Базовое описание: " + context.task_content[:280],
        ]
        verdict = validation_result.get("verdict")
        if verdict:
            fallback_parts.append(f"Последний вердикт проверки: `{verdict}`.")
        if issues:
            first_issue = issues[0]
            if isinstance(first_issue, dict) and "message" in first_issue:
                fallback_parts.append("Ключевое замечание проверки: " + str(first_issue["message"]))
        if related_titles:
            fallback_parts.append("Связанные задачи: " + related_titles)
        if llm_result is not None and llm_result.error_message:
            fallback_parts.append("LLM временно недоступна, поэтому ниже краткое резервное резюме.")

        return ChatAgentResult(
            agent_name=self.metadata.name,
            message_type="agent_answer",
            response=" ".join(fallback_parts),
            source_ref={
                "collection": "tasks",
                "related_task_ids": [
                    item["task_id"] for item in context.related_tasks if "task_id" in item
                ],
                "fallback": True,
            },
        )
