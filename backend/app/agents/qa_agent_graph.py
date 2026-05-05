from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Literal

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.agents.system_prompts import (
    QA_ANSWER_SYSTEM_PROMPT,
    QA_VERIFIER_SYSTEM_PROMPT,
)
from app.services.llm_runtime_service import LLMRuntimeService
from app.services.qdrant_service import QdrantService

QA_AGENT_KEY = "qa"
QA_AGENT_NAME = "QAAgent"
QA_AGENT_DESCRIPTION = (
    "Отвечает на вопросы по требованиям с учётом контекста задачи, Qdrant RAG и последней проверки."
)
QA_AGENT_ALIASES = ("question", "analyst", "qaagent", "qa-agent")

QA_ANSWER_AGENT_KEY = "qa-answer"
QA_ANSWER_AGENT_NAME = "QAAnswerAgent"
QA_ANSWER_AGENT_DESCRIPTION = (
    "Формирует аналитический ответ по задаче на основе текущего контекста, валидации и RAG-данных."
)
QA_ANSWER_AGENT_ALIASES: tuple[str, ...] = ()

QA_VERIFIER_AGENT_KEY = "qa-verifier"
QA_VERIFIER_AGENT_NAME = "QAVerifierAgent"
QA_VERIFIER_AGENT_DESCRIPTION = (
    "Проверяет, что аналитический ответ опирается на доступный контекст без догадок."
)
QA_VERIFIER_AGENT_ALIASES: tuple[str, ...] = ()

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
_ATTACHMENT_SOURCE_TYPES = {"attachment_text", "attachment_image_alt_text"}
_FIXED_ANALYSIS_MODE = "deep"
_FIXED_NEEDS_RAG = True
_FIXED_NEEDS_VERIFICATION = True
_FIXED_RETRIEVAL_LIMIT = 5


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
    analysis_mode: str
    needs_rag: bool
    needs_verification: bool
    retrieval_query: str
    retrieval_limit: int
    focus_points: list[str]
    canonical_question_hint: str | None
    rag_snippets: list[str]
    rag_chunk_ids: list[str]
    attachment_filenames: list[str]
    cross_task_snippets: list[str]
    cross_task_chunk_ids: list[str]
    cross_task_ids: list[str]
    cross_task_sources: list[dict[str, str]]
    rag_context_scope: str
    answer_system_prompt: str
    answer_user_prompt: str
    answer_payload: dict[str, object] | None
    answer_ok: bool
    answer_error_message: str | None
    answer_provider_kind: str | None
    answer_model: str | None
    response: str
    verify_system_prompt: str
    verify_user_prompt: str
    verify_payload: dict[str, object] | None
    verify_ok: bool
    verify_error_message: str | None
    verify_provider_kind: str | None
    verify_model: str | None


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


def _build_llm_stage_ref(
    *,
    provider_kind: str | None,
    model: str | None,
    ok: bool,
) -> dict[str, object]:
    return {
        "provider_kind": provider_kind,
        "model": model,
        "ok": ok,
    }


def _is_attachment_document(document: Document) -> bool:
    metadata = document.metadata or {}
    source_type = str(metadata.get("source_type") or "").strip()
    chunk_kind = str(metadata.get("chunk_kind") or "").strip()
    return source_type in _ATTACHMENT_SOURCE_TYPES or chunk_kind in _ATTACHMENT_SOURCE_TYPES


def _format_cross_task_document(document: Document) -> tuple[str, dict[str, str]] | None:
    content = document.page_content.strip()
    if not content:
        return None

    metadata = document.metadata or {}
    source = {
        "task_id": str(metadata.get("task_id") or "").strip(),
        "task_title": str(metadata.get("task_title") or "").strip(),
        "task_status": str(metadata.get("task_status") or "").strip(),
        "source_type": str(metadata.get("source_type") or "").strip(),
        "chunk_id": str(metadata.get("chunk_id") or "").strip(),
    }
    source_text = (
        f"Задача: {source['task_title'] or source['task_id'] or 'неизвестно'} "
        f"(id: {source['task_id'] or 'нет'}, статус: {source['task_status'] or 'нет'}, "
        f"source_type: {source['source_type'] or 'нет'}, chunk_id: {source['chunk_id'] or 'нет'})"
    )
    return f"{source_text}\n{content}", source


