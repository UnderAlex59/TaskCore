from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.chat_graph import (
    ChatGraphState,
    _orchestrate_chat_request,
    _prepare_chat_request,
)
from app.services.graph_run_tracing import (
    get_current_graph_run_id,
    run_traced_graph,
    traced_node,
)


class ChatRoutingEvalState(ChatGraphState, total=False):
    graph_run_id: str | None
    actual_route: dict[str, object]


def _finalize_routing_eval(state: ChatRoutingEvalState) -> ChatRoutingEvalState:
    routing = dict(state.get("routing", {}))
    actual_route: dict[str, object] = {
        "ai_response_required": bool(state.get("ai_response_required")),
        "target_agent_key": state.get("target_agent_key"),
        "message_type": str(state.get("message_type", "general")),
        "routing_mode": str(state.get("routing_mode", routing.get("mode", "auto"))),
        "routing_reason": str(state.get("routing_reason", routing.get("reason", ""))),
        "routing_status": str(routing.get("status", "")),
        "provider_kind": routing.get("provider_kind"),
        "model": routing.get("model"),
    }
    parse_error = routing.get("parse_error")
    runtime_error = routing.get("runtime_error")
    if parse_error:
        actual_route["parse_error"] = str(parse_error)
    if runtime_error:
        actual_route["runtime_error"] = str(runtime_error)
    return {
        "actual_route": actual_route,
        "ai_response_required": actual_route["ai_response_required"],
        "graph_run_id": get_current_graph_run_id(),
        "routing": routing,
        "source_ref": {"routing": routing},
        "target_agent_key": state.get("target_agent_key"),
        "message_type": actual_route["message_type"],
        "routing_mode": actual_route["routing_mode"],
        "routing_reason": actual_route["routing_reason"],
    }


@lru_cache
def get_chat_routing_eval_graph():
    graph = StateGraph(ChatRoutingEvalState)
    graph.add_node(
        "prepare_chat_request",
        traced_node("prepare_chat_request", _prepare_chat_request),
    )
    graph.add_node(
        "orchestrate_chat_request",
        traced_node("orchestrate_chat_request", _orchestrate_chat_request),
    )
    graph.add_node(
        "finalize_routing_eval",
        traced_node("finalize_routing_eval", _finalize_routing_eval),
    )
    graph.add_edge(START, "prepare_chat_request")
    graph.add_edge("prepare_chat_request", "orchestrate_chat_request")
    graph.add_edge("orchestrate_chat_request", "finalize_routing_eval")
    graph.add_edge("finalize_routing_eval", END)
    return graph.compile()


async def run_chat_routing_eval_graph(
    *,
    db: Any,
    task_id: str | None,
    project_id: str | None,
    actor_user_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    message_content: str,
    validation_result: dict | None,
    requested_agent: str | None = None,
    raw_message_content: str | None = None,
) -> ChatRoutingEvalState:
    state = await run_traced_graph(
        graph_key="chat_routing_eval_graph",
        graph=get_chat_routing_eval_graph(),
        source="orchestrator_eval",
        force_trace=True,
        input_state={
            "db": db,
            "task_id": task_id,
            "project_id": project_id,
            "actor_user_id": actor_user_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "message_type": "general",
            "message_content": message_content,
            "validation_result": validation_result,
            "related_tasks": [],
            "requested_agent": requested_agent,
            "raw_message_content": raw_message_content or message_content,
        },
    )
    return state
