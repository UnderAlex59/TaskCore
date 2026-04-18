from __future__ import annotations

import re
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.state import ValidationState
from app.core.validation_settings import normalize_validation_node_settings


class ValidationGraphState(ValidationState, total=False):
    title: str
    content: str
    tags: list[str]
    custom_rules: list[dict[str, object]]
    related_tasks: list[dict[str, object]]
    attachment_names: list[str]
    normalized_title: str
    normalized_content: str
    lower_text: str
    core_issues: list[dict[str, str]]
    core_questions: list[str]
    custom_rule_issues: list[dict[str, str]]
    context_questions: list[str]
    validation_node_settings: dict[str, bool]


def _contains_acceptance_language(text: str) -> bool:
    markers = (
        "должен",
        "should",
        "must",
        "если",
        "when",
        "then",
        "acceptance",
        "критер",
    )
    return any(marker in text for marker in markers)


def _rule_keywords(value: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9_]{5,}", value.lower())}


def _normalize_validation_input(state: ValidationGraphState) -> ValidationGraphState:
    normalized_title = str(state.get("title", "")).strip()
    normalized_content = str(state.get("content", "")).strip()
    return {
        "normalized_title": normalized_title,
        "normalized_content": normalized_content,
        "lower_text": f"{normalized_title}\n{normalized_content}".lower(),
        "validation_node_settings": normalize_validation_node_settings(
            state.get("validation_node_settings")
        ),
    }


def _evaluate_core_rules(state: ValidationGraphState) -> ValidationGraphState:
    if not state.get("validation_node_settings", {}).get("core_rules", True):
        return {"core_issues": [], "core_questions": []}

    normalized_title = str(state.get("normalized_title", ""))
    normalized_content = str(state.get("normalized_content", ""))
    lower_text = str(state.get("lower_text", ""))

    issues: list[dict[str, str]] = []
    questions: list[str] = []

    if len(normalized_title) < 8:
        issues.append(
            {
                "code": "title_too_short",
                "severity": "medium",
                "message": "Название задачи слишком короткое и не фиксирует контекст требования.",
            }
        )

    if len(normalized_content) < 80:
        issues.append(
            {
                "code": "content_too_short",
                "severity": "high",
                "message": (
                    "Описание слишком короткое: не хватает деталей для разработки "
                    "и тестирования."
                ),
            }
        )

    ambiguous_terms = (
        "быстро",
        "удобно",
        "примерно",
        "etc",
        "и т.д.",
        "как обычно",
        "понятно",
    )
    matched_ambiguous = [term for term in ambiguous_terms if term in lower_text]
    if matched_ambiguous:
        issues.append(
            {
                "code": "ambiguous_language",
                "severity": "high",
                "message": "Обнаружены расплывчатые формулировки: " + ", ".join(matched_ambiguous),
            }
        )

    if not _contains_acceptance_language(lower_text):
        questions.append("Добавьте критерии приёмки или условия выполнения требования.")

    return {
        "core_issues": issues,
        "core_questions": questions,
    }


def _evaluate_custom_rules(state: ValidationGraphState) -> ValidationGraphState:
    if not state.get("validation_node_settings", {}).get("custom_rules", True):
        return {"custom_rule_issues": []}

    lower_text = str(state.get("lower_text", ""))
    issues: list[dict[str, str]] = []

    for rule in state.get("custom_rules", []):
        title_value = str(rule.get("title", ""))
        description_value = str(rule.get("description", ""))
        keywords = _rule_keywords(f"{title_value} {description_value}")
        if keywords and not any(keyword in lower_text for keyword in keywords):
            issues.append(
                {
                    "code": f"custom_rule_{title_value.lower().replace(' ', '_')}",
                    "severity": "medium",
                    "message": (
                        f"Требование не отражает правило «{title_value}»: "
                        f"{description_value}"
                    ),
                }
            )

    return {"custom_rule_issues": issues}


