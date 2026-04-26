from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.attachment_vision_graph import VISION_AGENT_KEY
from app.agents.state import VisionTestState
from app.models.llm_provider_config import LLMProviderConfig
from app.services.llm_runtime_service import LLMRuntimeService

DEFAULT_VISION_TEST_PROMPT = (
    "Извлеки весь читаемый текст с изображения. "
    "Сохрани естественный порядок чтения сверху вниз и слева направо. "
    "Не пересказывай изображение и не добавляй пояснения от себя. "
    "Неразборчивые фрагменты помечай как [неразборчиво]. "
    "Ответ дай простым текстом без Markdown."
)


class VisionTestGraphState(VisionTestState, total=False):
    db: Any
    image_bytes: bytes


async def _invoke_vision_test(state: VisionTestGraphState) -> VisionTestGraphState:
    db = state.get("db")
    image_bytes = state.get("image_bytes", b"")
    if db is None or not image_bytes:
        return {
            "ok": False,
            "message": "Изображение не передано.",
            "result_text": None,
        }

    result = await LLMRuntimeService.invoke_vision(
        db,
        agent_key=VISION_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=None,
        project_id=None,
        image_bytes=image_bytes,
        content_type=str(state.get("content_type") or "application/octet-stream"),
        prompt=str(state.get("prompt") or DEFAULT_VISION_TEST_PROMPT),
    )
    provider_name: str | None = None
    if result.provider_config_id:
        provider = await db.get(LLMProviderConfig, result.provider_config_id)
        if provider is not None:
            provider_name = provider.name

    return {
        "ok": result.ok,
        "provider_config_id": result.provider_config_id,
        "provider_kind": result.provider_kind,
        "provider_name": provider_name,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "result_text": result.text.strip() if result.text else None,
        "message": result.error_message or result.text or "Пустой ответ модели.",
    }


@lru_cache
def get_vision_test_graph():
    graph = StateGraph(VisionTestGraphState)
    graph.add_node("invoke_vision_test", _invoke_vision_test)
    graph.add_edge(START, "invoke_vision_test")
    graph.add_edge("invoke_vision_test", END)
    return graph.compile()


async def run_vision_test_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    image_bytes: bytes,
    content_type: str,
    prompt: str = DEFAULT_VISION_TEST_PROMPT,
) -> VisionTestState:
    state = await get_vision_test_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "image_bytes": image_bytes,
            "content_type": content_type,
            "prompt": prompt,
        }
    )
    return {
        "ok": bool(state.get("ok")),
        "provider_config_id": state.get("provider_config_id"),
        "provider_kind": str(state.get("provider_kind") or ""),
        "provider_name": state.get("provider_name"),
        "model": str(state.get("model") or ""),
        "latency_ms": state.get("latency_ms"),
        "content_type": str(content_type),
        "prompt": str(prompt),
        "result_text": state.get("result_text"),
        "message": str(state.get("message") or ""),
    }
