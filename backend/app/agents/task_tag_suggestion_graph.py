from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.task import TaskTagSuggestionItem, TaskTagSuggestionResponse
from app.services.llm_runtime_service import LLMRuntimeService

TASK_TAG_SUGGESTER_AGENT_KEY = "task_tag_suggester"
TASK_TAG_SUGGESTER_AGENT_NAME = "TaskTagSuggester"
TASK_TAG_SUGGESTER_AGENT_DESCRIPTION = (
    "Подбирает до 5 наиболее подходящих тегов задачи из справочника проекта."
)
TASK_TAG_SUGGESTER_AGENT_ALIASES = ("task-tags", "tag-suggester")


class TaskTagSuggestionState(TypedDict, total=False):
    db: AsyncSession
    actor_user_id: str
    project_id: str
    task_id: str
    title: str
    content: str
    current_tags: list[str]
    available_tags: list[str]
    system_prompt: str
    user_prompt: str
    llm_text: str
    suggestions: list[dict[str, str | float]]


def _build_prompts(state: TaskTagSuggestionState) -> TaskTagSuggestionState:
    available_tags = state.get("available_tags", [])
    current_tags = state.get("current_tags", [])
    title = str(state.get("title", "")).strip()
    content = str(state.get("content", "")).strip()

    return {
        "system_prompt": (
            "Ты подбираешь теги задачи из проектного справочника. "
            "Выбирай только теги из переданного списка. "
            "Предлагай только теги, которые подходят задаче минимум на 0.80. "
            "Максимум 5 тегов. "
            "Не придумывай новые теги, не переименовывай их и не добавляй теги с низкой уверенностью. "
            'Верни строго JSON вида {"suggestions":[{"tag":"...", "confidence":0.87, "reason":"..."}]}.'
        ),
        "user_prompt": (
            "Справочник тегов проекта:\n"
            + "\n".join(f"- {tag}" for tag in available_tags)
            + "\n\n"
            + f"Уже выбранные теги: {', '.join(current_tags) if current_tags else 'нет'}\n\n"
            + f"Название задачи:\n{title}\n\n"
            + f"Текст задачи:\n{content or 'нет текста'}"
        ),
    }


async def _invoke_llm(state: TaskTagSuggestionState) -> TaskTagSuggestionState:
    db = state["db"]
    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=TASK_TAG_SUGGESTER_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get("system_prompt", "")),
        user_prompt=str(state.get("user_prompt", "")),
        prompt_key=TASK_TAG_SUGGESTER_AGENT_KEY,
    )
    if not result.ok or not result.text:
        raise RuntimeError(result.error_message or "Не удалось получить рекомендации по тегам от LLM.")
    return {"llm_text": result.text}


def _parse_suggestions(state: TaskTagSuggestionState) -> TaskTagSuggestionState:
    available_tags = set(state.get("available_tags", []))
    parsed = json.loads(str(state.get("llm_text", "")).strip())
    raw_suggestions = parsed.get("suggestions", []) if isinstance(parsed, dict) else []

    suggestions: list[dict[str, str | float]] = []
    seen_tags: set[str] = set()
    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue

        tag = str(item.get("tag", "")).strip()
        if not tag or tag not in available_tags or tag in seen_tags:
            continue

        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            continue

        reason = str(item.get("reason", "")).strip()
        if confidence < 0.8 or not reason:
            continue

        seen_tags.add(tag)
        suggestions.append(
            {
                "tag": tag,
                "confidence": min(confidence, 1.0),
                "reason": reason[:300],
            }
        )
        if len(suggestions) >= 5:
            break

    return {"suggestions": suggestions}


@lru_cache
def get_task_tag_suggestion_graph():
    graph = StateGraph(TaskTagSuggestionState)
    graph.add_node("build_prompts", _build_prompts)
    graph.add_node("invoke_llm", _invoke_llm)
    graph.add_node("parse_suggestions", _parse_suggestions)
    graph.add_edge(START, "build_prompts")
    graph.add_edge("build_prompts", "invoke_llm")
    graph.add_edge("invoke_llm", "parse_suggestions")
    graph.add_edge("parse_suggestions", END)
    return graph.compile()


async def run_task_tag_suggestion_graph(
    *,
    db: AsyncSession,
    actor_user_id: str,
    project_id: str,
    task_id: str,
    title: str,
    content: str,
    current_tags: list[str],
    available_tags: list[str],
) -> TaskTagSuggestionResponse:
    state = await get_task_tag_suggestion_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "project_id": project_id,
            "task_id": task_id,
            "title": title,
            "content": content,
            "current_tags": current_tags,
            "available_tags": available_tags,
        }
    )
    return TaskTagSuggestionResponse(
        suggestions=[
            TaskTagSuggestionItem.model_validate(item)
            for item in state.get("suggestions", [])
        ],
        generated_at=datetime.now(UTC),
    )
