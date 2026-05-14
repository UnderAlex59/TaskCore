from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.chat_agents.base import ChatAgentContext
from app.agents.chat_routing import analyze_chat_routing
from app.agents.state import ChatState
from app.agents.subgraph_registry import (
    find_agent_subgraph,
    list_agent_subgraphs,
    run_agent_subgraph,
)
from app.services.graph_run_tracing import run_traced_graph, traced_condition, traced_node

MANAGER_AGENT_KEY = "manager"


class ChatGraphState(ChatState, total=False):
    db: Any
    task_id: str | None
    project_id: str | None
    actor_user_id: str | None
    source_message_id: str | None
    task_title: str
    task_status: str
    task_content: str
    message_type: str
    message_content: str
    validation_result: dict | None
    related_tasks: list[dict[str, object]]
    requested_agent: str | None
    raw_message_content: str | None
    routing: dict[str, object]
    routing_reason: str
    target_agent_key: str | None
    routing_mode: str


def _build_chat_agent_context(state: ChatGraphState) -> ChatAgentContext:
    return ChatAgentContext(
        db=state.get("db"),
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        task_title=str(state.get("task_title", "")),
        task_status=str(state.get("task_status", "")),
        task_content=str(state.get("task_content", "")),
        message_type=str(state.get("message_type", "")),
        message_content=str(state.get("message_content", "")),
        validation_result=state.get("validation_result"),
        related_tasks=list(state.get("related_tasks", [])),
        requested_agent=state.get("requested_agent"),
        raw_message_content=state.get("raw_message_content"),
    )


def _prepare_chat_request(state: ChatGraphState) -> ChatGraphState:
    return {
        "message_content": str(state.get("message_content", "")).strip(),
        "raw_message_content": state.get("raw_message_content") or state.get("message_content"),
    }


def _build_available_routing_agents() -> list[dict[str, object]]:
    return [
        {
            "key": spec.metadata.key,
            "name": spec.metadata.name,
            "description": spec.metadata.description,
            "aliases": list(spec.metadata.aliases),
        }
        for spec in list_agent_subgraphs()
        if spec.auto_routable
    ]


def _forced_routing_ref(
    *,
    target_agent_key: str,
    message_type: str,
    reason: str,
    requested_agent: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "mode": "forced",
        "status": "routed",
        "ai_response_required": True,
        "target_agent_key": target_agent_key,
        "message_type": message_type,
        "reason": reason,
        "provider_kind": None,
        "model": None,
    }
    if requested_agent is not None:
        payload["requested_agent"] = requested_agent
    return payload


async def _orchestrate_chat_request(state: ChatGraphState) -> ChatGraphState:
    requested_agent = state.get("requested_agent")
    if requested_agent is not None:
        target_spec = find_agent_subgraph(str(requested_agent))
        if target_spec is not None:
            routing = _forced_routing_ref(
                target_agent_key=target_spec.metadata.key,
                message_type=str(state.get("message_type", "general")),
                reason="forced_agent",
                requested_agent=str(requested_agent),
            )
            return {
                "ai_response_required": True,
                "target_agent_key": target_spec.metadata.key,
                "routing_mode": "forced",
                "routing_reason": "forced_agent",
                "routing": routing,
                "source_ref": {"routing": routing},
            }
        routing = _forced_routing_ref(
            target_agent_key=MANAGER_AGENT_KEY,
            message_type="general",
            reason="unknown_forced_agent",
            requested_agent=str(requested_agent),
        )
        return {
            "ai_response_required": True,
            "target_agent_key": MANAGER_AGENT_KEY,
            "routing_mode": "forced",
            "routing_reason": "unknown_forced_agent",
            "message_type": "general",
            "routing": routing,
            "source_ref": {"routing": routing},
        }

    outcome = await analyze_chat_routing(
        db=state.get("db"),
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        task_title=str(state.get("task_title", "")),
        task_status=str(state.get("task_status", "")),
        task_content=str(state.get("task_content", "")),
        message_content=str(state.get("message_content", "")),
        available_agents=_build_available_routing_agents(),
    )
    routing = outcome.source_ref(mode="auto")

    return {
        "ai_response_required": outcome.ai_response_required,
        "target_agent_key": outcome.target_agent_key,
        "message_type": outcome.message_type,
        "routing_mode": "auto",
        "routing_reason": outcome.reason,
        "routing": routing,
        "source_ref": {"routing": routing},
    }


