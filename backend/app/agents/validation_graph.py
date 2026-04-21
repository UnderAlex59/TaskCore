from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.state import ValidationState
from app.core.validation_settings import normalize_validation_node_settings
from app.services.llm_runtime_service import LLMRuntimeService
from app.services.qdrant_service import QdrantService

VALIDATION_AGENT_KEY = "task-validation"
VALIDATION_AGENT_NAME = "TaskValidationAgent"
VALIDATION_AGENT_DESCRIPTION = (
    "Проводит LLM-валидацию требований задачи по базовым, кастомным и контекстным правилам."
)
VALIDATION_AGENT_ALIASES: tuple[str, ...] = ()
_ALLOWED_SEVERITIES = {"low", "medium", "high"}


class ValidationGraphState(ValidationState, total=False):
    db: Any
    actor_user_id: str | None
    task_id: str | None
    project_id: str
    title: str
    content: str
    tags: list[str]
    custom_rules: list[dict[str, object]]
    related_tasks: list[dict[str, object]]
    attachment_names: list[str]
    normalized_title: str
    normalized_content: str
    lower_text: str
    validation_node_settings: dict[str, bool]
    rag_questions: list[str]
    core_system_prompt: str
    core_user_prompt: str
    custom_rules_system_prompt: str
    custom_rules_user_prompt: str
    context_system_prompt: str
    context_user_prompt: str
    core_issues: list[dict[str, str]]
    core_questions: list[str]
    custom_rule_issues: list[dict[str, str]]
    context_questions: list[str]


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


def _dedupe_questions(questions: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for question in questions:
        normalized = question.casefold()
        if not question or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(question)
    return deduped


def _normalize_issue_list(candidate: object) -> list[dict[str, str]]:
    if not isinstance(candidate, list):
        return []

    issues: list[dict[str, str]] = []
    for index, item in enumerate(candidate, start=1):
        if isinstance(item, dict):
            message = str(item.get("message", "")).strip()
            code = str(item.get("code", "")).strip() or f"validation_issue_{index}"
            severity = str(item.get("severity", "medium")).strip().lower()
        else:
            message = str(item).strip()
            code = f"validation_issue_{index}"
            severity = "medium"

        if not message:
            continue
        if severity not in _ALLOWED_SEVERITIES:
            severity = "medium"
        issues.append({"code": code, "severity": severity, "message": message})

    return issues


def _normalize_question_list(candidate: object) -> list[str]:
    if not isinstance(candidate, list):
        return []
    return _dedupe_questions([str(item).strip() for item in candidate if str(item).strip()])


def _fallback_core_analysis(state: ValidationGraphState) -> tuple[list[dict[str, str]], list[str]]:
    settings = state.get("validation_node_settings", {})
    if not settings.get("core_rules", True):
        return [], []

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
                "message": "Описание слишком короткое: не хватает деталей для разработки и тестирования.",
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

    return issues, questions


def _fallback_custom_rules_analysis(state: ValidationGraphState) -> list[dict[str, str]]:
    settings = state.get("validation_node_settings", {})
    if not settings.get("custom_rules", True):
        return []

    lower_text = str(state.get("lower_text", ""))
    issues: list[dict[str, str]] = []

    for rule in state.get("custom_rules", []):
        title_value = str(rule.get("title", "")).strip()
        description_value = str(rule.get("description", "")).strip()
        keywords = _rule_keywords(f"{title_value} {description_value}")
        if keywords and not any(keyword in lower_text for keyword in keywords):
            issues.append(
                {
                    "code": f"custom_rule_{title_value.lower().replace(' ', '_') or 'missing'}",
                    "severity": "medium",
                    "message": f"Требование не отражает правило «{title_value}»: {description_value}",
                }
            )

    return issues


def _fallback_context_questions(state: ValidationGraphState) -> list[str]:
    settings = state.get("validation_node_settings", {})
    if not settings.get("context_questions", True):
        return []

    lower_text = str(state.get("lower_text", ""))
    questions: list[str] = []

    if not state.get("tags"):
        questions.append(
            "Укажите хотя бы один тег, чтобы правила проверки и маршрутизация были предсказуемыми."
        )

    if not state.get("attachment_names") and any(
        token in lower_text for token in ("макет", "diagram", "ui", "экран", "schema")
    ):
        questions.append(
            "В тексте упомянут визуальный или структурный артефакт. Можно ли приложить изображение, макет или схему?"
        )

    related_tasks = state.get("related_tasks", [])
    if related_tasks:
        related_titles = ", ".join(
            str(item["title"]) for item in related_tasks[:2] if "title" in item
        )
        questions.append(
            "Найдены похожие задачи. Проверьте, не дублирует ли текущее требование уже существующую работу: "
            + related_titles
        )

    questions.extend(str(question).strip() for question in state.get("rag_questions", []))
    return _dedupe_questions([question for question in questions if question.strip()])


async def _invoke_validation_llm(
    state: ValidationGraphState,
    *,
    system_prompt_key: str,
    user_prompt_key: str,
) -> dict[str, object] | None:
    db = state.get("db")
    if db is None:
        return None

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=VALIDATION_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get(system_prompt_key, "")),
        user_prompt=str(state.get(user_prompt_key, "")),
    )
    if not result.ok or not result.text:
        return None
    return _extract_json_payload(result.text)