def _resolve_rag_context_scope(*, has_attachments: bool, has_cross_task: bool) -> str:
    if has_attachments and has_cross_task:
        return "attachments+cross_task"
    if has_attachments:
        return "attachments"
    if has_cross_task:
        return "cross_task"
    return "none"


def _prepare_qa_request(state: QAAgentGraphState) -> QAAgentGraphState:
    validation_result = state.get("validation_result") or {}
    related_titles = ", ".join(
        str(item["title"])
        for item in list(state.get("related_tasks", []))[:3]
        if "title" in item
    )
    issues = list(validation_result.get("issues", []))
    questions = list(validation_result.get("questions", []))
    message_content = str(state.get("message_content", "")).strip()

    return {
        "related_titles": related_titles,
        "issues": issues,
        "questions": questions,
        "analysis_mode": _FIXED_ANALYSIS_MODE,
        "needs_rag": _FIXED_NEEDS_RAG,
        "needs_verification": _FIXED_NEEDS_VERIFICATION,
        "retrieval_query": message_content,
        "retrieval_limit": _FIXED_RETRIEVAL_LIMIT,
        "focus_points": [],
        "canonical_question_hint": _normalize_validation_question(
            None,
            fallback_question=message_content,
        ),
    }


async def _collect_qa_context(state: QAAgentGraphState) -> QAAgentGraphState:
    task_id = str(state.get("task_id") or "").strip()
    project_id = str(state.get("project_id") or "").strip()
    needs_rag = bool(state.get("needs_rag"))
    retrieval_query = str(state.get("retrieval_query", "")).strip()
    retrieval_limit = int(state.get("retrieval_limit", 3))
    collect_attachments = bool(task_id)
    query_text = retrieval_query or str(state.get("message_content", ""))

    rag_documents = (
        await QdrantService.search_task_knowledge(
            task_id=task_id,
            query_text=query_text,
            limit=retrieval_limit,
            include_source_types=sorted(_ATTACHMENT_SOURCE_TYPES),
        )
        if collect_attachments
        else []
    )
    attachment_documents = [
        document
        for document in rag_documents
        if _is_attachment_document(document) and document.page_content.strip()
    ]
    rag_snippets = [document.page_content for document in attachment_documents]
    rag_chunk_ids = [
        str(document.metadata.get("chunk_id"))
        for document in attachment_documents
        if document.metadata.get("chunk_id")
    ]
    attachment_filenames = [
        str(document.metadata.get("filename"))
        for document in attachment_documents
        if document.metadata.get("filename")
    ]
    cross_task_documents = (
        await QdrantService.search_project_task_knowledge(
            project_id=project_id,
            query_text=query_text,
            exclude_task_id=task_id or None,
            limit=retrieval_limit,
        )
        if needs_rag and project_id
        else []
    )
    cross_task_snippets: list[str] = []
    cross_task_sources: list[dict[str, str]] = []
    for document in cross_task_documents:
        formatted = _format_cross_task_document(document)
        if formatted is None:
            continue
        snippet, source = formatted
        source_task_id = source.get("task_id", "")
        if task_id and source_task_id == task_id:
            continue
        cross_task_snippets.append(snippet)
        cross_task_sources.append(source)

    cross_task_chunk_ids = [
        source["chunk_id"] for source in cross_task_sources if source.get("chunk_id")
    ]
    cross_task_ids = list(
        dict.fromkeys(source["task_id"] for source in cross_task_sources if source.get("task_id"))
    )

    validation_result = state.get("validation_result") or {}
    issues = list(state.get("issues", []))
    questions = list(state.get("questions", []))
    related_titles = str(state.get("related_titles", ""))
    focus_points = list(state.get("focus_points", []))
    rag_context = "\n\n".join(f"- {snippet}" for snippet in rag_snippets) if rag_snippets else "нет"
    cross_task_context = (
        "\n\n".join(f"- {snippet}" for snippet in cross_task_snippets)
        if cross_task_snippets
        else "нет"
    )
    rag_context_scope = _resolve_rag_context_scope(
        has_attachments=bool(rag_snippets),
        has_cross_task=bool(cross_task_snippets),
    )
    all_chunk_ids = [*rag_chunk_ids, *cross_task_chunk_ids]

    return {
        "rag_snippets": rag_snippets,
        "rag_chunk_ids": all_chunk_ids,
        "attachment_filenames": attachment_filenames,
        "cross_task_snippets": cross_task_snippets,
        "cross_task_chunk_ids": cross_task_chunk_ids,
        "cross_task_ids": cross_task_ids,
        "cross_task_sources": cross_task_sources,
        "rag_context_scope": rag_context_scope,
        "answer_system_prompt": QA_ANSWER_SYSTEM_PROMPT,
        "answer_user_prompt": (
            f"Режим анализа: {state.get('analysis_mode', 'direct')}\n"
            f"Фокус анализа: {focus_points or 'не задан'}\n"
            f"Название задачи: {state.get('task_title', '')}\n"
            f"Статус задачи: {state.get('task_status', '')}\n"
            f"Описание задачи:\n{state.get('task_content', '')}\n\n"
            f"Дополнительный контекст из вложений:\n{rag_context}\n\n"
            "Контекст из других задач проекта:\n"
            "Используй этот блок только как справочный. Если он конфликтует с текущей задачей, "
            "приоритет у текущей задачи. Не переноси требования из другой задачи "
            "без явного основания.\n"
            f"{cross_task_context}\n\n"
            f"Вопрос пользователя:\n{state.get('message_content', '')}\n\n"
            f"Вердикт проверки: {validation_result.get('verdict', 'нет')}\n"
            f"Замечания проверки: {issues}\n"
            f"Открытые вопросы проверки: {questions}\n"
            f"Связанные задачи: {related_titles or 'нет'}"
        ),
    }


