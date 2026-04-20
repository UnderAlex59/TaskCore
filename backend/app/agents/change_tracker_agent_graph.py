from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.services.llm_runtime_service import LLMRuntimeService
from app.services.qdrant_service import QdrantService

CHANGE_TRACKER_AGENT_KEY = "change-tracker"
CHANGE_TRACKER_AGENT_NAME = "ChangeTrackerAgent"
CHANGE_TRACKER_AGENT_DESCRIPTION = (
    "Преобразует запросы из чата в отслеживаемые предложения по изменению требований."
)
CHANGE_TRACKER_AGENT_ALIASES = ("change", "proposal", "changes")


class ChangeTrackerGraphState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    task_id: str | None
    project_id: str | None
    task_title: str
    task_status: str
    task_content: str
    message_content: str
    routing_mode: str
    system_prompt: str
    user_prompt: str
    provider_kind: str | None
    model: str | None
    llm_ok: bool
    llm_error_message: str | None
    duplicate_match: dict[str, object] | None


def _fallback_acknowledgement() -> str:
    return (
        "Предложение по изменению зарегистрировано "
        "и ожидает проверки аналитиком или администратором. "
        "После одобрения требование будет возвращено на доработку "
        "и повторную проверку."
    )


def _prepare_change_request(state: ChangeTrackerGraphState) -> ChangeTrackerGraphState:
    return {
        "system_prompt": (
            "Ты нормализуешь запросы на изменение требований. "
            "Верни строгий JSON с ключами proposal_text и acknowledgement. "
            "proposal_text должен содержать чёткое, выполнимое изменение требования. "
            "acknowledgement должен быть одной короткой фразой для пользователя. "
            "Отвечай только на русском языке."
        ),
        "user_prompt": (
            f"Название задачи: {state.get('task_title', '')}\n"
            f"Статус задачи: {state.get('task_status', '')}\n"
            f"Описание задачи:\n{state.get('task_content', '')}\n\n"
            f"Запрошенное изменение:\n{state.get('message_content', '')}\n"
        ),
    }


async def _invoke_change_tracker_llm(state: ChangeTrackerGraphState) -> ChangeTrackerGraphState:
    db = state.get("db")
    if db is None:
        return {
            "llm_ok": False,
            "llm_error_message": None,
            "provider_kind": None,
            "model": None,
            "response": "",
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=CHANGE_TRACKER_AGENT_KEY,
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
        "response": result.text or "",
    }


async def _detect_duplicate_proposal(state: ChangeTrackerGraphState) -> ChangeTrackerGraphState:
    proposal_text = str(state.get("message_content", "")).strip()
    raw_response = str(state.get("response", "")).strip()
    if state.get("llm_ok") and raw_response:
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            proposal_text = str(payload.get("proposal_text") or proposal_text).strip()

    project_id = str(state.get("project_id") or "").strip()
    if not proposal_text or not project_id:
        return {"duplicate_match": None}

    duplicate_match = await QdrantService.find_duplicate_proposal(
        project_id=project_id,
        proposal_text=proposal_text,
    )
    return {"duplicate_match": duplicate_match}


def _finalize_change_request(state: ChangeTrackerGraphState) -> ChangeTrackerGraphState:
    proposal_text = str(state.get("message_content", ""))
    response = _fallback_acknowledgement()
    raw_response = str(state.get("response", "")).strip()

    if state.get("llm_ok") and raw_response:
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            proposal_text = str(payload.get("proposal_text") or proposal_text).strip()
            response = str(payload.get("acknowledgement") or response).strip()

    duplicate_match = state.get("duplicate_match")
    if isinstance(duplicate_match, dict):
        duplicate_task_id = str(duplicate_match.get("task_id", "")).strip()
        duplicate_proposal_id = str(duplicate_match.get("proposal_id", "")).strip()
        response = (
            "Похожее предложение уже зарегистрировано"
            + (f" в задаче {duplicate_task_id}" if duplicate_task_id else "")
            + ". Новый дубликат не сохранён."
        )
        return {
            "agent_name": CHANGE_TRACKER_AGENT_NAME,
            "message_type": "agent_answer",
            "proposal_text": proposal_text,
            "response": response,
            "source_ref": {
                "collection": "task_proposals",
                "provider_kind": state.get("provider_kind") if state.get("llm_ok") else None,
                "model": state.get("model") if state.get("llm_ok") else None,
                "fallback": not bool(state.get("llm_ok")),
                "agent_key": CHANGE_TRACKER_AGENT_KEY,
                "agent_description": CHANGE_TRACKER_AGENT_DESCRIPTION,
                "routing_mode": str(state.get("routing_mode", "auto")),
                "duplicate_proposal": True,
                "duplicate_task_id": duplicate_task_id or None,
                "duplicate_proposal_id": duplicate_proposal_id or None,
            },
        }

    return {
        "agent_name": CHANGE_TRACKER_AGENT_NAME,
        "message_type": "agent_proposal",
        "proposal_text": proposal_text,
        "response": response,
        "source_ref": {
            "collection": "task_proposals",
            "provider_kind": state.get("provider_kind") if state.get("llm_ok") else None,
            "model": state.get("model") if state.get("llm_ok") else None,
            "fallback": not bool(state.get("llm_ok")),
            "agent_key": CHANGE_TRACKER_AGENT_KEY,
            "agent_description": CHANGE_TRACKER_AGENT_DESCRIPTION,
            "routing_mode": str(state.get("routing_mode", "auto")),
        },
    }


@lru_cache
def get_change_tracker_agent_graph():
    graph = StateGraph(ChangeTrackerGraphState)
    graph.add_node("prepare_change_request", _prepare_change_request)
    graph.add_node("invoke_change_tracker_llm", _invoke_change_tracker_llm)
    graph.add_node("detect_duplicate_proposal", _detect_duplicate_proposal)
    graph.add_node("finalize_change_request", _finalize_change_request)
    graph.add_edge(START, "prepare_change_request")
    graph.add_edge("prepare_change_request", "invoke_change_tracker_llm")
    graph.add_edge("invoke_change_tracker_llm", "detect_duplicate_proposal")
    graph.add_edge("detect_duplicate_proposal", "finalize_change_request")
    graph.add_edge("finalize_change_request", END)
    return graph.compile()


async def run_change_tracker_agent_graph(
    *,
    db,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    message_content: str,
    routing_mode: str,
) -> ChatState:
    state = await get_change_tracker_agent_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "message_content": message_content,
            "routing_mode": routing_mode,
        }
    )
    result: ChatState = {
        "agent_name": str(state.get("agent_name", CHANGE_TRACKER_AGENT_NAME)),
        "message_type": str(state.get("message_type", "agent_proposal")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
    }
    if state.get("proposal_text") is not None:
        result["proposal_text"] = str(state.get("proposal_text"))
    return result