def _prepare_core_rules_request(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    return {
        "core_system_prompt": (
            "Ты проверяешь задачу по базовым требованиям качества постановки в духе IEEE. "
            "Оцени полноту, однозначность, тестируемость, наличие критериев приёмки, явных ограничений и пригодность текста к разработке. "
            "Верни строго JSON с ключами issues и questions. "
            "issues — массив объектов с полями code, severity, message. "
            "questions — массив уточняющих вопросов. "
            "Если нарушений нет, верни пустой массив issues. "
            "Не добавляй текст вне JSON."
        ),
        "core_user_prompt": (
            "Настройка core_rules:\n"
            f"{json.dumps({'core_rules': settings.get('core_rules', True)}, ensure_ascii=False)}\n\n"
            "Название задачи:\n"
            f"{state.get('normalized_title', '')}\n\n"
            "Описание задачи:\n"
            f"{state.get('normalized_content', '')}\n\n"
            "Теги:\n"
            f"{json.dumps(list(state.get('tags', [])), ensure_ascii=False)}\n\n"
            "Вложения:\n"
            f"{json.dumps(list(state.get('attachment_names', [])), ensure_ascii=False)}"
        ),
    }


async def _evaluate_core_rules(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("core_rules", True):
        return {"core_issues": [], "core_questions": []}

    payload = await _invoke_validation_llm(
        state,
        system_prompt_key="core_system_prompt",
        user_prompt_key="core_user_prompt",
    )
    if payload is None:
        issues, questions = _fallback_core_analysis(state)
    else:
        issues = _normalize_issue_list(payload.get("issues"))
        questions = _normalize_question_list(payload.get("questions"))

    return {"core_issues": issues, "core_questions": questions}


def _prepare_custom_rules_request(state: ValidationGraphState) -> ValidationGraphState:
    custom_rules = [
        {
            "title": str(rule.get("title", "")).strip(),
            "description": str(rule.get("description", "")).strip(),
            "applies_to_tags": list(rule.get("applies_to_tags", []))
            if isinstance(rule.get("applies_to_tags"), list)
            else [],
        }
        for rule in list(state.get("custom_rules", []))
    ]
    return {
        "custom_rules_system_prompt": (
            "Ты проверяешь, соответствует ли задача пользовательским правилам проекта. "
            "Используй смысловой анализ, а не буквальный поиск отдельных слов. "
            "Верни строго JSON с ключом issues. "
            "issues — массив объектов с полями code, severity, message. "
            "Если нарушений нет, верни пустой массив. "
            "Не добавляй текст вне JSON."
        ),
        "custom_rules_user_prompt": (
            "Название задачи:\n"
            f"{state.get('normalized_title', '')}\n\n"
            "Описание задачи:\n"
            f"{state.get('normalized_content', '')}\n\n"
            "Теги:\n"
            f"{json.dumps(list(state.get('tags', [])), ensure_ascii=False)}\n\n"
            "Правила проекта:\n"
            f"{json.dumps(custom_rules, ensure_ascii=False)}"
        ),
    }


async def _evaluate_custom_rules(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("custom_rules", True):
        return {"custom_rule_issues": []}

    payload = await _invoke_validation_llm(
        state,
        system_prompt_key="custom_rules_system_prompt",
        user_prompt_key="custom_rules_user_prompt",
    )
    issues = (
        _fallback_custom_rules_analysis(state)
        if payload is None
        else _normalize_issue_list(payload.get("issues"))
    )
    return {"custom_rule_issues": issues}


async def _search_project_questions(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("context_questions", True):
        return {"rag_questions": []}

    project_id = str(state.get("project_id", "")).strip()
    if not project_id:
        return {"rag_questions": []}

    documents = await QdrantService.search_project_questions(
        project_id=project_id,
        query_text=f"{state.get('normalized_title', '')}\n{state.get('normalized_content', '')}",
        tags=list(state.get("tags", [])),
        limit=5,
    )
    return {
        "rag_questions": _dedupe_questions(
            [
                str(document.page_content).strip()
                for document in documents
                if document.page_content.strip()
            ]
        )
    }


def _prepare_context_questions_request(state: ValidationGraphState) -> ValidationGraphState:
    related_titles = [
        str(item.get("title", "")).strip()
        for item in list(state.get("related_tasks", []))
        if str(item.get("title", "")).strip()
    ]
    return {
        "context_system_prompt": (
            "Ты формируешь только уточняющие вопросы по задаче. "
            "Не ищи нарушения базовых правил и не выноси вердикт. "
            "Нужно выделить недостающий контекст, важные артефакты, уточнения по зависимостям и вопросы по похожим задачам. "
            "Верни строго JSON с ключом questions, где questions — массив строк. "
            "Не добавляй текст вне JSON."
        ),
        "context_user_prompt": (
            "Название задачи:\n"
            f"{state.get('normalized_title', '')}\n\n"
            "Описание задачи:\n"
            f"{state.get('normalized_content', '')}\n\n"
            "Теги:\n"
            f"{json.dumps(list(state.get('tags', [])), ensure_ascii=False)}\n\n"
            "Вложения:\n"
            f"{json.dumps(list(state.get('attachment_names', [])), ensure_ascii=False)}\n\n"
            "Похожие задачи:\n"
            f"{json.dumps(related_titles, ensure_ascii=False)}\n\n"
            "Исторические вопросы проекта:\n"
            f"{json.dumps(list(state.get('rag_questions', [])), ensure_ascii=False)}"
        ),
    }


async def _inspect_context(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("context_questions", True):
        return {"context_questions": []}

    payload = await _invoke_validation_llm(
        state,
        system_prompt_key="context_system_prompt",
        user_prompt_key="context_user_prompt",
    )
    questions = (
        _fallback_context_questions(state)
        if payload is None
        else _dedupe_questions(
            _normalize_question_list(payload.get("questions"))
            + [str(item).strip() for item in state.get("rag_questions", [])]
        )
    )
    return {"context_questions": questions}


def _route_after_normalization(
    state: ValidationGraphState,
) -> Literal[
    "prepare_core_rules_request",
    "prepare_custom_rules_request",
    "search_project_questions",
    "finalize_validation_result",
]:
    settings = state.get("validation_node_settings", {})
    if not any(settings.get(flag, True) for flag in ("core_rules", "custom_rules", "context_questions")):
        return "finalize_validation_result"
    if settings.get("core_rules", True):
        return "prepare_core_rules_request"
    if settings.get("custom_rules", True):
        return "prepare_custom_rules_request"
    if settings.get("context_questions", True):
        return "search_project_questions"
    return "finalize_validation_result"


def _route_after_core_rules(
    state: ValidationGraphState,
) -> Literal[
    "prepare_custom_rules_request",
    "search_project_questions",
    "finalize_validation_result",
]:
    if list(state.get("core_issues", [])):
        return "finalize_validation_result"

    settings = state.get("validation_node_settings", {})
    if settings.get("custom_rules", True):
        return "prepare_custom_rules_request"
    if settings.get("context_questions", True):
        return "search_project_questions"
    return "finalize_validation_result"


def _route_after_custom_rules(
    state: ValidationGraphState,
) -> Literal["search_project_questions", "finalize_validation_result"]:
    if list(state.get("custom_rule_issues", [])):
        return "finalize_validation_result"

    settings = state.get("validation_node_settings", {})
    if settings.get("context_questions", True):
        return "search_project_questions"
    return "finalize_validation_result"


def _finalize_validation_result(state: ValidationGraphState) -> ValidationGraphState:
    issues = [
        *list(state.get("core_issues", [])),
        *list(state.get("custom_rule_issues", [])),
    ]

    if issues:
        return {
            "issues": issues,
            "questions": list(state.get("core_questions", [])),
            "verdict": "needs_rework",
        }

    return {
        "issues": [],
        "questions": _dedupe_questions(
            [
                *list(state.get("core_questions", [])),
                *list(state.get("context_questions", [])),
            ]
        ),
        "verdict": "approved",
    }


@lru_cache
def get_validation_graph():
    graph = StateGraph(ValidationGraphState)
    graph.add_node("normalize_validation_input", _normalize_validation_input)
    graph.add_node("prepare_core_rules_request", _prepare_core_rules_request)
    graph.add_node("evaluate_core_rules", _evaluate_core_rules)
    graph.add_node("prepare_custom_rules_request", _prepare_custom_rules_request)
    graph.add_node("evaluate_custom_rules", _evaluate_custom_rules)
    graph.add_node("search_project_questions", _search_project_questions)
    graph.add_node("prepare_context_questions_request", _prepare_context_questions_request)
    graph.add_node("inspect_context", _inspect_context)
    graph.add_node("finalize_validation_result", _finalize_validation_result)
    graph.add_edge(START, "normalize_validation_input")
    graph.add_conditional_edges(
        "normalize_validation_input",
        _route_after_normalization,
        {
            "prepare_core_rules_request": "prepare_core_rules_request",
            "prepare_custom_rules_request": "prepare_custom_rules_request",
            "search_project_questions": "search_project_questions",
            "finalize_validation_result": "finalize_validation_result",
        },
    )
    graph.add_edge("prepare_core_rules_request", "evaluate_core_rules")
    graph.add_conditional_edges(
        "evaluate_core_rules",
        _route_after_core_rules,
        {
            "prepare_custom_rules_request": "prepare_custom_rules_request",
            "search_project_questions": "search_project_questions",
            "finalize_validation_result": "finalize_validation_result",
        },
    )
    graph.add_edge("prepare_custom_rules_request", "evaluate_custom_rules")
    graph.add_conditional_edges(
        "evaluate_custom_rules",
        _route_after_custom_rules,
        {
            "search_project_questions": "search_project_questions",
            "finalize_validation_result": "finalize_validation_result",
        },
    )
    graph.add_edge("search_project_questions", "prepare_context_questions_request")
    graph.add_edge("prepare_context_questions_request", "inspect_context")
    graph.add_edge("inspect_context", "finalize_validation_result")
    graph.add_edge("finalize_validation_result", END)
    return graph.compile()


async def run_validation_graph(
    *,
    db: Any | None = None,
    actor_user_id: str | None = None,
    task_id: str | None = None,
    project_id: str,
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
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
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
