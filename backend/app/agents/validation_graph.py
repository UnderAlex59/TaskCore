from __future__ import annotations

import json
import re
from hashlib import sha256
from ast import literal_eval
from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.state import ValidationState
from app.agents.system_prompts import (
    VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
    VALIDATION_CONTEXT_QUESTIONS_SYSTEM_PROMPT,
    VALIDATION_CORE_PROMPT_KEY,
    VALIDATION_CORE_SYSTEM_PROMPT,
    VALIDATION_CUSTOM_RULES_PROMPT_KEY,
    VALIDATION_CUSTOM_RULES_SYSTEM_PROMPT,
)
from app.core.validation_settings import normalize_validation_node_settings
from app.services.graph_run_tracing import (
    get_current_graph_run_id,
    run_traced_graph,
    traced_condition,
    traced_node,
)
from app.services.llm_runtime_service import LLMRuntimeService
from app.services.qdrant_service import QdrantService

VALIDATION_AGENT_KEY = "task-validation"
VALIDATION_AGENT_NAME = "TaskValidationAgent"
VALIDATION_AGENT_DESCRIPTION = (
    "Проводит LLM-валидацию требований задачи по базовым, кастомным и контекстным правилам."
)
VALIDATION_AGENT_ALIASES: tuple[str, ...] = ()
_ALLOWED_SEVERITIES = {"low", "medium", "high"}
_VALIDATION_SOURCES = {"core_rules", "custom_rules", "context_questions"}
_TASK_SECTION_HEADING_PATTERN = re.compile(
    (
        r"^##\s+"
        r"(Описание|Бизнес-правила|Acceptance criteria|Материалы|История изменений)"
        r"\s*$"
    ),
    re.MULTILINE,
)


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
    historical_questions_override: list[str] | None
    prompt_overrides: dict[str, str]
    provider_config_id: str | None
    llm_diagnostics: list[dict[str, object]]
    graph_run_id: str | None
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
    normalized_content = _strip_empty_task_sections(str(state.get("content", "")))
    return {
        "normalized_title": normalized_title,
        "normalized_content": normalized_content,
        "lower_text": f"{normalized_title}\n{normalized_content}".lower(),
        "validation_node_settings": normalize_validation_node_settings(
            state.get("validation_node_settings")
        ),
    }


def _strip_empty_task_sections(content: str) -> str:
    normalized_content = content.strip()
    matches = list(_TASK_SECTION_HEADING_PATTERN.finditer(normalized_content))
    if not matches:
        return normalized_content

    parts: list[str] = []
    prefix = normalized_content[: matches[0].start()].strip()
    if prefix:
        parts.append(prefix)

    for index, current_match in enumerate(matches):
        next_match = matches[index + 1] if index + 1 < len(matches) else None
        section_end = next_match.start() if next_match else len(normalized_content)
        section_body = normalized_content[
            current_match.end() : section_end
        ].strip()
        if section_body:
            parts.append(f"## {current_match.group(1)}\n{section_body}")

    return "\n\n".join(parts).strip()


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


def _finding_id(*, source: str, code: str, message: str) -> str:
    normalized = "\n".join(
        (
            source.strip().casefold(),
            code.strip().casefold(),
            re.sub(r"\s+", " ", message.strip()).casefold(),
        )
    )
    return sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _normalize_blocking_issues(
    issues: list[dict[str, str]],
    *,
    source: str,
) -> list[dict[str, str]]:
    normalized_source = source if source in _VALIDATION_SOURCES else "core_rules"
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(issues, start=1):
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        code = str(item.get("code", "")).strip() or f"{normalized_source}_{index}"
        severity = str(item.get("severity", "medium")).strip().lower()
        if severity not in _ALLOWED_SEVERITIES:
            severity = "medium"
        normalized.append(
            {
                "finding_id": _finding_id(
                    source=normalized_source,
                    code=code,
                    message=message,
                ),
                "source": normalized_source,
                "code": code,
                "severity": severity,
                "message": message,
            }
        )
    return normalized