def _inspect_context(state: ValidationGraphState) -> ValidationGraphState:
    if not state.get("validation_node_settings", {}).get("context_questions", True):
        return {"context_questions": list(state.get("core_questions", []))}

    lower_text = str(state.get("lower_text", ""))
    questions = list(state.get("core_questions", []))

    if not state.get("tags"):
        questions.append(
            "Укажите хотя бы один тег, чтобы правила проверки и маршрутизация были предсказуемыми."
        )

    if not state.get("attachment_names") and any(
        token in lower_text
        for token in ("макет", "diagram", "ui", "экран", "schema")
    ):
        questions.append(
            "В тексте упомянут визуальный или структурный артефакт. "
            "Можно ли приложить изображение, макет или схему?"
        )

    related_tasks = state.get("related_tasks", [])
    if related_tasks:
        related_titles = ", ".join(
            str(item["title"]) for item in related_tasks[:2] if "title" in item
        )
        questions.append(
            "Найдены похожие задачи. Проверьте, не дублирует ли текущее "
            "требование уже существующую работу: "
            + related_titles
        )

    return {"context_questions": questions}


def _finalize_validation_result(state: ValidationGraphState) -> ValidationGraphState:
    issues = [
        *list(state.get("core_issues", [])),
        *list(state.get("custom_rule_issues", [])),
    ]
    questions = list(state.get("context_questions", []))
    return {
        "issues": issues,
        "questions": questions,
        "verdict": "needs_rework" if issues else "approved",
    }


def _route_after_normalization(state: ValidationGraphState) -> str:
    settings = state.get("validation_node_settings", {})
    if settings.get("core_rules", True):
        return "evaluate_core_rules"
    if settings.get("custom_rules", True):
        return "evaluate_custom_rules"
    if settings.get("context_questions", True):
        return "inspect_context"
    return "finalize_validation_result"


def _route_after_core_rules(state: ValidationGraphState) -> str:
    settings = state.get("validation_node_settings", {})
    if settings.get("custom_rules", True):
        return "evaluate_custom_rules"
    if settings.get("context_questions", True):
        return "inspect_context"
    return "finalize_validation_result"


def _route_after_custom_rules(state: ValidationGraphState) -> str:
    settings = state.get("validation_node_settings", {})
    if settings.get("context_questions", True):
        return "inspect_context"
    return "finalize_validation_result"


@lru_cache
def get_validation_graph():
    graph = StateGraph(ValidationGraphState)
    graph.add_node("normalize_validation_input", _normalize_validation_input)
    graph.add_node("evaluate_core_rules", _evaluate_core_rules)
    graph.add_node("evaluate_custom_rules", _evaluate_custom_rules)
    graph.add_node("inspect_context", _inspect_context)
    graph.add_node("finalize_validation_result", _finalize_validation_result)
    graph.add_edge(START, "normalize_validation_input")
    graph.add_conditional_edges(
        "normalize_validation_input",
        _route_after_normalization,
    )
    graph.add_conditional_edges(
        "evaluate_core_rules",
        _route_after_core_rules,
    )
    graph.add_conditional_edges(
        "evaluate_custom_rules",
        _route_after_custom_rules,
    )
    graph.add_edge("inspect_context", "finalize_validation_result")
    graph.add_edge("finalize_validation_result", END)
    return graph.compile()


async def run_validation_graph(
    *,
    title: str,
    content: str,
    tags: list[str],
    custom_rules: list[dict[str, object]],
    related_tasks: list[dict[str, object]],
    attachment_names: list[str],
    validation_node_settings: dict[str, bool] | None = None,
) -> ValidationState:
    state = await get_validation_graph().ainvoke(
        {
            "title": title,
            "content": content,
            "tags": tags,
            "custom_rules": custom_rules,
            "related_tasks": related_tasks,
            "attachment_names": attachment_names,
            "validation_node_settings": validation_node_settings,
        }
    )
    return {
        "issues": list(state.get("issues", [])),
        "questions": list(state.get("questions", [])),
        "verdict": str(state.get("verdict", "approved")),
    }
