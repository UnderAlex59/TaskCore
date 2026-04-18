from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.services.llm_runtime_service import LLMRuntimeService

QA_AGENT_KEY = "qa"
QA_AGENT_NAME = "QAAgent"
QA_AGENT_DESCRIPTION = (
    "Отвечает на вопросы по требованиям с учётом контекста задачи и последней проверки."
)
QA_AGENT_ALIASES = ("question", "analyst", "qaagent", "qa-agent")

_LOW_CONFIDENCE_MARKERS = (
    "недостаточно",
    "не хватает",
    "не могу подтвердить",
    "не могу ответить",
    "неизвестно",
    "нет данных",
    "нужно уточнить",
    "не указано",
    "не описано",
)
_BACKLOG_NOTICE = "Вопрос сохранён в базе вопросов для последующей валидации задачи."


class QAAgentGraphState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    task_id: str | None
    project_id: str | None
    task_title: str
    task_status: str
    task_content: str
    message_content: str
    validation_result: dict | None
    related_tasks: list[dict[str, object]]
    routing_mode: str
    related_titles: str
    issues: list[object]
    questions: list[object]
    system_prompt: str
    user_prompt: str
    llm_payload: dict[str, object] | None
    llm_ok: bool
    llm_error_message: str | None
    provider_kind: str | None
    model: str | None


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


def _normalize_confidence(value: object, fallback_text: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"high", "low"}:
        return normalized

    lowered = fallback_text.lower()
    if any(marker in lowered for marker in _LOW_CONFIDENCE_MARKERS):
        return "low"
    return "high"


def _normalize_validation_question(candidate: object, *, fallback_question: str) -> str:
    question = str(candidate or "").strip() or fallback_question.strip()
    if not question.endswith("?"):
        question = f"{question}?"
    return question


def _append_backlog_notice(response: str) -> str:
    if _BACKLOG_NOTICE.casefold() in response.casefold():
        return response
    separator = "" if response.endswith((".", "!", "?")) else "."
    return f"{response}{separator} {_BACKLOG_NOTICE}".strip()


def _prepare_qa_request(state: QAAgentGraphState) -> QAAgentGraphState:
    validation_result = state.get("validation_result") or {}
    related_titles = ", ".join(
        str(item["title"])
        for item in list(state.get("related_tasks", []))[:3]
        if "title" in item
    )
    issues = list(validation_result.get("issues", []))
    questions = list(validation_result.get("questions", []))
    return {
        "related_titles": related_titles,
        "issues": issues,
        "questions": questions,
        "system_prompt": (
            "Ты опытный продуктовый аналитик. "
            "Отвечай на вопрос пользователя только на русском языке, "
            "используя контекст задачи, результаты последней проверки и связанные задачи. "
            "Не придумывай факты. "
            "Верни строгий JSON с ключами answer, confidence, canonical_question. "
            "confidence должен быть high только если "
            "в текущем контексте есть надёжный ответ без догадок; "
            "иначе верни low. "
            "Если confidence=low, в answer прямо укажи, каких данных не хватает, "
            "а в canonical_question дай краткую каноническую формулировку вопроса "
            "для базы валидации. "
            "Если confidence=high, canonical_question верни null."
        ),
        "user_prompt": (
            f"Название задачи: {state.get('task_title', '')}\n"
            f"Статус задачи: {state.get('task_status', '')}\n"
            f"Описание задачи:\n{state.get('task_content', '')}\n\n"
            f"Вопрос пользователя:\n{state.get('message_content', '')}\n\n"
            f"Вердикт проверки: {validation_result.get('verdict', 'нет')}\n"
            f"Замечания проверки: {issues}\n"
            f"Открытые вопросы проверки: {questions}\n"
            f"Связанные задачи: {related_titles or 'нет'}"
        ),
    }


async def _invoke_qa_llm(state: QAAgentGraphState) -> QAAgentGraphState:
    db = state.get("db")
    if db is None:
        return {
            "llm_ok": False,
            "llm_error_message": None,
            "provider_kind": None,
            "model": None,
            "llm_payload": None,
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=QA_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get("system_prompt", "")),
        user_prompt=str(state.get("user_prompt", "")),
    )
    return {
        "llm_ok": bool(result.ok),
        "llm_error_message": result.error_message,
        "provider_kind": result.provider_kind,
        "model": result.model,
        "llm_payload": (
            _extract_json_payload(result.text or "")
            if result.ok and result.text
            else None
        ),
        "response": result.text or "",
    }