async def _invoke_qa_answer(state: QAAgentGraphState) -> QAAgentGraphState:
    db = state.get("db")
    if db is None:
        return {
            "answer_ok": False,
            "answer_error_message": None,
            "answer_provider_kind": None,
            "answer_model": None,
            "answer_payload": None,
            "response": "",
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=QA_ANSWER_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get("answer_system_prompt", "")),
        user_prompt=str(state.get("answer_user_prompt", "")),
        prompt_key=QA_ANSWER_AGENT_KEY,
    )
    return {
        "answer_ok": bool(result.ok),
        "answer_error_message": result.error_message,
        "answer_provider_kind": result.provider_kind,
        "answer_model": result.model,
        "answer_payload": (
            _extract_json_payload(result.text or "")
            if result.ok and result.text
            else None
        ),
        "response": result.text or "",
    }


def _route_after_qa_answer(
    state: QAAgentGraphState,
) -> Literal["prepare_qa_verification", "finalize_qa_response"]:
    if not state.get("answer_ok") or state.get("answer_payload") is None:
        return "finalize_qa_response"

    payload = state.get("answer_payload") or {}
    answer_text = str(payload.get("answer") or state.get("response", "")).strip()
    confidence = _normalize_confidence(payload.get("confidence"), answer_text)
    if confidence == "low":
        return "finalize_qa_response"
    if state.get("needs_verification") or state.get("analysis_mode") == "deep":
        return "prepare_qa_verification"
    return "finalize_qa_response"