def _context_questions_to_issues(questions: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for question in questions:
        message = question.strip()
        if not message:
            continue
        issues.append(
            {
                "code": "context_question",
                "severity": "medium",
                "message": message,
            }
        )
    return _normalize_blocking_issues(issues, source="context_questions")


def _normalize_question_list(candidate: object) -> list[str]:
    if not isinstance(candidate, list):
        return []

    questions: list[str] = []
    for item in candidate:
        question = _normalize_question_item(item)
        if question:
            questions.append(question)
    return _dedupe_questions(questions)


def _canonical_question_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _select_canonical_context_questions(
    candidate_questions: object,
    canonical_questions: object,
) -> list[str]:
    normalized_canonical = _normalize_question_list(canonical_questions)
    canonical_by_key = {
        _canonical_question_key(question): question for question in normalized_canonical
    }
    selected: list[str] = []
    for candidate in _normalize_question_list(candidate_questions):
        canonical = canonical_by_key.get(_canonical_question_key(candidate))
        if canonical:
            selected.append(canonical)
    return _dedupe_questions(selected)


def _normalize_question_item(item: object) -> str:
    if isinstance(item, dict):
        for key in ("message", "question", "text", "content"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    if not isinstance(item, str):
        return str(item).strip()

    value = item.strip()
    if not value:
        return ""

    if value.startswith("{") and value.endswith("}"):
        for parser in (json.loads, literal_eval):
            try:
                parsed = parser(value)
            except (SyntaxError, ValueError, TypeError, json.JSONDecodeError):
                continue
            normalized = _normalize_question_item(parsed)
            if normalized:
                return normalized

    return value


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

    return _normalize_question_list(state.get("rag_questions", []))


async def _invoke_validation_llm(
    state: ValidationGraphState,
    *,
    prompt_key: str,
    system_prompt_key: str,
    user_prompt_key: str,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    db = state.get("db")
    metadata: dict[str, object] = {
        "prompt_key": prompt_key,
        "ok": False,
        "used_fallback": False,
        "parse_error": None,
        "error_message": None,
    }
    if db is None:
        metadata["error_message"] = "LLM runtime skipped: no database session."
        return None, metadata

    prompt_overrides = state.get("prompt_overrides", {})
    system_prompt_override = (
        prompt_overrides.get(prompt_key) if isinstance(prompt_overrides, dict) else None
    )
    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=VALIDATION_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get(system_prompt_key, "")),
        user_prompt=str(state.get(user_prompt_key, "")),
        prompt_key=prompt_key,
        provider_config_id=state.get("provider_config_id"),
        system_prompt_override=system_prompt_override,
    )
    metadata.update(
        {
            "ok": bool(result.ok),
            "provider_config_id": result.provider_config_id,
            "provider_kind": result.provider_kind,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "estimated_cost_usd": float(result.estimated_cost_usd)
            if result.estimated_cost_usd is not None
            else None,
            "error_message": result.error_message,
            "system_prompt_overridden": system_prompt_override is not None,
        }
    )
    if not result.ok or not result.text:
        metadata["used_fallback"] = True
        return None, metadata
    payload = _extract_json_payload(result.text)
    if payload is None:
        metadata["parse_error"] = "invalid_json"
        metadata["used_fallback"] = True
    return payload, metadata


def _prepare_core_rules_request(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    return {
        "core_system_prompt": VALIDATION_CORE_SYSTEM_PROMPT,
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

    payload, metadata = await _invoke_validation_llm(
        state,
        prompt_key=VALIDATION_CORE_PROMPT_KEY,
        system_prompt_key="core_system_prompt",
        user_prompt_key="core_user_prompt",
    )
    if payload is None:
        issues, questions = _fallback_core_analysis(state)
    else:
        issues = _normalize_issue_list(payload.get("issues"))
        questions = _normalize_question_list(payload.get("questions"))

    return {
        "core_issues": issues,
        "core_questions": questions,
        "llm_diagnostics": [*list(state.get("llm_diagnostics", [])), metadata],
    }


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
        "custom_rules_system_prompt": VALIDATION_CUSTOM_RULES_SYSTEM_PROMPT,
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

    payload, metadata = await _invoke_validation_llm(
        state,
        prompt_key=VALIDATION_CUSTOM_RULES_PROMPT_KEY,
        system_prompt_key="custom_rules_system_prompt",
        user_prompt_key="custom_rules_user_prompt",
    )
    issues = (
        _fallback_custom_rules_analysis(state)
        if payload is None
        else _normalize_issue_list(payload.get("issues"))
    )
    return {
        "custom_rule_issues": issues,
        "llm_diagnostics": [*list(state.get("llm_diagnostics", [])), metadata],
    }


async def _search_project_questions(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("context_questions", True):
        return {"rag_questions": []}

    if "historical_questions_override" in state:
        return {
            "rag_questions": _normalize_question_list(
                state.get("historical_questions_override") or []
            )
        }

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
        "rag_questions": _normalize_question_list(
            [
                document.page_content
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
        "context_system_prompt": VALIDATION_CONTEXT_QUESTIONS_SYSTEM_PROMPT,
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
            "Исторические вопросы проекта "
            "(выбирай только точные строки из этого списка):\n"
            f"{json.dumps(list(state.get('rag_questions', [])), ensure_ascii=False)}"
        ),
    }


async def _inspect_context(state: ValidationGraphState) -> ValidationGraphState:
    settings = state.get("validation_node_settings", {})
    if not settings.get("context_questions", True):
        return {"context_questions": []}

    payload, metadata = await _invoke_validation_llm(
        state,
        prompt_key=VALIDATION_CONTEXT_QUESTIONS_PROMPT_KEY,
        system_prompt_key="context_system_prompt",
        user_prompt_key="context_user_prompt",
    )
    questions = _fallback_context_questions(state)
    if payload is not None:
        questions = _select_canonical_context_questions(
            payload.get("questions"),
            state.get("rag_questions", []),
        )
    return {
        "context_questions": questions,
        "llm_diagnostics": [*list(state.get("llm_diagnostics", [])), metadata],
    }


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
        *_normalize_blocking_issues(list(state.get("core_issues", [])), source="core_rules"),
        *_normalize_blocking_issues(
            list(state.get("custom_rule_issues", [])),
            source="custom_rules",
        ),
        *_context_questions_to_issues(list(state.get("context_questions", []))),
    ]

    if issues:
        return {
            "issues": issues,
            "questions": list(state.get("core_questions", [])),
            "verdict": "needs_rework",
            "graph_run_id": get_current_graph_run_id(),
        }

    return {
        "issues": [],
        "questions": _dedupe_questions(list(state.get("core_questions", []))),
        "verdict": "approved",
        "graph_run_id": get_current_graph_run_id(),
    }


@lru_cache
def get_validation_graph():
    graph = StateGraph(ValidationGraphState)
    graph.add_node("normalize_validation_input", traced_node("normalize_validation_input", _normalize_validation_input))
    graph.add_node("prepare_core_rules_request", traced_node("prepare_core_rules_request", _prepare_core_rules_request))
    graph.add_node("evaluate_core_rules", traced_node("evaluate_core_rules", _evaluate_core_rules))
    graph.add_node("prepare_custom_rules_request", traced_node("prepare_custom_rules_request", _prepare_custom_rules_request))
    graph.add_node("evaluate_custom_rules", traced_node("evaluate_custom_rules", _evaluate_custom_rules))
    graph.add_node("search_project_questions", traced_node("search_project_questions", _search_project_questions))
    graph.add_node("prepare_context_questions_request", traced_node("prepare_context_questions_request", _prepare_context_questions_request))
    graph.add_node("inspect_context", traced_node("inspect_context", _inspect_context))
    graph.add_node("finalize_validation_result", traced_node("finalize_validation_result", _finalize_validation_result))
    graph.add_edge(START, "normalize_validation_input")
    graph.add_conditional_edges(
        "normalize_validation_input",
        traced_condition(
            "route_after_normalization",
            "normalize_validation_input",
            {
                "prepare_core_rules_request": "prepare_core_rules_request",
                "prepare_custom_rules_request": "prepare_custom_rules_request",
                "search_project_questions": "search_project_questions",
                "finalize_validation_result": "finalize_validation_result",
            },
            _route_after_normalization,
        ),
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
        traced_condition(
            "route_after_core_rules",
            "evaluate_core_rules",
            {
                "prepare_custom_rules_request": "prepare_custom_rules_request",
                "search_project_questions": "search_project_questions",
                "finalize_validation_result": "finalize_validation_result",
            },
            _route_after_core_rules,
        ),
        {
            "prepare_custom_rules_request": "prepare_custom_rules_request",
            "search_project_questions": "search_project_questions",
            "finalize_validation_result": "finalize_validation_result",
        },
    )
    graph.add_edge("prepare_custom_rules_request", "evaluate_custom_rules")
    graph.add_conditional_edges(
        "evaluate_custom_rules",
        traced_condition(
            "route_after_custom_rules",
            "evaluate_custom_rules",
            {
                "search_project_questions": "search_project_questions",
                "finalize_validation_result": "finalize_validation_result",
            },
            _route_after_custom_rules,
        ),
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
    state = await run_traced_graph(
        graph_key="validation_graph",
        graph=get_validation_graph(),
        source="task_validation",
        input_state=
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
        "graph_run_id": state.get("graph_run_id"),
        "llm_diagnostics": list(state.get("llm_diagnostics", [])),
        "core_issues": list(state.get("core_issues", [])),
        "core_questions": list(state.get("core_questions", [])),
        "custom_rule_issues": list(state.get("custom_rule_issues", [])),
        "context_questions": list(state.get("context_questions", [])),
        "rag_questions": list(state.get("rag_questions", [])),
    }


async def run_validation_eval_graph(
    *,
    db: Any,
    actor_user_id: str | None = None,
    project_id: str,
    title: str,
    content: str,
    tags: list[str],
    custom_rules: list[dict[str, object]],
    related_tasks: list[dict[str, object]],
    attachment_names: list[str],
    historical_questions: list[str] | None = None,
    validation_node_settings: dict[str, bool] | None = None,
    provider_config_id: str | None = None,
    prompt_overrides: dict[str, str] | None = None,
) -> ValidationGraphState:
    state = await run_traced_graph(
        graph_key="validation_graph",
        graph=get_validation_graph(),
        source="validation_eval",
        force_trace=True,
        input_state={
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": None,
            "project_id": project_id,
            "title": title,
            "content": content,
            "tags": tags,
            "custom_rules": custom_rules,
            "related_tasks": related_tasks,
            "attachment_names": attachment_names,
            "historical_questions_override": historical_questions or [],
            "validation_node_settings": validation_node_settings,
            "provider_config_id": provider_config_id,
            "prompt_overrides": prompt_overrides or {},
            "llm_diagnostics": [],
        },
    )
    return {
        "issues": list(state.get("issues", [])),
        "questions": list(state.get("questions", [])),
        "verdict": str(state.get("verdict", "approved")),
        "graph_run_id": state.get("graph_run_id"),
        "llm_diagnostics": list(state.get("llm_diagnostics", [])),
        "core_issues": list(state.get("core_issues", [])),
        "core_questions": list(state.get("core_questions", [])),
        "custom_rule_issues": list(state.get("custom_rule_issues", [])),
        "context_questions": list(state.get("context_questions", [])),
        "rag_questions": list(state.get("rag_questions", [])),
    }
