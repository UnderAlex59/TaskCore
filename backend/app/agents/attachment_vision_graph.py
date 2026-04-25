from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import VisionAltTextState
from app.services.llm_runtime_service import LLMRuntimeService

VISION_AGENT_KEY = "rag-vision"
VISION_AGENT_NAME = "AttachmentVisionAgent"
VISION_AGENT_DESCRIPTION = (
    "Генерирует alt-text для изображений во вложениях задач, "
    "чтобы включать визуальный контент в семантический поиск."
)
VISION_AGENT_ALIASES: tuple[str, ...] = ("vision-alt-text", "attachment-vision")
VISION_ALT_TEXT_PROMPT = (
    "Опиши изображение для поиска по базе требований. "
    "Если это схема, макет интерфейса, таблица или диаграмма, перечисли ключевые "
    "объекты, подписи, поля, связи, состояния и бизнес-смысл. "
    "Ответ дай кратким связным текстом на русском языке без Markdown."
)


class AttachmentVisionGraphState(VisionAltTextState, total=False):
    db: Any
    actor_user_id: str | None
    image_bytes: bytes
    content_type: str
    prompt: str


async def _invoke_vision_alt_text(
    state: AttachmentVisionGraphState,
) -> AttachmentVisionGraphState:
    db = state.get("db")
    image_bytes = state.get("image_bytes", b"")
    if db is None or not image_bytes:
        return {"alt_text": None}

    result = await LLMRuntimeService.invoke_vision(
        db,
        agent_key=VISION_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        image_bytes=image_bytes,
        content_type=str(state.get("content_type") or "application/octet-stream"),
        prompt=str(state.get("prompt") or VISION_ALT_TEXT_PROMPT),
    )
    if not result.ok or not result.text:
        return {"alt_text": None}
    return {"alt_text": result.text.strip() or None}


@lru_cache
def get_attachment_vision_graph():
    graph = StateGraph(AttachmentVisionGraphState)
    graph.add_node("invoke_vision_alt_text", _invoke_vision_alt_text)
    graph.add_edge(START, "invoke_vision_alt_text")
    graph.add_edge("invoke_vision_alt_text", END)
    return graph.compile()


async def run_attachment_vision_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    image_bytes: bytes,
    content_type: str,
    prompt: str = VISION_ALT_TEXT_PROMPT,
) -> VisionAltTextState:
    state = await get_attachment_vision_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "image_bytes": image_bytes,
            "content_type": content_type,
            "prompt": prompt,
        }
    )
    return {
        "task_id": task_id,
        "project_id": project_id,
        "alt_text": state.get("alt_text"),
    }