def _prepare_qa_verification(state: QAAgentGraphState) -> QAAgentGraphState:
    payload = state.get("answer_payload") or {}
    draft_answer = str(payload.get("answer") or state.get("response", "")).strip()
    draft_confidence = _normalize_confidence(payload.get("confidence"), draft_answer)
    rag_context = (
        "\n\n".join(f"- {snippet}" for snippet in list(state.get("rag_snippets", [])))
        if state.get("rag_snippets")
        else "нет"
    )
    cross_task_context = (
        "\n\n".join(f"- {snippet}" for snippet in list(state.get("cross_task_snippets", [])))
        if state.get("cross_task_snippets")
        else "нет"
    )
    validation_result = state.get("validation_result") or {}

    return {
        "verify_system_prompt": QA_VERIFIER_SYSTEM_PROMPT,
        "verify_user_prompt": (
            f"Название задачи: {state.get('task_title', '')}\n"
            f"Описание задачи:\n{state.get('task_content', '')}\n\n"
            f"Дополнительный контекст из вложений:\n{rag_context}\n\n"
            "Контекст из других задач проекта:\n"
            "Используй этот блок только как справочный. Если он конфликтует с текущей задачей, "
            "приоритет у текущей задачи.\n"
            f"{cross_task_context}\n\n"
            f"Вердикт проверки: {validation_result.get('verdict', 'нет')}\n"
            f"Draft answer:\n{draft_answer}\n\n"
            f"Draft confidence: {draft_confidence}\n"
            f"Вопрос пользователя:\n{state.get('message_content', '')}"
        ),
    }


