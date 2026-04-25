from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.agents.system_prompts import (
    CHANGE_TRACKER_SYSTEM_PROMPT,
    CHAT_ROUTING_SYSTEM_PROMPT,
    QA_ANSWER_SYSTEM_PROMPT,
    QA_PLANNER_SYSTEM_PROMPT,
    QA_VERIFIER_SYSTEM_PROMPT,
    VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
    VALIDATION_CONTEXT_QUESTIONS_SYSTEM_PROMPT,
    VALIDATION_CORE_PROMPT_KEY,
    VALIDATION_CORE_SYSTEM_PROMPT,
    VALIDATION_CUSTOM_RULES_PROMPT_KEY,
    VALIDATION_CUSTOM_RULES_SYSTEM_PROMPT,
)


@dataclass(frozen=True, slots=True)
class LLMPromptDefinition:
    prompt_key: str
    agent_key: str
    name: str
    description: str
    default_system_prompt: str
    aliases: tuple[str, ...] = ()
    priority: int = 100


@lru_cache
def list_llm_prompt_definitions() -> tuple[LLMPromptDefinition, ...]:
    return (
        LLMPromptDefinition(
            prompt_key="qa-planner",
            agent_key="qa-planner",
            name="QAPlannerAgent",
            description=(
                "Планирует, насколько глубокий анализ нужен для вопроса по задаче "
                "и какой контекст стоит извлекать."
            ),
            default_system_prompt=QA_PLANNER_SYSTEM_PROMPT,
            priority=20,
        ),
        LLMPromptDefinition(
            prompt_key="qa-answer",
            agent_key="qa-answer",
            name="QAAnswerAgent",
            description=(
                "Формирует аналитический ответ по задаче на основе текущего контекста, "
                "валидации и RAG-данных."
            ),
            default_system_prompt=QA_ANSWER_SYSTEM_PROMPT,
            priority=30,
        ),
        LLMPromptDefinition(
            prompt_key="qa-verifier",
            agent_key="qa-verifier",
            name="QAVerifierAgent",
            description=(
                "Проверяет, что аналитический ответ действительно опирается "
                "на доступный контекст и не содержит догадок."
            ),
            default_system_prompt=QA_VERIFIER_SYSTEM_PROMPT,
            priority=40,
        ),
        LLMPromptDefinition(
            prompt_key="change-tracker",
            agent_key="change-tracker",
            name="ChangeTrackerAgent",
            description=(
                "Преобразует запросы из чата в отслеживаемые предложения "
                "по изменению требований."
            ),
            default_system_prompt=CHANGE_TRACKER_SYSTEM_PROMPT,
            aliases=("change", "proposal", "changes"),
            priority=50,
        ),
        LLMPromptDefinition(
            prompt_key="chat-routing",
            agent_key="chat-routing",
            name="ChatRoutingAgent",
            description=(
                "Определяет, относится ли сообщение пользователя к предметному "
                "контексту текущей задачи."
            ),
            default_system_prompt=CHAT_ROUTING_SYSTEM_PROMPT,
            priority=60,
        ),
        LLMPromptDefinition(
            prompt_key=VALIDATION_CORE_PROMPT_KEY,
            agent_key="task-validation",
            name="TaskValidationAgent: базовые правила",
            description=(
                "Проверяет полноту, однозначность, тестируемость и критерии "
                "приёмки требования."
            ),
            default_system_prompt=VALIDATION_CORE_SYSTEM_PROMPT,
            priority=70,
        ),
        LLMPromptDefinition(
            prompt_key=VALIDATION_CUSTOM_RULES_PROMPT_KEY,
            agent_key="task-validation",
            name="TaskValidationAgent: правила проекта",
            description="Сопоставляет требование с пользовательскими правилами проекта.",
            default_system_prompt=VALIDATION_CUSTOM_RULES_SYSTEM_PROMPT,
            priority=80,
        ),
        LLMPromptDefinition(
            prompt_key=VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
            agent_key="task-validation",
            name="TaskValidationAgent: вопросы по контексту",
            description=(
                "Формирует уточняющие вопросы по недостающему контексту, "
                "артефактам и похожим задачам."
            ),
            default_system_prompt=VALIDATION_CONTEXT_QUESTIONS_SYSTEM_PROMPT,
            priority=90,
        ),
    )


def get_llm_prompt_definition(prompt_key: str) -> LLMPromptDefinition | None:
    normalized = prompt_key.casefold()
    for definition in list_llm_prompt_definitions():
        if definition.prompt_key.casefold() == normalized:
            return definition
    return None
