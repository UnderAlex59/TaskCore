from __future__ import annotations

from typing import Any, TypedDict

import pytest
from httpx import AsyncClient
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.graph_run_event import GraphRunEvent
from app.models.graph_run_log import GraphRunLog
from app.models.llm_request_log import LLMRequestLog
from app.models.llm_runtime_settings import LLMRuntimeSettings
from app.services.graph_run_tracing import (
    GRAPH_NODE_CONTEXT,
    GRAPH_RUN_CONTEXT,
    run_traced_graph,
    traced_condition,
    traced_node,
)
from app.services.llm_runtime_service import LLMRuntimeService

pytestmark = pytest.mark.requires_db


class DemoState(TypedDict, total=False):
    db: Any
    result: str
    task_id: str | None
    project_id: str | None
    actor_user_id: str | None


async def register_and_login(
    client: AsyncClient,
    *,
    email: str,
    full_name: str,
) -> str:
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "StrongPass1",
            "full_name": full_name,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": email, "password": "StrongPass1"},
    )
    assert login_response.status_code == 200
    return str(login_response.json()["access_token"])


def _build_demo_graph():
    graph = StateGraph(DemoState)
    graph.add_node("prepare", traced_node("prepare", lambda state: {"result": "ok"}))
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", END)
    return graph.compile()


def _build_failing_graph():
    def fail(_: DemoState) -> DemoState:
        raise RuntimeError("node failed")

    graph = StateGraph(DemoState)
    graph.add_node("fail", traced_node("fail", fail))
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile()


def _build_conditional_graph():
    def route(_: DemoState) -> str:
        return "finish"

    graph = StateGraph(DemoState)
    graph.add_node("prepare", traced_node("prepare", lambda state: {"result": "ok"}))
    graph.add_node("finish", traced_node("finish", lambda state: {"result": state["result"]}))
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        traced_condition("route_after_prepare", "prepare", {"finish": "finish"}, route),
        {"finish": "finish"},
    )
    graph.add_edge("finish", END)
    return graph.compile()


@pytest.mark.asyncio
async def test_traced_graph_writes_successful_run_and_events() -> None:
    async with AsyncSessionLocal() as db:
        state = await run_traced_graph(
            graph_key="demo_graph",
            graph=_build_demo_graph(),
            input_state={"db": db, "task_id": None, "project_id": None, "actor_user_id": None},
            source="test",
        )

    assert state["result"] == "ok"
    async with AsyncSessionLocal() as db:
        run = (await db.scalars(select(GraphRunLog).where(GraphRunLog.graph_key == "demo_graph"))).one()
        events = (
            await db.scalars(select(GraphRunEvent).where(GraphRunEvent.graph_run_id == run.id))
        ).all()

    assert run.status == "success"
    assert run.input_preview is not None
    assert run.input_preview["db"] == "[omitted]"
    assert run.final_state_preview == {"result": "ok"}
    assert len(events) == 1
    assert events[0].event_type == "node"
    assert events[0].node_name == "prepare"
    assert events[0].payload is not None
    assert events[0].payload["input_preview"]["db"] == "[omitted]"
    assert events[0].payload["result"] == {"result": "ok"}
    assert events[0].payload["result_preview"] == {"result": "ok"}
    assert [event.sequence for event in events] == sorted(event.sequence for event in events)


@pytest.mark.asyncio
async def test_traced_graph_writes_failed_run_and_reraises() -> None:
    async with AsyncSessionLocal() as db:
        with pytest.raises(RuntimeError, match="node failed"):
            await run_traced_graph(
                graph_key="failing_graph",
                graph=_build_failing_graph(),
                input_state={"db": db, "task_id": None, "project_id": None, "actor_user_id": None},
                source="test",
            )

    async with AsyncSessionLocal() as db:
        run = (await db.scalars(select(GraphRunLog).where(GraphRunLog.graph_key == "failing_graph"))).one()
        event = (
            await db.scalars(
                select(GraphRunEvent)
                .where(GraphRunEvent.graph_run_id == run.id, GraphRunEvent.event_type == "node")
            )
        ).one()

    assert run.status == "error"
    assert run.error_message == "node failed"
    assert event.status == "error"
    assert event.node_name == "fail"
    assert event.error_message == "node failed"
    assert event.payload is not None
    assert event.payload["input_preview"]["db"] == "[omitted]"


@pytest.mark.asyncio
async def test_traced_condition_writes_selected_transition() -> None:
    async with AsyncSessionLocal() as db:
        await run_traced_graph(
            graph_key="conditional_graph",
            graph=_build_conditional_graph(),
            input_state={"db": db, "task_id": None, "project_id": None, "actor_user_id": None},
            source="test",
        )

    async with AsyncSessionLocal() as db:
        run = (
            await db.scalars(select(GraphRunLog).where(GraphRunLog.graph_key == "conditional_graph"))
        ).one()
        transition = (
            await db.scalars(
                select(GraphRunEvent).where(
                    GraphRunEvent.graph_run_id == run.id,
                    GraphRunEvent.event_type == "transition",
                )
            )
        ).one()

    assert transition.node_name == "prepare"
    assert transition.payload is not None
    assert transition.payload["selected"] == ["finish"]
    assert transition.payload["target_nodes"] == ["finish"]
    assert transition.payload["reason"] == "finish"
    assert transition.payload["condition_input_preview"]["db"] == "[omitted]"


