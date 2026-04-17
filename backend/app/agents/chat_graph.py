from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.chat_agents.base import ChatAgentContext
from app.agents.chat_agents.registry import dispatch_chat_agent
from app.agents.state import ChatState


class ChatGraphState(ChatState, total=False):
    db: Any
    task_id: str | None
    project_id: str | None
    actor_user_id: str | None
    task_title: str
    task_status: str
    task_content: str
    message_type: str
    message_content: str
    validation_result: dict | None
    related_tasks: list[dict[str, object]]
    requested_agent: str | None
    raw_message_content: str | None


def _prepare_chat_request(state: ChatGraphState) -> ChatGraphState:
    return {
        "message_content": str(state.get("message_content", "")).strip(),
        "raw_message_content": state.get("raw_message_content") or state.get("message_content"),
    }


async def _dispatch_chat_request(state: ChatGraphState) -> ChatGraphState:
    result = await dispatch_chat_agent(
        ChatAgentContext(
            db=state.get("db"),
            task_title=str(state.get("task_title", "")),
            task_status=str(state.get("task_status", "")),
            task_content=str(state.get("task_content", "")),
            message_type=str(state.get("message_type", "")),
            message_content=str(state.get("message_content", "")),
            validation_result=state.get("validation_result"),
            related_tasks=list(state.get("related_tasks", [])),
            actor_user_id=state.get("actor_user_id"),
            task_id=state.get("task_id"),
            project_id=state.get("project_id"),
            requested_agent=state.get("requested_agent"),
            raw_message_content=state.get("raw_message_content"),
        )
    )

    payload: ChatGraphState = {
        "agent_name": result.agent_name,
        "message_type": result.message_type,
        "response": result.response,
        "source_ref": result.source_ref,
    }
    if result.proposal_text is not None:
        payload["proposal_text"] = result.proposal_text
    return payload


def _finalize_chat_response(state: ChatGraphState) -> ChatGraphState:
    final_state: ChatGraphState = {
        "agent_name": str(state.get("agent_name", "")),
        "message_type": str(state.get("message_type", "")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
    }
    proposal_text = state.get("proposal_text")
    if proposal_text is not None:
        final_state["proposal_text"] = str(proposal_text)
    return final_state


@lru_cache
def get_chat_graph():
    graph = StateGraph(ChatGraphState)
    graph.add_node("prepare_chat_request", _prepare_chat_request)
    graph.add_node("dispatch_chat_request", _dispatch_chat_request)
    graph.add_node("finalize_chat_response", _finalize_chat_response)
    graph.add_edge(START, "prepare_chat_request")
    graph.add_edge("prepare_chat_request", "dispatch_chat_request")
    graph.add_edge("dispatch_chat_request", "finalize_chat_response")
    graph.add_edge("finalize_chat_response", END)
    return graph.compile()


async def run_chat_graph(
    *,
    db,
    task_id: str | None,
    project_id: str | None,
    actor_user_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    message_type: str,
    message_content: str,
    validation_result: dict | None,
    related_tasks: list[dict[str, object]],
    requested_agent: str | None = None,
    raw_message_content: str | None = None,
) -> ChatState:
    state = await get_chat_graph().ainvoke(
        {
            "db": db,
            "task_id": task_id,
            "project_id": project_id,
            "actor_user_id": actor_user_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "message_type": message_type,
            "message_content": message_content,
            "validation_result": validation_result,
            "related_tasks": related_tasks,
            "requested_agent": requested_agent,
            "raw_message_content": raw_message_content,
        }
    )

    result: ChatState = {
        "agent_name": str(state.get("agent_name", "")),
        "message_type": str(state.get("message_type", "")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
    }
    proposal_text = state.get("proposal_text")
    if proposal_text is not None:
        result["proposal_text"] = str(proposal_text)
    return result