def _build_fallback_response(state: QAAgentGraphState) -> tuple[str, str]:
    validation_result = state.get("validation_result") or {}
    fallback_parts = [
        (
            f"Контекст задачи: «{state.get('task_title', '')}», "
            f"текущий статус `{state.get('task_status', '')}`."
        ),
        "Базовое описание: " + str(state.get("task_content", ""))[:280],
    ]
    verdict = validation_result.get("verdict")
    if verdict:
        fallback_parts.append(f"Последний вердикт проверки: `{verdict}`.")
    issues = list(state.get("issues", []))
    if issues:
        first_issue = issues[0]
        if isinstance(first_issue, dict) and "message" in first_issue:
            fallback_parts.append("Ключевое замечание проверки: " + str(first_issue["message"]))
    related_titles = str(state.get("related_titles", ""))
    if related_titles:
        fallback_parts.append("Связанные задачи: " + related_titles)
    if state.get("llm_error_message"):
        fallback_parts.append(
            "LLM временно недоступна, поэтому ниже краткое резервное резюме."
        )
    return (
        " ".join(fallback_parts),
        _normalize_validation_question(
            None,
            fallback_question=str(state.get("message_content", "")),
        ),
    )


def _finalize_qa_response(state: QAAgentGraphState) -> QAAgentGraphState:
    raw_response = str(state.get("response", "")).strip()
    payload = state.get("llm_payload")
    response = raw_response
    confidence = _normalize_confidence(None, response)
    validation_backlog_question: str | None = None

    if state.get("llm_ok") and payload is not None:
        response = str(payload.get("answer") or response).strip()
        confidence = _normalize_confidence(payload.get("confidence"), response)
        if confidence == "low":
            validation_backlog_question = _normalize_validation_question(
                payload.get("canonical_question"),
                fallback_question=str(state.get("message_content", "")),
            )
    elif not state.get("llm_ok"):
        response, validation_backlog_question = _build_fallback_response(state)
        confidence = "low"

    if confidence == "low":
        response = _append_backlog_notice(response)

    return {
        "agent_name": QA_AGENT_NAME,
        "message_type": "agent_answer",
        "response": response,
        "source_ref": {
            "collection": "tasks",
            "provider_kind": state.get("provider_kind"),
            "model": state.get("model"),
            "answer_confidence": confidence,
            "validation_backlog_question": validation_backlog_question,
            "related_task_ids": [
                item["task_id"]
                for item in list(state.get("related_tasks", []))
                if "task_id" in item
            ],
            "agent_key": QA_AGENT_KEY,
            "agent_description": QA_AGENT_DESCRIPTION,
            "routing_mode": str(state.get("routing_mode", "auto")),
        },
    }


@lru_cache
def get_qa_agent_graph():
    graph = StateGraph(QAAgentGraphState)
    graph.add_node("prepare_qa_request", _prepare_qa_request)
    graph.add_node("invoke_qa_llm", _invoke_qa_llm)
    graph.add_node("finalize_qa_response", _finalize_qa_response)
    graph.add_edge(START, "prepare_qa_request")
    graph.add_edge("prepare_qa_request", "invoke_qa_llm")
    graph.add_edge("invoke_qa_llm", "finalize_qa_response")
    graph.add_edge("finalize_qa_response", END)
    return graph.compile()


async def run_qa_agent_graph(
    *,
    db,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    message_content: str,
    validation_result: dict | None,
    related_tasks: list[dict[str, object]],
    routing_mode: str,
) -> ChatState:
    state = await get_qa_agent_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "message_content": message_content,
            "validation_result": validation_result,
            "related_tasks": related_tasks,
            "routing_mode": routing_mode,
        }
    )
    return {
        "agent_name": str(state.get("agent_name", QA_AGENT_NAME)),
        "message_type": str(state.get("message_type", "agent_answer")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
    }