@pytest.mark.asyncio
async def test_runtime_toggle_disables_graph_run_monitoring() -> None:
    async with AsyncSessionLocal() as db:
        runtime = await db.get(LLMRuntimeSettings, 1)
        if runtime is None:
            runtime = LLMRuntimeSettings(
                id=1,
                prompt_log_mode="full",
                graph_monitoring_enabled=False,
            )
            db.add(runtime)
        else:
            runtime.graph_monitoring_enabled = False
        await db.commit()

        state = await run_traced_graph(
            graph_key="disabled_graph",
            graph=_build_demo_graph(),
            input_state={"db": db, "task_id": None, "project_id": None, "actor_user_id": None},
            source="test",
        )

    assert state["result"] == "ok"
    async with AsyncSessionLocal() as db:
        run = await db.scalar(select(GraphRunLog).where(GraphRunLog.graph_key == "disabled_graph"))
        runtime = await db.get(LLMRuntimeSettings, 1)
        if runtime is not None:
            runtime.graph_monitoring_enabled = True
            await db.commit()
    assert run is None


@pytest.mark.asyncio
async def test_llm_request_log_receives_current_graph_context() -> None:
    async with AsyncSessionLocal() as db:
        run = GraphRunLog(graph_key="context_graph", status="running")
        db.add(run)
        await db.commit()
        run_id = run.id

        run_token = GRAPH_RUN_CONTEXT.set(run_id)
        node_token = GRAPH_NODE_CONTEXT.set("invoke_llm")
        try:
            LLMRuntimeService._add_request_log(
                db,
                prompt_log_mode="metadata_only",
                request_kind="chat",
                actor_user_id=None,
                task_id=None,
                project_id=None,
                agent_key="qa",
                config=type("Config", (), {
                    "id": None,
                    "provider_kind": "openai",
                    "model": "test-model",
                })(),
                status="success",
                latency_ms=10,
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                estimated_cost_usd=None,
                request_messages=None,
                response_text=None,
                error_message=None,
            )
            await db.commit()
        finally:
            GRAPH_NODE_CONTEXT.reset(node_token)
            GRAPH_RUN_CONTEXT.reset(run_token)

    async with AsyncSessionLocal() as db:
        log = (await db.scalars(select(LLMRequestLog).where(LLMRequestLog.graph_run_id == run_id))).one()

    assert log.graph_node_name == "invoke_llm"


@pytest.mark.asyncio
async def test_admin_can_list_and_view_graph_runs(client: AsyncClient) -> None:
    token = await register_and_login(
        client,
        email="graph-admin@example.com",
        full_name="Graph Admin",
    )
    async with AsyncSessionLocal() as db:
        run = GraphRunLog(graph_key="chat_graph", status="success", source="test")
        db.add(run)
        await db.flush()
        db.add_all([
            GraphRunEvent(
                graph_run_id=run.id,
                sequence=1,
                event_type="node",
                node_name="invoke_agent_subgraph",
                namespace="chat_graph",
                status="success",
                payload={
                    "graph_key": "chat_graph",
                    "input_preview": {"message": "in"},
                    "node_name": "invoke_agent_subgraph",
                    "result": {"response": "ok"},
                    "result_preview": {"response": "ok"},
                },
            ),
            GraphRunEvent(
                graph_run_id=run.id,
                sequence=2,
                event_type="node",
                node_name="prepare_qa_request",
                namespace="chat_graph / invoke_agent_subgraph / qa_agent_graph",
                status="success",
                payload={
                    "graph_key": "qa_agent_graph",
                    "input_preview": {"message": "question"},
                    "node_name": "prepare_qa_request",
                    "result": {"message_content": "question"},
                    "result_preview": {"message_content": "question"},
                },
            ),
            GraphRunEvent(
                graph_run_id=run.id,
                sequence=3,
                event_type="transition",
                node_name="orchestrate_chat_request",
                namespace="chat_graph",
                status="success",
                payload={
                    "condition": "route_chat_request",
                    "condition_input_preview": {"intent": "qa"},
                    "graph_key": "chat_graph",
                    "reason": "collect_related_tasks",
                    "selected": ["collect_related_tasks"],
                    "source_node": "orchestrate_chat_request",
                    "target_nodes": ["collect_related_tasks"],
                },
            ),
            GraphRunEvent(
                graph_run_id=run.id,
                sequence=4,
                event_type="debug",
                node_name=None,
                status="success",
                payload={"step": "legacy noise"},
            ),
        ])
        await db.commit()
        run_id = run.id

    headers = {"Authorization": f"Bearer {token}"}
    list_response = await client.get("/admin/monitoring/graphs/runs", headers=headers)
    detail_response = await client.get(f"/admin/monitoring/graphs/runs/{run_id}", headers=headers)
    summary_response = await client.get("/admin/monitoring/graphs/summary", headers=headers)

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["graph_key"] == "chat_graph"
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["node_tree"][0]["node_name"] == "invoke_agent_subgraph"
    assert detail_payload["node_tree"][0]["input_preview"] == {"message": "in"}
    assert detail_payload["node_tree"][0]["children"][0]["node_name"] == "prepare_qa_request"
    assert detail_payload["transitions"][0]["selected"] == ["collect_related_tasks"]
    assert detail_payload["transitions"][0]["reason"] == "collect_related_tasks"
    assert detail_payload["graph_views"]
    assert "nodes" in detail_payload["graph_views"][0]
    assert "executed_edge_ids" in detail_payload["graph_views"][0]
    assert summary_response.status_code == 200
    assert summary_response.json()["runs_total"] >= 1
