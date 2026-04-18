from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status
from langgraph.graph import END, START, StateGraph

from app.agents.state import ProviderTestState


class ProviderTestGraphState(ProviderTestState, total=False):
    db: Any
    provider_id: str
    actor_user_id: str | None
    provider_kind: str
    model: str
    invocation_message: str


async def _load_provider(state: ProviderTestGraphState) -> ProviderTestGraphState:
    db = state.get("db")
    provider_id = state.get("provider_id")
    if db is None or not provider_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Контекст проверки провайдера не инициализирован",
        )

    from app.models.llm_provider_config import LLMProviderConfig

    provider = await db.get(LLMProviderConfig, str(provider_id))
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль провайдера не найден",
        )

    return {
        "provider_kind": str(provider.provider_kind),
        "model": str(provider.model),
    }


async def _invoke_provider_test(state: ProviderTestGraphState) -> ProviderTestGraphState:
    db = state.get("db")
    provider_id = state.get("provider_id")
    if db is None or not provider_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Контекст проверки провайдера не инициализирован",
        )

    from app.models.llm_provider_config import LLMProviderConfig
    from app.services.llm_runtime_service import LLMRuntimeService

    provider = await db.get(LLMProviderConfig, str(provider_id))
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль провайдера не найден",
        )

    result = await LLMRuntimeService.test_provider(
        db,
        config=provider,
        actor_user_id=str(state.get("actor_user_id")) if state.get("actor_user_id") else None,
    )
    return {
        "ok": bool(result.ok),
        "latency_ms": result.latency_ms,
        "invocation_message": str(
            result.text or result.error_message or "Пустой ответ от провайдера"
        ),
    }


def _finalize_provider_test(state: ProviderTestGraphState) -> ProviderTestGraphState:
    return {
        "ok": bool(state.get("ok", False)),
        "provider_kind": str(state.get("provider_kind", "")),
        "model": str(state.get("model", "")),
        "latency_ms": state.get("latency_ms"),
        "message": str(state.get("invocation_message", "")),
    }


@lru_cache
def get_provider_test_graph():
    graph = StateGraph(ProviderTestGraphState)
    graph.add_node("load_provider", _load_provider)
    graph.add_node("invoke_provider_test", _invoke_provider_test)
    graph.add_node("finalize_provider_test", _finalize_provider_test)
    graph.add_edge(START, "load_provider")
    graph.add_edge("load_provider", "invoke_provider_test")
    graph.add_edge("invoke_provider_test", "finalize_provider_test")
    graph.add_edge("finalize_provider_test", END)
    return graph.compile()


async def run_provider_test_graph(
    *,
    db,
    provider_id: str,
    actor_user_id: str | None,
) -> ProviderTestState:
    state = await get_provider_test_graph().ainvoke(
        {
            "db": db,
            "provider_id": provider_id,
            "actor_user_id": actor_user_id,
        }
    )
    return {
        "ok": bool(state.get("ok", False)),
        "provider_kind": str(state.get("provider_kind", "")),
        "model": str(state.get("model", "")),
        "latency_ms": state.get("latency_ms"),
        "message": str(state.get("message", "")),
    }
