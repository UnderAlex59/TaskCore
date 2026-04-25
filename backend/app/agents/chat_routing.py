from __future__ import annotations

import json
import re

from app.agents.system_prompts import CHAT_ROUTING_SYSTEM_PROMPT

_TASK_CONTEXT_HINTS = (
    "задач",
    "требован",
    "контекс",
    "критер",
    "валид",
    "измен",
    "доработ",
    "реализ",
    "провер",
    "статус",
    "api",
    "ui",
    "schema",
    "integration",
)
_STRONG_TASK_CONTEXT_HINTS = (
    "критер",
    "валид",
    "измен",
    "доработ",
    "реализ",
    "провер",
    "статус",
    "api",
    "ui",
    "schema",
    "integration",
)
_TEAM_COORDINATION_HINTS = (
    "настроен",
    "как настроение",
    "как дела",
    "готов",
    "гтов",
    "поработ",
    "в работу",
    "стартуем",
    "созвон",
    "на связи",
)
_TASK_CONTEXT_STOPWORDS = {
    "когда",
    "почему",
    "зачем",
    "какой",
    "какая",
    "какие",
    "можно",
    "нужно",
    "будет",
    "после",
    "сегодня",
    "завтра",
    "просто",
    "вообще",
    "please",
    "could",
    "would",
    "about",
    "there",
    "which",
}

CHAT_ROUTING_AGENT_KEY = "chat-routing"
CHAT_ROUTING_AGENT_NAME = "ChatRoutingAgent"
CHAT_ROUTING_AGENT_DESCRIPTION = (
    "Определяет, относится ли сообщение пользователя к предметному контексту текущей задачи."
)
CHAT_ROUTING_AGENT_ALIASES: tuple[str, ...] = ()


def extract_keywords(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9_]{4,}", value.lower())
        if token not in _TASK_CONTEXT_STOPWORDS
    }


def message_relates_to_task_context(
    *,
    task_title: str,
    task_content: str,
    message_content: str,
) -> bool:
    lowered_message = message_content.lower()
    task_keywords = extract_keywords("\n".join((task_title, task_content)))
    message_keywords = extract_keywords(lowered_message)
    has_keyword_overlap = bool(task_keywords.intersection(message_keywords))
    has_strong_task_hint = any(
        marker in lowered_message for marker in _STRONG_TASK_CONTEXT_HINTS
    )
    has_task_context_hint = any(marker in lowered_message for marker in _TASK_CONTEXT_HINTS)
    has_team_coordination_hint = any(
        marker in lowered_message for marker in _TEAM_COORDINATION_HINTS
    )

    if has_team_coordination_hint and not has_keyword_overlap and not has_strong_task_hint:
        return False
    if has_keyword_overlap or has_strong_task_hint:
        return True
    return has_task_context_hint and has_keyword_overlap


def _extract_json_payload(raw_text: str) -> dict[str, object] | None:
    text = raw_text.strip()
    if not text:
        return None

    candidates = [text]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is not None:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_task_related(candidate: object, *, fallback: bool) -> bool:
    if isinstance(candidate, bool):
        return candidate
    normalized = str(candidate).strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    return fallback


async def analyze_task_context_relevance(
    *,
    db,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    task_title: str,
    task_content: str,
    message_content: str,
) -> bool:
    fallback = message_relates_to_task_context(
        task_title=task_title,
        task_content=task_content,
        message_content=message_content,
    )
    if db is None:
        return fallback

    from app.services.llm_runtime_service import LLMRuntimeService

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=CHAT_ROUTING_AGENT_KEY,
        actor_user_id=actor_user_id,
        task_id=task_id,
        project_id=project_id,
        system_prompt=CHAT_ROUTING_SYSTEM_PROMPT,
        user_prompt=(
            "Название задачи:\n"
            f"{task_title.strip()}\n\n"
            "Описание задачи:\n"
            f"{task_content.strip()}\n\n"
            "Сообщение пользователя:\n"
            f"{message_content.strip()}"
        ),
        prompt_key=CHAT_ROUTING_AGENT_KEY,
    )
    payload = _extract_json_payload(result.text or "") if result.ok and result.text else None
    if payload is None:
        return fallback
    return _normalize_task_related(payload.get("task_related"), fallback=fallback)
