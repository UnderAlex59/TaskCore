from __future__ import annotations

import re

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