def _route_chat_request(state: ChatGraphState) -> Literal["collect_related_tasks", "__end__"]:
    if state.get("ai_response_required"):
        return "collect_related_tasks"
    return END


async def _collect_related_tasks(state: ChatGraphState) -> ChatGraphState:
    if state.get("related_tasks"):
        return {"related_tasks": list(state.get("related_tasks", []))}

    db = state.get("db")
    project_id = state.get("project_id")
    if db is None or not project_id:
        return {"related_tasks": []}

    task_id = state.get("task_id")
    from app.services.rag_service import RagService

    related_tasks = await RagService.search_related_tasks(
        db,
        project_id=str(project_id),
        query_text=f"{state.get('task_title', '')}\n{state.get('message_content', '')}",
        exclude_task_id=str(task_id) if task_id else None,
        limit=3,
    )
    return {
        "related_tasks": [
            {key: value for key, value in item.items()} for item in related_tasks
        ]
    }


async def _invoke_agent_subgraph(state: ChatGraphState) -> ChatGraphState:
    target_agent_key = str(state.get("target_agent_key", "")).strip()
    spec = find_agent_subgraph(target_agent_key)
    if spec is None:
        spec = find_agent_subgraph(MANAGER_AGENT_KEY)
        if spec is None:
            raise RuntimeError("Manager subgraph is not registered")

    result = await run_agent_subgraph(
        spec,
        context=_build_chat_agent_context(state),
        routing_mode=str(state.get("routing_mode", "auto")),
    )

    payload: ChatGraphState = {
        "ai_response_required": True,
        "agent_name": str(result.get("agent_name", "")),
        "message_type": str(result.get("message_type", "")),
        "response": str(result.get("response", "")),
        "source_ref": {
            **dict(result.get("source_ref", {})),
            "routing": dict(state.get("routing", {})),
        },
    }
    proposal_text = result.get("proposal_text")
    if proposal_text is not None:
        payload["proposal_text"] = str(proposal_text)
    return payload


async def _persist_chat_artifacts(state: ChatGraphState) -> ChatGraphState:
    db = state.get("db")
    task_id = state.get("task_id")
    actor_user_id = state.get("actor_user_id")
    source_message_id = state.get("source_message_id")
    if db is None or task_id is None:
        return {}

    source_ref = dict(state.get("source_ref", {}))
    project_id = state.get("project_id")
    message_type = str(state.get("message_type", ""))

    duplicate_proposal = bool(source_ref.get("duplicate_proposal"))
    should_create_proposal = (
        state.get("proposal_text") is not None or message_type == "agent_proposal"
    )
    if should_create_proposal and not duplicate_proposal:
        from app.services.audit_service import AuditService
        from app.services.proposal_service import ProposalService

        proposal = await ProposalService.create_from_message(
            str(task_id),
            project_id=str(project_id) if project_id else None,
            source_message_id=str(source_message_id) if source_message_id else None,
            proposed_by=str(actor_user_id) if actor_user_id else None,
            proposal_text=str(state.get("proposal_text", state.get("message_content", ""))),
            db=db,
        )
        source_ref["proposal_id"] = proposal.id
        if actor_user_id is not None:
            AuditService.record(
                db,
                actor_user_id=str(actor_user_id),
                event_type="chat.proposal_requested",
                entity_type="change_proposal",
                entity_id=proposal.id,
                project_id=str(project_id) if project_id else None,
                task_id=str(task_id),
                metadata={"source_message_id": source_message_id},
            )

    validation_backlog_question = source_ref.get("validation_backlog_question")
    if isinstance(validation_backlog_question, str) and validation_backlog_question.strip():
        from app.models.task import Task
        from app.services.audit_service import AuditService
        from app.services.validation_question_service import ValidationQuestionService

        task = await db.get(Task, str(task_id))
        if task is not None:
            saved_question = await ValidationQuestionService.record_chat_question(
                task,
                validation_backlog_question,
                db,
                actor_user_id=str(actor_user_id) if actor_user_id is not None else None,
            )
            if saved_question is not None:
                source_ref["validation_backlog_saved"] = True
                source_ref["validation_question_id"] = saved_question.id
                if actor_user_id is not None:
                    AuditService.record(
                        db,
                        actor_user_id=str(actor_user_id),
                        event_type="chat.validation_question_recorded",
                        entity_type="validation_question",
                        entity_id=saved_question.id,
                        project_id=str(project_id) if project_id else None,
                        task_id=str(task_id),
                        metadata={
                            "source_message_id": source_message_id,
                            "question_text": saved_question.question_text,
                            "answer_confidence": source_ref.get("answer_confidence"),
                        },
                    )

    return {"source_ref": source_ref}