async def _invoke_qa_verifier(state: QAAgentGraphState) -> QAAgentGraphState:
    db = state.get("db")
    if db is None:
        return {
            "verify_ok": False,
            "verify_error_message": None,
            "verify_provider_kind": None,
            "verify_model": None,
            "verify_payload": None,
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=QA_VERIFIER_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get("verify_system_prompt", "")),
        user_prompt=str(state.get("verify_user_prompt", "")),
        prompt_key=QA_VERIFIER_AGENT_KEY,
    )
    return {
        "verify_ok": bool(result.ok),
        "verify_error_message": result.error_message,
        "verify_provider_kind": result.provider_kind,
        "verify_model": result.model,
        "verify_payload": (
            _extract_json_payload(result.text or "")
            if result.ok and result.text
            else None
        ),
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
    rag_snippets = list(state.get("rag_snippets", []))
    if rag_snippets:
        fallback_parts.append(
            "Найден дополнительный контекст во вложениях: " + rag_snippets[0][:220]
        )
    cross_task_snippets = list(state.get("cross_task_snippets", []))
    if cross_task_snippets:
        fallback_parts.append(
            "Найден справочный контекст из других задач проекта: "
            + cross_task_snippets[0][:220]
        )
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
    if state.get("answer_error_message") or state.get("verify_error_message"):
        fallback_parts.append(
            "LLM временно недоступна, поэтому ниже краткое резервное резюме."
        )

    message_content = str(state.get("message_content", ""))
    canonical_question_hint = state.get("canonical_question_hint")
    return (
        " ".join(fallback_parts),
        _normalize_validation_question(
            canonical_question_hint,
            fallback_question=message_content,
        ),
    )


def _finalize_qa_response(state: QAAgentGraphState) -> QAAgentGraphState:
    answer_payload = state.get("answer_payload") or {}
    verify_payload = state.get("verify_payload") if state.get("verify_ok") else None
    response = str(state.get("response", "")).strip()
    confidence = _normalize_confidence(None, response)
    validation_backlog_question: str | None = None

    if state.get("answer_ok") and answer_payload:
        response = str(answer_payload.get("answer") or response).strip()
        confidence = _normalize_confidence(answer_payload.get("confidence"), response)
        if confidence == "low":
            validation_backlog_question = _normalize_validation_question(
                answer_payload.get("canonical_question") or state.get("canonical_question_hint"),
                fallback_question=str(state.get("message_content", "")),
            )
    elif not state.get("answer_ok"):
        response, validation_backlog_question = _build_fallback_response(state)
        confidence = "low"

    if verify_payload is not None:
        verified_response = str(verify_payload.get("final_answer") or response).strip()
        response = verified_response or response
        confidence = _normalize_confidence(verify_payload.get("confidence"), response)
        if confidence == "low":
            validation_backlog_question = _normalize_validation_question(
                verify_payload.get("canonical_question") or validation_backlog_question,
                fallback_question=str(state.get("message_content", "")),
            )

    if confidence == "low":
        response = _append_backlog_notice(response)

    llm_stages = {
        "answer": _build_llm_stage_ref(
            provider_kind=state.get("answer_provider_kind"),
            model=state.get("answer_model"),
            ok=bool(state.get("answer_ok")),
        ),
    }
    if state.get("verify_ok") or state.get("verify_payload") is not None:
        llm_stages["verifier"] = _build_llm_stage_ref(
            provider_kind=state.get("verify_provider_kind"),
            model=state.get("verify_model"),
            ok=bool(state.get("verify_ok")),
        )

    rag_context_scope = str(state.get("rag_context_scope", "none"))
    collection = "tasks"
    if state.get("rag_chunk_ids"):
        collection = "task_knowledge"
    elif rag_context_scope == "attachments":
        collection = "task_attachments"

    return {
        "agent_name": QA_AGENT_NAME,
        "message_type": "agent_answer",
        "response": response,
        "source_ref": {
            "collection": collection,
            "provider_kind": state.get("answer_provider_kind"),
            "model": state.get("answer_model"),
            "answer_confidence": confidence,
            "analysis_mode": str(state.get("analysis_mode", "direct")),
            "focus_points": list(state.get("focus_points", [])),
            "validation_backlog_question": validation_backlog_question,
            "chunk_ids": list(state.get("rag_chunk_ids", [])),
            "rag_context_scope": rag_context_scope,
            "attachment_filenames": list(state.get("attachment_filenames", [])),
            "cross_task_chunk_ids": list(state.get("cross_task_chunk_ids", [])),
            "cross_task_ids": list(state.get("cross_task_ids", [])),
            "cross_task_sources": list(state.get("cross_task_sources", [])),
            "related_task_ids": [
                item["task_id"]
                for item in list(state.get("related_tasks", []))
                if "task_id" in item
            ],
            "llm_stages": llm_stages,
            "agent_key": QA_AGENT_KEY,
            "agent_description": QA_AGENT_DESCRIPTION,
            "routing_mode": str(state.get("routing_mode", "auto")),
        },
    }


@lru_cache
def get_qa_agent_graph():
    graph = StateGraph(QAAgentGraphState)
    graph.add_node("prepare_qa_request", _prepare_qa_request)
    graph.add_node("collect_qa_context", _collect_qa_context)
    graph.add_node("invoke_qa_answer", _invoke_qa_answer)
    graph.add_node("prepare_qa_verification", _prepare_qa_verification)
    graph.add_node("invoke_qa_verifier", _invoke_qa_verifier)
    graph.add_node("finalize_qa_response", _finalize_qa_response)
    graph.add_edge(START, "prepare_qa_request")
    graph.add_edge("prepare_qa_request", "collect_qa_context")
    graph.add_edge("collect_qa_context", "invoke_qa_answer")
    graph.add_conditional_edges(
        "invoke_qa_answer",
        _route_after_qa_answer,
        {
            "prepare_qa_verification": "prepare_qa_verification",
            "finalize_qa_response": "finalize_qa_response",
        },
    )
    graph.add_edge("prepare_qa_verification", "invoke_qa_verifier")
    graph.add_edge("invoke_qa_verifier", "finalize_qa_response")
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
