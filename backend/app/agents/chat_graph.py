from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.chat_agents.base import ChatAgentContext
from app.agents.state import ChatState
from app.agents.subgraph_registry import (
    find_agent_subgraph,
    run_agent_subgraph,
    select_agent_subgraph,
)

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


async def _orchestrate_chat_request(state: ChatGraphState) -> ChatGraphState:
    requested_agent = state.get("requested_agent")
    if requested_agent is not None:
        target_spec = find_agent_subgraph(str(requested_agent))
        if target_spec is not None:
            return {
                "ai_response_required": True,
                "target_agent_key": target_spec.metadata.key,
                "routing_mode": "forced",
                "routing_reason": "forced_agent",
            }
        return {
            "ai_response_required": True,
            "target_agent_key": MANAGER_AGENT_KEY,
            "routing_mode": "forced",
            "routing_reason": "unknown_forced_agent",
        }

    target_spec = await select_agent_subgraph(_build_chat_agent_context(state))
    if target_spec is None:
        return {
            "ai_response_required": False,
            "target_agent_key": None,
            "routing_mode": "auto",
            "routing_reason": "background_message",
        }

    return {
        "ai_response_required": True,
        "target_agent_key": target_spec.metadata.key,
        "routing_mode": "auto",
        "routing_reason": f"auto_agent:{target_spec.metadata.key}",
    }


def _route_chat_request(state: ChatGraphState) -> str:
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
        "source_ref": dict(result.get("source_ref", {})),
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
    if (state.get("proposal_text") is not None or message_type == "agent_proposal") and not duplicate_proposal:
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
    }
    proposal_text = state.get("proposal_text")
    if proposal_text is not None:
        final_state["proposal_text"] = str(proposal_text)
    return final_state


@lru_cache
def get_chat_graph():
    graph = StateGraph(ChatGraphState)
    graph.add_node("prepare_chat_request", _prepare_chat_request)
    graph.add_node("orchestrate_chat_request", _orchestrate_chat_request)
    graph.add_node("collect_related_tasks", _collect_related_tasks)
    graph.add_node("invoke_agent_subgraph", _invoke_agent_subgraph)
    graph.add_node("persist_chat_artifacts", _persist_chat_artifacts)
    graph.add_node("finalize_chat_response", _finalize_chat_response)
    graph.add_edge(START, "prepare_chat_request")
    graph.add_edge("prepare_chat_request", "orchestrate_chat_request")
    graph.add_conditional_edges("orchestrate_chat_request", _route_chat_request)
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
    state = await get_chat_graph().ainvoke(
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