def _finalize_chat_response(state: ChatGraphState) -> ChatGraphState:
    final_state: ChatGraphState = {
        "ai_response_required": bool(state.get("ai_response_required")),
        "agent_name": str(state.get("agent_name", "")),
        "message_type": str(state.get("message_type", "")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
        "routing": dict(state.get("routing", {})),
    }
    proposal_text = state.get("proposal_text")
    if proposal_text is not None:
        final_state["proposal_text"] = str(proposal_text)
    return final_state


@lru_cache
def get_chat_graph():
    graph = StateGraph(ChatGraphState)
    graph.add_node(
        "prepare_chat_request",
        traced_node("prepare_chat_request", _prepare_chat_request),
    )
    graph.add_node(
        "orchestrate_chat_request",
        traced_node("orchestrate_chat_request", _orchestrate_chat_request),
    )
    graph.add_node(
        "collect_related_tasks",
        traced_node("collect_related_tasks", _collect_related_tasks),
    )
    graph.add_node(
        "invoke_agent_subgraph",
        traced_node("invoke_agent_subgraph", _invoke_agent_subgraph),
    )
    graph.add_node(
        "persist_chat_artifacts",
        traced_node("persist_chat_artifacts", _persist_chat_artifacts),
    )
    graph.add_node(
        "finalize_chat_response",
        traced_node("finalize_chat_response", _finalize_chat_response),
    )
    graph.add_edge(START, "prepare_chat_request")
    graph.add_edge("prepare_chat_request", "orchestrate_chat_request")
    graph.add_conditional_edges(
        "orchestrate_chat_request",
        traced_condition(
            "route_chat_request",
            "orchestrate_chat_request",
            {
                "collect_related_tasks": "collect_related_tasks",
                "__end__": END,
            },
            _route_chat_request,
        ),
        {
            "collect_related_tasks": "collect_related_tasks",
            "__end__": END,
        },
    )
    graph.add_edge("collect_related_tasks", "invoke_agent_subgraph")
    graph.add_edge("invoke_agent_subgraph", "persist_chat_artifacts")
    graph.add_edge("persist_chat_artifacts", "finalize_chat_response")
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
    related_tasks: list[dict[str, object]] | None = None,
    requested_agent: str | None = None,
    raw_message_content: str | None = None,
    source_message_id: str | None = None,
) -> ChatState:
    state = await run_traced_graph(
        graph_key="chat_graph",
        graph=get_chat_graph(),
        source="chat",
        input_state=
        {
            "db": db,
            "task_id": task_id,
            "project_id": project_id,
            "actor_user_id": actor_user_id,
            "source_message_id": source_message_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "message_type": message_type,
            "message_content": message_content,
            "validation_result": validation_result,
            "related_tasks": related_tasks or [],
            "requested_agent": requested_agent,
            "raw_message_content": raw_message_content,
        }
    )

    result: ChatState = {
        "ai_response_required": bool(state.get("ai_response_required")),
        "source_ref": dict(state.get("source_ref", {})),
    }
    if not result["ai_response_required"]:
        return result

    result.update(
        {
            "agent_name": str(state.get("agent_name", "")),
            "message_type": str(state.get("message_type", "")),
            "response": str(state.get("response", "")),
            "source_ref": dict(state.get("source_ref", {})),
        }
    )
    proposal_text = state.get("proposal_text")
    if proposal_text is not None:
        result["proposal_text"] = str(proposal_text)
    return result
